"""Crea, sube el asset y publica el Flow de cargar alumno (comando admin) vía Graph API.

El número de FENIX tiene WABA PROPIO (896276490105251, descubierto vía entry.id
del webhook el 2026-07-11) — NO está en el WABA de Dorita/Salsa (2112324596219739),
eso es solo el Business Portfolio compartido. El propio token de FENIX
(META_ACCESS_TOKEN) administra su WABA: lista números, flows, crea y publica.

Idempotente-ish: si ya existe un flow con el mismo nombre, lo reutiliza.
No imprime el token.

Uso: python scripts/crear_flow_cargar_nino.py
Ver scripts/crear_flow_fenix.py (Flow fenix_inscripcion — OJO: ese quedó en el WABA equivocado).
"""
import json
import os
import sys
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
FLOW_JSON_PATH = RAIZ / "config" / "flows" / "cargar_nino.json"
WABA_ID = "896276490105251"  # WABA PROPIO de Fenix (entry.id del webhook)
FLOW_NAME = "fenix_cargar_nino"
API = "https://graph.facebook.com/v21.0"
FENIX_ENV = RAIZ / ".env"


def _token() -> str:
    tok = os.getenv("META_MGMT_TOKEN", "").strip()
    if tok:
        return tok
    if FENIX_ENV.exists():
        for linea in FENIX_ENV.read_text(encoding="utf-8").splitlines():
            if linea.startswith("META_ACCESS_TOKEN="):
                return linea.split("=", 1)[1].strip()
    sys.exit("No hay token (seteá META_MGMT_TOKEN o META_ACCESS_TOKEN en el .env).")


def main() -> None:
    tok = _token()
    h = {"Authorization": f"Bearer {tok}"}
    flow_json = FLOW_JSON_PATH.read_text(encoding="utf-8")

    with httpx.Client(timeout=30) as c:
        r = c.get(f"{API}/{WABA_ID}/flows", headers=h, params={"fields": "id,name,status"})
        r.raise_for_status()
        flow_id = None
        for f in r.json().get("data", []):
            if f.get("name") == FLOW_NAME:
                flow_id = f["id"]
                print(f"Flow existente: {flow_id} (status {f.get('status')})")
                break

        if not flow_id:
            r = c.post(f"{API}/{WABA_ID}/flows", headers=h,
                       data={"name": FLOW_NAME, "categories": json.dumps(["OTHER"])})
            print("CREATE:", r.status_code, r.text)
            r.raise_for_status()
            flow_id = r.json()["id"]
            print(f"Flow creado: {flow_id}")

        files = {"file": ("flow.json", flow_json, "application/json")}
        r = c.post(f"{API}/{flow_id}/assets", headers=h,
                   data={"name": "flow.json", "asset_type": "FLOW_JSON"}, files=files)
        print("ASSET:", r.status_code, r.text)
        r.raise_for_status()
        val = r.json().get("validation_errors", [])
        if val:
            print("Errores de validacion:", json.dumps(val, indent=2, ensure_ascii=True))
            sys.exit("No publico: hay errores de validacion.")

        r = c.post(f"{API}/{flow_id}/publish", headers=h)
        print("PUBLISH:", r.status_code, r.text)
        r.raise_for_status()

        r = c.get(f"{API}/{flow_id}", headers=h, params={"fields": "id,name,status"})
        print("FINAL:", r.text)
        print(f"\n>>> FLOW_CARGAR_NINO_ID={flow_id}")


if __name__ == "__main__":
    main()
