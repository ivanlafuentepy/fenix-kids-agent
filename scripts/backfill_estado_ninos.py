# scripts/backfill_estado_ninos.py — Backfill de NIÑOS.ESTADO (migración FAMILIAS→NIÑO, paso 3)
#
# Copia el ESTADO PLAN de la FAMILIA de cada niño al campo nuevo NIÑOS.ESTADO
# (fldayrwUxsXRwru8O, creado 2026-07-13). Es ADITIVO: solo escribe el campo nuevo,
# nunca toca FAMILIAS. Idempotente: saltea niños que ya tienen ESTADO.
#
# Semántica (igual que familia_es_activa): familia con ESTADO PLAN vacío = cliente
# → el niño queda con ESTADO vacío también (el código trata vacío como "no A PRUEBA").
#
# Uso:
#   py -3 scripts/backfill_estado_ninos.py            # DRY-RUN (no escribe)
#   py -3 scripts/backfill_estado_ninos.py --escribir # escribe de verdad

import os
import sys
import json
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE = "appWwCQxALdMMV4MA"
URL = f"https://api.airtable.com/v0/{BASE}"
H = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

ESCRIBIR = "--escribir" in sys.argv


def _get_all(tabla: str, filtro: str = "") -> list[dict]:
    """Trae TODOS los registros paginando con offset (la API corta en 100)."""
    recs, offset = [], None
    while True:
        url = f"{URL}/{urllib.parse.quote(tabla)}?pageSize=100"
        if filtro:
            url += f"&filterByFormula={urllib.parse.quote(filtro)}"
        if offset:
            url += f"&offset={offset}"
        req = urllib.request.Request(url, headers=H)
        data = json.load(urllib.request.urlopen(req))
        recs += data.get("records", [])
        offset = data.get("offset")
        if not offset:
            return recs


def _patch(tabla: str, cambios: list[dict]) -> int:
    """PATCH en lotes de 10 (máximo de la API). Retorna cuántos escribió."""
    escritos = 0
    for i in range(0, len(cambios), 10):
        lote = cambios[i:i + 10]
        req = urllib.request.Request(
            f"{URL}/{urllib.parse.quote(tabla)}",
            data=json.dumps({"records": lote}).encode(),
            headers=H,
            method="PATCH",
        )
        try:
            urllib.request.urlopen(req)
            escritos += len(lote)
        except urllib.error.HTTPError as e:
            print(f"  ERROR {e.code} en lote {i}: {e.read().decode()[:200]}")
        time.sleep(0.25)  # rate limit de Airtable: 5 req/s compartido con Dorita
    return escritos


def main():
    print("Bajando datos…")
    ninos = _get_all("NIÑOS FENIX")
    familias = _get_all("FAMILIAS FENIX")
    print(f"  {len(ninos)} niños · {len(familias)} familias")

    estado_de_familia = {
        f["id"]: (f["fields"].get("ESTADO PLAN") or "").strip()
        for f in familias
    }

    cambios, stats = [], Counter()
    for n in ninos:
        f = n["fields"]
        etiqueta = f.get("NOMBRE COMPLETO") or n["id"]
        if f.get("ESTADO"):
            stats["ya tenían ESTADO"] += 1
            continue
        fams = f.get("FAMILIA") or []
        if not fams:
            stats["sin familia (queda vacío)"] += 1
            continue
        estado = estado_de_familia.get(fams[0], "")
        if not estado:
            stats["familia sin ESTADO PLAN (queda vacío)"] += 1
            continue
        cambios.append({"id": n["id"], "fields": {"ESTADO": estado}, "_etiqueta": etiqueta})
        stats[f"ESTADO={estado}"] += 1

    print(f"\n{'=' * 60}")
    print(f"NIÑOS a actualizar: {len(cambios)} de {len(ninos)}")
    for k, v in stats.most_common():
        print(f"   {v:4d}  {k}")
    print("=" * 60)

    if not ESCRIBIR:
        print("\nDRY-RUN — no se escribió nada. Correr con --escribir para aplicar.")
        print("\nEjemplos:")
        for c in cambios[:5]:
            print(f"   {c['_etiqueta']} -> {c['fields']['ESTADO']}")
        return

    # La API rechaza claves desconocidas en los records → sacar la etiqueta interna
    limpios = [{"id": c["id"], "fields": c["fields"]} for c in cambios]
    print("\nESCRIBIENDO…")
    ok = _patch("NIÑOS FENIX", limpios)
    print(f"  NIÑOS actualizados: {ok}/{len(limpios)}")
    print("\nListo. FAMILIAS quedó intacta (aditivo).")


if __name__ == "__main__":
    main()
