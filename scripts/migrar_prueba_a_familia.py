"""
Fase 3 — Migra los registros SUELTOS de PRUEBA FENIX → FAMILIAS + NIÑOS y repunta PAGOS.

Qué hace:
  - Agrupa los PRUEBA por TELEFONO (1 familia por teléfono, reusa si ya existe).
  - Deduplica hijos por (nombre normalizado) → 1 NIÑO por hijo real (consolida los
    re-registros tipo "Lee Jun x4").
  - Linkea cada PRUEBA → FAMILIA + NINO FENIX (traza + idempotencia).
  - Repunta los PAGOS de cada PRUEBA hacia FAMILIA FENIX, SOLO los de FUENTE=FENIX.

Qué NO hace (por decisión):
  - NO migra CANCELADOS (se revisan aparte).
  - NO crea RESERVAS históricas (las fechas viejas ya pasaron).
  - NO borra registros de PRUEBA FENIX (eso es Fase 4, tras verificar).
  - NO toca ningún pago que no sea FUENTE=FENIX (no roza Salsa).

Idempotente: re-correrlo no duplica (salta los PRUEBA que ya tienen FAMILIA+NINO,
y los pagos que ya cuelgan de la familia).

Uso:
    python scripts/migrar_prueba_a_familia.py            # DRY-RUN (no escribe nada)
    python scripts/migrar_prueba_a_familia.py --ejecutar # escribe en Airtable
"""

import asyncio
import sys
import os
import json
from datetime import datetime

from agent.airtable_client import (
    _get_records, _patch, _PRUEBAS, _FAMILIAS,
    crear_familia, crear_nino, buscar_familia_por_telefono,
    obtener_ninos_de_familia, _sin_acentos, deducir_genero,
)

DRY = "--ejecutar" not in sys.argv
_PAGOS = "PAGOS"
_FUENTE_FENIX = "FENIX KIDS ACADEMY"

# Correcciones manuales de rol: la heurística de género fallaba en estos.
# Confirmado con Iván (conoce a sus clientes). Clave = teléfono (único).
_OVERRIDE_ROL = {
    "595983273528": "padre",   # Luis Peralta
    "595971462496": "madre",   # Milagros Maldonado
    "595973295552": "madre",   # Ruth Almiron
    "595981980706": "madre",   # Nancy Segovia
    "595991278888": "madre",   # Solange Recalde
    "595983047547": "madre",   # Edith Guerrero
    "595982138554": "madre",   # Dirse Alcaraz
}


def _norm(s: str) -> str:
    return _sin_acentos((s or "").strip())


def _scalar(v):
    """Normaliza un valor que puede venir como lista/dict de Airtable a string."""
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):
        v = v.get("name", "")
    return str(v or "")


async def backup():
    """Snapshot JSON de PRUEBA, FAMILIAS y PAGOS-Fenix antes de tocar nada."""
    print("Backup pre-migración...")
    data = {
        "PRUEBA": await _get_records(_PRUEBAS, max_records=200),
        "FAMILIAS": await _get_records(_FAMILIAS, max_records=200),
        "PAGOS_FENIX": await _get_records(_PAGOS, formula=f"{{FUENTE}}='{_FUENTE_FENIX}'", max_records=300),
    }
    os.makedirs("backups", exist_ok=True)
    fn = f"backups/pre_migracion_prueba_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Guardado: {fn}")
    print(f"  PRUEBA={len(data['PRUEBA'])} · FAMILIAS={len(data['FAMILIAS'])} · PAGOS_FENIX={len(data['PAGOS_FENIX'])}\n")


async def main():
    modo = "DRY-RUN (no escribe)" if DRY else "EJECUTAR (escribe en Airtable)"
    print(f"\n=== Migración PRUEBA FENIX → FAMILIAS — {modo} ===\n")
    if not DRY:
        await backup()

    pruebas = await _get_records(_PRUEBAS, max_records=200)
    print(f"PRUEBA FENIX leídos: {len(pruebas)}")

    # Mapa de pagos FENIX (id -> fields) para repunte seguro (no toca Salsa)
    pagos_fenix = await _get_records(_PAGOS, formula=f"{{FUENTE}}='{_FUENTE_FENIX}'", max_records=300)
    pagos_fenix_map = {p["id"]: p.get("fields", {}) for p in pagos_fenix}
    print(f"PAGOS FUENTE=FENIX en la base: {len(pagos_fenix_map)}\n")

    # ── Filtrar: fuera cancelados y ya-migrados ───────────────────────────
    candidatos, saltados_cancelado, saltados_migrado = [], 0, 0
    for p in pruebas:
        f = p.get("fields", {})
        if _scalar(f.get("CONVERSION")).upper() == "CANCELADO":
            saltados_cancelado += 1
            continue
        if f.get("FAMILIA") and f.get("NINO FENIX"):
            saltados_migrado += 1
            continue
        candidatos.append(p)

    # ── Agrupar por teléfono ──────────────────────────────────────────────
    grupos, sin_tel = {}, []
    for p in candidatos:
        tel = (p.get("fields", {}).get("TELEFONO") or "").strip()
        if not tel:
            sin_tel.append(p)
            continue
        grupos.setdefault(tel, []).append(p)

    print(f"Cancelados saltados: {saltados_cancelado}")
    print(f"Ya migrados saltados: {saltados_migrado}")
    print(f"Candidatos a migrar: {len(candidatos)}  →  {len(grupos)} familias (por teléfono)")
    print(f"Sin teléfono (revisar a mano): {len(sin_tel)}\n")

    st = {
        "fam_nuevas": 0, "fam_reusadas": 0,
        "ninos_nuevos": 0, "ninos_reusados": 0,
        "pruebas_linkeadas": 0,
        "pagos_repuntados": 0, "pagos_ya_ok": 0, "pagos_no_fenix": 0,
    }

    for tel, regs in sorted(grupos.items()):
        # ── Familia: reusar o crear (A PRUEBA) ────────────────────────────
        fam = await buscar_familia_por_telefono(tel)
        if fam:
            fam_id = fam["id"]
            st["fam_reusadas"] += 1
            existentes = await obtener_ninos_de_familia(fam_id)
            etiqueta_fam = f"REUSA {fam_id}"
        else:
            nom = ape = ""
            for r in regs:
                rf = r.get("fields", {})
                if rf.get("NOMBRE"):
                    nom, ape = rf.get("NOMBRE", ""), rf.get("APELLIDO", "")
                    break
            # Rol: override manual si existe, si no deducir por el nombre
            _rol = _OVERRIDE_ROL.get(tel) or ("madre" if deducir_genero(nom) == "MUJER" else "padre")
            if DRY:
                fam_id, existentes = f"DRY-FAM-{tel}", []
                etiqueta_fam = f"CREAR familia A PRUEBA [{_rol}] ({nom} {ape})"
            else:
                fam_id = await crear_familia({_rol: {"nombre": nom, "apellido": ape, "telefono": tel}})
                if fam_id:
                    await _patch(_FAMILIAS, fam_id, {"ESTADO PLAN": "A PRUEBA"})
                existentes = []
                etiqueta_fam = f"CREADA {fam_id} [{_rol}] ({nom} {ape})"
            st["fam_nuevas"] += 1

        print(f"[{tel}] {etiqueta_fam}")
        mapa_nino = {_norm(n.get("nombre", "")): n.get("id") for n in existentes}

        # ── Niños (dedup por nombre) + link de cada PRUEBA ────────────────
        for r in regs:
            rf = r.get("fields", {})
            hijo = (rf.get("NOMBRE HIJO") or "").strip()
            hijo_ape = (rf.get("APELLIDO HIJO") or "").strip()
            key = _norm(hijo)

            nino_id = None
            if key and key in mapa_nino:
                nino_id = mapa_nino[key]
                st["ninos_reusados"] += 1
                print(f"    · hijo '{hijo}' → reusa niño {nino_id}")
            elif key:
                if DRY:
                    nino_id = f"DRY-NINO-{key}"
                    print(f"    · hijo '{hijo}' → CREAR niño")
                else:
                    nino_id = await crear_nino({
                        "nombre": hijo, "apellido": hijo_ape,
                        "fecha_nacimiento": rf.get("FECHA NACIMIENTO", ""),
                        "sexo": _scalar(rf.get("GENERO")),
                    }, fam_id)
                    print(f"    · hijo '{hijo}' → niño {nino_id}")
                if nino_id:
                    mapa_nino[key] = nino_id
                st["ninos_nuevos"] += 1
            else:
                print(f"    · (PRUEBA {r['id']} sin NOMBRE HIJO)")

            # Link PRUEBA → FAMILIA + NINO
            campos = {}
            if not rf.get("FAMILIA") and fam_id:
                campos["FAMILIA"] = [fam_id]
            if not rf.get("NINO FENIX") and nino_id:
                campos["NINO FENIX"] = [nino_id]
            if campos:
                st["pruebas_linkeadas"] += 1
                if not DRY:
                    await _patch(_PRUEBAS, r["id"], campos)

            # ── Repuntar PAGOS de esta PRUEBA → FAMILIA FENIX (solo Fenix) ─
            for pago_id in (rf.get("PAGOS") or []):
                pf = pagos_fenix_map.get(pago_id)
                if pf is None:
                    st["pagos_no_fenix"] += 1
                    print(f"    $ pago {pago_id} NO es FUENTE=FENIX → no se toca")
                    continue
                ya = pf.get("FAMILIA FENIX", []) or []
                if fam_id and fam_id in ya:
                    st["pagos_ya_ok"] += 1
                    continue
                st["pagos_repuntados"] += 1
                print(f"    $ pago {pago_id} → repuntar a FAMILIA FENIX")
                if not DRY and fam_id:
                    await _patch(_PAGOS, pago_id, {"FAMILIA FENIX": list(ya) + [fam_id]})
                # Reflejar el cambio en memoria: no repuntar el mismo pago dos veces
                # en esta corrida (cuando un pago cuelga de varios PRUEBA hermanos).
                if fam_id:
                    pf["FAMILIA FENIX"] = list(ya) + [fam_id]

    # ── Resumen ───────────────────────────────────────────────────────────
    print("\n=== RESUMEN ===")
    print(f"Familias nuevas:     {st['fam_nuevas']}")
    print(f"Familias reusadas:   {st['fam_reusadas']}")
    print(f"Niños nuevos:        {st['ninos_nuevos']}")
    print(f"Niños reusados:      {st['ninos_reusados']}")
    print(f"PRUEBA linkeadas:    {st['pruebas_linkeadas']}")
    print(f"Pagos a repuntar:    {st['pagos_repuntados']}")
    print(f"Pagos ya OK:         {st['pagos_ya_ok']}")
    print(f"Pagos NO Fenix:      {st['pagos_no_fenix']} (intactos)")
    print(f"Sin teléfono:        {len(sin_tel)}")
    if DRY:
        print("\n(DRY-RUN — no se escribió nada. Correr con --ejecutar para aplicar.)")


if __name__ == "__main__":
    asyncio.run(main())
