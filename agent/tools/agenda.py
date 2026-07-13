# agent/tools/agenda.py — Gestión de reservas para familias inscriptas
# Solo Aurora. Una sola tool unificada: gestionar_reserva.

import logging

from agent.airtable_client import (
    obtener_grupo_familiar,
    obtener_o_crear_horario,
    crear_reserva,
    _get_records,
    _delete,
    _RESERVAS,
)

logger = logging.getLogger("agentkit")


async def gestionar_reserva(
    telefono: str,
    accion: str,
    fecha: str | None = None,
    hora: str | None = None,
    familia_id: str | None = None,
) -> dict:
    """
    Tool unificada para agendar, reagendar y cancelar reservas (niño-eje, F7.b).
    - agendar: crea reserva nueva para todos los hijos
    - reagendar: busca reservas futuras por los links del niño, cancela, crea nueva
    - cancelar: cancela reservas de la fecha/hora indicada

    El grupo se resuelve por teléfono (tutor → hijos; fallback legacy FAMILIAS
    adentro de obtener_grupo_familiar). familia_id solo se usa como pista para
    el fallback y para el link transitorio RESERVAS→FAMILIAS.
    """
    accion = accion.lower().strip()

    if accion not in ("agendar", "reagendar", "cancelar"):
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"Acción '{accion}' no válida. Usar: agendar, reagendar, cancelar.",
        }

    grupo = await obtener_grupo_familiar(telefono, familia_id=familia_id or "")
    ninos = (grupo or {}).get("hijos", [])
    if not ninos:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No encontré niños registrados para este número.",
        }

    if accion == "agendar":
        return await _agendar(fecha, hora, ninos)
    elif accion == "reagendar":
        return await _reagendar(fecha, hora, ninos)
    elif accion == "cancelar":
        return await _cancelar(fecha, hora, ninos)


async def _reservas_futuras_de_ninos(ninos: list[dict]) -> list[dict]:
    """Reservas de hoy en adelante por los links RESERVAS FENIX de los hijos.

    Reemplaza el viejo FIND(record_id, ARRAYJOIN({FAMILIAS})) que NUNCA
    matcheaba (ARRAYJOIN de un link devuelve nombres, no ids — bug A8).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    rids = [rid for n in ninos for rid in (n.get("reserva_ids") or [])][-50:]
    if not rids:
        return []
    hoy = datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()
    _or = ",".join(f"RECORD_ID()='{r}'" for r in rids)
    formula = f"OR({_or})" if len(rids) > 1 else _or
    records = await _get_records(_RESERVAS, formula=formula, max_records=len(rids))
    futuras = []
    for r in records:
        f = r.get("fields", {})
        _fecha = f.get("FECHA", "")
        _fecha = (_fecha[0] if _fecha else "") if isinstance(_fecha, list) else _fecha
        if _fecha < hoy:
            continue
        _hora = f.get("HORA", "")
        _hora = (_hora[0] if _hora else "") if isinstance(_hora, list) else _hora
        _nom = f.get("NOMBRE COMPLETO", "")
        _nom = (_nom[0] if _nom else "") if isinstance(_nom, list) else _nom
        futuras.append({"id": r["id"], "fecha": _fecha, "hora": _hora, "nombre_nino": _nom})
    return futuras


async def _agendar(fecha: str, hora: str, ninos: list[dict]) -> dict:
    """Crea RESERVA para TODOS los hijos del grupo."""
    if not fecha or not hora:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": "Necesito fecha y hora para agendar.",
        }

    horario_id = await obtener_o_crear_horario(fecha, hora)
    if not horario_id:
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": f"No pude crear el horario {fecha} {hora} en Airtable.",
        }

    reservados = []
    reserva_ids = []
    for nino in ninos:
        nino_id = nino["id"]
        nombre = nino.get("nombre_completo") or nino.get("nombre") or "?"
        rid = await crear_reserva(nino_id, horario_id)
        if rid:
            reservados.append(nombre)
            reserva_ids.append(rid)
            logger.info(f"[AGENDA] Reserva creada: {nombre} → {rid}")

    if not reservados:
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": "No pude crear las reservas en Airtable.",
        }

    hijos_str = " y ".join(reservados)
    return {
        "texto": f"Reserva confirmada para {hijos_str} el sábado {fecha} a las {hora}h.",
        "agendada": True,
        "fecha": fecha,
        "hora": hora,
        "hijos": hijos_str,
        "cantidad": len(reservados),
        "reserva_ids": reserva_ids,
        "enviar_admin": False,
        "mensaje_admin": "",
    }


async def _reagendar(fecha_nueva: str, hora_nueva: str, ninos: list[dict]) -> dict:
    """Busca reservas futuras por los links del niño, crea la nueva, borra las viejas."""
    if not fecha_nueva or not hora_nueva:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": "Necesito la nueva fecha y hora para reagendar.",
        }

    reservas_futuras = await _reservas_futuras_de_ninos(ninos)
    if not reservas_futuras:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No hay reservas activas para reagendar. Usar agendar en su lugar.",
        }

    fecha_actual = reservas_futuras[0]["fecha"]
    hora_actual = reservas_futuras[0]["hora"]

    # Crear la reserva nueva PRIMERO: si _agendar falla (Airtable caído,
    # horario inválido), las reservas viejas quedan intactas. Antes se
    # borraba primero y un fallo dejaba a la familia SIN ninguna reserva
    # (auditoría 2026-07-12, A9).
    result = await _agendar(fecha_nueva, hora_nueva, ninos)
    if result.get("error"):
        return result
    _ids_nuevas = set(result.get("reserva_ids", []) or [])

    # Recién ahora borrar las futuras viejas — sin tocar las recién creadas
    # (crear_reserva es idempotente y puede devolver una que ya existía)
    for r in reservas_futuras:
        if r["id"] in _ids_nuevas:
            continue
        await _delete(_RESERVAS, r["id"])
        logger.info(f"[REAGENDAR] Borrada reserva {r['id']} ({r['fecha']} {r['hora']})")

    hijos = result.get("hijos", "?")
    return {
        "texto": f"Reserva reagendada para {hijos}: del {fecha_actual} {hora_actual}h al {fecha_nueva} {hora_nueva}h.",
        "reagendada": True,
        "agendada": True,
        "fecha": fecha_nueva,
        "hora": hora_nueva,
        "hijos": hijos,
        "reserva_ids": result.get("reserva_ids", []),
        "enviar_admin": False,
        "mensaje_admin": "",
    }


async def _cancelar(fecha: str, hora: str | None, ninos: list[dict]) -> dict:
    """Cancela las reservas del grupo para una fecha (y hora, si viene)."""
    if not fecha:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": "Necesito la fecha para cancelar.",
        }

    try:
        borradas = 0
        for r in await _reservas_futuras_de_ninos(ninos):
            if r["fecha"] == fecha and (not hora or r["hora"] == hora):
                if await _delete(_RESERVAS, r["id"]):
                    borradas += 1
                    logger.info(f"Reserva cancelada: {r['id']} ({r['nombre_nino']} {r['fecha']} {r['hora']})")
        if borradas == 0:
            hora_txt = f" a las {hora}h" if hora else ""
            return {
                "texto": f"No encontré reservas para cancelar el {fecha}{hora_txt}.",
                "cancelada": False,
                "cantidad_borradas": 0,
            }

        hora_txt = f" a las {hora}h" if hora else ""
        return {
            "texto": f"Cancelé {borradas} reserva(s) del sábado {fecha}{hora_txt}.",
            "cancelada": True,
            "cantidad_borradas": borradas,
            "fecha": fecha,
            "hora": hora or "",
        }

    except Exception as e:
        logger.error(f"[CANCELAR] Error: {e}")
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": f"Error cancelando reservas: {e}",
        }
