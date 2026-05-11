"""
FU GRUPO B — Envía 10 links wa.me a Lujan cada 10 minutos desde las 8:00am PY
Total: 467 links → 47 batches → termina ~15:50

Uso:
    python scripts/fu_grupo_b_lujan.py

Envía cada batch como un mensaje de WhatsApp a Lujan con 10 links listos para clickear.
"""

import json
import os
import sys
import asyncio
import httpx
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

LUJAN_PHONE = "595981189205"
IG_LINK = "https://www.instagram.com/p/DYB4KjQGuRO/?img_index=1"
MSG_TEMPLATE = f"Buen dia! Te saluda Lujan de Fenix Kids! Estamos por cerrar los cupos para este sabado, avisame si queres agendarle a tu hijo.\n\n{IG_LINK}"

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
PY_TZ = timezone(timedelta(hours=-3))

BATCH_SIZE = 10
INTERVALO_MIN = 10


def cargar_links():
    ruta = os.path.join(os.path.dirname(__file__), "..", "links_lujan.json")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def generar_batches(links):
    return [links[i:i+BATCH_SIZE] for i in range(0, len(links), BATCH_SIZE)]


def formatear_batch(batch: list, num_batch: int, total: int) -> str:
    """Formatea un batch de 10 links como mensaje para Lujan."""
    lineas = [f"📋 Batch {num_batch}/{total} — {len(batch)} contactos\n"]
    for i, lead in enumerate(batch, 1):
        nombre = (lead.get("nombre") or "").strip()
        hijo = (lead.get("hijo") or "").strip()
        label = f"{nombre}" if nombre else lead["tel"][-4:]
        if hijo:
            label += f" ({hijo})"
        lineas.append(f"{i}. {label}")
        lineas.append(lead["link"])
        lineas.append("")
    return "\n".join(lineas)


async def enviar_a_lujan(client: httpx.AsyncClient, texto: str) -> bool:
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": LUJAN_PHONE,
        "type": "text",
        "text": {"body": texto},
    }
    r = await client.post(url, json=payload, headers=headers, timeout=15)
    return r.status_code == 200


async def main():
    links = cargar_links()
    batches = generar_batches(links)
    total = len(batches)

    print(f"Total links: {len(links)}")
    print(f"Batches de {BATCH_SIZE}: {total}")
    print(f"Duración estimada: {total * INTERVALO_MIN} min ({total * INTERVALO_MIN // 60}h {total * INTERVALO_MIN % 60}min)")

    # Esperar hasta las 8:00am PY
    ahora = datetime.now(PY_TZ)
    target = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
    if ahora >= target:
        print("Ya pasó las 8am PY, enviando primer batch ahora...")
    else:
        espera = (target - ahora).total_seconds()
        print(f"Esperando hasta las 8:00am PY... ({espera:.0f}s = {espera/60:.1f} min)")
        await asyncio.sleep(espera)

    print(f"\nIniciando — {datetime.now(PY_TZ).strftime('%H:%M:%S')} PY")

    async with httpx.AsyncClient() as client:
        for i, batch in enumerate(batches, 1):
            texto = formatear_batch(batch, i, total)
            ahora_str = datetime.now(PY_TZ).strftime("%H:%M:%S")
            exito = await enviar_a_lujan(client, texto)
            status = "OK" if exito else "FAIL"
            print(f"  [{ahora_str}] Batch {i}/{total} — {status} ({len(batch)} links)")

            if i < total:
                # Esperar 10 minutos antes del próximo batch
                await asyncio.sleep(INTERVALO_MIN * 60)

    print(f"\n=== LISTO — {datetime.now(PY_TZ).strftime('%H:%M')} PY ===")
    print(f"Todos los batches enviados a Lujan ({LUJAN_PHONE})")


if __name__ == "__main__":
    asyncio.run(main())
