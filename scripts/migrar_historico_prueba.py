# scripts/migrar_historico_prueba.py — Migración 2.D: rescate del histórico de PRUEBA FENIX
#
# PRUEBA FENIX ya no se escribe ni se lee (2.C completa). Antes de renombrarla a
# LEGACY hay que copiar lo que SOLO vive ahí:
#   1. Asistencias históricas: pruebas con PRESENTE=True → RESERVA histórica
#      (NIÑO+HORARIO+PRESENTE) si el niño no la tiene ya para esa fecha.
#   2. ASISTENCIA FENIX: filas que linkean PRUEBA pero no NIÑO → completar NIÑO.
#   3. Caras: pruebas con FACE_ID cuyo NIÑO no tiene → re-indexar la FOTO en
#      Rekognition bajo el nino_id y guardar el FACE_ID nuevo en NIÑOS.
#   4. Reporte de lo no migrable (sin link a NIÑO, fechas ilegibles) → a mano.
#
# Uso:
#   py -3 scripts/migrar_historico_prueba.py --backup    # JSON completo a backups/
#   py -3 scripts/migrar_historico_prueba.py             # ANALIZAR (dry-run)
#   py -3 scripts/migrar_historico_prueba.py --escribir  # ejecutar de verdad

import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# El script vive en scripts/ — sumar la raíz del repo para importar agent.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Consola Windows cp1252 no banca → ni acentos en algunos casos
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

ESCRIBIR = "--escribir" in sys.argv
BACKUP = "--backup" in sys.argv

_RAIZ = Path(__file__).resolve().parent.parent


async def _todas(tabla: str, filtro: str = "") -> list[dict]:
    """Todos los registros, paginado (la _get_records del agente ya pagina)."""
    from agent.airtable_client import _get_records
    return await _get_records(tabla, formula=filtro, max_records=2000)


async def hacer_backup():
    hoy = datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()
    destino = _RAIZ / "backups" / hoy
    destino.mkdir(parents=True, exist_ok=True)
    for tabla, archivo in (("PRUEBA FENIX", "prueba_fenix.json"),
                           ("ASISTENCIA FENIX", "asistencia_fenix.json")):
        recs = await _todas(tabla)
        (destino / archivo).write_text(
            json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {tabla}: {len(recs)} registros → {destino / archivo}")
    print("Backup listo.")


def _fecha_iso(texto: str) -> str | None:
    """FECHA RESERVA es texto libre → ISO. Reusa el parser de la tool."""
    from agent.tools.reservas import _parsear_fecha
    t = (texto or "").strip()
    if not t or "definir" in t.lower():
        return None
    return _parsear_fecha(t)


async def migrar():
    from agent.airtable_client import (
        _get_records, _patch, _post, _BASE_URL, _headers,
        _NINOS, _RESERVAS, obtener_o_crear_horario, crear_reserva,
    )
    import httpx

    pruebas = await _todas("PRUEBA FENIX")
    asistencias = await _todas("ASISTENCIA FENIX")
    ninos = await _todas(_NINOS)
    nino_por_id = {n["id"]: n["fields"] for n in ninos}
    print(f"{len(pruebas)} pruebas · {len(asistencias)} asistencias · {len(ninos)} niños")

    stats = Counter()
    acciones_reserva: list[dict] = []   # {nino_id, fecha, hora, etiqueta}
    acciones_asis: list[dict] = []      # {asis_id, nino_id, etiqueta}
    acciones_cara: list[dict] = []      # {prueba_id, nino_id, foto_url, etiqueta}
    problemas: list[str] = []

    # Reservas existentes por (nino, fecha) — para no duplicar
    reservas_existentes: set[tuple[str, str]] = set()
    async with httpx.AsyncClient() as client:
        for n in ninos:
            for rid in n["fields"].get("RESERVAS FENIX", []) or []:
                try:
                    r = await client.get(f"{_BASE_URL}/{_RESERVAS}/{rid}", headers=_headers(), timeout=10)
                    if r.status_code == 200:
                        f = r.json().get("fields", {})
                        fe = f.get("FECHA", "")
                        fe = (fe[0] if fe else "") if isinstance(fe, list) else fe
                        reservas_existentes.add((n["id"], str(fe)[:10]))
                except Exception as e:
                    problemas.append(f"leyendo reserva {rid}: {e}")
    print(f"{len(reservas_existentes)} pares (niño, fecha) con reserva existente")

    # ── 1. Pruebas con PRESENTE → RESERVA histórica ────────────────────────
    for p in pruebas:
        f = p["fields"]
        etiqueta = f.get("NOMBRE COMPLETO") or p["id"]
        if not f.get("PRESENTE"):
            continue
        nino_ids = f.get("NINO FENIX") or []
        if not nino_ids:
            stats["PRESENTE sin link a NIÑO (a mano)"] += 1
            problemas.append(f"PRESENTE sin NIÑO: {etiqueta} ({p['id']})")
            continue
        fecha = _fecha_iso(f.get("FECHA RESERVA", ""))
        if not fecha and f.get("FECHA Y HORA RESERVA"):
            fecha = str(f["FECHA Y HORA RESERVA"])[:10]
        if not fecha:
            stats["PRESENTE sin fecha legible (a mano)"] += 1
            problemas.append(f"PRESENTE sin fecha: {etiqueta} ({p['id']}) FECHA RESERVA={f.get('FECHA RESERVA')!r}")
            continue
        hora = (f.get("HORA") or "").strip() or "11:00"
        if (nino_ids[0], fecha) in reservas_existentes:
            stats["PRESENTE ya tiene reserva esa fecha"] += 1
            continue
        acciones_reserva.append({"nino_id": nino_ids[0], "fecha": fecha, "hora": hora, "etiqueta": etiqueta})
        stats["RESERVA histórica a crear"] += 1

    # ── 2. ASISTENCIA con PRUEBA pero sin NIÑO ─────────────────────────────
    prueba_por_id = {p["id"]: p["fields"] for p in pruebas}
    for a in asistencias:
        f = a["fields"]
        if f.get("NIÑO"):
            stats["ASISTENCIA ya con NIÑO"] += 1
            continue
        prueba_link = f.get("PRUEBA") or []
        if not prueba_link:
            stats["ASISTENCIA sin PRUEBA ni NIÑO (a mano)"] += 1
            problemas.append(f"ASISTENCIA huérfana: {f.get('REGISTRO', a['id'])}")
            continue
        pf = prueba_por_id.get(prueba_link[0], {})
        nino_ids = pf.get("NINO FENIX") or []
        if not nino_ids:
            stats["ASISTENCIA con PRUEBA sin NIÑO (a mano)"] += 1
            problemas.append(f"ASISTENCIA {f.get('REGISTRO', a['id'])}: su PRUEBA no linkea NIÑO")
            continue
        acciones_asis.append({"asis_id": a["id"], "nino_id": nino_ids[0],
                              "etiqueta": f.get("REGISTRO") or a["id"]})
        stats["ASISTENCIA a completar con NIÑO"] += 1

    # ── 3. Caras: FACE_ID en PRUEBA cuyo NIÑO no tiene ─────────────────────
    for p in pruebas:
        f = p["fields"]
        if not (f.get("FACE_ID") or "").strip():
            continue
        nino_ids = f.get("NINO FENIX") or []
        if not nino_ids:
            stats["FACE_ID sin link a NIÑO (a mano)"] += 1
            problemas.append(f"FACE_ID sin NIÑO: {f.get('NOMBRE COMPLETO') or p['id']}")
            continue
        nf = nino_por_id.get(nino_ids[0], {})
        if (nf.get("FACE_ID") or "").strip():
            stats["FACE_ID: el NIÑO ya tiene la suya"] += 1
            continue
        fotos = f.get("FOTO") or []
        if not fotos:
            stats["FACE_ID sin FOTO para re-indexar (a mano)"] += 1
            problemas.append(f"FACE_ID sin FOTO: {f.get('NOMBRE COMPLETO') or p['id']}")
            continue
        acciones_cara.append({"prueba_id": p["id"], "nino_id": nino_ids[0],
                              "foto_url": fotos[0].get("url", ""),
                              "etiqueta": f.get("NOMBRE COMPLETO") or p["id"]})
        stats["CARA a re-indexar en el NIÑO"] += 1

    # ── Reporte ────────────────────────────────────────────────────────────
    print("\n" + "=" * 62)
    for k, v in stats.most_common():
        print(f"  {v:4d}  {k}")
    print("=" * 62)
    if problemas:
        print(f"\nPARA REVISAR A MANO ({len(problemas)}):")
        for x in problemas:
            print("  -", x)

    if not ESCRIBIR:
        print("\nDRY-RUN — nada se escribió. Ejemplos:")
        for a in acciones_reserva[:5]:
            print(f"  RESERVA: {a['etiqueta']} → {a['fecha']} {a['hora']}")
        for a in acciones_asis[:5]:
            print(f"  ASISTENCIA: {a['etiqueta']} → NIÑO {a['nino_id']}")
        for a in acciones_cara[:5]:
            print(f"  CARA: {a['etiqueta']} → NIÑO {a['nino_id']}")
        return

    print("\nESCRIBIENDO…")
    # 1. Reservas históricas (crear + marcar PRESENTE)
    ok_res = 0
    for a in acciones_reserva:
        try:
            horario_id = await obtener_o_crear_horario(a["fecha"], a["hora"])
            rid = await crear_reserva(a["nino_id"], horario_id, "") if horario_id else None
            if rid:
                await _patch(_RESERVAS, rid, {"PRESENTE": True})
                ok_res += 1
            else:
                print(f"  ERROR reserva: {a['etiqueta']}")
        except Exception as e:
            print(f"  ERROR reserva {a['etiqueta']}: {e}")
    print(f"  RESERVAS históricas: {ok_res}/{len(acciones_reserva)}")

    # 2. ASISTENCIA → NIÑO
    ok_asis = 0
    for a in acciones_asis:
        try:
            if await _patch("ASISTENCIA FENIX", a["asis_id"], {"NIÑO": [a["nino_id"]]}):
                ok_asis += 1
        except Exception as e:
            print(f"  ERROR asistencia {a['etiqueta']}: {e}")
    print(f"  ASISTENCIAS completadas: {ok_asis}/{len(acciones_asis)}")

    # 3. Caras → re-indexar en Rekognition bajo el nino_id
    ok_caras = 0
    import httpx as _hx
    from agent.face_recognition import actualizar_cara
    for a in acciones_cara:
        try:
            async with _hx.AsyncClient(timeout=30) as c:
                r = await c.get(a["foto_url"])
            if r.status_code != 200:
                print(f"  ERROR cara {a['etiqueta']}: foto HTTP {r.status_code}")
                continue
            face_id = await actualizar_cara(a["nino_id"], r.content)
            if face_id:
                from agent.airtable_client import _NINOS as _N
                await _patch(_N, a["nino_id"], {"FACE_ID": face_id})
                ok_caras += 1
            else:
                print(f"  ERROR cara {a['etiqueta']}: Rekognition no indexó")
        except Exception as e:
            print(f"  ERROR cara {a['etiqueta']}: {e}")
    print(f"  CARAS re-indexadas: {ok_caras}/{len(acciones_cara)}")
    print("\nListo. PRUEBA FENIX quedó intacta (solo se copió hacia afuera).")


if __name__ == "__main__":
    asyncio.run(hacer_backup() if BACKUP else migrar())
