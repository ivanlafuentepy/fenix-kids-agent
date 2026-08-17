# agent/loops.py — Background loops y funciones de recordatorio/followup
# Extraído de main.py (paso 9 del refactor)

"""
Loops infinitos que corren en background:
  - _resumen_diario_loop()        — 8 AM PY, resumen anuncios + reservas
  - _recordatorios_loop()         — cada 60s, revisa recordatorios pendientes
  - _asistencia_auto_loop()       — sábados, lista asistencia al terminar turno
  - _procesar_pendientes_noche()  — wrapper para night_mode
  - _followup_loop()              — DESACTIVADO, FU automático
  - _followup_fotos_oneshot()     — ONE-SHOT fotos mayo 2026
  - _followup_video_oneshot()     — ONE-SHOT video mayo 2026

Funciones auxiliares:
  - _delay_humano()               — simula tipeo humano
  - _programar_recordatorio_clase() — crea recordatorio 07:00 AM
  - _programar_llamada()          — crea alerta para admin
  - _enviar_recordatorio()        — envía recordatorio pendiente
  - _resetear_seguimiento()       — reset contador FU
  - _incrementar_seguimiento()    — incrementa contador FU
  - _ejecutar_followup()          — genera y envía FU a leads
"""

import os
import re
import json
import asyncio
import random
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from agent.memory import (
    guardar_mensaje, obtener_historial,
    crear_recordatorio, obtener_recordatorios_pendientes,
    marcar_recordatorio_enviado, cancelar_recordatorios_por_telefono,
    limpiar_mensajes_procesados_antiguos,
)
from agent.providers import obtener_proveedor
from agent.brain import generar_respuesta
from agent.ab_test import obtener_agent_actual
from agent.night_mode import (
    es_horario_nocturno,
    wakeup_loop as _noche_wakeup_loop,
    procesar_leads_pendientes as _noche_procesar_pendientes,
)
from agent.telegram_bridge import (
    obtener_o_crear_topic, enviar_a_topic,
    notificar_llamada_urgente,
    group_id_para_agente, grupo_telegram_para,
)
from agent.resumenes import (
    _generar_resumen_reservas, _generar_resumen_anuncios,
    _enviar_asistencia_automatica,
)
from agent.airtable_client import actualizar_conversion_lead

logger = logging.getLogger("agentkit")

_TZ_PY = ZoneInfo("America/Asuncion")

proveedor = obtener_proveedor()


# ── Delay humano ─────────────────────────────────────────────────────────────

async def _delay_humano(texto: str):
    """Simula tiempo de tipeo para que el agente no parezca un bot."""
    base = 1.0 + random.uniform(-0.5, 0.5)
    bonus = min(2.0, len(texto) / 150 * 0.5)
    await asyncio.sleep(max(0.3, base + bonus))


# ── Recordatorios ────────────────────────────────────────────────────────────

async def _programar_recordatorio_clase(telefono: str, fecha_iso: str, hora_clase: str = ""):
    """Programa recordatorio de clase para las 07:00 PY del día de la reserva."""
    await cancelar_recordatorios_por_telefono(telefono, tipo="clase")
    from datetime import date as _date_cls
    dia_clase = _date_cls.fromisoformat(fecha_iso)
    envio_local = datetime.combine(dia_clase, time(7, 0), tzinfo=_TZ_PY)
    envio_utc = envio_local.astimezone(timezone.utc).replace(tzinfo=None)
    if envio_utc <= datetime.utcnow():
        logger.info(f"[RECORDATORIO] 07:00 PY ya pasó para {telefono} — omitido")
        return
    payload = json.dumps({"template": "recordatorio_clase", "hora": hora_clase})
    rec_id = await crear_recordatorio(telefono, "clase", envio_utc, payload)
    logger.info(f"[RECORDATORIO] Clase programado id={rec_id} para {telefono} — {dia_clase} 07:00 PY")


async def programar_rescate_formulario(telefono: str):
    """Rescate del lead PAGADO que no completa el formulario Meta (auditoría
    2026-07-12 A7, aprobado por Ivan): sin esto quedaba colgado para siempre
    — el prompt le prohíbe al brain agendar y modo_agenda nunca se activaba.

    +2h  → re-envía el Flow (recordatorio único).
    +24h → suelta el formulario y cae al flujo de agenda por texto (modo_agenda).

    Persistido en Postgres (sobrevive deploys). Se cancela al completar el
    formulario. Si el horario cae de noche (21:00–08:00 PY) se corre a las
    09:00 PY siguientes — a un padre que pagó no se le escribe de madrugada.
    """
    await cancelar_recordatorios_por_telefono(telefono, tipo="form_rescate")

    def _clamp_nocturno(envio_utc):
        local = envio_utc.replace(tzinfo=timezone.utc).astimezone(_TZ_PY)
        if local.hour >= 21:
            local = (local + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif local.hour < 8:
            local = local.replace(hour=9, minute=0, second=0, microsecond=0)
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    ahora = datetime.utcnow()
    envio_2h = _clamp_nocturno(ahora + timedelta(hours=2))
    envio_24h = _clamp_nocturno(ahora + timedelta(hours=24))
    if envio_24h <= envio_2h:
        envio_24h = envio_2h + timedelta(hours=12)
    await crear_recordatorio(telefono, "form_rescate", envio_2h, json.dumps({"template": "form_rescate_2h"}))
    await crear_recordatorio(telefono, "form_rescate", envio_24h, json.dumps({"template": "form_rescate_24h"}))
    logger.info(f"[FORM-RESCATE] Programado para {telefono}: 2h={envio_2h}Z, 24h={envio_24h}Z")


async def _programar_llamada(telefono: str, hora_llamada: str):
    """Programa alerta de llamada para el admin a la hora indicada por el padre."""
    from urllib.parse import quote
    from agent.airtable_client import _get_records, _LEADS

    await cancelar_recordatorios_por_telefono(telefono, tipo="llamada")

    # Parsear hora: "15:00", "3pm", "3 de la tarde", "15", "3"
    hora_num = None
    minuto = 0
    _m = re.search(r'(\d{1,2})[:\.](\d{2})', hora_llamada)
    if _m:
        hora_num = int(_m.group(1))
        minuto = int(_m.group(2))
    else:
        _m2 = re.search(r'(\d{1,2})', hora_llamada)
        if _m2:
            hora_num = int(_m2.group(1))
    if hora_num is None:
        logger.warning(f"[LLAMADA] No pude parsear hora: {hora_llamada}")
        return
    # Si hora < 8 asumir PM
    if hora_num < 8:
        hora_num += 12

    hoy = datetime.now(_TZ_PY).date()
    envio_local = datetime.combine(hoy, time(hora_num, minuto), tzinfo=_TZ_PY)
    envio_utc = envio_local.astimezone(timezone.utc).replace(tzinfo=None)
    if envio_utc <= datetime.utcnow():
        # Ya pasó la hora, enviar alerta inmediata
        from agent.main import _alertar_pedido_llamada
        await _alertar_pedido_llamada(telefono, await obtener_historial(telefono, limite=20), "")
        return

    # Buscar datos del lead para el payload
    nombre_padre = ""
    nombre_hijo = ""
    try:
        lead_records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if lead_records:
            fields = lead_records[0].get("fields", {})
            nombre_padre = fields.get("NOMBRE RESPONSABLE", "")
            nombre_hijo = fields.get("NOMBRE NIÑO", "")
    except Exception:
        pass

    payload = json.dumps({
        "template": "llamada",
        "telefono_lead": telefono,
        "nombre_padre": nombre_padre,
        "nombre_hijo": nombre_hijo,
        "hora": hora_llamada,
    })
    rec_id = await crear_recordatorio(telefono, "llamada", envio_utc, payload)
    logger.info(f"[LLAMADA] Programada id={rec_id} para {telefono} a las {hora_num}:{minuto:02d} PY")


async def _enviar_recordatorio(rec):
    """Envía un recordatorio pendiente."""
    data = json.loads(rec.payload)
    template = data.get("template", "recordatorio_clase")

    if template == "llamada":
        # Alerta de llamada programada al admin
        telefono_lead = data.get("telefono_lead", rec.telefono)
        nombre_padre = data.get("nombre_padre", "")
        nombre_hijo = data.get("nombre_hijo", "")
        hora = data.get("hora", "")
        from urllib.parse import quote
        primer_nombre = nombre_padre.split()[0] if nombre_padre else ""
        mensaje_pre = f"Que tal {primer_nombre}, soy el profe Ivan te escribo desde mi personal, te puedo llamar ahora?" if primer_nombre else "Que tal, soy el profe Ivan te escribo desde mi personal, te puedo llamar ahora?"
        wa_link = f"https://wa.me/{telefono_lead}?text={quote(mensaje_pre)}"
        alerta = (
            f"🔔 Llamada programada AHORA\n\n"
            f"👤 {nombre_padre}\n"
            f"👦 Hijo/a: {nombre_hijo}\n"
            f"⏰ Hora acordada: {hora}\n\n"
            f"📲 {wa_link}"
        )
        admin_phone = os.getenv("ADMIN_PHONE", "")
        ok = await proveedor.enviar_mensaje(admin_phone, alerta)
        try:
            await notificar_llamada_urgente(telefono_lead, nombre_padre, wa_link)
        except Exception:
            pass
        return ok

    if template in ("form_rescate_2h", "form_rescate_24h"):
        # Rescate del formulario post-pago (A7). Guard: solo si el lead SIGUE
        # esperando el formulario — si ya lo completó, el recordatorio se marca
        # enviado sin mandar nada (la cancelación al completar es best-effort).
        from agent.ab_test import obtener_estado_flags
        flags = await obtener_estado_flags(rec.telefono)
        if not flags.get("esperando_formulario_reserva"):
            logger.info(f"[FORM-RESCATE] {rec.telefono} ya no espera formulario — {template} omitido")
            return True

        if template == "form_rescate_2h":
            # Recordatorio único: re-enviar el Flow
            from agent.formulario_reserva import enviar_formulario_reserva
            ok = await enviar_formulario_reserva(rec.telefono)
            if ok:
                await guardar_mensaje(rec.telefono, "assistant", "[formulario de reserva re-enviado +2h]")
                logger.info(f"[FORM-RESCATE] Flow re-enviado a {rec.telefono} (+2h)")
            return ok

        # form_rescate_24h: soltar el formulario y pasar directo a elegir turno.
        # El padre ya pagó: si el Flow nunca vuelve, igual tiene que quedar
        # anotado en los 2 días del campus.
        from agent.ab_test import actualizar_estado_flags
        from agent.desafio import ofrecer_turnos_campus
        await actualizar_estado_flags(rec.telefono, esperando_formulario_reserva=False)
        ok = await ofrecer_turnos_campus(rec.telefono, proveedor)
        if ok:
            logger.info(f"[FORM-RESCATE] {rec.telefono} pasado a elegir turnos (+24h)")
        try:
            _grp = await grupo_telegram_para(rec.telefono)
            _topic = await obtener_o_crear_topic(rec.telefono, f"📱 {rec.telefono}", group_override=_grp)
            if _topic:
                await enviar_a_topic(_topic, "⏰ Lead pagado no completó el formulario en 24h — pasado a agenda por texto", telefono=rec.telefono, group_override=_grp)
        except Exception as _e_fr:
            logger.warning(f"[FORM-RESCATE] espejo Telegram falló: {_e_fr}")
        return ok

    # Recordatorio de clase (default)
    hora = data.get("hora", "")
    msg = f"Hola! Te recordamos que hoy tenés tu clase a las {hora} en Fenix Kids 🥋 Te esperamos!"
    ok = await proveedor.enviar_mensaje(rec.telefono, msg)
    if ok:
        await guardar_mensaje(rec.telefono, "assistant", msg)
    return ok


# ── Loops infinitos ──────────────────────────────────────────────────────────

async def _resumen_diario_loop():
    """Envía resumen anuncios + resumen reservas al admin todos los días a las 8:00 AM PY."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    _PY = ZoneInfo("America/Asuncion")  # UTC-3 fijo — el -4 viejo mandaba el "8 AM" a las 9
    admin_phone = os.getenv("ADMIN_PHONE", "")
    while True:
        ahora = datetime.now(_PY)
        hoy_8 = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
        if ahora >= hoy_8:
            hoy_8 += timedelta(days=1)
        espera = (hoy_8 - ahora).total_seconds()
        logger.info(f"[RESUMEN DIARIO] Próximo envío en {espera/3600:.1f}h ({hoy_8.strftime('%Y-%m-%d %H:%M')} PY)")
        await asyncio.sleep(espera)
        try:
            logger.info("[RESUMEN DIARIO] Enviando resumen anuncios + reservas...")
            await _generar_resumen_anuncios(admin_phone, "resumen anuncios")
            await asyncio.sleep(3)
            await _generar_resumen_reservas(admin_phone)
            logger.info("[RESUMEN DIARIO] Enviado OK")
        except Exception as e:
            logger.error(f"[RESUMEN DIARIO] Error: {e}")


async def _confirmacion_sabado_loop():
    """Los jueves 9:00 AM PY manda la plantilla de confirmación de asistencia del
    sábado a cada familia con pago al día, dirigida al tutor que paga. Botón "Sí"
    → Aurora pregunta el turno (11:00/15:30) y agenda; botón "No" → no reserva.
    (La respuesta se maneja en agent/confirmacion_sabado.py, interceptada en main.)

    APAGADO por default: solo envía si CONFIRMACION_SABADO_ACTIVA=true en el env.
    Es un masivo a familias reales → no se dispara sin activación explícita de Ivan
    (misma disciplina que el follow-up de leads). El loop igual corre y duerme hasta
    el jueves; solo el envío está detrás del flag."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from agent.confirmacion_sabado import recolectar_envios, enviar_confirmacion_sabado
    _PY = ZoneInfo("America/Asuncion")
    admin_phone = os.getenv("ADMIN_PHONE", "")
    while True:
        ahora = datetime.now(_PY)
        # Próximo jueves (weekday 3) 9:00 AM PY.
        dias = (3 - ahora.weekday()) % 7
        proximo = ahora.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=dias)
        if proximo <= ahora:
            proximo += timedelta(days=7)
        espera = (proximo - ahora).total_seconds()
        logger.info(f"[CONF-SAB] Próximo envío jueves en {espera/3600:.1f}h ({proximo.strftime('%Y-%m-%d %H:%M')} PY)")
        await asyncio.sleep(espera)

        if os.getenv("CONFIRMACION_SABADO_ACTIVA", "").strip().lower() not in ("1", "true", "si", "sí"):
            logger.info("[CONF-SAB] CONFIRMACION_SABADO_ACTIVA apagado — no se envía este jueves")
            continue
        try:
            envios = await recolectar_envios()
            logger.info(f"[CONF-SAB] {len(envios)} familias al día para confirmar")
            enviados = 0
            for e in envios:
                try:
                    ok = await enviar_confirmacion_sabado(
                        e["telefono"], proveedor, e["nombre_padre"], e["hijos_str"])
                    if ok:
                        enviados += 1
                    await asyncio.sleep(2)  # rate limit — Meta silencia números por spam
                except Exception as ex:
                    logger.error(f"[CONF-SAB] Error enviando a {e.get('telefono')}: {ex}")
            logger.info(f"[CONF-SAB] Enviados {enviados}/{len(envios)}")
            if admin_phone:
                try:
                    await proveedor.enviar_mensaje(
                        admin_phone,
                        f"📅 Confirmación sábado enviada a {enviados}/{len(envios)} familias al día.")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[CONF-SAB] Error en loop: {e}")


async def _recordatorios_loop():
    """Loop que cada 60s revisa recordatorios pendientes en PostgreSQL y los envía.
    Marca ENVIADO solo si el envío salió (antes un 4xx de Meta lo marcaba igual
    y el recordatorio se perdía en silencio — auditoría 04-07-26 A19); si falla,
    reintenta máx 3 ciclos y se rinde (no spamear el log para siempre).
    _enviados_sin_marcar evita el duplicado si el envío salió pero el marcado
    en DB falló (se reintenta solo el marcado, no el envío)."""
    _ciclo = 0
    _reintentos_envio: dict[int, int] = {}
    _enviados_sin_marcar: set[int] = set()
    while True:
        try:
            pendientes = await obtener_recordatorios_pendientes(datetime.utcnow())
            for rec in pendientes:
                try:
                    if rec.id in _enviados_sin_marcar:
                        await marcar_recordatorio_enviado(rec.id)
                        _enviados_sin_marcar.discard(rec.id)
                        continue
                    ok = await _enviar_recordatorio(rec)
                    if not ok:
                        _reintentos_envio[rec.id] = _reintentos_envio.get(rec.id, 0) + 1
                        if _reintentos_envio[rec.id] >= 3:
                            await marcar_recordatorio_enviado(rec.id)
                            _reintentos_envio.pop(rec.id, None)
                            logger.error(f"[RECORDATORIO] id={rec.id} descartado tras 3 envíos fallidos (¿ventana 24h cerrada?)")
                        else:
                            logger.warning(f"[RECORDATORIO] Envío falló id={rec.id} — reintento {_reintentos_envio[rec.id]}/3 en el próximo ciclo")
                        continue
                    _reintentos_envio.pop(rec.id, None)
                    _enviados_sin_marcar.add(rec.id)
                    await marcar_recordatorio_enviado(rec.id)
                    _enviados_sin_marcar.discard(rec.id)
                    logger.info(f"[RECORDATORIO] Enviado id={rec.id} a {rec.telefono}")
                except Exception as e:
                    logger.error(f"[RECORDATORIO] Error enviando id={rec.id}: {e}")
            # Cada 30 min: limpiar dedup table (mensajes > 24h)
            _ciclo += 1
            if _ciclo % 30 == 0:
                await limpiar_mensajes_procesados_antiguos()
        except Exception as e:
            logger.error(f"[RECORDATORIO] Error en loop: {e}")
        await asyncio.sleep(60)


async def _procesar_pendientes_noche():
    """Wrapper para procesar leads nocturnos con dependencias inyectadas."""
    await _noche_procesar_pendientes(
        proveedor=proveedor,
        obtener_historial_fn=obtener_historial,
        guardar_mensaje_fn=guardar_mensaje,
        generar_respuesta_fn=generar_respuesta,
        obtener_o_crear_topic_fn=obtener_o_crear_topic,
        enviar_a_topic_fn=enviar_a_topic,
    )


async def _asistencia_auto_loop():
    """Loop que envía lista de asistencia automáticamente al terminar cada turno (sábados)."""
    from datetime import datetime, timezone, timedelta
    _PY_TZ = timezone(timedelta(hours=-3))
    # Horarios de envío: {hora_envio: turno_que_terminó}
    _HORARIOS_ASISTENCIA = {
        (11, 0): "9:30",    # 11:00 → lista del turno 9:30
        (12, 30): "11:00",  # 12:30 → lista del turno 11:00
        (17, 0): "15:30",   # 17:00 → lista del turno 15:30
    }
    _enviados_hoy: set[str] = set()

    while True:
        try:
            ahora = datetime.now(_PY_TZ)
            # Solo sábados
            if ahora.weekday() == 5:
                for (h, m), turno in _HORARIOS_ASISTENCIA.items():
                    if ahora.hour == h and ahora.minute >= m and ahora.minute < m + 5 and turno not in _enviados_hoy:
                        _enviados_hoy.add(turno)
                        await _enviar_asistencia_automatica(turno)
            else:
                _enviados_hoy.clear()
        except Exception as e:
            logger.error(f"[ASISTENCIA AUTO] Error: {e}")
        await asyncio.sleep(60)


# ── Horarios mensuales (auto-creación) ───────────────────────────────────────

async def _horarios_mensuales_loop():
    """
    Mantiene la tabla HORARIOS cargada sola — nunca más falta un turno.

    - Al arrancar: asegura el mes ACTUAL + el SIGUIENTE (tapa huecos al instante).
    - Después: corre el ÚLTIMO día de cada mes a las 9:00 AM PY y crea el mes siguiente.

    Avisa por WhatsApp al admin SOLO si creó turnos nuevos (evita spam en cada
    reinicio de Railway, donde normalmente ya está todo cargado).
    """
    from datetime import datetime, date, time, timedelta
    from calendar import monthrange
    from agent.airtable_client import crear_horarios_mes

    admin_phone = os.getenv("ADMIN_PHONE", "")
    meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    def _mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
        return (anio + 1, 1) if mes == 12 else (anio, mes + 1)

    def _ultimo_dia_9am(anio: int, mes: int) -> datetime:
        ultimo = monthrange(anio, mes)[1]
        return datetime.combine(date(anio, mes, ultimo), time(9, 0), tzinfo=_TZ_PY)

    def _fmt(item: str) -> str:
        # "2026-07-04 11:00" → "sábado 4 de julio — 11:00h"
        fecha, hora = item.split(" ")
        dd = date.fromisoformat(fecha)
        return f"sábado {dd.day} de {meses_es[dd.month - 1]} — {hora}h"

    async def _asegurar(meses: list[tuple[int, int]], titulo: str):
        creados: list[str] = []
        for (a, m) in meses:
            try:
                res = await crear_horarios_mes(a, m)
                creados.extend(res["creados"])
            except Exception as e:
                logger.error(f"[HORARIOS-MES] Error creando {a}-{m:02d}: {e}")
        if creados and admin_phone:
            lineas = "\n".join(f"  • {_fmt(c)}" for c in creados)
            msg = f"🗓️ {titulo}\n\nCargué {len(creados)} turnos nuevos en la agenda:\n{lineas}"
            try:
                await proveedor.enviar_mensaje(admin_phone, msg)
            except Exception as e:
                logger.error(f"[HORARIOS-MES] No pude avisar al admin: {e}")
        return creados

    # ── Arranque: asegurar mes actual + siguiente ──
    try:
        ahora = datetime.now(_TZ_PY)
        await _asegurar(
            [(ahora.year, ahora.month), _mes_siguiente(ahora.year, ahora.month)],
            "Agenda al día (arranque)",
        )
    except Exception as e:
        logger.error(f"[HORARIOS-MES] Error en arranque: {e}")

    # ── Loop: último día del mes 9:00 AM PY → crear mes siguiente ──
    while True:
        ahora = datetime.now(_TZ_PY)
        target = _ultimo_dia_9am(ahora.year, ahora.month)
        if ahora >= target:
            # El último día de este mes ya pasó → apuntar al del mes siguiente
            a2, m2 = _mes_siguiente(ahora.year, ahora.month)
            target = _ultimo_dia_9am(a2, m2)
        delay = (target - ahora).total_seconds()
        logger.info(f"[HORARIOS-MES] Próxima creación en {delay/86400:.1f}d ({target.strftime('%Y-%m-%d %H:%M')} PY)")
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        try:
            # Estamos a fin de mes → crear el mes siguiente
            ahora2 = datetime.now(_TZ_PY)
            a3, m3 = _mes_siguiente(ahora2.year, ahora2.month)
            await _asegurar([(a3, m3)], f"Horarios de {meses_es[m3 - 1]} {a3} creados")
        except Exception as e:
            logger.error(f"[HORARIOS-MES] Error creando mes siguiente: {e}")

        await asyncio.sleep(3600)  # evitar doble disparo el mismo día


# ── Keep-alive ventana 24h del admin ─────────────────────────────────────────

async def _keepalive_ventana_admin_loop():
    """Mantiene abierta la ventana de 24h de Meta hacia el WhatsApp del admin.

    Meta solo permite enviar texto libre dentro de las 24h desde el último
    mensaje del usuario. Las alertas urgentes al admin (padre quiere llamada,
    Ivan no supo responder, monitor) son texto libre — si la ventana está
    cerrada, NO llegan al WhatsApp y solo quedan en Telegram.

    Para evitarlo, todos los días a las 9:00 AM PY mandamos un botón "Sí" al
    admin. Al apretarlo, el admin genera un mensaje ENTRANTE que reabre la
    ventana de 24h. Va por reloj (no por intervalo): reiniciar el servidor NO
    dispara un botón extra, solo sale a las 9 AM. Mientras el admin apriete el
    botón cada día, todas las alertas le llegan por WhatsApp.

    LIMITACIÓN (acordada con Ivan): el botón es un mensaje normal. Si la ventana
    YA está cerrada (el admin no apretó el botón dentro de las 24h), este envío
    falla y la cadena queda rota hasta que el admin le escriba "hola" al bot.
    """
    from datetime import datetime, timedelta

    admin_phone = os.getenv("ADMIN_PHONE", "")
    if not admin_phone:
        logger.warning("[KEEPALIVE-VENTANA] ADMIN_PHONE no configurado — loop no arranca")
        return

    texto = (
        "🔔 Ventana de alertas Fenix\n\n"
        "Apretá *Sí* para seguir recibiendo las alertas urgentes "
        "por WhatsApp las próximas 24h."
    )
    botones = [{"id": "activar_ventana", "title": "Sí"}]

    while True:
        # Por reloj: próxima 9:00 AM PY (reiniciar el server NO dispara botón extra)
        ahora = datetime.now(_TZ_PY)
        target = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
        if ahora >= target:
            target += timedelta(days=1)
        delay = (target - ahora).total_seconds()
        logger.info(f"[KEEPALIVE-VENTANA] Próximo botón en {delay:.0f}s ({target.strftime('%Y-%m-%d %H:%M')} PY)")

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        try:
            ok = await proveedor.enviar_botones(admin_phone, texto, botones)
            if ok:
                logger.info("[KEEPALIVE-VENTANA] Botón enviado al admin (9 AM PY)")
            else:
                logger.warning(
                    "[KEEPALIVE-VENTANA] Botón NO salió (¿ventana cerrada?) — "
                    "el admin debe escribir 'hola' al bot para reabrir la cadena"
                )
        except Exception as e:
            logger.error(f"[KEEPALIVE-VENTANA] Error enviando botón: {e}")

        await asyncio.sleep(60)  # evitar doble ejecución


# ── Follow-up leads ──────────────────────────────────────────────────────────

async def _resetear_seguimiento(telefono: str):
    """Pone SEGUIMIENTOS=0 y FECHA FOLLOWUP=ahora cuando Ivan manda datos bancarios."""
    from agent.airtable_client import obtener_lead_record_id, _patch, _LEADS
    from datetime import datetime, timezone
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return
    campos = {"SEGUIMIENTOS": 0, "FECHA FOLLOWUP": datetime.now(timezone.utc).isoformat()}
    await _patch(_LEADS, record_id, campos)
    logger.info(f"[FOLLOWUP] {telefono} → SEGUIMIENTOS reseteado")


async def _incrementar_seguimiento(telefono: str) -> int:
    """Incrementa SEGUIMIENTOS y actualiza FECHA FOLLOWUP. Retorna el nuevo valor."""
    from agent.airtable_client import obtener_lead_record_id, _patch, _get_records, _LEADS
    from datetime import datetime, timezone
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return 0
    # Leer valor actual
    records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    actual = records[0].get("fields", {}).get("SEGUIMIENTOS", 0) if records else 0
    nuevo = (actual or 0) + 1
    campos = {"SEGUIMIENTOS": nuevo, "FECHA FOLLOWUP": datetime.now(timezone.utc).isoformat()}
    await _patch(_LEADS, record_id, campos)
    logger.info(f"[FOLLOWUP] {telefono} → SEGUIMIENTOS={nuevo}")
    return nuevo


async def _followup_loop():
    """Loop diario 9:00 AM PY — follow-up a leads con datos bancarios enviados pero sin pago."""
    from zoneinfo import ZoneInfo
    from datetime import datetime, time, timedelta

    _TZ_PY = ZoneInfo("America/Asuncion")

    while True:
        # Calcular próxima 9:00 AM PY
        ahora = datetime.now(_TZ_PY)
        target = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
        if ahora >= target:
            target += timedelta(days=1)
        delay = (target - ahora).total_seconds()
        logger.info(f"[FOLLOWUP] Próximo ciclo en {delay:.0f}s ({target.strftime('%Y-%m-%d %H:%M')} PY)")

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        try:
            await _ejecutar_followup()
        except Exception as e:
            logger.error(f"[FOLLOWUP] Error en ciclo: {e}", exc_info=True)

        await asyncio.sleep(60)  # evitar doble ejecución


async def _ejecutar_followup():
    """Recorre leads CONTACTADO y envía follow-up respetando ventana 24h de WhatsApp.

    Lógica de ventana:
    - FU1 siempre se envía (24h después de datos bancarios — ventana abierta por msg del lead).
    - FU2 solo si RESPONDIO FU1=True (el lead respondió al FU1, reabrió ventana).
    - FU3 solo si RESPONDIO FU2=True (idem).
    - Si pasaron 24h y NO respondió al FU previo → DESCARTADO (ventana cerrada).
    """
    from datetime import datetime, timezone
    import httpx as _httpx_fu

    ahora = datetime.now(timezone.utc)

    # Buscar leads con CONVERSION=CONTACTADO y SEGUIMIENTOS<3
    formula = "AND({CONVERSION}='CONTACTADO',OR({SEGUIMIENTOS}<3,{SEGUIMIENTOS}=BLANK()))"
    try:
        all_records = []
        offset_fu = None
        base_id = os.getenv("AIRTABLE_BASE_ID")
        api_key = os.getenv("AIRTABLE_API_KEY")
        while True:
            from urllib.parse import quote
            params = f"filterByFormula={quote(formula)}&pageSize=100"
            if offset_fu:
                params += f"&offset={offset_fu}"
            _url = f"https://api.airtable.com/v0/{base_id}/LEADS%20FENIX?{params}"
            async with _httpx_fu.AsyncClient(timeout=15) as _cl:
                _r = await _cl.get(_url, headers={"Authorization": f"Bearer {api_key}"})
                _data = _r.json()
            all_records.extend(_data.get("records", []))
            offset_fu = _data.get("offset")
            if not offset_fu:
                break

        for rec in all_records:
            fields = rec.get("fields", {})
            telefono = fields.get("TELEFONO", "")
            fecha_fu = fields.get("FECHA FOLLOWUP", "")
            seguimientos = fields.get("SEGUIMIENTOS", 0) or 0
            if not telefono or not fecha_fu:
                continue

            # Verificar que pasaron al menos 24h desde el último followup
            try:
                fecha_ultimo = datetime.fromisoformat(fecha_fu.replace("Z", "+00:00"))
                horas_desde = (ahora - fecha_ultimo).total_seconds() / 3600
                if horas_desde < 24:
                    continue
            except Exception:
                continue

            # ── Validar ventana 24h: FU2+ solo si respondió al FU anterior ──
            respondio_fu1 = fields.get("RESPONDIO FU1", False)
            respondio_fu2 = fields.get("RESPONDIO FU2", False)

            if seguimientos == 1 and not respondio_fu1:
                # FU1 enviado, no respondió, 24h pasaron → ventana cerrada
                await actualizar_conversion_lead(telefono, "DESCARTADO")
                logger.info(f"[FOLLOWUP] {telefono}: no respondió FU1, ventana cerrada → DESCARTADO")
                continue
            if seguimientos == 2 and not respondio_fu2:
                # FU2 enviado, no respondió, 24h pasaron → ventana cerrada
                await actualizar_conversion_lead(telefono, "DESCARTADO")
                logger.info(f"[FOLLOWUP] {telefono}: no respondió FU2, ventana cerrada → DESCARTADO")
                continue

            # Datos para el mensaje
            nombre_hijo = fields.get("NOMBRE NIÑO", "") or ""
            nombre_padre = fields.get("NOMBRE RESPONSABLE", "") or ""
            primer_nombre = nombre_padre.split()[0] if nombre_padre else ""

            historial = await obtener_historial(telefono, limite=20)

            # Safety check: si ya pagó entre medio
            pago_en_hist = any(
                "pago confirmado" in m.get("content", "").lower()
                for m in historial if m.get("role") == "assistant"
            )
            if pago_en_hist:
                await actualizar_conversion_lead(telefono, "PAGO")
                continue

            # Generar instrucción según número de seguimiento
            if seguimientos == 0:
                instruccion = (
                    f"[SISTEMA: El padre {primer_nombre} recibió los datos bancarios hace 24h "
                    f"pero no mandó el comprobante. Mandá un mensaje corto y amable recordándole "
                    f"que tiene el lugar reservado para {nombre_hijo or 'su hijo/a'} y que te mande "
                    f"el comprobante cuando pueda. No presiones. Máximo 2 líneas.]"
                )
            elif seguimientos == 1:
                instruccion = (
                    f"[SISTEMA: Segundo seguimiento a {primer_nombre}. Ya le recordaste ayer y respondió. "
                    f"Preguntá si le gustaría agendar una prueba para {nombre_hijo or 'su hijo/a'}. "
                    f"Ofrecé ayuda si tiene alguna duda. Corto y directo. Máximo 2 líneas.]"
                )
            elif seguimientos == 2:
                instruccion = (
                    f"[SISTEMA: Tercer y último seguimiento a {primer_nombre}. "
                    f"Decile que el lugar de {nombre_hijo or 'su hijo/a'} sigue disponible pero que "
                    f"necesitás confirmar. Si no responde, no se le contacta más. Máximo 2 líneas.]"
                )
            else:
                continue

            try:
                respuesta_fu = await generar_respuesta(
                    mensaje=instruccion,
                    historial=historial,
                    agent_actual="ivan",
                )
                await guardar_mensaje(telefono, "assistant", respuesta_fu)
                await proveedor.enviar_mensaje(telefono, respuesta_fu)
                nuevo = await _incrementar_seguimiento(telefono)

                # Si llegó a 3 → DESCARTADO
                if nuevo >= 3:
                    await actualizar_conversion_lead(telefono, "DESCARTADO")
                    logger.info(f"[FOLLOWUP] {telefono}: 3 seguimientos completados → DESCARTADO")

                # Espejar en Telegram — grupo según el agente REAL del número
                # (agent_actual), no forzar leads: si ya es familia iría al grupo
                # equivocado y el topic rebota creando uno nuevo en cada envío.
                try:
                    _grp_fu = await grupo_telegram_para(telefono)
                    _topic_fu = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=_grp_fu)
                    if _topic_fu:
                        await enviar_a_topic(_topic_fu, f"🔔 FOLLOWUP ({nuevo}/3): {respuesta_fu}", telefono=telefono, group_override=_grp_fu)
                except Exception:
                    pass

                logger.info(f"[FOLLOWUP] {telefono}: seguimiento {nuevo}/3 enviado")
                await asyncio.sleep(3)  # pausa entre leads
            except Exception as e:
                logger.error(f"[FOLLOWUP] Error enviando a {telefono}: {e}")

    except Exception as e:
        logger.error(f"[FOLLOWUP] Error en ciclo: {e}")

    logger.info("[FOLLOWUP] Ciclo completado")


# ── Follow-up masivo fotos — ONE-SHOT ────────────────────────────────────────

_FOLLOWUP_FOTO1 = os.path.join(os.path.dirname(__file__), "..", "static", "followup_caricatura.png")
_FOLLOWUP_FOTO2 = os.path.join(os.path.dirname(__file__), "..", "static", "followup_foto.jpeg")


async def _followup_fotos_oneshot():
    """Envía fotos + texto a leads del 4-5 mayo. Se ejecuta UNA vez el 6 mayo 6AM PY."""
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta
    from agent.airtable_client import _get_records, _LEADS, _patch
    import httpx

    _TZ_PY = ZoneInfo("America/Asuncion")

    # Esperar hasta 6:00 AM PY del 5 de mayo
    ahora = datetime.now(_TZ_PY)
    target = datetime(2026, 5, 5, 6, 0, 0, tzinfo=_TZ_PY)
    if ahora >= target:
        # Ya pasó, verificar si es el mismo día (permite re-deploy el mismo día)
        if (ahora - target).total_seconds() > 3600:  # más de 1h después = ya corrió
            logger.info("[FOLLOWUP-FOTOS] Ya pasó la ventana — oneshot desactivado")
            return
    else:
        delay = (target - ahora).total_seconds()
        logger.info(f"[FOLLOWUP-FOTOS] Esperando {delay:.0f}s hasta 6AM PY 2026-05-05")
        await asyncio.sleep(delay)

    logger.info("[FOLLOWUP-FOTOS] Iniciando envío masivo de fotos...")

    # Buscar leads desde 4 mayo que NO tengan 1ER FOLLOWUP checked
    formula = "AND(IS_AFTER({FECHA CREACION},'2026-05-04T10:00:00.000Z'),NOT({1ER FOLLOWUP}))"
    all_records = []
    offset = None
    base_id = os.getenv("AIRTABLE_BASE_ID")
    api_key = os.getenv("AIRTABLE_API_KEY")

    while True:
        from urllib.parse import quote
        params = f"filterByFormula={quote(formula)}&pageSize=100"
        if offset:
            params += f"&offset={offset}"
        url = f"https://api.airtable.com/v0/{base_id}/LEADS%20FENIX?{params}"
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.get(url, headers={"Authorization": f"Bearer {api_key}"})
            data = r.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    logger.info(f"[FOLLOWUP-FOTOS] {len(all_records)} leads para enviar")

    # Leer fotos
    with open(_FOLLOWUP_FOTO1, "rb") as f:
        foto1_bytes = f.read()
    with open(_FOLLOWUP_FOTO2, "rb") as f:
        foto2_bytes = f.read()

    enviados = 0
    for rec in all_records:
        fields = rec.get("fields", {})
        telefono = fields.get("TELEFONO", "")
        conversion = fields.get("CONVERSION", "")
        nombre_hijo = fields.get("NOMBRE NIÑO", "") or fields.get("NOMBRE NI\u00d1O", "") or ""
        if not telefono:
            continue

        try:
            # Enviar foto 1
            await proveedor.enviar_imagen_bytes(telefono, foto1_bytes, "image/png")
            await asyncio.sleep(2)

            # Enviar foto 2
            await proveedor.enviar_imagen_bytes(telefono, foto2_bytes, "image/jpeg")
            await asyncio.sleep(2)

            # Texto según si pagó o no
            if conversion == "PAGO" and nombre_hijo:
                texto = (
                    f"Aqui es donde {nombre_hijo} se transforma, este sabado entrenamos con todo!! "
                    f"Cupos casi llenos para este sabado, los esperamos! 🔥🌳"
                )
            else:
                texto = (
                    "Aqui es donde tu hijo se transforma, este sabado entrenamos con todo!! "
                    "Cupos casi llenos para este sabado, te gustaria confirmar la reserva? 🔥🌳"
                )

            await proveedor.enviar_mensaje(telefono, texto)
            await guardar_mensaje(telefono, "assistant", texto)

            # Espejar en Telegram — grupo según el agente REAL del número (ver nota arriba)
            try:
                _grp_ff = await grupo_telegram_para(telefono)
                _topic_fu_fotos = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=_grp_ff)
                if _topic_fu_fotos:
                    await enviar_a_topic(_topic_fu_fotos, f"📢 1ER FOLLOWUP: [📸 2 fotos + texto enviado]", telefono=telefono, group_override=_grp_ff)
            except Exception:
                pass

            # Marcar 1ER FOLLOWUP en Airtable
            await _patch(_LEADS, rec["id"], {"1ER FOLLOWUP": True})

            enviados += 1
            logger.info(f"[FOLLOWUP-FOTOS] Enviado a {telefono} ({enviados}/{len(all_records)})")
            await asyncio.sleep(3)  # pausa entre leads

        except Exception as e:
            logger.error(f"[FOLLOWUP-FOTOS] Error con {telefono}: {e}")

    logger.info(f"[FOLLOWUP-FOTOS] Completado: {enviados}/{len(all_records)} enviados")


# ── Follow-up video — ONE-SHOT ───────────────────────────────────────────────

_FOLLOWUP_VIDEO = os.path.join(os.path.dirname(__file__), "..", "static", "followup_video.mp4")


async def _followup_video_oneshot():
    """Envía video a todos los leads con ventana 24h abierta. ONE-SHOT 6AM PY 6/5."""
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta
    from agent.memory import async_session, Mensaje
    from sqlalchemy import select as sa_select

    _TZ_PY = ZoneInfo("America/Asuncion")

    # Esperar hasta 6:00 AM PY del 6 de mayo
    ahora = datetime.now(_TZ_PY)
    target = datetime(2026, 5, 6, 6, 0, 0, tzinfo=_TZ_PY)
    if ahora >= target:
        if (ahora - target).total_seconds() > 3600:
            logger.info("[FOLLOWUP-VIDEO] Ya pasó la ventana — oneshot desactivado")
            return
    else:
        delay = (target - ahora).total_seconds()
        logger.info(f"[FOLLOWUP-VIDEO] Esperando {delay:.0f}s hasta 6AM PY 2026-05-06")
        await asyncio.sleep(delay)

    logger.info("[FOLLOWUP-VIDEO] Iniciando envío masivo de video...")

    # Ventana 24h: leads que escribieron después del 5 de mayo 5:00 UTC (~1AM PY)
    from datetime import timezone
    corte_ventana = datetime(2026, 5, 5, 5, 0, 0, tzinfo=timezone.utc)

    # Buscar teléfonos con mensajes user recientes (ventana abierta)
    telefonos_ventana = set()
    async with async_session() as session:
        query = (
            sa_select(Mensaje.telefono)
            .where(Mensaje.role == "user")
            .where(Mensaje.timestamp > corte_ventana.replace(tzinfo=None))
            .distinct()
        )
        result = await session.execute(query)
        telefonos_ventana = {row[0] for row in result.all()}

    if not telefonos_ventana:
        logger.info("[FOLLOWUP-VIDEO] No hay leads con ventana abierta")
        return

    # Excluir admin
    admin_phone = os.getenv("ADMIN_PHONE", "")
    telefonos_ventana.discard(admin_phone)

    logger.info(f"[FOLLOWUP-VIDEO] {len(telefonos_ventana)} leads con ventana abierta")

    # Consultar Airtable para saber quién ya recibió 1ER FOLLOWUP
    from agent.airtable_client import _get_records, _LEADS
    leads_con_1er_fu = set()
    for telefono in telefonos_ventana:
        try:
            recs = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
            if recs and recs[0].get("fields", {}).get("1ER FOLLOWUP"):
                leads_con_1er_fu.add(telefono)
        except Exception:
            pass
    logger.info(f"[FOLLOWUP-VIDEO] {len(leads_con_1er_fu)} ya recibieron 1ER FU, {len(telefonos_ventana) - len(leads_con_1er_fu)} es su 1ro")

    # Leer video
    try:
        with open(_FOLLOWUP_VIDEO, "rb") as f:
            video_bytes = f.read()
    except FileNotFoundError:
        logger.error(f"[FOLLOWUP-VIDEO] Archivo no encontrado: {_FOLLOWUP_VIDEO}")
        return

    # Subir video UNA sola vez (reusar media_id)
    media_id_video = await proveedor.subir_media(video_bytes, "video/mp4")
    if not media_id_video:
        logger.error("[FOLLOWUP-VIDEO] No se pudo subir el video a Meta")
        return

    logger.info(f"[FOLLOWUP-VIDEO] Video subido: media_id={media_id_video}")

    texto_fu = "Regalale a tu hijo un sábado que recordará por el resto de su vida. Quedan pocos lugares disponibles."

    enviados = 0
    for telefono in telefonos_ventana:
        try:
            # Enviar video con caption
            ok = await proveedor.enviar_imagen(telefono, media_id_video, caption="")
            if not ok:
                # Fallback: enviar como video explícito
                url_msg = f"https://graph.facebook.com/{proveedor.api_version}/{proveedor.phone_number_id}/messages"
                headers = {"Authorization": f"Bearer {proveedor.access_token}", "Content-Type": "application/json"}
                import httpx
                async with httpx.AsyncClient() as cl:
                    await cl.post(url_msg, json={
                        "messaging_product": "whatsapp",
                        "to": telefono,
                        "type": "video",
                        "video": {"id": media_id_video},
                    }, headers=headers)

            await asyncio.sleep(2)

            # Enviar texto
            await proveedor.enviar_mensaje(telefono, texto_fu)
            await guardar_mensaje(telefono, "assistant", texto_fu)

            # Espejar en Telegram — anotar si es 1ro o 2do según si ya recibió el masivo de fotos
            _fu_num = "2DO" if telefono in leads_con_1er_fu else "1ER"
            try:
                _grp_vid = await grupo_telegram_para(telefono)
                _topic_vid = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=_grp_vid)
                if _topic_vid:
                    await enviar_a_topic(_topic_vid, f"📢 {_fu_num} FOLLOWUP: [🎬 Video + texto enviado]", telefono=telefono, group_override=_grp_vid)
            except Exception:
                pass

            enviados += 1
            logger.info(f"[FOLLOWUP-VIDEO] Enviado a {telefono} ({enviados}/{len(telefonos_ventana)})")
            await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"[FOLLOWUP-VIDEO] Error con {telefono}: {e}")

    logger.info(f"[FOLLOWUP-VIDEO] Completado: {enviados}/{len(telefonos_ventana)} enviados")


# ── Envío de facturas Fenix ───────────────────────────────────────────────────

async def _envio_facturas_fenix_loop():
    """Cada 90s: factura de FENIX emitida por el robot facturador (FACTURADO +
    COMPROBANTE SET + PDF en FACTURA PDF) que aún NO se envió al tutor →
    manda el PDF (LIBRE si la ventana 24h está abierta, plantilla
    factura_electronica_fenix con header documento si está cerrada) → ENVIADO.

    Espejo del loop de Dorita. Solo toma facturas con link TUTOR;
    las de Salsa (link ALUMNO) las reparte Dorita."""
    from agent.memory import ventana_abierta
    from agent.airtable_client import (
        listar_facturas_fenix_para_enviar, obtener_contacto_tutor,
        marcar_factura_fenix_enviada,
    )
    from agent.telegram_bridge import grupo_telegram_para

    logger.info("[FACTURA-ENVIO] Loop iniciado — polling cada 90s")
    _CAPTION = "Acá tenés tu factura 😊 ¡Muchas gracias por tu pago! 🔥"
    # Guard anti-doble-PDF: si el envío salió pero marcar_factura_fenix_enviada
    # falló (Airtable caído), sin esto la familia recibía el PDF de nuevo cada
    # 90s hasta que Airtable respondiera (auditoría 04-07-26 A19).
    _enviadas_sin_marcar: set[str] = set()
    while True:
        try:
            pendientes = await listar_facturas_fenix_para_enviar()
            for fac in pendientes:
                try:
                    if not fac.get("tutor_ids") or not fac.get("pdf_url"):
                        continue
                    if fac["record_id"] in _enviadas_sin_marcar:
                        # Ya se envió — solo reintentar el marcado, no el PDF
                        await marcar_factura_fenix_enviada(fac["record_id"])
                        _enviadas_sin_marcar.discard(fac["record_id"])
                        continue
                    # Niño-eje: contacto por el TUTOR de la factura.
                    tel, nombre = await obtener_contacto_tutor(fac["tutor_ids"][0])
                    if not tel:
                        logger.info(f"[FACTURA-ENVIO] rec {fac['record_id']} sin teléfono, salteo")
                        continue
                    abierta = await ventana_abierta(tel)
                    if abierta:
                        ok = await proveedor.enviar_documento_url(
                            tel, fac["pdf_url"], fac["pdf_filename"], _CAPTION)
                    else:
                        ok = await proveedor.enviar_plantilla(
                            tel, "factura_electronica_fenix",
                            componentes=[
                                {"type": "header", "parameters": [
                                    {"type": "document",
                                     "document": {"link": fac["pdf_url"], "filename": fac["pdf_filename"]}}]},
                                {"type": "body", "parameters": [
                                    {"type": "text", "parameter_name": "nombre", "text": nombre or "familia"}]},
                            ],
                            language="es_AR",  # la plantilla está aprobada en es_AR (default del método es "es")
                        )
                    _metodo = "MENSAJE NORMAL (ventana abierta)" if abierta else "PLANTILLA (ventana cerrada)"
                    if ok:
                        _enviadas_sin_marcar.add(fac["record_id"])
                        await marcar_factura_fenix_enviada(fac["record_id"])
                        _enviadas_sin_marcar.discard(fac["record_id"])
                        await guardar_mensaje(tel, "assistant", f"🧾 Factura enviada ({_metodo})")
                        logger.info(f"[FACTURA-ENVIO] ✅ enviada a {tel} por {_metodo} (rec {fac['record_id']})")
                        # Espejo a Telegram en el topic de la familia
                        try:
                            _grp = await grupo_telegram_para(tel)
                            _topic = await obtener_o_crear_topic(tel, nombre or tel, group_override=_grp)
                            if _topic:
                                await enviar_a_topic(_topic, f"🧾 Factura enviada a {nombre or tel} por {_metodo}",
                                                     telefono=tel, group_override=_grp)
                        except Exception as e:
                            logger.error(f"[FACTURA-ENVIO] error espejo Telegram: {e}")
                    else:
                        logger.error(f"[FACTURA-ENVIO] ❌ falló envío a {tel} por {_metodo} (rec {fac['record_id']})")
                    await asyncio.sleep(1.2)  # throttle Meta
                except Exception as e:
                    logger.error(f"[FACTURA-ENVIO] error rec {fac.get('record_id')}: {e}")
        except Exception as e:
            logger.error(f"[FACTURA-ENVIO] error loop: {e}")
        await asyncio.sleep(90)
