# scripts/generar_voces_alumnos.py — Voces del Guardián Fenix por alumno (Fase F SPEC-TOTEM)
"""
Genera los MP3 que la TV reproduce cuando un niño llega/completa vuelta/vence
dragón/halla tesoro. Voz George de ElevenLabs, pre-generados (costo ~cero en
runtime: se generan UNA vez por alumno y la TV solo reproduce archivos).

Desde que crear_nino() dispara la generación automática al inscribir un
alumno (agent/voces_alumnos.py), este script sirve para:
  - regenerar audios borrados/corruptos a mano
  - correr un barrido manual si algo quedó pendiente (ej. corte por quota)

Uso:
    python scripts/generar_voces_alumnos.py --dry              # cuenta chars/costo, no gasta
    python scripts/generar_voces_alumnos.py --nombres "Mateo,Lola"   # subset
    python scripts/generar_voces_alumnos.py                    # todos los ACTIVOS

Requiere env ELEVENLABS_API_KEY (la tiene Iván).
Salida: mundo-fenix/assets/voz/{escena}_{nombre}.mp3 (nombre normalizado:
minúsculas sin tildes — convención de tvVoz() en index.html).
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(message)s"))
_agentkit_logger = logging.getLogger("agentkit")
_agentkit_logger.setLevel(logging.INFO)
_agentkit_logger.addHandler(_handler)
_agentkit_logger.propagate = False

from agent.voces_alumnos import GUIONES, generar_audios_nino


async def alumnos_activos() -> list[str]:
    """Nombres de NIÑOS activos (no A PRUEBA) — para no quemar quota (niño-eje)."""
    from agent.airtable_client import _get_records, _NINOS
    ninos = await _get_records(_NINOS, formula="NOT({ESTADO}='A PRUEBA')", max_records=1000)
    nombres = []
    for n in ninos:
        nombre = (n.get("fields", {}) or {}).get("NOMBRE", "")
        if nombre.strip():
            nombres.append(nombre.strip())
    return sorted(set(nombres))


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

    if not os.getenv("ELEVENLABS_API_KEY", ""):
        print("FALTA env ELEVENLABS_API_KEY — cargala en .env y re-corré.")
        sys.exit(1)

    for n in nombres:
        print(f"{n}:")
        await generar_audios_nino(n)
        await asyncio.sleep(0.4)   # gentil con el rate limit


if __name__ == "__main__":
    asyncio.run(main())
