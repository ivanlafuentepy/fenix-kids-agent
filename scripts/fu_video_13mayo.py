"""
FU Video — 13 de mayo 2026
Envía video followup a leads CONSULTA/CONTACTADO de las últimas 24h.
Pre-flight: test al admin antes del masivo.
"""

import os
import sys
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fu-video-13mayo")

# Config — usar token de producción
META_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = "1005063086033214"
ADMIN_PHONE = "595982790407"
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}"
VIDEO_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "followup_video.mp4")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appWwCQxALdMMV4MA")

TEXTO_FU = "Regalale a tu hijo un sábado que recordará por el resto de su vida. Quedan pocos lugares disponibles."


async def subir_video(client: httpx.AsyncClient, video_bytes: bytes) -> str | None:
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


async def obtener_leads_ventana_abierta() -> list[str]:
    """Consulta Airtable por leads CONSULTA/CONTACTADO creados en últimas 24h."""
    formula = quote('AND(IS_AFTER(CREATED_TIME(), DATEADD(NOW(), -24, "hours")), OR({CONVERSION}="CONSULTA", {CONVERSION}="CONTACTADO"))')
    telefonos = []
    offset = None

    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params = f"filterByFormula={formula}&fields%5B%5D=TELEFONO&pageSize=100"
            if offset:
                params += f"&offset={offset}"
            url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/LEADS%20FENIX?{params}"
            r = await client.get(url, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}"})
            data = r.json()
            for rec in data.get("records", []):
                tel = rec.get("fields", {}).get("TELEFONO", "")
                if tel and tel != ADMIN_PHONE:
                    telefonos.append(tel)
            offset = data.get("offset")
            if not offset:
                break

    return telefonos


async def main():
    logger.info("=== FU VIDEO 13 MAYO — INICIO ===")

    # Verificar token
    expected_prefix = "EAAORCCzn"
    if not META_TOKEN or not META_TOKEN.startswith(expected_prefix):
        logger.error(f"TOKEN INCORRECTO — empieza con {META_TOKEN[:10] if META_TOKEN else 'VACIO'}... esperado {expected_prefix}")
        return

    # Leer video
    if not os.path.exists(VIDEO_PATH):
        logger.error(f"Video no encontrado: {VIDEO_PATH}")
        return
    with open(VIDEO_PATH, "rb") as f:
        video_bytes = f.read()
    logger.info(f"Video leído: {len(video_bytes) / 1024 / 1024:.1f} MB")

    # Obtener leads
    telefonos = await obtener_leads_ventana_abierta()
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

        # Pausa para que Ivan vea el test
        logger.info("Esperando 10s para que Ivan verifique el test...")
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

                await asyncio.sleep(3)

            except Exception as e:
                fallidos += 1
                logger.error(f"ERROR {telefono}: {e}")

    logger.info(f"=== FU VIDEO 13 MAYO — FIN ===")
    logger.info(f"Enviados: {enviados}/{len(telefonos)} | Fallidos: {fallidos}")


if __name__ == "__main__":
    asyncio.run(main())
