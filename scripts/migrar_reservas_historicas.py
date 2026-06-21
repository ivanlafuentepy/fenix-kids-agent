"""
A2 (migración) — Crea la RESERVA FENIX real de las pruebas VIVAS que hoy solo
viven como FECHA RESERVA+HORA dentro de PRUEBA FENIX.

Contexto: A1 (deployado 2026-06-21) empezó a crear la RESERVA real cuando se
define el sábado. Pero las pruebas agendadas ANTES de A1 (para el próximo sábado
en adelante) solo tienen su fecha en PRUEBA FENIX, no en RESERVAS. Este script
las puebla en RESERVAS para que la lista de asistencia pueda salir de ahí.

Qué hace:
  - Lee PRUEBA FENIX, se queda con las de FECHA RESERVA >= hoy (futuras/vivas).
  - Salta canceladas, ya inscriptas, sin teléfono y sin fecha parseable.
  - Para cada una, reusa gestionar_reserva(tel, "agendar", fecha, hora) — la MISMA
    ruta que usa A1: resuelve la familia por teléfono y crea una RESERVA por hijo.

Qué NO hace (por decisión):
  - NO borra ni patchea PRUEBA FENIX (queda intacta hasta el corte A3).
  - NO migra el histórico pasado (esas asistencias ya pasaron; los reportes viejos
    siguen leyendo PRUEBA hasta que se reestructuren).
  - NO toca PAGOS ni nada de Salsa.

Idempotente: crear_reserva no duplica (salta si el niño ya tiene reserva en ese
horario). Re-correrlo es seguro.

Uso:
    python scripts/migrar_reservas_historicas.py            # DRY-RUN (no escribe nada)
    python scripts/migrar_reservas_historicas.py --ejecutar # escribe en Airtable
"""

import asyncio
import sys
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from agent.airtable_client import (
    _get_records, _PRUEBAS, _RESERVAS, _FAMILIAS,
    buscar_familia_por_telefono, obtener_ninos_de_familia,
)
from agent.tools.reservas import _parsear_fecha
from agent.tools.agenda import gestionar_reserva

DRY = "--ejecutar" not in sys.argv
_SLOTS = ["9:30", "11:00", "15:30"]


def _scalar(v):
    """Normaliza un valor que puede venir como lista/dict de Airtable a string."""
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):
        v = v.get("name", "")
    return str(v or "")


def _normalizar_hora(hora_raw: str) -> str:
    """Mapea la HORA de PRUEBA ('11', '11h', '11:00') a un slot canónico."""
    h = (hora_raw or "").strip().lower().replace("hs", "").replace("h", "").strip()
    for t in _SLOTS:
        if h == t or h == t.split(":")[0] or h.lstrip("0") == t:
            return t
    return h  # devolver lo que haya; obtener_o_crear_horario decidirá


async def backup():
    """Snapshot JSON de PRUEBA y RESERVAS antes de tocar nada."""
    print("Backup pre-migración...")
    data = {
        "PRUEBA": await _get_records(_PRUEBAS, max_records=200),
        "RESERVAS": await _get_records(_RESERVAS, max_records=300),
        "FAMILIAS": await _get_records(_FAMILIAS, max_records=200),
    }
    os.makedirs("backups", exist_ok=True)
    fn = f"backups/pre_reservas_historicas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Guardado: {fn}")
    print(f"  PRUEBA={len(data['PRUEBA'])} · RESERVAS={len(data['RESERVAS'])} · FAMILIAS={len(data['FAMILIAS'])}\n")


async def main():
    modo = "DRY-RUN (no escribe)" if DRY else "EJECUTAR (escribe en Airtable)"
    print(f"\n=== Migración reservas vivas PRUEBA FENIX → RESERVAS FENIX — {modo} ===\n")
    if not DRY:
        await backup()

    hoy = datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()
    print(f"Fecha de corte (hoy PY): {hoy}  —  se migran pruebas con FECHA RESERVA >= hoy\n")

    pruebas = await _get_records(_PRUEBAS, max_records=200)
    print(f"PRUEBA FENIX leídos: {len(pruebas)}")

    # ── Filtrar candidatas (futuras, no canceladas, no inscriptas, con tel y fecha) ──
    candidatas = []
    sk_cancel = sk_inscripto = sk_sin_tel = sk_sin_fecha = sk_pasada = 0
    for p in pruebas:
        f = p.get("fields", {})
        if _scalar(f.get("CONVERSION")).upper() == "CANCELADO":
            sk_cancel += 1
            continue
        if f.get("INSCRIPTO") or f.get("INSCRIPCION"):
            sk_inscripto += 1
            continue
        tel = (f.get("TELEFONO") or "").strip()
        if not tel:
            sk_sin_tel += 1
            continue
        fecha_iso = _parsear_fecha(_scalar(f.get("FECHA RESERVA")))
        if not fecha_iso:
            sk_sin_fecha += 1
            continue
        if fecha_iso < hoy:
            sk_pasada += 1
            continue
        hora = _normalizar_hora(_scalar(f.get("HORA")))
        candidatas.append({
            "id": p["id"], "tel": tel, "fecha": fecha_iso, "hora": hora,
            "hijo": f"{_scalar(f.get('NOMBRE HIJO'))} {_scalar(f.get('APELLIDO HIJO'))}".strip(),
        })

    print(f"Saltadas — canceladas: {sk_cancel} · inscriptas: {sk_inscripto} · "
          f"sin tel: {sk_sin_tel} · sin fecha: {sk_sin_fecha} · pasadas: {sk_pasada}")
    print(f"Candidatas a migrar (fecha viva): {len(candidatas)}\n")

    st = {"creadas": 0, "ya_ok": 0, "sin_familia": 0, "errores": 0}

    for c in sorted(candidatas, key=lambda x: (x["fecha"], x["hora"], x["tel"])):
        etiqueta = f"[{c['tel']}] {c['hijo'] or '?'} → {c['fecha']} {c['hora']}h"

        if DRY:
            fam = await buscar_familia_por_telefono(c["tel"])
            if not fam:
                st["sin_familia"] += 1
                print(f"{etiqueta}  ⚠️ SIN FAMILIA (no se podrá crear reserva)")
                continue
            ninos = await obtener_ninos_de_familia(fam["id"])
            print(f"{etiqueta}  → CREAR {len(ninos)} reserva(s) (familia {fam['id']})")
            st["creadas"] += len(ninos) if ninos else 0
            continue

        # EJECUTAR — misma ruta que A1 (idempotente, crea por hijo)
        try:
            res = await gestionar_reserva(c["tel"], "agendar", fecha=c["fecha"], hora=c["hora"])
            if res.get("error"):
                if "familia" in (res.get("message") or "").lower():
                    st["sin_familia"] += 1
                    print(f"{etiqueta}  ⚠️ SIN FAMILIA — {res.get('message')}")
                else:
                    st["errores"] += 1
                    print(f"{etiqueta}  ❌ {res.get('message')}")
            else:
                st["creadas"] += res.get("cantidad", 0)
                print(f"{etiqueta}  ✅ {res.get('hijos', '?')} ({res.get('cantidad', 0)} reserva/s)")
        except Exception as e:
            st["errores"] += 1
            print(f"{etiqueta}  ❌ excepción: {e}")

    print("\n=== RESUMEN ===")
    print(f"Reservas creadas:    {st['creadas']}")
    print(f"Sin familia (skip):  {st['sin_familia']}")
    print(f"Errores:             {st['errores']}")
    if DRY:
        print("\n(DRY-RUN — no se escribió nada. Correr con --ejecutar para aplicar.)")


if __name__ == "__main__":
    asyncio.run(main())
