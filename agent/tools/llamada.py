# agent/tools/llamada.py — Programar llamada de callback
# Extraído de main.py:270-323

import json
import logging
import os
import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from agent.memory import crear_recordatorio, cancelar_recordatorios_por_telefono

logger = logging.getLogger("agentkit")
_TZ_PY = ZoneInfo("America/Asuncion")


async def programar_llamada(
    telefono: str,
    hora_llamada: str,
) -> dict:
    """
    Programa un recordatorio para que Ivan llame al padre a la hora indicada.
    Si la hora ya pasó, retorna aviso para llamar ahora.

    Retorna: {programada, hora, texto}
    """
    # Cancelar llamadas anteriores para este teléfono
    await cancelar_recordatorios_por_telefono(telefono, tipo="llamada")

    # Parsear hora: "15:00", "3pm", "3 de la tarde", "15", "3"
    hora_num = None
    minuto = 0
    _m = re.search(r'(\d{1,2})[:\.](\d{2})', hora_llamada)
    if _m:
        hora_num = int(_m.group(1))
        minuto = int(_m.group(2))
    else:
        _m2 = re.search(r'(\d{1,2})', hora_llamada)
        if _m2:
            hora_num = int(_m2.group(1))

    if hora_num is None:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"No pude interpretar la hora '{hora_llamada}'. Usá formato como '15:00' o '3pm'.",
        }

    # Si hora < 8, asumir PM
    if hora_num < 8:
        hora_num += 12

    hoy = datetime.now(_TZ_PY).date()
    envio_local = datetime.combine(hoy, time(hora_num, minuto), tzinfo=_TZ_PY)
    envio_utc = envio_local.astimezone(timezone.utc).replace(tzinfo=None)

    if envio_utc <= datetime.utcnow():
        return {
            "texto": f"La hora {hora_num}:{minuto:02d} ya pasó. Llamar ahora.",
            "programada": False,
            "hora": f"{hora_num}:{minuto:02d}",
            "ya_paso": True,
        }

    # Buscar datos del lead para el payload
    nombre_padre = ""
    nombre_hijo = ""
    try:
        from agent.airtable_client import _get_records, _LEADS
        lead_records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if lead_records:
            fields = lead_records[0].get("fields", {})
            nombre_padre = fields.get("NOMBRE RESPONSABLE", "")
            nombre_hijo = fields.get("NOMBRE NIÑO", "")
    except Exception:
        pass

    payload = json.dumps({
        "template": "llamada",
        "telefono_lead": telefono,
        "nombre_padre": nombre_padre,
        "nombre_hijo": nombre_hijo,
        "hora": hora_llamada,
    })
    rec_id = await crear_recordatorio(telefono, "llamada", envio_utc, payload)
    logger.info(f"[LLAMADA] Programada id={rec_id} para {telefono} a las {hora_num}:{minuto:02d} PY")

    return {
        "texto": f"Llamada programada para las {hora_num}:{minuto:02d}.",
        "programada": True,
        "hora": f"{hora_num}:{minuto:02d}",
    }
