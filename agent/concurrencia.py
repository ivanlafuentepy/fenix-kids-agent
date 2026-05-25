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
            # Limpiar los más viejos
            oldest = list(_locks_telefono.keys())[:50]
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
