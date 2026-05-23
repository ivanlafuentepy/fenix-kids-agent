# agent/tool_executor.py — Dispatcher de tools para Claude API
# Mapea tool_name → función Python y ejecuta.

import logging

from agent.tools.info import (
    consultar_precios, consultar_horarios, consultar_ubicacion,
    consultar_duracion, consultar_que_llevar, consultar_devolucion,
    consultar_medios_pago, enviar_datos_bancarios,
)
from agent.tools.reservas import reagendar_clase

logger = logging.getLogger("agentkit")

# Registro de tools: nombre → función async
_TOOLS = {
    "consultar_precios": consultar_precios,
    "consultar_horarios": consultar_horarios,
    "consultar_ubicacion": consultar_ubicacion,
    "consultar_duracion": consultar_duracion,
    "consultar_que_llevar": consultar_que_llevar,
    "consultar_devolucion": consultar_devolucion,
    "consultar_medios_pago": consultar_medios_pago,
    "enviar_datos_bancarios": enviar_datos_bancarios,
    "reagendar_clase": reagendar_clase,
}

# Tools que necesitan el teléfono del padre (acceden a Airtable)
_TOOLS_CON_TELEFONO = {"reagendar_clase"}


async def ejecutar_tool(nombre: str, params: dict, telefono: str) -> dict:
    """
    Ejecuta un tool y retorna el resultado como dict.

    Args:
        nombre: Nombre del tool (debe coincidir con tool_definitions.py)
        params: Parámetros que Claude envió en el tool_use
        telefono: Teléfono del padre (se inyecta automáticamente para tools que lo necesitan)

    Returns:
        Dict con al menos "texto" (str) + metadata opcional (enviar_afiche, enviar_admin, etc.)
    """
    fn = _TOOLS.get(nombre)
    if not fn:
        logger.warning(f"[TOOL] Tool desconocido: {nombre}")
        return {"texto": f"Tool {nombre} no existe.", "error": True}

    if nombre in _TOOLS_CON_TELEFONO:
        params["telefono"] = telefono

    try:
        resultado = await fn(**params)
        logger.info(f"[TOOL] {nombre}({params}) → {list(resultado.keys())}")
        return resultado
    except Exception as e:
        logger.error(f"[TOOL] Error ejecutando {nombre}: {e}")
        return {"texto": "Hubo un error procesando tu solicitud.", "error": True}
