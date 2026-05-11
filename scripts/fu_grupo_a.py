"""
FU GRUPO A — Envío directo de FENIX a leads con ventana abierta (139 leads)
Ejecutar a las 6am PY del jueves 7 de mayo.

Uso:
    python scripts/fu_grupo_a.py

Espera hasta las 6:00am PY y luego envía a todos los leads con ventana abierta.
"""

import json
import os
import sys
import time
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

IG_LINK = "https://www.instagram.com/p/DYB4KjQGuRO/?img_index=1"
MENSAJE = f"Feliz jueves! El sabado se acerca! Ya tenes tu lugar en Fenix?\n\n{IG_LINK}"

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
PY_TZ = timezone(timedelta(hours=-3))


def cargar_leads():
    ruta = os.path.join(os.path.dirname(__file__), "..", "ventana_abierta.json")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


async def enviar_mensaje(client: httpx.AsyncClient, telefono: str) -> bool:
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "text",
        "text": {"body": MENSAJE},
    }
    r = await client.post(url, json=payload, headers=headers, timeout=15)
    return r.status_code == 200


async def main():
    leads = cargar_leads()
    print(f"Leads cargados: {len(leads)}")
    print(f"Mensaje:\n{MENSAJE}\n")

    # Esperar hasta las 6:00am PY
    ahora = datetime.now(PY_TZ)
    target = ahora.replace(hour=6, minute=0, second=0, microsecond=0)
    if ahora >= target:
        print("Ya pasó las 6am PY, enviando ahora...")
    else:
        espera = (target - ahora).total_seconds()
        print(f"Esperando hasta las 6:00am PY... ({espera:.0f}s = {espera/60:.1f} min)")
        await asyncio.sleep(espera)

    print(f"\nIniciando envío — {datetime.now(PY_TZ).strftime('%H:%M:%S')} PY")
    print(f"Total: {len(leads)} mensajes\n")

    ok = 0
    fail = 0
    async with httpx.AsyncClient() as client:
        for i, lead in enumerate(leads):
            tel = lead["tel"]
            nombre = lead.get("nombre", "") or lead.get("hijo", "") or tel[-4:]
            exito = await enviar_mensaje(client, tel)
            if exito:
                ok += 1
                print(f"  [{i+1}/{len(leads)}] OK — {tel} ({nombre})")
            else:
                fail += 1
                # Obtener error de Meta para diagnóstico
                try:
                    err = r.json().get("error", {})
                    print(f"  [{i+1}/{len(leads)}] FAIL — {tel} | {r.status_code} {err.get('code')} {err.get('message','')[:80]}")
                except Exception:
                    print(f"  [{i+1}/{len(leads)}] FAIL — {tel} | HTTP {r.status_code}")
            await asyncio.sleep(1)  # pausa 1s entre mensajes

    print(f"\n=== LISTO ===")
    print(f"OK: {ok} | FAIL: {fail}")


if __name__ == "__main__":
    asyncio.run(main())
