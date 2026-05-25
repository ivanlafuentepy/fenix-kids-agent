# agent/reminders.py — Recordatorios automáticos de formulario pendiente
# FENIX KIDS ACADEMY

"""
Cuando un lead agenda una clase pero no llena el formulario (FORMULARIO=False en LEADS),
este módulo programa 4 recordatorios automáticos por WhatsApp:

  - Recordatorio 1 → 15 minutos después del envío del formulario
  - Recordatorio 2 → 2 horas
  - Recordatorio 3 → 8 horas
  - Recordatorio 4 → 23 horas (antes del cierre de ventana de 24hs de WhatsApp)

Reglas:
  - Todos los envíos respetan el horario 08:00–21:00 hora de Paraguay (UTC-4).
    Si el momento calculado cae fuera de ese rango, se pospone automáticamente.
  - Los recordatorios se cancelan en cuanto FORMULARIO pasa a True.
  - Si Railway se reinicia, los tasks pendientes se pierden — aceptable por ahora.
"""

import asyncio
import random
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("agentkit")

# Zona horaria de Paraguay: UTC-4 (sin horario de verano)
_PARAGUAY_OFFSET_H = -4
_HORA_INICIO = 8    # 08:00 local
_HORA_FIN    = 21   # 21:00 local

# Tareas de recordatorio de formulario: {telefono: [Task, ...]}
_tareas_activas: dict[str, list[asyncio.Task]] = {}

# Tareas de seguimiento inicial (rompehielos sin respuesta): {telefono: [Task, ...]}
_tareas_seguimiento: dict[str, list[asyncio.Task]] = {}

_HORARIOS_FENIX = "🕙 11:00h | 🕞 15:30h"

_MENSAJES_SEGUIMIENTO = {
    "A": [
        "Hola! ¿Te quedó alguna duda sobre el Parque FENIX? Acá estoy para contarte lo que necesités 😊",
        (
            f"Te cuento los horarios para venir al parque con tu hijo:\n"
            f"Sábados: {_HORARIOS_FENIX}\n100mil por hijo, padres entran gratis 🌳 ¿Te gustaría agendar un sábado inolvidable para vos y tu hijo?"
        ),
        "Imaginate un sábado al aire libre, frente al río, vos entrenando al lado de tu hijo 🌳 ¿Te gustaría agendar un sábado inolvidable para los dos?",
    ],
    "B": [
        "¿Todo bien? Si querés te cuento más sobre el Parque FENIX, entrenamientos al aire libre para toda la familia 🌿",
        (
            f"Los sábados son así: tu hijo trepa, corre, supera desafíos en la naturaleza. Y vos entrenás al lado con tu propio profe 💪\n"
            f"Sábados: {_HORARIOS_FENIX}\n¿Te gustaría agendar un sábado inolvidable para vos y tu hijo? 🤝"
        ),
        "En el Parque FENIX entrenás con tu hijo en 3000m² de naturaleza, frente al río 🌳 ¿Te gustaría agendar un sábado inolvidable para los dos?",
    ],
}


def _hora_local(dt_utc: datetime) -> datetime:
    """Convierte UTC a hora de Paraguay."""
    return dt_utc + timedelta(hours=_PARAGUAY_OFFSET_H)


def _proxima_ventana_permitida_utc(dt_utc: datetime) -> datetime:
    """
    Si dt_utc en hora local cae fuera de 08:00–21:00, retorna el próximo
    momento permitido (08:00 del mismo día o del día siguiente).
    Si ya está dentro del horario, retorna dt_utc sin cambios.
    """
    local = _hora_local(dt_utc)
    if _HORA_INICIO <= local.hour < _HORA_FIN:
        return dt_utc
    # Calcular las 08:00 locales del día correcto
    if local.hour >= _HORA_FIN:
        # Ya pasó las 21:00 → mañana 08:00
        target_local = datetime(
            local.year, local.month, local.day,
            _HORA_INICIO, 0, 0
        ) + timedelta(days=1)
    else:
        # Antes de las 08:00 → hoy 08:00
        target_local = datetime(
            local.year, local.month, local.day,
            _HORA_INICIO, 0, 0
        )
    # Convertir de vuelta a UTC
    return target_local - timedelta(hours=_PARAGUAY_OFFSET_H)


async def _tarea_recordatorio(
    telefono: str,
    mensaje: str,
    delay_seconds: float,
    inicio_utc: datetime,
    formulario_check_fn,
    proveedor,
    guardar_fn,
):
    """
    Task asyncio que espera el delay, verifica horario y FORMULARIO,
    y envía el recordatorio si todo está OK.
    """
    await asyncio.sleep(delay_seconds)

    # ① Ventana de WhatsApp: no enviar si pasaron más de 23.5 horas del inicio
    if datetime.utcnow() > inicio_utc + timedelta(hours=23, minutes=30):
        logger.info(f"[REMINDER] Ventana 24hs cerrada para {telefono} — recordatorio omitido")
        return

    # ② Formulario: verificar si ya se completó
    try:
        if await formulario_check_fn(telefono):
            logger.info(f"[REMINDER] FORMULARIO ya True para {telefono} — recordatorio cancelado")
            return
    except Exception as e:
        logger.error(f"[REMINDER] Error verificando formulario {telefono}: {e}")
        return

    # ③ Horario: ajustar si cae fuera de 08:00–21:00
    ahora_utc = datetime.utcnow()
    permitido_utc = _proxima_ventana_permitida_utc(ahora_utc)
    if permitido_utc > ahora_utc:
        espera_extra = (permitido_utc - ahora_utc).total_seconds()
        logger.info(f"[REMINDER] Fuera de horario — posponiendo {espera_extra:.0f}s para {telefono}")
        await asyncio.sleep(espera_extra)
        # Re-verificar formulario después de la espera adicional
        try:
            if await formulario_check_fn(telefono):
                logger.info(f"[REMINDER] FORMULARIO completado durante espera para {telefono}")
                return
        except Exception:
            return

    # ④ Enviar
    try:
        ok = await proveedor.enviar_mensaje(telefono, mensaje)
        if ok:
            await guardar_fn(telefono, "assistant", mensaje)
            logger.info(f"[REMINDER] ✅ Enviado a {telefono}: {mensaje[:60]}")
        else:
            logger.warning(f"[REMINDER] ❌ Falló envío a {telefono}")
    except Exception as e:
        logger.error(f"[REMINDER] Excepción enviando a {telefono}: {e}")


def cancelar_recordatorios(telefono: str):
    """Cancela todas las tareas de recordatorio de formulario pendientes para este teléfono."""
    tareas = _tareas_activas.pop(telefono, [])
    for t in tareas:
        t.cancel()
    if tareas:
        logger.info(f"[REMINDER] {len(tareas)} tarea(s) cancelada(s) para {telefono}")


def cancelar_seguimiento(telefono: str):
    """Cancela todos los mensajes de seguimiento inicial pendientes para este teléfono."""
    tareas = _tareas_seguimiento.pop(telefono, [])
    for t in tareas:
        t.cancel()
    if tareas:
        logger.info(f"[SEGUIMIENTO] {len(tareas)} tarea(s) cancelada(s) para {telefono}")


def programar_recordatorios_formulario(
    telefono: str,
    dia: str | None,
    hora: str | None,
    proveedor,
    formulario_check_fn,
    guardar_fn,
):
    """
    Programa 4 recordatorios para completar el registro en chat.
    Cancela cualquier recordatorio previo pendiente para el mismo teléfono.

    Args:
        telefono:            número WhatsApp del lead
        dia:                 día de la clase agendada (ej: "martes")
        hora:                hora de la clase (ej: "19:30")
        proveedor:           instancia de ProveedorWhatsApp
        formulario_check_fn: coroutine function que recibe telefono y retorna bool
        guardar_fn:          coroutine function guardar_mensaje(tel, role, content)
    """
    cancelar_recordatorios(telefono)

    fecha_hora = f"{dia} a las {hora}" if dia and hora else "tu clase agendada"
    inicio_utc = datetime.utcnow()

    recordatorios = [
        (
            15 * 60,
            "Solo me falta tu formulario para completar tu registro 😊",
        ),
        (
            2 * 3600,
            (
                "¡Hola! 🙌\n"
                "Todavía tengo pendiente tu registro.\n"
                "Si completás el formulario ya te dejo todo listo para tu clase."
            ),
        ),
        (
            8 * 3600,
            (
                "Te escribo por última vez por hoy 😊\n"
                "Si querés asegurar tu lugar, solo necesito que completes el formulario."
            ),
        ),
        (
            23 * 3600,
            (
                "Cierro agenda en breve ⏳\n"
                "Si todavía querés venir, completá el formulario y te confirmo tu lugar."
            ),
        ),
    ]

    tareas = [
        asyncio.create_task(
            _tarea_recordatorio(
                telefono=telefono,
                mensaje=msg,
                delay_seconds=delay,
                inicio_utc=inicio_utc,
                formulario_check_fn=formulario_check_fn,
                proveedor=proveedor,
                guardar_fn=guardar_fn,
            )
        )
        for delay, msg in recordatorios
    ]

    _tareas_activas[telefono] = tareas
    logger.info(f"[REMINDER] {len(tareas)} recordatorio(s) programados para {telefono} ({fecha_hora})")


def programar_seguimiento_inicial(
    telefono: str,
    proveedor,
    guardar_fn,
    formulario_check_fn,
):
    """
    Programa 3 mensajes de seguimiento automático después del rompehielos,
    para cuando el lead no responde.

    Timings: +15 min, +2 horas, +6 horas
    Se cancela automáticamente cuando el lead envía cualquier mensaje.
    """
    cancelar_seguimiento(telefono)

    variante = random.choice(["A", "B"])
    inicio_utc = datetime.utcnow()
    delays = [15 * 60, 2 * 3600, 6 * 3600]

    tareas = [
        asyncio.create_task(
            _tarea_recordatorio(
                telefono=telefono,
                mensaje=_MENSAJES_SEGUIMIENTO[variante][i],
                delay_seconds=delays[i],
                inicio_utc=inicio_utc,
                formulario_check_fn=formulario_check_fn,
                proveedor=proveedor,
                guardar_fn=guardar_fn,
            )
        )
        for i in range(3)
    ]

    _tareas_seguimiento[telefono] = tareas
    logger.info(f"[SEGUIMIENTO] 3 mensajes programados para {telefono} (variante {variante})")


# ── Guardado parcial de RESERVA LEADS (15 min sin respuesta del lead) ──────────

# Task por teléfono: {telefono: Task}
_tareas_guardado_parcial: dict[str, asyncio.Task] = {}


def cancelar_guardado_parcial(telefono: str):
    """Cancela el task de guardado parcial pendiente para este teléfono."""
    tarea = _tareas_guardado_parcial.pop(telefono, None)
    if tarea:
        tarea.cancel()
        logger.info(f"[PARCIAL] Task de guardado parcial cancelado para {telefono}")


async def _tarea_guardado_parcial(
    telefono: str,
    check_evento_fn,
    obtener_historial_fn,
    guardar_parcial_fn,
):
    """
    Task que espera 15 min y luego guarda los datos disponibles en RESERVA LEADS,
    rellenando los campos faltantes con valores vacíos. Solo corre si el lead
    todavía no tiene evento en Google Calendar (es decir, el formulario no está completo).
    """
    await asyncio.sleep(15 * 60)

    try:
        if await check_evento_fn(telefono):
            logger.info(f"[PARCIAL] Ya tiene evento — guardado parcial cancelado para {telefono}")
            return

        historial = await obtener_historial_fn(telefono, 40)
        ok = await guardar_parcial_fn(telefono, historial)
        if ok:
            logger.info(f"[PARCIAL] ✅ RESERVA LEADS guardado con datos parciales para {telefono}")
        else:
            logger.warning(f"[PARCIAL] No se pudo guardar RESERVA LEADS parcial para {telefono}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[PARCIAL] Error en guardado parcial para {telefono}: {e}")


def programar_guardado_parcial(
    telefono: str,
    check_evento_fn,
    obtener_historial_fn,
    guardar_parcial_fn,
):
    """
    Programa un guardado de RESERVA LEADS con datos parciales en 15 minutos.
    Se cancela si el lead responde antes (cancelar_guardado_parcial en cada mensaje entrante).
    Se cancela solo si ya tiene evento (formulario completo).
    """
    cancelar_guardado_parcial(telefono)
    tarea = asyncio.create_task(
        _tarea_guardado_parcial(
            telefono=telefono,
            check_evento_fn=check_evento_fn,
            obtener_historial_fn=obtener_historial_fn,
            guardar_parcial_fn=guardar_parcial_fn,
        )
    )
    _tareas_guardado_parcial[telefono] = tarea
    logger.info(f"[PARCIAL] Guardado parcial programado para {telefono} en 15 min")
