# agent/confirmacion_sabado.py — Confirmación proactiva de asistencia del sábado (Aurora)
#
# Reemplaza la reserva por iniciativa del padre como flujo PRINCIPAL: los jueves
# 9:00 AM PY Aurora manda la plantilla `confirmacion_sabado_fenix` preguntando si
# el hijo viene a entrenar el sábado.
#   - Botón "Sí" → Aurora pregunta el turno (11:00 / 15:30) con botones interactivos.
#                  Al elegir turno → crea la reserva para TODOS los hijos de la familia.
#   - Botón "No" → no reserva, mensaje corto de agradecimiento.
#
# El estado vive en flags de ab_test (esperando_confirmacion_sabado), NUNCA en
# memoria del proceso (Railway reinicia sin aviso). El QR quedó solo para leads;
# las familias hacen check-in facial al llegar (Mundo Fenix).
#
# El loop del jueves que dispara la plantilla vive en agent/loops.py y usa
# enviar_confirmacion_sabado() de este módulo.

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agent.memory import guardar_mensaje
from agent.ab_test import actualizar_estado_flags
from agent.telegram_bridge import enviar_a_topic
from agent.tools.agenda import gestionar_reserva

logger = logging.getLogger("agentkit")

_TZ_PY = ZoneInfo("America/Asuncion")

_PLANTILLA = "confirmacion_sabado_fenix"

# Turnos ofrecidos al confirmar (mismos valores de HORARIOS FENIX).
_BTN_TURNO_1100 = {"id": "turno_sab_1100", "title": "11:00"}
_BTN_TURNO_1530 = {"id": "turno_sab_1530", "title": "15:30"}
_TURNO_POR_BTN = {"turno_sab_1100": "11:00", "turno_sab_1530": "15:30"}

# Respuestas afirmativas / negativas al botón de la plantilla (texto del quick-reply
# o texto libre del padre mientras el flag está activo).
_SI = {"sí", "si", "dale", "confirmo", "sí, confirmo", "si, confirmo", "va", "sip", "sí!"}
_NO = {"no", "esta vez no", "no puede", "no puede ir", "nop", "no viene"}


def _proximo_sabado(hoy: datetime) -> str:
    """Fecha ISO del sábado de esta semana (la plantilla se manda el jueves)."""
    dias = (5 - hoy.weekday()) % 7   # 5 = sábado
    sabado = hoy + timedelta(days=dias)
    return sabado.strftime("%Y-%m-%d")


async def _espejar(topic_id: int | None, texto: str, telefono: str, tg_group: int):
    """Espeja la respuesta de Aurora al topic de Telegram (best-effort)."""
    if not topic_id:
        return
    try:
        await enviar_a_topic(topic_id, f"🌟 AURORA: {texto}", telefono=telefono, group_override=tg_group)
    except Exception as e:
        logger.warning(f"[CONF-SAB] No se pudo espejar en Telegram: {e}")


async def recolectar_envios() -> list[dict]:
    """Arma la lista de envíos del jueves (niño-eje): una entrada por tutor
    pagador, con TODOS sus hijos al día agrupados.

    Migración FAMILIAS→NIÑO: el "al día" se lee del NIÑO ({AL DÍA?} sobre sus
    PAGOS) y el destinatario sale de los links PADRE/MADRE del niño — la tabla
    FAMILIAS ya no participa (salvo el fallback de niños viejos sin tutores
    linkeados, que resuelve por su FAMILIA).

    Returns:
        [{telefono, nombre_padre, hijos_str, tutor_id}] — solo tutores con
        teléfono e hijos con nombre (los incompletos se saltan).
    """
    from agent.airtable_client import (
        obtener_ninos_al_dia,
        _get_records,
        _ALUMNOS,
        _NEGOCIO_FENIX,
    )

    ninos = await obtener_ninos_al_dia()
    if not ninos:
        return []

    # Todos los tutores Fenix de una vez (filas de ALUMNOS con marca Fenix,
    # paginado) — evita un GET por niño y no trae la tabla compartida entera.
    _f_tut = (f"OR(FIND('{_NEGOCIO_FENIX}', ARRAYJOIN({{NEGOCIO}}))>0, "
              "{HIJOS FENIX (PADRE)}!='', {HIJOS FENIX (MADRE)}!='')")
    tutores_raw = await _get_records(_ALUMNOS, formula=_f_tut, max_records=2000)
    tutor_por_id = {t["id"]: (t.get("fields", {}) or {}) for t in tutores_raw}

    # Agrupar hijos al día por tutor pagador.
    grupos: dict[str, dict] = {}   # tutor_id -> {telefono, nombre_padre, hijos}
    for n in ninos:
        f = n.get("fields", {}) or {}
        nombre_hijo = ((f.get("APODO") or f.get("NOMBRE")) or "").strip()
        if not nombre_hijo:
            continue

        # Candidatos a pagador: PADRE + MADRE (ALUMNOS) del niño (niño-eje).
        candidatos = [
            (tid, tutor_por_id[tid])
            for tid in (f.get("PADRE (ALUMNOS)") or []) + (f.get("MADRE (ALUMNOS)") or [])
            if tid in tutor_por_id
        ]
        # Pagador: el primer tutor con teléfono (ES QUIEN PAGA murió con la
        # tabla TUTORES legacy — ALUMNOS no lo tiene).
        con_tel = [(tid, tf) for tid, tf in candidatos if (tf.get("TELEFONO LIMPIO") or "").strip()]
        pagador = con_tel[0] if con_tel else None
        if not pagador:
            continue
        tid, tf = pagador

        if tid not in grupos:
            _nom = (tf.get("NOMBRE") or "").strip()
            grupos[tid] = {
                "telefono": (tf.get("TELEFONO LIMPIO") or "").strip(),
                "nombre_padre": _nom.split(" ")[0] if _nom else "",
                "hijos": [],
                "tutor_id": tid,
            }
        if nombre_hijo not in grupos[tid]["hijos"]:
            grupos[tid]["hijos"].append(nombre_hijo)

    return [
        {
            "telefono": g["telefono"],
            "nombre_padre": g["nombre_padre"],
            "hijos_str": " y ".join(g["hijos"]),
            "tutor_id": g["tutor_id"],
        }
        for g in grupos.values()
    ]


async def enviar_confirmacion_sabado(telefono: str, proveedor, nombre_padre: str, hijos_str: str) -> bool:
    """Manda la plantilla del jueves y deja el flag esperando la respuesta.

    Usado por el loop del jueves (agent/loops.py). Devuelve True si Meta aceptó
    el envío. Solo marca el flag si el envío salió (si no, no esperamos respuesta).
    """
    ok = await proveedor.enviar_plantilla(
        telefono, _PLANTILLA,
        variables=[nombre_padre or "familia", hijos_str or "tu hijo"],
        language="es_AR",
    )
    if ok:
        await actualizar_estado_flags(telefono, esperando_confirmacion_sabado=True)
        await guardar_mensaje(telefono, "assistant", "[plantilla confirmación sábado enviada]")
        logger.info(f"[CONF-SAB] Plantilla enviada a {telefono} ({hijos_str})")
    return ok


async def manejar_respuesta(
    telefono: str,
    texto: str,
    btn_id: str | None,
    es_boton: bool,
    flags: dict,
    proveedor,
    *,
    topic_id: int | None = None,
    tg_group: int = 0,
) -> str | None:
    """Intercepta la respuesta a la plantilla del jueves y el turno elegido.

    Returns:
        str  → este handler ya respondió; main.py NO debe seguir al menú/brain.
        None → no aplica; seguir el flujo normal de Aurora.
    """
    btn_id = btn_id or ""
    _texto_norm = (texto or "").strip().lower()

    # ── Eligió turno (botón interactivo) → crear la reserva ────────────────
    # No depende del flag: el btn_id solo existe si Aurora mandó estos botones.
    if btn_id in _TURNO_POR_BTN:
        hora = _TURNO_POR_BTN[btn_id]
        fecha = _proximo_sabado(datetime.now(_TZ_PY))
        res = await gestionar_reserva(telefono, "agendar", fecha=fecha, hora=hora)
        await actualizar_estado_flags(telefono, esperando_confirmacion_sabado=False)
        if res.get("agendada"):
            hijos = res.get("hijos", "tu hijo")
            msg = f"¡Listo! Reserva confirmada ✅ {hijos} este sábado a las {hora}h 🌳"
        else:
            msg = res.get("message") or "Uy, no pude confirmar la reserva ahora. Escribime y lo resolvemos 🙏"
        await proveedor.enviar_mensaje(telefono, msg)
        await guardar_mensaje(telefono, "assistant", msg)
        await _espejar(topic_id, msg, telefono, tg_group)
        logger.info(f"[CONF-SAB] {telefono}: turno {hora} → agendada={res.get('agendada')}")
        return "[reserva sábado]"

    # ── Respuesta a la plantilla (solo si estamos esperándola) ─────────────
    if not flags.get("esperando_confirmacion_sabado"):
        return None

    # "Sí" → preguntar el turno con botones
    if _texto_norm in _SI:
        await actualizar_estado_flags(telefono, esperando_confirmacion_sabado=False)
        _pregunta = "¡Genial! 🎉 ¿A qué hora lo llevás este sábado?"
        await proveedor.enviar_botones(telefono, _pregunta, [_BTN_TURNO_1100, _BTN_TURNO_1530])
        await guardar_mensaje(telefono, "assistant", _pregunta)
        await _espejar(topic_id, f"{_pregunta}\n[botones: 11:00 / 15:30]", telefono, tg_group)
        logger.info(f"[CONF-SAB] {telefono}: confirmó — preguntando turno")
        return "[confirmó sábado — pregunta turno]"

    # "No" → no reserva
    if _texto_norm in _NO:
        await actualizar_estado_flags(telefono, esperando_confirmacion_sabado=False)
        msg = "¡Dale, gracias por avisar! 🙌 Cualquier cosa escribime. ¡Nos vemos la próxima! 🌳"
        await proveedor.enviar_mensaje(telefono, msg)
        await guardar_mensaje(telefono, "assistant", msg)
        await _espejar(topic_id, msg, telefono, tg_group)
        logger.info(f"[CONF-SAB] {telefono}: dijo que no viene")
        return "[no viene sábado]"

    # Texto libre ambiguo con el flag activo → dejar que Aurora conversacional
    # responda (el padre pregunta algo antes de confirmar). El flag queda vivo.
    return None
