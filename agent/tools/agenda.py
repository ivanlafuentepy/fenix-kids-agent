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
    texto = f"Reserva confirmada para {hijos_str} el sábado {fecha} a las {hora}h."

    enviar_admin = False
    mensaje_admin = ""

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


async def reagendar_clase_aurora(
    telefono: str,
    fecha_actual: str,
    hora_actual: str,
    fecha_nueva: str,
    hora_nueva: str,
    familia_id: str | None = None,
) -> dict:
    """
    Reagenda una clase inscripta: cancela la reserva vieja y crea la nueva.
    Una sola tool, una sola llamada. Sin duplicados.
    """
    # Cancelar la vieja
    result_cancel = await cancelar_reserva(telefono, fecha_actual, hora_actual, familia_id)
    if result_cancel.get("error"):
        return result_cancel

    # Crear la nueva
    result_agendar = await agendar_clase(telefono, fecha_nueva, hora_nueva, familia_id)
    if result_agendar.get("error"):
        return result_agendar

    hijos = result_agendar.get("hijos", "?")
    return {
        "texto": f"Reserva reagendada para {hijos}: del {fecha_actual} {hora_actual}h al {fecha_nueva} {hora_nueva}h.",
        "reagendada": True,
        "fecha_anterior": fecha_actual,
        "hora_anterior": hora_actual,
        "fecha_nueva": fecha_nueva,
        "hora_nueva": hora_nueva,
        "hijos": hijos,
        "enviar_admin": True,
        "mensaje_admin": (
            f"🔄 REAGENDAMIENTO\n"
            f"{hijos}: {fecha_actual} {hora_actual} → {fecha_nueva} {hora_nueva}\n"
            f"📱 https://wa.me/{telefono}"
        ),
    }
