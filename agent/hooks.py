# agent/hooks.py — Sistema de hooks PreToolUse / PostToolUse
# Validan parámetros antes de ejecutar y procesan resultados después

import asyncio
import logging
import time
from datetime import date
from zoneinfo import ZoneInfo
from typing import Callable, Awaitable

logger = logging.getLogger("agentkit")

_TZ_PY = ZoneInfo("America/Asuncion")
_HORARIOS_VALIDOS = {"11:00", "15:30"}

# ── Tipos ──────────────────────────────────────────────────────────
# Pre:  async (tool_name, params, context) -> dict|None  (None=OK, dict con error=bloquear)
# Post: async (tool_name, params, result, context) -> dict  (result posiblemente modificado)

PreHookFn = Callable[[str, dict, dict], Awaitable[dict | None]]
PostHookFn = Callable[[str, dict, dict, dict], Awaitable[dict]]

_pre_hooks: list[PreHookFn] = []
_post_hooks: list[PostHookFn] = []


def registrar_pre_hook(fn: PreHookFn):
    _pre_hooks.append(fn)


def registrar_post_hook(fn: PostHookFn):
    _post_hooks.append(fn)


async def ejecutar_pre_hooks(tool_name: str, params: dict, context: dict) -> dict | None:
    """Ejecuta todos los pre-hooks. Si alguno retorna error, bloquea la tool."""
    for hook in _pre_hooks:
        try:
            result = await hook(tool_name, params, context)
            if result and result.get("error"):
                logger.info(f"[HOOK-PRE] {hook.__name__} bloqueó {tool_name}: {result.get('message', '')}")
                return result
        except Exception as e:
            logger.error(f"[HOOK-PRE] Error en {hook.__name__}: {e}")
    return None


async def ejecutar_post_hooks(tool_name: str, params: dict, result: dict, context: dict) -> dict:
    """Ejecuta todos los post-hooks. Cada uno puede modificar el result."""
    for hook in _post_hooks:
        try:
            result = await hook(tool_name, params, result, context)
        except Exception as e:
            logger.error(f"[HOOK-POST] Error en {hook.__name__}: {e}")
    return result


# ══════════════════════════════════════════════════════════════════
# PRE-HOOKS CONCRETOS
# ══════════════════════════════════════════════════════════════════

_TOOLS_CON_HORA = {
    "confirmar_reserva", "gestionar_reserva",
    "consultar_disponibilidad", "consultar_agendados", "reagendar_clase",
}


async def validar_fecha_hora(tool_name: str, params: dict, context: dict) -> dict | None:
    """Valida hora ∈ {9:30, 11:00, 15:30}, fecha es sábado futuro. Normaliza fecha a ISO."""
    if tool_name not in _TOOLS_CON_HORA:
        return None

    # Validar hora
    hora = params.get("hora") or params.get("hora_nueva")
    if hora and hora not in _HORARIOS_VALIDOS:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"Hora '{hora}' no es válida. Los horarios son: 9:30, 11:00 y 15:30.",
        }

    # Validar y normalizar fecha
    fecha = params.get("fecha")
    if not fecha:
        return None  # algunos tools permiten fecha vacía (consultar sin filtro)

    from agent.tools.reservas import _parsear_fecha
    fecha_iso = _parsear_fecha(fecha)
    if not fecha_iso:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"No pude interpretar la fecha '{fecha}'. Usá formato como '31 de mayo' o '31/5'.",
        }

    d = date.fromisoformat(fecha_iso)

    # Sábado = weekday 5
    if d.weekday() != 5:
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"El {fecha_iso} es {dias[d.weekday()]}, no sábado. FENIX KIDS solo tiene clases los sábados.",
        }

    # Fecha futura (permitir hoy si es sábado)
    from datetime import datetime
    hoy = datetime.now(_TZ_PY).date()
    if d < hoy:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"El {fecha_iso} ya pasó. Elegí un sábado futuro.",
        }

    # Normalizar: reemplazar param original con ISO
    params["fecha"] = fecha_iso
    return None


# Anti-escalación spam: max 1 por teléfono por hora
_escalaciones_recientes: dict[str, float] = {}  # telefono -> timestamp


async def anti_escalacion_spam(tool_name: str, params: dict, context: dict) -> dict | None:
    """Máximo 1 escalación por teléfono por hora."""
    if tool_name != "escalar_a_humano":
        return None

    telefono = context.get("telefono", "")
    ahora = time.time()

    # Limpiar entradas viejas (> 1 hora)
    _viejas = [k for k, v in _escalaciones_recientes.items() if ahora - v > 3600]
    for k in _viejas:
        del _escalaciones_recientes[k]

    ultima = _escalaciones_recientes.get(telefono)
    if ultima and ahora - ultima < 3600:
        minutos_restantes = int((3600 - (ahora - ultima)) / 60)
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": f"Ya se escaló esta conversación hace poco. El equipo ya fue notificado. Podés intentar de nuevo en {minutos_restantes} minutos.",
        }

    _escalaciones_recientes[telefono] = ahora
    return None


# ══════════════════════════════════════════════════════════════════
# POST-HOOKS CONCRETOS
# ══════════════════════════════════════════════════════════════════

async def notificar_telegram(tool_name: str, params: dict, result: dict, context: dict) -> dict:
    """Notifica reservas y cancelaciones al grupo de Telegram."""
    if result.get("error"):
        return result

    if tool_name in ("gestionar_reserva", "confirmar_reserva"):
        try:
            from agent.telegram_bridge import enviar_a_topic, obtener_o_crear_topic
            telefono = context.get("telefono", "")
            _es_cancelacion = result.get("cancelada")
            _es_reagendada = result.get("reagendada")
            if _es_cancelacion:
                accion = "❌ CANCELACIÓN"
            elif _es_reagendada:
                accion = "🔄 REAGENDAMIENTO"
            else:
                accion = "✅ RESERVA"
            fecha = result.get("fecha", result.get("fecha_display", ""))
            hora = result.get("hora", "")
            hijos = result.get("hijos", "")
            link = f"https://wa.me/{telefono}"
            msg = f"📋 {accion}: {hijos} — {fecha} {hora}\n{link}"
            topic_id = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            if topic_id:
                asyncio.create_task(enviar_a_topic(topic_id, msg, telefono=telefono))
        except Exception as e:
            logger.error(f"[HOOK-POST] Error notificando Telegram: {e}")

    return result


async def enviar_capi_event(tool_name: str, params: dict, result: dict, context: dict) -> dict:
    """Envía evento Meta CAPI para tracking de conversiones."""
    if result.get("error"):
        return result

    if tool_name == "confirmar_reserva" and result.get("confirmada"):
        try:
            from agent.meta_capi import enviar_lead_submitted
            telefono = context.get("telefono", "")
            asyncio.create_task(enviar_lead_submitted(telefono))
            logger.info(f"[HOOK-POST] CAPI LeadSubmitted enviado para {telefono}")
        except Exception as e:
            logger.error(f"[HOOK-POST] Error CAPI: {e}")

    return result


# ══════════════════════════════════════════════════════════════════
# REGISTRO AUTOMÁTICO
# ══════════════════════════════════════════════════════════════════

registrar_pre_hook(validar_fecha_hora)
registrar_pre_hook(anti_escalacion_spam)
registrar_post_hook(notificar_telegram)
registrar_post_hook(enviar_capi_event)
