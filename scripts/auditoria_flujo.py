"""
Auditoría de flujo de leads con datos bancarios — FENIX KIDS ACADEMY

Verifica que cada lead que recibió datos bancarios completó el flujo:
  datos bancarios → pago → agenda → formulario → QR

Y que los datos en Airtable (PRUEBA FENIX) están completos.

Uso:
  python scripts/auditoria_flujo.py
"""

import asyncio
import httpx
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

# Fix encoding Windows (emojis en terminal)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "https://fenix-kids-agent-production.up.railway.app"
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "23ebc7b3d716f558f4ba53a4b3f000dbceb09b350aa5a65fc3f6475227a1e8d9")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appWwCQxALdMMV4MA")
AIRTABLE_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"

CI_BANCARIO = "1604338"  # Alias bancario — si aparece en msg de assistant, se enviaron datos

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
PY_TZ = timezone(timedelta(hours=-3))


# ── Airtable helpers ─────────────────────────────────────────────────────────

async def fetch_all_prueba_fenix() -> list[dict]:
    """Fetch todos los registros de PRUEBA FENIX (paginado)."""
    records = []
    offset = None
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params = {"pageSize": "100"}
            if offset:
                params["offset"] = offset
            r = await client.get(
                f"{AIRTABLE_BASE_URL}/PRUEBA%20FENIX",
                headers=headers,
                params=params,
            )
            if r.status_code != 200:
                print(f"Error Airtable: {r.status_code} — {r.text[:200]}")
                break
            data = r.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
    return records


# ── Railway helpers ──────────────────────────────────────────────────────────

async def fetch_conversacion(client: httpx.AsyncClient, telefono: str) -> list[dict]:
    """Fetch conversación completa de producción."""
    try:
        r = await client.get(
            f"{BASE_URL}/conversacion/{telefono}",
            headers={"X-ADMIN-KEY": ADMIN_KEY},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("conversacion", [])
    except Exception as e:
        print(f"  Error fetch {telefono}: {e}")
    return []


# ── Checks modulares: FLUJO CONVERSACIONAL ───────────────────────────────────

def check_datos_bancarios(mensajes: list[dict]) -> bool:
    """¿El assistant envió datos bancarios (ALIAS 1604338)?"""
    return any(
        CI_BANCARIO in m.get("texto", "")
        for m in mensajes
        if m.get("rol") == "assistant"
    )


def check_pago_confirmado(mensajes: list[dict]) -> bool:
    """¿El user envió comprobante Y el assistant confirmó el pago?"""
    tiene_comprobante = any(
        m.get("texto", "").strip() in ("[imagen]", "[documento]")
        for m in mensajes
        if m.get("rol") == "user"
    )
    tiene_confirmacion = any(
        "pago confirmado" in m.get("texto", "").lower()
        for m in mensajes
        if m.get("rol") == "assistant"
    )
    return tiene_comprobante and tiene_confirmacion


def check_agenda(record: dict) -> bool:
    """¿PRUEBA FENIX tiene fecha/hora de reserva definida?"""
    f = record.get("fields", {})
    fecha = (f.get("FECHA RESERVA") or "").strip()
    hora = (f.get("HORA") or "").strip()
    return bool(fecha) and fecha != "(por definir)" and bool(hora) and hora != "(por definir)"


def check_formulario(record: dict) -> bool:
    """¿PRUEBA FENIX tiene nombre padre + nombre hijo completos?"""
    f = record.get("fields", {})
    nombre = (f.get("NOMBRE") or "").strip()
    apellido = (f.get("APELLIDO") or "").strip()
    nombre_hijo = (f.get("NOMBRE HIJO") or "").strip()
    return bool(nombre) and bool(apellido) and bool(nombre_hijo)


def check_qr(record: dict) -> bool:
    """¿Se envió el QR?"""
    return bool(record.get("fields", {}).get("QR ENVIADO"))


# ── Checks modulares: CAMPOS AIRTABLE ───────────────────────────────────────

CAMPOS_REQUERIDOS = [
    ("NOMBRE", "Nombre padre"),
    ("APELLIDO", "Apellido padre"),
    ("NOMBRE HIJO", "Nombre hijo"),
    ("APELLIDO HIJO", "Apellido hijo"),
    ("FECHA NACIMIENTO", "Fecha nacimiento"),
    ("FECHA RESERVA", "Fecha reserva"),
    ("HORA", "Hora"),
    ("QR RESERVA", "URL QR"),
]

CAMPOS_CHECK = [
    ("QR ENVIADO", "QR enviado"),
]

CAMPOS_LINK = [
    ("LEAD", "Lead vinculado"),
]

CAMPOS_MONTO = [
    ("MONTO", "Monto"),
    ("METODO DE PAGO", "Método de pago"),
]


def check_campos_airtable(record: dict) -> dict[str, bool]:
    """Verifica completitud de cada campo requerido."""
    f = record.get("fields", {})
    resultado = {}

    for campo, label in CAMPOS_REQUERIDOS:
        valor = (f.get(campo) or "").strip()
        resultado[label] = bool(valor) and valor != "(por definir)"

    for campo, label in CAMPOS_CHECK:
        resultado[label] = bool(f.get(campo))

    for campo, label in CAMPOS_LINK:
        resultado[label] = bool(f.get(campo))

    for campo, label in CAMPOS_MONTO:
        valor = f.get(campo)
        if campo == "MONTO":
            resultado[label] = isinstance(valor, (int, float)) and valor > 0
        else:
            resultado[label] = bool(valor)

    return resultado


# ── Categorización de acciones ───────────────────────────────────────────────

def categorizar_acciones(flujo: dict, campos: dict, telefono: str) -> list[str]:
    """Determina qué acciones tomar según los checks."""
    acciones = []

    if not flujo["pago"]:
        acciones.append("Verificar comprobante manualmente")
    if not flujo["agenda"]:
        acciones.append("Definir fecha y hora de reserva")
    if not flujo["formulario"]:
        acciones.append("Pedir datos al padre (nombre, apellido, hijo)")
    if not flujo["qr"]:
        acciones.append(f"Enviar QR con /enviar-qr/{telefono}")

    faltantes = [label for label, ok in campos.items() if not ok]
    if faltantes:
        acciones.append(f"Completar en Airtable: {', '.join(faltantes)}")

    return acciones if acciones else ["Sin acción requerida"]


# ── Output ───────────────────────────────────────────────────────────────────

def imprimir_lead(telefono: str, nombre: str, flujo: dict, campos: dict, acciones: list[str]):
    """Imprime resultado de un lead."""
    # Flujo
    flujo_items = []
    for paso, ok in flujo.items():
        emoji = "\u2705" if ok else "\u274c"
        flujo_items.append(f"{paso}{emoji}")
    flujo_ok = all(flujo.values())
    flujo_label = "OK" if flujo_ok else "INCOMPLETO"

    # Airtable
    faltantes = [label for label, ok in campos.items() if not ok]
    at_ok = len(faltantes) == 0
    at_label = "OK | completo" if at_ok else f"INCOMPLETO | falta: {', '.join(faltantes)}"

    # Acciones
    accion_str = " + ".join(acciones) if acciones[0] != "Sin acción requerida" else acciones[0]

    print(f"\n{telefono} \u2014 {nombre}")
    print(f"  Flujo: {flujo_label} | {' '.join(flujo_items)}")
    print(f"  Airtable: {at_label}")
    print(f"  Acción: {accion_str}")


def imprimir_resumen(resultados: list[dict]):
    """Imprime resumen final."""
    total = len(resultados)
    flujo_ok = sum(1 for r in resultados if all(r["flujo"].values()))
    at_ok = sum(1 for r in resultados if all(r["airtable"].values()))

    sin_pago = sum(1 for r in resultados if not r["flujo"]["pago"])
    sin_agenda = sum(1 for r in resultados if not r["flujo"]["agenda"])
    sin_form = sum(1 for r in resultados if not r["flujo"]["formulario"])
    sin_qr = sum(1 for r in resultados if not r["flujo"]["qr"])

    pct_flujo = (flujo_ok / total * 100) if total else 0
    pct_at = (at_ok / total * 100) if total else 0

    print(f"\n{'=' * 50}")
    print(f"  RESUMEN")
    print(f"{'=' * 50}")
    print(f"Total leads auditados: {total}")
    print(f"Flujo completo: {flujo_ok}/{total} ({pct_flujo:.0f}%)")
    print(f"Airtable completo: {at_ok}/{total} ({pct_at:.0f}%)")
    print(f"\nAcciones pendientes:")
    if sin_pago:
        print(f"  - Verificar pago: {sin_pago} leads")
    if sin_agenda:
        print(f"  - Definir agenda: {sin_agenda} leads")
    if sin_form:
        print(f"  - Pedir formulario: {sin_form} leads")
    if sin_qr:
        print(f"  - Enviar QR: {sin_qr} leads")
    if flujo_ok == total and at_ok == total:
        print("  Ninguna \u2014 todo OK")


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    ahora = datetime.now(PY_TZ)
    fecha_str = ahora.strftime("%Y-%m-%d")

    print(f"{'=' * 50}")
    print(f"  AUDITORIA FENIX \u2014 {fecha_str}")
    print(f"{'=' * 50}")

    # 1. Fetch PRUEBA FENIX
    print("\nCargando registros de PRUEBA FENIX...")
    pruebas = await fetch_all_prueba_fenix()
    print(f"  {len(pruebas)} registros encontrados")

    # 2. Filtrar solo los que tienen teléfono
    pruebas_con_tel = [p for p in pruebas if p.get("fields", {}).get("TELEFONO")]
    print(f"  {len(pruebas_con_tel)} con teléfono")

    # 3. Auditar cada uno
    resultados = []
    async with httpx.AsyncClient() as client:
        for i, record in enumerate(pruebas_con_tel):
            f = record.get("fields", {})
            telefono = f["TELEFONO"]
            nombre = f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip() or "Sin nombre"
            nombre_hijo = f.get("NOMBRE HIJO", "")

            # Fetch conversación
            mensajes = await fetch_conversacion(client, telefono)

            # Solo auditar leads que recibieron datos bancarios
            if not mensajes or not check_datos_bancarios(mensajes):
                continue

            # Checks de flujo
            flujo = {
                "datos": True,  # ya verificado arriba
                "pago": check_pago_confirmado(mensajes),
                "agenda": check_agenda(record),
                "formulario": check_formulario(record),
                "qr": check_qr(record),
            }

            # Checks de Airtable
            campos = check_campos_airtable(record)

            # Acciones
            acciones = categorizar_acciones(flujo, campos, telefono)

            # Output
            imprimir_lead(telefono, f"{nombre} ({nombre_hijo})" if nombre_hijo else nombre, flujo, campos, acciones)

            resultados.append({
                "telefono": telefono,
                "nombre": nombre,
                "nombre_hijo": nombre_hijo,
                "record_id": record["id"],
                "flujo": flujo,
                "airtable": campos,
                "acciones": acciones,
            })

    # 4. Resumen
    if resultados:
        imprimir_resumen(resultados)
    else:
        print("\nNo se encontraron leads con datos bancarios enviados.")

    # 5. Guardar JSON
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, f"auditoria_{fecha_str}.json")
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(
            {"fecha": fecha_str, "total": len(resultados), "resultados": resultados},
            fp, ensure_ascii=False, indent=2,
        )
    print(f"\nJSON guardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
