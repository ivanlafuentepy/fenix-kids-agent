# agent/transcriber.py — Transcripción de audios de WhatsApp con Groq Whisper
# FENIX KIDS ACADEMY

"""
Convierte mensajes de voz de WhatsApp en texto usando Groq Whisper.

Flujo:
  1. Meta envía un media_id en el webhook cuando el lead manda un audio.
  2. descargar_audio_whatsapp() obtiene la URL real del archivo y lo descarga.
  3. transcribir_audio() envía los bytes a Groq Whisper y devuelve el texto.

Variables de entorno requeridas:
  GROQ_API_KEY       — clave de la API de Groq
  META_ACCESS_TOKEN  — token de la Cloud API de Meta (para descargar el audio)
"""

import os
import logging
import httpx

logger = logging.getLogger("agentkit")

GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL   = "whisper-large-v3"
META_GRAPH_URL = "https://graph.facebook.com/v21.0"


async def descargar_audio_whatsapp(media_id: str) -> tuple[bytes, str] | tuple[None, None]:
    """
    Descarga el archivo de audio de WhatsApp a partir de su media_id.

    Meta Cloud API requiere dos pasos:
      1. GET /{media_id} → devuelve la URL real del archivo y el mime_type
      2. GET {url}       → descarga el archivo con el access token en el header

    Returns:
        (bytes del audio, mime_type) o (None, None) si falla.
    """
    # META_MEDIA_TOKEN: token de app suscrita al WABA (Dorita) para descargar media
    access_token = os.getenv("META_MEDIA_TOKEN", os.getenv("META_ACCESS_TOKEN"))
    if not access_token:
        logger.error("[Transcriber] META_ACCESS_TOKEN no configurado")
        return None, None

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30) as client:
        # Paso 1: obtener URL del archivo
        r = await client.get(f"{META_GRAPH_URL}/{media_id}", headers=headers)
        if r.status_code != 200:
            logger.error(f"[Transcriber] Error obteniendo URL de media {media_id}: {r.status_code} {r.text}")
            return None, None

        data      = r.json()
        url       = data.get("url")
        mime_type = data.get("mime_type", "audio/ogg")

        if not url:
            logger.error(f"[Transcriber] Respuesta sin 'url' para media_id={media_id}: {data}")
            return None, None

        # Paso 2: descargar el archivo
        r2 = await client.get(url, headers=headers)
        if r2.status_code != 200:
            logger.error(f"[Transcriber] Error descargando audio: {r2.status_code}")
            return None, None

        logger.info(f"[Transcriber] Audio descargado — {len(r2.content)} bytes, mime={mime_type}")
        return r2.content, mime_type


async def transcribir_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
    """
    Envía el audio a Groq Whisper y devuelve el texto transcripto.

    Args:
        audio_bytes: Bytes del archivo de audio descargado de WhatsApp.
        mime_type:   MIME type del archivo (ej: "audio/ogg; codecs=opus").

    Returns:
        Texto transcripto, o None si falla.
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        logger.error("[Transcriber] GROQ_API_KEY no configurada")
        return None

    # WhatsApp envía audios como OGG/Opus. Groq los acepta directamente.
    # El nombre del archivo le indica a Groq el formato.
    extension = _mime_to_extension(mime_type)
    filename  = f"audio.{extension}"

    headers = {"Authorization": f"Bearer {groq_api_key}"}
    files   = {"file": (filename, audio_bytes, mime_type)}
    data    = {"model": GROQ_MODEL, "language": "es"}

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(GROQ_API_URL, headers=headers, files=files, data=data)
        if r.status_code != 200:
            logger.error(f"[Transcriber] Error Groq Whisper: {r.status_code} — {r.text}")
            return None

        texto = r.json().get("text", "").strip()
        logger.info(f"[Transcriber] Transcripción: '{texto}'")
        return texto or None


async def detectar_y_traducir(texto: str) -> tuple[bool, str | None, str | None]:
    """
    Detecta si el texto está en español y, si no lo está, lo traduce.

    Returns:
        (es_espanol, traduccion_al_espanol_o_None, nombre_idioma_o_None)
        Ejemplo: (False, "Hola, quiero info", "inglés")
    """
    import json
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = (
        f"Analizá el siguiente texto y respondé en JSON estricto con tres campos:\n"
        f'- "es_espanol": true si el idioma es español, false si no\n'
        f'- "idioma": nombre del idioma en español (ej: "inglés", "portugués", "francés")\n'
        f'- "traduccion": traducción al español si no es español, null si ya es español\n\n'
        f"Respondé SOLO el JSON, sin texto adicional.\n\n"
        f"Texto: {texto}"
    )
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        data = json.loads(raw)
        es_espanol = data.get("es_espanol", True)
        idioma     = data.get("idioma") if not es_espanol else None
        traduccion = data.get("traduccion") if not es_espanol else None
        return es_espanol, traduccion, idioma
    except Exception as e:
        logger.warning(f"[Traduccion] Error detectando idioma: {e}")
        return True, None, None  # ante la duda, asumir español


def _mime_to_extension(mime_type: str) -> str:
    """Mapea mime_type al extension de archivo que Groq espera."""
    mime = mime_type.split(";")[0].strip().lower()
    mapping = {
        "audio/ogg":  "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4":  "mp4",
        "audio/wav":  "wav",
        "audio/webm": "webm",
        "audio/m4a":  "m4a",
    }
    return mapping.get(mime, "ogg")  # OGG es el formato por defecto de WhatsApp
