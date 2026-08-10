# agent/concurrencia.py — Locks por teléfono, rate limit y fire-and-forget
# Extraído de main.py — sin cambios de lógica

import asyncio
import logging
import time as _time

logger = logging.getLogger("agentkit")

# Lock por teléfono: evita race conditions con mensajes rápidos
_locks_telefono: dict[str, asyncio.Lock] = {}
_MAX_LOCKS = 200


def _obtener_lock(telefono: str) -> asyncio.Lock:
    """Retorna un lock exclusivo por teléfono (evita procesamiento paralelo)."""
    if telefono not in _locks_telefono:
        if len(_locks_telefono) > _MAX_LOCKS:
            # Limpiar los más viejos — pero NUNCA un lock tomado: si se borra
            # mientras alguien lo tiene, el próximo mensaje del mismo teléfono
            # crea un lock nuevo y los dos se procesan EN PARALELO (historial
            # desordenado, flags pisados — auditoría 04-07-26 M2).
            oldest = [k for k in list(_locks_telefono.keys()) if not _locks_telefono[k].locked()][:50]
            for k in oldest:
                _locks_telefono.pop(k, None)
        _locks_telefono[telefono] = asyncio.Lock()
    return _locks_telefono[telefono]


# Rate limit por teléfono: máx 10 mensajes en 60 segundos
_rate_limit: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 60


def _check_rate_limit(telefono: str) -> bool:
    """Retorna True si el teléfono excede el rate limit."""
    ahora = _time.time()
    if telefono not in _rate_limit:
        _rate_limit[telefono] = []
    # Limpiar entradas viejas
    _rate_limit[telefono] = [t for t in _rate_limit[telefono] if ahora - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit[telefono]) >= _RATE_LIMIT_MAX:
        return True
    _rate_limit[telefono].append(ahora)
    return False


def _fire_and_forget(coro):
    """Lanza un task async con logging de errores."""
    task = asyncio.create_task(coro)
    task.add_done_callback(
        lambda t: logger.error(f"[BACKGROUND] Task falló: {t.exception()}")
        if not t.cancelled() and t.exception() else None
    )
    return task


# ── Mensajes en vuelo ────────────────────────────────────────────────────────
# El webhook responde 200 a Meta y procesa en background: si el proceso muere
# (CADA git push redeploya Railway), esos mensajes quedaban marcados como
# procesados por la dedup y no se contestaban NUNCA (auditoría de silencio S7).
# Se registran acá para poder esperarlos en el shutdown.
_mensajes_en_vuelo: set = set()


def procesar_mensaje_task(coro):
    """Como _fire_and_forget, pero la task queda registrada como 'en vuelo'."""
    task = _fire_and_forget(coro)
    _mensajes_en_vuelo.add(task)
    task.add_done_callback(_mensajes_en_vuelo.discard)
    return task


async def esperar_mensajes_en_vuelo(timeout: float = 15.0) -> int:
    """Espera a que terminen los mensajes que se están procesando.

    Se llama en el shutdown, ANTES de cancelar los loops. Railway da unos
    segundos de gracia tras el SIGTERM: alcanzan para terminar de contestar.
    Devuelve cuántos quedaron sin terminar (0 = todos contestados).
    """
    pendientes = {t for t in _mensajes_en_vuelo if not t.done()}
    if not pendientes:
        return 0
    logger.warning(f"[SHUTDOWN] Esperando {len(pendientes)} mensaje(s) en vuelo (máx {timeout}s)")
    _, sin_terminar = await asyncio.wait(pendientes, timeout=timeout)
    if sin_terminar:
        logger.error(f"[SHUTDOWN] {len(sin_terminar)} mensaje(s) quedaron sin responder por el reinicio")
    else:
        logger.info("[SHUTDOWN] Todos los mensajes en vuelo quedaron contestados")
    return len(sin_terminar)
