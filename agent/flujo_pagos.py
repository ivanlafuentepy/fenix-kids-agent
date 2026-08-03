# agent/flujo_pagos.py — Flujo de pagos (comprobantes, confirmación, agenda)
# Extraído de main.py — Paso 8 del refactor

import os
import asyncio
import logging

from agent.memory import guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.ab_test import (
    obtener_estado_flags, actualizar_estado_flags,
)
from agent.telegram_bridge import (
    enviar_a_topic,
    notificar_pago_telegram,
    reactivar_dorita,
)
from agent.meta_capi import enviar_evento_pago
from agent.pagos import (
    detectar_tipo_pago,
    registrar_pago_pendiente, confirmar_pago,
    formatear_monto, monto_prueba_por_hijos_detallado,
)
from agent.airtable_client import (
    actualizar_conversion_lead, crear_grupo_a_prueba,
    registrar_pago_fenix,
)
from agent.detectores_conv import (
    _extraer_nombre_del_historial, _extraer_nombre_hijo_historial,
)
from agent.afiches import _armar_mensaje_agenda_post_pago
from agent.brain import extraer_datos_formulario

logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()


# ── Flujo de pagos ───────────────────────────────────────────────────────────

async def _procesar_comprobante(
    telefono: str,
    texto: str,
    media_id: str | None,
    historial: list[dict],
    topic_id: int | None,
    group_override: int = 0,
    metodo_pago: str = "TRANSFER",
    monto_override: int | None = None,
    tipo_override: str | None = None,
    concepto_pago: str = "PRUEBA",
    auth_number: str = "",
):
    """
    Procesa un pago confirmado (comprobante de transferencia o tarjeta):
    1. Responde al lead "gracias, verificando"
    2. Detecta tipo de pago (prueba vs inscripción)
    3. Reenvía imagen al admin + botones confirmar/rechazar
    4. Notifica en Telegram

    Con los defaults es el flujo de TRANSFERENCIA de siempre, intacto. El pago
    con TARJETA (webhook /pago-confirmado de la pasarela) llama con
    metodo_pago="CREDIT CARD" + monto_override/tipo_override del Pedido — el
    monto viene EXACTO y firmado de la pasarela, no se adivina por regex.
    """
    admin_phone = os.getenv("ADMIN_PHONE", "")
    nombre_padre = _extraer_nombre_del_historial(historial, texto) or "Lead"
    nombre_hijo = _extraer_nombre_hijo_historial(historial)
    tipo = tipo_override or detectar_tipo_pago(historial)

    # Calcular monto correcto (multi-hijo)
    _monto_adivinado = False
    if monto_override:
        monto = int(monto_override)
    elif tipo == "prueba":
        monto, _monto_adivinado = monto_prueba_por_hijos_detallado(historial)
    else:
        monto = 0

    monto_fmt = formatear_monto(monto) if monto else ""
    tipo_label = f"PRUEBA {monto_fmt}" if tipo == "prueba" and monto else "PRUEBA" if tipo == "prueba" else "INSCRIPCIÓN"

    # ── Auto-confirmar pago (sin esperar botones del admin) ──────────────
    # (user message ya guardado al inicio del flujo)

    # Confirmar pago directo
    await registrar_pago_pendiente(
        telefono=telefono,
        tipo=tipo,
        plan=tipo,
        monto=monto,
        media_id=media_id,
    )
    await confirmar_pago(telefono)

    # Mensaje al lead: pago confirmado directo. Best-effort: si el envío
    # revienta (red caída, token muerto), el flujo SIGUE — antes abortaba acá
    # con "Pago confirmado!" ya guardado en historial → sin PAGO en Airtable,
    # sin aviso al admin, y el guard ya_pago bloqueaba reprocesar el
    # comprobante: limbo irrecuperable (auditoría 04-07-26 A3).
    msg_lead = "Pago confirmado! 🎉"
    try:
        await guardar_mensaje(telefono, "assistant", msg_lead)
        await proveedor.enviar_mensaje(telefono, msg_lead)
    except Exception as e:
        logger.error(f"[PAGOS] Error enviando 'Pago confirmado' a {telefono}: {e}")

    # Actualizar conversión en Airtable + registrar en qué FU pagó
    try:
        await actualizar_conversion_lead(telefono, "PAGO")
        # Si tenía seguimientos, registrar en cuál pagó
        from agent.airtable_client import _get_records, _LEADS, _patch
        _lr_pago = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if _lr_pago:
            _seg_pago = _lr_pago[0].get("fields", {}).get("SEGUIMIENTOS", 0) or 0
            if _seg_pago >= 1:
                await _patch(_LEADS, _lr_pago[0]["id"], {"PAGO POST FU": _seg_pago})
                logger.info(f"[FOLLOWUP] {telefono} pagó después de FU{_seg_pago}")
    except Exception as e:
        logger.error(f"[PAGOS] Error actualizando conversión: {e}")

    # CONVERSION=PAGO ya se marcó arriba — follow-up loop lo excluye automáticamente

    # ── Registrar el PAGO por código (única fuente — reemplaza la automatización ──
    #    vieja de Airtable). Solo pruebas con monto; la inscripción
    #    crea sus PAGOS en inscripcion.py. Garantiza el grupo antes de colgar el pago.
    _pago_rid_factura = None
    if tipo == "prueba" and monto > 0:
        try:
            # Alta niño-eje (F7.b): TUTOR + NIÑOS A PRUEBA. Idempotente — si el
            # tutor ya existe con hijos, no crea nada.
            _pn = (nombre_padre or "").split()
            _ninos_pago = []
            if nombre_hijo and nombre_hijo != "no mencionó":
                _ninos_pago = [{"nombre": nombre_hijo}]
            _tutor_id_pago, _ = await crear_grupo_a_prueba(
                telefono=telefono,
                nombre_tutor=_pn[0] if _pn else (nombre_padre or ""),
                apellido_tutor=" ".join(_pn[1:]) if len(_pn) > 1 else "",
                ninos=_ninos_pago,
            )
            if not _tutor_id_pago:
                logger.warning(f"[PAGOS] Alta de grupo A PRUEBA falló para {telefono} — registro el pago igual")
            # registrar_pago_fenix resuelve niños/pagador por el grupo familiar del teléfono
            from agent.airtable_client import _get_records, _LEADS
            _lr_pago2 = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
            _lead_id_pago = _lr_pago2[0]["id"] if _lr_pago2 else None
            _pago_rid_factura = await registrar_pago_fenix(
                monto, concepto=concepto_pago, metodo=metodo_pago,
                lead_id=_lead_id_pago, telefono=telefono,
            )
        except Exception as e:
            logger.error(f"[PAGOS] Error registrando PAGO por código para {telefono}: {e}")

    # ── Cerrar Pedido de tarjeta abierto (si pagó por TRANSFERENCIA) ─────
    # Si Aurora mandó el link de tarjeta pero el padre transfirió, el Pedido
    # quedaba 'esperando_pago' para siempre: meses después, cualquier pago con
    # tarjeta de ese teléfono se clasificaba como esta prueba (auditoría M6).
    # En tarjeta lo cierra el webhook /pago-confirmado; acá cubrimos transferencia.
    if metodo_pago == "TRANSFER":
        try:
            from agent.memory import marcar_pedido_cargado
            if await marcar_pedido_cargado(telefono):
                logger.info(f"[PAGOS] Pedido de tarjeta abierto cerrado (pagó por transferencia) {telefono}")
        except Exception as e:
            logger.error(f"[PAGOS] Error cerrando Pedido abierto de {telefono}: {e}")

    # ── Ofrecer factura (espejo Dorita): el PAGO ya quedó cargado, la factura ──
    #    es un extra opcional encima. El botón se atiende en main.py con el flag
    #    pago_esperando_factura (interceptación temprana, antes del brain).
    if _pago_rid_factura:
        try:
            from agent.facturas import BOTONES_FACTURA
            await actualizar_estado_flags(
                telefono,
                pago_esperando_factura=True,
                factura_esperando_datos=False,
                factura_pago_rid=_pago_rid_factura,
                factura_monto=monto,
                factura_concepto=concepto_pago,
            )
            _msg_factura = "🧾 ¿Necesitás factura?"
            await guardar_mensaje(telefono, "assistant", _msg_factura)
            await proveedor.enviar_botones(telefono, _msg_factura, BOTONES_FACTURA)
        except Exception as e:
            logger.error(f"[FACTURA] Error ofreciendo factura a {telefono}: {e}")

    # CAPI: evento Purchase (comprobante confirmado) — best-effort: una
    # excepción acá (query ctwa a la DB) abortaba lo que queda del flujo y,
    # en tarjeta, hacía que la pasarela registrara el pago DE NUEVO (C7).
    try:
        await enviar_evento_pago(telefono)
    except Exception as e:
        logger.error(f"[PAGOS] Error CAPI Purchase para {telefono}: {e}")

    # Notificar al admin (solo informativo, sin botones)
    # Link al topic de Telegram de este lead
    tg_link_admin = ""
    if topic_id and group_override:
        gid = str(group_override).replace("-100", "", 1)
        tg_link_admin = f"\n💬 https://t.me/c/{gid}/{topic_id}"
    # Link wa.me para hablar con el padre
    wa_link_pago = f"https://wa.me/{telefono}"
    if metodo_pago == "TRANSFER":
        _metodo_linea = ""
    else:
        _aut = f" (aut. {auth_number})" if auth_number else ""
        _metodo_linea = f"💳 Método: TARJETA{_aut}\n"
    # Inscripción: el PAGO en Airtable lo crea 'cargar familia' (inscripcion.py),
    # no este flujo — sin este aviso quedaba sin registrar y nadie se enteraba (M9).
    _aviso_inscripcion = (
        "\n⚠️ INSCRIPCIÓN: el PAGO no se registra solo — corré 'cargar familia'."
        if tipo != "prueba" else ""
    )
    # Monto adivinado: ninguna regex encontró el monto acordado en el chat y
    # se registró el fallback de 100k — el admin tiene que verificar (A4).
    _aviso_monto = (
        f"\n⚠️ Monto ADIVINADO (no encontré el acordado en el chat) — "
        f"verificá el comprobante vs {formatear_monto(monto)} registrados."
        if _monto_adivinado else ""
    )
    msg_admin = (
        f"💰 PAGO RECIBIDO ✅\n\n"
        f"💰 Tipo: {tipo_label}\n"
        f"{_metodo_linea}"
        f"📲 {wa_link_pago}"
        f"{tg_link_admin}"
        f"{_aviso_inscripcion}"
        f"{_aviso_monto}"
    )
    # Reenviar imagen al admin (si hay media_id)
    if media_id:
        try:
            await proveedor.enviar_imagen(
                admin_phone,
                media_id,
                caption=f"Comprobante de {nombre_padre} ({telefono})",
            )
        except Exception as e:
            logger.error(f"[PAGOS] Error reenviando imagen al admin: {e}")
    try:
        await proveedor.enviar_mensaje(admin_phone, msg_admin)
    except Exception as e:
        logger.error(f"[PAGOS] Error notificando admin: {e}")

    # Notificar en Telegram
    try:
        await notificar_pago_telegram(
            telefono=telefono,
            nombre=nombre_padre,
            estado="confirmado",
            tipo=tipo_label,
            monto=monto,
        )
    except Exception as e:
        logger.error(f"[PAGOS] Error notificando Telegram: {e}")

    # Espejar en Telegram del lead
    if topic_id:
        _metodo_topic = " 💳 TARJETA" if metodo_pago != "TRANSFER" else ""
        await enviar_a_topic(topic_id, f"✅ PAGO CONFIRMADO — {tipo_label}{_metodo_topic}", telefono=telefono, group_override=group_override)

    logger.info(f"[PAGOS] Pago AUTO-CONFIRMADO para {telefono} tipo={tipo} metodo={metodo_pago}")

    # ── Post-pago: mensaje determinístico de agenda (sin Claude) ─────────
    # SOLO para prueba: la inscripción recibía el mensaje de agenda de CLASE DE
    # PRUEBA aunque estaba pagando el plan mensual (auditoría 04-07-26 M9).
    if tipo == "prueba":
        try:
            await asyncio.sleep(3)
            # Nuevo flujo: ANTES de ofrecer las fechas, mandar el formulario nativo de Meta
            # para completar los datos (niño + padre/madre). La agenda se ofrece recién
            # cuando el lead completa el formulario (ver agent/formulario_reserva.py).
            from agent.formulario_reserva import enviar_formulario_reserva
            enviado = await enviar_formulario_reserva(telefono)
            if enviado:
                await actualizar_estado_flags(telefono, esperando_formulario_reserva=True)
                await guardar_mensaje(telefono, "assistant", "[formulario de reserva enviado]")
                # Rescate A7 (aprobado 12/07): +2h re-envía el Flow, +24h cae a
                # agenda por texto — sin esto un lead pagado que no completaba
                # el formulario quedaba colgado para siempre.
                try:
                    from agent.loops import programar_rescate_formulario
                    await programar_rescate_formulario(telefono)
                except Exception as _e_resc:
                    logger.error(f"[PAGOS] No se pudo programar rescate de formulario: {_e_resc}")
                if topic_id:
                    await enviar_a_topic(topic_id, "📋 Formulario de reserva enviado al lead", telefono=telefono, group_override=group_override)
                logger.info(f"[PAGOS] Formulario de reserva enviado a {telefono}")
            else:
                # Fallback: si el formulario no salió (token/flow), usar el flujo viejo de agenda
                msg_agenda = await _armar_mensaje_agenda_post_pago()
                await guardar_mensaje(telefono, "assistant", msg_agenda)
                await proveedor.enviar_mensaje(telefono, msg_agenda)
                await actualizar_estado_flags(telefono, modo_agenda=True)
                if topic_id:
                    await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {msg_agenda}", telefono=telefono, group_override=group_override)
                logger.warning(f"[PAGOS] Formulario no salió — fallback a agenda directa para {telefono}")
        except Exception as e:
            logger.error(f"[PAGOS] Error en post-pago (formulario/agenda): {e}")


# ── /agenda — Ivan cierra agenda tras llamada telefónica ──────────────────────

# Solo los precios vigentes: 100k/1 hijo, 150k/2, 200k/3. Los viejos (90/120/180)
# se retiraron — aceptarlos hacía cobrar de menos si el admin seguía la ayuda vieja.
_MONTOS_AGENDA = {"100mil": 100_000, "150mil": 150_000, "200mil": 200_000, "gratis": 0}


async def _cerrar_agenda_desde_telegram(telefono: str, comando: str, thread_id: int, group_override: int = 0):
    """
    /agenda 100mil Carolina  → 1 hijo, 100k
    /agenda 150mil Carolina  → 2 hijos, 150k
    /agenda 200mil Carolina  → 3 hijos, 200k
    /agenda gratis Carolina  → prueba gratis (referidos/promo)

    Ivan usa esto cuando cierra la agenda por llamada telefónica.
    Crea la FAMILIA A PRUEBA + NIÑOS, reactiva el agente, y le manda al padre
    el formulario + datos bancarios para el comprobante (o solo formulario si gratis).
    """
    partes = comando.strip().split(maxsplit=2)
    if len(partes) < 3 or partes[1].lower() not in _MONTOS_AGENDA:
        await enviar_a_topic(
            thread_id,
            "⚠️ Uso: /agenda 100mil|150mil|200mil|gratis nombre\nEj: /agenda 100mil Carolina",
            telefono=telefono,
            group_override=group_override,
        )
        return

    monto = _MONTOS_AGENDA[partes[1].lower()]
    es_gratis = partes[1].lower() == "gratis"
    nombre_padre = partes[2].strip()

    try:
        historial_completo = await obtener_historial(telefono, limite=40)

        # Extraer datos con Haiku
        datos_form = await extraer_datos_formulario(historial_completo)
        padre_data = datos_form.get("padre") or {}
        nombre_resp = padre_data.get("nombre", "") or nombre_padre
        apellido_resp = padre_data.get("apellido", "") or ""
        ninos_form = datos_form.get("ninos", [])

        # Actualizar conversión
        await actualizar_conversion_lead(telefono, "GRATIS" if es_gratis else "PAGO")

        # ── GRUPO A PRUEBA: TUTOR + NIÑOS (F7.b: alta niño-eje — FAMILIAS ya
        # no se crea). El lead sigue con Ivan (router) hasta inscribirse; el
        # monto se registra en PAGOS recién cuando llega el comprobante.
        try:
            if ninos_form:
                _ninos_familia = [
                    {
                        "nombre": n.get("nombre", ""),
                        "apellido": n.get("apellido", ""),
                        "fecha_nacimiento": n.get("fecha_nacimiento", ""),
                    }
                    for n in ninos_form if n.get("nombre")
                ]
            else:
                _nh_fam = _extraer_nombre_hijo_historial(historial_completo)
                _ninos_familia = [{"nombre": _nh_fam}] if _nh_fam and _nh_fam != "no mencionó" else []
            _tutor_id_ag, _grupo_ninos = await crear_grupo_a_prueba(
                telefono=telefono,
                nombre_tutor=nombre_resp,
                apellido_tutor=apellido_resp,
                ninos=_ninos_familia,
            )
            logger.info(f"[AGENDA] Grupo A PRUEBA: tutor={_tutor_id_ag}, niños={_grupo_ninos}")
        except Exception as e:
            logger.error(f"[AGENDA] Error creando grupo A PRUEBA: {e}")

        # ── Determinar cantidad de hijos para el mensaje ──────────────────
        cant_hijos = len(ninos_form) if ninos_form else 1
        if cant_hijos == 1:
            texto_form = "Te envío el formulario para tu hijo/a"
        else:
            texto_form = f"Te envío los formularios para tus {cant_hijos} hijos"

        # ── Mensaje al padre ───────────────────────────────────────────────
        if es_gratis:
            msg_whatsapp = (
                f"{texto_form} 📋\n\n"
                f"Tu sábado en el parque es GRATIS 🎉 (cortesía referidos FENIX Kids)\n\n"
                f"Te confirmo el horario en breve, muchas gracias {nombre_padre} 🤝"
            )
        else:
            from agent.pagos import DATOS_BANCARIOS
            from agent.pagos_tarjeta import link_pago_fenix, tarjeta_habilitada
            monto_fmt = f"{monto:,}".replace(",", ".")

            # Pago con tarjeta: link firmado a la pasarela + Pedido abierto para
            # que /pago-confirmado sepa que este cobro lo inició Aurora.
            _linea_tarjeta = ""
            if tarjeta_habilitada():
                try:
                    _link_tarjeta = link_pago_fenix(
                        monto, concepto="Sábado en el parque", telefono=telefono)
                    _linea_tarjeta = f"💳 Si preferís tarjeta, pagá acá:\n{_link_tarjeta}\n\n"
                    from agent.memory import crear_o_actualizar_pedido
                    _concepto_pedido = "CLASE" if monto in (750_000, 350_000) else "PRUEBA"
                    await crear_o_actualizar_pedido(
                        telefono, tipo="prueba", concepto=_concepto_pedido, monto_total=monto)
                except Exception as e:
                    logger.error(f"[AGENDA] Error armando link de tarjeta: {e}")
                    _linea_tarjeta = ""

            msg_whatsapp = (
                f"{texto_form} 📋\n\n"
                f"El monto del sábado en el parque es {monto_fmt} Gs\n\n"
                f"{DATOS_BANCARIOS}\n\n"
                f"{_linea_tarjeta}"
                f"Si transferís, pasame nomas acá el comprobante, muchas gracias {nombre_padre} 🤝"
            )

        # Enviar al padre por WhatsApp
        await proveedor.enviar_mensaje(telefono, msg_whatsapp)
        await guardar_mensaje(telefono, "assistant", msg_whatsapp)

        # Reactivar el agente para que procese el comprobante
        await reactivar_dorita(telefono)

        # Notificar en Telegram
        monto_label = "GRATIS (referidos)" if es_gratis else f"{monto:,} Gs".replace(",", ".")
        await enviar_a_topic(
            thread_id,
            f"✅ Agenda cerrada — FAMILIA A PRUEBA ({cant_hijos} niño{'s' if cant_hijos != 1 else ''}) — {monto_label}\n"
            f"📲 Mensaje enviado a {nombre_padre}{' con formulario + transferencia/tarjeta' if not es_gratis else ' (prueba gratis)'}\n"
            f"🔊 Agente reactivado (esperando comprobante)",
            telefono=telefono,
            group_override=group_override,
        )
        logger.info(f"[AGENDA] {telefono}: familia A PRUEBA ({cant_hijos} niños), {monto_label}, msg enviado a {nombre_padre}")

    except Exception as e:
        logger.error(f"[CERRAR_AGENDA] Error: {e}")
        await enviar_a_topic(thread_id, f"❌ Error cerrando agenda: {e}", telefono=telefono, group_override=group_override)
