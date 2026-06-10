# agent/flujo_pagos.py — Flujo de pagos (comprobantes, confirmación, agenda)
# Extraído de main.py — Paso 8 del refactor

import os
import asyncio
import logging

from agent.memory import guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.ab_test import (
    obtener_agent_actual, obtener_estado_flags, actualizar_estado_flags,
)
from agent.telegram_bridge import (
    obtener_o_crear_topic, enviar_a_topic,
    notificar_pago_telegram,
    group_id_para_agente,
    reactivar_dorita,
)
from agent.meta_capi import enviar_evento_pago
from agent.pagos import (
    detectar_tipo_pago,
    registrar_pago_pendiente, obtener_pago_pendiente,
    confirmar_pago, rechazar_pago,
    formatear_monto, monto_prueba_por_hijos,
)
from agent.airtable_client import (
    actualizar_conversion_lead, crear_prueba_fenix, crear_familia_a_prueba,
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
):
    """
    Procesa un posible comprobante de pago:
    1. Responde al lead "gracias, verificando"
    2. Detecta tipo de pago (prueba vs inscripción)
    3. Reenvía imagen al admin + botones confirmar/rechazar
    4. Notifica en Telegram
    """
    admin_phone = os.getenv("ADMIN_PHONE", "")
    nombre_padre = _extraer_nombre_del_historial(historial, texto) or "Lead"
    nombre_hijo = _extraer_nombre_hijo_historial(historial)
    tipo = detectar_tipo_pago(historial)

    # Calcular monto correcto (multi-hijo)
    if tipo == "prueba":
        monto = monto_prueba_por_hijos(historial)
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

    # Mensaje al lead: pago confirmado directo
    msg_lead = "Pago confirmado! 🎉"
    await guardar_mensaje(telefono, "assistant", msg_lead)
    await proveedor.enviar_mensaje(telefono, msg_lead)

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

    # CAPI: evento Purchase (comprobante confirmado)
    await enviar_evento_pago(telefono)

    # Notificar al admin (solo informativo, sin botones)
    # Link al topic de Telegram de este lead
    tg_link_admin = ""
    if topic_id and group_override:
        gid = str(group_override).replace("-100", "", 1)
        tg_link_admin = f"\n💬 https://t.me/c/{gid}/{topic_id}"
    # Link wa.me para hablar con el padre
    wa_link_pago = f"https://wa.me/{telefono}"
    msg_admin = (
        f"💰 PAGO RECIBIDO ✅\n\n"
        f"💰 Tipo: {tipo_label}\n"
        f"📲 {wa_link_pago}"
        f"{tg_link_admin}"
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
        await enviar_a_topic(topic_id, f"✅ PAGO CONFIRMADO — {tipo_label}", telefono=telefono, group_override=group_override)

    logger.info(f"[PAGOS] Pago AUTO-CONFIRMADO para {telefono} tipo={tipo}")

    # ── Post-pago: mensaje determinístico de agenda (sin Claude) ─────────
    try:
        await asyncio.sleep(3)
        msg_agenda = await _armar_mensaje_agenda_post_pago()
        await guardar_mensaje(telefono, "assistant", msg_agenda)
        await proveedor.enviar_mensaje(telefono, msg_agenda)
        await actualizar_estado_flags(telefono, modo_agenda=True)
        if topic_id:
            await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {msg_agenda}", telefono=telefono, group_override=group_override)
        logger.info(f"[PAGOS] Modo agenda activado para {telefono}")
    except Exception as e:
        logger.error(f"[PAGOS] Error enviando agenda post-pago: {e}")


async def _procesar_boton_pago(btn_titulo: str):
    """
    Procesa la respuesta del admin (confirmar/rechazar) a un comprobante.
    Busca el pago pendiente más reciente y actúa según el botón.
    """
    admin_phone = os.getenv("ADMIN_PHONE", "")

    tel_lead, datos = await obtener_pago_pendiente()
    if not tel_lead or not datos:
        await proveedor.enviar_mensaje(admin_phone, "No hay pagos pendientes de confirmar.")
        return

    tipo = datos.get("tipo", "prueba")
    tipo_label = "PRUEBA 90K" if tipo == "prueba" else "INSCRIPCIÓN"
    topic_id = None

    if "confirmar" in btn_titulo:
        # ── Confirmar pago ────────────────────────────────────────────────
        await confirmar_pago(tel_lead)

        # Mensaje al admin
        await proveedor.enviar_mensaje(admin_phone, f"✅ Pago de {tel_lead} confirmado.")

        # Mensaje al lead
        msg_lead = "Pago confirmado! 🎉"
        await proveedor.enviar_mensaje(tel_lead, msg_lead)
        await guardar_mensaje(tel_lead, "assistant", msg_lead)

        # Actualizar conversión en Airtable
        try:
            await actualizar_conversion_lead(tel_lead, "PAGO")
        except Exception as e:
            logger.error(f"[PAGOS] Error actualizando conversión: {e}")

        # CAPI: evento Purchase (botón admin confirmó)
        await enviar_evento_pago(tel_lead)

        # Notificar en Telegram
        _ag_pago, _ = await obtener_agent_actual(tel_lead)
        _grp_pago = group_id_para_agente(_ag_pago or "ivan")
        topic_id = await obtener_o_crear_topic(tel_lead, f"📱 {tel_lead}", group_override=_grp_pago)
        if topic_id:
            await enviar_a_topic(topic_id, f"✅ PAGO CONFIRMADO — {tipo_label}", telefono=tel_lead, group_override=_grp_pago)

        try:
            historial = await obtener_historial(tel_lead)
            nombre = _extraer_nombre_del_historial(historial) or "Lead"
            await notificar_pago_telegram(
                telefono=tel_lead,
                nombre=nombre,
                estado="confirmado",
                tipo=tipo_label,
                monto=datos.get("monto", 0),
            )
        except Exception as e:
            logger.error(f"[PAGOS] Error notificando Telegram confirmación: {e}")

        logger.info(f"[PAGOS] Pago CONFIRMADO para {tel_lead}")

        # ── Post-pago: mensaje determinístico de agenda (sin Claude) ─────────
        try:
            await asyncio.sleep(3)
            msg_agenda = await _armar_mensaje_agenda_post_pago()
            await guardar_mensaje(tel_lead, "assistant", msg_agenda)
            await proveedor.enviar_mensaje(tel_lead, msg_agenda)
            await actualizar_estado_flags(tel_lead, modo_agenda=True)
            if topic_id:
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {msg_agenda}", telefono=tel_lead, group_override=_grp_pago)
            logger.info(f"[PAGOS] Modo agenda activado para {tel_lead}")
        except Exception as e:
            logger.error(f"[PAGOS] Error enviando agenda post-pago: {e}")

    elif "rechazar" in btn_titulo:
        # ── Rechazar pago ─────────────────────────────────────────────────
        await rechazar_pago(tel_lead)

        # Mensaje al admin
        await proveedor.enviar_mensaje(admin_phone, f"❌ Pago de {tel_lead} rechazado.")

        # Mensaje al lead
        msg_lead = "Hubo un problema con la transferencia. ¿Podrías verificar y reenviar el comprobante? 😊"
        await proveedor.enviar_mensaje(tel_lead, msg_lead)
        await guardar_mensaje(tel_lead, "assistant", msg_lead)

        # Notificar en Telegram (reusar _grp_pago si existe, sino resolver)
        if not topic_id:
            _ag_r, _ = await obtener_agent_actual(tel_lead)
            _grp_r = group_id_para_agente(_ag_r or "ivan")
            topic_id = await obtener_o_crear_topic(tel_lead, f"📱 {tel_lead}", group_override=_grp_r)
        if topic_id:
            await enviar_a_topic(topic_id, f"❌ PAGO RECHAZADO — {tipo_label}", telefono=tel_lead)

        try:
            historial = await obtener_historial(tel_lead)
            nombre = _extraer_nombre_del_historial(historial) or "Lead"
            await notificar_pago_telegram(
                telefono=tel_lead,
                nombre=nombre,
                estado="rechazado",
                tipo=tipo_label,
            )
        except Exception as e:
            logger.error(f"[PAGOS] Error notificando Telegram rechazo: {e}")

        logger.info(f"[PAGOS] Pago RECHAZADO para {tel_lead}")


# ── /agenda — Ivan cierra agenda tras llamada telefónica ──────────────────────

_MONTOS_AGENDA = {"90mil": 90_000, "100mil": 100_000, "120mil": 120_000, "150mil": 150_000, "180mil": 180_000, "gratis": 0}


async def _cerrar_agenda_desde_telegram(telefono: str, comando: str, thread_id: int, group_override: int = 0):
    """
    /agenda 90mil Carolina   → 1 hijo, 90k
    /agenda 120mil Carolina  → 2 hijos, 120k
    /agenda 150mil Carolina  → 3 hijos, 150k
    /agenda gratis Carolina  → prueba gratis (referidos/promo)

    Ivan usa esto cuando cierra la agenda por llamada telefónica.
    Crea PRUEBA FENIX, reactiva el agente, y le manda al padre
    el formulario + datos bancarios para el comprobante (o solo formulario si gratis).
    """
    partes = comando.strip().split(maxsplit=2)
    if len(partes) < 3 or partes[1].lower() not in _MONTOS_AGENDA:
        await enviar_a_topic(
            thread_id,
            "⚠️ Uso: /agenda 90mil|120mil|150mil|gratis nombre\nEj: /agenda 90mil Carolina",
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

        # Obtener lead_id y diagnóstico
        from agent.airtable_client import _get_records, _LEADS
        lead_records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        lead_record_id = lead_records[0]["id"] if lead_records else None
        diagnostico_ids = lead_records[0].get("fields", {}).get("DIAGNOSTICO", []) if lead_records else []

        # Actualizar conversión
        await actualizar_conversion_lead(telefono, "GRATIS" if es_gratis else "PAGO")

        # Crear PRUEBA FENIX por cada niño (monto solo en primero)
        creados = 0
        _conversion_prueba = "GRATIS" if es_gratis else "PAGO"
        _n_hijos_pf = len(ninos_form) if ninos_form else 1
        if monto in (750_000, 350_000):
            _concepto_pf = "CLASE"
        else:
            _concepto_pf = "PRUEBA"
        if ninos_form:
            for i, n in enumerate(ninos_form):
                await crear_prueba_fenix(
                    telefono=telefono,
                    nombre_responsable=nombre_resp,
                    apellido_responsable=apellido_resp,
                    nombre_hijo=n.get("nombre", ""),
                    apellido_hijo=n.get("apellido", ""),
                    edad_hijo="",
                    fecha_reserva="(por definir)",
                    hora="(por definir)",
                    fecha_nacimiento=n.get("fecha_nacimiento", ""),
                    monto=monto if i == 0 else 0,
                    concepto=_concepto_pf,
                    conversion=_conversion_prueba,
                    diagnostico_ids=diagnostico_ids,
                    lead_record_id=lead_record_id,
                )
                creados += 1
        else:
            # Fallback sin datos de hijos
            nh = _extraer_nombre_hijo_historial(historial_completo)
            await crear_prueba_fenix(
                telefono=telefono,
                nombre_responsable=nombre_resp,
                apellido_responsable=apellido_resp,
                nombre_hijo=nh if nh != "no mencionó" else "",
                apellido_hijo="",
                edad_hijo="",
                fecha_reserva="(por definir)",
                hora="(por definir)",
                monto=monto,
                concepto=_concepto_pf,
                conversion=_conversion_prueba,
                diagnostico_ids=diagnostico_ids,
                lead_record_id=lead_record_id,
            )
            creados = 1

        # ── Dual-write: crear/reusar FAMILIA en estado A PRUEBA (Fase 2.A) ──
        # El lead que agendó/pagó la prueba se materializa como FAMILIA A PRUEBA
        # + NIÑOS. Sigue con Ivan (router lo mantiene) hasta inscribirse.
        # PRUEBA FENIX se mantiene en paralelo por ahora. Nunca rompe el pago.
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
            _fam_id, _fam_ninos = await crear_familia_a_prueba(
                telefono=telefono,
                nombre_padre=nombre_resp,
                apellido_padre=apellido_resp,
                ninos=_ninos_familia,
            )
            logger.info(f"[AGENDA] FAMILIA A PRUEBA: {_fam_id}, niños={_fam_ninos}")
        except Exception as e:
            logger.error(f"[AGENDA] Error creando FAMILIA A PRUEBA: {e}")

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
            monto_fmt = f"{monto:,}".replace(",", ".")
            msg_whatsapp = (
                f"{texto_form} 📋\n\n"
                f"El monto del sábado en el parque es {monto_fmt} Gs\n\n"
                f"{DATOS_BANCARIOS}\n\n"
                f"Pasame nomas acá el comprobante de transferencia, muchas gracias {nombre_padre} 🤝"
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
            f"✅ Agenda cerrada — {creados} PRUEBA FENIX — {monto_label}\n"
            f"📲 Mensaje enviado a {nombre_padre}{' con formulario + datos bancarios' if not es_gratis else ' (prueba gratis)'}\n"
            f"🔊 Agente reactivado (esperando comprobante)",
            telefono=telefono,
            group_override=group_override,
        )
        logger.info(f"[AGENDA] {telefono}: {creados} registros, {monto_label}, msg enviado a {nombre_padre}")

    except Exception as e:
        logger.error(f"[CERRAR_AGENDA] Error: {e}")
        await enviar_a_topic(thread_id, f"❌ Error cerrando agenda: {e}", telefono=telefono, group_override=group_override)
