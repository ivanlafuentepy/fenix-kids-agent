# agent/formulario_reserva.py — Formulario Meta para completar los datos de la RESERVA de un lead
"""
Reemplaza el viejo paso de "pasame los datos por texto" (prompts.yaml FASE 4) por el
formulario nativo de Meta (WhatsApp Flow).

Flujo nuevo: el lead paga la prueba → se le manda ESTE formulario (antes de ofrecer las
fechas) → al completarlo se ACTUALIZAN la FAMILIA a prueba + NIÑO + TUTORES existentes
(creados parciales en el pago) con los datos reales → recién ahí se le ofrecen los sábados.

Reusa el MISMO Flow que el comando admin "cargar niño" (mismos campos: niño obligatorio;
papá y mamá opcionales). Se distingue del alta de admin por el flag persistente
`esperando_formulario_reserva` del lead, no por el payload. A diferencia de
`procesar_formulario_cargar_nino` (que crea FAMILIA ACTIVO), acá se ACTUALIZA sin duplicar.

Env: FLOW_CARGAR_NINO_ID (Flow publicado en el WABA propio de FENIX 896276490105251).
"""

import os
import logging

from agent.providers import obtener_proveedor
from agent.cargar_nino import _fecha_desde_flow, _tutor_desde_flow

logger = logging.getLogger("agentkit")
proveedor = obtener_proveedor()

FLOW_CARGAR_NINO_ID = os.getenv("FLOW_CARGAR_NINO_ID", "")


async def enviar_formulario_reserva(telefono: str) -> bool:
    """Envía el Flow de Meta al lead para completar los datos de su reserva.
    flow_token='reserva' marca el contexto (informativo; el handler decide por el flag)."""
    if not FLOW_CARGAR_NINO_ID:
        logger.error("[RESERVA-FORM] Falta FLOW_CARGAR_NINO_ID — no puedo enviar el formulario")
        return False
    return await proveedor.enviar_flow(
        telefono=telefono,
        flow_id=FLOW_CARGAR_NINO_ID,
        screen="NINO",
        texto="¡Pago recibido! 🎉 Para dejar lista tu reserva, completá estos datos 📋",
        boton_texto="Completar datos",
        flow_token="reserva",
    )


def _campos_tutor(persona: dict) -> dict:
    """persona → campos del tutor en ALUMNOS (mismo criterio que crear_o_actualizar_tutor)."""
    campos: dict = {"NOMBRE": persona["nombre"]}
    if persona.get("apellido"):
        campos["APELLIDO"] = persona["apellido"]
    if persona.get("ci"):
        campos["CI"] = str(persona["ci"]).strip()
    if persona.get("telefono"):
        campos["TELEFONO"] = str(persona["telefono"]).strip()
    if persona.get("email"):
        campos["EMAIL"] = persona["email"]
    if persona.get("fecha_nacimiento"):
        campos["FECHA NACIMIENTO"] = persona["fecha_nacimiento"]
    return campos


async def _guardar_tutor(
    tutores_grupo: list[dict],
    hijos: list[dict],
    persona: dict,
    parentesco: str,
) -> str | None:
    """Actualiza el tutor de ese parentesco del grupo familiar (sin duplicar); si no
    existe, lo crea y lo linkea a los hijos (PADRE/MADRE del niño, niño-eje).
    Se matchea por parentesco (no por CELL) porque el tutor parcial se creó en el
    pago con el CELL del WhatsApp y el formulario puede traer OTRO teléfono."""
    from agent.airtable_client import crear_o_actualizar_tutor, _patch, _ALUMNOS, _NINOS
    if not persona.get("nombre"):
        return None
    existente = next(
        (t for t in tutores_grupo if (t.get("parentesco") or "") == parentesco and t.get("id")),
        None,
    )
    if existente:
        try:
            await _patch(_ALUMNOS, existente["id"], _campos_tutor(persona))
            return existente["id"]
        except Exception as e:
            logger.error(f"[RESERVA-FORM] error actualizando tutor {parentesco}: {e}")
            return None

    tid = await crear_o_actualizar_tutor(persona, parentesco)
    # Niño-eje: linkear el tutor nuevo (fila ALUMNOS) a los hijos.
    if tid:
        campo = "MADRE (ALUMNOS)" if parentesco == "Mamá" else "PADRE (ALUMNOS)"
        for h in hijos:
            if h.get("id"):
                try:
                    await _patch(_NINOS, h["id"], {campo: [tid]})
                except Exception as e:
                    logger.error(f"[RESERVA-FORM] error linkeando {campo} del niño {h['id']}: {e}")
    return tid


def _resumen_formulario(flow_data: dict) -> str:
    """Texto con TODOS los datos del formulario, para el espejo a Telegram y al
    admin. Nunca más un formulario invisible (caso 595981941407, 25/07)."""
    def _persona(prefijo: str, etiqueta: str) -> str:
        p = _tutor_desde_flow(flow_data, prefijo)
        if not p:
            return f"{etiqueta}: (sin datos)"
        partes = [f"{p.get('nombre', '')} {p.get('apellido', '')}".strip()]
        if p.get("ci"):
            partes.append(f"CI {p['ci']}")
        if p.get("telefono"):
            partes.append(str(p["telefono"]))
        if p.get("email"):
            partes.append(p["email"])
        if p.get("fecha_nacimiento"):
            partes.append(f"nac. {p['fecha_nacimiento']}")
        return f"{etiqueta}: " + " · ".join(x for x in partes if x)

    nino = (f"{(flow_data.get('nino_nombre') or '').strip()} "
            f"{(flow_data.get('nino_apellido') or '').strip()}").strip() or "(sin nombre)"
    linea_nino = f"👶 {nino}"
    if (flow_data.get("nino_ci") or "").strip():
        linea_nino += f" — CI {flow_data['nino_ci'].strip()}"
    lineas = [linea_nino]
    _fn = _fecha_desde_flow(flow_data.get("nino_fecha_nacimiento", ""))
    if _fn:
        lineas.append(f"🎂 {_fn}")
    lineas.append(_persona("padre", "👨 Papá"))
    lineas.append(_persona("madre", "👩 Mamá"))
    return "\n".join(lineas)


async def _espejar_formulario(telefono: str, flow_data: dict) -> None:
    """Manda el contenido completo del formulario a Telegram (topic del lead) y
    al WhatsApp del admin. Best-effort: nunca rompe el flujo."""
    resumen = (f"📋 FORMULARIO DE RESERVA COMPLETADO\n📱 {telefono}\n\n"
               f"{_resumen_formulario(flow_data)}")
    try:
        from agent.telegram_bridge import (
            obtener_o_crear_topic, enviar_a_topic, grupo_telegram_para,
        )
        _grp = await grupo_telegram_para(telefono)
        _topic = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=_grp)
        if _topic:
            await enviar_a_topic(_topic, resumen, telefono=telefono, group_override=_grp)
    except Exception as e:
        logger.error(f"[RESERVA-FORM] espejo Telegram del formulario falló: {e}")
    admin_phone = os.getenv("ADMIN_PHONE", "")
    if admin_phone:
        try:
            await proveedor.enviar_mensaje(admin_phone, resumen)
        except Exception as e:
            logger.error(f"[RESERVA-FORM] espejo WhatsApp admin del formulario falló: {e}")


async def _completar_pago_huerfano(telefono: str, nino_ids: list[str], tutor_id: str | None) -> None:
    """Back-fill del PAGO: el pago se registra ANTES del formulario, así que si en
    ese momento el niño no existía (extractor sin nombre), el PAGO nació sin
    NIÑOS FENIX ni PAGA — huérfano e invisible en las vistas (caso 25/07).
    Acá, con el niño ya real, se linkea. Solo toca PAGOs PRUEBA sin niños."""
    from agent.airtable_client import _get_records, _patch, _LEADS, _PAGOS
    if not nino_ids:
        return
    lead = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    pago_ids = (lead[0].get("fields", {}) or {}).get("PAGOS", []) if lead else []
    if not pago_ids:
        return
    _or = ",".join(f"RECORD_ID()='{p}'" for p in pago_ids)
    pagos = await _get_records(_PAGOS, formula=f"OR({_or})" if len(pago_ids) > 1 else _or,
                               max_records=len(pago_ids))
    for p in pagos:
        pf = p.get("fields", {}) or {}
        if (pf.get("CONCEPTO") or "").startswith("PRUEBA") and not pf.get("NIÑOS FENIX"):
            campos: dict = {"NIÑOS FENIX": nino_ids}
            # El tutor es una fila de ALUMNOS → link PAGA (ALUMNOS); el viejo
            # PAGA (→TUTORES) quedó legacy.
            if tutor_id and not pf.get("PAGA (ALUMNOS)"):
                campos["PAGA (ALUMNOS)"] = [tutor_id]
            await _patch(_PAGOS, p["id"], campos)
            logger.info(f"[RESERVA-FORM] PAGO huérfano {p['id']} linkeado a niños {nino_ids}")


async def procesar_formulario_reserva(telefono: str, flow_data: dict) -> None:
    """Completa (o CREA) NIÑO + TUTORES a prueba con los datos del formulario y
    dispara la agenda (sábados). El niño NACE del formulario si no existe — antes,
    sin grupo previo, los datos se descartaban (caso 595981941407, 25/07).
    NO crea inscripto ACTIVO."""
    from agent.airtable_client import (
        obtener_grupo_familiar, actualizar_nino,
        buscar_tutor_por_telefono, _tutor_a_dict, crear_nino, vincular_tutor_a_lead,
        tutor_tiene_telefono,
    )
    from agent.ab_test import obtener_estado_flags, actualizar_estado_flags
    from agent.afiches import _armar_mensaje_agenda_post_pago
    from agent.memory import guardar_mensaje

    flags = await obtener_estado_flags(telefono)

    # 0. Espejo con TODOS los datos — primero, antes de tocar Airtable
    await _espejar_formulario(telefono, flow_data)

    grupo = await obtener_grupo_familiar(telefono)
    hijos = (grupo or {}).get("hijos", [])
    tutores = (grupo or {}).get("tutores", [])
    # Tutor parcial del pago (todavía sin hijos → obtener_grupo_familiar da None):
    # traerlo para que _guardar_tutor lo ACTUALICE en vez de duplicarlo.
    if not tutores:
        _t_parcial = await buscar_tutor_por_telefono(telefono)
        if _t_parcial:
            tutores = [_tutor_a_dict(_t_parcial["id"], _t_parcial.get("fields", {}) or {})]

    # PADRE / MADRE primero — el niño nuevo necesita sus ids para los links
    padre_id = madre_id = None
    try:
        padre = _tutor_desde_flow(flow_data, "padre")
        madre = _tutor_desde_flow(flow_data, "madre")
        if padre:
            padre_id = await _guardar_tutor(tutores, hijos, padre, "Papá")
        if madre:
            madre_id = await _guardar_tutor(tutores, hijos, madre, "Mamá")
    except Exception as e:
        logger.error(f"[RESERVA-FORM] error actualizando tutores: {e}")
    # El tutor parcial existente cubre el parentesco que el formulario no trajo
    if not padre_id:
        padre_id = next((t["id"] for t in tutores if t.get("parentesco") == "Papá" and t.get("id")), None)
    if not madre_id:
        madre_id = next((t["id"] for t in tutores if t.get("parentesco") == "Mamá" and t.get("id")), None)

    # NIÑO — actualizar el existente, o CREARLO si no está
    nino_nombre = (flow_data.get("nino_nombre") or "").strip()
    nino_apellido = (flow_data.get("nino_apellido") or "").strip()
    nino_ci = (flow_data.get("nino_ci") or "").strip()
    nino_fecha = _fecha_desde_flow(flow_data.get("nino_fecha_nacimiento", ""))
    _nino_ids_form: list[str] = [h["id"] for h in hijos if h.get("id")]
    try:
        objetivo = None
        if nino_nombre:
            objetivo = next(
                (n for n in hijos if (n.get("nombre") or "").strip().lower() == nino_nombre.lower()),
                None,
            )
        if not objetivo and hijos:
            objetivo = hijos[0]
        if objetivo:
            campos: dict = {}
            if nino_apellido:
                campos["APELLIDO"] = nino_apellido
            if nino_ci:
                campos["CI"] = nino_ci
            if nino_fecha:
                campos["FECHA NACIMIENTO"] = nino_fecha
            if campos:
                await actualizar_nino(objetivo["id"], campos)
        elif nino_nombre:
            nino_id = await crear_nino(
                {"nombre": nino_nombre, "apellido": nino_apellido, "ci": nino_ci,
                 "fecha_nacimiento": nino_fecha},
                padre_id=padre_id or "", madre_id=madre_id or "", estado="A PRUEBA",
            )
            if nino_id:
                _nino_ids_form.append(nino_id)
            logger.info(f"[RESERVA-FORM] Niño CREADO desde el formulario: {nino_id} para {telefono}")
    except Exception as e:
        logger.error(f"[RESERVA-FORM] error con el niño del formulario: {e}")

    # LEAD ↔ TUTOR (lo hacía crear_grupo_a_prueba; sin esto el lead queda sin link)
    _sender_id = next(
        (t["id"] for t in tutores if t.get("id") and tutor_tiene_telefono(t, telefono)),
        None,
    ) or padre_id or madre_id
    if _sender_id:
        try:
            await actualizar_estado_flags(telefono, tutor_id=_sender_id)
            await vincular_tutor_a_lead(telefono, _sender_id)
        except Exception as e:
            logger.warning(f"[RESERVA-FORM] no pude vincular tutor al lead: {e}")

    # PAGO — back-fill: el pago se registró ANTES del formulario; si nació sin
    # niños linkeados (el caso Blas 25/07), linkearlo ahora que el niño existe
    try:
        await _completar_pago_huerfano(telefono, _nino_ids_form, _sender_id)
    except Exception as e:
        logger.error(f"[RESERVA-FORM] back-fill del pago falló: {e}")

    logger.info(f"[RESERVA-FORM] datos completados: grupo de {telefono} ({len(hijos)} hijos previos)")

    # Cerrar el paso del formulario y activar modo agenda. prueba_creada=True
    # desarma el detector legacy de main.py (_es_formulario_completo), que el
    # 25/07 recreó al niño con datos adivinados ENCIMA de los del formulario.
    await actualizar_estado_flags(
        telefono, esperando_formulario_reserva=False, modo_agenda=True, prueba_creada=True,
    )
    # Cancelar el rescate A7 (+2h/+24h) — el formulario ya se completó
    try:
        from agent.memory import cancelar_recordatorios_por_telefono
        await cancelar_recordatorios_por_telefono(telefono, tipo="form_rescate")
    except Exception as e:
        logger.warning(f"[RESERVA-FORM] no se pudo cancelar rescate: {e}")
    # Agenda: no re-ofrecerla si ya estaba activa y el formulario llegó tarde
    # (rescate +24h ya cayó a agenda por texto → evitar el mensaje duplicado)
    if not flags.get("esperando_formulario_reserva") and flags.get("modo_agenda"):
        logger.info(f"[RESERVA-FORM] {telefono}: agenda ya ofrecida — no la repito")
        return
    try:
        msg_agenda = await _armar_mensaje_agenda_post_pago()
        await guardar_mensaje(telefono, "assistant", msg_agenda)
        await proveedor.enviar_mensaje(telefono, msg_agenda)
        # Espejo a Telegram (best-effort — nunca rompe el flujo)
        try:
            from agent.telegram_bridge import (
                obtener_o_crear_topic, enviar_a_topic, grupo_telegram_para,
            )
            _grp = await grupo_telegram_para(telefono)
            _topic = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=_grp)
            if _topic:
                await enviar_a_topic(_topic, f"👨‍🏫 IVAN: {msg_agenda}", telefono=telefono, group_override=_grp)
        except Exception as e:
            logger.error(f"[RESERVA-FORM] espejo Telegram falló: {e}")
    except Exception as e:
        logger.error(f"[RESERVA-FORM] error enviando agenda tras formulario: {e}")
