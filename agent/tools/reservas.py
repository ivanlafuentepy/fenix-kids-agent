# agent/tools/reservas.py — Acciones sobre clases de prueba
# Busca PRUEBA FENIX en Airtable para reagendar y confirmar reservas.

import os
import re
import logging
from datetime import date

logger = logging.getLogger("agentkit")

_HORARIOS_VALIDOS = {"11:00", "15:30"}


async def reagendar_clase(telefono: str, hora_nueva: str | None = None, **kwargs) -> dict:
    """
    Reagenda clase de prueba. Busca registros en PRUEBA FENIX por teléfono.

    Si hora_nueva se especifica y es válida → actualiza en Airtable.
    Si no → retorna las reservas actuales para que Claude pregunte.
    """
    from agent.airtable_client import _get_records, _patch, _PRUEBAS

    pruebas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{telefono}'", max_records=10)

    if not pruebas:
        return {
            "texto": "No encontré una reserva de clase de prueba para este número.",
            "reagendado": False,
        }

    # Armar info de reservas actuales
    reservas_info = []
    for pr in pruebas:
        f = pr.get("fields", {})
        reservas_info.append({
            "record_id": pr["id"],
            "hijo": f.get("NOMBRE HIJO", "?"),
            "fecha": f.get("FECHA RESERVA", "?"),
            "hora": f.get("HORA", "?"),
        })

    hora_actual = reservas_info[0]["hora"] if reservas_info else "?"

    # Si no especificó hora → retornar reservas actuales + opciones
    if not hora_nueva:
        opciones = sorted(h for h in _HORARIOS_VALIDOS if h != hora_actual)
        info_txt = "\n".join(f"• {r['hijo']} → {r['fecha']} {r['hora']}" for r in reservas_info)
        return {
            "reservas_actuales": info_txt,
            "horarios_disponibles": opciones,
            "reagendado": False,
            "texto": f"Reserva actual:\n{info_txt}\n\nHorarios disponibles: {' | '.join(opciones)}",
        }

    # Validar hora
    if hora_nueva not in _HORARIOS_VALIDOS:
        return {
            "texto": f"Horario no válido. Los horarios son: {' | '.join(sorted(_HORARIOS_VALIDOS))}",
            "reagendado": False,
        }

    # Si ya tiene esa hora → no hacer nada
    if hora_nueva == hora_actual:
        return {
            "texto": f"Ya está reservado a las {hora_nueva}h, no hay cambio.",
            "reagendado": False,
        }

    # Actualizar TODOS los registros en Airtable
    hijos_reagendados = []
    for r in reservas_info:
        await _patch(_PRUEBAS, r["record_id"], {"HORA": hora_nueva})
        hijos_reagendados.append(r["hijo"])
        logger.info(f"[REAGENDAR-TOOL] {r['hijo']} ({telefono}): {r['hora']} → {hora_nueva}")

    hijos_txt = ", ".join(hijos_reagendados)

    # Notificar admin por WhatsApp
    nombre_resp = pruebas[0].get("fields", {}).get("NOMBRE", "?")
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    notificacion_admin = {
        "enviar_admin": True,
        "mensaje_admin": (
            f"🔄 REAGENDAMIENTO\n"
            f"👤 {nombre_resp}\n"
            f"👧 {hijos_txt}\n"
            f"❌ De: {hora_actual}\n"
            f"✅ A: {hora_nueva}\n"
            f"📱 https://wa.me/{telefono}"
        ),
    }

    return {
        "texto": f"Listo! Cambié a las {hora_nueva}h ✅ — {hijos_txt}",
        "reagendado": True,
        "hora_anterior": hora_actual,
        "hora_nueva": hora_nueva,
        "hijos": hijos_txt,
        **notificacion_admin,
    }


def _parsear_fecha(fecha_texto: str) -> str | None:
    """
    Intenta convertir texto de fecha a formato ISO (YYYY-MM-DD).
    Acepta: '2026-05-31', '31 de mayo', 'sábado 31', '31/5', '31/05/2026'.
    Retorna None si no puede parsear.
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime

    hoy = datetime.now(ZoneInfo("America/Asuncion")).date()

    # Ya es ISO
    try:
        return date.fromisoformat(fecha_texto).isoformat()
    except (ValueError, TypeError):
        pass

    # "31/5" o "31/05/2026"
    m = re.match(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?", fecha_texto)
    if m:
        dia, mes = int(m.group(1)), int(m.group(2))
        anio = int(m.group(3)) if m.group(3) else hoy.year
        try:
            return date(anio, mes, dia).isoformat()
        except ValueError:
            pass

    # "31 de mayo", "sábado 31 de mayo"
    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)", fecha_texto.lower())
    if m and m.group(2) in meses:
        dia, mes = int(m.group(1)), meses[m.group(2)]
        try:
            d = date(hoy.year, mes, dia)
            if d < hoy:
                d = date(hoy.year + 1, mes, dia)
            return d.isoformat()
        except ValueError:
            pass

    # "sábado 31" (sin mes — asumir mes actual o siguiente)
    m = re.search(r"(\d{1,2})", fecha_texto)
    if m:
        dia = int(m.group(1))
        try:
            d = date(hoy.year, hoy.month, dia)
            if d < hoy:
                mes_sig = hoy.month + 1 if hoy.month < 12 else 1
                anio_sig = hoy.year if hoy.month < 12 else hoy.year + 1
                d = date(anio_sig, mes_sig, dia)
            return d.isoformat()
        except ValueError:
            pass

    return None


async def confirmar_reserva_prueba(telefono: str, fecha: str, hora: str, **kwargs) -> dict:
    """
    Confirma o crea una reserva de clase de prueba en PRUEBA FENIX.

    Si ya existe registro para este teléfono → actualiza fecha y hora.
    Si no existe → retorna error (el lead necesita pasar por el flujo primero).
    """
    from agent.airtable_client import _get_records, _patch, _PRUEBAS

    # Validar hora
    if hora not in _HORARIOS_VALIDOS:
        return {
            "texto": f"Horario no válido. Los horarios son: {' | '.join(sorted(_HORARIOS_VALIDOS))}",
            "confirmada": False,
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": f"Hora '{hora}' no es válida. Opciones: 9:30, 11:00, 15:30.",
        }

    # Parsear fecha
    fecha_iso = _parsear_fecha(fecha)
    if not fecha_iso:
        return {
            "texto": f"No pude entender la fecha '{fecha}'. Usá formato como '31 de mayo' o '2026-05-31'.",
            "confirmada": False,
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": f"Fecha '{fecha}' no se pudo parsear.",
        }

    # Verificar que sea sábado
    d = date.fromisoformat(fecha_iso)
    if d.weekday() != 5:
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        return {
            "texto": f"El {fecha_iso} es {dias[d.weekday()]}, no sábado. Las clases son solo los sábados.",
            "confirmada": False,
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": f"La fecha {fecha_iso} no es sábado.",
        }

    # Buscar registros existentes
    pruebas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{telefono}'", max_records=10)

    if not pruebas:
        return {
            "texto": "No encontré un registro de prueba para este número. El padre necesita completar el flujo primero.",
            "confirmada": False,
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No hay registro PRUEBA FENIX para este teléfono.",
        }

    # Actualizar fecha y hora en todos los registros
    meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    fecha_display = f"sábado {d.day} de {meses_es[d.month - 1]}"

    hijos_confirmados = []
    for pr in pruebas:
        f = pr.get("fields", {})
        await _patch(_PRUEBAS, pr["id"], {"FECHA RESERVA": fecha_iso, "HORA": hora})
        hijos_confirmados.append(f.get("NOMBRE HIJO", "?"))
        logger.info(f"[CONFIRMAR-TOOL] {f.get('NOMBRE HIJO', '?')} ({telefono}): {fecha_iso} {hora}")

    hijos_txt = ", ".join(hijos_confirmados)
    nombre_resp = pruebas[0].get("fields", {}).get("NOMBRE", "?")

    # Notificar admin
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    notificacion_admin = {
        "enviar_admin": True,
        "mensaje_admin": (
            f"✅ RESERVA CONFIRMADA\n"
            f"👤 {nombre_resp}\n"
            f"👧 {hijos_txt}\n"
            f"📅 {fecha_display} a las {hora}h\n"
            f"📱 https://wa.me/{telefono}"
        ),
    }

    return {
        "texto": f"Reserva confirmada ✅ {hijos_txt} el {fecha_display} a las {hora}h",
        "confirmada": True,
        "fecha": fecha_iso,
        "fecha_display": fecha_display,
        "hora": hora,
        "hijos": hijos_txt,
        **notificacion_admin,
    }
