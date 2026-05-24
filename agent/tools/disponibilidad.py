# agent/tools/disponibilidad.py — Consulta de disponibilidad y agendados
# Ivan ve solo conteos (privacidad). Aurora ve nombres.

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from agent.airtable_client import (
    obtener_ninos_por_horario,
    obtener_horarios_disponibles,
    formatear_lista_ninos,
)

logger = logging.getLogger("agentkit")
_TZ_PY = ZoneInfo("America/Asuncion")
_HORARIOS = ["9:30", "11:00", "15:30"]


async def consultar_disponibilidad(
    telefono: str,
    fecha: str | None = None,
    hora: str | None = None,
) -> dict:
    """
    Consulta cuántos niños hay agendados por slot.
    - fecha+hora: conteo para ese slot específico
    - solo fecha: conteo para los 3 turnos de ese día
    - nada: próximos horarios disponibles

    Retorna solo CONTEO, nunca nombres (privacidad para Ivan).
    """
    try:
        # Sin fecha: mostrar próximos horarios disponibles
        if not fecha:
            horarios = await obtener_horarios_disponibles(max_horarios=8)
            if not horarios:
                return {"texto": "No hay horarios cargados próximamente.", "slots": []}

            slots = []
            for h in horarios:
                ninos = await obtener_ninos_por_horario(h["fecha"], h["hora"])
                slots.append({
                    "fecha": h["fecha"],
                    "hora": h["hora"],
                    "dia": h.get("dia", ""),
                    "cantidad": len(ninos),
                })

            lineas = [f"📅 {s['dia'] or s['fecha']} {s['hora']}h → {s['cantidad']} niños" for s in slots]
            return {
                "texto": "Disponibilidad próximos sábados:\n" + "\n".join(lineas),
                "slots": slots,
            }

        # Con fecha pero sin hora: mostrar los 3 turnos de ese día
        if not hora:
            slots = []
            for h in _HORARIOS:
                ninos = await obtener_ninos_por_horario(fecha, h)
                slots.append({"fecha": fecha, "hora": h, "cantidad": len(ninos)})

            lineas = [f"⏰ {s['hora']}h → {s['cantidad']} niños" for s in slots]
            return {
                "texto": f"Disponibilidad para el {fecha}:\n" + "\n".join(lineas),
                "slots": slots,
            }

        # Con fecha y hora: slot específico
        ninos = await obtener_ninos_por_horario(fecha, hora)
        return {
            "texto": f"El {fecha} a las {hora}h hay {len(ninos)} niños agendados.",
            "slots": [{"fecha": fecha, "hora": hora, "cantidad": len(ninos)}],
        }

    except Exception as e:
        logger.error(f"[DISPONIBILIDAD] Error: {e}")
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": f"Error consultando disponibilidad: {e}",
        }


async def consultar_agendados(
    telefono: str,
    fecha: str,
    hora: str,
) -> dict:
    """
    Lista de niños agendados para un slot (con nombres).
    Solo para Aurora — Ivan usa consultar_disponibilidad (solo conteos).
    """
    try:
        ninos = await obtener_ninos_por_horario(fecha, hora)
        if not ninos:
            return {
                "texto": f"No hay niños agendados para el {fecha} a las {hora}h.",
                "lista": "",
                "cantidad": 0,
            }

        lista = formatear_lista_ninos(ninos, fecha, hora)
        return {
            "texto": lista,
            "lista": lista,
            "cantidad": len(ninos),
        }

    except Exception as e:
        logger.error(f"[AGENDADOS] Error: {e}")
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": f"Error consultando agendados: {e}",
        }
