"""Crea, sube el asset y publica el Flow de inscripción de Fenix vía Graph API.

Fenix vive en el WABA compartido con Salsa Soul (2112324596219739). El token de
Fenix no tiene rol de management sobre ese WABA, así que para crear/publicar el
Flow se usa el token de management con acceso al WABA (el de whatsapp-agentkit/Dorita).

Idempotente-ish: si ya existe un flow con el mismo nombre, lo reutiliza.
Lee el token de management vía la env var META_MGMT_TOKEN, o del .env de
whatsapp-agentkit como fallback. No imprime el token.

Uso: python scripts/crear_flow_fenix.py
Réplica de whatsapp-agentkit/scripts/crear_flow_inscripcion.py.
"""
import json
import os
import sys
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
FLOW_JSON_PATH = RAIZ / "config" / "flows" / "formulario_fenix.json"
WABA_ID = "2112324596219739"  # WABA compartido Fenix + Salsa Soul
FLOW_NAME = "fenix_inscripcion"
API = "https://graph.facebook.com/v21.0"
DORITA_ENV = Path.home() / "Projects" / "whatsapp-agentkit" / ".env"


def _token() -> str:
    tok = os.getenv("META_MGMT_TOKEN", "").strip()
    if tok:
        return tok
    if DORITA_ENV.exists():
        for linea in DORITA_ENV.read_text(encoding="utf-8").splitlines():
            if linea.startswith("META_ACCESS_TOKEN="):
                return linea.split("=", 1)[1].strip()
    sys.exit("No hay token de management (seteá META_MGMT_TOKEN o el .env de Dorita).")


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
        print(f"\n>>> FENIX_FLOW_ID={flow_id}")


if __name__ == "__main__":
    main()
