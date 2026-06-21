"""
B1 (migración) — Migra los campos PADRE/MADRE embebidos en FAMILIAS FENIX a
registros propios en la tabla nueva TUTORES FENIX (un registro por persona).

Qué hace:
  - Por cada FAMILIA, crea un TUTOR Papá (de NOMBRE PADRE...) y/o un TUTOR Mamá
    (de NOMBRE MADRE...), copiando NOMBRE, APELLIDO, APODO, CI, CELL, EMAIL,
    FECHA NACIMIENTO y linkeando a la FAMILIA.
  - ES QUIEN PAGA: marca al tutor cuyo CELL (normalizado) coincide con el TELEFONO
    de alguna PRUEBA FENIX con pago (MONTO>0 o PAGOS) de esa familia — es decir,
    el que hizo/pagó la prueba. Si ninguno matchea, queda sin marcar (revisar a mano).

Qué NO hace (por decisión):
  - NO toca los campos PADRE/MADRE de FAMILIAS (se mantienen hasta el corte B3).
  - NO borra ni modifica PRUEBA ni PAGOS.

Idempotente: clave (familia_id, parentesco). Si la familia ya tiene un TUTOR con
ese parentesco, no lo vuelve a crear.

Uso:
    python scripts/migrar_tutores.py            # DRY-RUN (no escribe nada)
    python scripts/migrar_tutores.py --ejecutar # escribe en Airtable
"""

import asyncio
import sys
import os
import json
import re
from datetime import datetime

import httpx
from agent.airtable_client import _post, _FAMILIAS, _PRUEBAS, _BASE_URL, _headers

DRY = "--ejecutar" not in sys.argv
_TUTORES = "TUTORES FENIX"


async def _get_all(table: str) -> list[dict]:
    """Lee TODOS los registros de una tabla con paginación completa.
    OJO: airtable_client._get_records NO pagina (trae solo la 1ª página de 100);
    para idempotencia y conteos hay que paginar o se generan duplicados.
    """
    recs, offset = [], None
    async with httpx.AsyncClient(timeout=20) as c:
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            r = await c.get(f"{_BASE_URL}/{table}", params=params, headers=_headers())
            if r.status_code != 200:
                print(f"  ⚠️ GET {table} → {r.status_code}: {r.text[:150]}")
                break
            j = r.json()
            recs += j.get("records", [])
            offset = j.get("offset")
            if not offset:
                break
    return recs


def _norm_tel(v) -> str:
    """Normaliza un teléfono igual que la fórmula CELL LIMPIO (solo dígitos, 0→595)."""
    if isinstance(v, list):
        v = v[0] if v else ""
    s = re.sub(r"[^0-9]", "", str(v or "").strip())
    if s.startswith("0"):
        s = "595" + s[1:]
    return s


def _s(f, key) -> str:
    v = f.get(key, "")
    if isinstance(v, list):
        v = v[0] if v else ""
    return str(v or "").strip()


async def backup():
    print("Backup pre-migración...")
    data = {
        "FAMILIAS": await _get_all(_FAMILIAS),
        "TUTORES": await _get_all(_TUTORES),
        "PRUEBA": await _get_all(_PRUEBAS),
    }
    os.makedirs("backups", exist_ok=True)
    fn = f"backups/pre_migracion_tutores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Guardado: {fn}")
    print(f"  FAMILIAS={len(data['FAMILIAS'])} · TUTORES={len(data['TUTORES'])} · PRUEBA={len(data['PRUEBA'])}\n")


def _extraer_tutor(f, rol) -> dict | None:
    """Arma los campos del tutor desde los campos PADRE/MADRE de una FAMILIA. None si no hay nombre."""
    suf = "PADRE" if rol == "Papá" else "MADRE"
    nombre = _s(f, f"NOMBRE {suf}")
    if not nombre:
        return None
    campos = {"NOMBRE": nombre, "PARENTESCO": rol}
    for dst, src in [
        ("APELLIDO", f"APELLIDO {suf}"), ("APODO", f"APODO {suf}"),
        ("CI", f"CI {suf}"), ("CELL", f"CELL {suf}"),
        ("EMAIL", f"EMAIL {suf}"), ("FECHA NACIMIENTO", f"FECHA NACIMIENTO {suf}"),
    ]:
        val = _s(f, src)
        if val:
            campos[dst] = val
    return campos


async def main():
    modo = "DRY-RUN (no escribe)" if DRY else "EJECUTAR (escribe en Airtable)"
    print(f"\n=== Migración PADRE/MADRE → TUTORES FENIX — {modo} ===\n")
    if not DRY:
        await backup()

    familias = await _get_all(_FAMILIAS)
    print(f"FAMILIAS FENIX leídas: {len(familias)}")

    # Tutores existentes (idempotencia): set de (familia_id, parentesco)
    tutores_exist = await _get_all(_TUTORES)
    ya = set()
    for t in tutores_exist:
        tf = t.get("fields", {})
        fam = tf.get("FAMILIA", [])
        fam_id = fam[0] if fam else ""
        ya.add((fam_id, _s(tf, "PARENTESCO")))
    print(f"TUTORES ya existentes: {len(tutores_exist)}\n")

    # Índice de teléfonos que pagaron: tel_normalizado de PRUEBA con MONTO>0 o PAGOS
    pruebas = await _get_all(_PRUEBAS)
    tels_pagaron = set()
    for p in pruebas:
        pf = p.get("fields", {})
        monto = pf.get("MONTO", 0) or 0
        if monto > 0 or pf.get("PAGOS"):
            tel = _norm_tel(pf.get("TELEFONO"))
            if tel:
                tels_pagaron.add(tel)
    print(f"Teléfonos con pago en PRUEBA: {len(tels_pagaron)}\n")

    st = {"tutores_nuevos": 0, "ya_ok": 0, "quien_paga": 0, "fam_sin_tutor": 0}

    for fam in sorted(familias, key=lambda x: x.get("fields", {}).get("FAMILIA", "")):
        fam_id = fam["id"]
        f = fam.get("fields", {})
        nombre_fam = _s(f, "FAMILIA") or fam_id

        creados_fam = 0
        for rol in ("Papá", "Mamá"):
            tutor = _extraer_tutor(f, rol)
            if not tutor:
                continue
            if (fam_id, rol) in ya:
                st["ya_ok"] += 1
                continue

            tutor["FAMILIA"] = [fam_id]
            # ¿Es quien paga? Su CELL matchea un teléfono que pagó en PRUEBA
            cell_norm = _norm_tel(tutor.get("CELL", ""))
            paga = bool(cell_norm) and cell_norm in tels_pagaron
            if paga:
                tutor["ES QUIEN PAGA"] = True
                st["quien_paga"] += 1

            marca = "  💲PAGA" if paga else ""
            print(f"[{nombre_fam}] CREAR {rol}: {tutor['NOMBRE']} {tutor.get('APELLIDO','')}"
                  f" (CI={tutor.get('CI','-')}, CELL={tutor.get('CELL','-')}){marca}")
            st["tutores_nuevos"] += 1
            creados_fam += 1

            if not DRY:
                res = await _post(_TUTORES, tutor)
                if not res:
                    print(f"    ⚠️ ERROR creando tutor {rol} de {nombre_fam}")

        if creados_fam == 0 and not any((fam_id, r) in ya for r in ("Papá", "Mamá")):
            st["fam_sin_tutor"] += 1
            print(f"[{nombre_fam}] ⚠️ sin NOMBRE PADRE ni MADRE — no se crea tutor")

    print("\n=== RESUMEN ===")
    print(f"Tutores a crear:       {st['tutores_nuevos']}")
    print(f"  de ellos 'quien paga': {st['quien_paga']}")
    print(f"Ya existían (skip):    {st['ya_ok']}")
    print(f"Familias sin tutor:    {st['fam_sin_tutor']}")
    if DRY:
        print("\n(DRY-RUN — no se escribió nada. Correr con --ejecutar para aplicar.)")


if __name__ == "__main__":
    asyncio.run(main())
