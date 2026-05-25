# agent/tools/agenda.py — Agendar y cancelar clases para familias inscriptas
# Solo Aurora. Reemplaza la detección regex de "tiene su lugar" y "cancelé la reserva".

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


async def agendar_clase(
    telefono: str,
    fecha: str,
    hora: str,
    familia_id: str | None = None,
) -> dict:
    """
    Crea RESERVA para TODOS los hijos de la familia inscripta.
    Multi-hijo por defecto: si la familia tiene 3 hijos, los 3 quedan agendados.

    Requiere familia_id (inyectado por executor) o lo resuelve por teléfono.
    """
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
            "message": "No encontré una familia registrada para este número. Primero hay que registrar la familia.",
        }

    # Obtener hijos
    ninos = await obtener_ninos_de_familia(familia_id)
    if not ninos:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "La familia no tiene hijos registrados. Primero hay que registrar al menos un hijo.",
        }

    # Obtener o crear horario
    horario_id = await obtener_o_crear_horario(fecha, hora)
    if not horario_id:
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": f"No pude crear el horario {fecha} {hora} en Airtable.",
        }

    # Limpiar reservas futuras existentes antes de crear
    # Esto evita duplicados — si ya tiene reserva, la borra y crea la nueva
    from datetime import date as _date_cls
    from agent.airtable_client import _delete
    _hoy = _date_cls.today().isoformat()
    reservas_existentes = await _get_records(
        _RESERVAS,
        formula=f"FIND('{familia_id}', ARRAYJOIN({{FAMILIAS}}))",
        max_records=50,
    )
    _borradas = 0
    for _rex in reservas_existentes:
        _rf = _rex.get("fields", {})
        # FECHA puede ser lookup (lista) o texto
        _fecha_res = _rf.get("FECHA", "")
        if isinstance(_fecha_res, list):
            _fecha_res = _fecha_res[0] if _fecha_res else ""
        if _fecha_res and _fecha_res >= _hoy:
            await _delete(_RESERVAS, _rex["id"])
            _borradas += 1
            logger.info(f"[AGENDA] Reserva vieja borrada: {_rex['id']} ({_fecha_res})")
    if _borradas:
        logger.info(f"[AGENDA] {_borradas} reserva(s) vieja(s) borradas para familia {familia_id}")

    # Crear reserva nueva para cada hijo
    reservados = []
    for nino in ninos:
        nino_id = nino["id"]
        nombre = nino.get("nombre_completo") or nino.get("nombre") or "?"
        rid = await crear_reserva(nino_id, horario_id, familia_id)
        if rid:
            reservados.append(nombre)
            logger.info(f"[AGENDA] Reserva creada: {nombre} → {rid}")

    if not reservados:
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": "No pude crear las reservas en Airtable.",
        }

    hijos_str = " y ".join(reservados)
    if _borradas:
        texto = f"Reserva reagendada para {hijos_str} al sábado {fecha} a las {hora}h."
    else:
        texto = f"Reserva confirmada para {hijos_str} el sábado {fecha} a las {hora}h."

    # Notificar al admin si fue reagendamiento
    enviar_admin = bool(_borradas)
    mensaje_admin = ""
    if _borradas:
        mensaje_admin = (
            f"🔄 REAGENDAMIENTO\n"
            f"{hijos_str} → {fecha} {hora}h\n"
            f"📱 https://wa.me/{telefono}"
        )

    return {
        "texto": texto,
        "agendada": True,
        "fecha": fecha,
        "hora": hora,
        "hijos": hijos_str,
        "cantidad": len(reservados),
        "enviar_admin": enviar_admin,
        "mensaje_admin": mensaje_admin,
    }


async def cancelar_reserva(
    telefono: str,
    fecha: str,
    hora: str | None = None,
    familia_id: str | None = None,
) -> dict:
    """
    Cancela reservas de la familia para un sábado (+ hora opcional).
    Si no se especifica hora, cancela todos los turnos de ese día.
    """
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
