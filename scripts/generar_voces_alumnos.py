# scripts/generar_voces_alumnos.py — Voces del Guardián Fenix por alumno (Fase F SPEC-TOTEM)
"""
Genera los MP3 que la TV reproduce cuando un niño llega/completa vuelta/vence
dragón/halla tesoro. Voz George de ElevenLabs, pre-generados (costo ~cero en
runtime: se generan UNA vez por alumno y la TV solo reproduce archivos).

Uso:
    python scripts/generar_voces_alumnos.py --dry              # cuenta chars/costo, no gasta
    python scripts/generar_voces_alumnos.py --nombres "Mateo,Lola"   # subset
    python scripts/generar_voces_alumnos.py                    # todos los ACTIVOS

Requiere env ELEVENLABS_API_KEY (la tiene Iván — plan free: 10k chars/mes).
Salida: mundo-fenix/assets/voz/{escena}_{nombre}.mp3 (nombre normalizado:
minúsculas sin tildes — convención de tvVoz() en index.html).
"""

import argparse
import asyncio
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import httpx

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


async def alumnos_activos() -> list[str]:
    """Nombres de NIÑOS de familias ACTIVAS (no A PRUEBA) — para no quemar quota."""
    from agent.airtable_client import _get_records, _FAMILIAS, obtener_ninos_de_familia
    # misma definición que familia_es_activa: todo lo que NO esté A PRUEBA
    familias = await _get_records(_FAMILIAS, formula="NOT({ESTADO PLAN}='A PRUEBA')", max_records=300)
    nombres = []
    for fam in familias:
        for nino in await obtener_ninos_de_familia(fam["id"]):
            if nino.get("nombre"):
                nombres.append(nino["nombre"].strip())
    return sorted(set(nombres))


async def generar(nombre: str, escena: str, texto: str, key: str) -> bool:
    path = os.path.join(OUT_DIR, f"{escena}_{norm(nombre)}.mp3")
    if os.path.exists(path):
        print(f"  ya existe: {os.path.basename(path)}")
        return True
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={"text": texto, "model_id": MODEL, "voice_settings": SETTINGS},
            timeout=60,
        )
        if r.status_code != 200:
            print(f"  ERROR {escena}_{norm(nombre)}: {r.status_code} {r.text[:150]}")
            return False
        with open(path, "wb") as f:
            f.write(r.content)
        print(f"  ok: {os.path.basename(path)} ({len(r.content)//1024} KB)")
        return True


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nombres", help="subset separado por comas (ej: Mateo,Lola)")
    ap.add_argument("--dry", action="store_true", help="solo contar chars, no genera")
    args = ap.parse_args()

    if args.nombres:
        nombres = [n.strip() for n in args.nombres.split(",") if n.strip()]
    else:
        nombres = await alumnos_activos()
        print(f"Alumnos ACTIVOS encontrados: {len(nombres)}")

    total_chars = sum(len(g.format(n=n)) for n in nombres for g in GUIONES.values())
    print(f"{len(nombres)} alumnos × 4 escenas = {len(nombres)*4} MP3 · ~{total_chars:,} chars"
          f" (free tier: 10k/mes; Creator $5: 100k)")
    if args.dry:
        return

    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        print("FALTA env ELEVENLABS_API_KEY — cargala en .env y re-corré.")
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)
    for n in nombres:
        print(f"{n}:")
        for escena, guion in GUIONES.items():
            ok = await generar(n, escena, guion.format(n=n), key)
            if not ok:
                print("Corte por error (¿quota?) — lo generado queda, re-corré después.")
                return
            await asyncio.sleep(0.4)   # gentil con el rate limit


if __name__ == "__main__":
    asyncio.run(main())
