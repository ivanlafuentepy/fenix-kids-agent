# agent/tools/agenda.py — Gestión de reservas para familias inscriptas
# Solo Aurora. Una sola tool unificada: gestionar_reserva.

import os
import logging

from agent.airtable_client import (
    buscar_familia_por_telefono,
    obtener_ninos_de_familia,
    obtener_o_crear_horario,
    crear_reserva,
    cancelar_reservas_familia_fecha,
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
    Tool unificada para agendar, reagendar y cancelar reservas.
    - agendar: crea reserva nueva para todos los hijos
    - reagendar: busca reserva actual en Airtable, cancela, crea nueva
    - cancelar: cancela reservas de la fecha/hora indicada
    """
    accion = accion.lower().strip()

    if accion not in ("agendar", "reagendar", "cancelar"):
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"Acción '{accion}' no válida. Usar: agendar, reagendar, cancelar.",
        }

    # Resolver familia
    if not familia_id:
        fam = await buscar_familia_por_telefono(telefono)
        if fam:
            familia_id = fam["id"]
    if not familia_id:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No encontré una familia registrada para este número.",
        }

    if accion == "agendar":
        return await _agendar(telefono, fecha, hora, familia_id)
    elif accion == "reagendar":
        return await _reagendar(telefono, fecha, hora, familia_id)
    elif accion == "cancelar":
        return await _cancelar(telefono, fecha, hora, familia_id)


async def _agendar(telefono: str, fecha: str, hora: str, familia_id: str) -> dict:
    """Crea RESERVA para TODOS los hijos de la familia."""
    if not fecha or not hora:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": "Necesito fecha y hora para agendar.",
        }

    ninos = await obtener_ninos_de_familia(familia_id)
    if not ninos:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "La familia no tiene hijos registrados.",
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
        rid = await crear_reserva(nino_id, horario_id, familia_id)
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


async def _reagendar(telefono: str, fecha_nueva: str, hora_nueva: str, familia_id: str) -> dict:
    """Busca reserva actual en Airtable, cancela, crea nueva."""
    if not fecha_nueva or not hora_nueva:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": "Necesito la nueva fecha y hora para reagendar.",
        }

    # Buscar reserva actual en Airtable (por familia)
    from agent.airtable_client import _get_records, _RESERVAS
    from datetime import datetime
    from zoneinfo import ZoneInfo

    _hoy = datetime.now(ZoneInfo("America/Asuncion")).date()

    # Buscar familia por nombre (lookup texto, no record link)
    fam_record = await _get_records("FAMILIAS FENIX", formula=f"RECORD_ID()='{familia_id}'", max_records=1)
    if not fam_record:
        return {"error": True, "error_category": "business", "is_retryable": False, "message": "Familia no encontrada."}

    nombre_familia = fam_record[0].get("fields", {}).get("FAMILIA", "")
    if not nombre_familia:
        campos = fam_record[0].get("fields", {})
        nombre_familia = f"FAMILIA {campos.get('APELLIDO PADRE', '')} {campos.get('APELLIDO MADRE', '')}".strip()

    reservas = await _get_records(_RESERVAS, formula=f"FIND('{nombre_familia}', ARRAYJOIN({{FAMILIA}}))", max_records=50)

    # Filtrar solo futuras
    reservas_futuras = []
    for r in reservas:
        f = r.get("fields", {})
        _fecha = f.get("FECHA", "")
        if isinstance(_fecha, list):
            _fecha = _fecha[0] if _fecha else ""
        if _fecha >= _hoy.isoformat():
            _hora = f.get("HORA", "")
            if isinstance(_hora, list):
                _hora = _hora[0] if _hora else ""
            reservas_futuras.append({"id": r["id"], "fecha": _fecha, "hora": _hora})

    if not reservas_futuras:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No hay reservas activas para reagendar. Usar agendar en su lugar.",
        }

    # Cancelar todas las reservas futuras actuales
    fecha_actual = reservas_futuras[0]["fecha"]
    hora_actual = reservas_futuras[0]["hora"]
    for r in reservas_futuras:
        await _delete(_RESERVAS, r["id"])
        logger.info(f"[REAGENDAR] Borrada reserva {r['id']} ({r['fecha']} {r['hora']})")

    # Crear nueva
    result = await _agendar(telefono, fecha_nueva, hora_nueva, familia_id)
    if result.get("error"):
        return result

    hijos = result.get("hijos", "?")
    return {
        "texto": f"Reserva reagendada para {hijos}: del {fecha_actual} {hora_actual}h al {fecha_nueva} {hora_nueva}h.",
        "reagendada": True,
        "agendada": True,
        "fecha": fecha_nueva,
        "hora": hora_nueva,
        "hijos": hijos,
        "reserva_ids": result.get("reserva_ids", []),
        "enviar_admin": True,
        "mensaje_admin": (
            f"🔄 REAGENDAMIENTO\n"
            f"{hijos}: {fecha_actual} {hora_actual} → {fecha_nueva} {hora_nueva}\n"
            f"📱 https://wa.me/{telefono}"
        ),
    }


async def _cancelar(telefono: str, fecha: str, hora: str | None, familia_id: str) -> dict:
    """Cancela reservas de la familia para una fecha/hora."""
    if not fecha:
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": True,
            "message": "Necesito la fecha para cancelar.",
        }

    try:
        borradas = await cancelar_reservas_familia_fecha(familia_id, fecha, hora or "")
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
