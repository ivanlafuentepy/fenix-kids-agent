"""
Exportar conversaciones de producción a MDs por fecha.
Descarga todas las conversaciones de la API de prod y genera:
  - CONVERSACIONES FENIX/YYYY-MM-DD.md (un MD por día)
  - CONVERSACIONES FENIX/CONVERSACIONES_RESERVAS.md (solo las que reservaron)
"""

import asyncio
import httpx
import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict

# Config
BASE_URL = "https://fenix-kids-agent-production.up.railway.app"
ADMIN_KEY = "23ebc7b3d716f558f4ba53a4b3f000dbceb09b350aa5a65fc3f6475227a1e8d9"
HEADERS = {"X-ADMIN-KEY": ADMIN_KEY}
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CONVERSACIONES FENIX")
PHONES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "all_phones.txt")

# Fechas a exportar
FECHA_INICIO = "2026-05-01"
FECHA_FIN = "2026-05-07"

# Timezone offset Paraguay (UTC-3) — los timestamps de prod son UTC
PY_OFFSET = timedelta(hours=-3)


def ts_to_py(ts_str: str) -> datetime | None:
    """Convierte ISO timestamp a datetime en hora Paraguay."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        # Si no tiene timezone, asumir UTC
        if dt.tzinfo is None:
            return dt + PY_OFFSET
        return dt + PY_OFFSET
    except Exception:
        try:
            dt = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
            return dt + PY_OFFSET
        except Exception:
            return None


def fecha_py(ts_str: str) -> str:
    """Retorna la fecha en formato YYYY-MM-DD (hora Paraguay)."""
    dt = ts_to_py(ts_str)
    if dt:
        return dt.strftime("%Y-%m-%d")
    return ""


def hora_py(ts_str: str) -> str:
    """Retorna hora:min en hora Paraguay."""
    dt = ts_to_py(ts_str)
    if dt:
        return dt.strftime("%H:%M")
    return ""


def extraer_nombre_de_conversacion(mensajes: list[dict]) -> str:
    """Intenta extraer el nombre del padre/madre de la conversación."""
    import re
    # Buscar en mensajes del asistente que mencionan nombre
    for m in mensajes:
        if m.get("rol") == "assistant":
            txt = m.get("texto", "")
            # "Reserva confirmada ✅ Eladio y Amira tienen..."
            match = re.search(r"[Rr]eserva confirmada[✅!\s]*(.+?)\s+tienen?\s+su\s+lugar", txt)
            if match:
                return match.group(1).strip()
    # Buscar nombre del hijo en respuestas de Ivan
    for m in mensajes:
        if m.get("rol") == "assistant":
            txt = m.get("texto", "")
            match = re.search(r"(?:Con|Para)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s+a\s+los\s+\d+", txt)
            if match:
                return match.group(1).strip()
    return ""


def conversacion_tiene_reserva(mensajes: list[dict]) -> bool:
    """Detecta si la conversación terminó en reserva/pago."""
    for m in mensajes:
        txt = (m.get("texto", "") or "").lower()
        if m.get("rol") == "assistant":
            if "reserva confirmada" in txt:
                return True
            if "pago confirmado" in txt:
                return True
    return False


def conversacion_tiene_agendamiento(mensajes: list[dict]) -> bool:
    """Detecta si la conversación llegó a agendar (eligió horario)."""
    for m in mensajes:
        txt = (m.get("texto", "") or "").lower()
        if m.get("rol") == "assistant":
            if "datos para la transferencia" in txt:
                return True
            if "reserva confirmada" in txt:
                return True
    return False


def formatear_conversacion(telefono: str, data: dict, mensajes_del_dia: list[dict]) -> str:
    """Formatea una conversación completa para el MD."""
    nombre = extraer_nombre_de_conversacion(data.get("conversacion", []))
    tiene_reserva = conversacion_tiene_reserva(mensajes_del_dia)

    lines = []
    lines.append(f"### {telefono}" + (f" — {nombre}" if nombre else ""))
    lines.append(f"**Mensajes del día:** {len(mensajes_del_dia)}" + (" | ✅ RESERVÓ" if tiene_reserva else ""))
    lines.append("")

    for m in mensajes_del_dia:
        rol = m.get("rol", "?")
        texto = m.get("texto", "")
        ts = m.get("timestamp", "")
        hora = hora_py(ts)

        if rol == "user":
            lines.append(f"**[{hora}] 👤 PADRE:**")
        elif rol == "assistant":
            lines.append(f"**[{hora}] 🤖 AGENTE:**")
        else:
            lines.append(f"**[{hora}] 📌 {rol.upper()}:**")

        # Texto con indentación
        for linea in texto.split("\n"):
            lines.append(f"> {linea}")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


async def descargar_conversacion(client: httpx.AsyncClient, telefono: str) -> dict | None:
    """Descarga una conversación completa de prod."""
    try:
        r = await client.get(
            f"{BASE_URL}/conversacion/{telefono}",
            headers=HEADERS,
            timeout=15.0,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        print(f"  Error {telefono}: {e}")
        return None


async def main():
    # Leer teléfonos
    with open(PHONES_FILE, "r") as f:
        phones = [line.strip() for line in f if line.strip()]

    print(f"Total teléfonos: {len(phones)}")
    print(f"Descargando conversaciones de prod...")

    # Descargar todas las conversaciones (en batches de 20 para no saturar)
    todas = {}  # telefono -> data
    batch_size = 20

    async with httpx.AsyncClient() as client:
        for i in range(0, len(phones), batch_size):
            batch = phones[i:i+batch_size]
            tasks = [descargar_conversacion(client, tel) for tel in batch]
            results = await asyncio.gather(*tasks)

            for tel, data in zip(batch, results):
                if data and data.get("conversacion"):
                    todas[tel] = data

            done = min(i + batch_size, len(phones))
            if done % 100 == 0 or done == len(phones):
                print(f"  {done}/{len(phones)} descargados ({len(todas)} con mensajes)")

    print(f"\nConversaciones con mensajes: {len(todas)}")

    # Agrupar mensajes por fecha (hora Paraguay)
    # Para cada día, necesitamos saber qué teléfonos tuvieron actividad ese día
    por_fecha = defaultdict(list)  # fecha -> [(telefono, data, mensajes_del_dia)]

    # También recopilar todas las que tienen reserva
    con_reserva = []  # [(telefono, data)]

    for telefono, data in todas.items():
        mensajes = data.get("conversacion", [])

        # Agrupar mensajes por fecha
        mensajes_por_dia = defaultdict(list)
        for m in mensajes:
            fecha = fecha_py(m.get("timestamp", ""))
            if fecha:
                mensajes_por_dia[fecha].append(m)

        # Agregar a por_fecha
        for fecha, msgs_dia in mensajes_por_dia.items():
            por_fecha[fecha].append((telefono, data, msgs_dia))

        # Detectar si tiene reserva
        if conversacion_tiene_reserva(mensajes):
            con_reserva.append((telefono, data))

    # Generar MDs por fecha (del 1 al 7 de mayo)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    fecha_actual = datetime.strptime(FECHA_INICIO, "%Y-%m-%d")
    fecha_fin = datetime.strptime(FECHA_FIN, "%Y-%m-%d")

    while fecha_actual <= fecha_fin:
        fecha_str = fecha_actual.strftime("%Y-%m-%d")
        fecha_display = fecha_actual.strftime("%d/%m/%Y")
        dia_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][fecha_actual.weekday()]

        convs_dia = por_fecha.get(fecha_str, [])

        # Contar agendados del día
        total_agendados = sum(1 for _, _, msgs in convs_dia if conversacion_tiene_agendamiento(msgs))
        total_reservados = sum(1 for _, _, msgs in convs_dia if conversacion_tiene_reserva(msgs))

        lines = []
        lines.append(f"# CONVERSACIONES FENIX — {dia_semana} {fecha_display}")
        lines.append("")
        lines.append(f"**Total conversaciones activas:** {len(convs_dia)}")
        lines.append(f"**Total agendados:** {total_agendados}")
        lines.append(f"**Total reservados (pago):** {total_reservados}")
        lines.append("")

        # Lista de todos los números con nombres
        lines.append("## Lista de contactos del día")
        lines.append("")
        lines.append("| # | Teléfono | Nombre | Msgs | Estado |")
        lines.append("|---|----------|--------|------|--------|")

        for idx, (tel, data, msgs_dia) in enumerate(sorted(convs_dia, key=lambda x: x[2][0].get("timestamp", "") if x[2] else ""), 1):
            nombre = extraer_nombre_de_conversacion(data.get("conversacion", []))
            tiene_res = "✅ RESERVÓ" if conversacion_tiene_reserva(msgs_dia) else ""
            tiene_ag = "📋 Agendó" if not tiene_res and conversacion_tiene_agendamiento(msgs_dia) else ""
            estado = tiene_res or tiene_ag or "—"
            lines.append(f"| {idx} | {tel} | {nombre or '—'} | {len(msgs_dia)} | {estado} |")

        lines.append("")
        lines.append("---")
        lines.append("")

        # Conversaciones completas
        lines.append("## Conversaciones completas")
        lines.append("")

        for tel, data, msgs_dia in sorted(convs_dia, key=lambda x: x[2][0].get("timestamp", "") if x[2] else ""):
            lines.append(formatear_conversacion(tel, data, msgs_dia))

        if not convs_dia:
            lines.append("*No hubo conversaciones este día.*")
            lines.append("")

        # Escribir MD
        filename = f"{fecha_str}.md"
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"  {filename} — {len(convs_dia)} conversaciones, {total_reservados} reservas")

        fecha_actual += timedelta(days=1)

    # Generar CONVERSACIONES_RESERVAS.md
    lines = []
    lines.append("# CONVERSACIONES RESERVAS — Todas las que pagaron")
    lines.append("")
    lines.append(f"**Total conversaciones con reserva:** {len(con_reserva)}")
    lines.append(f"**Período:** {FECHA_INICIO} al {FECHA_FIN}")
    lines.append("")

    # Lista
    lines.append("## Lista de reservas")
    lines.append("")
    lines.append("| # | Teléfono | Nombre |")
    lines.append("|---|----------|--------|")

    for idx, (tel, data) in enumerate(sorted(con_reserva, key=lambda x: x[0]), 1):
        nombre = extraer_nombre_de_conversacion(data.get("conversacion", []))
        lines.append(f"| {idx} | {tel} | {nombre or '—'} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Conversaciones completas
    lines.append("## Conversaciones completas")
    lines.append("")

    for tel, data in sorted(con_reserva, key=lambda x: x[0]):
        mensajes = data.get("conversacion", [])
        nombre = extraer_nombre_de_conversacion(mensajes)

        lines.append(f"### {tel}" + (f" — {nombre}" if nombre else ""))
        lines.append(f"**Total mensajes:** {len(mensajes)}")
        lines.append("")

        for m in mensajes:
            rol = m.get("rol", "?")
            texto = m.get("texto", "")
            ts = m.get("timestamp", "")
            hora = hora_py(ts)
            fecha = fecha_py(ts)

            if rol == "user":
                lines.append(f"**[{fecha} {hora}] 👤 PADRE:**")
            elif rol == "assistant":
                lines.append(f"**[{fecha} {hora}] 🤖 AGENTE:**")
            else:
                lines.append(f"**[{fecha} {hora}] 📌 {rol.upper()}:**")

            for linea in texto.split("\n"):
                lines.append(f"> {linea}")
            lines.append("")

        lines.append("---")
        lines.append("")

    filepath = os.path.join(OUTPUT_DIR, "CONVERSACIONES_RESERVAS.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  CONVERSACIONES_RESERVAS.md — {len(con_reserva)} conversaciones con reserva")
    print(f"\nListo! Archivos en: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
