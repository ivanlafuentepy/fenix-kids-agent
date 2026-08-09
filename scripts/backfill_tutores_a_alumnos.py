# scripts/backfill_tutores_a_alumnos.py — Copia CODIGO y FACTURA de TUTORES FENIX
# a la fila de ALUMNOS que corresponde (match por teléfono), y espeja el link
# FACTURAS.TUTOR → FACTURAS.TUTOR (ALUMNOS). One-off de la migración Etapa 2
# (adiós TUTORES FENIX, 09/08/2026). Solo escribe campos NUEVOS y vacíos.
#
# Uso:  py -3 scripts/backfill_tutores_a_alumnos.py           (dry-run, no escribe)
#       py -3 scripts/backfill_tutores_a_alumnos.py --ejecutar

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from agent.airtable_client import _get_records, _patch, _ALUMNOS, _TUTORES  # noqa: E402

EJECUTAR = "--ejecutar" in sys.argv
FACTURAS = "FACTURAS"


def _limpio(tel: str) -> str:
    t = "".join(c for c in str(tel or "") if c.isdigit())
    if t.startswith("0"):
        t = "595" + t[1:]
    return t


async def main():
    print(f"{'EJECUTANDO' if EJECUTAR else 'DRY-RUN (no escribe)'}\n")

    tutores = await _get_records(_TUTORES, max_records=2000)
    alumnos = await _get_records(_ALUMNOS, formula="OR({TELEFONO LIMPIO}!='',{TELEFONO2 LIMPIO}!='')", max_records=5000)

    # Índice teléfono → fila de ALUMNOS (los dos números)
    por_tel: dict[str, dict] = {}
    for a in alumnos:
        f = a.get("fields", {})
        for k in ("TELEFONO LIMPIO", "TELEFONO2 LIMPIO"):
            t = str(f.get(k) or "").strip()
            if t and t not in por_tel:
                por_tel[t] = a

    # Índice record_id de TUTORES → fila (para el espejo de FACTURAS)
    tutor_por_id = {t["id"]: t for t in tutores}

    # ── 1) CODIGO y FACTURA de TUTORES → ALUMNOS ──────────────────────────
    sin_match, copiados, conflictos = [], 0, []
    mapa_tutor_alumno: dict[str, str] = {}
    for t in tutores:
        tf = t.get("fields", {})
        codigo = str(tf.get("CODIGO") or "").strip()
        factura = str(tf.get("FACTURA") or "").strip()
        cell = _limpio(tf.get("CELL LIMPIO") or tf.get("CELL") or "")
        al = por_tel.get(cell) if cell else None
        if al:
            mapa_tutor_alumno[t["id"]] = al["id"]
        if not codigo and not factura:
            continue
        nombre = f"{tf.get('NOMBRE','')} {tf.get('APELLIDO','')}".strip()
        if not al:
            sin_match.append(f"  SIN MATCH: {nombre} (CELL {cell or '?'}) codigo={codigo or '-'} factura={factura or '-'}")
            continue
        af = al.get("fields", {})
        upd = {}
        if codigo:
            existente = str(af.get("CODIGO FENIX") or "").strip()
            if not existente:
                upd["CODIGO FENIX"] = codigo
            elif existente != codigo:
                conflictos.append(f"  CONFLICTO CODIGO: {nombre} ALUMNOS={existente} TUTORES={codigo}")
        if factura:
            existente = str(af.get("FACTURA FENIX") or "").strip()
            if not existente:
                upd["FACTURA FENIX"] = factura
            elif existente != factura:
                conflictos.append(f"  CONFLICTO FACTURA: {nombre} ALUMNOS={existente!r} TUTORES={factura!r}")
        if upd:
            print(f"  {nombre} ({cell}) → {upd}")
            if EJECUTAR:
                ok = await _patch(_ALUMNOS, al["id"], upd)
                if not ok:
                    print(f"    ⚠️ PATCH FALLÓ para {al['id']}")
                    continue
            copiados += 1

    print(f"\nCODIGO/FACTURA: {copiados} filas {'copiadas' if EJECUTAR else 'a copiar'}")
    for linea in sin_match:
        print(linea)
    for linea in conflictos:
        print(linea)

    # ── 2) FACTURAS.TUTOR → TUTOR (ALUMNOS) (espejo del link legacy) ─────
    facturas = await _get_records(FACTURAS, formula="AND({TUTOR}!='',{TUTOR (ALUMNOS)}='')", max_records=2000)
    espejadas, huerfanas = 0, []
    for fac in facturas:
        ff = fac.get("fields", {})
        tids = ff.get("TUTOR") or []
        tid = tids[0] if tids else ""
        aid = mapa_tutor_alumno.get(tid, "")
        if not aid:
            trec = tutor_por_id.get(tid, {})
            tnom = f"{trec.get('fields',{}).get('NOMBRE','?')} {trec.get('fields',{}).get('APELLIDO','')}".strip()
            huerfanas.append(f"  FACTURA {fac['id']} (nro {ff.get('NUMERO','?')}): tutor {tnom} sin fila ALUMNOS")
            continue
        print(f"  FACTURA nro {ff.get('NUMERO','?')} → TUTOR (ALUMNOS)={aid}")
        if EJECUTAR:
            ok = await _patch(FACTURAS, fac["id"], {"TUTOR (ALUMNOS)": [aid]})
            if not ok:
                print(f"    ⚠️ PATCH FALLÓ para {fac['id']}")
                continue
        espejadas += 1

    print(f"\nFACTURAS: {espejadas} {'espejadas' if EJECUTAR else 'a espejar'}")
    for linea in huerfanas:
        print(linea)


asyncio.run(main())
