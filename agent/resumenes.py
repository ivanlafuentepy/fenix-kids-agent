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
# Montos viejos por concepto: eliminado. El campo MONTO de cada pago ya trae el valor real.


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


async def _tutor_de_familia(familia_id: str) -> tuple[str, str]:
    """(nombre, telefono) del tutor de contacto de una FAMILIA (madre primero).
    Devuelve ("", "") si falla — los resúmenes nunca se rompen por esto."""
    if not familia_id:
        return "", ""
    try:
        from agent.airtable_client import _BASE_URL, _headers
        import httpx
        async with httpx.AsyncClient() as _cl:
            _r = await _cl.get(f"{_BASE_URL}/FAMILIAS%20FENIX/{familia_id}", headers=_headers(), timeout=10)
            if _r.status_code == 200:
                _ff = _r.json().get("fields", {})
                if _ff.get("CELL MADRE"):
                    return f"{_ff.get('NOMBRE MADRE', '')} {_ff.get('APELLIDO MADRE', '')}".strip(), _ff["CELL MADRE"]
                if _ff.get("CELL PADRE"):
                    return f"{_ff.get('NOMBRE PADRE', '')} {_ff.get('APELLIDO PADRE', '')}".strip(), _ff["CELL PADRE"]
    except Exception:
        pass
    return "", ""


async def _generar_resumen_reservas(telefono: str, fecha_override=None):
    """Genera resumen de reservas de un sábado, agrupado por turno.
    Si fecha_override es None, usa el sábado más cercano.
    Separa AURORA (inscriptos) y FENIX (prueba) por es_prueba — fuente única
    RESERVAS FENIX (migración 2.B: PRUEBA FENIX ya no se consulta)."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario

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
    fecha_label = f"{_DIAS[sabado.weekday()]} {sabado.day}/{sabado.month}"

    turnos = ["9:30", "11:00", "15:30"]

    # ── Fuente única: RESERVAS FENIX (inscriptos + pruebas, split por es_prueba) ──
    aurora_por_turno: dict[str, list[dict]] = {}
    fenix_por_turno: dict[str, list[dict]] = {}
    for hora in turnos:
        ninos = await obtener_ninos_por_horario(fecha_iso, hora)
        aurora_por_turno[hora] = [n for n in ninos if not n.get("es_prueba")]
        fenix_por_turno[hora] = [n for n in ninos if n.get("es_prueba")]

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

    # Fuente única: RESERVAS FENIX — inscriptos y pruebas juntos, marcados
    # por es_prueba (migración 2.B). Padre/teléfono salen de la FAMILIA
    # también para los de prueba (existe por el dual-write al pagar).
    ninos_por_turno: dict[str, list[dict]] = {}
    for hora in turnos:
        ninos_por_turno[hora] = await obtener_ninos_por_horario(fecha_iso, hora)

    # Armar mensaje
    emojis = ["🦁", "🐯", "🦊", "🐻", "🐼", "🦋", "🌟", "⚡", "🔥", "🎯", "🦅", "🐺", "🌈", "🎪", "🏆", "🦈", "🐉", "🦖", "🌵", "🎸"]
    lineas = [f"👨‍👩‍👧‍👦 *FAMILIAS — {fecha_label}*\n"]
    total = 0
    _emoji_idx = 0

    for hora in turnos:
        ninos = ninos_por_turno[hora]
        total += len(ninos)

        lineas.append(f"⏰ *{hora}h* — {len(ninos)}")

        for n in ninos:
            emoji = emojis[_emoji_idx % len(emojis)]
            _emoji_idx += 1
            nombre_hijo = (n.get("apodo") or n["nombre"]).split()[0]
            _padre_nombre, _tel_padre = await _tutor_de_familia(n.get("familia_id", ""))
            _marca = " 🔥" if n.get("es_prueba") else ""
            lineas.append(f"  {emoji} {nombre_hijo}{_marca} | {_padre_nombre}")
            if _tel_padre:
                lineas.append(f"      wa.me/{_tel_padre}")

        if not ninos:
            lineas.append("   — vacio")
        lineas.append("")

    lineas.append(f"*Total: {total}*")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_telegram(telefono: str):
    """Genera resumen de las clases de PRUEBA del sábado con link de Telegram
    por familia. Fuente: RESERVAS FENIX con es_prueba (migración 2.B) — el
    teléfono y el responsable salen de la FAMILIA; hermanos se agrupan por
    familia_id. Los cancelados ya no aparecen (la reserva se borra al cancelar)."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario
    from agent.telegram_bridge import obtener_topic

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    dias_hasta_sabado = (5 - hoy.weekday()) % 7
    if dias_hasta_sabado == 0 and hoy.weekday() != 5:
        dias_hasta_sabado = 7
    sabado = hoy + timedelta(days=dias_hasta_sabado)
    fecha_iso = sabado.isoformat()

    turnos = ["9:30", "11:00", "15:30"]

    lineas = [f"📋 *RESERVAS + TELEGRAM — SAB {sabado.day}/{sabado.month}*\n"]
    total = 0

    for hora in turnos:
        ninos = await obtener_ninos_por_horario(fecha_iso, hora)
        kids = [n for n in ninos if n.get("es_prueba")]

        # Agrupar hermanos por familia
        by_fam: dict[str, dict] = {}
        for k in kids:
            fam_id = k.get("familia_id", "") or f"_sin_fam_{k['id']}"
            if fam_id not in by_fam:
                by_fam[fam_id] = {"nombres": [], "familia_id": k.get("familia_id", "")}
            by_fam[fam_id]["nombres"].append(f"{k['nombre']} {k['apellido']}".strip())

        count = len(kids)
        total += count
        lineas.append(f"⏰ *{hora}h* — {count} niño{'s' if count != 1 else ''}")

        for fam_id, data in by_fam.items():
            responsable, tel = await _tutor_de_familia(data["familia_id"])
            # Link al topic de Telegram de esa conversación
            topic = await obtener_topic(tel) if tel else None
            if topic and topic.group_id:
                gid = str(topic.group_id).replace("-100", "", 1)
                tg_link = f"https://t.me/c/{gid}/{topic.topic_id}"
            elif topic:
                tg_link = f"topic:{topic.topic_id}"
            else:
                tg_link = "sin topic"

            for nombre in data["nombres"]:
                lineas.append(f"   - {nombre}")
            if responsable:
                lineas.append(f"     👤 {responsable}")
            lineas.append(f"     💬 {tg_link}")
            lineas.append("")

        if not kids:
            lineas.append("   — vacío")
            lineas.append("")

    lineas.append(f"👧👦 *Total: {total}*")
    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_lista_asistencia(telefono: str, turno_especifico: str = ""):
    """Genera lista numerada de niños para pasar asistencia. Guarda estado en
    _asistencia_pendiente. Fuente única: RESERVAS FENIX — los de prueba vienen
    marcados con es_prueba (🔥) (migración 2.B, PRUEBA FENIX ya no se consulta)."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    # Si es sábado, usar hoy. Si no, buscar el sábado más cercano pasado (para control post-clase)
    if hoy.weekday() == 5:
        sabado = hoy
    else:
        # Último sábado
        sabado = hoy - timedelta(days=(hoy.weekday() + 2) % 7)

    fecha_iso = sabado.isoformat()

    turnos = [turno_especifico] if turno_especifico else ["9:30", "11:00", "15:30"]
    registros = []  # lista global numerada
    lineas = [f"✅ *ASISTENCIA — SAB {sabado.day}/{sabado.month}*\n"]

    for hora in turnos:
        ninos = await obtener_ninos_por_horario(fecha_iso, hora)
        if not ninos:
            continue

        lineas.append(f"⏰ *{hora}h* ({len(ninos)})")

        for n in ninos:
            idx = len(registros) + 1
            _n_parts = (n.get("apodo") or n.get("nombre", "?")).split()
            nombre = _n_parts[0] if _n_parts else "?"
            _a_parts = (n.get("apellido") or "").split()
            apellido = _a_parts[0] if _a_parts else ""
            nombre_full = f"{nombre} {apellido}".strip()
            registros.append({"idx": idx, "nombre": nombre_full, "tabla": "RESERVAS",
                              "record_id": n.get("reserva_id", ""), "nino_id": n.get("id", "")})
            _fuego = " 🔥" if n.get("es_prueba") else ""
            # Indicador de asistencia ya cargada
            _mark = ""
            if n.get("presente"):
                _mark = " ✅"
            elif n.get("ausente"):
                _mark = " ❌"
            lineas.append(f"   {idx}. {nombre_full}{_fuego}{_mark}")

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
    """Procesa la respuesta de asistencia: 'ok' o '5 7' (ausentes).
    Todos los registros viven en RESERVAS FENIX (migración 2.B)."""
    from agent.airtable_client import _patch, _RESERVAS

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
        if reg.get("record_id"):
            await _patch(_RESERVAS, reg["record_id"], campos_update)

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
    Deduce el turno de la asistencia pendiente. Busca SOLO en NIÑOS FENIX
    (migración 2.B: los de prueba también existen ahí por el dual-write).
    """
    from datetime import datetime, timezone, timedelta
    from agent.airtable_client import _get_records, _NINOS, _patch, _RESERVAS, obtener_o_crear_horario, crear_reserva
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
            resultados.append(f"❌ {nombre_buscar} (no encontrado en NIÑOS FENIX)")

    # No limpiar asistencia pendiente — permite seguir agregando
    msg = f"📋 Asistencia extra ({turno}h):\n" + "\n".join(resultados)
    await proveedor.enviar_mensaje(telefono, msg)
    logger.info(f"[ASISTENCIA+] {resultados}")


async def _marcar_presente_por_nombre(telefono: str, nombre_buscar: str):
    """Marca PRESENTE=true para un niño buscado por nombre en las RESERVAS del
    sábado (inscriptos Y pruebas — migración 2.B, fuente única). Si no tiene
    reserva, lo busca en NIÑOS FENIX y le crea reserva + presente."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario, _patch, _RESERVAS
    import unicodedata

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    # Si es sábado, usar hoy. Si no, último sábado
    if hoy.weekday() == 5:
        sabado = hoy
    else:
        sabado = hoy - timedelta(days=(hoy.weekday() + 2) % 7)

    fecha_iso = sabado.isoformat()

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
        ninos_hora = await obtener_ninos_por_horario(fecha_iso, hora)
        for n in ninos_hora:
            nombre_full = f"{n.get('nombre', '')} {n.get('apellido', '')}".strip()
            apodo = n.get("apodo", "")
            if _match_nombre(nombre_buscar, nombre_full) or (apodo and _match_nombre(nombre_buscar, apodo)):
                encontrados.append({"nombre": nombre_full, "record_id": n.get("reserva_id", ""),
                                    "hora": hora, "es_prueba": n.get("es_prueba", False)})

    if not encontrados:
        # No tiene reserva para hoy — buscar en NIÑOS FENIX y crear reserva
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

        await proveedor.enviar_mensaje(telefono, f"No encontré a *{nombre_buscar}* en NIÑOS FENIX.")
        return

    # Marcar PRESENTE en todos los matches
    marcados = []
    for reg in encontrados:
        if reg["record_id"]:
            await _patch(_RESERVAS, reg["record_id"], {"PRESENTE": True})
            _f = " 🔥" if reg.get("es_prueba") else ""
            marcados.append(f"{reg['nombre']}{_f} ({reg['hora']}h)")

    if marcados:
        msg = f"✅ PRESENTE: {', '.join(marcados)}"
    else:
        msg = f"⚠️ Encontré a {nombre_buscar} pero no tiene record_id para marcar."

    await proveedor.enviar_mensaje(telefono, msg)
    logger.info(f"[PRESENTE] Marcado: {marcados}")


async def _enviar_asistencia_automatica(turno: str):
    """Envía la lista de asistencia automáticamente al terminar un turno."""
    admin_phone = os.getenv("ADMIN_PHONE", "")
    try:
        await _generar_lista_asistencia(admin_phone, turno_especifico=turno)
        logger.info(f"[ASISTENCIA] Lista automática enviada para turno {turno}")
    except Exception as e:
        logger.error(f"[ASISTENCIA] Error enviando lista automática: {e}")


async def _generar_resumen_asistencia(telefono: str, fecha_override=None):
    """
    Genera resumen de quién VINO a clase (PRESENTE=true), por turno.
    Fuente única: RESERVAS FENIX via obtener_ninos_por_horario — inscriptos
    y pruebas juntos, split por es_prueba (migración 2.B).
    Si fecha_override=None, usa el sábado más reciente.
    """
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario

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

    turnos = ["9:30", "11:00", "15:30"]
    lineas = [f"📋 *ASISTENCIA — SÁB {sabado.day}/{sabado.month}*\n"]

    total_presentes = 0
    total_ausentes = 0
    total_aurora = 0
    total_fenix = 0

    for hora in turnos:
        presentes_turno = []
        ausentes_turno = []

        ninos = await obtener_ninos_por_horario(fecha_iso, hora)
        for n in ninos:
            nombre = (n.get("apodo") or n.get("nombre") or "?").strip().split()[0]
            apellido = (n.get("apellido") or "").strip().split()[0] if n.get("apellido") else ""
            nombre_full = f"{nombre} {apellido}".strip()
            edad_str = f" ({n['edad']})" if n.get("edad") else ""
            fuego = " 🔥" if n.get("es_prueba") else ""
            if n.get("presente"):
                presentes_turno.append(f"✅ {nombre_full}{edad_str}{fuego}")
                if n.get("es_prueba"):
                    total_fenix += 1
                else:
                    total_aurora += 1
            else:
                ausentes_turno.append(f"❌ {nombre_full}{edad_str}{fuego}")

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
        monto = f.get("MONTO", 0)
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
        monto = f.get("MONTO", 0)
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
