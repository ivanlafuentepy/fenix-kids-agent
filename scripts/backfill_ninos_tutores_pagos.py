# scripts/backfill_ninos_tutores_pagos.py — Backfill M2 de la migración FAMILIAS→NIÑO
#
# Llena los campos NUEVOS a partir de los datos actuales. Es ADITIVO: solo escribe
# en campos nuevos y NUNCA toca los viejos (FAMILIA, FAMILIA FENIX siguen intactos).
#
#   NIÑOS.PADRE / NIÑOS.MADRE  <- el tutor de su familia con PARENTESCO Papá / Mamá
#   PAGOS.NIÑOS FENIX          <- los niños de la familia del pago (los 2-3 hermanos)
#   PAGOS.PAGA                 <- el tutor de la familia (ES QUIEN PAGA, o el único)
#
# Uso:
#   py -3 scripts/backfill_ninos_tutores_pagos.py            # DRY-RUN (no escribe)
#   py -3 scripts/backfill_ninos_tutores_pagos.py --escribir # escribe de verdad

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
    tutores = _get_all("TUTORES FENIX")
    # Un pago es "de FENIX" si está linkeado a una FAMILIA FENIX — NO por FUENTE:
    # hay pagos de familias de Fenix cargados con FUENTE='SALSA SOUL STUDIO'
    # (ej. FAMILIA Molinas Silva, concepto F.SUSCRIPCION). Filtrar por FUENTE
    # los dejaba afuera y esos niños quedaban sin VENCE EL.
    pagos = _get_all("PAGOS", "{FAMILIA FENIX}!=''")
    print(f"  {len(ninos)} niños · {len(tutores)} tutores · {len(pagos)} pagos con FAMILIA FENIX")

    # Índices: familia_id -> tutores / niños
    tutores_de_familia: dict[str, list[dict]] = {}
    for t in tutores:
        for fam in t["fields"].get("FAMILIA") or []:
            tutores_de_familia.setdefault(fam, []).append(t)

    ninos_de_familia: dict[str, list[dict]] = {}
    for n in ninos:
        for fam in n["fields"].get("FAMILIA") or []:
            ninos_de_familia.setdefault(fam, []).append(n)

    def _parentesco(t: dict) -> str:
        return (t["fields"].get("PARENTESCO") or "").strip().lower()

    # ── 1. NIÑOS: PADRE / MADRE ────────────────────────────────────────────
    cambios_ninos, stats_n = [], Counter()
    for n in ninos:
        f = n["fields"]
        if f.get("PADRE") or f.get("MADRE"):
            stats_n["ya tenían"] += 1
            continue
        fams = f.get("FAMILIA") or []
        if not fams:
            stats_n["sin familia (no se puede)"] += 1
            continue
        de_la_flia = tutores_de_familia.get(fams[0], [])
        padre = next((t for t in de_la_flia if _parentesco(t) == "papá"), None)
        madre = next((t for t in de_la_flia if _parentesco(t) == "mamá"), None)
        campos = {}
        if padre:
            campos["PADRE"] = [padre["id"]]
        if madre:
            campos["MADRE"] = [madre["id"]]
        if not campos:
            stats_n["familia sin tutores Papá/Mamá"] += 1
            continue
        cambios_ninos.append({"id": n["id"], "fields": campos})
        stats_n["con padre Y madre" if (padre and madre) else "solo uno de los dos"] += 1

    # ── 2. PAGOS: NIÑOS FENIX + PAGA ───────────────────────────────────────
    cambios_pagos, stats_p = [], Counter()
    for p in pagos:
        f = p["fields"]
        if f.get("NIÑOS FENIX") or f.get("PAGA"):
            stats_p["ya tenían"] += 1
            continue
        fams = f.get("FAMILIA FENIX") or []
        if not fams:
            stats_p["sin FAMILIA FENIX (queda igual)"] += 1
            continue
        fam = fams[0]
        hijos = ninos_de_familia.get(fam, [])
        de_la_flia = tutores_de_familia.get(fam, [])
        # quién paga: el marcado ES QUIEN PAGA; si no, el único tutor; si hay 2 sin marca, ninguno
        quien = next((t for t in de_la_flia if t["fields"].get("ES QUIEN PAGA")), None)
        if not quien and len(de_la_flia) == 1:
            quien = de_la_flia[0]

        campos = {}
        if hijos:
            campos["NIÑOS FENIX"] = [h["id"] for h in hijos]
        if quien:
            campos["PAGA"] = [quien["id"]]
        if not campos:
            stats_p["familia sin niños ni tutores"] += 1
            continue
        cambios_pagos.append({"id": p["id"], "fields": campos})
        stats_p[f"{len(hijos)} niño(s)" + (" + pagador" if quien else " (sin pagador claro)")] += 1

    # ── Reporte ────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"NIÑOS a actualizar: {len(cambios_ninos)} de {len(ninos)}")
    for k, v in stats_n.most_common():
        print(f"   {v:4d}  {k}")
    print(f"\nPAGOS a actualizar: {len(cambios_pagos)} de {len(pagos)}")
    for k, v in stats_p.most_common():
        print(f"   {v:4d}  {k}")
    print("=" * 60)

    if not ESCRIBIR:
        print("\nDRY-RUN — no se escribió nada. Correr con --escribir para aplicar.")
        # muestra 3 ejemplos de cada uno
        for titulo, cambios, tabla in (("NIÑOS", cambios_ninos, ninos), ("PAGOS", cambios_pagos, pagos)):
            print(f"\nEjemplos {titulo}:")
            por_id = {r["id"]: r for r in tabla}
            for c in cambios[:3]:
                orig = por_id[c["id"]]["fields"]
                etiqueta = orig.get("NOMBRE COMPLETO") or orig.get("NOMBRE PAGO") or c["id"]
                print(f"   {etiqueta} -> { {k: len(v) for k, v in c['fields'].items()} }")
        return

    print("\nESCRIBIENDO…")
    n_ok = _patch("NIÑOS FENIX", cambios_ninos)
    print(f"  NIÑOS actualizados: {n_ok}/{len(cambios_ninos)}")
    p_ok = _patch("PAGOS", cambios_pagos)
    print(f"  PAGOS actualizados: {p_ok}/{len(cambios_pagos)}")
    print("\nListo. Los campos VIEJOS (FAMILIA / FAMILIA FENIX) quedaron intactos.")


if __name__ == "__main__":
    main()
