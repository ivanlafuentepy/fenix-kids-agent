"""
Exportar conversaciones de LEADS (Ivan) de produccion a MDs por fecha.
Excluye Aurora. Usa Airtable PRUEBA FENIX como fuente de verdad para reservas.
"""

import asyncio
import httpx
import os
import sys
import re
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

BASE_URL = "https://fenix-kids-agent-production.up.railway.app"
ADMIN_KEY = "23ebc7b3d716f558f4ba53a4b3f000dbceb09b350aa5a65fc3f6475227a1e8d9"
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "IVAN VAULT", "FENIX KIDS", "CONVERSACIONES FENIX")
PHONES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "all_phones.txt")
PY_OFFSET = timedelta(hours=-3)

# Default: exportar del 8 al 10 de mayo (lo que falta)
FECHA_INICIO = sys.argv[1] if len(sys.argv) > 1 else "2026-05-08"
FECHA_FIN = sys.argv[2] if len(sys.argv) > 2 else "2026-05-10"


def ts_to_py(ts_str):
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt + PY_OFFSET
        return dt + PY_OFFSET
    except Exception:
        try:
            return datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S") + PY_OFFSET
        except Exception:
            return None


def fecha_py(ts):
    dt = ts_to_py(ts)
    return dt.strftime("%Y-%m-%d") if dt else ""


def hora_py(ts):
    dt = ts_to_py(ts)
    return dt.strftime("%H:%M") if dt else ""


def es_conversacion_ivan(data):
    """True si la conversacion empezo con Ivan (lead), no Aurora."""
    mensajes = data.get("conversacion", [])
    for m in mensajes:
        if m.get("rol") == "assistant":
            txt = m.get("texto", "")
            if "Soy Aurora" in txt or "soy Aurora" in txt:
                return False
            if "FENIX Kids" in txt or "Profe Ivan" in txt or "fuera de servicio" in txt.lower():
                return True
            return True
    return True


def extraer_nombre_de_conversacion(mensajes):
    # From "Reserva confirmada X tiene..."
    for m in mensajes:
        if m.get("rol") == "assistant":
            txt = m.get("texto", "")
            match = re.search(
                r"[Rr]eserva confirmada[^\n]*?([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+(?:\s+y\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)?)\s+tienen?\s+su\s+lugar",
                txt,
            )
            if match:
                return match.group(1).strip()
    # From "Con [Nombre] a los X"
    for m in mensajes:
        if m.get("rol") == "assistant":
            txt = m.get("texto", "")
            match = re.search(r"(?:Con|Para)\s+([A-Z][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)\s+a\s+los\s+\d+", txt)
            if match:
                return match.group(1).strip()
    return ""


def tiene_agendamiento(mensajes):
    for m in mensajes:
        if m.get("rol") == "assistant":
            txt = (m.get("texto", "") or "").lower()
            if "datos para la transferencia" in txt:
                return True
    return False


async def get_real_reservas():
    """Get phones that actually have PRUEBA FENIX in Airtable."""
    headers = {"Authorization": f"Bearer {os.getenv('AIRTABLE_API_KEY')}"}
    phones = set()
    offset = None
    async with httpx.AsyncClient() as client:
        while True:
            params = {"pageSize": "100"}
            if offset:
                params["offset"] = offset
            r = await client.get(
                f"https://api.airtable.com/v0/{os.getenv('AIRTABLE_BASE_ID')}/PRUEBA%20FENIX",
                headers=headers, params=params, timeout=15,
            )
            data = r.json()
            for rec in data.get("records", []):
                tel = rec.get("fields", {}).get("TELEFONO", "")
                if tel:
                    phones.add(tel)
            offset = data.get("offset")
            if not offset:
                break
    return phones


async def download_conversation(client, tel):
    try:
        r = await client.get(
            f"{BASE_URL}/conversacion/{tel}",
            headers={"X-ADMIN-KEY": ADMIN_KEY},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  Error {tel}: {e}")
    return None


async def main():
    # Get real reservas from Airtable
    real_reservas = await get_real_reservas()
    print(f"Reservas reales (Airtable): {len(real_reservas)}")

    # Read phones
    with open(PHONES_FILE) as f:
        phones = [l.strip() for l in f if l.strip()]
    print(f"Total telefonos: {len(phones)}")

    # Download all conversations
    todas = {}
    async with httpx.AsyncClient() as client:
        for i in range(0, len(phones), 20):
            batch = phones[i:i+20]
            tasks = [download_conversation(client, tel) for tel in batch]
            results = await asyncio.gather(*tasks)
            for tel, data in zip(batch, results):
                if data and data.get("conversacion"):
                    todas[tel] = data
            done = min(i + 20, len(phones))
            if done % 100 == 0 or done == len(phones):
                print(f"  {done}/{len(phones)} ({len(todas)} con msgs)")

    # Filter only Ivan leads
    ivan_convs = {tel: data for tel, data in todas.items() if es_conversacion_ivan(data)}
    aurora_count = len(todas) - len(ivan_convs)
    print(f"Ivan (leads): {len(ivan_convs)} | Aurora (excluidas): {aurora_count}")

    # Group by date
    por_fecha = defaultdict(list)
    for tel, data in ivan_convs.items():
        mensajes = data.get("conversacion", [])
        msgs_por_dia = defaultdict(list)
        for m in mensajes:
            f = fecha_py(m.get("timestamp", ""))
            if f:
                msgs_por_dia[f].append(m)
        for fecha, msgs in msgs_por_dia.items():
            por_fecha[fecha].append((tel, data, msgs))

    # Generate daily MDs
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]

    fecha_actual = datetime.strptime(FECHA_INICIO, "%Y-%m-%d")
    fecha_fin = datetime.strptime(FECHA_FIN, "%Y-%m-%d")

    while fecha_actual <= fecha_fin:
        fs = fecha_actual.strftime("%Y-%m-%d")
        fd = fecha_actual.strftime("%d/%m/%Y")
        dia = dias[fecha_actual.weekday()]

        convs = por_fecha.get(fs, [])
        total_datos = sum(1 for _, _, msgs in convs if tiene_agendamiento(msgs))
        total_ag = sum(1 for tel, _, _ in convs if tel in real_reservas)

        lines = []
        lines.append(f"# CONVERSACIONES FENIX (LEADS) - {dia} {fd}")
        lines.append("")
        lines.append(f"**Total conversaciones activas:** {len(convs)}")
        lines.append(f"**Agendaron (pagaron):** {total_ag}")
        lines.append(f"**Datos enviados (sin pagar):** {total_datos}")
        lines.append("")

        # Contact table
        lines.append("## Lista de contactos del dia")
        lines.append("")
        lines.append("| # | Telefono | Nombre | Msgs | Estado |")
        lines.append("|---|----------|--------|------|--------|")

        sorted_convs = sorted(convs, key=lambda x: x[2][0].get("timestamp", "") if x[2] else "")
        for idx, (tel, data, msgs) in enumerate(sorted_convs, 1):
            nombre = extraer_nombre_de_conversacion(data.get("conversacion", []))
            es_res = tel in real_reservas
            es_ag = tiene_agendamiento(msgs)
            estado = "AGENDÓ ✅" if es_res else ("Datos enviados" if es_ag else "-")
            lines.append(f"| {idx} | {tel} | {nombre or '-'} | {len(msgs)} | {estado} |")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Conversaciones completas")
        lines.append("")

        for tel, data, msgs in sorted_convs:
            nombre = extraer_nombre_de_conversacion(data.get("conversacion", []))
            es_res = tel in real_reservas

            lines.append(f"### {tel}" + (f" - {nombre}" if nombre else ""))
            lines.append(f"**Mensajes del dia:** {len(msgs)}" + (" | RESERVO" if es_res else ""))
            lines.append("")

            for m in msgs:
                rol = m.get("rol", "?")
                texto = m.get("texto", "")
                ts = m.get("timestamp", "")
                h = hora_py(ts)

                if rol == "user":
                    lines.append(f"**[{h}] PADRE:**")
                elif rol == "assistant":
                    lines.append(f"**[{h}] IVAN:**")
                else:
                    lines.append(f"**[{h}] {rol.upper()}:**")

                for linea in texto.split("\n"):
                    lines.append(f"> {linea}")
                lines.append("")

            lines.append("---")
            lines.append("")

        if not convs:
            lines.append("*No hubo conversaciones de leads este dia.*")
            lines.append("")

        filepath = os.path.join(OUTPUT_DIR, f"FENIX {fs}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"  {fs}.md - {len(convs)} convs, {total_ag} agendaron")
        fecha_actual += timedelta(days=1)

    print("\nListo!")


if __name__ == "__main__":
    asyncio.run(main())
