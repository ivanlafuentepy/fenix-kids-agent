"""
FU Video — 8 de mayo 2026 — 6:00 AM PY
Envía video followup a todos los leads con ventana 24h abierta.
Pre-flight: envía 1 test al admin antes del loop masivo.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fu-video")

_TZ_PY = ZoneInfo("America/Asuncion")

# Config
META_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "1005063086033214")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "595982790407")
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}"
VIDEO_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "followup_video.mp4")

# Ventana: leads que escribieron en las últimas 24h
# 6am PY del 8 mayo = 9am UTC del 8 mayo → corte = 9am UTC del 7 mayo
CORTE_VENTANA = datetime(2026, 5, 7, 9, 0, 0, tzinfo=timezone.utc)

TEXTO_FU = "Regalale a tu hijo un sábado que recordará por el resto de su vida. Quedan pocos lugares disponibles."


async def subir_video(client: httpx.AsyncClient, video_bytes: bytes) -> str | None:
    """Sube video a Meta y retorna media_id."""
    url = f"{BASE_URL}/media"
    headers = {"Authorization": f"Bearer {META_TOKEN}"}
    files = {"file": ("followup.mp4", video_bytes, "video/mp4")}
    data = {"messaging_product": "whatsapp", "type": "video/mp4"}
    r = await client.post(url, headers=headers, files=files, data=data, timeout=60)
    if r.status_code == 200:
        mid = r.json().get("id")
        logger.info(f"Video subido OK: media_id={mid}")
        return mid
    logger.error(f"Error subiendo video: {r.status_code} — {r.text}")
    return None


async def enviar_video(client: httpx.AsyncClient, telefono: str, media_id: str) -> bool:
    """Envía video por media_id."""
    url = f"{BASE_URL}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "video",
        "video": {"id": media_id},
    }
    r = await client.post(url, json=payload, headers=headers, timeout=30)
    return r.status_code == 200


async def enviar_texto(client: httpx.AsyncClient, telefono: str, texto: str) -> bool:
    """Envía mensaje de texto."""
    url = f"{BASE_URL}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": texto},
    }
    r = await client.post(url, json=payload, headers=headers, timeout=30)
    return r.status_code == 200


async def obtener_ventana_abierta() -> set[str]:
    """Consulta PostgreSQL por leads con mensajes recientes (ventana 24h)."""
    from agent.memory import async_session, Mensaje
    from sqlalchemy import select as sa_select

    telefonos = set()
    async with async_session() as session:
        query = (
            sa_select(Mensaje.telefono)
            .where(Mensaje.role == "user")
            .where(Mensaje.timestamp > CORTE_VENTANA.replace(tzinfo=None))
            .distinct()
        )
        result = await session.execute(query)
        telefonos = {row[0] for row in result.all()}

    # Excluir admin
    telefonos.discard(ADMIN_PHONE)
    return telefonos


async def main():
    ahora = datetime.now(_TZ_PY)
    logger.info(f"Hora actual PY: {ahora.strftime('%H:%M:%S')}")

    # Esperar hasta 6:00 AM PY
    target = datetime(2026, 5, 8, 6, 0, 0, tzinfo=_TZ_PY)
    if ahora < target:
        delay = (target - ahora).total_seconds()
        logger.info(f"Esperando {delay:.0f}s ({delay/3600:.1f}h) hasta 6:00 AM PY...")
        await asyncio.sleep(delay)
    elif (ahora - target).total_seconds() > 7200:
        logger.error("Ya pasaron más de 2h desde las 6am. Abortando.")
        return

    logger.info("=== FU VIDEO 8 MAYO — INICIO ===")

    # Leer video
    if not os.path.exists(VIDEO_PATH):
        logger.error(f"Video no encontrado: {VIDEO_PATH}")
        return
    with open(VIDEO_PATH, "rb") as f:
        video_bytes = f.read()
    logger.info(f"Video leído: {len(video_bytes) / 1024 / 1024:.1f} MB")

    # Obtener leads con ventana abierta
    telefonos = await obtener_ventana_abierta()
    if not telefonos:
        logger.info("No hay leads con ventana abierta. Nada que enviar.")
        return
    logger.info(f"Leads con ventana abierta: {len(telefonos)}")

    async with httpx.AsyncClient() as client:
        # Subir video una sola vez
        media_id = await subir_video(client, video_bytes)
        if not media_id:
            logger.error("No se pudo subir el video. Abortando.")
            return

        # ══ PRE-FLIGHT: test al admin ══
        logger.info(f"Pre-flight: enviando test al admin ({ADMIN_PHONE})...")
        ok_vid = await enviar_video(client, ADMIN_PHONE, media_id)
        await asyncio.sleep(2)
        ok_txt = await enviar_texto(client, ADMIN_PHONE, f"[TEST FU VIDEO] {TEXTO_FU}")
        if not ok_vid or not ok_txt:
            logger.error("PRE-FLIGHT FALLIDO. No se envía a nadie más. Revisá el token.")
            return
        logger.info("Pre-flight OK — admin recibió video + texto")

        # Pausa 10s para que Ivan vea el test
        await asyncio.sleep(10)

        # ══ ENVÍO MASIVO ══
        enviados = 0
        fallidos = 0
        for telefono in telefonos:
            try:
                ok1 = await enviar_video(client, telefono, media_id)
                await asyncio.sleep(2)
                ok2 = await enviar_texto(client, telefono, TEXTO_FU)

                if ok1 and ok2:
                    enviados += 1
                    logger.info(f"OK {telefono} ({enviados}/{len(telefonos)})")
                else:
                    fallidos += 1
                    logger.warning(f"FAIL {telefono} — video:{ok1} texto:{ok2}")

                await asyncio.sleep(3)  # Rate limiting

            except Exception as e:
                fallidos += 1
                logger.error(f"ERROR {telefono}: {e}")

    logger.info(f"=== FU VIDEO 8 MAYO — FIN ===")
    logger.info(f"Enviados: {enviados}/{len(telefonos)} | Fallidos: {fallidos}")


if __name__ == "__main__":
    asyncio.run(main())
