# agent/contenido_social.py — Engranaje de redes sociales + follow-up diario
# FENIX KIDS ACADEMY
#
# Dos funciones principales:
#   1. Polling CONTENIDO FENIX → cuando Claude de Postiz crea un registro nuevo,
#      este módulo detecta NOTIFICADO=false y envía WhatsApp a los padres cuyos
#      hijos aparecen en el posteo.
#   2. Calendario diario — cada día envía a TODAS las familias inscriptas
#      el último contenido de la red social del día:
#        Lunes=Instagram, Martes=Facebook, Miércoles=TikTok,
#        Jueves=YouTube, Viernes=Threads, Sábado=fotos, Domingo=videos

import asyncio
import logging
from datetime import datetime, timedelta

from agent.airtable_client import (
    obtener_contenido_no_notificado,
    marcar_contenido_notificado,
    obtener_ultimo_contenido_por_red,
    obtener_familias_inscriptas,
    obtener_nombre_nino,
    obtener_redes,
)

logger = logging.getLogger("agentkit")

# Zona horaria Paraguay: UTC-4
_PARAGUAY_OFFSET_H = -4
_HORA_ENVIO_DIARIO = 10  # 10:00 AM hora Paraguay

# Calendario semanal: día de la semana (0=lunes) → red social
_CALENDARIO_SEMANAL = {
    0: "Instagram",   # Lunes
    1: "Facebook",    # Martes
    2: "TikTok",      # Miércoles
    3: "YouTube",     # Jueves
    4: "Threads",     # Viernes
    # 5: Sábado → fotos directas (flujo manual por ahora)
    # 6: Domingo → videos directos (flujo manual por ahora)
}

# Referencia al proveedor de WhatsApp (se inyecta al iniciar)
_proveedor = None

# Task del polling
_polling_task: asyncio.Task | None = None
_calendario_task: asyncio.Task | None = None


def _hora_local() -> datetime:
    """Retorna la hora actual en Paraguay (UTC-4)."""
    return datetime.utcnow() + timedelta(hours=_PARAGUAY_OFFSET_H)


# ── Polling de CONTENIDO FENIX ───────────────────────────────────────────────

async def _procesar_contenido_nuevo():
    """
    Busca registros en CONTENIDO FENIX con NOTIFICADO=false.
    Por cada uno, envía WhatsApp personalizado a los padres cuyos hijos aparecen.
    """
    registros = await obtener_contenido_no_notificado()
    if not registros:
        return

    familias = await obtener_familias_inscriptas()
    if not familias:
        logger.warning("[CONTENIDO] No hay familias inscriptas con teléfono")
        return

    for reg in registros:
        link = reg.get("link", "")
        red = reg.get("red", "")
        nino_ids_posteo = set(reg.get("nino_ids", []))

        if not link:
            logger.warning(f"[CONTENIDO] Registro {reg['id']} sin LINK, se marca como notificado")
            await marcar_contenido_notificado(reg["id"])
            continue

        # Obtener nombres de los niños del posteo
        nombres_ninos = {}
        for nid in nino_ids_posteo:
            nino = await obtener_nombre_nino(nid)
            if nino:
                nombres_ninos[nid] = nino.get("apodo") or nino.get("nombre", "")

        # Enviar a cada familia que tiene un hijo en el posteo
        enviados = 0
        for familia in familias:
            telefono = familia["telefono"]
            nombre_padre = (
                familia.get("apodo_padre")
                or familia.get("nombre_padre")
                or familia.get("apodo_madre")
                or familia.get("nombre_madre")
                or ""
            )

            # Ver si algún hijo de esta familia aparece en el posteo
            hijos_en_posteo = [
                nombres_ninos[nid]
                for nid in familia.get("nino_ids", [])
                if nid in nino_ids_posteo and nid in nombres_ninos
            ]

            if hijos_en_posteo:
                # Mensaje personalizado: "tu hijo aparece!"
                nombres = " y ".join(hijos_en_posteo)
                mensaje = (
                    f"Hola {nombre_padre}! 😊\n"
                    f"{nombres} aparece en nuestro nuevo posteo de {red}!\n"
                    f"Miralo acá 👇\n{link}"
                )
                ok = await _proveedor.enviar_mensaje(telefono, mensaje)
                if ok:
                    enviados += 1
                    logger.info(f"[CONTENIDO] Enviado personalizado a {telefono} ({nombres})")
                else:
                    # Ventana cerrada — intentar con plantilla
                    logger.info(f"[CONTENIDO] Ventana cerrada para {telefono}, intentando plantilla")
                    await _proveedor.enviar_plantilla(
                        telefono, "contenido_hijo",
                        variables=[nombre_padre, nombres, red, link],
                    )

        await marcar_contenido_notificado(reg["id"])
        logger.info(f"[CONTENIDO] Registro {reg['id']} procesado: {enviados} familias notificadas")


async def _polling_loop():
    """Loop de polling: revisa CONTENIDO FENIX cada 5 minutos."""
    logger.info("[CONTENIDO] Polling iniciado — cada 5 minutos")
    while True:
        try:
            await _procesar_contenido_nuevo()
        except Exception as e:
            logger.error(f"[CONTENIDO] Error en polling: {e}")
        await asyncio.sleep(300)  # 5 minutos


# ── Calendario diario ────────────────────────────────────────────────────────

async def _enviar_contenido_diario():
    """
    Envía a TODAS las familias inscriptas el último contenido
    de la red social correspondiente al día de la semana.
    """
    ahora = _hora_local()
    dia_semana = ahora.weekday()  # 0=lunes, 6=domingo

    red = _CALENDARIO_SEMANAL.get(dia_semana)
    if not red:
        logger.info(f"[CALENDARIO] Día {dia_semana} (sáb/dom) — sin envío automático de red")
        return

    # Buscar último contenido no notificado de esa red
    contenido = await obtener_ultimo_contenido_por_red(red)

    # Si no hay contenido nuevo, usar el perfil genérico de la red
    if not contenido:
        redes = await obtener_redes()
        perfil = next((r for r in redes if r["red"] == red), None)
        if not perfil:
            logger.info(f"[CALENDARIO] No hay contenido ni perfil para {red}")
            return
        link = perfil["perfil"]
        icono = perfil.get("icono", "")
    else:
        link = contenido["link"]
        icono = ""

    familias = await obtener_familias_inscriptas()
    if not familias:
        return

    enviados = 0
    for familia in familias:
        telefono = familia["telefono"]
        nombre_padre = (
            familia.get("apodo_padre")
            or familia.get("nombre_padre")
            or familia.get("apodo_madre")
            or familia.get("nombre_madre")
            or ""
        )

        if contenido:
            # Hay posteo nuevo de esa red
            nino_ids_posteo = set(contenido.get("nino_ids", []))
            hijos_en_posteo = []
            for nid in familia.get("nino_ids", []):
                if nid in nino_ids_posteo:
                    nino = await obtener_nombre_nino(nid)
                    if nino:
                        hijos_en_posteo.append(nino.get("apodo") or nino.get("nombre", ""))

            if hijos_en_posteo:
                nombres = " y ".join(hijos_en_posteo)
                mensaje = (
                    f"Hola {nombre_padre}! 😊\n"
                    f"{nombres} aparece en nuestro nuevo posteo de {red}!\n"
                    f"Miralo acá 👇\n{link}"
                )
            else:
                mensaje = (
                    f"Hola {nombre_padre}! 😊\n"
                    f"Mirá nuestro nuevo posteo en {red} 👇\n{link}"
                )
        else:
            # No hay posteo nuevo, enviar link al perfil genérico
            mensaje = (
                f"Hola {nombre_padre}! 😊\n"
                f"Seguinos en {red} para ver todo lo que hacemos en FENIX Kids 🌳\n{link}"
            )

        ok = await _proveedor.enviar_mensaje(telefono, mensaje)
        if ok:
            enviados += 1
        else:
            # Ventana cerrada — intentar con plantilla
            await _proveedor.enviar_plantilla(
                telefono, "contenido_diario",
                variables=[nombre_padre, red, link],
            )

    # Marcar contenido como notificado si existía
    if contenido:
        await marcar_contenido_notificado(contenido["id"])

    logger.info(f"[CALENDARIO] {red}: enviado a {enviados}/{len(familias)} familias")


async def _calendario_loop():
    """
    Loop del calendario diario.
    Espera hasta las 10:00 AM Paraguay y envía el contenido del día.
    """
    logger.info("[CALENDARIO] Scheduler diario iniciado")
    while True:
        ahora = _hora_local()
        # Calcular próxima ejecución: hoy a las 10:00 o mañana si ya pasó
        siguiente = ahora.replace(hour=_HORA_ENVIO_DIARIO, minute=0, second=0, microsecond=0)
        if ahora >= siguiente:
            siguiente += timedelta(days=1)

        espera = (siguiente - ahora).total_seconds()
        logger.info(f"[CALENDARIO] Próximo envío en {espera/3600:.1f}h ({siguiente.strftime('%A %H:%M')})")
        await asyncio.sleep(espera)

        try:
            await _enviar_contenido_diario()
        except Exception as e:
            logger.error(f"[CALENDARIO] Error: {e}")


# ── Recordatorio viernes pre-clase ────────────────────────────────────────────

async def _enviar_recordatorio_viernes():
    """
    Viernes 18:00 PY: busca RESERVAS del sábado siguiente.
    Por cada niño con reserva, envía recordatorio al padre con confirmación activa.
    """
    from agent.airtable_client import obtener_ninos_por_horario

    ahora = _hora_local()

    # Calcular el sábado siguiente (siempre mañana si hoy es viernes)
    dias_hasta_sabado = (5 - ahora.weekday()) % 7
    if dias_hasta_sabado == 0:
        dias_hasta_sabado = 1  # Si es viernes, mañana es sábado
    sabado = ahora + timedelta(days=dias_hasta_sabado)
    fecha_sabado = sabado.strftime("%Y-%m-%d")

    familias = await obtener_familias_inscriptas()
    if not familias:
        return

    # Para cada horario buscar niños reservados
    horarios = ["11:00", "15:30"]
    # Mapear nino_id → (familia_telefono, nombre_padre, hora)
    notificaciones: dict[str, list[dict]] = {}  # telefono → [{hijo, hora}]

    for hora in horarios:
        ninos = await obtener_ninos_por_horario(fecha_sabado, hora)
        for nino in ninos:
            nombre_nino = nino.get("apodo") or nino.get("nombre", "")
            # Buscar a qué familia pertenece este niño
            for familia in familias:
                # Comparar por nombre (no tenemos nino_id directo en la respuesta de obtener_ninos_por_horario)
                tel = familia["telefono"]
                if tel not in notificaciones:
                    notificaciones[tel] = []
                # Verificar si algún hijo de esta familia matchea
                # (el niño tiene nombre y apellido, la familia tiene nino_ids)
                # Por simplificación: matchear por nombre+apellido
                nombre_completo_nino = f"{nino.get('nombre', '')} {nino.get('apellido', '')}".strip().lower()
                for nid in familia.get("nino_ids", []):
                    nino_data = await obtener_nombre_nino(nid)
                    if nino_data:
                        nombre_familia = f"{nino_data.get('nombre', '')} {nino_data.get('apellido', '')}".strip().lower()
                        if nombre_familia == nombre_completo_nino:
                            notificaciones[tel].append({
                                "hijo": nino_data.get("apodo") or nino_data.get("nombre", ""),
                                "hora": hora,
                            })
                            break

    # Enviar recordatorios
    enviados = 0
    for telefono, hijos_info in notificaciones.items():
        if not hijos_info:
            continue

        # Buscar nombre del padre
        familia = next((f for f in familias if f["telefono"] == telefono), None)
        if not familia:
            continue

        nombre_padre = (
            familia.get("apodo_padre")
            or familia.get("nombre_padre")
            or familia.get("apodo_madre")
            or familia.get("nombre_madre")
            or ""
        )

        # Agrupar hijos por hora
        if len(hijos_info) == 1:
            h = hijos_info[0]
            mensaje = (
                f"Hola {nombre_padre}! 😊\n"
                f"Mañana {h['hijo']} tiene clase a las {h['hora']}h\n"
                f"Respondé CONFIRMO así le reservo su lugar 💪🌳"
            )
        else:
            lineas = [f"• {h['hijo']} a las {h['hora']}h" for h in hijos_info]
            mensaje = (
                f"Hola {nombre_padre}! 😊\n"
                f"Mañana tus hijos tienen clase en FENIX:\n"
                + "\n".join(lineas) + "\n"
                f"Respondé CONFIRMO así les reservo su lugar 💪🌳"
            )

        ok = await _proveedor.enviar_mensaje(telefono, mensaje)
        if ok:
            enviados += 1
        else:
            # Ventana cerrada — plantilla
            hijos_str = ", ".join(h["hijo"] for h in hijos_info)
            horas_str = ", ".join(set(h["hora"] for h in hijos_info))
            await _proveedor.enviar_plantilla(
                telefono, "recordatorio_clase",
                variables=[nombre_padre, hijos_str, horas_str],
            )

    logger.info(f"[RECORDATORIO] Viernes: {enviados} familias notificadas para el sábado {fecha_sabado}")


async def _recordatorio_viernes_loop():
    """
    Loop que espera hasta el viernes 18:00 PY y envía recordatorios.
    """
    logger.info("[RECORDATORIO] Scheduler viernes iniciado")
    while True:
        ahora = _hora_local()
        # Calcular próximo viernes a las 18:00
        dias_hasta_viernes = (4 - ahora.weekday()) % 7  # 4 = viernes
        if dias_hasta_viernes == 0 and ahora.hour >= 18:
            dias_hasta_viernes = 7  # Ya pasó, esperar al próximo

        siguiente = ahora.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=dias_hasta_viernes)
        espera = (siguiente - ahora).total_seconds()

        if espera < 0:
            espera += 7 * 24 * 3600  # Failsafe: esperar una semana

        logger.info(f"[RECORDATORIO] Próximo viernes en {espera/3600:.1f}h")
        await asyncio.sleep(espera)

        try:
            await _enviar_recordatorio_viernes()
        except Exception as e:
            logger.error(f"[RECORDATORIO] Error: {e}")


# ── Inicialización ───────────────────────────────────────────────────────────

def iniciar_contenido_social(proveedor):
    """
    Inicia los dos loops en background:
      1. Polling de CONTENIDO FENIX (cada 5 min)
      2. Calendario diario (una vez al día a las 10:00 PY)

    Llamar desde main.py en el lifespan del servidor.
    """
    global _proveedor, _polling_task, _calendario_task
    _proveedor = proveedor

    # DESACTIVADO (2026-06-23): los broadcasts automáticos a familias se van a
    # rearmar desde cero en otra sesión. No arrancamos los loops para que NINGUNA
    # familia reciba saludos diarios / posteos / recordatorios automáticos.
    # El código de los loops queda intacto como referencia para el rediseño.
    # _polling_task = asyncio.create_task(_polling_loop())
    # _calendario_task = asyncio.create_task(_calendario_loop())
    # _recordatorio_task = asyncio.create_task(_recordatorio_viernes_loop())

    logger.info("[CONTENIDO] Módulo cargado — broadcasts automáticos DESACTIVADOS (rediseño pendiente)")
