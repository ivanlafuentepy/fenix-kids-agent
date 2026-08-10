# agent/envio_seguro.py — Envío al padre con reintento y alerta si no llega
#
# Por qué existe: `proveedor.enviar_mensaje` devuelve bool y NUNCA lanza (token
# muerto, 4xx de Meta, red caída → False). Todos los call sites ignoraban ese
# bool: no había reintento, nadie se enteraba, y el historial quedaba diciendo
# que se había respondido. El padre veía silencio (auditoría de silencio 09/08, S8).
#
# Acá el envío se reintenta una vez ante un fallo transitorio y, si tampoco sale,
# se alerta al admin con el texto que no llegó para que pueda mandarlo a mano.

import asyncio
import logging
import os

logger = logging.getLogger("agentkit")

_ESPERA_REINTENTO = 2.0   # segundos; un blip de red se resuelve solo


async def _alertar_admin(telefono: str, texto: str, proveedor, motivo: str):
    """Le avisa al admin que un mensaje NO llegó. Best-effort."""
    admin = os.getenv("ADMIN_PHONE", "")
    if not admin or admin == telefono:
        return
    try:
        await proveedor.enviar_mensaje(
            admin,
            f"🚨 NO PUDE ENVIAR el mensaje a https://wa.me/{telefono}\n"
            f"Motivo: {motivo}\n\n"
            f"Texto que quedó sin llegar:\n{texto[:600]}",
        )
    except Exception as e:
        logger.error(f"[ENVIO] Tampoco pude alertar al admin sobre {telefono}: {e}")


async def enviar_al_padre(proveedor, telefono: str, texto: str) -> bool:
    """Envía un texto al padre; reintenta una vez y alerta si no llega.

    Retorna True si salió (en el primer intento o en el reintento).
    """
    if not (texto or "").strip():
        logger.error(f"[ENVIO] Texto VACÍO para {telefono} — no se envía")
        return False
    try:
        if await proveedor.enviar_mensaje(telefono, texto):
            return True
    except Exception as e:
        logger.error(f"[ENVIO] Excepción enviando a {telefono}: {e}")

    logger.warning(f"[ENVIO] Falló el envío a {telefono} — reintento en {_ESPERA_REINTENTO}s")
    await asyncio.sleep(_ESPERA_REINTENTO)
    try:
        if await proveedor.enviar_mensaje(telefono, texto):
            logger.info(f"[ENVIO] Reintento OK para {telefono}")
            return True
    except Exception as e:
        logger.error(f"[ENVIO] Excepción en el reintento a {telefono}: {e}")

    logger.error(f"[ENVIO] NO se pudo enviar a {telefono} tras 2 intentos")
    await _alertar_admin(telefono, texto, proveedor, "Meta rechazó el envío 2 veces")
    return False


async def enviar_botones_al_padre(proveedor, telefono: str, texto: str, botones: list) -> bool:
    """Igual que enviar_al_padre pero con botones interactivos.

    Si el interactivo no sale (Meta los rechaza más seguido que el texto plano),
    cae a texto plano: mejor el texto sin botones que el silencio — era el caso
    del PRIMER mensaje de un lead nuevo, que se perdía entero (S14).
    """
    try:
        if await proveedor.enviar_botones(telefono, texto, botones):
            return True
    except Exception as e:
        logger.error(f"[ENVIO] Excepción enviando botones a {telefono}: {e}")

    logger.warning(f"[ENVIO] Botones fallaron para {telefono} — caigo a texto plano")
    _opciones = "\n".join(
        f"• {b.get('title', '')}" for b in (botones or []) if isinstance(b, dict)
    )
    _texto_plano = f"{texto}\n\n{_opciones}".strip() if _opciones else texto
    return await enviar_al_padre(proveedor, telefono, _texto_plano)
