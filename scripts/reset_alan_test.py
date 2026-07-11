# scripts/reset_alan_test.py — deja a ALAN TEST como si nunca hubiera llegado HOY
"""
Reset del niño de prueba de Ivan (NIÑOS: recLwzdHkFbHSysge / GUARDIAN: recMSDXlCzdQoU7dL)
para re-probar el flujo completo del Espejo: llegada + selector de avatar + presentación TV.

Borra/revierte SOLO lo de HOY (fecha PY):
  1. juego_eventos con nino_nombre='ALAN' (Postgres Railway)
  2. juego_vueltas uid='FACE:recLwzdHkFbHSysge'
  3. asistencias de hoy en ASISTENCIA FENIX
  4. movimientos de hoy del guardián + ORO vuelve al valor pre-test (20)
  5. guardián: ROBOT vacío, ESTADO JSON {}

Uso (necesita RAILWAY_API_TOKEN en el env y .env del repo para Airtable):
  py -3 scripts/reset_alan_test.py
"""

import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

NINO_ID = "recLwzdHkFbHSysge"
GUARDIAN_ID = "recMSDXlCzdQoU7dL"
NOMBRE_EVENTO = "ALAN"       # los eventos usan el NOMBRE de NIÑOS (sin apellido)
ORO_BASE = 20                # oro del guardián antes de las pruebas del 11/07

RAILWAY_PROJECT = "d8955677-8717-417a-a2e5-3daa553e3f21"
RAILWAY_ENV = "f37dbc59-4613-42de-9484-806b9b45b3fe"
RAILWAY_PG = "34f33911-8eaf-45a9-9085-bfeecf46b2a9"

_AT_KEY = os.getenv("AIRTABLE_API_KEY") or os.getenv("AIRTABLE_TOKEN") or ""
_AT_BASE = os.getenv("AIRTABLE_BASE_ID") or ""
_H = {"Authorization": f"Bearer {_AT_KEY}", "Content-Type": "application/json"}


def _hoy_py() -> str:
    return datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()


def _hoy0_utc() -> datetime:
    h = datetime.now(ZoneInfo("America/Asuncion")).replace(hour=0, minute=0, second=0, microsecond=0)
    return h.astimezone(timezone.utc).replace(tzinfo=None)


def _airtable(method: str, path: str, data: dict | None = None) -> dict:
    r = urllib.request.Request(f"https://api.airtable.com/v0/{_AT_BASE}/{path}", method=method,
                               headers=_H, data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(r) as resp:
        return json.load(resp)


def _db_url() -> str:
    """DATABASE_PUBLIC_URL del Postgres de FENIX via GraphQL de Railway."""
    q = {"query": f'query{{variables(projectId:"{RAILWAY_PROJECT}",environmentId:"{RAILWAY_ENV}",serviceId:"{RAILWAY_PG}")}}'}
    r = urllib.request.Request("https://backboard.railway.com/graphql/v2", method="POST",
                               headers={"Authorization": f"Bearer {os.getenv('RAILWAY_API_TOKEN', '')}",
                                        "Content-Type": "application/json",
                                        "User-Agent": "curl/8.0"},  # el edge 403ea el UA de urllib
                               data=json.dumps(q).encode())
    with urllib.request.urlopen(r) as resp:
        return json.load(resp)["data"]["variables"].get("DATABASE_PUBLIC_URL") or ""


async def _reset_postgres():
    import asyncpg
    conn = await asyncpg.connect(_db_url())
    hoy0 = _hoy0_utc()
    n1 = await conn.execute("DELETE FROM juego_eventos WHERE nino_nombre = $1 AND timestamp >= $2",
                            NOMBRE_EVENTO, hoy0)
    n2 = await conn.execute("DELETE FROM juego_vueltas WHERE uid = $1 AND cerrada >= $2",
                            f"FACE:{NINO_ID}", hoy0)
    print(f"postgres: eventos {n1} | vueltas {n2}")
    await conn.close()


def _reset_airtable():
    hoy = _hoy_py()
    # asistencias de hoy
    f = urllib.parse.quote(f"AND(SEARCH('alan', LOWER({{REGISTRO}})), IS_SAME({{FECHA}}, '{hoy}', 'day'))")
    for rec in _airtable("GET", f"ASISTENCIA%20FENIX?filterByFormula={f}&maxRecords=10").get("records", []):
        _airtable("DELETE", f"ASISTENCIA%20FENIX/{rec['id']}")
        print(f"asistencia borrada: {rec['fields'].get('REGISTRO')} ({rec['fields'].get('MÉTODO')})")
    # movimientos de hoy del guardián
    f = urllib.parse.quote(f"AND({{GUARDIAN ID}}='{GUARDIAN_ID}', IS_SAME(CREATED_TIME(), '{hoy}', 'day'))")
    for rec in _airtable("GET", f"MOVIMIENTOS%20BRASAS%20FENIX?filterByFormula={f}&maxRecords=20").get("records", []):
        _airtable("DELETE", f"MOVIMIENTOS%20BRASAS%20FENIX/{rec['id']}")
        print(f"movimiento borrado: {rec['fields'].get('MOTIVO')} ({rec['fields'].get('MONTO')})")
    # guardián como nuevo
    _airtable("PATCH", f"GUARDIANES%20FENIX/{GUARDIAN_ID}",
              {"fields": {"ROBOT": None, "ESTADO JSON": "{}", "ORO": ORO_BASE, "PLATA": 0}})
    g = _airtable("GET", f"GUARDIANES%20FENIX/{GUARDIAN_ID}")["fields"]
    print(f"guardian: ROBOT={g.get('ROBOT')!r} ORO={g.get('ORO')} PLATA={g.get('PLATA')} ESTADO={g.get('ESTADO JSON')}")


if __name__ == "__main__":
    if not (_AT_KEY and _AT_BASE and os.getenv("RAILWAY_API_TOKEN")):
        sys.exit("faltan AIRTABLE_API_KEY/AIRTABLE_BASE_ID (.env) o RAILWAY_API_TOKEN (env)")
    asyncio.run(_reset_postgres())
    _reset_airtable()
    print("LISTO — Alan vuelve a ser primera llegada del día")
