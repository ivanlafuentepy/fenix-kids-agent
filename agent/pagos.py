# agent/pagos.py — Flujo de pagos: comprobante, confirmación admin, estado
# FENIX KIDS ACADEMY

"""
Manejo de pagos por transferencia bancaria.
Estado en memoria (se pierde al reiniciar — aceptable para MVP).

Flujo:
1. Ivan muestra datos bancarios → lead manda foto comprobante
2. Sistema detecta comprobante → responde al lead → envía botones al admin
3. Admin confirma/rechaza → lead recibe resultado → continúa flujo
"""

import logging
from datetime import datetime

logger = logging.getLogger("agentkit")

# ── Datos bancarios ──────────────────────────────────────────────────────────

DATOS_BANCARIOS = (
    "Ivan Lafuente\n"
    "Itaú\n"
    "Cta cte 1074574\n"
    "CI 1604338\n"
    "Cell 0982790407"
)

# Marcador para detectar si Ivan ya mostró los datos bancarios en el historial
CI_BANCARIO = "1604338"

# ── Precios ──────────────────────────────────────────────────────────────────

PRECIOS = {
    "prueba": {"cuota": 90_000, "matricula": 0, "total": 90_000, "label": "PRUEBA 90K"},
    "quincenal_mensual": {"cuota": 250_000, "matricula": 200_000, "total": 450_000, "label": "QUINCENAL MENSUAL"},
    "quincenal_trimestral": {"cuota": 450_000, "matricula": 150_000, "total": 600_000, "label": "QUINCENAL TRIMESTRAL"},
    "semanal_mensual": {"cuota": 350_000, "matricula": 200_000, "total": 550_000, "label": "SEMANAL MENSUAL"},
    "semanal_trimestral": {"cuota": 700_000, "matricula": 150_000, "total": 850_000, "label": "SEMANAL TRIMESTRAL"},
}

# ── Detección de comprobante ─────────────────────────────────────────────────

_KEYWORDS_PAGO = [
    "comprobante", "transferi", "transferí",
    "pagué", "pague", "te mandé", "te mande",
    "ya pague", "ya pagué", "hice la transferencia",
    "ahí te mandé", "ahi te mande",
]


def es_posible_comprobante(texto: str, historial: list[dict]) -> bool:
    """
    Detecta si el mensaje es un comprobante de pago.
    Dos condiciones deben cumplirse AMBAS:
    1. Es media ([imagen]/[documento]) o contiene keywords de pago
    2. Ivan ya envió los datos bancarios (CI 1604338 en mensajes del assistant)
    """
    # Condición 1: parece un pago
    es_media = texto in ("[imagen]", "[documento]")
    tiene_keyword = any(k in texto.lower() for k in _KEYWORDS_PAGO)
    parece_pago = es_media or tiene_keyword

    if not parece_pago:
        return False

    # Condición 2: datos bancarios ya enviados
    datos_enviados = any(
        CI_BANCARIO in m.get("content", "")
        for m in historial
        if m.get("role") == "assistant"
    )

    return datos_enviados


# ── Estado en memoria ────────────────────────────────────────────────────────

# Lead que envió comprobante, esperando que admin confirme/rechace
_pago_pendiente_confirmacion: dict[str, dict] = {}
# key: telefono_lead
# value: {"tipo": str, "plan": str, "monto": int, "ts": datetime, "media_id": str|None}

# Lead cuyo pago fue confirmado, esperando que complete datos post-pago
_esperando_post_pago: dict[str, str] = {}
# key: telefono_lead
# value: tipo ("prueba" | "inscripcion")


def registrar_pago_pendiente(
    telefono: str,
    tipo: str,
    plan: str = "",
    monto: int = 0,
    media_id: str | None = None,
):
    """Registra que el lead envió un comprobante y esperamos confirmación del admin."""
    _pago_pendiente_confirmacion[telefono] = {
        "tipo": tipo,
        "plan": plan,
        "monto": monto,
        "ts": datetime.utcnow(),
        "media_id": media_id,
    }
    logger.info(f"[PAGOS] Pago pendiente registrado: {telefono} tipo={tipo} plan={plan} monto={monto}")


def tiene_pago_pendiente(telefono: str | None = None) -> bool:
    """Verifica si hay pago(s) pendiente(s). Si no se pasa teléfono, verifica si hay alguno."""
    if telefono:
        return telefono in _pago_pendiente_confirmacion
    return len(_pago_pendiente_confirmacion) > 0


def obtener_pago_pendiente(telefono: str | None = None) -> tuple[str | None, dict | None]:
    """
    Retorna (telefono, datos) del pago pendiente.
    Si se pasa teléfono, busca ese específico. Si no, retorna el primero.
    """
    if telefono and telefono in _pago_pendiente_confirmacion:
        return telefono, _pago_pendiente_confirmacion[telefono]
    if not telefono and _pago_pendiente_confirmacion:
        tel = next(iter(_pago_pendiente_confirmacion))
        return tel, _pago_pendiente_confirmacion[tel]
    return None, None


def confirmar_pago(telefono: str) -> dict | None:
    """Confirma el pago y lo saca del dict de pendientes. Retorna los datos o None."""
    datos = _pago_pendiente_confirmacion.pop(telefono, None)
    if datos:
        logger.info(f"[PAGOS] Pago CONFIRMADO para {telefono}")
    return datos


def rechazar_pago(telefono: str) -> dict | None:
    """Rechaza el pago y lo saca del dict de pendientes. Retorna los datos o None."""
    datos = _pago_pendiente_confirmacion.pop(telefono, None)
    if datos:
        logger.info(f"[PAGOS] Pago RECHAZADO para {telefono}")
    return datos


# ── Detección de tipo de pago ────────────────────────────────────────────────

_KEYWORDS_INSCRIPCION = [
    "inscribirme", "inscribir", "inscripcion", "inscripción",
    "de una", "directo", "quiero el plan", "me inscribo",
]


def detectar_tipo_pago(historial: list[dict]) -> str:
    """
    Determina si el lead quiere prueba o inscripción según el historial.
    Default: prueba (lo más común en Fenix).
    """
    msgs_lead = [m.get("content", "").lower() for m in historial if m.get("role") == "user"]
    for ml in msgs_lead:
        if any(k in ml for k in _KEYWORDS_INSCRIPCION):
            return "inscripcion"
    return "prueba"


def formatear_monto(monto: int) -> str:
    """Formatea monto en guaraníes: 450000 → '450.000'"""
    return f"{monto:,}".replace(",", ".")
