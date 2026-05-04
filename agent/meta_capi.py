# agent/meta_capi.py — Integración con Meta Conversions API for Business Messaging
# Envía eventos server-side a Meta para optimización de anuncios Click-to-WhatsApp

"""
Eventos implementados:
- LeadSubmitted     -> cuando el lead confirma turno y paga (se crea PRUEBA FENIX)
- Purchase          -> cuando se confirma el pago / inscripción

Usa action_source="business_messaging" + messaging_channel="whatsapp"
+ ctwa_clid para que Meta pueda atribuir la conversión al anuncio.
"""

import os
import time
import logging
import httpx

logger = logging.getLogger("agentkit")

META_CAPI_PIXEL_ID = os.getenv("META_CAPI_PIXEL_ID", "")
META_CAPI_ACCESS_TOKEN = os.getenv("META_CAPI_ACCESS_TOKEN", "")
META_GRAPH_VERSION = "v21.0"
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")


async def _enviar_evento(event_name: str, telefono: str, ctwa_clid: str | None = None,
                          custom_data: dict | None = None) -> bool:
    if not META_CAPI_PIXEL_ID or not META_CAPI_ACCESS_TOKEN:
        logger.warning("[CAPI] META_CAPI_PIXEL_ID o META_CAPI_ACCESS_TOKEN no configurados")
        return False

    url = f"https://graph.facebook.com/{META_GRAPH_VERSION}/{META_CAPI_PIXEL_ID}/events"

    user_data = {}
    if ctwa_clid:
        user_data["ctwa_clid"] = ctwa_clid
    if WHATSAPP_BUSINESS_ACCOUNT_ID:
        user_data["whatsapp_business_account_id"] = WHATSAPP_BUSINESS_ACCOUNT_ID

    evento = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "action_source": "business_messaging",
        "messaging_channel": "whatsapp",
        "user_data": user_data,
    }
    if custom_data:
        evento["custom_data"] = custom_data

    payload = {
        "data": [evento],
        "access_token": META_CAPI_ACCESS_TOKEN,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload)
            if r.status_code == 200:
                logger.info(f"[CAPI] '{event_name}' enviado — ctwa_clid={'sí' if ctwa_clid else 'no'}")
                return True
            else:
                logger.error(f"[CAPI] '{event_name}' falló: {r.status_code} — {r.text}")
                return False
    except Exception as e:
        logger.error(f"[CAPI] Excepción '{event_name}': {e}")
        return False


async def enviar_evento_agenda(telefono: str) -> bool:
    """Evento LeadSubmitted — el lead agendó y pagó su prueba."""
    from agent.memory import obtener_ctwa_clid
    clid = await obtener_ctwa_clid(telefono)
    return await _enviar_evento("LeadSubmitted", telefono, ctwa_clid=clid)


async def enviar_evento_pago(telefono: str) -> bool:
    """Evento Purchase — confirmación de pago/inscripción."""
    from agent.memory import obtener_ctwa_clid
    clid = await obtener_ctwa_clid(telefono)
    return await _enviar_evento("Purchase", telefono, ctwa_clid=clid)
