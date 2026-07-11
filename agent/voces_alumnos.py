# agent/voces_alumnos.py — Voces del Guardián Fenix por alumno (ElevenLabs)
"""
Genera los MP3 que la TV del tótem reproduce cuando un niño llega/completa
vuelta/vence dragón/halla tesoro. Voz George de ElevenLabs, pre-generados
(costo ~cero en runtime: se generan UNA vez por alumno y la TV solo reproduce
archivos).

Fuente única de guiones/config — usada por:
  - agent/airtable_client.py (crear_nino): dispara la generación al crear el alumno
  - scripts/generar_voces_alumnos.py: generación batch manual
"""

import os
import unicodedata
import logging

import httpx

logger = logging.getLogger("agentkit")

VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"          # George
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.4}
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "mundo-fenix", "assets", "voz")

# Guiones por escena (SPEC-TOTEM 4E) — {n} = nombre del niño
GUIONES = {
    "llegada": "¡{n} llegó a La Casona! El Guardián Fenix te da la bienvenida, campeón. Ganaste diez monedas de oro… ¡que comience la aventura!",
    "vuelta":  "¡Increíble, {n}! Vuelta completada… el cofre del tesoro está cada vez más cerca. ¡Seguí así, Guardián!",
    "dragon":  "¡{n} venció al dragón! La Casona respira tranquila gracias a vos. Ganaste una nueva insignia… ¡sos una leyenda!",
    "tesoro":  "¡{n} encontró el cofre del Capitán! Trescientas monedas de plata para el héroe del día. ¡La Casona entera te aplaude!",
}


def norm(nombre: str) -> str:
    """mateo, lola… minúsculas sin tildes (convención tvVoz de index.html)."""
    s = unicodedata.normalize("NFD", nombre.strip().lower())
    return "".join(c for c in s if c.isalnum())


async def _generar_mp3(nombre: str, escena: str, texto: str, key: str) -> bool:
    nombre_archivo = f"{escena}_{norm(nombre)}.mp3"
    path = os.path.join(OUT_DIR, nombre_archivo)
    if os.path.exists(path):
        logger.info(f"[VOZ-ALUMNO] ya existe: {nombre_archivo}")
        return True
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={"text": texto, "model_id": MODEL, "voice_settings": SETTINGS},
            timeout=60,
        )
        if r.status_code != 200:
            logger.error(f"[VOZ-ALUMNO] ERROR {nombre_archivo}: {r.status_code} {r.text[:150]}")
            return False
        with open(path, "wb") as f:
            f.write(r.content)
        logger.info(f"[VOZ-ALUMNO] ok: {nombre_archivo} ({len(r.content)//1024} KB)")
        return True


async def generar_audios_nino(nombre: str) -> None:
    """Genera los 4 MP3 (llegada/vuelta/dragon/tesoro) de un alumno nuevo.

    Pensado para correr en background (fire-and-forget) al crear el NIÑO en
    Airtable — no debe bloquear ni tumbar el flujo de inscripción si falla.
    """
    if not nombre or not nombre.strip():
        return
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        logger.warning(f"[VOZ-ALUMNO] Falta ELEVENLABS_API_KEY — no se generó audio de {nombre}")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    for escena, guion in GUIONES.items():
        ok = await _generar_mp3(nombre, escena, guion.format(n=nombre), key)
        if not ok:
            logger.error(f"[VOZ-ALUMNO] Corte por error generando audios de {nombre} (¿quota?)")
            return
    logger.info(f"[VOZ-ALUMNO] Audios generados para {nombre}")
