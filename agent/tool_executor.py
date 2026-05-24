# agent/tool_executor.py — Dispatcher de tools para Claude API
# Solo tools de ACCIÓN (reagendar, confirmar reserva, escalar, etc.)
# FAQ simples se manejan con interceptores regex (gratis, sin API).

import logging

from agent.tools.reservas import reagendar_clase, confirmar_reserva_prueba
from agent.tools.escalacion import escalar_a_humano
from agent.tools.disponibilidad import consultar_disponibilidad, consultar_agendados
from agent.tools.llamada import programar_llamada
from agent.tools.agenda import agendar_clase, cancelar_reserva
from agent.tools.registro import registrar_familia, registrar_hijo

logger = logging.getLogger("agentkit")

# Registro de tools: nombre → función async
_TOOLS = {
    # Ivan
    "reagendar_clase": reagendar_clase,
    "confirmar_reserva": confirmar_reserva_prueba,
    "escalar_a_humano": escalar_a_humano,
    "consultar_disponibilidad": consultar_disponibilidad,
    "programar_llamada": programar_llamada,
    # Aurora
    "agendar_clase": agendar_clase,
    "cancelar_reserva": cancelar_reserva,
    "consultar_agendados": consultar_agendados,
    "registrar_familia": registrar_familia,
    "registrar_hijo": registrar_hijo,
}

# Tools que necesitan el teléfono del padre (acceden a Airtable/Telegram)
_TOOLS_CON_TELEFONO = {*_TOOLS.keys()}  # todas necesitan teléfono

# Tools que necesitan familia_id (Aurora: operaciones sobre familias inscriptas)
_TOOLS_CON_FAMILIA = {"agendar_clase", "cancelar_reserva", "registrar_hijo", "registrar_familia", "consultar_agendados"}


async def ejecutar_tool(nombre: str, params: dict, telefono: str) -> dict:
    """
    Ejecuta un tool y retorna el resultado como dict con errores estructurados.

    Errores siguen el formato Anthropic:
    {
        "error": True,
        "error_category": "transient" | "validation" | "business",
        "is_retryable": bool,
        "message": str,
        "attempted_query": str,
    }
    """
    fn = _TOOLS.get(nombre)
    if not fn:
        logger.warning(f"[TOOL] Tool desconocido: {nombre}")
        return {
            "texto": f"Tool '{nombre}' no existe. Tools disponibles: {', '.join(_TOOLS.keys())}.",
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"Tool '{nombre}' no registrado.",
            "attempted_query": f"{nombre}({params})",
        }

    if nombre in _TOOLS_CON_TELEFONO:
        params["telefono"] = telefono

    # Resolver familia_id para tools de Aurora que lo necesitan
    if nombre in _TOOLS_CON_FAMILIA and "familia_id" not in params:
        try:
            from agent.ab_test import obtener_familia_id
            from agent.airtable_client import buscar_familia_por_telefono
            fam_id = await obtener_familia_id(telefono)
            if not fam_id:
                fam = await buscar_familia_por_telefono(telefono)
                if fam:
                    fam_id = fam["id"]
            params["familia_id"] = fam_id  # puede ser None, la tool maneja el error
        except Exception as e:
            logger.warning(f"[TOOL] Error resolviendo familia_id para {nombre}: {e}")
            params["familia_id"] = None

    try:
        resultado = await fn(**params)
        if "error" not in resultado:
            resultado["error"] = False
        logger.info(f"[TOOL] {nombre}({params}) → {list(resultado.keys())}")
        return resultado

    except (TimeoutError, ConnectionError, OSError) as e:
        logger.error(f"[TOOL] Error transitorio en {nombre}: {e}")
        return {
            "texto": "El servicio está temporalmente no disponible. Intentá de nuevo en unos segundos.",
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": f"Error transitorio en {nombre}: {type(e).__name__}",
            "attempted_query": f"{nombre}({params})",
        }

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"[TOOL] Error de validación en {nombre}: {e}")
        return {
            "texto": f"Datos inválidos: {e}",
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"Error de validación en {nombre}: {e}",
            "attempted_query": f"{nombre}({params})",
        }

    except Exception as e:
        error_msg = str(e).lower()
        # Detectar errores transitorios por contenido del mensaje
        if any(k in error_msg for k in ("timeout", "connect", "overloaded", "rate", "429", "503")):
            logger.error(f"[TOOL] Error transitorio (detectado) en {nombre}: {e}")
            return {
                "texto": "El servicio está temporalmente no disponible.",
                "error": True,
                "error_category": "transient",
                "is_retryable": True,
                "message": f"Error transitorio en {nombre}: {e}",
                "attempted_query": f"{nombre}({params})",
            }

        logger.error(f"[TOOL] Error interno en {nombre}: {e}")
        return {
            "texto": f"Error interno procesando {nombre}.",
            "error": True,
            "error_category": "internal",
            "is_retryable": False,
            "message": f"Error en {nombre}: {str(e)[:200]}",
            "attempted_query": f"{nombre}({params})",
        }
