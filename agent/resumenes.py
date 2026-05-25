# agent/resumenes.py — Resúmenes admin y asistencia
# Extraído de main.py — sin cambios de lógica

import os
import re
import logging

from agent.airtable_client import (
    obtener_ninos_por_horario, _get_records, _patch, crear_reserva,
    obtener_o_crear_horario,
    _LEADS, _PRUEBAS, _RESERVAS, _HORARIOS, _NINOS, _FAMILIAS,
    _BASE_URL, _headers,
)
from agent.telegram_bridge import obtener_topic
from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit")
proveedor = obtener_proveedor()

# Estado de asistencia pendiente: {telefono_admin: [{idx, record_id, tabla, nombre},...]}
_asistencia_pendiente: dict[str, list[dict]] = {}

# ── Resumen anuncios (comando admin) ─────────────────────────────────────────

_DIAS_SEMANA = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
_MESES_NOMBRE = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                 7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
_MONTOS_CONCEPTO = {
    "F.PRUEBA 90MIL": 90_000,
    "F.PRUEBA 100MIL": 100_000,
    "F.PRUEBA 120MIL": 120_000,
    "F.PRUEBA 150MIL": 150_000,
    "F.PRUEBA 180MIL": 180_000,
    "FENIXMAMA": 350_000,
    "PAQUETE5": 350_000,
    "PAQUETE12": 750_000,
}


def _parsear_filtro_fecha(texto_cmd: str) -> tuple[str, str | None, str | None]:
    """
    Parsea el filtro de fecha del comando resumen anuncios.
    Retorna (label, fecha_desde, fecha_hasta) en formato YYYY-MM-DD.
    None = sin filtro (mes corriente por default).
    """
    from datetime import date, timedelta, datetime, timezone

    # Paraguay es UTC-3 — Railway corre en UTC, así que forzamos hora PY
    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    # "resumen anuncios hoy"
    if "hoy" in texto_cmd:
        iso = hoy.isoformat()
        return f"hoy ({hoy.day}/{hoy.month})", iso, iso

    # "resumen anuncios ayer"
    if "ayer" in texto_cmd:
        ayer = hoy - timedelta(days=1)
        iso = ayer.isoformat()
        return f"ayer ({ayer.day}/{ayer.month})", iso, iso

    # "resumen anuncios abril" / "resumen anuncios marzo"
    for num, nombre in _MESES_NOMBRE.items():
        if nombre in texto_cmd:
            desde = f"{hoy.year}-{num:02d}-01"
            if num == 12:
                hasta = f"{hoy.year + 1}-01-01"
            else:
                hasta = f"{hoy.year}-{num + 1:02d}-01"
            # hasta es el primer día del mes siguiente (exclusive)
            ultimo = date.fromisoformat(hasta) - timedelta(days=1)
            return f"{nombre} {hoy.year}", desde, ultimo.isoformat()

    # Default: mes corriente (anuncios empezaron el 3 de mayo 2026)
    desde = f"{hoy.year}-{hoy.month:02d}-01"
    # Los anuncios arrancaron el 3/5, no contar leads orgánicos previos
    if hoy.year == 2026 and hoy.month == 5:
        desde = "2026-05-03"
    if hoy.month == 12:
        hasta_next = f"{hoy.year + 1}-01-01"
    else:
        hasta_next = f"{hoy.year}-{hoy.month + 1:02d}-01"
    ultimo = date.fromisoformat(hasta_next) - timedelta(days=1)
    return f"{_MESES_NOMBRE[hoy.month]} {hoy.year}", desde, ultimo.isoformat()


def _generar_slug(nombre: str, apellido: str) -> str:
    """Genera slug URL-friendly: 'Mariano Emanuel' + 'Centurion Saucedo' → 'mariano-emanuel-centurion-saucedo'"""
    import unicodedata
    raw = f"{nombre} {apellido}".lower().strip()
    norm = unicodedata.normalize("NFD", raw)
    norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", norm).strip("-")


async def _generar_resumen_reservas(telefono: str, fecha_override=None):
    """Genera resumen de reservas de un sábado, agrupado por turno.
    Si fecha_override es None, usa el sábado más cercano.
    Separa AURORA (alumnos inscriptos) y FENIX (clases de prueba)."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario, _get_records, _PRUEBAS
    import httpx as _httpx_res

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        # Calcular el sábado más cercano (hoy si es sábado, sino el próximo)
        dias_hasta_sabado = (5 - hoy.weekday()) % 7
        if dias_hasta_sabado == 0 and hoy.weekday() != 5:
            dias_hasta_sabado = 7
        sabado = hoy + timedelta(days=dias_hasta_sabado)
    fecha_iso = sabado.isoformat()

    _DIAS = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
    _MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
              7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
    fecha_label = f"{_DIAS[sabado.weekday()]} {sabado.day}/{sabado.month}"
    # FECHA RESERVA en PRUEBA FENIX se guarda como "9 de mayo" (texto, no ISO)
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    turnos = ["9:30", "11:00", "15:30"]

    # ── AURORA: alumnos inscriptos (RESERVAS FENIX via HORARIOS) ──
    aurora_por_turno = {}
    for hora in turnos:
        ninos = await obtener_ninos_por_horario(fecha_iso, hora)
        aurora_por_turno[hora] = ninos

    # ── FENIX: clases de prueba (PRUEBA FENIX con FECHA RESERVA = sábado) ──
    # Buscar por formato texto ("9 de mayo") y también ISO por si se normaliza a futuro
    pruebas_texto = await _get_records(
        _PRUEBAS,
        formula=f"AND({{FECHA RESERVA}}='{fecha_texto}', NOT({{INSCRIPTO}}))",
        max_records=50,
    )
    pruebas_iso = await _get_records(
        _PRUEBAS,
        formula=f"AND({{FECHA RESERVA}}='{fecha_iso}', NOT({{INSCRIPTO}}))",
        max_records=50,
    )
    # Dedup por record id
    _seen_ids = set()
    pruebas = []
    for rec in pruebas_texto + pruebas_iso:
        if rec["id"] not in _seen_ids:
            _seen_ids.add(rec["id"])
            pruebas.append(rec)
    fenix_por_turno: dict[str, list[dict]] = {h: [] for h in turnos}
    for rec in pruebas:
        f = rec.get("fields", {})
        hora_raw = (f.get("HORA") or "").strip()
        # Normalizar para matchear turnos (ej: "11h" → "11:00", "9:30h" → "9:30")
        if hora_raw not in fenix_por_turno:
            _h_clean = hora_raw.replace("h", "").replace("hs", "").strip()
            for t in turnos:
                if _h_clean == t or _h_clean.lstrip("0") == t or _h_clean == t.split(":")[0]:
                    hora_raw = t
                    break
        if hora_raw in fenix_por_turno:
            nombre = f.get("NOMBRE HIJO", "")
            apellido = f.get("APELLIDO HIJO", "")
            edad = str(f["EDAD HIJO"]) if f.get("EDAD HIJO") else ""
            fenix_por_turno[hora_raw].append({
                "nombre": nombre,
                "apellido": apellido,
                "edad": edad,
            })

    # ── Armar mensaje ──
    emojis = ["🦁", "🐯", "🦊", "🐻", "🐼", "🦋", "🌟", "⚡", "🔥", "🎯", "🦅", "🐺", "🌈", "🎪", "🏆"]
    _link_web = f"https://fenixkidsacademy.com/reservas?fecha={fecha_iso}"
    lineas = [f"📋 *RESERVAS — {fecha_label}*\n🔗 {_link_web}\n"]
    total_aurora = 0
    total_fenix = 0

    for hora in turnos:
        aurora = aurora_por_turno[hora]
        fenix = fenix_por_turno[hora]
        total_turno = len(aurora) + len(fenix)
        total_aurora += len(aurora)
        total_fenix += len(fenix)

        # Calcular edad promedio del turno (edad viene como "3,5" = 3 años 5 meses)
        edades_turno = []
        for n in aurora + fenix:
            try:
                _edad_raw = str(n.get("edad", ""))
                if "," in _edad_raw:
                    _a, _m = _edad_raw.split(",", 1)
                    edades_turno.append(int(_a) + int(_m) / 12)
                elif _edad_raw:
                    edades_turno.append(int(_edad_raw))
            except (ValueError, KeyError, TypeError):
                pass
        prom_str = f" — prom {sum(edades_turno)/len(edades_turno):.0f} años" if edades_turno else ""

        lineas.append(f"⏰ *{hora}h* — {total_turno} niño{'s' if total_turno != 1 else ''}{prom_str}")

        if aurora:
            lineas.append(f"   🌳 *Aurora ({len(aurora)}):*")
            for i, n in enumerate(aurora):
                emoji = emojis[i % len(emojis)]
                nombre = (n.get("apodo") or n["nombre"]).split()[0]
                apellido = n["apellido"].split()[0] if n["apellido"] else ""
                nombre_full = f"{nombre} {apellido}".strip()
                edad_str = f" ({n['edad']})" if n.get("edad") else ""
                lineas.append(f"      {emoji} {nombre_full}{edad_str}")

        if fenix:
            lineas.append(f"   🔥 *Fenix — prueba ({len(fenix)}):*")
            for i, n in enumerate(fenix):
                emoji = emojis[(i + len(aurora)) % len(emojis)]
                nombre = n["nombre"].split()[0] if n["nombre"] else ""
                apellido = n["apellido"].split()[0] if n["apellido"] else ""
                nombre_full = f"{nombre} {apellido}".strip()
                edad_str = f" ({n['edad']})" if n.get("edad") else ""
                lineas.append(f"      {emoji} {nombre_full}{edad_str}")

        if not aurora and not fenix:
            lineas.append("   — vacío")

        lineas.append("")

    total = total_aurora + total_fenix
    lineas.append(f"👧👦 *Total: {total} guerrero{'s' if total != 1 else ''}*")
    lineas.append(f"   🌳 Aurora: {total_aurora} | 🔥 Prueba: {total_fenix}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_flias(telefono: str, fecha_override=None):
    """Resumen tipo reservas pero con nombre hijo | nombre padre + link wa.me."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario, _get_records, _PRUEBAS

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        dias_hasta_sabado = (5 - hoy.weekday()) % 7
        if dias_hasta_sabado == 0 and hoy.weekday() != 5:
            dias_hasta_sabado = 7
        sabado = hoy + timedelta(days=dias_hasta_sabado)
    fecha_iso = sabado.isoformat()

    _DIAS = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
    fecha_label = f"{_DIAS[sabado.weekday()]} {sabado.day}/{sabado.month}"

    turnos = ["9:30", "11:00", "15:30"]

    # AURORA: inscriptos
    aurora_por_turno = {}
    for hora in turnos:
        ninos = await obtener_ninos_por_horario(fecha_iso, hora)
        aurora_por_turno[hora] = ninos

    # FENIX: pruebas (excluir INSCRIPTO=true, ya están en RESERVAS)
    pruebas_iso = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_iso}', NOT({{INSCRIPTO}}))", max_records=50)
    fenix_por_turno: dict[str, list[dict]] = {h: [] for h in turnos}
    for rec in pruebas_iso:
        f = rec.get("fields", {})
        hora_raw = (f.get("HORA") or "").strip()
        if hora_raw not in fenix_por_turno:
            _h_clean = hora_raw.replace("h", "").replace("hs", "").strip()
            for t in turnos:
                if _h_clean == t or _h_clean.lstrip("0") == t or _h_clean == t.split(":")[0]:
                    hora_raw = t
                    break
        if hora_raw in fenix_por_turno:
            tel_padre = f.get("TELEFONO", "")
            nombre_hijo = (f.get("NOMBRE HIJO") or "").split()[0]
            nombre_padre = f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip()
            fenix_por_turno[hora_raw].append({
                "nombre_hijo": nombre_hijo,
                "nombre_padre": nombre_padre,
                "telefono": tel_padre,
            })

    # Armar mensaje
    emojis = ["🦁", "🐯", "🦊", "🐻", "🐼", "🦋", "🌟", "⚡", "🔥", "🎯", "🦅", "🐺", "🌈", "🎪", "🏆", "🦈", "🐉", "🦖", "🌵", "🎸"]
    lineas = [f"👨‍👩‍👧‍👦 *FAMILIAS — {fecha_label}*\n"]
    total = 0
    _emoji_idx = 0

    for hora in turnos:
        aurora = aurora_por_turno[hora]
        fenix = fenix_por_turno[hora]
        total_turno = len(aurora) + len(fenix)
        total += total_turno

        lineas.append(f"⏰ *{hora}h* — {total_turno}")

        if aurora:
            for n in aurora:
                emoji = emojis[_emoji_idx % len(emojis)]
                _emoji_idx += 1
                nombre_hijo = (n.get("apodo") or n["nombre"]).split()[0]
                _fam_id = n.get("familia_id", "")
                _padre_nombre = ""
                _tel_padre = ""
                if _fam_id:
                    try:
                        from agent.airtable_client import _BASE_URL, _headers
                        import httpx
                        async with httpx.AsyncClient() as _cl:
                            _r = await _cl.get(f"{_BASE_URL}/FAMILIAS%20FENIX/{_fam_id}", headers=_headers(), timeout=10)
                            if _r.status_code == 200:
                                _ff = _r.json().get("fields", {})
                                if _ff.get("CELL MADRE"):
                                    _padre_nombre = f"{_ff.get('NOMBRE MADRE', '')} {_ff.get('APELLIDO MADRE', '')}".strip()
                                    _tel_padre = _ff["CELL MADRE"]
                                elif _ff.get("CELL PADRE"):
                                    _padre_nombre = f"{_ff.get('NOMBRE PADRE', '')} {_ff.get('APELLIDO PADRE', '')}".strip()
                                    _tel_padre = _ff["CELL PADRE"]
                    except Exception:
                        pass
                wa_link = f"wa.me/{_tel_padre}" if _tel_padre else ""
                lineas.append(f"  {emoji} {nombre_hijo} | {_padre_nombre}")
                if wa_link:
                    lineas.append(f"      {wa_link}")

        if fenix:
            for n in fenix:
                emoji = emojis[_emoji_idx % len(emojis)]
                _emoji_idx += 1
                wa_link = f"wa.me/{n['telefono']}" if n["telefono"] else ""
                lineas.append(f"  {emoji} {n['nombre_hijo']} | {n['nombre_padre']}")
                if wa_link:
                    lineas.append(f"      {wa_link}")

        if not aurora and not fenix:
            lineas.append("   — vacio")
        lineas.append("")

    lineas.append(f"*Total: {total}*")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_telegram(telefono: str):
    """Genera resumen de reservas con link de Telegram debajo de cada nombre."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records, _PRUEBAS
    from agent.telegram_bridge import obtener_topic

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    dias_hasta_sabado = (5 - hoy.weekday()) % 7
    if dias_hasta_sabado == 0 and hoy.weekday() != 5:
        dias_hasta_sabado = 7
    sabado = hoy + timedelta(days=dias_hasta_sabado)
    _MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
              7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"
    fecha_iso = sabado.isoformat()

    # Buscar PRUEBA FENIX por texto e ISO
    pruebas_texto = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_texto}'", max_records=50)
    pruebas_iso = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_iso}'", max_records=50)
    _seen = set()
    pruebas = []
    for rec in pruebas_texto + pruebas_iso:
        if rec["id"] not in _seen:
            _seen.add(rec["id"])
            pruebas.append(rec)

    turnos = ["9:30", "11:00", "15:30"]
    por_turno: dict[str, list[dict]] = {h: [] for h in turnos}

    for rec in pruebas:
        f = rec.get("fields", {})
        hora_raw = (f.get("HORA") or "").strip()
        # Normalizar
        if hora_raw not in por_turno:
            _h = hora_raw.replace("h", "").replace("hs", "").strip()
            for t in turnos:
                if _h == t or _h.lstrip("0") == t or _h == t.split(":")[0]:
                    hora_raw = t
                    break
        if hora_raw in por_turno:
            por_turno[hora_raw].append({
                "nombre": f.get("NOMBRE HIJO", ""),
                "apellido": f.get("APELLIDO HIJO", ""),
                "tel": f.get("TELEFONO", ""),
                "conversion": f.get("CONVERSION", ""),
                "responsable": f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip(),
            })

    # Agrupar por teléfono dentro de cada turno para hermanos
    lineas = [f"📋 *RESERVAS + TELEGRAM — SAB {sabado.day}/{sabado.month}*\n"]
    total = 0

    for hora in turnos:
        kids = por_turno[hora]
        # Agrupar por tel
        by_tel: dict[str, list] = {}
        for k in kids:
            tel = k["tel"]
            if tel not in by_tel:
                by_tel[tel] = {"nombres": [], "responsable": k.get("responsable", "")}
            nombre = f"{k['nombre']} {k['apellido']}".strip()
            if k.get("conversion") == "CANCELADO":
                nombre += " (CANCELADO)"
            by_tel[tel]["nombres"].append(nombre)

        count = sum(len(v["nombres"]) for v in by_tel.values())
        total += count
        lineas.append(f"⏰ *{hora}h* — {count} niño{'s' if count != 1 else ''}")

        for tel, data in by_tel.items():
            # Get Telegram topic link
            topic = await obtener_topic(tel)
            if topic and topic.group_id:
                gid = str(topic.group_id).replace("-100", "", 1)
                tg_link = f"https://t.me/c/{gid}/{topic.topic_id}"
            elif topic:
                tg_link = f"topic:{topic.topic_id}"
            else:
                tg_link = "sin topic"

            for nombre in data["nombres"]:
                lineas.append(f"   - {nombre}")
            if data["responsable"]:
                lineas.append(f"     👤 {data['responsable']}")
            lineas.append(f"     💬 {tg_link}")
            lineas.append("")

        if not kids:
            lineas.append("   — vacío")
            lineas.append("")

    lineas.append(f"👧👦 *Total: {total}*")
    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_lista_asistencia(telefono: str, turno_especifico: str = ""):
    """Genera lista numerada de niños para pasar asistencia. Guarda estado en _asistencia_pendiente."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario, _get_records, _PRUEBAS

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    # Si es sábado, usar hoy. Si no, buscar el sábado más cercano pasado (para control post-clase)
    if hoy.weekday() == 5:
        sabado = hoy
    else:
        # Último sábado
        sabado = hoy - timedelta(days=(hoy.weekday() + 2) % 7)

    fecha_iso = sabado.isoformat()
    _MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
              7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    turnos = [turno_especifico] if turno_especifico else ["9:30", "11:00", "15:30"]
    registros = []  # lista global numerada
    lineas = [f"✅ *ASISTENCIA — SAB {sabado.day}/{sabado.month}*\n"]

    for hora in turnos:
        # Aurora (inscriptos)
        ninos_aurora = await obtener_ninos_por_horario(fecha_iso, hora)
        # Fenix (pruebas)
        pruebas = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_texto}', {{HORA}}='{hora}')", max_records=50)
        # También buscar por ISO
        pruebas_iso = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_iso}', {{HORA}}='{hora}')", max_records=50)
        _seen = set()
        for p in pruebas + pruebas_iso:
            if p["id"] not in _seen:
                _seen.add(p["id"])

        if not ninos_aurora and not _seen:
            continue

        # El total real se calcula después de filtrar duplicados
        _idx_antes = len(registros)
        _linea_header_idx = len(lineas)
        lineas.append("")  # placeholder — se reemplaza abajo

        # Aurora (inscriptos)
        # Guardar nombres normalizados para dedup contra pruebas
        import unicodedata as _ud_asis
        def _norm_asis(t): return "".join(c for c in _ud_asis.normalize("NFD", t.lower()) if _ud_asis.category(c) != "Mn")
        _nombres_inscriptos = set()

        for n in ninos_aurora:
            idx = len(registros) + 1
            _n_parts = (n.get("apodo") or n.get("nombre", "?")).split()
            nombre = _n_parts[0] if _n_parts else "?"
            _a_parts = (n.get("apellido") or "").split()
            apellido = _a_parts[0] if _a_parts else ""
            nombre_full = f"{nombre} {apellido}".strip()
            _nombres_inscriptos.add(_norm_asis(f"{n.get('nombre', '')} {n.get('apellido', '')}"))
            reserva_id = n.get("reserva_id", "")
            registros.append({"idx": idx, "nombre": nombre_full, "tabla": "RESERVAS", "record_id": reserva_id, "nino_id": n.get("id", "")})
            # Indicador de asistencia ya cargada
            _mark = ""
            if n.get("presente"):
                _mark = " ✅"
            elif n.get("ausente"):
                _mark = " ❌"
            lineas.append(f"   {idx}. {nombre_full}{_mark}")

        # Fenix pruebas (excluir si ya está como inscripto)
        for pid in _seen:
            p = next(x for x in pruebas + pruebas_iso if x["id"] == pid)
            f = p.get("fields", {})
            if f.get("CONVERSION") == "CANCELADO":
                continue
            if f.get("INSCRIPTO"):
                continue
            _nombre_prueba = f"{f.get('NOMBRE HIJO', '')} {f.get('APELLIDO HIJO', '')}".strip()
            if _norm_asis(_nombre_prueba) in _nombres_inscriptos:
                continue  # ya listado como inscripto
            idx = len(registros) + 1
            _n_parts = (f.get("NOMBRE HIJO") or "?").split()
            nombre = _n_parts[0] if _n_parts else "?"
            _a_parts = (f.get("APELLIDO HIJO") or "").split()
            apellido = _a_parts[0] if _a_parts else ""
            nombre_full = f"{nombre} {apellido}".strip()
            registros.append({"idx": idx, "nombre": nombre_full, "tabla": "PRUEBAS", "record_id": p["id"]})
            _mark_p = ""
            if f.get("PRESENTE"):
                _mark_p = " ✅"
            elif f.get("AUSENTE"):
                _mark_p = " ❌"
            lineas.append(f"   {idx}. {nombre_full} 🔥{_mark_p}")

        # Reemplazar header con total real
        _total_turno = len(registros) - _idx_antes
        lineas[_linea_header_idx] = f"⏰ *{hora}h* ({_total_turno})"
        lineas.append("")

    if not registros:
        await proveedor.enviar_mensaje(telefono, "No hay reservas para pasar asistencia.")
        return

    lineas.append(f"*Total: {len(registros)}*")
    lineas.append("")
    lineas.append("Respondé *ok* (todos vinieron) o los números de los que faltaron (ej: 5 7)")

    _asistencia_pendiente[telefono] = registros
    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _procesar_respuesta_asistencia(telefono: str, respuesta: str):
    """Procesa la respuesta de asistencia: 'ok' o '5 7' (ausentes)."""
    from agent.airtable_client import _patch, _RESERVAS, _PRUEBAS

    registros = _asistencia_pendiente.pop(telefono, [])
    if not registros:
        await proveedor.enviar_mensaje(telefono, "No hay asistencia pendiente.")
        return

    if respuesta == "ok":
        ausentes = set()
    else:
        # Aceptar "1 2", "1,2", "1, 2", etc.
        _nums = re.split(r'[\s,]+', respuesta)
        ausentes = set(int(n) for n in _nums if n.isdigit())

    presentes = 0
    ausentes_nombres = []

    for reg in registros:
        es_presente = reg["idx"] not in ausentes
        campos_update = {"PRESENTE": es_presente, "AUSENTE": not es_presente}
        if reg["tabla"] == "RESERVAS" and reg.get("record_id"):
            await _patch(_RESERVAS, reg["record_id"], campos_update)
        elif reg["tabla"] == "PRUEBAS" and reg.get("record_id"):
            await _patch(_PRUEBAS, reg["record_id"], campos_update)

        if es_presente:
            presentes += 1
        else:
            ausentes_nombres.append(reg["nombre"])

    msg = f"✅ Asistencia cargada!\n\nPresentes: {presentes}/{len(registros)}"
    if ausentes_nombres:
        msg += f"\nAusentes: {', '.join(ausentes_nombres)}"

    await proveedor.enviar_mensaje(telefono, msg)
    logger.info(f"[ASISTENCIA] {presentes}/{len(registros)} presentes, ausentes: {ausentes_nombres}")


async def _agregar_presentes_por_nombres(telefono: str, texto: str):
    """
    Recibe nombres (separados por línea o coma) de niños que no estaban en la lista
    de asistencia pero vinieron. Crea reserva + marca PRESENTE para cada uno.
    Deduce el turno de la asistencia pendiente.
    """
    from datetime import datetime, timezone, timedelta
    from agent.airtable_client import _get_records, _NINOS, _PRUEBAS, _patch, _RESERVAS, obtener_o_crear_horario, crear_reserva
    import unicodedata

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()
    if hoy.weekday() == 5:
        sabado = hoy
    else:
        sabado = hoy - timedelta(days=(hoy.weekday() + 2) % 7)
    fecha_iso = sabado.isoformat()

    # Deducir turno de la asistencia pendiente
    registros_pendientes = _asistencia_pendiente.get(telefono, [])
    turno = "9:30"  # default
    if registros_pendientes:
        # Buscar el turno del último bloque — está implícito en el horario
        # Deducir por hora actual
        hora_py = datetime.now(_PY_TZ).hour
        if hora_py < 11:
            turno = "9:30"
        elif hora_py < 15:
            turno = "11:00"
        else:
            turno = "15:30"

    def _normalizar(t: str) -> str:
        t = unicodedata.normalize("NFD", t.lower())
        return "".join(c for c in t if unicodedata.category(c) != "Mn")

    def _match_nombre(buscar: str, completo: str) -> bool:
        """Todas las palabras de 'buscar' deben estar en 'completo'."""
        palabras = _normalizar(buscar).split()
        target = _normalizar(completo)
        return all(p in target for p in palabras)

    # Parsear nombres (separados por línea o coma)
    nombres = [n.strip() for n in re.split(r'[,\n]+', texto) if n.strip()]

    resultados = []
    ninos_all = await _get_records(_NINOS, formula="", max_records=200)
    for nombre_buscar in nombres:
        # Buscar en NIÑOS FENIX
        nino_match = None
        for n in ninos_all:
            f = n.get("fields", {})
            nombre_full = f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip()
            apodo = f.get("APODO", "")
            if _match_nombre(nombre_buscar, nombre_full) or (apodo and _match_nombre(nombre_buscar, apodo)):
                nino_match = {"id": n["id"], "nombre": nombre_full, "familia": f.get("FAMILIA", [])}
                break

        if nino_match:
            # Crear reserva + marcar presente
            horario_id = await obtener_o_crear_horario(fecha_iso, turno)
            if horario_id:
                familia_id = nino_match["familia"][0] if nino_match["familia"] else ""
                reserva_id = await crear_reserva(nino_match["id"], horario_id, familia_id)
                if reserva_id:
                    await _patch(_RESERVAS, reserva_id, {"PRESENTE": True})
                    resultados.append(f"✅ {nino_match['nombre']}")
                else:
                    resultados.append(f"⚠️ {nombre_buscar} (no pude crear reserva)")
            else:
                resultados.append(f"⚠️ {nombre_buscar} (no pude obtener horario)")
        else:
            # Buscar en PRUEBA FENIX
            _MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                      7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
            fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"
            pruebas = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_texto}'", max_records=50)
            pruebas_iso = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_iso}'", max_records=50)
            prueba_match = None
            for p in pruebas + pruebas_iso:
                pf = p.get("fields", {})
                nombre_full = f"{pf.get('NOMBRE HIJO', '')} {pf.get('APELLIDO HIJO', '')}".strip()
                if _match_nombre(nombre_buscar, nombre_full):
                    prueba_match = p
                    break

            if prueba_match:
                await _patch(_PRUEBAS, prueba_match["id"], {"PRESENTE": True})
                resultados.append(f"✅ {nombre_full} 🔥")
            else:
                resultados.append(f"❌ {nombre_buscar} (no encontrado)")

    # No limpiar asistencia pendiente — permite seguir agregando
    msg = f"📋 Asistencia extra ({turno}h):\n" + "\n".join(resultados)
    await proveedor.enviar_mensaje(telefono, msg)
    logger.info(f"[ASISTENCIA+] {resultados}")


async def _marcar_presente_por_nombre(telefono: str, nombre_buscar: str, solo_prueba: bool = False):
    """Marca PRESENTE=true para un niño buscado por nombre. solo_prueba=True busca solo en PRUEBA FENIX, False solo en NIÑOS/RESERVAS."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario, _get_records, _patch, _RESERVAS, _PRUEBAS
    import unicodedata

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    # Si es sábado, usar hoy. Si no, último sábado
    if hoy.weekday() == 5:
        sabado = hoy
    else:
        sabado = hoy - timedelta(days=(hoy.weekday() + 2) % 7)

    fecha_iso = sabado.isoformat()
    _MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
              7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    def _normalizar(t: str) -> str:
        t = unicodedata.normalize("NFD", t.lower())
        return "".join(c for c in t if unicodedata.category(c) != "Mn")

    def _match_nombre(buscar: str, completo: str) -> bool:
        """Todas las palabras de 'buscar' deben estar en 'completo'."""
        palabras = _normalizar(buscar).split()
        target = _normalizar(completo)
        return all(p in target for p in palabras)

    encontrados = []

    for hora in ["9:30", "11:00", "15:30"]:
        # Inscriptos (solo si NO es solo_prueba)
        if not solo_prueba:
            ninos_aurora = await obtener_ninos_por_horario(fecha_iso, hora)
            for n in ninos_aurora:
                nombre_full = f"{n.get('nombre', '')} {n.get('apellido', '')}".strip()
                apodo = n.get("apodo", "")
                if _match_nombre(nombre_buscar, nombre_full) or (apodo and _match_nombre(nombre_buscar, apodo)):
                    encontrados.append({"nombre": nombre_full, "tabla": "RESERVAS", "record_id": n.get("reserva_id", ""), "hora": hora})

        # Pruebas (solo si ES solo_prueba)
        if solo_prueba:
            pruebas = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_texto}', {{HORA}}='{hora}')", max_records=50)
            pruebas_iso = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_iso}', {{HORA}}='{hora}')", max_records=50)
            _seen = set()
            for p in pruebas + pruebas_iso:
                if p["id"] not in _seen:
                    _seen.add(p["id"])
                    f = p.get("fields", {})
                    if f.get("CONVERSION") == "CANCELADO":
                        continue
                    nombre_full = f"{f.get('NOMBRE HIJO', '')} {f.get('APELLIDO HIJO', '')}".strip()
                    if _match_nombre(nombre_buscar, nombre_full):
                        encontrados.append({"nombre": nombre_full, "tabla": "PRUEBAS", "record_id": p["id"], "hora": hora})

    if not encontrados:
        # No tiene reserva para hoy — buscar en NIÑOS FENIX y crear reserva
        if not solo_prueba:
            from agent.airtable_client import _get_records, _NINOS, obtener_o_crear_horario, crear_reserva
            # Buscar niño por nombre en toda la tabla NIÑOS FENIX
            ninos_all = await _get_records(_NINOS, formula="", max_records=200)
            nino_match = None
            for n in ninos_all:
                f = n.get("fields", {})
                nombre_full = f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip()
                apodo = f.get("APODO", "")
                if _match_nombre(nombre_buscar, nombre_full) or (apodo and _match_nombre(nombre_buscar, apodo)):
                    nino_match = {"id": n["id"], "nombre": nombre_full, "familia": f.get("FAMILIA", [])}
                    break

            if nino_match:
                # Deducir turno actual por hora PY
                hora_py = datetime.now(_PY_TZ).hour
                if hora_py < 11:
                    turno_auto = "9:30"
                elif hora_py < 15:
                    turno_auto = "11:00"
                else:
                    turno_auto = "15:30"

                # Crear horario + reserva
                horario_id = await obtener_o_crear_horario(fecha_iso, turno_auto)
                if horario_id:
                    familia_id = nino_match["familia"][0] if nino_match["familia"] else ""
                    reserva_id = await crear_reserva(nino_match["id"], horario_id, familia_id)
                    if reserva_id:
                        await _patch(_RESERVAS, reserva_id, {"PRESENTE": True})
                        await proveedor.enviar_mensaje(telefono, f"✅ PRESENTE (reserva creada): {nino_match['nombre']} ({turno_auto}h)")
                        logger.info(f"[PRESENTE] Creada reserva + presente: {nino_match['nombre']} {turno_auto}")
                        return

                await proveedor.enviar_mensaje(telefono, f"⚠️ Encontré a {nino_match['nombre']} pero no pude crear la reserva.")
                return

        await proveedor.enviar_mensaje(telefono, f"No encontré a *{nombre_buscar}* en {'PRUEBA FENIX' if solo_prueba else 'NIÑOS FENIX'}.")
        return

    # Marcar PRESENTE en todos los matches
    marcados = []
    for reg in encontrados:
        if reg["record_id"]:
            tabla = _RESERVAS if reg["tabla"] == "RESERVAS" else _PRUEBAS
            await _patch(tabla, reg["record_id"], {"PRESENTE": True})
            marcados.append(f"{reg['nombre']} ({reg['hora']}h)")

    if marcados:
        msg = f"✅ PRESENTE: {', '.join(marcados)}"
    else:
        msg = f"⚠️ Encontré a {nombre_buscar} pero no tiene record_id para marcar."

    await proveedor.enviar_mensaje(telefono, msg)
    logger.info(f"[PRESENTE] Marcado: {marcados}")


async def _enviar_asistencia_automatica(turno: str):
    """Envía la lista de asistencia automáticamente al terminar un turno."""
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    try:
        await _generar_lista_asistencia(admin_phone, turno_especifico=turno)
        logger.info(f"[ASISTENCIA] Lista automática enviada para turno {turno}")
    except Exception as e:
        logger.error(f"[ASISTENCIA] Error enviando lista automática: {e}")


async def _generar_resumen_asistencia(telefono: str, fecha_override=None):
    """
    Genera resumen de quién VINO a clase (PRESENTE=true), por turno.
    Separa inscriptos (Aurora/RESERVAS) y pruebas (Fenix/PRUEBA FENIX).
    Si fecha_override=None, usa el sábado más reciente.
    """
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records, _PRUEBAS, _RESERVAS, _HORARIOS, _NINOS, _BASE_URL, _headers
    import httpx

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        dias_desde_sabado = (hoy.weekday() - 5) % 7
        if dias_desde_sabado == 0 and hoy.weekday() != 5:
            dias_desde_sabado = 7
        sabado = hoy - timedelta(days=dias_desde_sabado)

    fecha_iso = sabado.isoformat()
    _MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
              7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    turnos = ["9:30", "11:00", "15:30"]
    lineas = [f"📋 *ASISTENCIA — SÁB {sabado.day}/{sabado.month}*\n"]

    total_presentes = 0
    total_ausentes = 0
    total_aurora = 0
    total_fenix = 0

    for hora in turnos:
        presentes_turno = []
        ausentes_turno = []

        # ── Inscriptos (RESERVAS FENIX) ── buscar horario → reservas → verificar PRESENTE
        horarios = await _get_records(_HORARIOS, formula=f"AND(DATESTR({{FECHA}})='{fecha_iso}', {{HORA}}='{hora}')", max_records=1)
        if horarios:
            reserva_ids = horarios[0].get("fields", {}).get("RESERVAS FENIX", [])
            async with httpx.AsyncClient() as client:
                for res_id in reserva_ids:
                    try:
                        r = await client.get(f"{_BASE_URL}/{_RESERVAS}/{res_id}", headers=_headers(), timeout=10)
                        if r.status_code != 200:
                            continue
                        res_f = r.json().get("fields", {})
                        presente = res_f.get("PRESENTE", False)
                        nino_ids = res_f.get("NINO", [])
                        for nino_id in nino_ids:
                            rn = await client.get(f"{_BASE_URL}/{_NINOS}/{nino_id}", headers=_headers(), timeout=10)
                            if rn.status_code != 200:
                                continue
                            nf = rn.json().get("fields", {})
                            nombre = (nf.get("APODO") or nf.get("NOMBRE") or "?").strip().split()[0] if (nf.get("APODO") or nf.get("NOMBRE")) else "?"
                            apellido = (nf.get("APELLIDO") or "").strip().split()[0] if nf.get("APELLIDO") else ""
                            nombre_full = f"{nombre} {apellido}".strip()
                            edad = str(nf.get("EDAD", "")) if nf.get("EDAD") else ""
                            edad_str = f" ({edad})" if edad else ""
                            if presente:
                                presentes_turno.append(f"✅ {nombre_full}{edad_str}")
                                total_aurora += 1
                            else:
                                ausentes_turno.append(f"❌ {nombre_full}{edad_str}")
                    except Exception as e:
                        logger.warning(f"[RESUMEN ASIS] Error reserva {res_id}: {e}")

        # ── Pruebas (PRUEBA FENIX) ──
        pruebas = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_texto}', {{HORA}}='{hora}')", max_records=50)
        pruebas_iso = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_iso}', {{HORA}}='{hora}')", max_records=50)
        _seen = set()
        for p in pruebas + pruebas_iso:
            if p["id"] in _seen:
                continue
            _seen.add(p["id"])
            f = p.get("fields", {})
            if f.get("CONVERSION") == "CANCELADO":
                continue
            nombre = (f.get("NOMBRE HIJO") or "?").strip().split()[0] if f.get("NOMBRE HIJO") else "?"
            apellido = (f.get("APELLIDO HIJO") or "").strip().split()[0] if f.get("APELLIDO HIJO") else ""
            nombre_full = f"{nombre} {apellido}".strip()
            edad = f.get("EDAD HIJO", "")
            edad_str = f" ({edad})" if edad else ""
            presente = f.get("PRESENTE", False)
            if presente:
                presentes_turno.append(f"✅ {nombre_full}{edad_str} 🔥")
                total_fenix += 1
            else:
                ausentes_turno.append(f"❌ {nombre_full}{edad_str} 🔥")

        n_presentes = len(presentes_turno)
        n_total = n_presentes + len(ausentes_turno)
        total_presentes += n_presentes
        total_ausentes += len(ausentes_turno)

        if n_total == 0:
            continue

        lineas.append(f"⏰ *{hora}h* — {n_presentes}/{n_total} presentes")
        for l in presentes_turno:
            lineas.append(f"   {l}")
        for l in ausentes_turno:
            lineas.append(f"   {l}")
        lineas.append("")

    if total_presentes == 0 and total_ausentes == 0:
        await proveedor.enviar_mensaje(telefono, f"No hay datos de asistencia para el {sabado.day}/{sabado.month}.")
        return

    lineas.append(f"*TOTAL: {total_presentes} presentes, {total_ausentes} ausentes*")
    lineas.append(f"Aurora: {total_aurora} | Fenix (prueba): {total_fenix}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_prueba(telefono: str, fecha_override=None):
    """
    Dashboard de PRUEBA FENIX para un sábado:
    - Asistencia por turno
    - Total pagos prueba
    - Inscriptos
    - Seguimiento enviado/descartado/pendiente
    """
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records, _PRUEBAS

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        dias_desde_sabado = (hoy.weekday() - 5) % 7
        if dias_desde_sabado == 0 and hoy.weekday() != 5:
            dias_desde_sabado = 7
        sabado = hoy - timedelta(days=dias_desde_sabado)

    fecha_iso = sabado.isoformat()
    _MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
              7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    # Obtener todas las pruebas de esa fecha
    pruebas_t = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_texto}'", max_records=50)
    pruebas_i = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_iso}'", max_records=50)
    _seen = set()
    pruebas = []
    for p in pruebas_t + pruebas_i:
        if p["id"] not in _seen:
            _seen.add(p["id"])
            pruebas.append(p)

    # Filtrar cancelados
    pruebas = [p for p in pruebas if p.get("fields", {}).get("CONVERSION") != "CANCELADO"]

    if not pruebas:
        await proveedor.enviar_mensaje(telefono, f"No hay pruebas para el {sabado.day}/{sabado.month}.")
        return

    # Obtener seguimiento de esa fecha
    seg_records = await _get_records("SEGUIMIENTO FENIX", formula=f"DATESTR({{FECHA}})='{fecha_iso}'", max_records=50)
    # Indexar seguimiento por teléfono
    seg_por_tel = {}
    for s in seg_records:
        sf = s.get("fields", {})
        tel = sf.get("TELEFONO", "")
        if tel:
            seg_por_tel[tel] = sf

    # Leer pagos vinculados de cada prueba
    import httpx
    from agent.airtable_client import _BASE_URL, _headers

    async with httpx.AsyncClient() as _hc:
        for p in pruebas:
            f = p.get("fields", {})
            pagos_ids = f.get("PAGOS", [])
            monto_total = 0
            monto_inscripcion = 0
            for pid in pagos_ids:
                try:
                    r = await _hc.get(f"{_BASE_URL}/PAGOS/{pid}", headers=_headers(), timeout=10)
                    if r.status_code == 200:
                        pf = r.json().get("fields", {})
                        m = pf.get("MONTO", 0) or 0
                        concepto = pf.get("CONCEPTO", "")
                        if "PRUEBA" in concepto:
                            monto_total += m
                        else:
                            monto_inscripcion += m
                except Exception:
                    pass
            f["_monto_prueba"] = monto_total
            f["_monto_inscripcion"] = monto_inscripcion

    # Agrupar por teléfono (familia) y turno
    familias = {}
    for p in pruebas:
        f = p.get("fields", {})
        tel = f.get("TELEFONO", "?")
        hora = (f.get("HORA") or "").strip().replace("h", "").replace("hs", "")
        for t in ["9:30", "11:00", "15:30"]:
            if hora == t or hora == t.split(":")[0] or hora.lstrip("0") == t:
                hora = t
                break
        if hora not in ["9:30", "11:00", "15:30"]:
            hora = "15:30"

        nombre_hijo = (f.get("NOMBRE HIJO") or "?").strip()
        edad = f.get("EDAD HIJO", "")
        presente = f.get("PRESENTE", False)
        conversion = f.get("CONVERSION", "")
        inscripcion = f.get("INSCRIPCION", False)
        nombre_padre = f"{f.get('NOMBRE RESPONSABLE', '')} {f.get('APELLIDO RESPONSABLE', '')}".strip()

        # Si no tiene nombre, buscar en seguimiento (tiene el nombre en el mensaje)
        if not nombre_padre and tel in seg_por_tel:
            _seg_msg = seg_por_tel[tel].get("MENSAJE", "")
            if _seg_msg.startswith("Hola "):
                nombre_padre = _seg_msg.split("!")[0].replace("Hola ", "")

        # Si sigue sin nombre, buscar en LEADS
        if not nombre_padre:
            try:
                _leads = await _get_records("LEADS FENIX", formula=f"{{TELEFONO}}='{tel}'", max_records=1)
                if _leads:
                    _lf = _leads[0].get("fields", {})
                    nombre_padre = _lf.get("NOMBRE RESPONSABLE", "")
            except Exception:
                pass

        if tel not in familias:
            familias[tel] = {
                "padre": nombre_padre,
                "turno": hora,
                "hijos": [],
                "monto_prueba": 0,
                "monto_inscripcion": 0,
                "conversion": conversion,
                "inscripcion": inscripcion,
            }
        familias[tel]["hijos"].append({
            "nombre": nombre_hijo,
            "edad": edad,
            "presente": presente,
        })
        familias[tel]["monto_prueba"] += f.get("_monto_prueba", 0)
        _conv_order = {"CONSULTA": 0, "AGENDA": 1, "PAGO": 2, "INSCRIPTO": 3}
        if _conv_order.get(conversion, 0) > _conv_order.get(familias[tel]["conversion"], 0):
            familias[tel]["conversion"] = conversion
        if inscripcion:
            familias[tel]["inscripcion"] = True
        # Guardar familia_id para buscar pagos de inscripción
        familia_ids = f.get("FAMILIA", [])
        if familia_ids and "familia_id" not in familias[tel]:
            familias[tel]["familia_id"] = familia_ids[0]

    # Buscar pagos de inscripción por familia_id
    # Filtrar por FUENTE=FENIX para no traer pagos de Dorita (base compartida)
    _pagos_fenix = await _get_records("PAGOS", formula="{FUENTE}='FENIX KIDS ACADEMY'", max_records=100)
    for tel, fam in familias.items():
        if (fam["conversion"] == "INSCRIPTO" or fam["inscripcion"]) and fam.get("familia_id"):
            fam_id = fam["familia_id"]
            for pg in _pagos_fenix:
                pf = pg.get("fields", {})
                fam_links = pf.get("FAMILIA FENIX", []) or []
                if fam_id in fam_links:
                    concepto = pf.get("CONCEPTO", "")
                    m = pf.get("MONTO", 0) or 0
                    if "PRUEBA" not in concepto:
                        fam["monto_inscripcion"] += m

    total_ninos = 0
    total_presentes = 0
    total_ausentes = 0
    total_pagaron_prueba = 0
    total_inscriptos = 0
    total_seg_enviado = 0
    total_seg_descartado = 0
    total_seg_pendiente = 0
    monto_prueba_total = 0
    monto_inscripcion_total = 0

    lineas = [f"🔥 *RESUMEN PRUEBA — SÁB {sabado.day}/{sabado.month}*\n"]

    # Agrupar familias por turno
    for hora in ["9:30", "11:00", "15:30"]:
        fams_turno = [(tel, fam) for tel, fam in familias.items() if fam["turno"] == hora]
        if not fams_turno:
            continue

        n_hijos_turno = sum(len(fam["hijos"]) for _, fam in fams_turno)
        lineas.append(f"⏰ *{hora}h* ({n_hijos_turno} niños, {len(fams_turno)} familias)")

        for tel, fam in fams_turno:
            padre = fam["padre"] or tel
            conversion = fam["conversion"]
            monto_pr = fam["monto_prueba"]
            monto_insc = fam["monto_inscripcion"]
            inscripto = fam["inscripcion"] or conversion == "INSCRIPTO"

            # Seguimiento
            seg = seg_por_tel.get(tel, {})
            if seg:
                if seg.get("ENVIADO"):
                    seg_ico = "📩"
                    total_seg_enviado += 1
                elif seg.get("DESCARTADO"):
                    seg_ico = "🚫"
                    total_seg_descartado += 1
                else:
                    seg_ico = "⏳"
                    total_seg_pendiente += 1
            else:
                seg_ico = "⏳"
                total_seg_pendiente += 1

            # Línea padre
            padre_info = f"   *{padre}*"
            if monto_pr > 0:
                padre_info += f" | prueba {monto_pr // 1000}mil"
                total_pagaron_prueba += 1
                monto_prueba_total += monto_pr
            if inscripto:
                total_inscriptos += 1
                padre_info += f" | 🎓 INSCRIPTO"
                if monto_insc > 0:
                    padre_info += f" {monto_insc // 1000}mil"
                    monto_inscripcion_total += monto_insc
            padre_info += f" {seg_ico}"
            lineas.append(padre_info)

            # Líneas hijos
            for h in fam["hijos"]:
                total_ninos += 1
                asis = "✅" if h["presente"] else "❌"
                if h["presente"]:
                    total_presentes += 1
                else:
                    total_ausentes += 1
                edad_str = f" ({h['edad']})" if h["edad"] else ""
                lineas.append(f"      {asis} {h['nombre']}{edad_str}")

        lineas.append("")

    recaudado_total = monto_prueba_total + monto_inscripcion_total

    lineas.append(f"📊 *TOTALES*")
    lineas.append(f"👨‍👩‍👧 Familias: {len(familias)} | Niños: {total_ninos}")
    lineas.append(f"✅ Vinieron: {total_presentes} | ❌ No vinieron: {total_ausentes}")
    lineas.append(f"💰 Pagaron prueba: {total_pagaron_prueba} ({monto_prueba_total // 1000}mil)")
    lineas.append(f"🎓 Inscriptos: {total_inscriptos} ({monto_inscripcion_total // 1000}mil)")
    lineas.append(f"💵 *Recaudado total: {recaudado_total // 1000}mil*")
    lineas.append(f"📩 Seguimiento: {total_seg_enviado} | 🚫 {total_seg_descartado} | ⏳ {total_seg_pendiente}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_seguimiento(telefono: str, fecha_override=None):
    """Resumen de mensajes personalizados: enviados, descartados, pendientes."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        # Último sábado
        dias_desde_sabado = (hoy.weekday() - 5) % 7
        if dias_desde_sabado == 0 and hoy.weekday() != 5:
            dias_desde_sabado = 7
        sabado = hoy - timedelta(days=dias_desde_sabado)

    fecha_iso = sabado.isoformat()
    records = await _get_records("SEGUIMIENTO FENIX", formula=f"DATESTR({{FECHA}})='{fecha_iso}'", max_records=50)

    if not records:
        await proveedor.enviar_mensaje(telefono, f"No hay seguimiento para el {sabado.day}/{sabado.month}.")
        return

    enviados = []
    descartados = []
    pendientes = []

    for r in records:
        f = r.get("fields", {})
        msg = f.get("MENSAJE", "")
        if msg.startswith("Hola "):
            nombre = msg.split("!")[0].replace("Hola ", "")
        else:
            nombre = f.get("TELEFONO", "?")
        turno = f.get("TURNO", "")
        linea = f"{nombre} ({turno})"

        if f.get("ENVIADO"):
            enviados.append(linea)
        elif f.get("DESCARTADO"):
            descartados.append(linea)
        else:
            pendientes.append(linea)

    lineas = [f"📋 *SEGUIMIENTO — SÁB {sabado.day}/{sabado.month}*\n"]

    if enviados:
        lineas.append(f"✅ *Enviados ({len(enviados)}):*")
        for l in enviados:
            lineas.append(f"   {l}")
        lineas.append("")

    if descartados:
        lineas.append(f"❌ *Descartados ({len(descartados)}):*")
        for l in descartados:
            lineas.append(f"   {l}")
        lineas.append("")

    if pendientes:
        lineas.append(f"⏳ *Pendientes ({len(pendientes)}):*")
        for l in pendientes:
            lineas.append(f"   {l}")
        lineas.append("")

    lineas.append(f"*Total: {len(records)}* — ✅{len(enviados)} ❌{len(descartados)} ⏳{len(pendientes)}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_followup(telefono: str):
    """Genera resumen de follow-ups: quién espera respuesta, quién respondió, descartados, pagaron."""
    from datetime import datetime, timezone, timedelta
    from agent.airtable_client import _get_records, _LEADS
    from urllib.parse import quote

    ahora = datetime.now(timezone.utc)
    base_id = os.getenv("AIRTABLE_BASE_ID")
    api_key = os.getenv("AIRTABLE_API_KEY")

    # Traer todos los leads que entraron al sistema de FU (tienen FECHA FOLLOWUP)
    # Incluye CONTACTADO (en proceso) y DESCARTADO (cerrados) y PAGO (convirtieron)
    formula = "NOT({FECHA FOLLOWUP}=BLANK())"
    all_records = []
    offset_fu = None
    import httpx as _httpx_fu
    while True:
        params = f"filterByFormula={quote(formula)}&pageSize=100"
        if offset_fu:
            params += f"&offset={offset_fu}"
        _url = f"https://api.airtable.com/v0/{base_id}/LEADS%20FENIX?{params}"
        async with _httpx_fu.AsyncClient(timeout=15) as _cl:
            _r = await _cl.get(_url, headers={"Authorization": f"Bearer {api_key}"})
            _data = _r.json()
        all_records.extend(_data.get("records", []))
        offset_fu = _data.get("offset")
        if not offset_fu:
            break

    # Clasificar leads
    esperando = []      # FU enviado, esperando respuesta (< 24h)
    respondieron = []   # Respondió al último FU, esperando pago
    descartados = []    # No respondió, ventana cerrada
    pagaron = []        # Pagó post-FU

    for rec in all_records:
        f = rec.get("fields", {})
        tel = f.get("TELEFONO", "")
        nombre_padre = (f.get("NOMBRE RESPONSABLE", "") or "").split()[0] if f.get("NOMBRE RESPONSABLE") else tel[-4:]
        nombre_hijo = f.get("NOMBRE NIÑO", "") or ""
        conversion = f.get("CONVERSION", "")
        seguimientos = f.get("SEGUIMIENTOS", 0) or 0
        respondio_fu1 = f.get("RESPONDIO FU1", False)
        respondio_fu2 = f.get("RESPONDIO FU2", False)
        fecha_fu = f.get("FECHA FOLLOWUP", "")
        pago_post = f.get("PAGO POST FU", 0) or 0

        if not tel:
            continue

        # Calcular horas desde último FU
        horas_desde = 0
        try:
            fecha_ultimo = datetime.fromisoformat(fecha_fu.replace("Z", "+00:00"))
            horas_desde = (ahora - fecha_ultimo).total_seconds() / 3600
        except Exception:
            pass

        label = f"{nombre_padre} ({nombre_hijo})" if nombre_hijo else nombre_padre

        # Clasificar
        if conversion == "PAGO":
            if pago_post or seguimientos >= 1:
                pagaron.append(f"💰 {label} — pagó post FU{seguimientos}")
            continue

        if conversion == "DESCARTADO":
            fu_label = f"FU{seguimientos}" if seguimientos else "FU1"
            descartados.append(f"⛔ {label} — no respondió {fu_label}")
            continue

        # CONTACTADO — en proceso
        if seguimientos == 0:
            # Tiene FECHA FOLLOWUP pero SEGUIMIENTOS=0 → esperando primer FU
            esperando.append(f"⏳ {label} — esperando FU1 ({int(horas_desde)}h)")
            continue

        # Determinar si respondió al último FU
        if seguimientos == 1:
            if respondio_fu1:
                respondieron.append(f"✅ {label} — respondió FU1, esperando pago")
            else:
                esperando.append(f"🟡 {label} — FU1 enviado hace {int(horas_desde)}h")
        elif seguimientos == 2:
            if respondio_fu2:
                respondieron.append(f"✅ {label} — respondió FU2, esperando pago")
            else:
                esperando.append(f"🟡 {label} — FU2 enviado hace {int(horas_desde)}h")
        elif seguimientos >= 3:
            esperando.append(f"🔴 {label} — FU3 enviado hace {int(horas_desde)}h")

    # Armar mensaje
    lineas = ["📊 *RESUMEN FOLLOWUP*\n"]

    if esperando:
        lineas.append(f"🟡 *EN CURSO ({len(esperando)}):*")
        lineas.extend(esperando)
        lineas.append("")

    if respondieron:
        lineas.append(f"✅ *RESPONDIERON ({len(respondieron)}):*")
        lineas.extend(respondieron)
        lineas.append("")

    if pagaron:
        lineas.append(f"💰 *PAGARON POST-FU ({len(pagaron)}):*")
        lineas.extend(pagaron)
        lineas.append("")

    if descartados:
        lineas.append(f"❌ *DESCARTADOS ({len(descartados)}):*")
        lineas.extend(descartados)
        lineas.append("")

    total = len(esperando) + len(respondieron) + len(pagaron) + len(descartados)
    lineas.append(f"📈 *Total en FU: {total}* — ✅{len(respondieron)} 💰{len(pagaron)} ❌{len(descartados)} 🟡{len(esperando)}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


def _fecha_py(iso_str: str) -> str:
    """Convierte un timestamp ISO (UTC o con offset) a fecha PY (YYYY-MM-DD).
    Si solo tiene fecha sin hora, la devuelve tal cual."""
    from datetime import datetime, timezone, timedelta
    _PY_TZ = timezone(timedelta(hours=-3))
    if not iso_str:
        return ""
    try:
        # Intentar parsear como datetime completo
        if "T" in iso_str:
            # fromisoformat maneja offsets como +00:00 y -03:00
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.astimezone(_PY_TZ).date().isoformat()
        # Solo fecha, devolver tal cual
        return iso_str[:10]
    except Exception:
        return iso_str[:10]


async def _generar_resumen_anuncios(telefono: str, texto_cmd: str):
    """Genera y envía resumen de PRUEBA FENIX agrupado por fecha."""
    from datetime import date as _date_cls
    from collections import defaultdict
    import httpx as _httpx_r
    from agent.airtable_client import _get_records

    label, fecha_desde, fecha_hasta = _parsear_filtro_fecha(texto_cmd)

    # Paginar todos los registros de PRUEBA FENIX
    all_records = []
    offset = None
    base_id = os.getenv("AIRTABLE_BASE_ID")
    api_key = os.getenv("AIRTABLE_API_KEY")
    while True:
        params = f"pageSize=100"
        if offset:
            params += f"&offset={offset}"
        _url = f"https://api.airtable.com/v0/{base_id}/PRUEBA%20FENIX?{params}"
        async with _httpx_r.AsyncClient(timeout=15) as _cl:
            _r = await _cl.get(_url, headers={"Authorization": f"Bearer {api_key}"})
            _data = _r.json()
        all_records.extend(_data.get("records", []))
        offset = _data.get("offset")
        if not offset:
            break

    # Filtrar por rango de fechas (convertir UTC → hora PY)
    registros_filtrados = []
    for rec in all_records:
        f = rec.get("fields", {})
        fecha_raw = _fecha_py(f.get("FECHA CREACION", ""))
        if not fecha_raw:
            continue
        if fecha_desde and fecha_raw < fecha_desde:
            continue
        if fecha_hasta and fecha_raw > fecha_hasta:
            continue
        registros_filtrados.append(rec)

    # Contar leads totales por día (LEADS FENIX por FECHA CREACION)
    leads_por_fecha = defaultdict(int)
    _offset_leads = None
    while True:
        _params_l = "pageSize=100&fields%5B%5D=FECHA%20CREACION"
        if _offset_leads:
            _params_l += f"&offset={_offset_leads}"
        _url_l = f"https://api.airtable.com/v0/{base_id}/LEADS%20FENIX?{_params_l}"
        async with _httpx_r.AsyncClient(timeout=15) as _cl:
            _r_l = await _cl.get(_url_l, headers={"Authorization": f"Bearer {api_key}"})
            _data_l = _r_l.json()
        for _rec_l in _data_l.get("records", []):
            _fc_l = _fecha_py(_rec_l.get("fields", {}).get("FECHA CREACION", ""))
            if _fc_l:
                if fecha_desde and _fc_l < fecha_desde:
                    continue
                if fecha_hasta and _fc_l > fecha_hasta:
                    continue
                leads_por_fecha[_fc_l] += 1
        _offset_leads = _data_l.get("offset")
        if not _offset_leads:
            break
    total_leads = sum(leads_por_fecha.values())

    if not registros_filtrados and total_leads == 0:
        await proveedor.enviar_mensaje(telefono, f"📊 RESUMEN ANUNCIOS — {label}\n\nSin datos en este período.")
        return

    # Agrupar por fecha + contar por concepto (solo con monto > 0)
    por_fecha = defaultdict(lambda: {"conceptos": defaultdict(int), "total_monto": 0, "cantidad": 0})
    for rec in registros_filtrados:
        f = rec.get("fields", {})
        fecha_raw = _fecha_py(f.get("FECHA CREACION", ""))
        concepto = f.get("CONCEPTO", "") or "s/concepto"
        monto = f.get("MONTO", 0) or _MONTOS_CONCEPTO.get(concepto, 0)
        if monto > 0:
            por_fecha[fecha_raw]["cantidad"] += 1
            por_fecha[fecha_raw]["total_monto"] += monto
            por_fecha[fecha_raw]["conceptos"][concepto] += 1

    # Totales generales — gasto real desde GASTOS FENIX (fallback 200k/día)
    _GASTO_DEFAULT = 200_000
    gastos_reales = {}
    try:
        _gastos_recs = await _get_records("GASTOS FENIX", max_records=100)
        for _gr in _gastos_recs:
            _gf = _gr.get("fields", {})
            if _gf.get("FECHA"):
                gastos_reales[_gf["FECHA"]] = _gf.get("MONTO", 0) or 0
    except Exception:
        pass
    total_agendados = len(registros_filtrados)
    total_agendado = sum(d["total_monto"] for d in por_fecha.values())
    num_dias = max(len(leads_por_fecha), len(por_fecha))
    # Sumar gasto real por cada día del período
    todas_fechas_gasto = sorted(set(list(leads_por_fecha.keys()) + list(por_fecha.keys())))
    total_gastado = sum(gastos_reales.get(f, _GASTO_DEFAULT) for f in todas_fechas_gasto)
    diferencia = total_agendado - total_gastado
    total_agendado_fmt = f"{total_agendado:,}".replace(",", ".")
    total_gastado_fmt = f"{total_gastado:,}".replace(",", ".")
    diferencia_fmt = f"{diferencia:,}".replace(",", ".")
    signo = "+" if diferencia >= 0 else ""
    pct_global = f"{(total_agendados/total_leads*100):.0f}%" if total_leads else "0%"
    media_agendados_dia = f"{total_agendados/num_dias:.1f}" if num_dias else "0"
    media_monto_dia = f"{total_agendado//num_dias:,}".replace(",", ".") if num_dias else "0"

    lineas = [
        f"📊 RESUMEN ANUNCIOS — {label}",
        f"🌟 Leads: {total_leads} | {total_agendados} agendados | {pct_global} | {media_agendados_dia}/día",
        f"✅ {total_agendado_fmt} Gs | {media_monto_dia}/día",
        "",
    ]

    # Todas las fechas (leads + agendados)
    todas_fechas = sorted(set(list(leads_por_fecha.keys()) + list(por_fecha.keys())), reverse=True)
    for fecha_iso in todas_fechas:
        d = por_fecha.get(fecha_iso, {"conceptos": defaultdict(int), "total_monto": 0, "cantidad": 0})
        leads_dia = leads_por_fecha.get(fecha_iso, 0)
        # Formato: DOM 4/5
        try:
            _fd = _date_cls.fromisoformat(fecha_iso)
            dia_sem = _DIAS_SEMANA[_fd.weekday()]
            fecha_label = f"{dia_sem} {_fd.day}/{_fd.month}"
        except Exception:
            fecha_label = fecha_iso
        pct_dia = f"{(d['cantidad']/leads_dia*100):.0f}%" if leads_dia else "0%"
        monto_dia = f"{d['total_monto']:,}".replace(",", ".")
        _gasto_este_dia = gastos_reales.get(fecha_iso, _GASTO_DEFAULT)
        gasto_dia_fmt = f"{_gasto_este_dia:,}".replace(",", ".")
        lineas.append("")
        lineas.append(f"📅 {fecha_label} — {leads_dia} leads")
        if d["cantidad"]:
            lineas.append(f"✅ {d['cantidad']} agendados | {pct_dia}")
            lineas.append(f"🔔 Total: {monto_dia} Gs (gasto: {gasto_dia_fmt})")
            # Desglose por concepto
            desglose = [f"{c}: {n}" for c, n in sorted(d["conceptos"].items()) if n > 0]
            if desglose:
                lineas.append(f"   💵 {' | '.join(desglose)}")
        else:
            lineas.append(f"✅ 0 agendados")

    # Separar pagos por tipo
    _total_pruebas = 0
    _total_fenixmama = 0
    for rec in registros_filtrados:
        f = rec.get("fields", {})
        monto = f.get("MONTO", 0) or _MONTOS_CONCEPTO.get(f.get("CONCEPTO", ""), 0)
        concepto = f.get("CONCEPTO", "")
        if monto > 0:
            if concepto == "FENIXMAMA":
                _total_fenixmama += monto
            else:
                _total_pruebas += monto
    _total_pruebas_fmt = f"{_total_pruebas:,}".replace(",", ".")
    _total_fenixmama_fmt = f"{_total_fenixmama:,}".replace(",", ".")

    # Inscriptos + monto PLAN
    _inscriptos = [r for r in all_records if r.get("fields", {}).get("CONVERSION") == "INSCRIPTO"]
    _total_inscriptos = len(_inscriptos)
    _total_plan = sum(r.get("fields", {}).get("PLAN", 0) or 0 for r in _inscriptos)
    _total_plan_fmt = f"{_total_plan:,}".replace(",", ".")

    # Total recaudado
    _total_recaudado = _total_pruebas + _total_fenixmama + _total_plan
    _total_recaudado_fmt = f"{_total_recaudado:,}".replace(",", ".")
    _diferencia_real = _total_recaudado - total_gastado
    _dif_real_fmt = f"{_diferencia_real:,}".replace(",", ".")
    _signo_real = "+" if _diferencia_real >= 0 else ""

    # Totales finales
    lineas.append("")
    lineas.append(f"💰 *Pagos:*")
    lineas.append(f"   🔥 Pruebas: {_total_pruebas_fmt} Gs")
    lineas.append(f"   🎁 Fenixmama: {_total_fenixmama_fmt} Gs")
    lineas.append(f"   🏆 Plan inscriptos ({_total_inscriptos}): {_total_plan_fmt} Gs")
    lineas.append(f"💵 *Total recaudado: {_total_recaudado_fmt} Gs*")
    lineas.append(f"📢 Total anuncios ({num_dias} días): {total_gastado_fmt} Gs")
    lineas.append(f"{'✅' if _diferencia_real >= 0 else '🔴'} Diferencia: {_signo_real}{_dif_real_fmt} Gs")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))
