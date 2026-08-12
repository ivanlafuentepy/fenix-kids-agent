# agent/tools/reservas.py — Acciones sobre clases de prueba
# Confirma y reagenda sobre RESERVAS FENIX (migración 2.C: PRUEBA FENIX ya no
# se lee ni se escribe acá; la reserva actual sale de los links del niño).

import os
import re
import logging
from datetime import date

logger = logging.getLogger("agentkit")

_HORARIOS_VALIDOS = {"11:00", "15:30"}


def _horarios_de(fecha_iso: str | None) -> tuple[str, ...]:
    """Los horarios que corren ESE día — un feriado puede tener uno solo.

    Sin fecha se devuelve el conjunto general: no hay forma de saber qué corre.
    """
    base = tuple(sorted(_HORARIOS_VALIDOS))
    if not fecha_iso:
        return base
    from agent.desafio import turnos_de
    return turnos_de(fecha_iso, base)


async def gestionar_prueba(
    telefono: str,
    accion: str,
    fecha: str | None = None,
    hora: str | None = None,
    **kwargs,
) -> dict:
    """
    Tool unificada para confirmar y reagendar clases de prueba.
    - confirmar: confirma prueba con fecha y hora
    - reagendar: busca prueba actual en Airtable, cambia fecha/hora
    """
    accion = accion.lower().strip()

    if accion == "confirmar":
        if not fecha or not hora:
            return {
                "error": True,
                "error_category": "validation",
                "is_retryable": True,
                "message": "Necesito fecha y hora para confirmar la prueba.",
            }
        return await confirmar_reserva_prueba(telefono, fecha, hora)

    elif accion == "reagendar":
        return await reagendar_clase(telefono, hora_nueva=hora, fecha_nueva=fecha)

    else:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"Acción '{accion}' no válida. Usar: confirmar, reagendar.",
        }


async def reagendar_clase(telefono: str, hora_nueva: str | None = None, fecha_nueva: str | None = None, **kwargs) -> dict:
    """
    Reagenda la clase de prueba sobre RESERVAS FENIX (migración 2.C: la tabla
    PRUEBA FENIX ya no se lee ni se escribe acá). Las reservas actuales salen
    de los links del niño (grupo familiar niño-eje) y el reagendamiento real lo
    hace gestionar_reserva (crea la nueva ANTES de borrar la vieja, A9).

    Si hora/fecha nuevas vienen → reagenda. Si no → retorna las reservas
    actuales para que Claude pregunte.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from agent.airtable_client import obtener_grupo_familiar, _get_records, _RESERVAS

    # Reservas futuras actuales por los links RESERVAS FENIX de los hijos
    grupo = await obtener_grupo_familiar(telefono)
    reservas_info: list[dict] = []
    if grupo:
        _hoy = datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()
        _rids = [rid for h in grupo["hijos"] for rid in (h.get("reserva_ids") or [])][-60:]
        if _rids:
            _or = ",".join(f"RECORD_ID()='{rid}'" for rid in _rids)
            _formula = f"OR({_or})" if len(_rids) > 1 else _or
            for r in await _get_records(_RESERVAS, formula=_formula, max_records=len(_rids)):
                f = r.get("fields", {})
                _f = f.get("FECHA", "")
                _f = (_f[0] if _f else "") if isinstance(_f, list) else _f
                if _f < _hoy:
                    continue
                _h = f.get("HORA", "")
                _h = (_h[0] if _h else "") if isinstance(_h, list) else _h
                _n = f.get("NOMBRE COMPLETO", "")
                _n = (_n[0] if _n else "?") if isinstance(_n, list) else (_n or "?")
                reservas_info.append({"record_id": r["id"], "hijo": _n, "fecha": _f, "hora": _h})

    if not reservas_info:
        return {
            "texto": "No encontré una reserva de clase de prueba para este número.",
            "reagendado": False,
        }

    reservas_info.sort(key=lambda r: r["fecha"])
    hora_actual = reservas_info[0]["hora"]
    fecha_actual = reservas_info[0]["fecha"]

    # Si no especificó NI hora NI fecha → retornar reservas actuales + opciones
    # (antes exigía hora: "pasanos al sábado 11, mismo horario" era imposible
    # de reagendar — auditoría 04-07-26 A14)
    if not hora_nueva and not fecha_nueva:
        opciones = [h for h in _horarios_de(fecha_actual) if h != hora_actual]
        info_txt = "\n".join(f"• {r['hijo']} → {r['fecha']} {r['hora']}" for r in reservas_info)
        return {
            "reservas_actuales": info_txt,
            "horarios_disponibles": opciones,
            "reagendado": False,
            "texto": f"Reserva actual:\n{info_txt}\n\nHorarios disponibles: {' | '.join(opciones)}",
        }

    # Validar hora (solo si vino: puede reagendar cambiando solo la fecha).
    # Contra los turnos del día destino: un feriado corre con uno solo.
    _validos = _horarios_de(_parsear_fecha(fecha_nueva) if fecha_nueva else fecha_actual)
    if hora_nueva and hora_nueva not in _validos:
        return {
            "texto": f"Horario no válido. Los horarios de ese día son: {' | '.join(_validos)}",
            "reagendado": False,
        }

    # Misma hora Y sin fecha nueva → no hay nada que cambiar.
    # (Antes este early-return ignoraba fecha_nueva: "mismo horario, otro
    # sábado" respondía "no hay cambio" y dejaba la fecha vieja — A14.)
    if hora_nueva == hora_actual and not fecha_nueva:
        return {
            "texto": f"Ya está reservado a las {hora_nueva}h, no hay cambio.",
            "reagendado": False,
        }

    # Fecha/hora destino: la nueva si vino, si no la actual (solo-fecha o solo-hora)
    _fecha_real = _parsear_fecha(fecha_nueva) if fecha_nueva else fecha_actual
    _hora_real = hora_nueva or hora_actual
    if not _fecha_real:
        return {
            "texto": f"No pude entender la fecha '{fecha_nueva}'. Usá formato como '31 de mayo' o '2026-05-31'.",
            "reagendado": False,
        }

    # Reagendar en RESERVAS (crea antes de borrar); si no había previa, agenda.
    from agent.tools.agenda import gestionar_reserva
    res = await gestionar_reserva(telefono, "reagendar", fecha=_fecha_real, hora=_hora_real)
    if res.get("error"):
        res = await gestionar_reserva(telefono, "agendar", fecha=_fecha_real, hora=_hora_real)
    if res.get("error"):
        return {
            "texto": "No pude reagendar la reserva. " + (res.get("message") or ""),
            "reagendado": False,
            "error": True,
            "error_category": res.get("error_category", "business"),
            "is_retryable": res.get("is_retryable", True),
            "message": res.get("message", "No se pudo reagendar."),
        }

    _reserva_ids = res.get("reserva_ids", [])
    await _vincular_reservas_lead(telefono, _reserva_ids)
    hijos_txt = res.get("hijos", "?")

    # Notificar admin por WhatsApp
    _tuts = (grupo or {}).get("tutores") or []
    nombre_resp = (_tuts[0].get("nombre", "?") if _tuts else "?")
    notificacion_admin = {
        "enviar_admin": True,
        "mensaje_admin": (
            f"🔄 REAGENDAMIENTO\n"
            f"👤 {nombre_resp}\n"
            f"👧 {hijos_txt}\n"
            f"❌ De: {fecha_actual} {hora_actual}\n"
            f"✅ A: {_fecha_real} {_hora_real}\n"
            f"📱 https://wa.me/{telefono}"
        ),
    }

    return {
        "texto": f"Listo! Reserva actualizada ✅ — {hijos_txt} → {_fecha_real} {_hora_real}h",
        "reagendado": True,
        "hora_anterior": hora_actual,
        "hora_nueva": _hora_real,
        "hijos": hijos_txt,
        "reserva_ids": _reserva_ids,
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


async def _crear_reserva_real(telefono: str, fecha_iso: str, hora: str, reagendar: bool = False) -> None:
    """A1 (migración) — crea/reagenda la RESERVA FENIX real para la familia del lead en prueba.

    La familia ya existe (dual-write al pagar + migración histórica). Aislado en
    try/except: nunca rompe la confirmación al padre. Reusa la maquinaria de
    agenda.py (resuelve familia por teléfono y crea una RESERVA por cada hijo,
    idempotente).
    """
    try:
        from agent.tools.agenda import gestionar_reserva
        accion = "reagendar" if reagendar else "agendar"
        res = await gestionar_reserva(telefono, accion, fecha=fecha_iso, hora=hora)
        # Si era reagendar pero no había reserva previa real → agendar normal
        if res.get("error") and reagendar:
            res = await gestionar_reserva(telefono, "agendar", fecha=fecha_iso, hora=hora)
        if res.get("error"):
            logger.warning(f"[A1] Reserva real NO creada para {telefono}: {res.get('message')}")
        else:
            logger.info(f"[A1] Reserva real OK para {telefono}: {fecha_iso} {hora}")
    except Exception as e:
        logger.error(f"[A1] Error creando reserva real para {telefono}: {e}")


async def _vincular_reservas_lead(telefono: str, reserva_ids: list[str]) -> None:
    """Vincula las RESERVAS FENIX al LEAD (campo LEAD FENIX) para verlas desde
    la tabla de leads. Aislado: nunca rompe la confirmación al padre."""
    if not reserva_ids:
        return
    try:
        from agent.airtable_client import _get_records, _patch, _LEADS, _RESERVAS
        lr = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if not lr:
            return
        lead_id = lr[0]["id"]
        for rid in reserva_ids:
            await _patch(_RESERVAS, rid, {"LEAD FENIX": [lead_id]})
    except Exception as e:
        logger.error(f"[RESERVA] No pude vincular reservas al lead {telefono}: {e}")


async def confirmar_reserva_prueba(telefono: str, fecha: str, hora: str, **kwargs) -> dict:
    """
    Confirma la reserva de la clase de prueba (migración 2.C: solo RESERVAS).

    Crea la RESERVA real en RESERVAS FENIX para todos los hijos de la familia
    del lead (la familia existe por el dual-write al pagar) y la vincula al LEAD.
    """
    # Validar hora contra los turnos del día pedido (un feriado tiene uno solo)
    _validos = _horarios_de(_parsear_fecha(fecha))
    if hora not in _validos:
        return {
            "texto": f"Horario no válido. Los horarios de ese día son: {' | '.join(_validos)}",
            "confirmada": False,
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": f"Hora '{hora}' no es válida para el {fecha}. Opciones: {', '.join(_validos)}.",
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

    # Migración 2.C: la confirmación va DIRECTO a RESERVAS FENIX (PRUEBA ya no
    # se lee ni se escribe). La familia existe por el dual-write al pagar; la
    # reserva se vincula al LEAD para verla desde la tabla de leads.
    from agent.tools.agenda import gestionar_reserva
    _res = await gestionar_reserva(telefono, "agendar", fecha=fecha_iso, hora=hora)
    if _res.get("error"):
        return {
            "texto": "No pude confirmar la reserva. " + (_res.get("message") or ""),
            "confirmada": False,
            "error": True,
            "error_category": _res.get("error_category", "business"),
            "is_retryable": _res.get("is_retryable", False),
            "message": _res.get("message", "No se pudo crear la reserva."),
        }
    _reserva_ids = _res.get("reserva_ids", [])
    await _vincular_reservas_lead(telefono, _reserva_ids)
    _meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
              "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    _d = date.fromisoformat(fecha_iso)
    _fecha_display = f"sábado {_d.day} de {_meses[_d.month - 1]}"
    _hijos = _res.get("hijos", "")
    return {
        "texto": f"Reserva confirmada ✅ {_hijos} el {_fecha_display} a las {hora}h",
        "confirmada": True,
        "fecha": fecha_iso,
        "fecha_display": _fecha_display,
        "hora": hora,
        "hijos": _hijos,
        "reserva_ids": _reserva_ids,
        "enviar_admin": True,
        "mensaje_admin": (
            f"✅ RESERVA CONFIRMADA\n"
            f"👧 {_hijos}\n"
            f"📅 {_fecha_display} a las {hora}h\n"
            f"📱 https://wa.me/{telefono}"
        ),
    }
