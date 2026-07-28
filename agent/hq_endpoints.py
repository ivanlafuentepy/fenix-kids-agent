# agent/hq_endpoints.py — Router /hq para el Centro de Comando (app maestra de Iván)
"""
Router AISLADO y ADITIVO para Fenix Kids. NO toca el webhook ni los handlers de Iván.

Expone acciones de ESCRITURA que el Centro de Comando necesita y que conviene hacer
desde el agente (dueño del provider de WhatsApp, de la ventana de 24h, del espejo a
Telegram y de la base de Airtable):

  POST /hq/enviar        {telefono, texto}                 → manda WhatsApp de texto
  POST /hq/enviar-media  (multipart: archivo, telefono, caption) → foto o video
  POST /hq/silencio      {telefono, accion}                → callar / reactivar al agente
  POST /hq/asistencia    {nino_id, presente, nombre?, familia_id?, telefono?}
                                                            → marca/desmarca presente hoy

La LECTURA de conversaciones y datos NO pasa por acá: el Centro de Comando lee directo
la DB (solo-lectura) y Airtable. Mantener este archivo chico y sin lógica de negocio.

Auth: header `X-HQ-Key` == env `HQ_API_KEY`. Si HQ_API_KEY no está seteada, el router
queda cerrado (fail-closed) y devuelve 503.
"""

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Header, HTTPException, Body, File, Form, UploadFile

from agent.providers import obtener_proveedor
from agent.memory import guardar_mensaje
from agent.telegram_bridge import (
    silenciar_dorita, reactivar_dorita, obtener_o_crear_topic, enviar_a_topic,
)
from agent.airtable_client import (
    crear_asistencia, borrar_asistencia, obtener_asistencias_ninos_fecha,
)

logger = logging.getLogger("agentkit")
router = APIRouter()

HQ_API_KEY = os.getenv("HQ_API_KEY", "")
_TZ = ZoneInfo("America/Asuncion")


def _auth(x_hq_key: str | None):
    if not HQ_API_KEY:
        raise HTTPException(status_code=503, detail="HQ no configurado")
    if not x_hq_key or x_hq_key != HQ_API_KEY:
        raise HTTPException(status_code=401, detail="no autorizado")


async def _espejar_telegram(telefono: str, texto: str):
    """Best-effort: refleja lo enviado en el topic de Telegram del contacto."""
    try:
        topic = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
        tid = topic.topic_id if hasattr(topic, "topic_id") else topic
        if tid:
            await enviar_a_topic(tid, f"👤 Iván (Comando): {texto}", telefono=telefono)
    except Exception as e:
        logger.warning(f"[HQ] espejo a Telegram falló para {telefono}: {e}")


@router.post("/hq/enviar")
async def hq_enviar(payload: dict = Body(...), x_hq_key: str | None = Header(default=None)):
    _auth(x_hq_key)
    telefono = str(payload.get("telefono", "")).strip()
    texto = str(payload.get("texto", "")).strip()
    if not telefono or not texto:
        raise HTTPException(status_code=422, detail="telefono y texto requeridos")

    proveedor = obtener_proveedor()
    ok = await proveedor.enviar_mensaje(telefono, texto)
    if not ok:
        raise HTTPException(status_code=502, detail="WhatsApp rechazó el envío (¿ventana 24h cerrada?)")

    await guardar_mensaje(telefono, "assistant", texto)
    await silenciar_dorita(telefono)
    await _espejar_telegram(telefono, texto)
    return {"ok": True, "telefono": telefono}


@router.post("/hq/enviar-media")
async def hq_enviar_media(
    archivo: UploadFile = File(...),
    telefono: str = Form(...),
    caption: str = Form(""),
    x_hq_key: str | None = Header(default=None),
):
    """Reenvía una foto o video al contacto. El provider de Fenix solo soporta imagen/video."""
    _auth(x_hq_key)
    telefono = telefono.strip()
    caption = (caption or "").strip()
    if not telefono:
        raise HTTPException(status_code=422, detail="telefono requerido")

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=422, detail="archivo vacío")
    mime = (archivo.content_type or "application/octet-stream").split(";")[0].strip()

    proveedor = obtener_proveedor()
    if mime.startswith("image/"):
        ok = await proveedor.enviar_imagen_bytes(telefono, contenido, mime, caption=caption)
        marcador = "[imagen]"
    elif mime.startswith("video/"):
        ok = await proveedor.enviar_video_bytes(telefono, contenido, mime, caption=caption)
        marcador = "[video]"
    else:
        raise HTTPException(status_code=415, detail="solo se soportan imágenes y videos")

    if not ok:
        raise HTTPException(status_code=502, detail="WhatsApp rechazó el envío (¿ventana 24h cerrada?)")

    texto_hist = f"{marcador} {caption}".strip()
    await guardar_mensaje(telefono, "assistant", texto_hist)
    await silenciar_dorita(telefono)
    await _espejar_telegram(telefono, texto_hist)
    return {"ok": True, "telefono": telefono, "tipo": marcador}


@router.post("/hq/silencio")
async def hq_silencio(payload: dict = Body(...), x_hq_key: str | None = Header(default=None)):
    _auth(x_hq_key)
    telefono = str(payload.get("telefono", "")).strip()
    accion = str(payload.get("accion", "")).strip()
    if not telefono:
        raise HTTPException(status_code=422, detail="telefono requerido")
    if accion == "silenciar":
        await silenciar_dorita(telefono)
    elif accion == "activar":
        await reactivar_dorita(telefono)
    else:
        raise HTTPException(status_code=422, detail="accion debe ser silenciar|activar")
    return {"ok": True, "telefono": telefono, "accion": accion}


@router.post("/hq/asistencia")
async def hq_asistencia(payload: dict = Body(...), x_hq_key: str | None = Header(default=None)):
    """Marca (presente=True) o desmarca (presente=False) a un niño como presente HOY.

    Escribe en ASISTENCIA FENIX. Idempotente: si ya está marcado, no duplica; si se
    desmarca, borra la fila de hoy.
    """
    _auth(x_hq_key)
    nino_id = str(payload.get("nino_id", "")).strip()
    presente = bool(payload.get("presente", True))
    if not nino_id:
        raise HTTPException(status_code=422, detail="nino_id requerido")

    ahora = datetime.now(_TZ)
    fecha_iso = ahora.date().isoformat()

    existentes = await obtener_asistencias_ninos_fecha([nino_id], fecha_iso)
    ya = existentes.get(nino_id)

    if presente:
        if ya:
            return {"ok": True, "presente": True, "asistencia_id": ya}
        rec_id = await crear_asistencia(
            nombre=str(payload.get("nombre", "")).strip(),
            fecha_iso=fecha_iso,
            hora_checkin_iso=ahora.isoformat(),
            nino_id=nino_id,
            telefono=str(payload.get("telefono", "")).strip(),
            # metodo por defecto "QR" (opción válida del singleSelect; el campo no
            # tiene otras opciones y _post no usa typecast)
        )
        if not rec_id:
            raise HTTPException(status_code=502, detail="no se pudo crear la asistencia")
        # Descontar la clase del pack (idempotente por día; None = mensual viejo).
        # Best-effort: marcar presente nunca falla por el saldo.
        saldo = None
        try:
            from agent.airtable_client import descontar_clase
            _r_pack = await descontar_clase(nino_id, fecha_iso)
            saldo = _r_pack[0] if _r_pack else None
        except Exception as e:
            logger.warning(f"[HQ] descuento de clase falló para {nino_id}: {e}")
        return {"ok": True, "presente": True, "asistencia_id": rec_id, "clases_restantes": saldo}
    else:
        if ya:
            await borrar_asistencia(ya)
        return {"ok": True, "presente": False}
