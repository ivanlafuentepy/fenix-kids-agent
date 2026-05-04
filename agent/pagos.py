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
    "prueba_2": {"cuota": 120_000, "matricula": 0, "total": 120_000, "label": "PRUEBA 120K (2 hijos)"},
    "prueba_3": {"cuota": 150_000, "matricula": 0, "total": 150_000, "label": "PRUEBA 150K (3 hijos)"},
    "quincenal_mensual": {"cuota": 250_000, "matricula": 200_000, "total": 450_000, "label": "QUINCENAL MENSUAL"},
    "quincenal_trimestral": {"cuota": 450_000, "matricula": 140_000, "total": 590_000, "label": "QUINCENAL TRIMESTRAL"},
    "semanal_mensual": {"cuota": 350_000, "matricula": 200_000, "total": 550_000, "label": "SEMANAL MENSUAL"},
    "semanal_trimestral": {"cuota": 690_000, "matricula": 140_000, "total": 830_000, "label": "SEMANAL TRIMESTRAL"},
}


def monto_prueba_por_hijos(historial: list[dict]) -> int:
    """Detecta cuántos hijos vienen según el historial y retorna el monto correcto."""
    import re
    texto_completo = " ".join(m.get("content", "").lower() for m in historial)
    # Buscar menciones de cantidad de hijos
    if re.search(r"(tres|3)\s*(hijos|hermanos|chicos|nenes)", texto_completo):
        return 150_000
    if re.search(r"(dos|2)\s*(hijos|hermanos|chicos|nenes)", texto_completo):
        return 120_000
    # Default: 1 hijo = 90mil
    return 90_000

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
    Tres condiciones deben cumplirse TODAS:
    1. Es media ([imagen]/[documento]) o contiene keywords de pago
    2. Ivan ya envió los datos bancarios (CI 1604338 en mensajes del assistant)
    3. El lead pidió pagar/agendar (evita falso positivo con fotos casuales)
    """
    # Condición 1: SOLO imagen o documento es comprobante.
    # Texto NUNCA es comprobante — evita falsos positivos con "transferir",
    # "comprobante", "en la semana te transfiero", etc.
    es_media = texto in ("[imagen]", "[documento]")
    if not es_media:
        return False

    # Condición 2: datos bancarios ya enviados
    datos_enviados = any(
        CI_BANCARIO in m.get("content", "")
        for m in historial
        if m.get("role") == "assistant"
    )

    if not datos_enviados:
        return False

    # Condición 3: verificar contexto de pago en mensajes recientes.
    # Esto evita que una foto casual (del hijo, etc.) se marque como comprobante.
    if es_media:
        _keywords_contexto_pago = [
            "transfer", "pago", "pague", "pagué", "comprobante",
            "mand", "prueba", "90", "inscri", "itaú", "itau",
        ]
        msgs_lead_recientes = [
            m.get("content", "").lower()
            for m in historial[-10:]
            if m.get("role") == "user"
        ]
        msgs_agente_recientes = [
            m.get("content", "").lower()
            for m in historial[-6:]
            if m.get("role") == "assistant"
        ]
        # El agente mencionó transferencia/comprobante recientemente
        agente_pidio_pago = any(
            any(k in msg for k in ["transferencia", "comprobante", CI_BANCARIO])
            for msg in msgs_agente_recientes
        )
        # El lead mencionó algo de pago
        lead_hablo_pago = any(
            any(k in msg for k in _keywords_contexto_pago)
            for msg in msgs_lead_recientes
        )
        if not agente_pidio_pago and not lead_hablo_pago:
            return False

    return True


# ── Estado persistente en PostgreSQL (sobrevive reinicios) ────────────────────

from agent.memory import (
    registrar_pago_pendiente_db,
    obtener_pago_pendiente_db,
    tiene_pago_pendiente_db,
    resolver_pago_db,
)


async def registrar_pago_pendiente(
    telefono: str,
    tipo: str,
    plan: str = "",
    monto: int = 0,
    media_id: str | None = None,
):
    """Registra que el lead envió un comprobante y esperamos confirmación del admin."""
    await registrar_pago_pendiente_db(telefono, tipo, plan, monto, media_id)
    logger.info(f"[PAGOS] Pago pendiente registrado: {telefono} tipo={tipo} plan={plan} monto={monto}")


async def tiene_pago_pendiente(telefono: str | None = None) -> bool:
    """Verifica si hay pago(s) pendiente(s)."""
    return await tiene_pago_pendiente_db(telefono)


async def obtener_pago_pendiente(telefono: str | None = None) -> tuple[str | None, dict | None]:
    """Retorna (telefono, datos) del pago pendiente más reciente."""
    return await obtener_pago_pendiente_db(telefono)


async def confirmar_pago(telefono: str) -> dict | None:
    """Confirma el pago en PostgreSQL. Retorna los datos o None."""
    datos = await resolver_pago_db(telefono, "confirmado")
    if datos:
        logger.info(f"[PAGOS] Pago CONFIRMADO para {telefono}")
    return datos


async def rechazar_pago(telefono: str) -> dict | None:
    """Rechaza el pago en PostgreSQL. Retorna los datos o None."""
    datos = await resolver_pago_db(telefono, "rechazado")
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
