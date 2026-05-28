"""
Script one-shot: marcar QR ENVIADO=True en todos los PRUEBA FENIX que no lo tienen.
Son agendas viejas — no se envía WhatsApp, solo se actualiza Airtable.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agent.airtable_client import _get_records, _PRUEBAS, marcar_qr_enviado_prueba


async def main():
    # Buscar PRUEBA FENIX donde QR ENVIADO está vacío/false
    formula = "NOT({QR ENVIADO})"
    records = await _get_records(_PRUEBAS, formula=formula, max_records=100)

    print(f"Encontrados: {len(records)} registros sin QR ENVIADO")

    if not records:
        print("Nada que hacer.")
        return

    exitos = 0
    errores = 0
    for r in records:
        fields = r.get("fields", {})
        tel = fields.get("TELEFONO", "?")
        nombre = fields.get("NOMBRE HIJO", fields.get("NOMBRE", "?"))
        ok = await marcar_qr_enviado_prueba(r["id"])
        status = "OK" if ok else "FAIL"
        if ok:
            exitos += 1
        else:
            errores += 1
        print(f"  {status} {nombre} ({tel}) — {r['id']}")

    print(f"\nResultado: {exitos} marcados, {errores} errores")


if __name__ == "__main__":
    asyncio.run(main())
