# agent/night_mode.py — Modo noche: respuesta automática 23:00–07:00
# FENIX KIDS ACADEMY

"""
Si un lead escribe entre 23:00 y 07:00 hora Paraguay, el agente
responde una sola vez con un mensaje fijo y marca al lead como pendiente.
A las 07:00 procesa todos los pendientes con Claude.

Persistencia: flag noche_pendiente en ConversacionAB (PostgreSQL).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("agentkit")

_TZ_PARAGUAY = ZoneInfo("America/Asuncion")

_HORA_INICIO_NOCHE = 23
_HORA_FIN_NOCHE = 6

MENSAJE_NOCHE = (
    "Muchas gracias por contactarnos, de 23 a 06 estamos fuera de servicio. "
    "Mañana a las 06:00 serás el primero en recibir nuestra atención 🥋"
)


def _paraguay_now() -> datetime:
    return datetime.now(_TZ_PARAGUAY)


def es_horario_nocturno(dt_utc: datetime | None = None) -> bool:
    if dt_utc is None:
        local = _paraguay_now()
    else:
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
        local = dt_utc.astimezone(_TZ_PARAGUAY)
    h = local.hour
    return h >= _HORA_INICIO_NOCHE or h < _HORA_FIN_NOCHE


def _segundos_hasta_proxima_7am() -> float:
    local = _paraguay_now()
    if local.hour < _HORA_FIN_NOCHE:
        target = local.replace(hour=_HORA_FIN_NOCHE, minute=0, second=0, microsecond=0)
    else:
        target = (local + timedelta(days=1)).replace(hour=_HORA_FIN_NOCHE, minute=0, second=0, microsecond=0)
    return max(0.0, (target - local).total_seconds())


async def procesar_leads_pendientes(
    proveedor,
    obtener_historial_fn,
    guardar_mensaje_fn,
    generar_respuesta_fn,
    obtener_o_crear_topic_fn,
    enviar_a_topic_fn,
):
    """Procesa leads con noche_pendiente=True a las 07:00."""
    from agent.ab_test import obtener_leads_noche_pendiente, limpiar_noche_pendiente

    pendientes = await obtener_leads_noche_pendiente()
    if not pendientes:
        logger.info("[NOCHE 07:00] Sin leads pendientes")
        return

    logger.info(f"[NOCHE 07:00] Procesando {len(pendientes)} lead(s)")

    for telefono in pendientes:
        try:
            await limpiar_noche_pendiente(telefono)
            historial = await obtener_historial_fn(telefono)
            if not historial:
                continue

            ultimo_user_idx = None
            for i in range(len(historial) - 1, -1, -1):
                if historial[i].get("role") == "user":
                    ultimo_user_idx = i
                    break
            if ultimo_user_idx is None:
                continue

            mensaje_actual = historial[ultimo_user_idx]["content"]
            historial_previo = historial[:ultimo_user_idx]

            respuesta = await generar_respuesta_fn(
                mensaje=mensaje_actual,
                historial=historial_previo,
                agent_actual="ivan",
            )

            await guardar_mensaje_fn(telefono, "assistant", respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
            logger.info(f"[NOCHE 07:00] ✅ {telefono}: {respuesta[:60]}...")

            try:
                topic_id = await obtener_o_crear_topic_fn(telefono, f"📱 {telefono}")
                if topic_id:
                    await enviar_a_topic_fn(topic_id, f"🌅 IVAN [07:00]: {respuesta}", telefono=telefono)
            except Exception as e:
                logger.error(f"[NOCHE 07:00] Error Telegram {telefono}: {e}")

            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"[NOCHE 07:00] Error {telefono}: {e}")


async def wakeup_loop(processor_callback):
    """Loop diario que despierta a las 07:00 PY."""
    while True:
        delay = _segundos_hasta_proxima_7am()
        logger.info(f"[NOCHE] Wakeup loop dormirá {delay:.0f}s")
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        try:
            await processor_callback()
        except Exception as e:
            logger.error(f"[NOCHE] Error en wakeup: {e}")
        await asyncio.sleep(60)
