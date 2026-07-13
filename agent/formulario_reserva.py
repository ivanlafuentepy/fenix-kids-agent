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
    """persona → campos de TUTORES FENIX (mismo criterio que crear_o_actualizar_tutor)."""
    campos: dict = {"NOMBRE": persona["nombre"]}
    if persona.get("apellido"):
        campos["APELLIDO"] = persona["apellido"]
    if persona.get("ci"):
        campos["CI"] = str(persona["ci"]).strip()
    if persona.get("telefono"):
        campos["CELL"] = str(persona["telefono"]).strip()
    if persona.get("email"):
        campos["EMAIL"] = persona["email"]
    if persona.get("fecha_nacimiento"):
        campos["FECHA NACIMIENTO"] = persona["fecha_nacimiento"]
    return campos


async def _guardar_tutor(familia_id: str, persona: dict, parentesco: str) -> str | None:
    """Actualiza el tutor de ese parentesco que ya tiene la familia (sin duplicar); si no
    existe, lo crea. Necesario porque el tutor padre parcial se creó en el pago con el CELL
    del WhatsApp, y el formulario puede traer OTRO teléfono → crear_o_actualizar_tutor (que
    matchea por CELL+parentesco) crearía un duplicado. Acá matcheamos por parentesco."""
    from agent.airtable_client import (
        obtener_tutores_de_familia, crear_o_actualizar_tutor, _patch, _TUTORES,
    )
    if not persona.get("nombre"):
        return None
    try:
        tutores = await obtener_tutores_de_familia(familia_id)
        existente = next(
            (t for t in tutores if (t.get("parentesco") or "") == parentesco and t.get("id")),
            None,
        )
        if existente:
            await _patch(_TUTORES, existente["id"], _campos_tutor(persona))
            return existente["id"]
    except Exception as e:
        logger.error(f"[RESERVA-FORM] error buscando tutor {parentesco}: {e}")
    return await crear_o_actualizar_tutor(persona, parentesco, familia_id=familia_id)


async def procesar_formulario_reserva(telefono: str, flow_data: dict) -> None:
    """Completa FAMILIA/NIÑO/TUTORES a prueba con los datos del formulario y dispara la
    agenda (sábados). NO crea inscripto ACTIVO — la familia ya existe (creada en el pago)."""
    from agent.airtable_client import (
        buscar_familia_por_telefono, obtener_ninos_de_familia, actualizar_nino,
    )
    from agent.ab_test import actualizar_estado_flags
    from agent.afiches import _armar_mensaje_agenda_post_pago
    from agent.memory import guardar_mensaje

    familia = await buscar_familia_por_telefono(telefono)
    if not familia:
        logger.warning(f"[RESERVA-FORM] {telefono}: no encontré familia a prueba — no completo datos")
    else:
        familia_id = familia["id"]
        # NIÑO — completar el hijo parcial (apellido, fecha nac, CI)
        nino_nombre = (flow_data.get("nino_nombre") or "").strip()
        nino_apellido = (flow_data.get("nino_apellido") or "").strip()
        nino_ci = (flow_data.get("nino_ci") or "").strip()
        nino_fecha = _fecha_desde_flow(flow_data.get("nino_fecha_nacimiento", ""))
        try:
            ninos = await obtener_ninos_de_familia(familia_id)
            objetivo = None
            if nino_nombre:
                objetivo = next(
                    (n for n in ninos if (n.get("nombre") or "").strip().lower() == nino_nombre.lower()),
                    None,
                )
            if not objetivo and ninos:
                objetivo = ninos[0]
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
        except Exception as e:
            logger.error(f"[RESERVA-FORM] error actualizando niño: {e}")

        # PADRE / MADRE — actualizar los tutores existentes sin duplicar
        try:
            padre = _tutor_desde_flow(flow_data, "padre")
            madre = _tutor_desde_flow(flow_data, "madre")
            if padre:
                await _guardar_tutor(familia_id, padre, "Papá")
            if madre:
                await _guardar_tutor(familia_id, madre, "Mamá")
        except Exception as e:
            logger.error(f"[RESERVA-FORM] error actualizando tutores: {e}")

        logger.info(f"[RESERVA-FORM] datos completados: familia={familia_id} ({telefono})")

    # Ahora sí: cerrar el paso del formulario y ofrecer las fechas (activar modo agenda)
    await actualizar_estado_flags(telefono, esperando_formulario_reserva=False, modo_agenda=True)
    # Cancelar el rescate A7 (+2h/+24h) — el formulario ya se completó
    try:
        from agent.memory import cancelar_recordatorios_por_telefono
        await cancelar_recordatorios_por_telefono(telefono, tipo="form_rescate")
    except Exception as e:
        logger.warning(f"[RESERVA-FORM] no se pudo cancelar rescate: {e}")
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
                await enviar_a_topic(_topic, "📋 Formulario de reserva completado", telefono=telefono, group_override=_grp)
                await enviar_a_topic(_topic, f"👨‍🏫 IVAN: {msg_agenda}", telefono=telefono, group_override=_grp)
        except Exception as e:
            logger.error(f"[RESERVA-FORM] espejo Telegram falló: {e}")
    except Exception as e:
        logger.error(f"[RESERVA-FORM] error enviando agenda tras formulario: {e}")
