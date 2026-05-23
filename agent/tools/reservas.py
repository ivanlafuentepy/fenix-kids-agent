# agent/tools/reservas.py — Reagendamiento de clases de prueba
# Busca PRUEBA FENIX en Airtable y actualiza hora/fecha.

import os
import logging

logger = logging.getLogger("agentkit")

_HORARIOS_VALIDOS = {"9:30", "11:00", "15:30"}


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
