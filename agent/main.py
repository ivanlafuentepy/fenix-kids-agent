# agent/main.py — Servidor FastAPI + Webhook WhatsApp
# FENIX KIDS ACADEMY — dual agente: Profe Ivan + Aurora

"""
Endpoints:
  GET  /              → health check
  GET  /stats         → estadísticas de conversión
  GET  /webhook       → verificación Meta Cloud API
  POST /webhook       → mensajes entrantes de WhatsApp
  POST /telegram/webhook → mensajes desde Telegram (admin → WhatsApp)
  GET  /telegram/setup?url=https://... → registra webhook Telegram
"""

import os
import re
import asyncio
import random
import logging
# OrderedDict eliminado — ya no se usa cache de dedup en memoria
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta, extraer_datos_formulario
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial,
    crear_recordatorio, obtener_recordatorios_pendientes,
    marcar_recordatorio_enviado, cancelar_recordatorios_por_telefono,
    mensaje_ya_procesado, registrar_mensaje_procesado, borrar_mensaje_procesado,
    limpiar_mensajes_procesados_antiguos,
)
from agent.providers import obtener_proveedor
from agent.ab_test import (
    asignar_variante, obtener_estadisticas,
    marcar_conversion, esta_convertido,
    guardar_airtable_record_id, obtener_airtable_record_id,
    obtener_agent_actual, actualizar_agent_actual,
    obtener_familia_id, guardar_familia_id,
    marcar_noche_pendiente, tiene_noche_pendiente,
)
from agent.night_mode import (
    es_horario_nocturno, MENSAJE_NOCHE,
    wakeup_loop as _noche_wakeup_loop,
    procesar_leads_pendientes as _noche_procesar_pendientes,
)
from agent.telegram_bridge import (
    obtener_o_crear_topic, enviar_a_topic, enviar_media_a_topic,
    dorita_esta_activa, silenciar_dorita, reactivar_dorita,
    obtener_telefono_por_topic,
    configurar_webhook, obtener_info_webhook,
    notificar_agenda_telegram, notificar_llamada_urgente,
    notificar_pago_telegram,
    group_id_para_agente,
)
from agent.meta_capi import enviar_evento_agenda, enviar_evento_pago
from agent.pagos import (
    es_posible_comprobante, detectar_tipo_pago,
    registrar_pago_pendiente, tiene_pago_pendiente,
    obtener_pago_pendiente, confirmar_pago, rechazar_pago,
    formatear_monto, PRECIOS, CI_BANCARIO, monto_prueba_por_hijos,
)
from agent.airtable_client import (
    crear_lead, obtener_lead_record_id,
    actualizar_conversion_lead, actualizar_agent_lead,
    marcar_formulario_lead, crear_familia_completa, crear_familia, crear_nino,
    obtener_ninos_de_familia, crear_reserva,
    buscar_familia_por_telefono, buscar_familia_por_nombre,
    eliminar_lead, eliminar_todo_de_telefono,
    obtener_o_crear_horario, crear_prueba_fenix,
    actualizar_datos_lead, actualizar_diagnostico_lead,
    actualizar_reserva_lead, marcar_control_datos,
    obtener_ninos_por_horario, formatear_lista_ninos,
    obtener_horarios_disponibles, obtener_redes,
    cancelar_reservas_familia_fecha,
)
from agent.memory import limpiar_estado_completo
from agent.reminders import (
    programar_seguimiento_inicial, cancelar_seguimiento,
    programar_recordatorios_formulario, cancelar_recordatorios,
)
from agent.memory import guardar_mensaje as _guardar_mensaje
from agent.transcriber import descargar_audio_whatsapp, transcribir_audio

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

TELEGRAM_GROUP_ID = int(os.getenv("TELEGRAM_GROUP_ID", "0"))

# ── Protección contra Prompt Injection ───────────────────────────────────────
# Solo frases específicas e inequívocas — evitar tokens cortos que causan
# falsos positivos en lenguaje cotidiano (ej: "dan" matchea "¿dan clases?").
_PALABRAS_PELIGROSAS = [
    "ignora tus instrucciones", "ignore your instructions",
    "olvida todo", "forget everything", "forget your instructions",
    "nuevo rol", "new role", "actua como", "pretend you are",
    "system prompt", "jailbreak",
]


def _es_mensaje_sospechoso(texto: str) -> bool:
    t = texto.lower()
    return any(p in t for p in _PALABRAS_PELIGROSAS)


# ── Detección de spam / scam / cuenta hackeada ──────────────────────────────
# Links sospechosos, cadenas de estafa, mensajes masivos reenviados.
# Cuando se detecta: NO responder, silenciar conversación, alertar admin.
_PATRONES_SPAM = [
    re.compile(r'https?://[^\s]*\.buzz(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.xyz(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.top(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.click(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.link(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.win(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.loan(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'me dieron los?\s*[\₲$]\s*[\d.,]+.*pru[eé]balo', re.IGNORECASE),
    re.compile(r'gan[eéa]\s+[\₲$]?\s*[\d.,]+.*(?:link|haz\s*clic|prueba)', re.IGNORECASE),
    re.compile(r'(?:regalo|gané|ganaste|sorteo|premio).*https?://', re.IGNORECASE),
]


def _es_spam_o_scam(texto: str) -> bool:
    """Detecta mensajes de spam, scam o cuenta hackeada."""
    return any(p.search(texto) for p in _PATRONES_SPAM)


# ── Detección de diagnóstico / neurodivergencia ──────────────────────────────
_KEYWORDS_DIAGNOSTICO = [
    r'\btdah\b', r'\btea\b', r'\bautism', r'\bespectro\b', r'\basperger\b',
    r'\bd[eé]ficit\b', r'\bs[ií]ndrome\b', r'\bneurodiv', r'\bdiagn[oó]stic',
    r'\bpsic[oó]log', r'\bpsicopedag', r'\bfonoaudi[oó]log',
    r'\btera(pist|peuta|pia)\b', r'\bmedicad', r'\bmedicaci[oó]n\b',
    r'\bconcerta\b', r'\britalina\b', r'\batomoxetina\b',
]


def detectar_diagnostico(texto: str) -> bool:
    """Retorna True si el texto menciona diagnósticos o tratamientos neurodivergentes."""
    return any(re.search(p, texto.lower()) for p in _KEYWORDS_DIAGNOSTICO)


proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Lock por teléfono: evita race conditions con mensajes rápidos
_locks_telefono: dict[str, asyncio.Lock] = {}
_MAX_LOCKS = 200


def _obtener_lock(telefono: str) -> asyncio.Lock:
    """Retorna un lock exclusivo por teléfono (evita procesamiento paralelo)."""
    if telefono not in _locks_telefono:
        if len(_locks_telefono) > _MAX_LOCKS:
            # Limpiar los más viejos
            oldest = list(_locks_telefono.keys())[:50]
            for k in oldest:
                _locks_telefono.pop(k, None)
        _locks_telefono[telefono] = asyncio.Lock()
    return _locks_telefono[telefono]


# Rate limit por teléfono: máx 10 mensajes en 60 segundos
_rate_limit: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 60


def _check_rate_limit(telefono: str) -> bool:
    """Retorna True si el teléfono excede el rate limit."""
    import time as _time
    ahora = _time.time()
    if telefono not in _rate_limit:
        _rate_limit[telefono] = []
    # Limpiar entradas viejas
    _rate_limit[telefono] = [t for t in _rate_limit[telefono] if ahora - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit[telefono]) >= _RATE_LIMIT_MAX:
        return True
    _rate_limit[telefono].append(ahora)
    return False


# Guard: PRUEBA FENIX ya creada para este lead (evita duplicados)
_prueba_creada: set[str] = set()

# Admin en modo padre (flujo normal): si no está acá, admin queda en modo secre (solo comandos)
_admin_modo_padre: set[str] = set()

# Estado de asistencia pendiente: {telefono_admin: [{idx, record_id, tabla, nombre},...]}
_asistencia_pendiente: dict[str, list[dict]] = {}

# Estado de inscripción pendiente: {telefono_admin: {datos de prueba fenix...}}
_inscripcion_pendiente: dict[str, dict] = {}

# Estado de sesión de fotos (reconocimiento facial):
# {telefono: {"turno": "9:30", "media_ids": [...], "resultados": [...]}}
_fotos_sesion: dict[str, dict] = {}

# Estado de registro de cara pendiente: {telefono: "nombre del niño"}
_cara_pendiente: dict[str, str] = {}


async def _delay_humano(texto: str):
    """Simula tiempo de tipeo para que el agente no parezca un bot."""
    base = 1.0 + random.uniform(-0.5, 0.5)
    bonus = min(2.0, len(texto) / 150 * 0.5)
    await asyncio.sleep(max(0.3, base + bonus))


# Números que no reciben delay de análisis (admin/pruebas)
_PHONES_SIN_DELAY = {os.getenv("ADMIN_PHONE", "595982790407")}

import re

# (eliminado: _normalizar_numeros_lead_viejo, _contar_numeros_rompehielos, _delay_por_numeros
#  — ya no se usa menú de dolor 1-15/1-10)


import json
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

_TZ_PY = ZoneInfo("America/Asuncion")


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
        admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
        ok = await proveedor.enviar_mensaje(admin_phone, alerta)
        try:
            await notificar_llamada_urgente(telefono_lead, nombre_padre, wa_link)
        except Exception:
            pass
        return ok

    # Recordatorio de clase (default)
    hora = data.get("hora", "")
    msg = f"Hola! Te recordamos que hoy tenés tu clase a las {hora} en Fenix Kids 🥋 Te esperamos!"
    ok = await proveedor.enviar_mensaje(rec.telefono, msg)
    if ok:
        await guardar_mensaje(rec.telefono, "assistant", msg)
    return ok


async def _keepalive_admin_loop():
    """Manda mensaje al admin a las 9:00 y 22:00 PY para mantener ventana WhatsApp."""
    from datetime import datetime, timezone, timedelta
    _PY = timezone(timedelta(hours=-4))
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    while True:
        ahora = datetime.now(_PY)
        # Calcular próximo envío: 9:00 o 22:00
        hoy_9 = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
        hoy_22 = ahora.replace(hour=22, minute=0, second=0, microsecond=0)
        manana_9 = hoy_9 + timedelta(days=1)
        proximos = [t for t in [hoy_9, hoy_22, manana_9] if t > ahora]
        proximo = min(proximos)
        espera = (proximo - ahora).total_seconds()
        logger.info(f"[KEEPALIVE] Próximo envío en {espera/3600:.1f}h ({proximo.strftime('%H:%M')} PY)")
        await asyncio.sleep(espera)
        try:
            hora_label = datetime.now(_PY).strftime("%H:%M")
            await proveedor.enviar_mensaje(admin_phone, f"Fenix Kids activo {hora_label} PY 🟢")
            logger.info(f"[KEEPALIVE] Enviado a admin")
        except Exception as e:
            logger.error(f"[KEEPALIVE] Error: {e}")


async def _recordatorios_loop():
    """Loop que cada 60s revisa recordatorios pendientes en PostgreSQL y los envía."""
    _ciclo = 0
    while True:
        try:
            pendientes = await obtener_recordatorios_pendientes(datetime.utcnow())
            for rec in pendientes:
                try:
                    await _enviar_recordatorio(rec)
                    await marcar_recordatorio_enviado(rec.id)
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


def _fire_and_forget(coro):
    """Lanza un task async con logging de errores."""
    task = asyncio.create_task(coro)
    task.add_done_callback(
        lambda t: logger.error(f"[BACKGROUND] Task falló: {t.exception()}")
        if not t.cancelled() and t.exception() else None
    )
    return task


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_group = os.getenv("TELEGRAM_GROUP_ID", "")
    # Recordatorios persistentes: polling cada 60s sobre PostgreSQL
    _recordatorios_task = _fire_and_forget(_recordatorios_loop())

    # Modo noche: procesar pendientes si arranca en horario diurno, luego loop 07:00
    if not es_horario_nocturno():
        try:
            await _procesar_pendientes_noche()
        except Exception as e:
            logger.error(f"[STARTUP] Error procesando pendientes nocturnos: {e}")
    _noche_task = _fire_and_forget(_noche_wakeup_loop(_procesar_pendientes_noche))

    # Follow-up leads: DESACTIVADO — Ivan prepara y envía manualmente a las 6am
    # _followup_task = _fire_and_forget(_followup_loop())

    # Follow-up masivo fotos: ONE-SHOT (ya ejecutado 5/5)
    _followup_fotos_task = _fire_and_forget(_followup_fotos_oneshot())
    # Follow-up video: ONE-SHOT 6:00 AM PY 2026-05-06
    _followup_video_task = _fire_and_forget(_followup_video_oneshot())

    # Keepalive: mantener ventana WhatsApp del admin abierta (cada 6h)
    _keepalive_task = _fire_and_forget(_keepalive_admin_loop())

    # Contenido social: polling CONTENIDO FENIX + calendario diario
    from agent.contenido_social import iniciar_contenido_social
    iniciar_contenido_social(proveedor)

    # Asistencia automática: enviar lista al terminar cada turno (sábados)
    _asistencia_task = _fire_and_forget(_asistencia_auto_loop())

    print(f"[STARTUP] FENIX KIDS — puerto {PORT}", flush=True)
    print(f"[STARTUP] Proveedor: {proveedor.__class__.__name__}", flush=True)
    print(
        f"[STARTUP][Telegram] TOKEN={'OK (' + tg_token[:8] + '...)' if tg_token else '*** NO CONFIGURADO ***'} | "
        f"GROUP_ID={tg_group if tg_group else '*** NO CONFIGURADO ***'}",
        flush=True,
    )
    yield
    _recordatorios_task.cancel()
    _noche_task.cancel()
    _keepalive_task.cancel()


app = FastAPI(title="FENIX KIDS ACADEMY — Agente WhatsApp", version="1.0.0", lifespan=lifespan)

_telegram_chats_vistos: dict[str, dict] = {}


# ── Auth admin (endpoints /debug, /telegram/setup, /stats) ────────────────────

async def _require_admin(x_admin_key: str | None = Header(default=None, alias="X-ADMIN-KEY")):
    """Valida header X-ADMIN-KEY contra la var de entorno ADMIN_API_KEY."""
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected:
        # Si no está configurada la clave, bloquear por seguridad
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY no configurada en el servidor")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# ── Health & stats ────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "fenix-kids-agent"}


@app.get("/stats")
async def estadisticas(_: bool = Depends(_require_admin)):
    stats = await obtener_estadisticas()
    return {"conversion": stats}


@app.get("/debug/{telefono}")
async def debug_lead(telefono: str, _: bool = Depends(_require_admin)):
    historial = await obtener_historial(telefono, limite=50)
    agent, modo = await obtener_agent_actual(telefono)
    familia_id = await obtener_familia_id(telefono)
    convertido = await esta_convertido(telefono)
    # Topic de Telegram
    topic_info = None
    try:
        from agent.telegram_bridge import obtener_topic
        topic = await obtener_topic(telefono)
        if topic:
            topic_info = {
                "topic_id": topic.topic_id,
                "nombre": topic.nombre,
                "group_id": topic.group_id,
            }
    except Exception:
        pass
    return {
        "telefono": telefono,
        "mensajes_totales": len(historial),
        "agent_actual": agent,
        "modo_nixie": modo,
        "familia_id": familia_id,
        "esta_convertido": convertido,
        "topic_telegram": topic_info,
        "ultimos_5": historial[-5:] if len(historial) >= 5 else historial,
    }


@app.post("/restaurar-aurora/{telefono}")
async def restaurar_aurora(telefono: str, _: bool = Depends(_require_admin)):
    """Restaura un número a Aurora sin borrar historial."""
    familia = await buscar_familia_por_telefono(telefono)
    if familia:
        await guardar_familia_id(telefono, familia["id"])
    await actualizar_agent_actual(telefono, "aurora", "cliente_inscripto")
    await reactivar_dorita(telefono)
    return {
        "status": "ok",
        "telefono": telefono,
        "agent": "aurora",
        "familia_id": familia["id"] if familia else None,
    }


@app.get("/diagnostico-audio")
async def debug_diagnostico_audio(_: bool = Depends(_require_admin)):
    """Diagnostica paso a paso por qué los audios podrían fallar."""
    import httpx
    resultado = {}

    # 1. Variables de entorno
    meta_token = os.getenv("META_ACCESS_TOKEN", "")
    media_token = os.getenv("META_MEDIA_TOKEN", "")
    groq_key = os.getenv("GROQ_API_KEY", "")
    phone_id = os.getenv("META_PHONE_NUMBER_ID", "")
    resultado["meta_token"] = f"{'OK (' + meta_token[:15] + '...)' if meta_token else '*** NO CONFIGURADO ***'}"
    resultado["meta_media_token"] = f"{'OK (' + media_token[:15] + '...)' if media_token else '*** NO CONFIGURADO — audios no van a funcionar ***'}"
    resultado["token_para_media"] = f"{'META_MEDIA_TOKEN' if media_token else 'META_ACCESS_TOKEN'} (se usa para descargar audio/imagen)"
    resultado["groq_key"] = f"{'OK (' + groq_key[:10] + '...)' if groq_key else '*** NO CONFIGURADO ***'}"
    resultado["phone_number_id"] = phone_id or "*** NO CONFIGURADO ***"

    # 2. Probar que el token de Meta funciona (GET al phone_number_id)
    if meta_token and phone_id:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"https://graph.facebook.com/v21.0/{phone_id}",
                    headers={"Authorization": f"Bearer {meta_token}"}
                )
                resultado["meta_api_test"] = {
                    "status": r.status_code,
                    "response": r.json() if r.status_code == 200 else r.text[:300],
                }
            except Exception as e:
                resultado["meta_api_test"] = {"error": str(e)}

    # 3. Probar que Groq responde
    if groq_key:
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}"}
                )
                resultado["groq_api_test"] = {
                    "status": r.status_code,
                    "ok": r.status_code == 200,
                }
            except Exception as e:
                resultado["groq_api_test"] = {"error": str(e)}

    # 4. Buscar último audio recibido en historial (cualquier lead)
    from agent.memory import async_session, Mensaje
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(Mensaje).where(Mensaje.content == "[audio]").order_by(Mensaje.id.desc()).limit(5)
        )
        audios = result.scalars().all()
        resultado["ultimos_audios_recibidos"] = [
            {"telefono": a.telefono, "id": a.id, "timestamp": str(a.timestamp)}
            for a in audios
        ] if audios else "Ningún [audio] encontrado en historial"

    return resultado


@app.get("/test-audio/{media_id}")
async def test_audio_download(media_id: str, _: bool = Depends(_require_admin)):
    """Prueba descargar y transcribir un media_id específico."""
    import httpx
    resultado = {"media_id": media_id}
    meta_token = os.getenv("META_ACCESS_TOKEN", "")
    if not meta_token:
        return {"error": "META_ACCESS_TOKEN no configurado"}

    # Paso 1: obtener URL
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(
                f"https://graph.facebook.com/v21.0/{media_id}",
                headers={"Authorization": f"Bearer {meta_token}"}
            )
            resultado["paso1_status"] = r.status_code
            resultado["paso1_response"] = r.json() if r.status_code == 200 else r.text[:500]
            if r.status_code != 200:
                return resultado

            url = r.json().get("url")
            mime = r.json().get("mime_type", "?")
            resultado["media_url"] = url[:50] + "..." if url else None
            resultado["mime_type"] = mime

            # Paso 2: descargar
            if url:
                r2 = await client.get(url, headers={"Authorization": f"Bearer {meta_token}"})
                resultado["paso2_status"] = r2.status_code
                resultado["paso2_bytes"] = len(r2.content) if r2.status_code == 200 else 0
                if r2.status_code != 200:
                    resultado["paso2_error"] = r2.text[:300]
        except Exception as e:
            resultado["error"] = str(e)

    return resultado


@app.get("/resumen-followup")
async def resumen_followup(_: bool = Depends(_require_admin)):
    """
    Revisa todos los leads con 1ER FOLLOWUP checked.
    Para cada uno, checkea el historial para ver si respondieron después del 5 de mayo.
    Marca RESPONDIO FU1 en Airtable y muestra resumen.
    """
    import httpx as _httpx_fu
    from datetime import datetime, timezone
    from agent.memory import async_session, Mensaje
    from sqlalchemy import select as sa_select

    base_id = os.getenv("AIRTABLE_BASE_ID")
    api_key = os.getenv("AIRTABLE_API_KEY")

    # Buscar todos los leads con 1ER FOLLOWUP checked
    formula = "{1ER FOLLOWUP}=TRUE()"
    all_records = []
    offset_r = None
    while True:
        from urllib.parse import quote
        params = f"filterByFormula={quote(formula)}&pageSize=100"
        if offset_r:
            params += f"&offset={offset_r}"
        url = f"https://api.airtable.com/v0/{base_id}/LEADS%20FENIX?{params}"
        async with _httpx_fu.AsyncClient(timeout=15) as cl:
            r = await cl.get(url, headers={"Authorization": f"Bearer {api_key}"})
            data = r.json()
        all_records.extend(data.get("records", []))
        offset_r = data.get("offset")
        if not offset_r:
            break

    # Fecha del masivo: 5 de mayo 2026
    fecha_masivo = datetime(2026, 5, 5, 9, 0, 0)

    resultados = []
    actualizados = 0
    for rec in all_records:
        fields = rec.get("fields", {})
        telefono = fields.get("TELEFONO", "")
        nombre = fields.get("NOMBRE RESPONSABLE", "") or ""
        nombre_hijo = fields.get("NOMBRE NIÑO", "") or ""
        conversion = fields.get("CONVERSION", "")
        respondio = fields.get("RESPONDIO FU1", False)

        if not telefono:
            continue

        # Buscar en DB si hay mensajes del USER después del 5 de mayo 9:00
        respondio_despues = False
        pago_post_fu = False
        ultimo_msg_user = None
        async with async_session() as session:
            # ¿Respondió?
            query = (
                sa_select(Mensaje)
                .where(Mensaje.telefono == telefono)
                .where(Mensaje.role == "user")
                .where(Mensaje.timestamp > fecha_masivo)
                .order_by(Mensaje.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(query)
            msg = result.scalar_one_or_none()
            if msg:
                respondio_despues = True
                ultimo_msg_user = msg.timestamp.isoformat()[:16]

            # ¿Pagó DESPUÉS del followup? (buscar "pago confirmado" del assistant después del 5/5)
            if conversion == "PAGO":
                query_pago = (
                    sa_select(Mensaje)
                    .where(Mensaje.telefono == telefono)
                    .where(Mensaje.role == "assistant")
                    .where(Mensaje.content.ilike("%pago confirmado%"))
                    .where(Mensaje.timestamp > fecha_masivo)
                    .limit(1)
                )
                result_pago = await session.execute(query_pago)
                if result_pago.scalar_one_or_none():
                    pago_post_fu = True

        # Marcar RESPONDIO FU1 en Airtable si respondió y no estaba marcado
        if respondio_despues and not respondio:
            try:
                async with _httpx_fu.AsyncClient(timeout=10) as cl:
                    await cl.patch(
                        f"https://api.airtable.com/v0/{base_id}/LEADS%20FENIX/{rec['id']}",
                        json={"fields": {"RESPONDIO FU1": True}},
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    )
                actualizados += 1
                respondio = True
            except Exception:
                pass

        resultados.append({
            "telefono": telefono,
            "nombre": f"{nombre} ({nombre_hijo})" if nombre_hijo else nombre,
            "conversion": conversion,
            "respondio": respondio_despues,
            "pago_post_fu": pago_post_fu,
            "ultimo_msg_post_fu": ultimo_msg_user,
        })

    # Stats
    total = len(resultados)
    respondieron = sum(1 for r in resultados if r["respondio"])
    no_respondieron = total - respondieron
    pagaron_post_fu = sum(1 for r in resultados if r["pago_post_fu"])
    pagaron_antes = sum(1 for r in resultados if r["conversion"] == "PAGO" and not r["pago_post_fu"])
    contactados = sum(1 for r in resultados if r["conversion"] == "CONTACTADO")
    consultas = sum(1 for r in resultados if r["conversion"] == "CONSULTA")

    return {
        "resumen": {
            "total_1er_followup": total,
            "respondieron": respondieron,
            "no_respondieron": no_respondieron,
            "tasa_respuesta": f"{respondieron/total*100:.1f}%" if total else "0%",
            "pagaron_POST_followup": pagaron_post_fu,
            "pagaron_ANTES_followup": pagaron_antes,
            "contactados_esperando_pago": contactados,
            "consultas_sin_avance": consultas,
            "airtable_actualizados": actualizados,
        },
        "respondieron": sorted(
            [r for r in resultados if r["respondio"]],
            key=lambda r: r["ultimo_msg_post_fu"] or "", reverse=True
        ),
        "no_respondieron": [r for r in resultados if not r["respondio"]],
    }


@app.get("/conversacion/{telefono}")
async def conversacion_completa(telefono: str, _: bool = Depends(_require_admin)):
    """Historial completo de una conversación con timestamps — para análisis de flujo."""
    from agent.memory import async_session, Mensaje
    from sqlalchemy import select as sa_select
    async with async_session() as session:
        query = (
            sa_select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.asc())
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()

    agent, modo = await obtener_agent_actual(telefono)
    return {
        "telefono": telefono,
        "agent_actual": agent,
        "modo_nixie": modo,
        "total_mensajes": len(mensajes),
        "conversacion": [
            {
                "rol": msg.role,
                "texto": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            }
            for msg in mensajes
        ],
    }


# ── Detección de activación / handoff / confirmación ────────────────────────

_CLAVES_AURORA = [
    "nixi", "hola nixi", "quiero hablar con nixi",
    "quiero reservar con nixi", "quiero agendar con nixi",
    "hablar con aurora", "reservar con aurora", "agendar con aurora",
]

# Teléfonos que ya pasaron por el flujo de registro/verificación (una vez por número)
_registro_ya_iniciado: set[str] = set()


def _detectar_registro(texto: str, telefono: str = "") -> bool:
    """El padre quiere registrarse. Solo si menciona 'aurora' explícitamente. Una vez por número."""
    if telefono and telefono in _registro_ya_iniciado:
        return False
    t = texto.lower()
    return "aurora" in t


def _detectar_activacion_aurora(texto: str) -> bool:
    """El padre escribió directamente a Aurora."""
    t = texto.lower()
    return any(k in t for k in _CLAVES_AURORA)


def _detectar_handoff_ivan_aurora(respuesta: str) -> bool:
    """Ivan dijo 'En breve te contacta AURORA' — señal de transferencia."""
    t = respuesta.lower()
    return "en breve te contacta aurora" in t or "te contacta aurora" in t


# ── Diagnóstico diferido (delay 3 min después de recibir edad) ────────────────

_diagnostico_pendiente: dict[str, asyncio.Task] = {}
_DELAY_DIAGNOSTICO = 180  # 3 minutos
_afiche_enviado: set[str] = set()  # teléfonos a los que ya se envió afiche


def _cancelar_diagnostico_pendiente(telefono: str):
    """Cancela el diagnóstico pendiente si existe."""
    task = _diagnostico_pendiente.pop(telefono, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"[DIAG] Diagnóstico pendiente cancelado para {telefono}")


def _detectar_respuesta_edad(texto: str, historial: list[dict]) -> bool:
    """Detecta si el padre está respondiendo a la pregunta de edad de Ivan."""
    if not historial:
        return False
    ultimo = historial[-1]
    if ultimo.get("role") != "assistant":
        return False
    contenido = ultimo.get("content", "").lower()
    if not re.search(r'cu[aá]ntos\s+a[ñn]os', contenido):
        return False
    # El padre respondió con número o "X años"
    t = texto.strip()
    if re.fullmatch(r'\d{1,2}', t) and 2 <= int(t) <= 15:
        return True
    if re.search(r'\b\d{1,2}\s*(?:años|añitos|a[ñn]os)', t, re.IGNORECASE):
        return True
    return False


def _diagnostico_ya_enviado(historial: list[dict]) -> bool:
    """Detecta si Ivan ya envió el diagnóstico/cierre emocional mirando el historial."""
    for msg in historial:
        if msg.get("role") == "assistant":
            t = msg.get("content", "").lower()
            # Ivan cierra con "qué te parece" + "pruebe/prueben" + "fenix"
            if "te parece" in t and "fenix" in t and ("prueb" in t or "parte de" in t):
                return True
    return False


def _padre_muestra_interes(texto: str) -> bool:
    """Detecta si el padre muestra interés después del diagnóstico."""
    t = texto.lower().strip()
    # Respuestas afirmativas / preguntas de agenda
    patrones = [
        r'^s[ií]$', r'^dale$', r'^ok$', r'^bueno$', r'^va$', r'^vamos$',
        r'^genial$', r'^perfecto$', r'^claro$', r'^obvio$', r'^por supuesto$',
        r'me interesa', r'quiero', r'quier[oa]', r'nos interesa',
        r'cuando', r'cuándo', r'cu[aá]ndo', r'horario', r'dias', r'días',
        r'agendar', r'reservar', r'inscrib', r'anotar',
        r'cómo es', r'como es', r'cómo hago', r'como hago',
        r'cuánto', r'cuanto', r'precio', r'costo', r'sale',
        r'probamos', r'prueba', r'puede probar', r'le gustar',
        r'que necesito', r'qué necesito',
    ]
    return any(re.search(p, t) for p in patrones)


def _padre_ya_pidio_precios(historial: list[dict]) -> bool:
    """Detecta si Ivan ya envió el afiche (padre pidió precios antes del diagnóstico)."""
    for msg in historial:
        if msg.get("role") == "assistant":
            t = msg.get("content", "").lower()
            if "te paso un afiche" in t:
                return True
    return False


# (eliminado: _contar_numeros_rompehielos_historial — ya no hay menú de dolor)


# ── Detección de pedido de llamada ───────────────────────────────────────────

_PATRONES_LLAMADA = [
    r"\bte\s+pued[oe]s?\s+llamar",
    r"\bpued[oe]\s+llamart?e",
    r"\bpodr[ií]a\s+llamart?e",
    r"\bpodemos\s+(?:llamar|hablar|llamarnos)",
    r"\bpod[eé]s\s+(?:llamar|hablar)",
    r"\bllamart?e(?:\s|$|\?)",
    r"\bllamarnos",
    r"\bhablar\s+(?:con\s+)?(?:vos|usted|contigo|ud|ivan|iván|el profe)",
    r"\buna\s+llamada",
    r"\bpor\s+tel[eé]fono",
    r"\btel[eé]fono\s+(?:tuyo|del profe|de iv[aá]n|personal)",
    r"\btu\s+n[uú]mero",
    r"\bme\s+llam[aá]s\??",
    r"\bque\s+te\s+llame",
    r"\bquiero\s+(?:hablar|llamar)",
    r"\bhablar\s+personalmente",
    r"\bllamada\s+telef[oó]nica",
    # Padre acepta oferta de llamada de Ivan
    r"\bpuedo\s+hablar",
    r"\bprefiero\s+(?:hablar|llamar|que me llam)",
    r"\bllamame",
    r"\bllam[aá]me",
    r"\bla\s+segunda",
    r"\bla\s+2da",
    r"\bsi\s*,?\s*llamame",
    r"\bdale\s+llamame",
    r"\bsi\s*,?\s*(?:podemos|podes)\s+hablar",
]

_REGEX_NOMBRE_PRESENTACION = re.compile(
    r"\b(?:soy|me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    re.IGNORECASE,
)
from agent.validar_nombre import es_nombre_valido as _validar_nombre_positivo


def _detectar_pedido_llamada(texto: str) -> bool:
    """Detecta si el padre está pidiendo hablar por teléfono / llamada."""
    t = texto.lower()
    return any(re.search(p, t) for p in _PATRONES_LLAMADA)


def _extraer_nombre_del_historial(historial: list[dict], texto_nuevo: str = "") -> str | None:
    """Busca el nombre del padre en mensajes 'soy X', 'me llamo X', etc."""
    textos = [texto_nuevo] if texto_nuevo else []
    textos += [m.get("content", "") for m in reversed(historial) if m.get("role") == "user"]
    for t in textos:
        m = _REGEX_NOMBRE_PRESENTACION.search(t)
        if not m:
            continue
        cand = m.group(1).strip().title()
        if _validar_nombre_positivo(cand):
            return cand
    return None


_REGEX_NOMBRE_HIJO = re.compile(
    r"(?:mi\s+hij[oa]\s+(?:se\s+llama\s+)?|se\s+llama\s+|(?:hijo|hija|nene|nena|niño|niña)\s+)([a-záéíóúñA-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[a-záéíóúñA-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    re.IGNORECASE,
)


# _NO_NOMBRE_HIJO eliminado — reemplazado por validación positiva en validar_nombre.py


def _es_nombre_hijo_valido(nombre: str) -> bool:
    """Valida nombre del hijo usando validación positiva (morfología + lista)."""
    return _validar_nombre_positivo(nombre)


def _extraer_nombre_hijo_historial(historial: list[dict]) -> str:
    """Busca nombre del hijo en mensajes del padre y respuestas del agente."""
    # Buscar en mensajes del padre primero (regex explícito)
    for m in reversed(historial):
        if m.get("role") == "user":
            match = _REGEX_NOMBRE_HIJO.search(m.get("content", ""))
            if match:
                candidato = match.group(1).strip().title()
                if _es_nombre_hijo_valido(candidato):
                    return candidato

    # Buscar cuando Ivan preguntó "cómo se llama tu hijo" y el padre respondió
    for i, m in enumerate(historial):
        if m.get("role") == "assistant" and re.search(
            r"c[oó]mo\s+se\s+llama\s+tu\s+hij[oa]", m.get("content", ""), re.IGNORECASE
        ):
            # El siguiente mensaje del usuario es la respuesta
            for j in range(i + 1, len(historial)):
                if historial[j].get("role") == "user":
                    resp = historial[j]["content"].strip()
                    # Ignorar si es una pregunta o pedido (no es un nombre)
                    _resp_lower = resp.lower()
                    _skip_words = ["precio", "costo", "como funciona", "horario",
                                   "ubicación", "ubicacion", "donde", "cuanto",
                                   "cuánto", "?", "info", "información",
                                   "tiene tdah", "tiene tea", "hiperactividad",
                                   "entre semana", "el monto"]
                    if any(sw in _resp_lower for sw in _skip_words):
                        break
                    # Puede ser "Maria", "se llama Maria", "Ivan, Maria", etc.
                    # Si tiene coma, el nombre del hijo suele ser la segunda parte
                    if "," in resp:
                        partes = [p.strip() for p in resp.split(",")]
                        # Tomar la última parte que parece nombre
                        for p in reversed(partes):
                            candidato = p.split()[0]
                            if _es_nombre_hijo_valido(candidato):
                                return candidato.title()
                    # Si es un nombre solo o "se llama X"
                    m_nombre = re.search(r"(?:se\s+llama\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", resp, re.IGNORECASE)
                    if m_nombre:
                        candidato = m_nombre.group(1).strip()
                        if _es_nombre_hijo_valido(candidato):
                            return candidato.title()
                    break

    # Buscar cuando Ivan usó el nombre del hijo en su respuesta ("cuántos años tiene Maria")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            match_edad = re.search(
                r"cu[aá]ntos\s+a[ñn]os\s+tiene\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
                m.get("content", ""), re.IGNORECASE,
            )
            if match_edad:
                nombre = match_edad.group(1).strip().title()
                if _es_nombre_hijo_valido(nombre):
                    return nombre

    # Buscar en respuestas del agente (ej: "Reserva confirmada ✅ Mateo...")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            contenido = m.get("content", "")
            match_conf = re.search(r"reserva confirmada[!✅\s]*\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", contenido, re.IGNORECASE)
            if match_conf:
                candidato = match_conf.group(1).strip().title()
                if _es_nombre_hijo_valido(candidato):
                    return candidato
    return "no mencionó"


_REGEX_EDAD = re.compile(
    r"(?:tiene|de|son)\s+(\d{1,2})\s*(?:años|añitos|a[ñn]os)",
    re.IGNORECASE,
)


def _extraer_edad_historial(historial: list[dict]) -> str:
    """Busca la edad del hijo en los mensajes del padre y respuestas de Ivan."""
    # 1. Buscar en mensajes del padre ("tiene 7 años", "7 añitos")
    for m in reversed(historial):
        if m.get("role") == "user":
            match = _REGEX_EDAD.search(m.get("content", ""))
            if match:
                return f"{match.group(1)} años"

    # 2. Buscar cuando Ivan preguntó edad y padre respondió solo un número
    for i, m in enumerate(historial):
        if m.get("role") == "assistant" and re.search(r'cu[aá]ntos\s+a[ñn]os', m.get("content", ""), re.IGNORECASE):
            for j in range(i + 1, len(historial)):
                if historial[j].get("role") == "user":
                    num_match = re.fullmatch(r'\d{1,2}', historial[j]["content"].strip())
                    if num_match and 2 <= int(num_match.group()) <= 15:
                        return f"{num_match.group()} años"
                    break

    # 3. Buscar en respuestas de Ivan ("a los 7 años", "Maria a los 5 años")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            match = re.search(r'a los\s+(\d{1,2})\s+a[ñn]os', m.get("content", ""), re.IGNORECASE)
            if match and 2 <= int(match.group(1)) <= 15:
                return f"{match.group(1)} años"

    return "no mencionó"


async def _alertar_pedido_llamada(telefono: str, historial: list[dict], texto_nuevo: str):
    """
    Manda alerta al admin cuando un lead pide hablar por teléfono.
    Doble canal: WhatsApp (ADMIN_PHONE) + Telegram (grupo agenda).
    Busca datos en Airtable (fuente de verdad), con fallback a regex del historial.
    """
    from urllib.parse import quote
    from agent.airtable_client import _get_records, _LEADS

    # Buscar datos en Airtable primero (fuente de verdad)
    nombre_padre = "no se presentó"
    nombre_hijo = "no mencionó"
    edad_hijo = "no mencionó"
    try:
        lead_records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if lead_records:
            fields = lead_records[0].get("fields", {})
            nombre_padre = fields.get("NOMBRE RESPONSABLE", "") or nombre_padre
            nombre_hijo = fields.get("NOMBRE NIÑO", "") or nombre_hijo
            edad_hijo = fields.get("EDAD", "") or edad_hijo
            if edad_hijo and edad_hijo != "no mencionó" and "año" not in edad_hijo:
                edad_hijo = f"{edad_hijo} años"
    except Exception as e:
        logger.error(f"[LLAMADA] Error consultando Airtable: {e}")

    # Fallback a regex si Airtable no tiene datos
    if nombre_padre == "no se presentó":
        nombre_padre = _extraer_nombre_del_historial(historial, texto_nuevo) or "no se presentó"
    if nombre_hijo == "no mencionó":
        nombre_hijo = _extraer_nombre_hijo_historial(historial)
    if edad_hijo == "no mencionó":
        edad_hijo = _extraer_edad_historial(historial)

    primer_nombre = nombre_padre.split()[0] if nombre_padre != "no se presentó" else ""
    mensaje_pre = f"Que tal {primer_nombre}, soy el profe Ivan te escribo desde mi personal, te puedo llamar ahora?" if primer_nombre else "Que tal, soy el profe Ivan te escribo desde mi personal, te puedo llamar ahora?"
    wa_link = f"https://wa.me/{telefono}?text={quote(mensaje_pre)}"

    alerta = (
        f"🚨 Urgente: Llamar a {nombre_padre}\n\n"
        f"👦 Hijo/a: {nombre_hijo}\n"
        f"🎂 Edad: {edad_hijo}\n\n"
        f"📲 {wa_link}"
    )

    # Canal 1: WhatsApp al admin (puede fallar si ventana 24h cerrada)
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    wa_ok = False
    try:
        wa_ok = await proveedor.enviar_mensaje(admin_phone, alerta)
        if wa_ok:
            logger.info(f"[LLAMADA] Alerta WhatsApp al admin {admin_phone}: OK")
        else:
            logger.warning(f"[LLAMADA] Alerta WhatsApp al admin FALLÓ (ventana 24h cerrada?)")
    except Exception as e:
        logger.error(f"[LLAMADA] Error WhatsApp admin: {e}")

    # Canal 2: Telegram grupo (SIEMPRE se manda, es el respaldo principal)
    tg_ok = False
    try:
        await notificar_llamada_urgente(telefono, nombre_padre, wa_link)
        tg_ok = True
        logger.info(f"[LLAMADA] Alerta Telegram enviada OK")
    except Exception as e:
        logger.error(f"[LLAMADA] Error Telegram: {e}")

    # Si ambos canales fallaron, loggear crítico
    if not wa_ok and not tg_ok:
        logger.critical(f"[LLAMADA] ⚠️ ALERTA NO ENTREGADA a ningún canal para {telefono}")


def _detectar_confirmacion_aurora(respuesta: str) -> list[dict]:
    """
    Detecta si Aurora confirmó una o más reservas.
    Retorna lista de {"fecha": ..., "hora": ...} (puede tener 0, 1 o más).
    """
    patrones = [
        r"reserva (?:confirmada|reagendada)[!✅\s]*.*?(?:el\s+)?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"tiene su lugar.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"quedaron reservados.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"listo[!✅\s🙌]*.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"qued[aá]s confirmad[oa].*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"agendam.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"est[aá] confirmado.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2}).*?(?:confirmad[oa]|reagendad[oa])",
        # Reagendamientos: "entrena el sábado X a las Y", "se pasa al sábado X a las Y"
        r"entrena (?:el\s+)?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"se pasa (?:al|para el)\s+s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"te (?:paso|cambio|muevo) (?:al|para el)\s+s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"(?:queda|quedás) (?:para (?:el )?|el )?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
    ]
    # Patrones sin fecha (cambio de hora mismo día): capturan solo hora, fecha = "hoy"
    patrones_sin_fecha = [
        r"se pasa a las\s+(\d{1,2}[:h]\d{0,2})",
        r"te cambio a las\s+(\d{1,2}[:h]\d{0,2})",
        r"nos vemos a las\s+(\d{1,2}[:h]\d{0,2}).*?(?:hoy|mismo)",
        r"a las\s+(\d{1,2}[:h]\d{0,2}).*?hoy mismo",
        r"a las\s+(\d{1,2}[:h]\d{0,2})\s+en vez de",
        r"te (?:paso|muevo|cambio) a las\s+(\d{1,2}[:h]\d{0,2})",
    ]
    texto_lower = respuesta.lower()
    resultados = []
    fechas_vistas = set()
    for patron in patrones:
        for match in re.finditer(patron, texto_lower):
            fecha = match.group(1).strip()
            hora = match.group(2).strip()
            key = f"{fecha}|{hora}"
            if key not in fechas_vistas:
                fechas_vistas.add(key)
                resultados.append({"fecha": fecha, "hora": hora})
    # Cambio de hora sin fecha → usar "hoy" como fecha
    if not resultados:
        for patron in patrones_sin_fecha:
            match = re.search(patron, texto_lower)
            if match:
                hora = match.group(1).strip()
                resultados.append({"fecha": "hoy", "hora": hora})
                break
    return resultados


# ── WhatsApp webhook ──────────────────────────────────────────────────────────

@app.get("/webhook")
async def webhook_verificacion(request: Request):
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


# ── KILL SWITCH — poner en True para frenar TODAS las respuestas ──────────────
AGENTE_PAUSADO = os.getenv("AGENTE_PAUSADO", "false").lower() == "true"


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Handler ultra-rápido: parsea, deduplica, lanza tasks async y responde 200 OK.
    Meta espera respuesta en < 20s — el procesamiento real puede tardar minutos
    (delays por números del rompehielos, Claude API, etc.) así que va en background.
    """
    if AGENTE_PAUSADO:
        logger.warning("[KILL SWITCH] Agente pausado — ignorando webhook")
        return {"status": "ok"}
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            # Deduplicación: registrar ANTES en PostgreSQL + procesar en background
            # Si el procesamiento falla, se borra la dedup para permitir reintento.
            # IMPORTANTE: responder 200 rápido (<5s) para que Meta no reintente.
            if msg.mensaje_id:
                if await mensaje_ya_procesado(msg.mensaje_id):
                    continue
                await registrar_mensaje_procesado(msg.mensaje_id)

            # Rate limit por teléfono
            if _check_rate_limit(msg.telefono):
                logger.warning(f"[RATE LIMIT] {msg.telefono} excede {_RATE_LIMIT_MAX} msgs/{_RATE_LIMIT_WINDOW}s")
                continue

            # Procesamiento en background — responder 200 rápido a Meta
            _fire_and_forget(_procesar_mensaje_webhook(msg))

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}", exc_info=True)
        return {"status": "error"}


async def _build_contexto_aurora(familia: dict, telefono: str = "") -> str:
    """Arma el contexto completo de una familia para inyectar en Aurora."""
    campos = familia.get("fields", {})

    def _primer_nombre(nombre: str) -> str:
        """Retorna solo el primer nombre (sin apellido ni segundo nombre)."""
        return nombre.strip().split()[0] if nombre and nombre.strip() else ""

    # Detectar quién escribe por teléfono — apodo primero, sino solo primer nombre
    _es_padre = telefono and (
        campos.get("CELL PADRE") == telefono or campos.get("CELL LIMPIO PADRE") == telefono
    )
    _es_madre = telefono and (
        campos.get("CELL MADRE") == telefono or campos.get("CELL LIMPIO MADRE") == telefono
    )
    if _es_padre:
        quien_escribe = campos.get("APODO PADRE", "").strip() or _primer_nombre(campos.get("NOMBRE PADRE", ""))
        es_genero = "papá"
    elif _es_madre:
        quien_escribe = campos.get("APODO MADRE", "").strip() or _primer_nombre(campos.get("NOMBRE MADRE", ""))
        es_genero = "mamá"
    else:
        quien_escribe = (
            campos.get("APODO PADRE", "").strip() or _primer_nombre(campos.get("NOMBRE PADRE", ""))
            or campos.get("APODO MADRE", "").strip() or _primer_nombre(campos.get("NOMBRE MADRE", ""))
        )
        es_genero = "padre/madre"

    # Datos de quien escribe
    nombre_desconocido = not quien_escribe
    if nombre_desconocido:
        datos_quien_escribe = "Nombre: (no registrado todavía — PEDIRLO PRIMERO), género: desconocido"
    else:
        datos_quien_escribe = f"Nombre: {quien_escribe}, género: {es_genero}"

    # Datos del padre
    datos_padre = []
    if campos.get("NOMBRE PADRE"):
        p = f"PADRE: {campos.get('NOMBRE PADRE', '')} {campos.get('APELLIDO PADRE', '')}".strip()
        if campos.get("APODO PADRE"):
            p += f" (apodo: {campos['APODO PADRE']})"
        if campos.get("CI PADRE"):
            p += f", CI: {campos['CI PADRE']}"
        if campos.get("CELL PADRE"):
            p += f", cel: {campos['CELL PADRE']}"
        if campos.get("EMAIL PADRE"):
            p += f", email: {campos['EMAIL PADRE']}"
        if campos.get("FECHA NACIMIENTO PADRE"):
            p += f", nac: {campos['FECHA NACIMIENTO PADRE']}"
        datos_padre.append(p)

    # Datos de la madre
    if campos.get("NOMBRE MADRE"):
        m = f"MADRE: {campos.get('NOMBRE MADRE', '')} {campos.get('APELLIDO MADRE', '')}".strip()
        if campos.get("APODO MADRE"):
            m += f" (apodo: {campos['APODO MADRE']})"
        if campos.get("CI MADRE"):
            m += f", CI: {campos['CI MADRE']}"
        if campos.get("CELL MADRE"):
            m += f", cel: {campos['CELL MADRE']}"
        if campos.get("EMAIL MADRE"):
            m += f", email: {campos['EMAIL MADRE']}"
        if campos.get("FECHA NACIMIENTO MADRE"):
            m += f", nac: {campos['FECHA NACIMIENTO MADRE']}"
        datos_padre.append(m)

    # Datos de los hijos
    hijos_raw = await obtener_ninos_de_familia(familia["id"])
    hijos_info = []
    nombres_hijos_display = []
    for i, h in enumerate(hijos_raw, 1):
        nombre_display = h["apodo"] or h["nombre"]
        nombres_hijos_display.append(nombre_display)
        info = f"HIJO {i}: {h['nombre']} {h['apellido']}".strip()
        if h["apodo"]:
            info += f" (apodo: {h['apodo']})"
        if h["ci"]:
            info += f", CI: {h['ci']}"
        if h["fecha_nacimiento"]:
            info += f", nac: {h['fecha_nacimiento']}"
        if h["sexo"]:
            info += f", sexo: {h['sexo']}"
        if h["talla_remera"]:
            info += f", talla: {h['talla_remera']}"
        hijos_info.append(info)

    contexto = (
        f"CONTEXTO FAMILIA INSCRIPTA:\n"
        f"Quien escribe: {datos_quien_escribe}\n"
        f"Hijos ({len(hijos_raw)}): {', '.join(nombres_hijos_display) if nombres_hijos_display else 'ninguno registrado aún'}\n"
        f"\nDATOS COMPLETOS PARA VERIFICACIÓN:\n"
    )
    for dp in datos_padre:
        contexto += f"  {dp}\n"
    for hi in hijos_info:
        contexto += f"  {hi}\n"
    if not hijos_info:
        contexto += "  (sin hijos registrados)\n"

    # Reservas activas de esta familia
    try:
        from agent.airtable_client import buscar_reservas_familia
        from datetime import date as _hoy_cls
        reservas_fam = await buscar_reservas_familia(familia["id"])
        # Filtrar solo futuras (desde hoy)
        _hoy_str = _hoy_cls.today().isoformat()
        reservas_futuras = [r for r in reservas_fam if r.get("fecha", "") >= _hoy_str]
        if reservas_futuras:
            contexto += "\nRESERVAS ACTIVAS DE ESTA FAMILIA:\n"
            for r in sorted(reservas_futuras, key=lambda x: x.get("fecha", "")):
                _nombre = r.get("nombre_nino", "?")
                _fecha = r.get("fecha", "?")
                _hora = r.get("hora", "?")
                try:
                    _fd = _hoy_cls.fromisoformat(_fecha)
                    _fecha_label = f"Sábado {_fd.day}/{_fd.month}"
                except Exception:
                    _fecha_label = _fecha
                contexto += f"  📅 {_nombre}: {_fecha_label} a las {_hora}h\n"
        else:
            contexto += "\nRESERVAS ACTIVAS: ninguna\n"
    except Exception as e:
        logger.error(f"[AURORA] Error cargando reservas familia: {e}")

    # Niños agendados por horario (próximos sábados)
    try:
        from datetime import date as _date_cls
        horarios = await obtener_horarios_disponibles(max_horarios=6)
        if horarios:
            contexto += "\nNIÑOS AGENDADOS POR HORARIO:\n"
            for hor in horarios:
                fecha_iso = hor.get("fecha", "")
                hora = hor.get("hora", "")
                if not fecha_iso or not hora:
                    continue
                ninos_hor = await obtener_ninos_por_horario(fecha_iso, hora)
                _fd = _date_cls.fromisoformat(fecha_iso)
                fecha_label = f"Sábado {_fd.day}/{_fd.month}"
                if ninos_hor:
                    nombres_lista = [f"{n['nombre']} {n['apellido']} ({n['edad']})" if n['edad'] else f"{n['nombre']} {n['apellido']}" for n in ninos_hor]
                    contexto += f"  {fecha_label} {hora}h: {', '.join(nombres_lista)}\n"
                else:
                    contexto += f"  {fecha_label} {hora}h: (nadie todavía)\n"
    except Exception as e:
        logger.error(f"[AURORA] Error cargando niños por horario: {e}")

    # Redes sociales (para opción 5 del menú)
    try:
        redes = await obtener_redes()
        if redes:
            contexto += "\nREDES SOCIALES:\n"
            for r in redes:
                icono = r.get("icono", "")
                red = r.get("red", "")
                perfil = r.get("perfil", "")
                if red and perfil:
                    contexto += f"  {icono} {red}: {perfil}\n"
    except Exception as e:
        logger.error(f"[AURORA] Error cargando redes: {e}")

    return contexto


async def _procesar_mensaje_webhook(msg):
    """
    Procesa un mensaje entrante en background (fuera del ciclo del webhook Meta).

    Flujo:
    1. Detectar comando reset ("holayosoyfenix"/"holayosoylasalsa")
    2. Cancelar recordatorios/seguimientos pendientes
    3. Espejo en Telegram — si Ivan está activo no responde el agente
    4. Protección prompt injection
    5. Modo nocturno (23:00–07:00 PY)
    6. Transcribir audio si aplica
    7. Detectar activación directa de Aurora
    8. Lead nuevo → crear en LEADS
    9. Generar respuesta con Ivan o Aurora
    10. Detectar handoff / extraer formulario / confirmación de reserva
    11. Guardar mensajes + enviar respuesta + espejo en Telegram
    """
    telefono = msg.telefono
    texto = msg.texto.strip()

    logger.info(f"[WA] {telefono}: {texto[:80]}")

    # Lock por teléfono: evita que mensajes rápidos se procesen en paralelo
    async with _obtener_lock(telefono):
      await _procesar_mensaje_interno(telefono, texto, msg)


async def _procesar_mensaje_interno(telefono: str, texto: str, msg):
    """Procesamiento real del mensaje, protegido por lock de teléfono."""
    try:
        # Capturar ctwa_clid del anuncio CTWA (viene en el primer mensaje del lead)
        if hasattr(msg, 'ctwa_clid') and msg.ctwa_clid:
            from agent.memory import guardar_ctwa_clid
            await guardar_ctwa_clid(msg.telefono, msg.ctwa_clid)
            logger.info(f"[CAPI] ctwa_clid capturado para {msg.telefono}")

        # Capturar ad_source_id (ID del anuncio Meta) del referral
        if hasattr(msg, 'ad_source_id') and msg.ad_source_id:
            from agent.memory import guardar_ad_source_id
            await guardar_ad_source_id(msg.telefono, msg.ad_source_id)
            logger.info(f"[AD] ad_source_id capturado para {msg.telefono}: {msg.ad_source_id}")

        # ── Transcribir audio ANTES de todo (para que comandos y detectores usen texto real)
        if texto == "[audio]":
            _media_token = os.getenv("META_MEDIA_TOKEN", "")
            _debug_info = f"media_id={msg.media_id or 'NINGUNO'}, META_MEDIA_TOKEN={'SÍ' if _media_token else 'NO'}"
            logger.info(f"[AUDIO] Detectado de {telefono} — {_debug_info}")
            if msg.media_id:
                try:
                    audio_bytes, mime_type = await descargar_audio_whatsapp(msg.media_id)
                    _debug_info += f", descarga={len(audio_bytes) if audio_bytes else 0}bytes, mime={mime_type}"
                    if audio_bytes:
                        transcripcion = await transcribir_audio(audio_bytes, mime_type)
                        if transcripcion:
                            texto = transcripcion
                            _debug_info += f", transcripcion=OK"
                            logger.info(f"[AUDIO] Transcripto OK: {texto[:80]}")
                        else:
                            _debug_info += ", transcripcion=VACIA"
                            logger.warning(f"[AUDIO] Transcripción vacía para {msg.media_id}")
                    else:
                        _debug_info += ", descarga=FALLÓ"
                        logger.error(f"[AUDIO] No se pudo descargar media {msg.media_id}")
                except Exception as e:
                    _debug_info += f", ERROR={e}"
                    logger.error(f"[AUDIO] Error transcribiendo: {e}", exc_info=True)
            if texto == "[audio]":
                logger.warning(f"[AUDIO] Falló para {telefono}: {_debug_info}")

        # ── Comando "comandos" (solo admin) — lista de comandos disponibles ──
        admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
        if texto.lower().strip() == "comandos" and telefono == admin_phone:
            msg_comandos = (
                "⚙️ *COMANDOS ADMIN*\n\n"
                "📊 *Resumenes:*\n"
                "• `resumen anuncios` — métricas de anuncios Meta\n"
                "• `resumen anuncios hoy` / `ayer` / `[mes]`\n"
                "• `resumen reservas` — reservas del sábado próximo por turno\n"
                "• `resumen asis` / `resumen asis 10/5` — quién vino (presentes por turno)\n"
                "• `resumen prueba` / `resumen prueba 9/5` — dashboard pruebas (asis+pagos+seguimiento)\n"
                "• `resumen seguimiento` / `seguimiento 9/5` — estado mensajes personalizados\n"
                "• `resumen telegram` — reservas + link Telegram de cada conversación\n"
                "• `resumen followup` — mapa completo de FU\n\n"
                "✅ *Asistencia:*\n"
                "• `asis 9.30` / `asis 11` / `asis 15.30` — pasar lista por turno\n"
                "• `asistencia` — lista completa todos los turnos\n\n"
                "👨‍👩‍👧 *Inscripción:*\n"
                "• `cargar familia [nombre padre]` — inscribir familia desde PRUEBA\n\n"
                "📸 *Fotos (reconocimiento facial):*\n"
                "• `fotos 9:30` / `fotos 11` / `fotos 15:30` — modo fotos de clase\n"
                "• `registrar cara [nombre]` — registrar cara de un niño nuevo\n\n"
                "🔄 *Reset:*\n"
                "• `holayosoyfenix` — reset completo (conversación + Airtable)\n"
                "• `modo alumno` — reset conversación, simular padre inscripto\n"
                "• `modo padre` — activar flujo normal (diagnóstico/Claude)\n"
                "• `modo secre` — volver a solo comandos (default)\n\n"
                "📋 *Info:*\n"
                "• `comandos` — esta lista"
            )
            await proveedor.enviar_mensaje(telefono, msg_comandos)
            return

        # ── Comando reset (solo admin) ────────────────────────────────────
        _reset_phones = {admin_phone, "595982844548"}
        if texto.lower() == "holayosoyfenix" and telefono in _reset_phones:
            cancelar_seguimiento(telefono)
            cancelar_recordatorios(telefono)
            _cancelar_diagnostico_pendiente(telefono)
            _admin_modo_padre.discard(telefono)
            if telefono == admin_phone:
                # Admin: reset completo incluyendo Airtable
                contador = await eliminar_todo_de_telefono(telefono)
                await limpiar_estado_completo(telefono)
                resumen = (
                    f"Reset completo ✅\n"
                    f"Borrados: lead={contador['lead']}, pruebas={contador.get('pruebas', 0)}, "
                    f"familia={contador['familia']}, niños={contador['ninos']}, reservas={contador['reservas']}"
                )
            else:
                # No admin: solo limpiar estado local, NO tocar Airtable
                await limpiar_estado_completo(telefono)
                resumen = "Reset conversación ✅ (datos de Airtable intactos)"
            await proveedor.enviar_mensaje(telefono, resumen)
            topic_reset = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            if topic_reset:
                await enviar_a_topic(topic_reset, f"⚙️ RESET — {resumen}", telefono=telefono)
            return

        # ── Respuesta a asistencia pendiente (solo admin) ─────────────────
        if telefono == admin_phone and telefono in _asistencia_pendiente:
            _resp_asis = texto.strip().lower()
            if _resp_asis == "ok" or re.match(r'^[\d\s,]+$', _resp_asis):
                try:
                    await _procesar_respuesta_asistencia(telefono, _resp_asis)
                except Exception as e:
                    logger.error(f"[ASISTENCIA] Error: {e}")
                    await proveedor.enviar_mensaje(telefono, f"Error procesando asistencia: {e}")
                return

        # ── Respuesta a inscripción pendiente (solo admin) ────────────────
        if telefono == admin_phone and telefono in _inscripcion_pendiente:
            try:
                await _procesar_respuesta_inscripcion(telefono, texto)
            except Exception as e:
                logger.error(f"[INSCRIPCION] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error procesando inscripción: {e}")
                _inscripcion_pendiente.pop(telefono, None)
            return

        # ── Modo fotos: acumular imágenes para reconocimiento facial ─────
        if telefono == admin_phone and telefono in _fotos_sesion:
            sesion_actual = _fotos_sesion[telefono]
            # Esperando confirmación del resumen
            if sesion_actual.get("_esperando_confirmacion"):
                _resp = texto.lower().strip()
                if _resp in ("si", "sí", "dale", "confirmo", "ok"):
                    await _confirmar_fotos(telefono)
                    return
                elif _resp in ("no", "cancelar", "na"):
                    _fotos_sesion.pop(telefono, None)
                    await proveedor.enviar_mensaje(telefono, "Sesión de fotos cancelada.")
                    return
                # Cualquier otra cosa — cancelar y seguir
                _fotos_sesion.pop(telefono, None)
            # Acumulando fotos
            elif texto == "[imagen]" and msg.media_id:
                await _acumular_foto(telefono, msg.media_id)
                return
            elif texto.lower().strip() in ("listo", "ya", "eso es todo", "fin"):
                await _finalizar_fotos(telefono)
                return
            # Si escribe otra cosa que no es imagen, finalizar y seguir
            elif texto != "[imagen]":
                await _finalizar_fotos(telefono)
                # No hacer return — que siga procesando el texto como comando normal

        # ── Comando "fotos [turno]" — iniciar modo fotos (solo admin) ─────
        if telefono == admin_phone and re.match(r'^fotos\b', texto.lower().strip()):
            await _iniciar_modo_fotos(telefono, texto)
            return

        # ── Comando "registrar cara [nombre]" (solo admin) ────────────────
        if telefono == admin_phone and texto.lower().strip().startswith("registrar cara"):
            _nombre_cara = texto.strip()[len("registrar cara"):].strip()
            if _nombre_cara:
                _cara_pendiente[telefono] = _nombre_cara
                await proveedor.enviar_mensaje(telefono, f"Dale, mandá la foto de {_nombre_cara} para registrar su cara")
            else:
                await proveedor.enviar_mensaje(telefono, "Usá: registrar cara [nombre del niño]")
            return

        # ── Recibir foto para registrar cara ──────────────────────────────
        if telefono == admin_phone and telefono in _cara_pendiente and texto == "[imagen]" and msg.media_id:
            await _procesar_registro_cara(telefono, msg.media_id)
            return

        # ── Comando cargar familia (solo admin) ───────────────────────────
        if telefono == admin_phone and texto.lower().strip().startswith("cargar familia"):
            _resto = texto.strip()[len("cargar familia"):].strip()
            if not _resto:
                await proveedor.enviar_mensaje(telefono, "Usá: cargar familia [nombre] [plan] [monto] [matricula]\nEj: cargar familia Diana Jara trimestral full monto 690 matricula 50 sub")
                return
            try:
                await _iniciar_inscripcion(telefono, _resto)
            except Exception as e:
                logger.error(f"[INSCRIPCION] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error: {e}")
            return

        # ── Comando asistencia (solo admin) ───────────────────────────────
        _texto_cmd = texto.lower().strip().rstrip(".,!?")
        if telefono == admin_phone and ("asistencia" in _texto_cmd or "control asis" in _texto_cmd or _texto_cmd.startswith("asis ")):
            try:
                # Detectar turno específico: "asistencia 9:30", "asistencia 11", "asistencia 15:30"
                _turno_cmd = ""
                _m_turno = re.search(r'(\d{1,2}[:.]\d{2}|\d{1,2})', _texto_cmd)
                if _m_turno:
                    _t = _m_turno.group(1).replace(".", ":")
                    if ":" not in _t:
                        _t = f"{_t}:00" if _t != "9" else "9:30"
                    # Normalizar a turnos válidos
                    _turno_map = {"9:30": "9:30", "11:00": "11:00", "15:30": "15:30", "11": "11:00", "15": "15:30", "9": "9:30"}
                    _turno_cmd = _turno_map.get(_t, _t)
                await _generar_lista_asistencia(telefono, turno_especifico=_turno_cmd)
            except Exception as e:
                logger.error(f"[ASISTENCIA] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando asistencia: {e}")
            return

        # ── Comando resumen anuncios (solo admin) ──────────────────────────
        if telefono == admin_phone and "resumen" in _texto_cmd and "anuncio" in _texto_cmd:
            try:
                await _generar_resumen_anuncios(telefono, _texto_cmd)
            except Exception as e:
                logger.error(f"[RESUMEN] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando resumen: {e}")
            return

        # ── Comando resumen telegram (solo admin) ──────────────────────────
        if telefono == admin_phone and "resumen" in _texto_cmd and "telegram" in _texto_cmd:
            try:
                await _generar_resumen_telegram(telefono)
            except Exception as e:
                logger.error(f"[RESUMEN TELEGRAM] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando resumen telegram: {e}")
            return

        # ── Comando resumen reservas (solo admin) ─────────────────────────
        # Acepta: "resumen reservas", "resumen reservas 23/5", "resumen reservas 16/5"
        if telefono == admin_phone and "resumen" in _texto_cmd and "reserva" in _texto_cmd:
            _fecha_override = None
            _m_fecha_res = re.search(r'(\d{1,2})/(\d{1,2})', _texto_cmd)
            if _m_fecha_res:
                from datetime import date as _date_cls, datetime as _dt_cls, timezone as _tz_cls, timedelta as _td_cls
                _anio = _dt_cls.now(_tz_cls(_td_cls(hours=-3))).year
                try:
                    _fecha_override = _date_cls(_anio, int(_m_fecha_res.group(2)), int(_m_fecha_res.group(1)))
                except ValueError:
                    pass
            try:
                await _generar_resumen_reservas(telefono, fecha_override=_fecha_override)
            except Exception as e:
                logger.error(f"[RESUMEN RESERVAS] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando resumen reservas: {e}")
            return

        # ── Comando resumen asistencia (solo admin) ─────────────────────────
        # Acepta: "resumen asis", "resumen asis 10/5", "resumen asistencia"
        if telefono == admin_phone and "resumen" in _texto_cmd and ("asis" in _texto_cmd or "asistencia" in _texto_cmd):
            _fecha_asis = None
            _m_fecha_asis = re.search(r'(\d{1,2})/(\d{1,2})', _texto_cmd)
            if _m_fecha_asis:
                from datetime import date as _date_cls, datetime as _dt_cls, timezone as _tz_cls, timedelta as _td_cls
                _anio = _dt_cls.now(_tz_cls(_td_cls(hours=-3))).year
                try:
                    _fecha_asis = _date_cls(_anio, int(_m_fecha_asis.group(2)), int(_m_fecha_asis.group(1)))
                except ValueError:
                    pass
            try:
                await _generar_resumen_asistencia(telefono, fecha_override=_fecha_asis)
            except Exception as e:
                logger.error(f"[RESUMEN ASIS] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando resumen asistencia: {e}")
            return

        # ── Comando resumen prueba (solo admin) ────────────────────────────
        # Acepta: "resumen prueba", "resumen prueba 9/5"
        if telefono == admin_phone and "resumen" in _texto_cmd and "prueba" in _texto_cmd:
            _fecha_pr = None
            _m_fecha_pr = re.search(r'(\d{1,2})/(\d{1,2})', _texto_cmd)
            if _m_fecha_pr:
                from datetime import date as _date_cls, datetime as _dt_cls, timezone as _tz_cls, timedelta as _td_cls
                _anio = _dt_cls.now(_tz_cls(_td_cls(hours=-3))).year
                try:
                    _fecha_pr = _date_cls(_anio, int(_m_fecha_pr.group(2)), int(_m_fecha_pr.group(1)))
                except ValueError:
                    pass
            try:
                await _generar_resumen_prueba(telefono, fecha_override=_fecha_pr)
            except Exception as e:
                logger.error(f"[RESUMEN PRUEBA] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error: {e}")
            return

        # ── Comando resumen seguimiento (solo admin) ─────────────────────
        # Acepta: "resumen seguimiento", "seguimiento 9/5"
        if telefono == admin_phone and ("seguimiento" in _texto_cmd or "seguim" in _texto_cmd):
            _fecha_seg = None
            _m_fecha_seg = re.search(r'(\d{1,2})/(\d{1,2})', _texto_cmd)
            if _m_fecha_seg:
                from datetime import date as _date_cls, datetime as _dt_cls, timezone as _tz_cls, timedelta as _td_cls
                _anio = _dt_cls.now(_tz_cls(_td_cls(hours=-3))).year
                try:
                    _fecha_seg = _date_cls(_anio, int(_m_fecha_seg.group(2)), int(_m_fecha_seg.group(1)))
                except ValueError:
                    pass
            try:
                await _generar_resumen_seguimiento(telefono, fecha_override=_fecha_seg)
            except Exception as e:
                logger.error(f"[RESUMEN SEG] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error: {e}")
            return

        # ── Comando resumen followup (solo admin) ──────────────────────────
        if telefono == admin_phone and "resumen" in _texto_cmd and ("followup" in _texto_cmd or "follow" in _texto_cmd or "fu" in _texto_cmd.split()):
            try:
                await _generar_resumen_followup(telefono)
            except Exception as e:
                logger.error(f"[RESUMEN FU] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando resumen followup: {e}")
            return

        # ── Comando resumen seguimiento (solo admin) ─────────────────────
        # Acepta: "resumen seguimiento", "seguimiento 9/5"
        if telefono == admin_phone and ("seguimiento" in _texto_cmd or "seguim" in _texto_cmd):
            _fecha_seg = None
            _m_fecha_seg = re.search(r'(\d{1,2})/(\d{1,2})', _texto_cmd)
            if _m_fecha_seg:
                from datetime import date as _date_cls, datetime as _dt_cls, timezone as _tz_cls, timedelta as _td_cls
                _anio = _dt_cls.now(_tz_cls(_td_cls(hours=-3))).year
                try:
                    _fecha_seg = _date_cls(_anio, int(_m_fecha_seg.group(2)), int(_m_fecha_seg.group(1)))
                except ValueError:
                    pass
            try:
                await _generar_resumen_seguimiento(telefono, fecha_override=_fecha_seg)
            except Exception as e:
                logger.error(f"[RESUMEN SEG] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error: {e}")
            return

        # ── Comando modo alumno (solo admin) — reset sin tocar Airtable ───
        if texto.lower().replace(" ", "") == "modoalumno" and telefono == admin_phone:
            cancelar_seguimiento(telefono)
            cancelar_recordatorios(telefono)
            _cancelar_diagnostico_pendiente(telefono)
            await limpiar_estado_completo(telefono)
            # Pre-setear Aurora + cliente_inscripto para que el router no lo mande a Ivan
            await asignar_variante(telefono)  # crea la fila en ConversacionAB
            await actualizar_agent_actual(telefono, "aurora", "cliente_inscripto")
            _admin_modo_padre.add(telefono)  # activar flujo normal para que responda
            await proveedor.enviar_mensaje(
                telefono,
                "Modo alumno ✅\nConversación limpia, Airtable intacto.\nEscribí como si fueras un padre inscripto.\nEscribí 'modo secre' para volver a comandos."
            )
            topic_alumno = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            if topic_alumno:
                await enviar_a_topic(topic_alumno, "⚙️ MODO ALUMNO — reset conversación sin tocar Airtable", telefono=telefono)
            return

        # ── Botones del admin (confirmar/rechazar pago) ────────────────────
        if telefono == admin_phone and msg.es_boton:
            btn_titulo = texto.lower().strip()
            # Botones de seguimiento (seg_enviado_recXXX / seg_descartado_recXXX)
            btn_raw_id = getattr(msg, 'btn_id', '') or ''
            if btn_raw_id.startswith("seg_enviado_") or btn_raw_id.startswith("seg_descartado_"):
                await _procesar_boton_seguimiento(btn_raw_id)
                return
            if "confirmar" in btn_titulo or "rechazar" in btn_titulo:
                await _procesar_boton_pago(btn_titulo)
                return

        # ── Modo secre: admin siempre en modo comando, no responde como agente ─
        # Si el admin escribe algo que no matcheó ningún comando arriba, ignorar.
        # Solo "modo padre" activa el flujo normal (diagnóstico/Claude).
        if telefono == admin_phone:
            _texto_admin = texto.strip().lower().replace(" ", "")
            if _texto_admin == "modopadre":
                # Activar modo padre: limpiar estado y dejar que fluya como lead
                _admin_modo_padre.add(telefono)
                await proveedor.enviar_mensaje(
                    telefono,
                    "Modo padre ✅\nAhora te respondo como si fueras un padre. Escribí 'modo secre' para volver."
                )
                return
            if _texto_admin == "modosecre":
                _admin_modo_padre.discard(telefono)
                await proveedor.enviar_mensaje(telefono, "Modo secre ✅\nSolo comandos admin.")
                return
            if telefono not in _admin_modo_padre:
                # Guardar mensaje y espejear en Telegram, pero no responder
                logger.info(f"[ADMIN] Mensaje ignorado (modo secre): {texto[:50]}")
                return

        # ── Cancelar timers pendientes (NO el diagnóstico — ese se envía siempre)
        cancelar_seguimiento(telefono)

        # ── Si hay diagnóstico pendiente y el padre solo dice "ok/dale/gracias" → no responder
        if telefono in _diagnostico_pendiente:
            _t = texto.strip().lower().rstrip("!.,")
            _ACK_WORDS = {"ok", "dale", "genial", "perfecto", "gracias", "bueno", "listo",
                          "si", "sí", "bien", "claro", "de una", "joya", "ta", "va",
                          "esperare", "espero", "aguardo", "okey", "oka", "okis"}
            if _t in _ACK_WORDS:
                await guardar_mensaje(telefono, "user", texto)
                # Tracking ventana 24h
                try:
                    from agent.airtable_client import obtener_lead_record_id as _olri2, _patch as _p2, _LEADS as _L2
                    _lr2 = await _olri2(telefono)
                    if _lr2:
                        from datetime import datetime, timezone
                        await _p2(_L2, _lr2, {"ULTIMO MENSAJE": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    pass
                if topic_id:
                    await enviar_a_topic(topic_id, f"👤 {texto} (esperando diagnóstico)", telefono=telefono, group_override=_tg_group)
                logger.info(f"[DIAG] Padre dijo '{texto}' — ignorando, diagnóstico pendiente")
                return

        # (Transcripción de audio ya se hizo al inicio de la función)


        # ── Preparar nombre para Telegram (se usa después del router) ─────
        _topic_nombre = f"📱 {telefono}"
        try:
            _fam_tg = await buscar_familia_por_telefono(telefono)
            if _fam_tg:
                _campos_tg = _fam_tg.get("fields", {})
                if _campos_tg.get("CELL PADRE") == telefono or _campos_tg.get("CELL LIMPIO PADRE") == telefono:
                    _n = f"{_campos_tg.get('NOMBRE PADRE', '')} {_campos_tg.get('APELLIDO PADRE', '')}".strip()
                elif _campos_tg.get("CELL MADRE") == telefono or _campos_tg.get("CELL LIMPIO MADRE") == telefono:
                    _n = f"{_campos_tg.get('NOMBRE MADRE', '')} {_campos_tg.get('APELLIDO MADRE', '')}".strip()
                else:
                    _n = _campos_tg.get("FAMILIA", "")
                if _n:
                    _topic_nombre = f"📱 {_n}"
            else:
                from agent.airtable_client import _get_records, _LEADS
                _lr = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
                if _lr:
                    _nombre_lead = _lr[0].get("fields", {}).get("NOMBRE RESPONSABLE", "")
                    if _nombre_lead:
                        _topic_nombre = f"📱 {_nombre_lead}"
        except Exception:
            pass
        # Determinar grupo Telegram: familia o "Hola Aurora" → FLIAS, sino → LEADS
        _quiere_aurora = "aurora" in texto.lower()
        _tg_group = group_id_para_agente("aurora") if (_fam_tg or _quiere_aurora) else group_id_para_agente("ivan")
        # Telegram es best-effort: si falla, el agente sigue respondiendo
        topic_id = None
        try:
            topic_id = await obtener_o_crear_topic(telefono, _topic_nombre, group_override=_tg_group)
            if topic_id:
                # Espejo: si es imagen, reenviar la imagen real a Telegram
                if texto == "[imagen]" and hasattr(msg, "media_id") and msg.media_id:
                    try:
                        img_bytes, _ = await descargar_audio_whatsapp(msg.media_id)
                        if img_bytes:
                            await enviar_media_a_topic(topic_id, img_bytes, tipo="imagen", telefono=telefono, group_override=_tg_group)
                        else:
                            await enviar_a_topic(topic_id, f"👤 {texto}", telefono=telefono, group_override=_tg_group)
                    except Exception:
                        await enviar_a_topic(topic_id, f"👤 {texto}", telefono=telefono, group_override=_tg_group)
                else:
                    await enviar_a_topic(topic_id, f"👤 {texto}", telefono=telefono, group_override=_tg_group)
        except Exception as e:
            logger.error(f"[TELEGRAM] Error espejo entrante: {e}")

        # ── Guardar mensaje del usuario ANTES de procesar ──────────────
        # Así nunca se pierde un mensaje aunque algo crashee después.
        await guardar_mensaje(telefono, "user", texto)

        # ── Actualizar ULTIMO MENSAJE en Airtable (tracking ventana 24h) ──
        try:
            from agent.airtable_client import obtener_lead_record_id, _patch, _LEADS
            _lr_id_um = await obtener_lead_record_id(telefono)
            if _lr_id_um:
                from datetime import datetime, timezone
                await _patch(_LEADS, _lr_id_um, {"ULTIMO MENSAJE": datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass  # no bloquear el flujo por esto

        # ── Alerta diagnóstico: si padre menciona TDAH/TEA/etc → avisar admin ──
        if detectar_diagnostico(texto) and telefono != admin_phone:
            try:
                _nombre_diag = ""
                from agent.airtable_client import _get_records, _LEADS
                _lr_diag = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
                if _lr_diag:
                    _nombre_diag = _lr_diag[0].get("fields", {}).get("NOMBRE RESPONSABLE", "")
                # Link al topic de Telegram
                _tg_link = ""
                if topic_id and _tg_group:
                    _gid_abs = str(_tg_group).replace("-100", "")
                    _tg_link = f"\n💬 t.me/c/{_gid_abs}/{topic_id}"

                _alerta_diag = (
                    f"🚨 DIAGNÓSTICO MENCIONADO\n\n"
                    f"Lead: {_nombre_diag or telefono}\n"
                    f"Tel: {telefono}\n"
                    f"Mensaje: {texto[:200]}\n\n"
                    f"⚠️ El agente sigue respondiendo normal (frame parque).\n"
                    f"/silenciar → tomar control manual"
                    f"{_tg_link}"
                )
                if topic_id:
                    await enviar_a_topic(topic_id, _alerta_diag, telefono=telefono, group_override=_tg_group)
                _agenda_grp = int(os.getenv("TELEGRAM_AGENDA_GROUP_ID", "0"))
                if _agenda_grp:
                    await enviar_a_topic(0, _alerta_diag, group_override=_agenda_grp)
                logger.info(f"[DIAGNOSTICO] Detectado en {telefono}: {texto[:50]}")
            except Exception as e:
                logger.warning(f"[DIAGNOSTICO] Error enviando alerta: {e}")

        # ── Verificar si Ivan (admin) está respondiendo manualmente ──��────
        if not await dorita_esta_activa(telefono):
            logger.info(f"Agente silenciado para {telefono} — Ivan activo en Telegram")
            return

        # ── Detección de comprobante de pago ───────���─────────────────────
        historial_pago = await obtener_historial(telefono)
        if es_posible_comprobante(texto, historial_pago):
            await _procesar_comprobante(telefono, texto, msg.media_id, historial_pago, topic_id, _tg_group)
            return

        # ── Pedido de llamada → dos escenarios ─────────────────────────────
        #  1) Ivan ofreció llamar ("te puedo llamar") y padre acepta → "Super, te llamo"
        #  2) Padre pide llamar por su cuenta → "Aguantame un ratito, te llamo"
        if _detectar_pedido_llamada(texto):
            historial_previo = await obtener_historial(telefono)

            # Buscar nombre del padre en Airtable (fuente de verdad)
            primer_nombre = ""
            try:
                from agent.airtable_client import _get_records, _LEADS
                _lr = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
                if _lr:
                    _f = _lr[0].get("fields", {})
                    _nombre_at = _f.get("NOMBRE RESPONSABLE", "")
                    if _nombre_at:
                        primer_nombre = _nombre_at.split()[0]
            except Exception:
                pass
            # Fallback a regex
            if not primer_nombre:
                _nombre_regex = _extraer_nombre_del_historial(historial_previo, texto)
                primer_nombre = _nombre_regex.split()[0] if _nombre_regex else ""

            # Detectar si Ivan ofreció llamar en el mensaje anterior
            _ivan_ofrecio_llamar = False
            for _m in reversed(historial_previo):
                if _m.get("role") == "assistant":
                    _contenido_ivan = _m.get("content", "").lower()
                    if "te puedo llamar" in _contenido_ivan or "te explico mejor todo" in _contenido_ivan:
                        _ivan_ofrecio_llamar = True
                    break

            if _ivan_ofrecio_llamar:
                # Caso 1: Ivan ofreció, padre acepta
                respuesta = (
                    f"Super, te llamo ahora desde mi número personal {primer_nombre} 🤝"
                    if primer_nombre else
                    "Super, te llamo ahora desde mi número personal 🤝"
                )
            elif primer_nombre:
                # Caso 2: Padre pide por su cuenta
                respuesta = (
                    f"Ahora mismo no puedo atender llamadas, aguantame un ratito "
                    f"{primer_nombre} y te llamo desde mi línea personal 🤝"
                )
            else:
                respuesta = (
                    "Ahora mismo no puedo atender llamadas, aguantame un ratito "
                    "y te llamo desde mi línea personal 🤝"
                )
            await guardar_mensaje(telefono, "assistant", respuesta)
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
            # Alerta al admin (WhatsApp + Telegram) — busca datos en Airtable
            await _alertar_pedido_llamada(telefono, historial_previo, texto)
            # Espejar en Telegram del lead (datos ya están en la alerta)
            if topic_id:
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {respuesta}", telefono=telefono, group_override=_tg_group)
            logger.info(f"[LLAMADA] Pedido de llamada detectado de {telefono}")
            return

        # ── Detección de spam / scam / cuenta hackeada ─────────────────
        if _es_spam_o_scam(texto):
            logger.warning(f"[SPAM] Mensaje sospechoso de {telefono}: {texto[:100]}")
            # Silenciar — NO responder nada al padre
            await silenciar_dorita(telefono)
            # Alertar a Ivan en Telegram
            _spam_alerta = (
                f"🚨 SPAM/SCAM DETECTADO\n\n"
                f"Tel: {telefono}\n"
                f"Mensaje: {texto[:300]}\n\n"
                f"⚠️ Agente SILENCIADO automáticamente.\n"
                f"Posible cuenta hackeada.\n\n"
                f"/reactivar → volver a activar el agente"
            )
            if topic_id:
                await enviar_a_topic(topic_id, _spam_alerta, telefono=telefono, group_override=_tg_group)
            _agenda_grp = int(os.getenv("TELEGRAM_AGENDA_GROUP_ID", "0"))
            if _agenda_grp:
                try:
                    await enviar_a_topic(None, _spam_alerta, telefono=telefono, group_override=_agenda_grp)
                except Exception:
                    pass
            return

        # ── Protección prompt injection ───────────────────────────────────
        if _es_mensaje_sospechoso(texto):
            logger.warning(f"[INJECTION] Mensaje sospechoso de {telefono}: {texto[:100]}")
            await silenciar_dorita(telefono)
            _inj_alerta = (
                f"🚨 PROMPT INJECTION DETECTADO\n\n"
                f"Tel: {telefono}\n"
                f"Mensaje: {texto[:300]}\n\n"
                f"⚠️ Agente SILENCIADO automáticamente.\n"
                f"/reactivar → volver a activar el agente"
            )
            if topic_id:
                await enviar_a_topic(topic_id, _inj_alerta, telefono=telefono, group_override=_tg_group)
            return

        # ── Modo nocturno (23:00–07:00 PY) — admin y padres inscriptos sin límite
        if es_horario_nocturno() and telefono not in _PHONES_SIN_DELAY:
            # Padres inscriptos no tienen restricción nocturna
            _familia_nocturno = await buscar_familia_por_telefono(telefono)
            if not _familia_nocturno:
                historial_noche = await obtener_historial(telefono, limite=5)
                _tiene_actividad = len(historial_noche) > 0
                if not _tiene_actividad or not await tiene_noche_pendiente(telefono):
                    if not await tiene_noche_pendiente(telefono):
                        await proveedor.enviar_mensaje(telefono, MENSAJE_NOCHE)
                        await guardar_mensaje(telefono, "assistant", MENSAJE_NOCHE)
                        # Espejar mensaje nocturno a Telegram
                        if topic_id:
                            await enviar_a_topic(topic_id, f"🌙 IVAN: {MENSAJE_NOCHE}", telefono=telefono, group_override=_tg_group)
                    await asignar_variante(telefono)
                    await marcar_noche_pendiente(telefono)
                    return

        # ── Obtener historial (20 msgs — suficiente para contexto, reduce costos API)
        historial = await obtener_historial(telefono, limite=20)

        # ── Asignar variante (crea fila en ConversacionAB si no existe) ───
        _, es_nuevo = await asignar_variante(telefono)

        # ── Estado de la conversación ─────────────────────────────────────
        agent_actual, modo_nixie = await obtener_agent_actual(telefono)

        # ── Detección respuesta post-followup (ventana 24h) ───────────────
        # Si el lead está en CONTACTADO y ya recibió al menos 1 followup,
        # marcar que respondió y actualizar FECHA FOLLOWUP (resetea reloj 24h).
        if agent_actual == "ivan":
            try:
                from agent.airtable_client import _get_records, _LEADS, _patch
                _lr_fu = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
                if _lr_fu:
                    _f_fu = _lr_fu[0].get("fields", {})
                    _conv_fu = _f_fu.get("CONVERSION", "")
                    _seg_fu = _f_fu.get("SEGUIMIENTOS", 0) or 0
                    if _conv_fu == "CONTACTADO" and _seg_fu >= 1:
                        from datetime import datetime, timezone
                        _campos_fu = {"FECHA FOLLOWUP": datetime.now(timezone.utc).isoformat()}
                        if _seg_fu == 1:
                            _campos_fu["RESPONDIO FU1"] = True
                        elif _seg_fu >= 2:
                            _campos_fu["RESPONDIO FU2"] = True
                        await _patch(_LEADS, _lr_fu[0]["id"], _campos_fu)
                        logger.info(f"[FOLLOWUP] {telefono} respondió post-FU{_seg_fu} → ventana 24h reabierta")
            except Exception as e:
                logger.error(f"[FOLLOWUP] Error detectando respuesta post-FU: {e}")

        # ── "Hola Aurora" fuerza Aurora (una vez por número) ──────────────
        _quiere_registro = _detectar_registro(texto, telefono)
        if _quiere_registro and agent_actual != "aurora":
            _registro_ya_iniciado.add(telefono)
            familia_reg = await buscar_familia_por_telefono(telefono)
            if not familia_reg:
                fam_id_nuevo = await crear_familia({"padre": {"telefono": telefono}, "madre": {"telefono": telefono}})
                if fam_id_nuevo:
                    await guardar_familia_id(telefono, fam_id_nuevo)
                    logger.info(f"[REGISTRO] FAMILIA creada: {fam_id_nuevo}")
            agent_actual = "aurora"
            modo_nixie = "cliente_inscripto"
            await actualizar_agent_actual(telefono, "aurora", modo_nixie)
            logger.info(f"[REGISTRO] {telefono} → Aurora (forzado por 'Hola Aurora')")

        # ── Lead nuevo: router Ivan/Aurora por teléfono ───────────────────
        if es_nuevo:
            if agent_actual != "aurora":
                familia_inscripta = await buscar_familia_por_telefono(telefono)
                if familia_inscripta:
                    agent_actual = "aurora"
                    modo_nixie = "cliente_inscripto"
                    await actualizar_agent_actual(telefono, "aurora", modo_nixie)
                    logger.info(f"[ROUTER] {telefono} es inscripto → Aurora")
                else:
                    agent_actual = "ivan"
                    modo_nixie = None
                    logger.info(f"[ROUTER] {telefono} no inscripto → Ivan")
            record_id = await crear_lead(telefono, rompehielos="A")
            if record_id:
                await guardar_airtable_record_id(telefono, record_id)
            await actualizar_agent_lead(telefono, agent_actual.upper(), modo_nixie)

        # ── Actualizar grupo Telegram si el router cambió el agente ──────
        _tg_group = group_id_para_agente(agent_actual or "ivan")

        # ── Si es Aurora cliente_inscripto: inyectar contexto con sus hijos ──
        contexto_extra = None
        if agent_actual == "aurora" and modo_nixie == "cliente_inscripto":
            # Primero buscar por familia_id guardada (modo padre admin)
            familia_existente = None
            fam_id = await obtener_familia_id(telefono)
            if fam_id:
                from agent.airtable_client import _get_records, _FAMILIAS
                recs = await _get_records(_FAMILIAS, formula=f"RECORD_ID()='{fam_id}'", max_records=1)
                familia_existente = recs[0] if recs else None
            # Fallback: buscar por teléfono
            if not familia_existente:
                familia_existente = await buscar_familia_por_telefono(telefono)
            if familia_existente:
                contexto_extra = await _build_contexto_aurora(familia_existente, telefono)

        # ── Sin delays artificiales — Claude responde directo ────────────
                # El flujo continúa abajo con la llamada normal a generar_respuesta()

        # ── Inyectar instrucción de pitch si tenemos nombre+edad y padre pidió precios ──
        if agent_actual == "ivan" and _padre_ya_pidio_precios(historial):
            # Buscar si ya tenemos nombre hijo y edad en Airtable
            _tiene_nombre_edad = False
            try:
                from agent.airtable_client import _get_records, _LEADS
                _lr = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
                if _lr:
                    _f = _lr[0].get("fields", {})
                    _tiene_nombre_edad = bool(_f.get("NOMBRE NIÑO")) and bool(_f.get("EDAD"))
            except Exception:
                pass
            if not _tiene_nombre_edad:
                # Fallback: buscar en historial
                _nh = _extraer_nombre_hijo_historial(historial + [{"role": "user", "content": texto}])
                _tiene_nombre_h = _nh and _nh != "no mencionó"
                _tiene_edad_h = any(
                    re.search(r'\b\d{1,2}\b', m.get("content", ""))
                    for m in historial + [{"role": "user", "content": texto}]
                    if m.get("role") == "user"
                ) if _tiene_nombre_h else False
                _tiene_nombre_edad = _tiene_nombre_h and _tiene_edad_h
            if _tiene_nombre_edad:
                contexto_extra = (contexto_extra or "") + (
                    "\n[SISTEMA: Ya tenés nombre del hijo y edad. El padre ya pidió precios. "
                    "Hacé el PITCH CORTO ahora: mencioná nombre 2x, edad 2x, conectá con FENIX "
                    "(naturaleza, trepar, sol, desafíos reales). "
                    "TERMINÁ SIEMPRE con: '¿Te gustaría que [nombre] venga a probar un día? 😊' "
                    "NO preguntes nombre del padre. NO vuelvas al rompehielos. "
                    "NO preguntes qué quiere reforzar. El cierre es la oferta de prueba.]"
                )

        # ── FASE 1: mensaje de apertura fijo para leads nuevos de Ivan ─────
        # No llamamos a Claude — el mensaje está hardcodeado y es siempre igual.
        _interceptado = False
        _acciones_interceptadas = []  # lista de acciones a ejecutar post-respuesta
        if es_nuevo and agent_actual == "ivan" and len(historial) <= 1:
            _interceptado = True
            respuesta = (
                "Hola! Te saluda el Profe Ivan de FENIX Kids Academy 🌳\n\n"
                "Imaginate este sábado: tu hijo trepando árboles, corriendo al sol, "
                "jugando frente al río, en una mansión de 3000m² rodeada de naturaleza 🔥\n\n"
                "Eso es el PARQUE FENIX. Acá no hay pantallas, no hay paredes, no hay aburrimiento. "
                "Hay tierra, árboles, desafíos reales y otros chicos como él.\n\n"
                "Y la mejor parte: vos también entrenás con él. Tenemos un profe para los papás "
                "en el mismo parque, al mismo tiempo. Van a salir los dos renovados 💪\n\n"
                "¿Cómo se llama y qué edad tiene tu hijo? 🤝"
            )
            logger.info(f"[FASE1] {telefono}: mensaje de apertura fijo (sin Claude)")

        # ── Intercepción pre-Claude: respuestas fijas que no necesitan IA ──
        # Si el padre pregunta algo que el código puede responder solo,
        # ni llamamos a Claude — ahorra tokens y evita respuestas duplicadas.
        if not _interceptado and agent_actual == "ivan":
            _pide_precios = _padre_pregunta_precios(texto)
            _pide_horarios = _padre_pregunta_horarios(texto)
            _pide_ubicacion = _padre_pregunta_ubicacion(texto)
            _pide_duracion = _padre_pregunta_duracion(texto)
            _pide_que_llevar = _padre_pregunta_que_llevar(texto)
            _pide_devolucion = _padre_pregunta_devolucion(texto)
            _pide_efectivo = _padre_pregunta_efectivo(texto)
            _dice_ya_transfiri = _padre_dice_ya_transfiri(texto)
            _pide_alias = _padre_pregunta_alias(texto)
            _interes_post_diag = (
                _diagnostico_ya_enviado(historial)
                and _padre_muestra_interes(texto)
                and telefono not in _afiche_enviado
            )

            _hay_intercepcion = (
                _pide_precios or _pide_horarios or _pide_ubicacion or _interes_post_diag
                or _pide_duracion or _pide_que_llevar or _pide_devolucion
                or _pide_efectivo or _dice_ya_transfiri or _pide_alias
            )

            if _hay_intercepcion:
                _interceptado = True
                _partes = []  # texto de respuesta

                # Interés post-diagnóstico → afiche precios (es lo que corresponde)
                if _interes_post_diag and not _pide_precios:
                    _pide_precios = True  # tratar como pedido de precios

                if _pide_precios and telefono not in _afiche_enviado:
                    _acciones_interceptadas.append("afiche_precios")
                    _partes.append("Te paso un afiche para que veas todas las opciones 😊")
                elif _pide_precios:
                    _partes.append("Sábado en el parque: 90mil papá + hijo. 2 hijos: 120mil. 3 hijos: 150mil. Solo transferencia 🌳")

                if _pide_horarios and telefono not in _afiche_horarios_enviado:
                    _acciones_interceptadas.append("afiche_horarios")
                    _partes.append("Entrenamos todos los sábados 🌳 Te paso el afiche con los horarios")
                elif _pide_horarios:
                    _partes.append("9:30h | 11:00h | 15:30h — ¿cuál te viene bien? 🤝")

                if _pide_ubicacion:
                    _partes.append(
                        "📍 FENIX Kids Academy — Parque Fenix dentro de La Casona Lafuente\n"
                        "Maestras Paraguayas 2056\n"
                        "https://maps.app.goo.gl/nZT5zGA7N8B76xmD6?g_st=iwb"
                    )

                if _pide_duracion:
                    _partes.append("80 minutos cada sesión 💪 Tu hijo entrena con su grupo y vos entrenás en paralelo con el profe de adultos. Salen los dos renovados 🌳")

                if _pide_que_llevar:
                    _partes.append("Solo ropa cómoda, zapatillas y agua 💧 Nosotros ponemos todo: instructores, equipamiento, el parque entero 🌳")

                if _pide_devolucion:
                    _partes.append("El sábado de 90mil es para venir a conocer el parque y entrenar en familia. No se descuenta de un plan ni se devuelve. Si después se enganchan, pasamos a un plan. Si no, no hay compromiso 🤝")

                if _pide_efectivo:
                    _partes.append("Para el sábado solo transferencia 😊 Si después se inscriben, aceptamos todos los medios de pago.")

                if _dice_ya_transfiri:
                    _partes.append("Genial! Mandame foto del comprobante así te confirmo 😊")

                if _pide_alias:
                    _partes.append("El alias es el CI: 1604338")

                respuesta = "\n\n".join(_partes)
                logger.info(f"[INTERCEPCIÓN] {telefono}: precios={_pide_precios} horarios={_pide_horarios} ubi={_pide_ubicacion} duracion={_pide_duracion} que_llevar={_pide_que_llevar} devolucion={_pide_devolucion} efectivo={_pide_efectivo} ya_transfiri={_dice_ya_transfiri} alias={_pide_alias}")

        # ── Generar respuesta con Claude (solo si no fue interceptado) ────
        if not _interceptado:
            respuesta = await generar_respuesta(
                mensaje=texto,
                historial=historial,
                agent_actual=agent_actual,
                contexto_extra=contexto_extra,
            )

        # ── Limpiar comandos internos [SISTEMA:...] que Claude genera ─────
        # Estos son comandos internos que NUNCA deben llegar al padre
        if "[SISTEMA:" in respuesta:
            # Extraer el bloque [SISTEMA:...] para logging pero NO enviarlo
            _sistema_match = re.search(r'\[SISTEMA:.*?\](?:.*?)(?=\n\n|\Z)', respuesta, re.DOTALL)
            if _sistema_match:
                logger.info(f"[SISTEMA] Comando interno detectado: {_sistema_match.group()[:200]}")
            # Limpiar TODO lo que empiece con [SISTEMA: hasta el final del bloque
            respuesta = re.sub(r'\[SISTEMA:[^\]]*\].*?(?=\n\n|\Z)', '', respuesta, flags=re.DOTALL).strip()
            # Si quedó vacío después de limpiar, no enviar nada
            if not respuesta:
                logger.info(f"[SISTEMA] Respuesta vaciada tras limpiar comando interno para {telefono}")
                return

        # ── Anti-repetición: quitar preguntas que ya se hicieron ──────────
        if agent_actual == "ivan" and historial:
            # Juntar TODOS los mensajes del assistant (no solo últimos 6)
            _msgs_fenix = " ".join(
                m.get("content", "").lower() for m in historial[-12:]
                if m.get("role") == "assistant"
            )
            _ya_nombre_padre = any(p in _msgs_fenix for p in [
                "con quién tengo el gusto", "con quien tengo el gusto",
                "vos cómo te llamás", "vos como te llamas", "cómo te llamás", "como te llamas",
            ])
            _ya_nombre_hijo = any(p in _msgs_fenix for p in [
                "cómo se llama tu hijo", "como se llama tu hijo", "cómo se llama", "como se llama",
            ])
            _ya_edad = "cuántos años" in _msgs_fenix or "cuantos años" in _msgs_fenix

            if _ya_nombre_padre:
                # Quitar "con quién tengo el gusto" de la respuesta
                respuesta = re.sub(
                    r'[¿?]*\s*[Cc]on qui[eé]n tengo el gusto\??\s*😊?\s*',
                    '',
                    respuesta
                ).strip()
                # Si también preguntó nombre padre con "Y para orientarte..." quitar
                respuesta = re.sub(
                    r'Y para orientarte mejor,?\s*', '', respuesta
                ).strip()
            # Limpiar TODAS las preguntas de nombre/edad de la respuesta primero
            _preguntas_nombre = [
                r'[¿Y y]*\s*[Cc][oó]mo se llama tu hij[oa][^?]*\??[^\n]*',
                r'[¿Y y]*\s*[Cc][oó]mo se llama\s*\??[^\n]*',
                r'[Yy] contame[,.]?\s*',
            ]
            _preguntas_edad = [
                r'[¿Y y]*\s*[Cc]u[aá]ntos a[ñn]os tiene[^?]*\??[^\n]*',
            ]
            _preguntas_padre = [
                r'[¿Y y]*\s*[Cc]on qui[eé]n tengo el gusto[^?]*\??[^\n]*',
                r'[¿Y y]*\s*[Vv]os c[oó]mo te llam[aá]s[^?]*\??[^\n]*',
                r'[¿Y y]*\s*[Cc][oó]mo te llam[aá]s[^?]*\??[^\n]*',
            ]

            # Quitar preguntas repetidas (ya preguntadas O ya respondidas)
            if _ya_nombre_hijo:
                for p in _preguntas_nombre:
                    respuesta = re.sub(p, '', respuesta)
            if _ya_edad:
                for p in _preguntas_edad:
                    respuesta = re.sub(p, '', respuesta)
            if _ya_nombre_padre:
                for p in _preguntas_padre:
                    respuesta = re.sub(p, '', respuesta)
            # También quitar si ya TENEMOS la respuesta (aunque no esté en últimos 6 msgs)
            # Esto se verifica después de generar, con datos de Airtable

            # Limpiar basura residual
            respuesta = re.sub(r'\n{3,}', '\n\n', respuesta)
            respuesta = re.sub(r'[¿?]\s*[Yy]\s*$', '', respuesta)  # "¿Y" suelto al final
            respuesta = re.sub(r'\b[Yy]\s*$', '', respuesta)  # "Y" suelto al final
            respuesta = re.sub(r'\ba\s+y\b', '', respuesta)  # "a y" residual
            respuesta = respuesta.strip()

            # Claude maneja las preguntas de nombre/edad desde el prompt.
            # NO appendar preguntas automáticamente — eso pisaba la respuesta de Claude.
            respuesta = re.sub(r'\n{3,}', '\n\n', respuesta).strip()

        # ── Nota: FAMILIAS FENIX solo se crea en inscripción directa,
        #    no en clase de prueba. Para prueba, los datos van a PRUEBA FENIX. ──

        # ── Actualizar datos del lead en Airtable (nombre, hijo, edad) ────
        if agent_actual == "ivan":
            try:
                _nombre_resp = _extraer_nombre_del_historial(historial, texto)
                _nombre_hijo = _extraer_nombre_hijo_historial(historial + [{"role": "user", "content": texto}])
                # Extraer edad: solo cuando el mensaje anterior del agente preguntó la edad
                # y el padre responde (con número solo o "X años"). Esto evita confundir
                # los números del rompehielos (1, 6, 12) con la edad.
                _edad = ""
                import re as _re
                _hist_completo = historial + [{"role": "user", "content": texto}]
                for _idx, _m in enumerate(reversed(_hist_completo)):
                    if _m.get("role") != "user":
                        continue
                    _contenido = _m["content"]
                    _real_idx = len(_hist_completo) - 1 - _idx
                    # Verificar que el msg anterior del agente preguntó edad
                    if _real_idx > 0:
                        _prev = _hist_completo[_real_idx - 1]
                        _agente_pregunto_edad = (
                            _prev.get("role") == "assistant"
                            and _re.search(r'cu[aá]ntos\s+a[ñn]os|qu[eé]\s+edad', _prev.get("content", ""), _re.IGNORECASE)
                        )
                    else:
                        _agente_pregunto_edad = False
                    if _agente_pregunto_edad:
                        # "7 años", "tiene 5 años", o simplemente "7"
                        _match_edad = _re.search(r'\b(\d{1,2})\b', _contenido)
                        if _match_edad and 2 <= int(_match_edad.group(1)) <= 15:
                            _edad = _match_edad.group(1)
                            break
                # Si no matcheó regex pero el mensaje anterior preguntó "con quién tengo el gusto"
                # y el texto es un nombre corto (1-3 palabras, sin números), tomarlo como nombre
                if not _nombre_resp and len(historial) >= 1:
                    _ultimo_agente = historial[-1].get("content", "").lower() if historial[-1].get("role") == "assistant" else ""
                    if "con quién tengo el gusto" in _ultimo_agente or "con quien tengo el gusto" in _ultimo_agente or "cómo se llama" in _ultimo_agente:
                        # "Ivan, se llama benja" → nombre padre = Ivan
                        # "Ivan" → nombre padre = Ivan
                        _texto_limpio = texto.strip()
                        # Ignorar si es un pedido/pregunta (no es un nombre)
                        _tl = _texto_limpio.lower()
                        _no_nombres = ["precio", "costo", "cuanto", "cuánto", "horario",
                                       "como funciona", "cómo funciona", "ubicacion",
                                       "ubicación", "donde", "info", "información",
                                       "hola", "buenas", "quiero", "necesito", "consulta"]
                        _es_pedido = any(w in _tl for w in _no_nombres) or "?" in _tl
                        if not _es_pedido:
                            # Si tiene coma, tomar la primera parte como nombre padre
                            if "," in _texto_limpio:
                                _nombre_resp = _texto_limpio.split(",")[0].strip().title()
                            elif not any(c.isdigit() for c in _texto_limpio):
                                _palabras = _texto_limpio.split()
                                if 1 <= len(_palabras) <= 3:
                                    _nombre_resp = _texto_limpio.title()

                if _nombre_resp or (_nombre_hijo and _nombre_hijo != "no mencionó") or _edad:
                    await actualizar_datos_lead(
                        telefono,
                        nombre_responsable=_nombre_resp or "",
                        nombre_nino=_nombre_hijo if _nombre_hijo != "no mencionó" else "",
                        edad=_edad,
                    )
            except Exception as e:
                logger.error(f"[LEAD DATA] Error actualizando datos lead {telefono}: {e}")

        # ── Detectar registro de nombre del padre/madre por Aurora ─────
        if agent_actual == "aurora" and "REGISTRO PADRE:" in respuesta:
            try:
                reg_padre = re.search(r'REGISTRO PADRE:\s*(.+?)(?:\n|$)', respuesta)
                if reg_padre:
                    nombre_completo = reg_padre.group(1).strip()
                    partes_nombre = nombre_completo.split(maxsplit=1)
                    nombre_p = partes_nombre[0].title() if partes_nombre else ""
                    apellido_p = partes_nombre[1].title() if len(partes_nombre) > 1 else ""

                    # Deducir si es papá o mamá por el nombre
                    from agent.airtable_client import deducir_genero
                    genero = deducir_genero(nombre_p)
                    es_madre = genero == "MUJER"

                    # Actualizar FAMILIA en Airtable
                    fam_id = await obtener_familia_id(telefono)
                    if not fam_id:
                        fam = await buscar_familia_por_telefono(telefono)
                        if fam:
                            fam_id = fam["id"]
                            await guardar_familia_id(telefono, fam_id)
                    if fam_id:
                        from agent.airtable_client import _patch, _FAMILIAS
                        if es_madre:
                            campos_fam = {
                                "NOMBRE MADRE": nombre_p, "CELL MADRE": telefono,
                                "CELL PADRE": "",  # limpiar el temporal
                            }
                            if apellido_p:
                                campos_fam["APELLIDO MADRE"] = apellido_p
                            rol = "MADRE"
                        else:
                            campos_fam = {
                                "NOMBRE PADRE": nombre_p, "CELL PADRE": telefono,
                                "CELL MADRE": "",  # limpiar el temporal
                            }
                            if apellido_p:
                                campos_fam["APELLIDO PADRE"] = apellido_p
                            rol = "PADRE"
                        await _patch(_FAMILIAS, fam_id, campos_fam)
                        logger.info(f"[REGISTRO] {rol} actualizado: {nombre_p} {apellido_p} → familia {fam_id}")
            except Exception as e:
                logger.error(f"[REGISTRO] Error actualizando nombre padre/madre: {e}")

        # ── Detectar registro de hijos por Aurora ─────────────────────────
        if agent_actual == "aurora" and "REGISTRO HIJO:" in respuesta:
            try:
                familia = await buscar_familia_por_telefono(telefono)
                if familia:
                    familia_id = familia["id"]
                    registros = re.findall(
                        r'REGISTRO HIJO:\s*(.+?)(?:\n|$)', respuesta
                    )
                    for reg in registros:
                        # Parsear: "nombre apellido, nac: fecha, CI: ci, talla: talla"
                        datos_nino = {}
                        # Nombre y apellido (antes de la primera coma)
                        partes = [p.strip() for p in reg.split(",")]
                        if partes:
                            nombre_parts = partes[0].split()
                            if len(nombre_parts) >= 2:
                                datos_nino["nombre"] = nombre_parts[0]
                                datos_nino["apellido"] = " ".join(nombre_parts[1:])
                            elif len(nombre_parts) == 1:
                                datos_nino["nombre"] = nombre_parts[0]
                        for parte in partes[1:]:
                            parte_lower = parte.lower().strip()
                            if parte_lower.startswith("nac:"):
                                datos_nino["fecha_nacimiento"] = parte.split(":", 1)[1].strip()
                            elif parte_lower.startswith("ci:"):
                                datos_nino["ci"] = parte.split(":", 1)[1].strip()
                            elif parte_lower.startswith("talla:"):
                                datos_nino["talla_remera"] = parte.split(":", 1)[1].strip()
                        if datos_nino.get("nombre"):
                            nino_id = await crear_nino(datos_nino, familia_id)
                            if nino_id:
                                logger.info(f"[AURORA] Niño creado: {datos_nino.get('nombre')} para familia {familia_id}")
            except Exception as e:
                logger.error(f"[AURORA] Error creando niño: {e}")

        # ── Detectar cancelación de reserva por Aurora ─────────────────────
        if agent_actual == "aurora" and "cancelé la reserva" in respuesta.lower():
            try:
                # Extraer fecha de "cancelé la reserva de X del sábado 2 de mayo a las 11:00h"
                _m_cancel = re.search(
                    r'cancelé la reserva.*?s[aá]bado\s+(\d{1,2})\s+de\s+(\w+)(?:\s+a\s+las?\s+(\d{1,2}[:.]\d{2}))?',
                    respuesta.lower()
                )
                if _m_cancel:
                    _dia = int(_m_cancel.group(1))
                    _mes_nombre = _m_cancel.group(2)
                    _hora_cancel = _m_cancel.group(3) or ""
                    if _hora_cancel:
                        _hora_cancel = _hora_cancel.replace(".", ":")
                    _meses = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
                              "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
                    _mes = _meses.get(_mes_nombre, 0)
                    if _mes:
                        from datetime import date as _date_cls
                        _year = _date_cls.today().year
                        _fecha_iso = f"{_year}-{_mes:02d}-{_dia:02d}"
                        fam_id_cancel = await obtener_familia_id(telefono)
                        if not fam_id_cancel:
                            _fam_c = await buscar_familia_por_telefono(telefono)
                            if _fam_c:
                                fam_id_cancel = _fam_c["id"]
                        if fam_id_cancel:
                            borradas = await cancelar_reservas_familia_fecha(fam_id_cancel, _fecha_iso, _hora_cancel)
                            logger.info(f"[CANCELAR] {borradas} reservas canceladas para {telefono} el {_fecha_iso} {_hora_cancel}")
            except Exception as e:
                logger.error(f"[CANCELAR] Error cancelando reserva: {e}")

        # ── Detectar confirmación de reserva (Ivan o Aurora) ───────────────
        # Guard: para Ivan, solo procesar si el lead YA pagó (comprobante recibido).
        # Sin esto, frases pre-pago como "tiene su lugar el sábado X" disparan
        # notificación de agenda + PAGO en Airtable antes de que el lead pague.
        confirmaciones = _detectar_confirmacion_aurora(respuesta)
        if confirmaciones and agent_actual == "ivan":
            _hist_reciente = await obtener_historial(telefono, limite=10)
            _pago_en_historial = any(
                "pago confirmado" in m.get("content", "").lower()
                for m in _hist_reciente
                if m.get("role") == "assistant"
            )
            if not _pago_en_historial:
                confirmaciones = []
                logger.info(f"[AGENDA] {telefono}: confirmación detectada pero sin pago previo — ignorada")
        for confirmacion in confirmaciones:
            await _procesar_confirmacion_reserva(telefono, confirmacion, respuesta, agent_actual)

        # ── Detectar llamada programada ("te llamo a las X") ──────────────
        if agent_actual == "ivan":
            _m_llamada = re.search(
                r'te llamo (?:a las?\s+)?(\d{1,2}(?:[:.]\d{2})?(?:\s*(?:hs?|pm|am))?)',
                respuesta.lower()
            )
            if _m_llamada and "desde mi" not in respuesta.lower():
                try:
                    await _programar_llamada(telefono, _m_llamada.group(1))
                    logger.info(f"[LLAMADA] Programada para {telefono} a las {_m_llamada.group(1)}")
                except Exception as e:
                    logger.error(f"[LLAMADA] Error programando: {e}")

        # ── Guardar respuesta (user ya guardado al inicio) ─────────────
        await guardar_mensaje(telefono, "assistant", respuesta)

        # ── Marcar CONVERSION=CONTACTADO si Ivan mandó datos bancarios ──
        if agent_actual == "ivan" and CI_BANCARIO in respuesta:
            try:
                await actualizar_conversion_lead(telefono, "CONTACTADO")
                await _resetear_seguimiento(telefono)
            except Exception as e:
                logger.error(f"[FOLLOWUP] Error marcando CONTACTADO: {e}")

        # ── Detectar si el padre mandó datos del formulario post-pago ──────
        _es_formulario_completo = False
        if agent_actual == "ivan" and telefono not in _prueba_creada:
            _pago_confirmado_cierre = any(
                "pago confirmado" in m.get("content", "").lower()
                for m in historial if m.get("role") == "assistant"
            )
            _ivan_pidio_formulario = any(
                ("📋" in m.get("content", "") or "pasame estos datos" in m.get("content", "").lower())
                for m in historial if m.get("role") == "assistant"
            )
            # El padre manda datos reales: texto con fechas (tiene "/") y suficiente largo
            # Si pago ya confirmado + Ivan pidió formulario, no exigir keywords —
            # la gente manda datos crudos sin decir "nombre" ni "nacimiento"
            _meses_texto = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
            _tiene_fechas = ("/" in texto or "-" in texto or any(m in texto.lower() for m in _meses_texto))
            _tiene_keywords = any(p in texto.lower() for p in ["nombre", "mamá", "mama", "papá", "papa", "nene", "nena", "hijo", "hija", "nacimiento"])
            _texto_tiene_datos = (
                len(texto) > 20
                and _tiene_fechas
                and (_tiene_keywords or (_pago_confirmado_cierre and _ivan_pidio_formulario))
            )
            _es_formulario_completo = (
                _pago_confirmado_cierre
                and _ivan_pidio_formulario
                and _texto_tiene_datos
            )

        # ── Detectar si Claude dice "te paso un afiche" (safety net) ──────
        _va_a_enviar_afiche = False
        if agent_actual == "ivan" and telefono not in _afiche_enviado and not _interceptado:
            if "te paso un afiche" in respuesta.lower():
                _va_a_enviar_afiche = True

        # ── Enviar respuesta (con delay humano) ────────────────────────────
        if _es_formulario_completo:
            # Extraer nombres hijos + fecha/hora del mensaje "Reserva confirmada" previo
            _hist_form = await obtener_historial(telefono, limite=40)
            _nombres_form = ""
            _fecha_form = ""
            _hora_form = ""
            for _m_f in reversed(_hist_form):
                if _m_f.get("role") == "assistant" and "reserva confirmada" in _m_f.get("content", "").lower():
                    _match_nombres = re.search(r"reserva confirmada[✅!\s]*(.+?)\s+tienen?\s+su\s+lugar", _m_f["content"], re.IGNORECASE)
                    if _match_nombres:
                        _nombres_form = _match_nombres.group(1).strip()
                    _match_f = re.search(r"s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})", _m_f["content"].lower())
                    if _match_f:
                        _fecha_form = _match_f.group(1)
                        _hora_form = _match_f.group(2)
                    break
            if not _nombres_form:
                _nombres_form = _extraer_nombre_hijo_historial(_hist_form) or ""
                if _nombres_form == "no mencionó":
                    _nombres_form = ""
            _nombre_part = f" {_nombres_form}" if _nombres_form else ""
            _fecha_part = f" el sábado {_fecha_form} a las {_hora_form}h" if _fecha_form else " el sábado"
            _verbo = "tienen" if " y " in _nombres_form else "tiene"
            respuesta = f"Muchas gracias por tus datos! Reserva confirmada ✅{_nombre_part} {_verbo} su lugar{_fecha_part} 🌳\n\nLos esperamos 🔥"
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
        elif _interceptado:
            # Respuesta interceptada por código — enviar texto + afiches
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
            # Ejecutar acciones (enviar afiches)
            for _accion in _acciones_interceptadas:
                if _accion == "afiche_precios":
                    _afiche_enviado.add(telefono)
                    await _enviar_afiche_y_followup(telefono, topic_id, _tg_group)
                elif _accion == "afiche_horarios":
                    _afiche_horarios_enviado.add(telefono)
                    await _enviar_afiche_horarios(telefono, topic_id, _tg_group)
        elif _va_a_enviar_afiche:
            # Post-diagnóstico interés → afiche precios (respuesta Claude se omite)
            _afiche_enviado.add(telefono)
            await _enviar_afiche_y_followup(telefono, topic_id, _tg_group)
        else:
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)

        # ── Espejo respuesta en Telegram ──────────────────────────────────
        agente_label = "🌟 AURORA" if agent_actual == "aurora" else "👨‍🏫 IVAN"
        if topic_id:
            await enviar_a_topic(topic_id, f"{agente_label}: {respuesta}", telefono=telefono, group_override=_tg_group)

        # ── Crear PRUEBA FENIX si el padre completó el formulario ─────────
        if _es_formulario_completo:
            _prueba_creada.add(telefono)
            try:
                from urllib.parse import quote
                admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
                historial_completo = await obtener_historial(telefono, limite=40)
                # Nombre padre del historial
                _np = _extraer_nombre_del_historial(historial_completo) or ""
                primer_nombre = _np.split()[0] if _np else ""
                # Nombre hijo
                _nh = _extraer_nombre_hijo_historial(historial_completo)
                _hijo = _nh if _nh and _nh != "no mencionó" else ""
                # Fecha/hora de la reserva confirmada
                _fecha_res = ""
                _hora_res = ""
                _MESES_A_NUM = {"enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06",
                                "julio":"07","agosto":"08","septiembre":"09","octubre":"10","noviembre":"11","diciembre":"12"}
                for _m_res in reversed(historial_completo):
                    if _m_res.get("role") == "assistant" and "reserva confirmada" in _m_res.get("content", "").lower():
                        _match_fecha = re.search(r"s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})", _m_res["content"].lower())
                        if _match_fecha:
                            _fecha_txt = _match_fecha.group(1)  # "16 de mayo"
                            _hora_res = _match_fecha.group(2).replace("h", ":").rstrip(":")
                            # Convertir "16 de mayo" → "2026-05-16"
                            _mf = re.match(r"(\d{1,2})\s+de\s+(\w+)", _fecha_txt)
                            if _mf and _mf.group(2) in _MESES_A_NUM:
                                _dia = _mf.group(1).zfill(2)
                                _mes = _MESES_A_NUM[_mf.group(2)]
                                _fecha_res = f"2026-{_mes}-{_dia}"
                            else:
                                _fecha_res = _fecha_txt  # fallback
                        break
                fecha_hora = f"el sábado {_fecha_res} a las {_hora_res}" if _fecha_res else "el sábado"

                # ── Crear PRUEBA FENIX con datos completos (Opción A) ─────────
                try:
                    from agent.airtable_client import _get_records, _LEADS
                    # Obtener lead_id y diagnóstico
                    _lr_pf = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
                    _lead_id = _lr_pf[0]["id"] if _lr_pf else None
                    _diag_ids = _lr_pf[0].get("fields", {}).get("DIAGNOSTICO", []) if _lr_pf else []

                    # Usar Haiku para extraer datos completos del historial
                    datos_form = await extraer_datos_formulario(historial_completo)
                    padre_data = datos_form.get("padre") or {}
                    nombre_resp = padre_data.get("nombre", "") or (_np.split()[0] if _np else "")
                    apellido_resp = padre_data.get("apellido", "") or (_np.split()[1] if _np and " " in _np else "")
                    ninos_form = datos_form.get("ninos", [])
                    _monto = monto_prueba_por_hijos(historial_completo)

                    if ninos_form:
                        for i, n in enumerate(ninos_form):
                            await crear_prueba_fenix(
                                telefono=telefono,
                                nombre_responsable=nombre_resp,
                                apellido_responsable=apellido_resp,
                                nombre_hijo=n.get("nombre", ""),
                                apellido_hijo=n.get("apellido", ""),
                                edad_hijo="",
                                fecha_reserva=_fecha_res,
                                hora=_hora_res,
                                fecha_nacimiento=n.get("fecha_nacimiento", ""),
                                monto=_monto if i == 0 else 0,
                                diagnostico_ids=_diag_ids,
                                lead_record_id=_lead_id,
                            )
                    else:
                        # Fallback con datos del historial
                        await crear_prueba_fenix(
                            telefono=telefono,
                            nombre_responsable=primer_nombre,
                            apellido_responsable="",
                            nombre_hijo=_hijo,
                            apellido_hijo="",
                            edad_hijo="",
                            fecha_reserva=_fecha_res,
                            hora=_hora_res,
                            monto=_monto,
                            diagnostico_ids=_diag_ids,
                            lead_record_id=_lead_id,
                        )
                    # Actualizar LEADS a PAGO
                    await actualizar_conversion_lead(telefono, "PAGO")
                    # CAPI: evento LeadSubmitted + Purchase
                    await enviar_evento_agenda(telefono)
                    await enviar_evento_pago(telefono)
                    logger.info(f"[PRUEBA FENIX] Creado post-formulario para {telefono}")
                except Exception as e:
                    logger.error(f"[PRUEBA FENIX] Error creando post-formulario: {e}")
                    # Alertar a Ivan en Telegram para que no se pierda
                    try:
                        if topic_id:
                            await enviar_a_topic(topic_id, f"⚠️ ERROR: No se pudo crear PRUEBA FENIX — {e}", telefono=telefono, group_override=_tg_group)
                    except Exception:
                        pass

                # ── Link wa.me al admin ───────────────────────────────────────
                # Usar datos de Haiku (más completos) con fallback al historial
                _nombre_padre_form = ""
                _hijo_form = ""
                if datos_form:
                    padre_d = datos_form.get("padre") or {}
                    _nombre_padre_form = padre_d.get("nombre", "") or ""
                    if not _nombre_padre_form and padre_d.get("apellido"):
                        _nombre_padre_form = padre_d.get("apellido", "")
                    # Nombre completo del padre desde Haiku
                    _np_full = f"{padre_d.get('nombre', '')} {padre_d.get('apellido', '')}".strip()
                    if _np_full:
                        _np = _np_full
                    # Hijos desde Haiku
                    ninos_nombres = [f"{n.get('nombre', '')} {n.get('apellido', '')}".strip() for n in datos_form.get("ninos", []) if n.get("nombre")]
                    if ninos_nombres:
                        _hijo_form = ", ".join(ninos_nombres)
                    else:
                        _hijo_form = _hijo
                else:
                    _hijo_form = _hijo
                if not _nombre_padre_form:
                    _nombre_padre_form = primer_nombre or ""
                _con_hijo = f", te espero con {_hijo_form}" if _hijo_form else ""
                _saludo = f"Que tal {_nombre_padre_form}" if _nombre_padre_form else "Que tal"
                msg_wa = f"{_saludo}, te saluda el profe Ivan de Fenix Kids. Recibí tu reserva{_con_hijo} {fecha_hora}. 🌳"
                wa_link = f"https://wa.me/{telefono}?text={quote(msg_wa)}"
                # Link al topic de Telegram
                _tg_link_reserva = ""
                if topic_id and _tg_group:
                    _gid_r = str(_tg_group).replace("-100", "", 1)
                    _tg_link_reserva = f"\n💬 https://t.me/c/{_gid_r}/{topic_id}"
                alerta_admin = (
                    f"📅 RESERVA COMPLETA\n\n"
                    f"👤 {_np or 'Lead'}\n"
                    f"👦 {_hijo_form or 'hijo/a'}\n"
                    f"📆 {fecha_hora}"
                    f"{_tg_link_reserva}\n\n"
                    f"📲 {wa_link}"
                )
                await proveedor.enviar_mensaje(admin_phone, alerta_admin)
                logger.info(f"[RESERVA] Link wa.me enviado al admin para {telefono}")
            except Exception as e:
                logger.error(f"[RESERVA] Error en cierre formulario: {e}")

        # ── Afiches de horarios y precios: se manejan arriba (pre-respuesta) para evitar duplicados ──

        # ── Seguimiento desactivado temporalmente ─────────────────────────
        # TODO: reactivar cuando se arme el follow up
        # if es_nuevo:
        #     programar_seguimiento_inicial(
        #         telefono=telefono,
        #         proveedor=proveedor,
        #         guardar_fn=_guardar_mensaje,
        #         formulario_check_fn=esta_convertido,
        #     )

        # Procesamiento exitoso (dedup ya registrada en webhook handler)
        pass

    except Exception as e:
        logger.error(f"[WEBHOOK] Error procesando {telefono}: {e}", exc_info=True)
        # Borrar dedup para que si el padre reenvía, se procese
        if msg.mensaje_id:
            await borrar_mensaje_procesado(msg.mensaje_id)


async def _procesar_confirmacion_reserva(
    telefono: str,
    confirmacion: dict,
    respuesta_aurora: str,
    agent_actual: str = "aurora",
):
    """
    Cuando se confirma una reserva:
    - Aurora (inscriptos): crear RESERVA en RESERVAS FENIX
    - Ivan (leads): crear registro en PRUEBA FENIX (NO en RESERVAS FENIX)
    """
    fecha_str = confirmacion.get("fecha", "")
    hora_str = confirmacion.get("hora", "")

    # Resolver "hoy" a fecha real
    if fecha_str == "hoy":
        from datetime import datetime, timezone, timedelta
        _PY_TZ = timezone(timedelta(hours=-3))
        _hoy = datetime.now(_PY_TZ).date()
        _MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                  7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
        fecha_str = f"{_hoy.day} de {_MESES[_hoy.month]}"

    logger.info(f"Confirmación detectada ({agent_actual}): {fecha_str} {hora_str} para {telefono}")

    # Solo Ivan toca LEADS FENIX — Aurora NUNCA toca LEADS ni PRUEBA
    if agent_actual == "ivan":
        await actualizar_conversion_lead(telefono, "PAGO")
        await actualizar_reserva_lead(telefono, fecha_str, hora_str)

    # Calcular fecha ISO para Airtable
    fecha_iso = None
    if fecha_str and hora_str:
        try:
            from datetime import date as _d
            _MESES = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
                       "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
            anio = _d.today().year
            # Formato "3/5" o "03/05"
            _m = re.search(r'(\d{1,2})/(\d{1,2})', fecha_str)
            if _m:
                dia, mes = int(_m.group(1)), int(_m.group(2))
                fecha_iso = f"{anio}-{mes:02d}-{dia:02d}"
            else:
                # Formato "9 de mayo" o "23 de mayo"
                _m2 = re.search(r'(\d{1,2})\s+de\s+(\w+)', fecha_str)
                if _m2:
                    dia = int(_m2.group(1))
                    mes_nombre = _m2.group(2).lower()
                    mes = _MESES.get(mes_nombre, 0)
                    if mes:
                        fecha_iso = f"{anio}-{mes:02d}-{dia:02d}"
            if not fecha_iso:
                # Último intento: solo número → asumir próximo sábado con ese día
                _m3 = re.search(r'(\d{1,2})', fecha_str)
                if _m3:
                    dia = int(_m3.group(1))
                    hoy = _d.today()
                    # Probar este mes y el siguiente
                    for delta_mes in range(0, 3):
                        mes_test = hoy.month + delta_mes
                        anio_test = hoy.year + (mes_test - 1) // 12
                        mes_test = (mes_test - 1) % 12 + 1
                        try:
                            fecha_test = _d(anio_test, mes_test, dia)
                            if fecha_test.weekday() == 5:  # sábado
                                fecha_iso = fecha_test.isoformat()
                                break
                        except ValueError:
                            continue
        except Exception as e:
            logger.error(f"Error calculando fecha: {e}")

    # ── Obtener niños de la familia (para nombre real + RESERVAS) ──────────────
    familia_id = await obtener_familia_id(telefono)
    if not familia_id:
        # Fallback: buscar en Airtable por CELL LIMPIO (familia pre-existente)
        _fam_at = await buscar_familia_por_telefono(telefono)
        if _fam_at:
            familia_id = _fam_at["id"]
            logger.info(f"[RESERVA] Familia encontrada via Airtable CELL LIMPIO: {familia_id}")
    ninos = await obtener_ninos_de_familia(familia_id) if familia_id else []

    # Nombre display para el evento: "Mateo González" | "Mateo y Sofía González" | fallback
    if ninos:
        nombres = [n.get("nombre_completo") or n.get("nombre") or "" for n in ninos]
        nombres = [n for n in nombres if n]
        if len(nombres) == 1:
            nombre_display = nombres[0]
        elif len(nombres) > 1:
            nombre_display = " y ".join(nombres)
        else:
            nombre_display = telefono
    else:
        nombre_display = telefono

    # ── Crear RESERVA en Airtable — SOLO para inscriptos (Aurora) ───────────────
    if agent_actual == "aurora" and fecha_iso and ninos:
        fecha_airtable = fecha_iso
        try:
            horario_id = await obtener_o_crear_horario(fecha_airtable, hora_str)
            if horario_id:
                for nino in ninos:
                    rid = await crear_reserva(nino["id"], horario_id, familia_id or "")
                    if rid:
                        logger.info(f"Reserva creada: {nino.get('nombre_completo', nino['id'])} → {rid}")
            else:
                logger.warning(f"No se pudo obtener/crear HORARIO {fecha_airtable} {hora_str}")
        except Exception as e:
            logger.error(f"Error creando RESERVA para {telefono}: {e}")

    # ── Reagendamiento PRUEBA FENIX (Ivan): actualizar fecha si ya existe ─────
    if agent_actual == "ivan" and fecha_str and hora_str:
        try:
            from agent.airtable_client import _get_records, _patch, _PRUEBAS
            _pruebas_existentes = await _get_records(
                _PRUEBAS, formula=f"{{TELEFONO}}='{telefono}'", max_records=5
            )
            if _pruebas_existentes:
                # Ya tiene PRUEBA FENIX → reagendamiento, actualizar fecha/hora
                _hora_norm = hora_str.replace("h", "").replace(".", ":")
                if ":" not in _hora_norm:
                    _hora_norm = f"{_hora_norm}:00"
                for _pr in _pruebas_existentes:
                    await _patch(_PRUEBAS, _pr["id"], {
                        "FECHA RESERVA": fecha_str,
                        "HORA": _hora_norm,
                    })
                    _nh_pr = _pr.get("fields", {}).get("NOMBRE HIJO", "?")
                    logger.info(f"[REAGENDAR] {_nh_pr} ({telefono}): {fecha_str} {_hora_norm}")
        except Exception as e:
            logger.error(f"[REAGENDAR] Error actualizando PRUEBA FENIX: {e}")

    # PRUEBA FENIX se crea post-formulario (cuando Ivan dice "los esperamos")
    # Ver bloque _es_cierre_formulario en el flujo principal

    # ── Enviar lista de niños agendados para ese horario ─────────────────────
    if fecha_iso:
        try:
            ninos_horario = await obtener_ninos_por_horario(fecha_iso, hora_str)
            if ninos_horario:
                # Armar label de fecha: "Sábado 26/4"
                from datetime import date as _date_cls
                _fd = _date_cls.fromisoformat(fecha_iso)
                fecha_label = f"Sábado {_fd.day}/{_fd.month}"
                lista = formatear_lista_ninos(ninos_horario, fecha_label, hora_str)
                await proveedor.enviar_mensaje(telefono, lista)
        except Exception as e:
            logger.error(f"[LISTA] Error enviando lista de niños: {e}")

    # Notificar en Telegram — buscar nombre aunque no haya familia
    _nombre_notif = nombre_display if (ninos and nombre_display != telefono) else None
    if not _nombre_notif:
        try:
            from agent.airtable_client import _get_records, _LEADS
            _lr_notif = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
            if _lr_notif:
                _f_notif = _lr_notif[0].get("fields", {})
                _hijo_notif = _f_notif.get("NOMBRE NIÑO", "")
                _padre_notif = _f_notif.get("NOMBRE RESPONSABLE", "")
                _nombre_notif = _hijo_notif or _padre_notif or None
        except Exception:
            pass
    if not _nombre_notif:
        _nombre_notif = _extraer_nombre_hijo_historial(await obtener_historial(telefono, limite=20))
        if _nombre_notif == "no mencionó":
            _nombre_notif = None
    # Armar nombre de hijos para el link wa.me
    _hijos_notif = None
    if ninos:
        _nombres_hijos = [n.get("apodo") or n.get("nombre") or "" for n in ninos]
        _nombres_hijos = [n for n in _nombres_hijos if n]
        if _nombres_hijos:
            _hijos_notif = " y ".join(_nombres_hijos)
    if not _hijos_notif and _nombre_notif:
        _hijos_notif = _nombre_notif  # fallback: usar el mismo nombre
    await notificar_agenda_telegram(
        telefono=telefono,
        dia=fecha_str,
        hora=hora_str,
        nombre=_nombre_notif,
        nombre_hijos=_hijos_notif,
        agente=agent_actual,
    )

    # Link wa.me se envía cuando el padre completa el formulario (no acá)
    # Ver _detectar_formulario_completo en el flujo principal

    # Programar recordatorio persistente para el día de la clase (07:00 PY)
    if fecha_iso:
        try:
            await _programar_recordatorio_clase(telefono, fecha_iso, hora_str)
        except Exception as _e_rec:
            logger.error(f"[RECORDATORIO] Error programando para {telefono}: {_e_rec}")



# ── Cargar familia (comando admin) ────────────────────────────────────────────

_METODO_MAP = {
    "SUB": "SUSCRIPCION", "SUSCRIPCION": "SUSCRIPCION", "SUSCRI": "SUSCRIPCION",
    "TRANS": "TRANSFER", "TRANSFER": "TRANSFER", "TRANSFERENCIA": "TRANSFER",
    "DEB": "DEB", "DEBITO": "DEB",
    "CRED": "CRED", "CREDITO": "CRED",
    "EFE": "EFECTIVO", "EFECTIVO": "EFECTIVO", "CASH": "EFECTIVO",
}


def _parsear_inscripcion(texto: str) -> dict:
    """
    Parsea texto libre de inscripción. Extrae plan, método, monto, matrícula.
    Acepta cualquier orden, con o sin keywords explícitos.
    Retorna dict con las claves encontradas (puede estar incompleto).
    """
    t = texto.lower().replace(",", " ").replace(".", " ")

    result = {}

    # ── Plan: detectar por keywords naturales ──
    # trimestral full/todos/semanal/4 = ST
    # trimestral dos/quincenal/2 = QT
    # mensual full/todos/semanal/4 = SM
    # mensual dos/quincenal/2 = QM
    # También acepta códigos: QM, SM, QT, ST
    if re.search(r'\b(st)\b', t):
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'\b(qt)\b', t):
        result["plan"] = "QUINCENAL TRIMESTRAL"
    elif re.search(r'\b(sm)\b', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\b(qm)\b', t):
        result["plan"] = "QUINCENAL MENSUAL"
    # Primero buscar "dos/quincenal" (más específico), después "full/todos"
    elif re.search(r'trimestral.{0,15}\b(dos|quincenal)\b', t):
        result["plan"] = "QUINCENAL TRIMESTRAL"
    elif re.search(r'\b(dos|quincenal)\b.{0,15}trimestral', t):
        result["plan"] = "QUINCENAL TRIMESTRAL"
    elif re.search(r'trimestral.{0,15}\b(full|todos|todas|completo|semanal)\b', t):
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'\b(full|todos|todas|completo|semanal)\b.{0,15}trimestral', t):
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'\btrimestral\b', t):
        # Solo "trimestral" sin calificador → asumir full (el más común)
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'mensual.{0,15}\b(dos|quincenal)\b', t):
        result["plan"] = "QUINCENAL MENSUAL"
    elif re.search(r'\b(dos|quincenal)\b.{0,15}mensual', t):
        result["plan"] = "QUINCENAL MENSUAL"
    elif re.search(r'mensual.{0,15}\b(full|todos|todas|completo|semanal)\b', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\b(full|todos|todas|completo|semanal)\b.{0,15}mensual', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\bmensual\b', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\btrimestral\b', t):
        # Solo "trimestral" sin más → pedir aclaración
        pass
    elif re.search(r'\bmensual\b', t):
        pass

    # ── Método de pago ──
    for keyword, metodo in _METODO_MAP.items():
        if keyword.lower() in t:
            result["metodo"] = metodo
            break

    # ── Monto y matrícula: buscar "monto X" y "matricula X" ──
    m_monto = re.search(r'monto\s+(\d+)', t)
    if m_monto:
        result["monto"] = int(m_monto.group(1))

    m_matri = re.search(r'matri(?:cula)?\s+(\d+)', t)
    if m_matri:
        result["matricula"] = int(m_matri.group(1))

    # Si no encontró con keyword, buscar números sueltos y asignar por contexto
    if "monto" not in result or "matricula" not in result:
        nums = re.findall(r'\b(\d{2,4})\b', t)
        # Filtrar números que ya se asignaron
        nums_int = [int(n) for n in nums]
        assigned = {result.get("monto"), result.get("matricula")}
        remaining = [n for n in nums_int if n not in assigned and n > 10]
        if remaining and "monto" not in result:
            result["monto"] = max(remaining)  # el más grande es el monto
            remaining.remove(result["monto"])
        if remaining and "matricula" not in result:
            result["matricula"] = remaining[0]

    # Normalizar montos a guaraníes (si < 10000, multiplicar por 1000)
    for key in ("monto", "matricula"):
        if key in result and result[key] < 10000:
            result[key] = result[key] * 1000

    return result


async def _iniciar_inscripcion(admin_phone: str, texto_completo: str):
    """
    Parsea texto libre: extrae nombre + datos de inscripción.
    Si tiene todo, ejecuta directo. Si falta algo, pide lo que falta.
    """
    from agent.airtable_client import _get_records, _PRUEBAS

    # Extraer datos del texto
    parsed = _parsear_inscripcion(texto_completo)

    # Buscar nombre: todo lo que no sea keyword de plan/método/monto
    _keywords = {
        "trimestral", "mensual", "full", "todos", "todas", "semanal", "quincenal",
        "dos", "completo", "monto", "matricula", "matri",
        "sub", "suscripcion", "suscri", "trans", "transfer", "transferencia",
        "deb", "debito", "cred", "credito", "efe", "efectivo", "cash",
        "qm", "sm", "qt", "st", "mil", "bi",
    }
    palabras = texto_completo.strip().split()
    nombre_parts = []
    for p in palabras:
        p_clean = re.sub(r'[,.:;!?]', '', p).lower()
        if p_clean in _keywords or p_clean.isdigit():
            break
        nombre_parts.append(p)
    nombre_buscar = " ".join(nombre_parts).strip()

    if not nombre_buscar:
        await proveedor.enviar_mensaje(admin_phone, "No entendí el nombre. Ej: cargar familia Diana Jara trimestral full monto 690 matricula 50")
        return

    # Buscar en PRUEBA FENIX — normalizar tildes para comparación
    import unicodedata
    def _sin_tildes(s: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()

    pruebas = await _get_records(_PRUEBAS, formula="", max_records=100)
    _nombre_norm = _sin_tildes(nombre_buscar)

    matches = []
    for p in pruebas:
        f = p.get("fields", {})
        nombre_completo = _sin_tildes(f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip())
        if _nombre_norm in nombre_completo or nombre_completo in _nombre_norm:
            matches.append(p)

    if not matches:
        for p in pruebas:
            f = p.get("fields", {})
            hijo_completo = _sin_tildes(f"{f.get('NOMBRE HIJO', '')} {f.get('APELLIDO HIJO', '')}".strip())
            if _nombre_norm in hijo_completo:
                matches.append(p)

    if not matches:
        await proveedor.enviar_mensaje(admin_phone, f"No encontré prueba para '{nombre_buscar}'")
        return

    if len(matches) > 1:
        # Dedup por teléfono (hermanos = mismo tel)
        _tels_vistos = set()
        matches_uniq = []
        for m in matches:
            _tel = m.get("fields", {}).get("TELEFONO", "")
            if _tel not in _tels_vistos:
                _tels_vistos.add(_tel)
                matches_uniq.append(m)
        if len(matches_uniq) > 1:
            msg = f"Encontré {len(matches_uniq)} familias:\n\n"
            for i, m in enumerate(matches_uniq, 1):
                f = m.get("fields", {})
                msg += f"{i}. {f.get('NOMBRE', '')} {f.get('APELLIDO', '')} → {f.get('NOMBRE HIJO', '')} ({f.get('TELEFONO', '')})\n"
            msg += "\nEscribí el número para elegir:"
            _inscripcion_pendiente[admin_phone] = {"step": "elegir", "matches": matches_uniq, "parsed": parsed}
            await proveedor.enviar_mensaje(admin_phone, msg)
            return
        matches = matches_uniq

    prueba = matches[0]
    tel = prueba.get("fields", {}).get("TELEFONO", "")

    # Buscar todas las pruebas de este teléfono (hermanos)
    todas_pruebas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{tel}'", max_records=10)

    # Si tenemos todo → ejecutar directo
    faltantes = []
    if "plan" not in parsed:
        faltantes.append("PLAN (ej: trimestral full, mensual dos, QT, SM...)")
    if "monto" not in parsed:
        faltantes.append("MONTO (en miles, ej: 690)")
    if "matricula" not in parsed:
        faltantes.append("MATRICULA (en miles, ej: 50)")

    if faltantes:
        # Mostrar lo que encontró y pedir lo que falta
        fp = prueba.get("fields", {})
        hijos_txt = ", ".join(
            f"{op.get('fields', {}).get('NOMBRE HIJO', '')} ({op.get('fields', {}).get('EDAD HIJO', '?')})"
            for op in todas_pruebas if op.get("fields", {}).get("NOMBRE HIJO")
        )
        msg = (
            f"📋 Encontré: {fp.get('NOMBRE', '')} {fp.get('APELLIDO', '')} ({tel})\n"
            f"👶 {hijos_txt}\n\n"
        )
        if parsed.get("plan"):
            msg += f"✅ Plan: {parsed['plan']}\n"
        if parsed.get("monto"):
            msg += f"✅ Monto: {parsed['monto'] // 1000}mil\n"
        if parsed.get("matricula"):
            msg += f"✅ Matrícula: {parsed['matricula'] // 1000}mil\n"
        if parsed.get("metodo"):
            msg += f"✅ Método: {parsed['metodo']}\n"
        msg += f"\nFalta:\n" + "\n".join(f"• {f}" for f in faltantes)
        msg += "\n\nCompletá lo que falta (texto libre):"

        _inscripcion_pendiente[admin_phone] = {
            "step": "completar",
            "prueba": prueba,
            "todas_pruebas": todas_pruebas,
            "parsed": parsed,
        }
        await proveedor.enviar_mensaje(admin_phone, msg)
        return

    # Todo completo → mostrar resumen y pedir confirmación
    metodo = parsed.get("metodo", "TRANSFER")
    await _mostrar_confirmacion(admin_phone, prueba, todas_pruebas, parsed, metodo)


async def _procesar_respuesta_inscripcion(admin_phone: str, texto: str):
    """Procesa respuestas pendientes de inscripción (elegir match o completar datos)."""
    datos = _inscripcion_pendiente.get(admin_phone)
    if not datos:
        return

    # Elegir entre múltiples matches
    if datos["step"] == "elegir":
        try:
            idx = int(texto.strip()) - 1
            matches = datos["matches"]
            parsed = datos.get("parsed", {})
            if 0 <= idx < len(matches):
                _inscripcion_pendiente.pop(admin_phone, None)
                prueba = matches[idx]
                tel = prueba.get("fields", {}).get("TELEFONO", "")
                from agent.airtable_client import _get_records, _PRUEBAS
                todas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{tel}'", max_records=10)
                # Re-iniciar con los datos parseados originales
                faltantes = []
                if "plan" not in parsed:
                    faltantes.append("PLAN")
                if "monto" not in parsed:
                    faltantes.append("MONTO")
                if "matricula" not in parsed:
                    faltantes.append("MATRICULA")
                if faltantes:
                    _inscripcion_pendiente[admin_phone] = {
                        "step": "completar",
                        "prueba": prueba,
                        "todas_pruebas": todas,
                        "parsed": parsed,
                    }
                    await proveedor.enviar_mensaje(admin_phone, f"Falta: {', '.join(faltantes)}\nCompletá (texto libre):")
                else:
                    metodo = parsed.get("metodo", "TRANSFER")
                    await _mostrar_confirmacion(admin_phone, prueba, todas, parsed, metodo)
            else:
                await proveedor.enviar_mensaje(admin_phone, f"Elegí entre 1 y {len(matches)}")
        except ValueError:
            _inscripcion_pendiente.pop(admin_phone, None)
            await proveedor.enviar_mensaje(admin_phone, "Cancelado.")
        return

    # Completar datos faltantes
    if datos["step"] == "completar":
        nuevos = _parsear_inscripcion(texto)
        parsed = datos["parsed"]
        # Merge: lo nuevo sobreescribe
        parsed.update(nuevos)
        datos["parsed"] = parsed

        faltantes = []
        if "plan" not in parsed:
            faltantes.append("PLAN (ej: trimestral full, mensual dos)")
        if "monto" not in parsed:
            faltantes.append("MONTO (en miles)")
        if "matricula" not in parsed:
            faltantes.append("MATRICULA (en miles)")

        if faltantes:
            msg = "Todavía falta:\n" + "\n".join(f"• {f}" for f in faltantes)
            await proveedor.enviar_mensaje(admin_phone, msg)
            return

        # Todo completo → pedir confirmación
        metodo = parsed.get("metodo", "TRANSFER")
        await _mostrar_confirmacion(admin_phone, datos["prueba"], datos["todas_pruebas"], parsed, metodo)
        return

    # Confirmar con si/no
    if datos["step"] == "confirmar":
        _r = texto.strip().lower().rstrip("!.,")
        if _r in ("si", "sí", "dale", "ok", "va", "confirmar", "listo", "yes"):
            _inscripcion_pendiente.pop(admin_phone, None)
            d = datos
            await _ejecutar_inscripcion(
                admin_phone, d["prueba"], d["todas_pruebas"],
                d["plan"], d["metodo"], d["monto"], d["matricula"]
            )
        elif _r in ("no", "cancelar", "cancel", "na"):
            _inscripcion_pendiente.pop(admin_phone, None)
            await proveedor.enviar_mensaje(admin_phone, "Cancelado ❌")
        else:
            await proveedor.enviar_mensaje(admin_phone, "Respondé *si* o *no*")
        return

    _inscripcion_pendiente.pop(admin_phone, None)


async def _mostrar_confirmacion(admin_phone: str, prueba: dict, todas_pruebas: list[dict], parsed: dict, metodo: str):
    """Muestra resumen y pide confirmación si/no."""
    fp = prueba.get("fields", {})
    tel = fp.get("TELEFONO", "")
    nombre_padre = f"{fp.get('NOMBRE', '')} {fp.get('APELLIDO', '')}".strip()
    hijos_txt = ", ".join(
        f"{op.get('fields', {}).get('NOMBRE HIJO', '')} ({op.get('fields', {}).get('EDAD HIJO', '?')})"
        for op in todas_pruebas if op.get("fields", {}).get("NOMBRE HIJO")
    )
    plan = parsed["plan"]
    monto = parsed["monto"]
    matricula = parsed["matricula"]

    msg = (
        f"📋 *CONFIRMAR INSCRIPCIÓN*\n\n"
        f"👨 {nombre_padre} ({tel})\n"
        f"👶 {hijos_txt}\n\n"
        f"📋 Plan: {plan}\n"
        f"💳 Método: {metodo}\n"
        f"💰 Monto plan: {monto // 1000}mil\n"
        f"💰 Matrícula: {matricula // 1000}mil\n\n"
        f"¿Confirmar? (si/no)"
    )

    _inscripcion_pendiente[admin_phone] = {
        "step": "confirmar",
        "prueba": prueba,
        "todas_pruebas": todas_pruebas,
        "plan": plan,
        "metodo": metodo,
        "monto": monto,
        "matricula": matricula,
    }
    await proveedor.enviar_mensaje(admin_phone, msg)


async def _ejecutar_inscripcion(
    admin_phone: str, prueba: dict, todas_pruebas: list[dict],
    plan: str, metodo: str, monto: int, matricula: int
):
    """Crea FAMILIA + NIÑOS + PAGOS + marca INSCRIPTO."""
    from agent.airtable_client import (
        _get_records, _post, _patch, _PRUEBAS, _LEADS, _FAMILIAS,
        crear_familia, crear_nino,
    )

    fp = prueba.get("fields", {})
    tel = fp.get("TELEFONO", "")
    nombre_padre = fp.get("NOMBRE", "")
    apellido_padre = fp.get("APELLIDO", "")

    # ── 1. Crear FAMILIA ──────────────────────────────────────────────
    familia_id = await crear_familia({
        "padre": {
            "nombre": nombre_padre,
            "apellido": apellido_padre,
            "telefono": tel,
        }
    })
    if not familia_id:
        await proveedor.enviar_mensaje(admin_phone, "Error creando familia en Airtable")
        return

    await _patch(_FAMILIAS, familia_id, {
        "PLAN": plan,
        "METODO PAGO": metodo,
        "ESTADO PLAN": "ACTIVO",
    })

    # ── 2. Crear NIÑO(S) ─────────────────────────────────────────────
    ninos_creados = []
    for op in todas_pruebas:
        of = op.get("fields", {})
        h_nombre = of.get("NOMBRE HIJO", "")
        h_apellido = of.get("APELLIDO HIJO", "")
        h_fn = of.get("FECHA NACIMIENTO", "")
        h_genero = of.get("GENERO", "")
        if h_nombre:
            nino_id = await crear_nino({
                "nombre": h_nombre,
                "apellido": h_apellido,
                "fecha_nacimiento": h_fn,
                "sexo": h_genero,
            }, familia_id)
            if nino_id:
                ninos_creados.append(f"{h_nombre} {h_apellido}")
                # Migrar cara de PRUEBA FENIX → NIÑOS FENIX
                prueba_face_id = of.get("FACE_ID", "")
                prueba_foto = of.get("FOTO", [])
                if prueba_face_id:
                    try:
                        import httpx
                        from agent.face_recognition import actualizar_cara
                        from agent.airtable_client import _patch, _NINOS
                        # Re-indexar con el nuevo record_id del niño
                        if prueba_foto:
                            foto_bytes = None
                            async with httpx.AsyncClient(timeout=30) as _hc:
                                _r = await _hc.get(prueba_foto[0]["url"])
                                if _r.status_code == 200:
                                    foto_bytes = _r.content
                            if foto_bytes:
                                new_face_id = await actualizar_cara(nino_id, foto_bytes)
                                if new_face_id:
                                    await _patch(_NINOS, nino_id, {"FACE_ID": new_face_id})
                                    logger.info(f"[FOTOS] Cara migrada de PRUEBA→NIÑO: {h_nombre} {h_apellido}")
                    except Exception as e:
                        logger.warning(f"[FOTOS] Error migrando cara: {e}")

    # ── 3. Crear PAGOS ───────────────────────────────────────────────
    _pagos_tabla = "PAGOS"
    pagos_creados = []

    _metodo_pagos = {
        "SUSCRIPCION": "TRANSFER", "TRANSFER": "TRANSFER",
        "DEB": "DEBIT CARD", "CRED": "CREDIT CARD", "EFECTIVO": "EFECTIVO",
    }
    metodo_pago_tabla = _metodo_pagos.get(metodo, "TRANSFER")

    _concepto_map = {
        "QUINCENAL MENSUAL": "F.MENSUAL250",
        "SEMANAL MENSUAL": "F.MENSUAL 350",
        "QUINCENAL TRIMESTRAL": "F.TRI 450",
        "SEMANAL TRIMESTRAL": "F.TRI 690",
    }
    _matri_concepto = "F.140/MATRICULA" if matricula <= 140_000 else "F.200/MATRICULA"

    if matricula > 0:
        pago_matri = await _post(_pagos_tabla, {
            "MONTO": matricula,
            "METODO DE PAGO": metodo_pago_tabla,
            "CONCEPTO": _matri_concepto,
            "ESTADO DE PAGO": "PAGADO",
            "FUENTE": "FENIX KIDS ACADEMY",
            "FAMILIA FENIX": [familia_id],
            "EXCEL": True,
        })
        if pago_matri:
            pagos_creados.append(f"Matrícula {matricula // 1000}mil")

    if monto > 0:
        concepto_plan = _concepto_map.get(plan, "MENSUAL")
        pago_plan = await _post(_pagos_tabla, {
            "MONTO": monto,
            "METODO DE PAGO": metodo_pago_tabla,
            "CONCEPTO": concepto_plan,
            "ESTADO DE PAGO": "PAGADO",
            "FUENTE": "FENIX KIDS ACADEMY",
            "FAMILIA FENIX": [familia_id],
            "EXCEL": True,
        })
        if pago_plan:
            pagos_creados.append(f"Plan {monto // 1000}mil")

    # ── 4. Marcar INSCRIPTO ──────────────────────────────────────────
    for op in todas_pruebas:
        await _patch(_PRUEBAS, op["id"], {
            "CONVERSION": "INSCRIPTO",
            "FAMILIA": [familia_id],
        })

    leads = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{tel}'", max_records=5)
    for lead in leads:
        await _patch(_LEADS, lead["id"], {
            "CONVERSION": "INSCRIPTO",
            "FAMILIA": [familia_id],
        })

    # ── Confirmar ─────────────────────────────────────────────────────
    msg = (
        f"✅ *FAMILIA CARGADA*\n\n"
        f"👨 {nombre_padre} {apellido_padre} ({tel})\n"
        f"👶 Hijos: {', '.join(ninos_creados) if ninos_creados else 'ninguno'}\n"
        f"📋 Plan: {plan}\n"
        f"💳 Método: {metodo}\n"
        f"💰 Pagos: {', '.join(pagos_creados) if pagos_creados else 'ninguno'}\n"
        f"🟢 Estado: ACTIVO\n\n"
        f"PRUEBA → INSCRIPTO ✅\n"
        f"LEAD → INSCRIPTO ✅"
    )
    await proveedor.enviar_mensaje(admin_phone, msg)
    logger.info(f"[INSCRIPCION] Familia creada: {nombre_padre} {apellido_padre} ({tel}) plan={plan} monto={monto} matri={matricula}")


# ── Follow-up leads (tracking + loop diario) ────────────────────────────────

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
                    f"Preguntá si le gustaría agendar un sábado inolvidable para él y {nombre_hijo or 'su hijo/a'}. "
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

                # Espejar en Telegram
                try:
                    _topic_fu = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=group_id_para_agente("ivan"))
                    if _topic_fu:
                        await enviar_a_topic(_topic_fu, f"🔔 FOLLOWUP ({nuevo}/3): {respuesta_fu}", telefono=telefono, group_override=group_id_para_agente("ivan"))
                except Exception:
                    pass

                logger.info(f"[FOLLOWUP] {telefono}: seguimiento {nuevo}/3 enviado")
                await asyncio.sleep(3)  # pausa entre leads
            except Exception as e:
                logger.error(f"[FOLLOWUP] Error enviando a {telefono}: {e}")

    except Exception as e:
        logger.error(f"[FOLLOWUP] Error en ciclo: {e}")

    logger.info("[FOLLOWUP] Ciclo completado")


# ── Resumen anuncios (comando admin) ─────────────────────────────────────────

_DIAS_SEMANA = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
_MESES_NOMBRE = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
                 7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
_MONTOS_CONCEPTO = {
    "F.PRUEBA 90MIL": 90_000,
    "F.PRUEBA 120MIL": 120_000,
    "F.PRUEBA 150MIL": 150_000,
}


def _parsear_filtro_fecha(texto_cmd: str) -> tuple[str, str | None, str | None]:
    """
    Parsea el filtro de fecha del comando resumen anuncios.
    Retorna (label, fecha_desde, fecha_hasta) en formato YYYY-MM-DD.
    None = sin filtro (mes corriente por default).
    """
    from datetime import date, timedelta, datetime, timezone

    # Paraguay es UTC-3 — Railway corre en UTC, así que forzamos hora PY
    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    # "resumen anuncios hoy"
    if "hoy" in texto_cmd:
        iso = hoy.isoformat()
        return f"hoy ({hoy.day}/{hoy.month})", iso, iso

    # "resumen anuncios ayer"
    if "ayer" in texto_cmd:
        ayer = hoy - timedelta(days=1)
        iso = ayer.isoformat()
        return f"ayer ({ayer.day}/{ayer.month})", iso, iso

    # "resumen anuncios abril" / "resumen anuncios marzo"
    for num, nombre in _MESES_NOMBRE.items():
        if nombre in texto_cmd:
            desde = f"{hoy.year}-{num:02d}-01"
            if num == 12:
                hasta = f"{hoy.year + 1}-01-01"
            else:
                hasta = f"{hoy.year}-{num + 1:02d}-01"
            # hasta es el primer día del mes siguiente (exclusive)
            ultimo = date.fromisoformat(hasta) - timedelta(days=1)
            return f"{nombre} {hoy.year}", desde, ultimo.isoformat()

    # Default: mes corriente
    desde = f"{hoy.year}-{hoy.month:02d}-01"
    if hoy.month == 12:
        hasta_next = f"{hoy.year + 1}-01-01"
    else:
        hasta_next = f"{hoy.year}-{hoy.month + 1:02d}-01"
    ultimo = date.fromisoformat(hasta_next) - timedelta(days=1)
    return f"{_MESES_NOMBRE[hoy.month]} {hoy.year}", desde, ultimo.isoformat()


async def _generar_resumen_reservas(telefono: str, fecha_override=None):
    """Genera resumen de reservas de un sábado, agrupado por turno.
    Si fecha_override es None, usa el sábado más cercano.
    Separa AURORA (alumnos inscriptos) y FENIX (clases de prueba)."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario, _get_records, _PRUEBAS
    import httpx as _httpx_res

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        # Calcular el sábado más cercano (hoy si es sábado, sino el próximo)
        dias_hasta_sabado = (5 - hoy.weekday()) % 7
        if dias_hasta_sabado == 0 and hoy.weekday() != 5:
            dias_hasta_sabado = 7
        sabado = hoy + timedelta(days=dias_hasta_sabado)
    fecha_iso = sabado.isoformat()

    _DIAS = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
    _MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
              7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
    fecha_label = f"{_DIAS[sabado.weekday()]} {sabado.day}/{sabado.month}"
    # FECHA RESERVA en PRUEBA FENIX se guarda como "9 de mayo" (texto, no ISO)
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    turnos = ["9:30", "11:00", "15:30"]

    # ── AURORA: alumnos inscriptos (RESERVAS FENIX via HORARIOS) ──
    aurora_por_turno = {}
    for hora in turnos:
        ninos = await obtener_ninos_por_horario(fecha_iso, hora)
        aurora_por_turno[hora] = ninos

    # ── FENIX: clases de prueba (PRUEBA FENIX con FECHA RESERVA = sábado) ──
    # Buscar por formato texto ("9 de mayo") y también ISO por si se normaliza a futuro
    pruebas_texto = await _get_records(
        _PRUEBAS,
        formula=f"{{FECHA RESERVA}}='{fecha_texto}'",
        max_records=50,
    )
    pruebas_iso = await _get_records(
        _PRUEBAS,
        formula=f"{{FECHA RESERVA}}='{fecha_iso}'",
        max_records=50,
    )
    # Dedup por record id
    _seen_ids = set()
    pruebas = []
    for rec in pruebas_texto + pruebas_iso:
        if rec["id"] not in _seen_ids:
            _seen_ids.add(rec["id"])
            pruebas.append(rec)
    fenix_por_turno: dict[str, list[dict]] = {h: [] for h in turnos}
    for rec in pruebas:
        f = rec.get("fields", {})
        hora_raw = (f.get("HORA") or "").strip()
        # Normalizar para matchear turnos (ej: "11h" → "11:00", "9:30h" → "9:30")
        if hora_raw not in fenix_por_turno:
            _h_clean = hora_raw.replace("h", "").replace("hs", "").strip()
            for t in turnos:
                if _h_clean == t or _h_clean.lstrip("0") == t or _h_clean == t.split(":")[0]:
                    hora_raw = t
                    break
        if hora_raw in fenix_por_turno:
            nombre = f.get("NOMBRE HIJO", "")
            apellido = f.get("APELLIDO HIJO", "")
            edad = str(f["EDAD HIJO"]) if f.get("EDAD HIJO") else ""
            fenix_por_turno[hora_raw].append({
                "nombre": nombre,
                "apellido": apellido,
                "edad": edad,
            })

    # ── Armar mensaje ──
    emojis = ["🦁", "🐯", "🦊", "🐻", "🐼", "🦋", "🌟", "⚡", "🔥", "🎯", "🦅", "🐺", "🌈", "🎪", "🏆"]
    lineas = [f"📋 *RESERVAS — {fecha_label}*\n"]
    total_aurora = 0
    total_fenix = 0

    for hora in turnos:
        aurora = aurora_por_turno[hora]
        fenix = fenix_por_turno[hora]
        total_turno = len(aurora) + len(fenix)
        total_aurora += len(aurora)
        total_fenix += len(fenix)

        # Calcular edad promedio del turno (edad viene como "3,5" = 3 años 5 meses)
        edades_turno = []
        for n in aurora + fenix:
            try:
                _edad_raw = str(n.get("edad", ""))
                if "," in _edad_raw:
                    _a, _m = _edad_raw.split(",", 1)
                    edades_turno.append(int(_a) + int(_m) / 12)
                elif _edad_raw:
                    edades_turno.append(int(_edad_raw))
            except (ValueError, KeyError, TypeError):
                pass
        prom_str = f" — prom {sum(edades_turno)/len(edades_turno):.0f} años" if edades_turno else ""

        lineas.append(f"⏰ *{hora}h* — {total_turno} niño{'s' if total_turno != 1 else ''}{prom_str}")

        if aurora:
            lineas.append(f"   🌳 *Aurora ({len(aurora)}):*")
            for i, n in enumerate(aurora):
                emoji = emojis[i % len(emojis)]
                nombre = (n.get("apodo") or n["nombre"]).split()[0]
                apellido = n["apellido"].split()[0] if n["apellido"] else ""
                nombre_full = f"{nombre} {apellido}".strip()
                edad_str = f" ({n['edad']})" if n.get("edad") else ""
                lineas.append(f"      {emoji} {nombre_full}{edad_str}")

        if fenix:
            lineas.append(f"   🔥 *Fenix — prueba ({len(fenix)}):*")
            for i, n in enumerate(fenix):
                emoji = emojis[(i + len(aurora)) % len(emojis)]
                nombre = n["nombre"].split()[0] if n["nombre"] else ""
                apellido = n["apellido"].split()[0] if n["apellido"] else ""
                nombre_full = f"{nombre} {apellido}".strip()
                edad_str = f" ({n['edad']})" if n.get("edad") else ""
                lineas.append(f"      {emoji} {nombre_full}{edad_str}")

        if not aurora and not fenix:
            lineas.append("   — vacío")

        lineas.append("")

    total = total_aurora + total_fenix
    lineas.append(f"👧👦 *Total: {total} guerrero{'s' if total != 1 else ''}*")
    lineas.append(f"   🌳 Aurora: {total_aurora} | 🔥 Prueba: {total_fenix}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_telegram(telefono: str):
    """Genera resumen de reservas con link de Telegram debajo de cada nombre."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records, _PRUEBAS
    from agent.telegram_bridge import obtener_topic

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    dias_hasta_sabado = (5 - hoy.weekday()) % 7
    if dias_hasta_sabado == 0 and hoy.weekday() != 5:
        dias_hasta_sabado = 7
    sabado = hoy + timedelta(days=dias_hasta_sabado)
    _MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
              7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"
    fecha_iso = sabado.isoformat()

    # Buscar PRUEBA FENIX por texto e ISO
    pruebas_texto = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_texto}'", max_records=50)
    pruebas_iso = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_iso}'", max_records=50)
    _seen = set()
    pruebas = []
    for rec in pruebas_texto + pruebas_iso:
        if rec["id"] not in _seen:
            _seen.add(rec["id"])
            pruebas.append(rec)

    turnos = ["9:30", "11:00", "15:30"]
    por_turno: dict[str, list[dict]] = {h: [] for h in turnos}

    for rec in pruebas:
        f = rec.get("fields", {})
        hora_raw = (f.get("HORA") or "").strip()
        # Normalizar
        if hora_raw not in por_turno:
            _h = hora_raw.replace("h", "").replace("hs", "").strip()
            for t in turnos:
                if _h == t or _h.lstrip("0") == t or _h == t.split(":")[0]:
                    hora_raw = t
                    break
        if hora_raw in por_turno:
            por_turno[hora_raw].append({
                "nombre": f.get("NOMBRE HIJO", ""),
                "apellido": f.get("APELLIDO HIJO", ""),
                "tel": f.get("TELEFONO", ""),
                "conversion": f.get("CONVERSION", ""),
                "responsable": f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip(),
            })

    # Agrupar por teléfono dentro de cada turno para hermanos
    lineas = [f"📋 *RESERVAS + TELEGRAM — SAB {sabado.day}/{sabado.month}*\n"]
    total = 0

    for hora in turnos:
        kids = por_turno[hora]
        # Agrupar por tel
        by_tel: dict[str, list] = {}
        for k in kids:
            tel = k["tel"]
            if tel not in by_tel:
                by_tel[tel] = {"nombres": [], "responsable": k.get("responsable", "")}
            nombre = f"{k['nombre']} {k['apellido']}".strip()
            if k.get("conversion") == "CANCELADO":
                nombre += " (CANCELADO)"
            by_tel[tel]["nombres"].append(nombre)

        count = sum(len(v["nombres"]) for v in by_tel.values())
        total += count
        lineas.append(f"⏰ *{hora}h* — {count} niño{'s' if count != 1 else ''}")

        for tel, data in by_tel.items():
            # Get Telegram topic link
            topic = await obtener_topic(tel)
            if topic and topic.group_id:
                gid = str(topic.group_id).replace("-100", "", 1)
                tg_link = f"https://t.me/c/{gid}/{topic.topic_id}"
            elif topic:
                tg_link = f"topic:{topic.topic_id}"
            else:
                tg_link = "sin topic"

            for nombre in data["nombres"]:
                lineas.append(f"   - {nombre}")
            if data["responsable"]:
                lineas.append(f"     👤 {data['responsable']}")
            lineas.append(f"     💬 {tg_link}")
            lineas.append("")

        if not kids:
            lineas.append("   — vacío")
            lineas.append("")

    lineas.append(f"👧👦 *Total: {total}*")
    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_lista_asistencia(telefono: str, turno_especifico: str = ""):
    """Genera lista numerada de niños para pasar asistencia. Guarda estado en _asistencia_pendiente."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario, _get_records, _PRUEBAS

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    # Si es sábado, usar hoy. Si no, buscar el sábado más cercano pasado (para control post-clase)
    if hoy.weekday() == 5:
        sabado = hoy
    else:
        # Último sábado
        sabado = hoy - timedelta(days=(hoy.weekday() + 2) % 7)

    fecha_iso = sabado.isoformat()
    _MESES = {1:"enero",2:"febrero",3:"marzo",4:"abril",5:"mayo",6:"junio",
              7:"julio",8:"agosto",9:"septiembre",10:"octubre",11:"noviembre",12:"diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    turnos = [turno_especifico] if turno_especifico else ["9:30", "11:00", "15:30"]
    registros = []  # lista global numerada
    lineas = [f"✅ *ASISTENCIA — SAB {sabado.day}/{sabado.month}*\n"]

    for hora in turnos:
        # Aurora (inscriptos)
        ninos_aurora = await obtener_ninos_por_horario(fecha_iso, hora)
        # Fenix (pruebas)
        pruebas = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_texto}', {{HORA}}='{hora}')", max_records=50)
        # También buscar por ISO
        pruebas_iso = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_iso}', {{HORA}}='{hora}')", max_records=50)
        _seen = set()
        for p in pruebas + pruebas_iso:
            if p["id"] not in _seen:
                _seen.add(p["id"])

        total = len(ninos_aurora) + len(_seen)
        if total == 0:
            continue

        lineas.append(f"⏰ *{hora}h* ({total})")

        # Aurora
        for n in ninos_aurora:
            idx = len(registros) + 1
            _n_parts = (n.get("apodo") or n.get("nombre", "?")).split()
            nombre = _n_parts[0] if _n_parts else "?"
            _a_parts = (n.get("apellido") or "").split()
            apellido = _a_parts[0] if _a_parts else ""
            nombre_full = f"{nombre} {apellido}".strip()
            reserva_id = n.get("reserva_id", "")
            registros.append({"idx": idx, "nombre": nombre_full, "tabla": "RESERVAS", "record_id": reserva_id, "nino_id": n.get("id", "")})
            lineas.append(f"   {idx}. {nombre_full}")

        # Fenix pruebas
        for pid in _seen:
            p = next(x for x in pruebas + pruebas_iso if x["id"] == pid)
            f = p.get("fields", {})
            if f.get("CONVERSION") == "CANCELADO":
                continue
            idx = len(registros) + 1
            _n_parts = (f.get("NOMBRE HIJO") or "?").split()
            nombre = _n_parts[0] if _n_parts else "?"
            _a_parts = (f.get("APELLIDO HIJO") or "").split()
            apellido = _a_parts[0] if _a_parts else ""
            nombre_full = f"{nombre} {apellido}".strip()
            registros.append({"idx": idx, "nombre": nombre_full, "tabla": "PRUEBAS", "record_id": p["id"]})
            lineas.append(f"   {idx}. {nombre_full} 🔥")

        lineas.append("")

    if not registros:
        await proveedor.enviar_mensaje(telefono, "No hay reservas para pasar asistencia.")
        return

    lineas.append(f"*Total: {len(registros)}*")
    lineas.append("")
    lineas.append("Respondé *ok* (todos vinieron) o los números de los que faltaron (ej: 5 7)")

    _asistencia_pendiente[telefono] = registros
    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _procesar_respuesta_asistencia(telefono: str, respuesta: str):
    """Procesa la respuesta de asistencia: 'ok' o '5 7' (ausentes)."""
    from agent.airtable_client import _patch, _RESERVAS, _PRUEBAS

    registros = _asistencia_pendiente.pop(telefono, [])
    if not registros:
        await proveedor.enviar_mensaje(telefono, "No hay asistencia pendiente.")
        return

    if respuesta == "ok":
        ausentes = set()
    else:
        # Aceptar "1 2", "1,2", "1, 2", etc.
        _nums = re.split(r'[\s,]+', respuesta)
        ausentes = set(int(n) for n in _nums if n.isdigit())

    presentes = 0
    ausentes_nombres = []

    for reg in registros:
        es_presente = reg["idx"] not in ausentes
        if reg["tabla"] == "RESERVAS" and reg.get("record_id"):
            await _patch(_RESERVAS, reg["record_id"], {"PRESENTE": es_presente})
        elif reg["tabla"] == "PRUEBAS" and reg.get("record_id"):
            await _patch(_PRUEBAS, reg["record_id"], {"PRESENTE": es_presente})

        if es_presente:
            presentes += 1
        else:
            ausentes_nombres.append(reg["nombre"])

    msg = f"✅ Asistencia cargada!\n\nPresentes: {presentes}/{len(registros)}"
    if ausentes_nombres:
        msg += f"\nAusentes: {', '.join(ausentes_nombres)}"

    await proveedor.enviar_mensaje(telefono, msg)
    logger.info(f"[ASISTENCIA] {presentes}/{len(registros)} presentes, ausentes: {ausentes_nombres}")


async def _enviar_asistencia_automatica(turno: str):
    """Envía la lista de asistencia automáticamente al terminar un turno."""
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    try:
        await _generar_lista_asistencia(admin_phone, turno_especifico=turno)
        logger.info(f"[ASISTENCIA] Lista automática enviada para turno {turno}")
    except Exception as e:
        logger.error(f"[ASISTENCIA] Error enviando lista automática: {e}")


async def _generar_resumen_asistencia(telefono: str, fecha_override=None):
    """
    Genera resumen de quién VINO a clase (PRESENTE=true), por turno.
    Separa inscriptos (Aurora/RESERVAS) y pruebas (Fenix/PRUEBA FENIX).
    Si fecha_override=None, usa el sábado más reciente.
    """
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records, _PRUEBAS, _RESERVAS, _HORARIOS, _NINOS, _BASE_URL, _headers
    import httpx

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        dias_desde_sabado = (hoy.weekday() - 5) % 7
        if dias_desde_sabado == 0 and hoy.weekday() != 5:
            dias_desde_sabado = 7
        sabado = hoy - timedelta(days=dias_desde_sabado)

    fecha_iso = sabado.isoformat()
    _MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
              7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    turnos = ["9:30", "11:00", "15:30"]
    lineas = [f"📋 *ASISTENCIA — SÁB {sabado.day}/{sabado.month}*\n"]

    total_presentes = 0
    total_ausentes = 0
    total_aurora = 0
    total_fenix = 0

    for hora in turnos:
        presentes_turno = []
        ausentes_turno = []

        # ── Inscriptos (RESERVAS FENIX) ── buscar horario → reservas → verificar PRESENTE
        horarios = await _get_records(_HORARIOS, formula=f"AND(DATESTR({{FECHA}})='{fecha_iso}', {{HORA}}='{hora}')", max_records=1)
        if horarios:
            reserva_ids = horarios[0].get("fields", {}).get("RESERVAS FENIX", [])
            async with httpx.AsyncClient() as client:
                for res_id in reserva_ids:
                    try:
                        r = await client.get(f"{_BASE_URL}/{_RESERVAS}/{res_id}", headers=_headers(), timeout=10)
                        if r.status_code != 200:
                            continue
                        res_f = r.json().get("fields", {})
                        presente = res_f.get("PRESENTE", False)
                        nino_ids = res_f.get("NINO", [])
                        for nino_id in nino_ids:
                            rn = await client.get(f"{_BASE_URL}/{_NINOS}/{nino_id}", headers=_headers(), timeout=10)
                            if rn.status_code != 200:
                                continue
                            nf = rn.json().get("fields", {})
                            nombre = (nf.get("APODO") or nf.get("NOMBRE") or "?").strip().split()[0] if (nf.get("APODO") or nf.get("NOMBRE")) else "?"
                            apellido = (nf.get("APELLIDO") or "").strip().split()[0] if nf.get("APELLIDO") else ""
                            nombre_full = f"{nombre} {apellido}".strip()
                            edad = str(nf.get("EDAD", "")) if nf.get("EDAD") else ""
                            edad_str = f" ({edad})" if edad else ""
                            if presente:
                                presentes_turno.append(f"✅ {nombre_full}{edad_str}")
                                total_aurora += 1
                            else:
                                ausentes_turno.append(f"❌ {nombre_full}{edad_str}")
                    except Exception as e:
                        logger.warning(f"[RESUMEN ASIS] Error reserva {res_id}: {e}")

        # ── Pruebas (PRUEBA FENIX) ──
        pruebas = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_texto}', {{HORA}}='{hora}')", max_records=50)
        pruebas_iso = await _get_records(_PRUEBAS, formula=f"AND({{FECHA RESERVA}}='{fecha_iso}', {{HORA}}='{hora}')", max_records=50)
        _seen = set()
        for p in pruebas + pruebas_iso:
            if p["id"] in _seen:
                continue
            _seen.add(p["id"])
            f = p.get("fields", {})
            if f.get("CONVERSION") == "CANCELADO":
                continue
            nombre = (f.get("NOMBRE HIJO") or "?").strip().split()[0] if f.get("NOMBRE HIJO") else "?"
            apellido = (f.get("APELLIDO HIJO") or "").strip().split()[0] if f.get("APELLIDO HIJO") else ""
            nombre_full = f"{nombre} {apellido}".strip()
            edad = f.get("EDAD HIJO", "")
            edad_str = f" ({edad})" if edad else ""
            presente = f.get("PRESENTE", False)
            if presente:
                presentes_turno.append(f"✅ {nombre_full}{edad_str} 🔥")
                total_fenix += 1
            else:
                ausentes_turno.append(f"❌ {nombre_full}{edad_str} 🔥")

        n_presentes = len(presentes_turno)
        n_total = n_presentes + len(ausentes_turno)
        total_presentes += n_presentes
        total_ausentes += len(ausentes_turno)

        if n_total == 0:
            continue

        lineas.append(f"⏰ *{hora}h* — {n_presentes}/{n_total} presentes")
        for l in presentes_turno:
            lineas.append(f"   {l}")
        for l in ausentes_turno:
            lineas.append(f"   {l}")
        lineas.append("")

    if total_presentes == 0 and total_ausentes == 0:
        await proveedor.enviar_mensaje(telefono, f"No hay datos de asistencia para el {sabado.day}/{sabado.month}.")
        return

    lineas.append(f"*TOTAL: {total_presentes} presentes, {total_ausentes} ausentes*")
    lineas.append(f"Aurora: {total_aurora} | Fenix (prueba): {total_fenix}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_prueba(telefono: str, fecha_override=None):
    """
    Dashboard de PRUEBA FENIX para un sábado:
    - Asistencia por turno
    - Total pagos prueba
    - Inscriptos
    - Seguimiento enviado/descartado/pendiente
    """
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records, _PRUEBAS

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        dias_desde_sabado = (hoy.weekday() - 5) % 7
        if dias_desde_sabado == 0 and hoy.weekday() != 5:
            dias_desde_sabado = 7
        sabado = hoy - timedelta(days=dias_desde_sabado)

    fecha_iso = sabado.isoformat()
    _MESES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
              7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
    fecha_texto = f"{sabado.day} de {_MESES[sabado.month]}"

    # Obtener todas las pruebas de esa fecha
    pruebas_t = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_texto}'", max_records=50)
    pruebas_i = await _get_records(_PRUEBAS, formula=f"{{FECHA RESERVA}}='{fecha_iso}'", max_records=50)
    _seen = set()
    pruebas = []
    for p in pruebas_t + pruebas_i:
        if p["id"] not in _seen:
            _seen.add(p["id"])
            pruebas.append(p)

    # Filtrar cancelados
    pruebas = [p for p in pruebas if p.get("fields", {}).get("CONVERSION") != "CANCELADO"]

    if not pruebas:
        await proveedor.enviar_mensaje(telefono, f"No hay pruebas para el {sabado.day}/{sabado.month}.")
        return

    # Obtener seguimiento de esa fecha
    seg_records = await _get_records("SEGUIMIENTO FENIX", formula=f"DATESTR({{FECHA}})='{fecha_iso}'", max_records=50)
    # Indexar seguimiento por teléfono
    seg_por_tel = {}
    for s in seg_records:
        sf = s.get("fields", {})
        tel = sf.get("TELEFONO", "")
        if tel:
            seg_por_tel[tel] = sf

    # Leer pagos vinculados de cada prueba
    import httpx
    from agent.airtable_client import _BASE_URL, _headers

    async with httpx.AsyncClient() as _hc:
        for p in pruebas:
            f = p.get("fields", {})
            pagos_ids = f.get("PAGOS", [])
            monto_total = 0
            monto_inscripcion = 0
            for pid in pagos_ids:
                try:
                    r = await _hc.get(f"{_BASE_URL}/PAGOS/{pid}", headers=_headers(), timeout=10)
                    if r.status_code == 200:
                        pf = r.json().get("fields", {})
                        m = pf.get("MONTO", 0) or 0
                        concepto = pf.get("CONCEPTO", "")
                        if "PRUEBA" in concepto:
                            monto_total += m
                        else:
                            monto_inscripcion += m
                except Exception:
                    pass
            f["_monto_prueba"] = monto_total
            f["_monto_inscripcion"] = monto_inscripcion

    # Agrupar por teléfono (familia) y turno
    familias = {}
    for p in pruebas:
        f = p.get("fields", {})
        tel = f.get("TELEFONO", "?")
        hora = (f.get("HORA") or "").strip().replace("h", "").replace("hs", "")
        for t in ["9:30", "11:00", "15:30"]:
            if hora == t or hora == t.split(":")[0] or hora.lstrip("0") == t:
                hora = t
                break
        if hora not in ["9:30", "11:00", "15:30"]:
            hora = "15:30"

        nombre_hijo = (f.get("NOMBRE HIJO") or "?").strip()
        edad = f.get("EDAD HIJO", "")
        presente = f.get("PRESENTE", False)
        conversion = f.get("CONVERSION", "")
        inscripcion = f.get("INSCRIPCION", False)
        nombre_padre = f"{f.get('NOMBRE RESPONSABLE', '')} {f.get('APELLIDO RESPONSABLE', '')}".strip()

        # Si no tiene nombre, buscar en seguimiento (tiene el nombre en el mensaje)
        if not nombre_padre and tel in seg_por_tel:
            _seg_msg = seg_por_tel[tel].get("MENSAJE", "")
            if _seg_msg.startswith("Hola "):
                nombre_padre = _seg_msg.split("!")[0].replace("Hola ", "")

        # Si sigue sin nombre, buscar en LEADS
        if not nombre_padre:
            try:
                _leads = await _get_records("LEADS FENIX", formula=f"{{TELEFONO}}='{tel}'", max_records=1)
                if _leads:
                    _lf = _leads[0].get("fields", {})
                    nombre_padre = _lf.get("NOMBRE RESPONSABLE", "")
            except Exception:
                pass

        if tel not in familias:
            familias[tel] = {
                "padre": nombre_padre,
                "turno": hora,
                "hijos": [],
                "monto_prueba": 0,
                "monto_inscripcion": 0,
                "conversion": conversion,
                "inscripcion": inscripcion,
            }
        familias[tel]["hijos"].append({
            "nombre": nombre_hijo,
            "edad": edad,
            "presente": presente,
        })
        familias[tel]["monto_prueba"] += f.get("_monto_prueba", 0)
        _conv_order = {"CONSULTA": 0, "AGENDA": 1, "PAGO": 2, "INSCRIPTO": 3}
        if _conv_order.get(conversion, 0) > _conv_order.get(familias[tel]["conversion"], 0):
            familias[tel]["conversion"] = conversion
        if inscripcion:
            familias[tel]["inscripcion"] = True
        # Guardar familia_id para buscar pagos de inscripción
        familia_ids = f.get("FAMILIA", [])
        if familia_ids and "familia_id" not in familias[tel]:
            familias[tel]["familia_id"] = familia_ids[0]

    # Buscar pagos de inscripción por familia_id
    # Filtrar por FUENTE=FENIX para no traer pagos de Dorita (base compartida)
    _pagos_fenix = await _get_records("PAGOS", formula="{FUENTE}='FENIX KIDS ACADEMY'", max_records=100)
    for tel, fam in familias.items():
        if (fam["conversion"] == "INSCRIPTO" or fam["inscripcion"]) and fam.get("familia_id"):
            fam_id = fam["familia_id"]
            for pg in _pagos_fenix:
                pf = pg.get("fields", {})
                fam_links = pf.get("FAMILIA FENIX", []) or []
                if fam_id in fam_links:
                    concepto = pf.get("CONCEPTO", "")
                    m = pf.get("MONTO", 0) or 0
                    if "PRUEBA" not in concepto:
                        fam["monto_inscripcion"] += m

    total_ninos = 0
    total_presentes = 0
    total_ausentes = 0
    total_pagaron_prueba = 0
    total_inscriptos = 0
    total_seg_enviado = 0
    total_seg_descartado = 0
    total_seg_pendiente = 0
    monto_prueba_total = 0
    monto_inscripcion_total = 0

    lineas = [f"🔥 *RESUMEN PRUEBA — SÁB {sabado.day}/{sabado.month}*\n"]

    # Agrupar familias por turno
    for hora in ["9:30", "11:00", "15:30"]:
        fams_turno = [(tel, fam) for tel, fam in familias.items() if fam["turno"] == hora]
        if not fams_turno:
            continue

        n_hijos_turno = sum(len(fam["hijos"]) for _, fam in fams_turno)
        lineas.append(f"⏰ *{hora}h* ({n_hijos_turno} niños, {len(fams_turno)} familias)")

        for tel, fam in fams_turno:
            padre = fam["padre"] or tel
            conversion = fam["conversion"]
            monto_pr = fam["monto_prueba"]
            monto_insc = fam["monto_inscripcion"]
            inscripto = fam["inscripcion"] or conversion == "INSCRIPTO"

            # Seguimiento
            seg = seg_por_tel.get(tel, {})
            if seg:
                if seg.get("ENVIADO"):
                    seg_ico = "📩"
                    total_seg_enviado += 1
                elif seg.get("DESCARTADO"):
                    seg_ico = "🚫"
                    total_seg_descartado += 1
                else:
                    seg_ico = "⏳"
                    total_seg_pendiente += 1
            else:
                seg_ico = "⏳"
                total_seg_pendiente += 1

            # Línea padre
            padre_info = f"   *{padre}*"
            if monto_pr > 0:
                padre_info += f" | prueba {monto_pr // 1000}mil"
                total_pagaron_prueba += 1
                monto_prueba_total += monto_pr
            if inscripto:
                total_inscriptos += 1
                padre_info += f" | 🎓 INSCRIPTO"
                if monto_insc > 0:
                    padre_info += f" {monto_insc // 1000}mil"
                    monto_inscripcion_total += monto_insc
            padre_info += f" {seg_ico}"
            lineas.append(padre_info)

            # Líneas hijos
            for h in fam["hijos"]:
                total_ninos += 1
                asis = "✅" if h["presente"] else "❌"
                if h["presente"]:
                    total_presentes += 1
                else:
                    total_ausentes += 1
                edad_str = f" ({h['edad']})" if h["edad"] else ""
                lineas.append(f"      {asis} {h['nombre']}{edad_str}")

        lineas.append("")

    recaudado_total = monto_prueba_total + monto_inscripcion_total

    lineas.append(f"📊 *TOTALES*")
    lineas.append(f"👨‍👩‍👧 Familias: {len(familias)} | Niños: {total_ninos}")
    lineas.append(f"✅ Vinieron: {total_presentes} | ❌ No vinieron: {total_ausentes}")
    lineas.append(f"💰 Pagaron prueba: {total_pagaron_prueba} ({monto_prueba_total // 1000}mil)")
    lineas.append(f"🎓 Inscriptos: {total_inscriptos} ({monto_inscripcion_total // 1000}mil)")
    lineas.append(f"💵 *Recaudado total: {recaudado_total // 1000}mil*")
    lineas.append(f"📩 Seguimiento: {total_seg_enviado} | 🚫 {total_seg_descartado} | ⏳ {total_seg_pendiente}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_seguimiento(telefono: str, fecha_override=None):
    """Resumen de mensajes personalizados: enviados, descartados, pendientes."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import _get_records

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha_override:
        sabado = fecha_override
    else:
        # Último sábado
        dias_desde_sabado = (hoy.weekday() - 5) % 7
        if dias_desde_sabado == 0 and hoy.weekday() != 5:
            dias_desde_sabado = 7
        sabado = hoy - timedelta(days=dias_desde_sabado)

    fecha_iso = sabado.isoformat()
    records = await _get_records("SEGUIMIENTO FENIX", formula=f"DATESTR({{FECHA}})='{fecha_iso}'", max_records=50)

    if not records:
        await proveedor.enviar_mensaje(telefono, f"No hay seguimiento para el {sabado.day}/{sabado.month}.")
        return

    enviados = []
    descartados = []
    pendientes = []

    for r in records:
        f = r.get("fields", {})
        msg = f.get("MENSAJE", "")
        if msg.startswith("Hola "):
            nombre = msg.split("!")[0].replace("Hola ", "")
        else:
            nombre = f.get("TELEFONO", "?")
        turno = f.get("TURNO", "")
        linea = f"{nombre} ({turno})"

        if f.get("ENVIADO"):
            enviados.append(linea)
        elif f.get("DESCARTADO"):
            descartados.append(linea)
        else:
            pendientes.append(linea)

    lineas = [f"📋 *SEGUIMIENTO — SÁB {sabado.day}/{sabado.month}*\n"]

    if enviados:
        lineas.append(f"✅ *Enviados ({len(enviados)}):*")
        for l in enviados:
            lineas.append(f"   {l}")
        lineas.append("")

    if descartados:
        lineas.append(f"❌ *Descartados ({len(descartados)}):*")
        for l in descartados:
            lineas.append(f"   {l}")
        lineas.append("")

    if pendientes:
        lineas.append(f"⏳ *Pendientes ({len(pendientes)}):*")
        for l in pendientes:
            lineas.append(f"   {l}")
        lineas.append("")

    lineas.append(f"*Total: {len(records)}* — ✅{len(enviados)} ❌{len(descartados)} ⏳{len(pendientes)}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


async def _generar_resumen_followup(telefono: str):
    """Genera resumen de follow-ups: quién espera respuesta, quién respondió, descartados, pagaron."""
    from datetime import datetime, timezone, timedelta
    from agent.airtable_client import _get_records, _LEADS
    from urllib.parse import quote

    ahora = datetime.now(timezone.utc)
    base_id = os.getenv("AIRTABLE_BASE_ID")
    api_key = os.getenv("AIRTABLE_API_KEY")

    # Traer todos los leads que entraron al sistema de FU (tienen FECHA FOLLOWUP)
    # Incluye CONTACTADO (en proceso) y DESCARTADO (cerrados) y PAGO (convirtieron)
    formula = "NOT({FECHA FOLLOWUP}=BLANK())"
    all_records = []
    offset_fu = None
    import httpx as _httpx_fu
    while True:
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

    # Clasificar leads
    esperando = []      # FU enviado, esperando respuesta (< 24h)
    respondieron = []   # Respondió al último FU, esperando pago
    descartados = []    # No respondió, ventana cerrada
    pagaron = []        # Pagó post-FU

    for rec in all_records:
        f = rec.get("fields", {})
        tel = f.get("TELEFONO", "")
        nombre_padre = (f.get("NOMBRE RESPONSABLE", "") or "").split()[0] if f.get("NOMBRE RESPONSABLE") else tel[-4:]
        nombre_hijo = f.get("NOMBRE NIÑO", "") or ""
        conversion = f.get("CONVERSION", "")
        seguimientos = f.get("SEGUIMIENTOS", 0) or 0
        respondio_fu1 = f.get("RESPONDIO FU1", False)
        respondio_fu2 = f.get("RESPONDIO FU2", False)
        fecha_fu = f.get("FECHA FOLLOWUP", "")
        pago_post = f.get("PAGO POST FU", 0) or 0

        if not tel:
            continue

        # Calcular horas desde último FU
        horas_desde = 0
        try:
            fecha_ultimo = datetime.fromisoformat(fecha_fu.replace("Z", "+00:00"))
            horas_desde = (ahora - fecha_ultimo).total_seconds() / 3600
        except Exception:
            pass

        label = f"{nombre_padre} ({nombre_hijo})" if nombre_hijo else nombre_padre

        # Clasificar
        if conversion == "PAGO":
            if pago_post or seguimientos >= 1:
                pagaron.append(f"💰 {label} — pagó post FU{seguimientos}")
            continue

        if conversion == "DESCARTADO":
            fu_label = f"FU{seguimientos}" if seguimientos else "FU1"
            descartados.append(f"⛔ {label} — no respondió {fu_label}")
            continue

        # CONTACTADO — en proceso
        if seguimientos == 0:
            # Tiene FECHA FOLLOWUP pero SEGUIMIENTOS=0 → esperando primer FU
            esperando.append(f"⏳ {label} — esperando FU1 ({int(horas_desde)}h)")
            continue

        # Determinar si respondió al último FU
        if seguimientos == 1:
            if respondio_fu1:
                respondieron.append(f"✅ {label} — respondió FU1, esperando pago")
            else:
                esperando.append(f"🟡 {label} — FU1 enviado hace {int(horas_desde)}h")
        elif seguimientos == 2:
            if respondio_fu2:
                respondieron.append(f"✅ {label} — respondió FU2, esperando pago")
            else:
                esperando.append(f"🟡 {label} — FU2 enviado hace {int(horas_desde)}h")
        elif seguimientos >= 3:
            esperando.append(f"🔴 {label} — FU3 enviado hace {int(horas_desde)}h")

    # Armar mensaje
    lineas = ["📊 *RESUMEN FOLLOWUP*\n"]

    if esperando:
        lineas.append(f"🟡 *EN CURSO ({len(esperando)}):*")
        lineas.extend(esperando)
        lineas.append("")

    if respondieron:
        lineas.append(f"✅ *RESPONDIERON ({len(respondieron)}):*")
        lineas.extend(respondieron)
        lineas.append("")

    if pagaron:
        lineas.append(f"💰 *PAGARON POST-FU ({len(pagaron)}):*")
        lineas.extend(pagaron)
        lineas.append("")

    if descartados:
        lineas.append(f"❌ *DESCARTADOS ({len(descartados)}):*")
        lineas.extend(descartados)
        lineas.append("")

    total = len(esperando) + len(respondieron) + len(pagaron) + len(descartados)
    lineas.append(f"📈 *Total en FU: {total}* — ✅{len(respondieron)} 💰{len(pagaron)} ❌{len(descartados)} 🟡{len(esperando)}")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


def _fecha_py(iso_str: str) -> str:
    """Convierte un timestamp ISO (UTC o con offset) a fecha PY (YYYY-MM-DD).
    Si solo tiene fecha sin hora, la devuelve tal cual."""
    from datetime import datetime, timezone, timedelta
    _PY_TZ = timezone(timedelta(hours=-3))
    if not iso_str:
        return ""
    try:
        # Intentar parsear como datetime completo
        if "T" in iso_str:
            # fromisoformat maneja offsets como +00:00 y -03:00
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.astimezone(_PY_TZ).date().isoformat()
        # Solo fecha, devolver tal cual
        return iso_str[:10]
    except Exception:
        return iso_str[:10]


async def _generar_resumen_anuncios(telefono: str, texto_cmd: str):
    """Genera y envía resumen de PRUEBA FENIX agrupado por fecha."""
    from datetime import date as _date_cls
    from collections import defaultdict
    import httpx as _httpx_r

    label, fecha_desde, fecha_hasta = _parsear_filtro_fecha(texto_cmd)

    # Paginar todos los registros de PRUEBA FENIX
    all_records = []
    offset = None
    base_id = os.getenv("AIRTABLE_BASE_ID")
    api_key = os.getenv("AIRTABLE_API_KEY")
    while True:
        params = f"pageSize=100"
        if offset:
            params += f"&offset={offset}"
        _url = f"https://api.airtable.com/v0/{base_id}/PRUEBA%20FENIX?{params}"
        async with _httpx_r.AsyncClient(timeout=15) as _cl:
            _r = await _cl.get(_url, headers={"Authorization": f"Bearer {api_key}"})
            _data = _r.json()
        all_records.extend(_data.get("records", []))
        offset = _data.get("offset")
        if not offset:
            break

    # Filtrar por rango de fechas (convertir UTC → hora PY)
    registros_filtrados = []
    for rec in all_records:
        f = rec.get("fields", {})
        fecha_raw = _fecha_py(f.get("FECHA CREACION", ""))
        if not fecha_raw:
            continue
        if fecha_desde and fecha_raw < fecha_desde:
            continue
        if fecha_hasta and fecha_raw > fecha_hasta:
            continue
        registros_filtrados.append(rec)

    if not registros_filtrados:
        await proveedor.enviar_mensaje(telefono, f"📊 RESUMEN ANUNCIOS — {label}\n\nSin agendados en este período.")
        return

    # Agrupar por fecha + contar por monto
    por_fecha = defaultdict(lambda: {"90": 0, "120": 0, "150": 0, "sin": 0, "total_monto": 0, "cantidad": 0})
    for rec in registros_filtrados:
        f = rec.get("fields", {})
        fecha_raw = _fecha_py(f.get("FECHA CREACION", ""))
        concepto = f.get("CONCEPTO", "")
        monto = _MONTOS_CONCEPTO.get(concepto, 0)
        por_fecha[fecha_raw]["cantidad"] += 1
        por_fecha[fecha_raw]["total_monto"] += monto
        if monto == 90_000:
            por_fecha[fecha_raw]["90"] += 1
        elif monto == 120_000:
            por_fecha[fecha_raw]["120"] += 1
        elif monto == 150_000:
            por_fecha[fecha_raw]["150"] += 1
        else:
            por_fecha[fecha_raw]["sin"] += 1

    # Totales generales
    _GASTO_DIARIO = 200_000  # Gs por día en anuncios
    total_agendados = len(registros_filtrados)
    total_agendado = sum(d["total_monto"] for d in por_fecha.values())
    num_dias = len(por_fecha)
    total_gastado = num_dias * _GASTO_DIARIO
    diferencia = total_agendado - total_gastado
    total_agendado_fmt = f"{total_agendado:,}".replace(",", ".")
    total_gastado_fmt = f"{total_gastado:,}".replace(",", ".")
    diferencia_fmt = f"{diferencia:,}".replace(",", ".")
    signo = "+" if diferencia >= 0 else ""

    lineas = [
        f"📊 RESUMEN ANUNCIOS — {label}",
        f"Total: {total_agendados} agendados — {total_agendado_fmt} Gs\n",
    ]

    for fecha_iso in sorted(por_fecha.keys(), reverse=True):
        d = por_fecha[fecha_iso]
        # Formato: DOM 4/5
        try:
            _fd = _date_cls.fromisoformat(fecha_iso)
            dia_sem = _DIAS_SEMANA[_fd.weekday()]
            fecha_label = f"{dia_sem} {_fd.day}/{_fd.month}"
        except Exception:
            fecha_label = fecha_iso
        monto_dia = f"{d['total_monto']:,}".replace(",", ".")
        gasto_dia_fmt = f"{_GASTO_DIARIO:,}".replace(",", ".")
        lineas.append(f"📅 {fecha_label} — {d['cantidad']} agendados — {monto_dia} Gs (gasto: {gasto_dia_fmt})")
        # Desglose por monto
        desglose = []
        if d["90"]:
            desglose.append(f"90mil: {d['90']}")
        if d["120"]:
            desglose.append(f"120mil: {d['120']}")
        if d["150"]:
            desglose.append(f"150mil: {d['150']}")
        if d["sin"]:
            desglose.append(f"s/monto: {d['sin']}")
        if desglose:
            lineas.append(f"   {' | '.join(desglose)}")

    # Totales finales
    lineas.append("")
    lineas.append(f"💰 Total agendado: {total_agendado_fmt} Gs")
    lineas.append(f"📢 Total gastado ({num_dias} días x {f'{_GASTO_DIARIO:,}'.replace(',','.')}): {total_gastado_fmt} Gs")
    lineas.append(f"{'✅' if diferencia >= 0 else '🔴'} Diferencia: {signo}{diferencia_fmt} Gs")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))


# ── Afiche de precios ────────────────────────────────────────────────────────

_AFICHE_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "afiche_fenix.png")
_AFICHE_HORARIOS_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "afiche_horarios.png")
_afiche_horarios_enviado: set[str] = set()  # teléfonos a los que ya se envió afiche horarios

async def _enviar_afiche_horarios(telefono: str, topic_id: int | None, tg_group: int = 0):
    """Envía el afiche de horarios cuando el padre pregunta por frecuencia/días/horarios."""
    try:
        with open(_AFICHE_HORARIOS_PATH, "rb") as f:
            image_bytes = f.read()
        ok = await proveedor.enviar_imagen_bytes(telefono, image_bytes, "image/png")
        if ok:
            logger.info(f"[AFICHE HORARIOS] Imagen enviada a {telefono}")
        else:
            logger.error(f"[AFICHE HORARIOS] Error enviando imagen a {telefono}")

        # Espejar en Telegram
        _tid = topic_id
        if not _tid:
            try:
                _tid = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=tg_group)
            except Exception:
                pass
        if _tid:
            await enviar_a_topic(_tid, "👨‍🏫 IVAN: [📸 Afiche de horarios enviado]", telefono=telefono, group_override=tg_group)

    except FileNotFoundError:
        logger.error(f"[AFICHE HORARIOS] Archivo no encontrado: {_AFICHE_HORARIOS_PATH}")
    except Exception as e:
        logger.error(f"[AFICHE HORARIOS] Error: {e}")


def _padre_pregunta_horarios(texto: str) -> bool:
    """Detecta si el padre pregunta por horarios, frecuencia o días."""
    t = texto.lower().strip()
    patrones = [
        "cuantas veces", "cuántas veces", "que dias", "qué días", "que día",
        "horario", "horarios", "a la semana", "por semana", "frecuencia",
        "cuando es", "cuándo es", "cuando son", "cuándo son",
        "que dia", "qué dia", "dias de clase", "días de clase",
    ]
    return any(p in t for p in patrones)


def _padre_pregunta_precios(texto: str) -> bool:
    """Detecta si el padre pregunta por precios, costos o planes."""
    t = texto.lower().strip()
    patrones = [
        "precio", "precios", "costo", "costos", "cuanto sale", "cuánto sale",
        "cuanto cuesta", "cuánto cuesta", "cuanto es", "cuánto es",
        "que sale", "qué sale", "tarifa", "tarifas", "planes", "mensualidad",
        "cuanto hay que pagar", "cuánto hay que pagar", "valor",
    ]
    return any(p in t for p in patrones)


def _padre_pregunta_ubicacion(texto: str) -> bool:
    """Detecta si el padre pregunta por ubicación o dirección."""
    t = texto.lower().strip()
    patrones = [
        "ubicacion", "ubicación", "donde queda", "dónde queda",
        "donde es", "dónde es", "direccion", "dirección",
        "donde están", "donde estan", "dónde están",
        "como llego", "cómo llego", "lugar", "mapa",
    ]
    return any(p in t for p in patrones)


def _padre_pregunta_duracion(texto: str) -> bool:
    """Detecta si el padre pregunta cuánto dura la clase."""
    t = texto.lower().strip()
    patrones = [
        "cuanto dura", "cuánto dura", "cuanto tiempo", "cuánto tiempo",
        "duracion", "duración", "cuantas horas", "cuántas horas",
        "cuanto es la clase", "cuánto es la clase", "cuanto rato", "cuánto rato",
    ]
    return any(p in t for p in patrones)


def _padre_pregunta_que_llevar(texto: str) -> bool:
    """Detecta si el padre pregunta qué llevar o qué necesitan."""
    t = texto.lower().strip()
    patrones = [
        "que llevo", "qué llevo", "que llevar", "qué llevar",
        "que necesito", "qué necesito", "que tienen que traer", "qué tienen que traer",
        "que hay que llevar", "qué hay que llevar", "que traigo", "qué traigo",
        "que necesitan", "qué necesitan", "que debo llevar", "qué debo llevar",
    ]
    return any(p in t for p in patrones)


def _padre_pregunta_devolucion(texto: str) -> bool:
    """Detecta si el padre pregunta por devolución o garantía."""
    t = texto.lower().strip()
    patrones = [
        "devolucion", "devolución", "devuelven", "reembolso",
        "si no le gusta", "si no les gusta", "garantia", "garantía",
        "se descuenta", "se puede descontar",
    ]
    return any(p in t for p in patrones)


def _padre_pregunta_efectivo(texto: str) -> bool:
    """Detecta si el padre pregunta por medios de pago / efectivo."""
    t = texto.lower().strip()
    patrones = [
        "efectivo", "en efectivo", "pago en efectivo", "tarjeta",
        "medio de pago", "medios de pago", "como pago", "cómo pago",
        "forma de pago", "formas de pago", "puedo pagar",
    ]
    return any(p in t for p in patrones)


def _padre_dice_ya_transfiri(texto: str) -> bool:
    """Detecta si el padre dice que ya transfirió pero sin enviar comprobante."""
    t = texto.lower().strip()
    patrones = [
        "ya transferi", "ya transferí", "ya hice la transferencia",
        "ya pague", "ya pagué", "ya deposite", "ya deposité",
        "ya envie", "ya envié", "listo ya pague", "listo ya pagué",
    ]
    return any(p in t for p in patrones)


def _padre_pregunta_alias(texto: str) -> bool:
    """Detecta si el padre pregunta por el alias bancario."""
    t = texto.lower().strip()
    patrones = [
        "alias", "cual es el alias", "cuál es el alias",
        "el alias", "numero de alias", "número de alias",
    ]
    return any(p in t for p in patrones)


async def _armar_followup_afiche(telefono: str) -> str:
    """Arma el follow-up del afiche con nombre del hijo desde Airtable o historial."""
    nombre_hijo = ""
    try:
        from agent.airtable_client import _get_records, _LEADS
        records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if records:
            nombre_hijo = records[0].get("fields", {}).get("NOMBRE NIÑO", "") or ""
    except Exception:
        pass
    # Si Airtable no lo tiene, buscar en historial
    if not nombre_hijo:
        try:
            historial = await obtener_historial(telefono, limite=30)
            _nh = _extraer_nombre_hijo_historial(historial)
            if _nh and _nh != "no mencionó":
                nombre_hijo = _nh
        except Exception:
            pass
    if nombre_hijo and _es_nombre_hijo_valido(nombre_hijo):
        return (
            f"¿Te gustaría agendar un sábado inolvidable para vos y {nombre_hijo}?\n\n"
            "Te puedo reservar por acá, o si preferís te llamo un rato "
            "así te explico todo 😊"
        )
    else:
        # Sin nombre del hijo → CTA genérico sin preguntar nombre de nuevo
        return (
            "¿Te gustaría agendar un sábado inolvidable para vos y tu hijo?\n\n"
            "Te puedo reservar por acá, o si preferís te llamo "
            "un rato así te explico todo 😊"
        )


async def _enviar_afiche_y_followup(telefono: str, topic_id: int | None, tg_group: int = 0):
    """Envía el afiche de precios + precios escritos + promo trimestral + CTA."""
    try:
        with open(_AFICHE_PATH, "rb") as f:
            image_bytes = f.read()

        ok = await proveedor.enviar_imagen_bytes(telefono, image_bytes, "image/png")
        if ok:
            logger.info(f"[AFICHE] Imagen enviada a {telefono}")
        else:
            logger.error(f"[AFICHE] Error enviando imagen a {telefono}")

        # Delay antes del mensaje de precios
        await asyncio.sleep(3)

        # Mensaje con precios escritos + promo trimestral
        msg_precios = (
            "📋 *Precios:*\n\n"
            "🌳 *Sábado en el Parque:*\n"
            "👨‍👦 Papá + 1 hijo: 90.000 Gs\n"
            "👨‍👦‍👦 Papá + 2 hijos: 120.000 Gs\n"
            "Papá + 3 hijos: 150.000 Gs\n\n"
            "📅 *PLAN MENSUAL* (4 sábados, papá + hijo): 350.000/mes + matrícula 200.000 (incluye camisilla)\n\n"
            "🔥 *PROMO TRIMESTRAL — 40% OFF* 🔥\n"
            "690.000 + matrícula 140.000 = 830.000 Gs total\n"
            "➡️ Ahorrás 420.000 Gs 🔥\n\n"
            "¿Te gustaría agendar un sábado inolvidable para vos y tu hijo? 😊"
        )
        await proveedor.enviar_mensaje(telefono, msg_precios)
        await guardar_mensaje(telefono, "assistant", msg_precios)

        # Follow-up CTA eliminado — la pregunta ya está al final del msg de precios

        # Espejar TODO en Telegram (con fallback si topic_id es None)
        _tid_afiche = topic_id
        if not _tid_afiche:
            try:
                _tid_afiche = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=tg_group)
            except Exception:
                pass
        if _tid_afiche:
            await enviar_a_topic(_tid_afiche, f"👨‍🏫 IVAN: [📸 Afiche de precios enviado]", telefono=telefono, group_override=tg_group)
            await enviar_a_topic(_tid_afiche, f"👨‍🏫 IVAN: {msg_precios}", telefono=telefono, group_override=tg_group)
            await enviar_a_topic(_tid_afiche, f"👨‍🏫 IVAN: {followup}", telefono=telefono, group_override=tg_group)

        logger.info(f"[AFICHE] Follow-up enviado a {telefono}")

    except FileNotFoundError:
        logger.error(f"[AFICHE] Archivo no encontrado: {_AFICHE_PATH}")
    except Exception as e:
        logger.error(f"[AFICHE] Error: {e}")


# ── Flujo de pagos ───────────────────────────────────────────────────────────

async def _procesar_comprobante(
    telefono: str,
    texto: str,
    media_id: str | None,
    historial: list[dict],
    topic_id: int | None,
    group_override: int = 0,
):
    """
    Procesa un posible comprobante de pago:
    1. Responde al lead "gracias, verificando"
    2. Detecta tipo de pago (prueba vs inscripción)
    3. Reenvía imagen al admin + botones confirmar/rechazar
    4. Notifica en Telegram
    """
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    nombre_padre = _extraer_nombre_del_historial(historial, texto) or "Lead"
    nombre_hijo = _extraer_nombre_hijo_historial(historial)
    tipo = detectar_tipo_pago(historial)

    # Calcular monto correcto (multi-hijo)
    if tipo == "prueba":
        monto = monto_prueba_por_hijos(historial)
    else:
        monto = 0

    monto_fmt = formatear_monto(monto) if monto else ""
    tipo_label = f"PRUEBA {monto_fmt}" if tipo == "prueba" and monto else "PRUEBA" if tipo == "prueba" else "INSCRIPCIÓN"

    # ── Auto-confirmar pago (sin esperar botones del admin) ──────────────
    # (user message ya guardado al inicio del flujo)

    # Confirmar pago directo
    await registrar_pago_pendiente(
        telefono=telefono,
        tipo=tipo,
        plan=tipo,
        monto=monto,
        media_id=media_id,
    )
    await confirmar_pago(telefono)

    # Mensaje al lead: pago confirmado directo
    msg_lead = "Pago confirmado! 🎉"
    await guardar_mensaje(telefono, "assistant", msg_lead)
    await proveedor.enviar_mensaje(telefono, msg_lead)

    # Actualizar conversión en Airtable + registrar en qué FU pagó
    try:
        await actualizar_conversion_lead(telefono, "PAGO")
        # Si tenía seguimientos, registrar en cuál pagó
        from agent.airtable_client import _get_records, _LEADS, _patch
        _lr_pago = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if _lr_pago:
            _seg_pago = _lr_pago[0].get("fields", {}).get("SEGUIMIENTOS", 0) or 0
            if _seg_pago >= 1:
                await _patch(_LEADS, _lr_pago[0]["id"], {"PAGO POST FU": _seg_pago})
                logger.info(f"[FOLLOWUP] {telefono} pagó después de FU{_seg_pago}")
    except Exception as e:
        logger.error(f"[PAGOS] Error actualizando conversión: {e}")

    # CONVERSION=PAGO ya se marcó arriba — follow-up loop lo excluye automáticamente

    # CAPI: evento Purchase (comprobante confirmado)
    await enviar_evento_pago(telefono)

    # Notificar al admin (solo informativo, sin botones)
    # Link al topic de Telegram de este lead
    tg_link_admin = ""
    if topic_id and group_override:
        gid = str(group_override).replace("-100", "", 1)
        tg_link_admin = f"\n💬 https://t.me/c/{gid}/{topic_id}"
    msg_admin = (
        f"💰 PAGO RECIBIDO ✅\n\n"
        f"👤 Padre: {nombre_padre}\n"
        f"👦 Hijo/a: {nombre_hijo}\n"
        f"📱 {telefono}\n"
        f"💰 Tipo: {tipo_label}"
        f"{tg_link_admin}\n\n"
        f"Auto-confirmado. Ivan sigue con el agendamiento."
    )
    # Reenviar imagen al admin (si hay media_id)
    if media_id:
        try:
            await proveedor.enviar_imagen(
                admin_phone,
                media_id,
                caption=f"Comprobante de {nombre_padre} ({telefono})",
            )
        except Exception as e:
            logger.error(f"[PAGOS] Error reenviando imagen al admin: {e}")
    try:
        await proveedor.enviar_mensaje(admin_phone, msg_admin)
    except Exception as e:
        logger.error(f"[PAGOS] Error notificando admin: {e}")

    # Notificar en Telegram
    try:
        await notificar_pago_telegram(
            telefono=telefono,
            nombre=nombre_padre,
            estado="confirmado",
            tipo=tipo_label,
            monto=monto,
        )
    except Exception as e:
        logger.error(f"[PAGOS] Error notificando Telegram: {e}")

    # Espejar en Telegram del lead
    if topic_id:
        await enviar_a_topic(topic_id, f"✅ PAGO CONFIRMADO — {tipo_label}", telefono=telefono, group_override=group_override)

    logger.info(f"[PAGOS] Pago AUTO-CONFIRMADO para {telefono} tipo={tipo}")

    # ── Ivan confirma reserva (solo si ya eligió horario antes) ─────────
    try:
        await asyncio.sleep(3)  # pausa natural
        historial_post = await obtener_historial(telefono, limite=40)
        agent_pago, _ = await obtener_agent_actual(telefono)
        respuesta_ivan = await generar_respuesta(
            mensaje=(
                "[SISTEMA: pago confirmado. Si el padre YA eligió sábado+horario antes de pagar, "
                "decí 'Reserva confirmada ✅ [NOMBRE] tiene su lugar el sábado [FECHA] a las [HORA]h' "
                "y agradecé la transferencia. NADA MÁS, no pidas datos, no mandes formulario. "
                "Si NO eligió horario todavía, ofrecé los sábados disponibles.]"
            ),
            historial=historial_post,
            agent_actual=agent_pago or "ivan",
        )
        await guardar_mensaje(telefono, "assistant", respuesta_ivan)
        await _delay_humano(respuesta_ivan)
        await proveedor.enviar_mensaje(telefono, respuesta_ivan)
        if topic_id:
            await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {respuesta_ivan}", telefono=telefono, group_override=group_override)

        # ── Formulario SEPARADO (solo si confirmó reserva) ─────────
        if "reserva confirmada" in respuesta_ivan.lower() or "tiene su lugar" in respuesta_ivan.lower():
            await asyncio.sleep(5)  # pausa entre mensajes
            msg_formulario = (
                "Ahora sí, para completar la reserva pasame estos datos 📋\n\n"
                "• Nombre completo tuyo (papá/mamá que acompaña)\n"
                "• Nombre completo del nene/a\n"
                "• Fecha de nacimiento del nene/a"
            )
            await guardar_mensaje(telefono, "assistant", msg_formulario)
            await proveedor.enviar_mensaje(telefono, msg_formulario)
            if topic_id:
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {msg_formulario}", telefono=telefono, group_override=group_override)
    except Exception as e:
        logger.error(f"[PAGOS] Error generando follow-up post-pago: {e}")


async def _procesar_boton_pago(btn_titulo: str):
    """
    Procesa la respuesta del admin (confirmar/rechazar) a un comprobante.
    Busca el pago pendiente más reciente y actúa según el botón.
    """
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")

    tel_lead, datos = await obtener_pago_pendiente()
    if not tel_lead or not datos:
        await proveedor.enviar_mensaje(admin_phone, "No hay pagos pendientes de confirmar.")
        return

    tipo = datos.get("tipo", "prueba")
    tipo_label = "PRUEBA 90K" if tipo == "prueba" else "INSCRIPCIÓN"

    if "confirmar" in btn_titulo:
        # ── Confirmar pago ────────────────────────────────────────────────
        await confirmar_pago(tel_lead)

        # Mensaje al admin
        await proveedor.enviar_mensaje(admin_phone, f"✅ Pago de {tel_lead} confirmado.")

        # Mensaje al lead
        msg_lead = "Pago confirmado! 🎉"
        await proveedor.enviar_mensaje(tel_lead, msg_lead)
        await guardar_mensaje(tel_lead, "assistant", msg_lead)

        # Actualizar conversión en Airtable
        try:
            await actualizar_conversion_lead(tel_lead, "PAGO")
        except Exception as e:
            logger.error(f"[PAGOS] Error actualizando conversión: {e}")

        # CAPI: evento Purchase (botón admin confirmó)
        await enviar_evento_pago(tel_lead)

        # Notificar en Telegram
        _ag_pago, _ = await obtener_agent_actual(tel_lead)
        _grp_pago = group_id_para_agente(_ag_pago or "ivan")
        topic_id = await obtener_o_crear_topic(tel_lead, f"📱 {tel_lead}", group_override=_grp_pago)
        if topic_id:
            await enviar_a_topic(topic_id, f"✅ PAGO CONFIRMADO — {tipo_label}", telefono=tel_lead, group_override=_grp_pago)

        try:
            historial = await obtener_historial(tel_lead)
            nombre = _extraer_nombre_del_historial(historial) or "Lead"
            await notificar_pago_telegram(
                telefono=tel_lead,
                nombre=nombre,
                estado="confirmado",
                tipo=tipo_label,
                monto=datos.get("monto", 0),
            )
        except Exception as e:
            logger.error(f"[PAGOS] Error notificando Telegram confirmación: {e}")

        logger.info(f"[PAGOS] Pago CONFIRMADO para {tel_lead}")

        # ── Ivan sigue automáticamente: pregunta sábado y horario ─────────
        try:
            await asyncio.sleep(3)  # pausa natural
            historial_post = await obtener_historial(tel_lead, limite=40)
            respuesta_ivan = await generar_respuesta(
                mensaje="[SISTEMA: pago confirmado, continuar con agendamiento]",
                historial=historial_post,
                agent_actual="ivan",
            )
            await guardar_mensaje(tel_lead, "assistant", respuesta_ivan)
            await _delay_humano(respuesta_ivan)
            await proveedor.enviar_mensaje(tel_lead, respuesta_ivan)
            if topic_id:
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {respuesta_ivan}", telefono=tel_lead, group_override=_grp_pago)
        except Exception as e:
            logger.error(f"[PAGOS] Error generando follow-up post-pago: {e}")

    elif "rechazar" in btn_titulo:
        # ── Rechazar pago ─────────────────────────────────────────────────
        await rechazar_pago(tel_lead)

        # Mensaje al admin
        await proveedor.enviar_mensaje(admin_phone, f"❌ Pago de {tel_lead} rechazado.")

        # Mensaje al lead
        msg_lead = "Hubo un problema con la transferencia. ¿Podrías verificar y reenviar el comprobante? 😊"
        await proveedor.enviar_mensaje(tel_lead, msg_lead)
        await guardar_mensaje(tel_lead, "assistant", msg_lead)

        # Notificar en Telegram (reusar _grp_pago si existe, sino resolver)
        if not topic_id:
            _ag_r, _ = await obtener_agent_actual(tel_lead)
            _grp_r = group_id_para_agente(_ag_r or "ivan")
            topic_id = await obtener_o_crear_topic(tel_lead, f"📱 {tel_lead}", group_override=_grp_r)
        if topic_id:
            await enviar_a_topic(topic_id, f"❌ PAGO RECHAZADO — {tipo_label}", telefono=tel_lead)

        try:
            historial = await obtener_historial(tel_lead)
            nombre = _extraer_nombre_del_historial(historial) or "Lead"
            await notificar_pago_telegram(
                telefono=tel_lead,
                nombre=nombre,
                estado="rechazado",
                tipo=tipo_label,
            )
        except Exception as e:
            logger.error(f"[PAGOS] Error notificando Telegram rechazo: {e}")

        logger.info(f"[PAGOS] Pago RECHAZADO para {tel_lead}")


# ── /agenda — Ivan cierra agenda tras llamada telefónica ──────────────────────

_MONTOS_AGENDA = {"90mil": 90_000, "120mil": 120_000, "150mil": 150_000, "gratis": 0}


async def _cerrar_agenda_desde_telegram(telefono: str, comando: str, thread_id: int, group_override: int = 0):
    """
    /agenda 90mil Carolina   → 1 hijo, 90k
    /agenda 120mil Carolina  → 2 hijos, 120k
    /agenda 150mil Carolina  → 3 hijos, 150k
    /agenda gratis Carolina  → prueba gratis (referidos/promo)

    Ivan usa esto cuando cierra la agenda por llamada telefónica.
    Crea PRUEBA FENIX, reactiva el agente, y le manda al padre
    el formulario + datos bancarios para el comprobante (o solo formulario si gratis).
    """
    partes = comando.strip().split(maxsplit=2)
    if len(partes) < 3 or partes[1].lower() not in _MONTOS_AGENDA:
        await enviar_a_topic(
            thread_id,
            "⚠️ Uso: /agenda 90mil|120mil|150mil|gratis nombre\nEj: /agenda 90mil Carolina",
            telefono=telefono,
            group_override=group_override,
        )
        return

    monto = _MONTOS_AGENDA[partes[1].lower()]
    es_gratis = partes[1].lower() == "gratis"
    nombre_padre = partes[2].strip()

    try:
        historial_completo = await obtener_historial(telefono, limite=40)

        # Extraer datos con Haiku
        datos_form = await extraer_datos_formulario(historial_completo)
        padre_data = datos_form.get("padre") or {}
        nombre_resp = padre_data.get("nombre", "") or nombre_padre
        apellido_resp = padre_data.get("apellido", "") or ""
        ninos_form = datos_form.get("ninos", [])

        # Obtener lead_id y diagnóstico
        from agent.airtable_client import _get_records, _LEADS
        lead_records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        lead_record_id = lead_records[0]["id"] if lead_records else None
        diagnostico_ids = lead_records[0].get("fields", {}).get("DIAGNOSTICO", []) if lead_records else []

        # Actualizar conversión
        await actualizar_conversion_lead(telefono, "GRATIS" if es_gratis else "PAGO")

        # Crear PRUEBA FENIX por cada niño (monto solo en primero)
        creados = 0
        _conversion_prueba = "GRATIS" if es_gratis else "PAGO"
        if ninos_form:
            for i, n in enumerate(ninos_form):
                await crear_prueba_fenix(
                    telefono=telefono,
                    nombre_responsable=nombre_resp,
                    apellido_responsable=apellido_resp,
                    nombre_hijo=n.get("nombre", ""),
                    apellido_hijo=n.get("apellido", ""),
                    edad_hijo="",
                    fecha_reserva="(por definir)",
                    hora="(por definir)",
                    fecha_nacimiento=n.get("fecha_nacimiento", ""),
                    monto=monto if i == 0 else 0,
                    conversion=_conversion_prueba,
                    diagnostico_ids=diagnostico_ids,
                    lead_record_id=lead_record_id,
                )
                creados += 1
        else:
            # Fallback sin datos de hijos
            nh = _extraer_nombre_hijo_historial(historial_completo)
            await crear_prueba_fenix(
                telefono=telefono,
                nombre_responsable=nombre_resp,
                apellido_responsable=apellido_resp,
                nombre_hijo=nh if nh != "no mencionó" else "",
                apellido_hijo="",
                edad_hijo="",
                fecha_reserva="(por definir)",
                hora="(por definir)",
                monto=monto,
                conversion=_conversion_prueba,
                diagnostico_ids=diagnostico_ids,
                lead_record_id=lead_record_id,
            )
            creados = 1

        # ── Determinar cantidad de hijos para el mensaje ──────────────────
        cant_hijos = len(ninos_form) if ninos_form else 1
        if cant_hijos == 1:
            texto_form = "Te envío el formulario para tu hijo/a"
        else:
            texto_form = f"Te envío los formularios para tus {cant_hijos} hijos"

        # ── Mensaje al padre ───────────────────────────────────────────────
        if es_gratis:
            msg_whatsapp = (
                f"{texto_form} 📋\n\n"
                f"Tu sábado en el parque es GRATIS 🎉 (cortesía referidos FENIX Kids)\n\n"
                f"Te confirmo el horario en breve, muchas gracias {nombre_padre} 🤝"
            )
        else:
            from agent.pagos import DATOS_BANCARIOS
            monto_fmt = f"{monto:,}".replace(",", ".")
            msg_whatsapp = (
                f"{texto_form} 📋\n\n"
                f"El monto del sábado en el parque es {monto_fmt} Gs\n\n"
                f"{DATOS_BANCARIOS}\n\n"
                f"Pasame nomas acá el comprobante de transferencia, muchas gracias {nombre_padre} 🤝"
            )

        # Enviar al padre por WhatsApp
        await proveedor.enviar_mensaje(telefono, msg_whatsapp)
        await guardar_mensaje(telefono, "assistant", msg_whatsapp)

        # Reactivar el agente para que procese el comprobante
        await reactivar_dorita(telefono)

        # Notificar en Telegram
        monto_label = "GRATIS (referidos)" if es_gratis else f"{monto:,} Gs".replace(",", ".")
        await enviar_a_topic(
            thread_id,
            f"✅ Agenda cerrada — {creados} PRUEBA FENIX — {monto_label}\n"
            f"📲 Mensaje enviado a {nombre_padre}{' con formulario + datos bancarios' if not es_gratis else ' (prueba gratis)'}\n"
            f"🔊 Agente reactivado (esperando comprobante)",
            telefono=telefono,
            group_override=group_override,
        )
        logger.info(f"[AGENDA] {telefono}: {creados} registros, {monto_label}, msg enviado a {nombre_padre}")

    except Exception as e:
        logger.error(f"[CERRAR_AGENDA] Error: {e}")
        await enviar_a_topic(thread_id, f"❌ Error cerrando agenda: {e}", telefono=telefono, group_override=group_override)


# ── Telegram webhook (admin → WhatsApp) ──────────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Recibe mensajes del bot de Telegram y los reenvía al WhatsApp del lead.
    Permite a Ivan responder manualmente desde Telegram.
    """
    try:
        body = await request.json()
        message = body.get("message") or body.get("edited_message")
        if not message:
            return {"status": "ok"}

        chat_id = message.get("chat", {}).get("id")
        thread_id = message.get("message_thread_id")
        from_user = message.get("from", {})
        texto_tg = message.get("text", "")

        if not texto_tg or not thread_id:
            return {"status": "ok"}

        # Ignorar mensajes de bots
        if from_user.get("is_bot"):
            return {"status": "ok"}

        telefono = await obtener_telefono_por_topic(thread_id)
        if not telefono:
            return {"status": "ok"}

        # El chat_id del mensaje nos dice desde qué grupo escribe Ivan
        _tg_grp = chat_id

        # Comandos de control
        if texto_tg.strip() == "/silenciar":
            await silenciar_dorita(telefono)
            await enviar_a_topic(thread_id, "🔇 Agente IA silenciado. Ivan activo.", telefono=telefono, group_override=_tg_grp)
            return {"status": "ok"}

        if texto_tg.strip() == "/reactivar":
            await reactivar_dorita(telefono)
            await enviar_a_topic(thread_id, "🔊 Agente Fénix activado.", telefono=telefono, group_override=_tg_grp)
            return {"status": "ok"}

        if texto_tg.strip() == "/aprobado":
            # Evaluación aprobada → enviar mensaje al padre y reactivar agente
            await reactivar_dorita(telefono)
            historial = await obtener_historial(telefono, limite=20)
            agent_actual, _ = await obtener_agent_actual(telefono)
            respuesta = await generar_respuesta(
                mensaje="[SISTEMA: EVALUACION_APROBADA]",
                historial=historial,
                agent_actual=agent_actual,
            )
            await proveedor.enviar_mensaje(telefono, respuesta)
            await guardar_mensaje(telefono, "assistant", respuesta)
            await enviar_a_topic(thread_id, f"✅ APROBADO → IVAN: {respuesta}", telefono=telefono, group_override=_tg_grp)
            return {"status": "ok"}

        if texto_tg.strip() == "/rechazado":
            # Evaluación rechazada → enviar mensaje al padre, no seguir vendiendo
            await reactivar_dorita(telefono)
            historial = await obtener_historial(telefono, limite=20)
            agent_actual, _ = await obtener_agent_actual(telefono)
            respuesta = await generar_respuesta(
                mensaje="[SISTEMA: EVALUACION_RECHAZADA]",
                historial=historial,
                agent_actual=agent_actual,
            )
            await proveedor.enviar_mensaje(telefono, respuesta)
            await guardar_mensaje(telefono, "assistant", respuesta)
            await enviar_a_topic(thread_id, f"❌ RECHAZADO → IVAN: {respuesta}", telefono=telefono, group_override=_tg_grp)
            return {"status": "ok"}

        if texto_tg.strip() == "/fenix":
            # Reset conversación + reactivar (Airtable intacto)
            cancelar_seguimiento(telefono)
            cancelar_recordatorios(telefono)
            _cancelar_diagnostico_pendiente(telefono)
            await limpiar_estado_completo(telefono)
            _registro_ya_iniciado.discard(telefono)
            await reactivar_dorita(telefono)
            await enviar_a_topic(thread_id, "🔄 Conversación reseteada + agente activado.\nUsá /registro para iniciar registro.", telefono=telefono, group_override=_tg_grp)
            return {"status": "ok"}

        # /registro — verificar datos o registrar familia desde Telegram
        if texto_tg.strip() == "/registro":
            logger.info(f"[/registro] telefono={telefono} thread_id={thread_id} chat_id={chat_id}")
            familia = await buscar_familia_por_telefono(telefono)
            logger.info(f"[/registro] familia={'ENCONTRADA: '+familia.get('fields',{}).get('FAMILIA','') if familia else 'NO ENCONTRADA'}")
            # Preparar Aurora para manejar las respuestas
            _registro_ya_iniciado.discard(telefono)
            await asignar_variante(telefono)
            await actualizar_agent_actual(telefono, "aurora", "cliente_inscripto")
            await reactivar_dorita(telefono)

            if familia:
                campos = familia.get("fields", {})
                await guardar_familia_id(telefono, familia["id"])

                # Nombre para saludar (apodo o primer nombre)
                _es_padre = campos.get("CELL PADRE") == telefono or campos.get("CELL LIMPIO PADRE") == telefono
                _es_madre = campos.get("CELL MADRE") == telefono or campos.get("CELL LIMPIO MADRE") == telefono
                if _es_padre:
                    _nombre_wa = campos.get("APODO PADRE", "").strip() or (campos.get("NOMBRE PADRE", "").strip().split()[0] if campos.get("NOMBRE PADRE") else "")
                elif _es_madre:
                    _nombre_wa = campos.get("APODO MADRE", "").strip() or (campos.get("NOMBRE MADRE", "").strip().split()[0] if campos.get("NOMBRE MADRE") else "")
                else:
                    _nombre_wa = campos.get("NOMBRE PADRE", "").strip().split()[0] if campos.get("NOMBRE PADRE") else ""

                # Armar resumen de datos para WhatsApp
                hijos = await obtener_ninos_de_familia(familia["id"])
                datos_hijos = ""
                for h in hijos:
                    datos_hijos += f"\n👧 {h['nombre']} {h['apellido']}"
                    if h.get('fecha_nacimiento'):
                        datos_hijos += f", nac: {h['fecha_nacimiento']}"
                    if h.get('ci'):
                        datos_hijos += f", CI: {h['ci']}"
                    if h.get('talla_remera'):
                        datos_hijos += f", talla: {h['talla_remera']}"

                if _nombre_wa and datos_hijos:
                    # Registrado con hijos → saludo normal + menú
                    msg_wa = (
                        f"Hola {_nombre_wa}! 🤗 Soy Aurora 🌟 de Fenix Kids.\n"
                        f"¿En qué te puedo ayudar?\n"
                        f"1️⃣ Agendar clase\n"
                        f"2️⃣ Ver lista de niños agendados por clase\n"
                        f"3️⃣ Ver Fotos Fenix (próximamente)\n"
                        f"4️⃣ Ver Videos Fenix (próximamente)\n"
                        f"5️⃣ Redes Sociales"
                    )
                elif _nombre_wa:
                    # Registrado sin hijos → pedir formulario
                    msg_wa = (
                        f"Hola {_nombre_wa}! 🤗 Soy Aurora 🌟 de Fenix Kids.\n"
                        f"No tengo registrados los datos de tu familia todavía 😊\n"
                        f"¿Cuántos hijos tenés en Fenix?"
                    )
                else:
                    # Sin nombre → pedir nombre
                    msg_wa = (
                        "Hola! 🤗 Soy Aurora 🌟 de Fenix Kids.\n"
                        "No tengo registrado tu número todavía 😊\n"
                        "¿Con quién tengo el gusto? (nombre y apellido)"
                    )

                await proveedor.enviar_mensaje(telefono, msg_wa)
                await guardar_mensaje(telefono, "assistant", msg_wa)

                # Mostrar en Telegram el mensaje exacto que se envió
                await enviar_a_topic(thread_id, f"🌟 AURORA: {msg_wa}", telefono=telefono, group_override=_tg_grp)
            else:
                # No registrado → crear FAMILIA mínima + mandar formulario
                fam_id_nuevo = await crear_familia({"padre": {"telefono": telefono}, "madre": {"telefono": telefono}})
                if fam_id_nuevo:
                    await guardar_familia_id(telefono, fam_id_nuevo)
                msg_registro = (
                    "Hola! 🤗 Soy Aurora 🌟, asistente IA de Fenix Kids.\n"
                    "Bienvenido/a a la familia Fenix! 🌳 Necesito registrar tus datos.\n"
                    "¿Con quién tengo el gusto? (nombre y apellido)"
                )
                await proveedor.enviar_mensaje(telefono, msg_registro)
                await guardar_mensaje(telefono, "assistant", msg_registro)
                await enviar_a_topic(thread_id, f"🌟 AURORA: {msg_registro}", telefono=telefono, group_override=_tg_grp)
            return {"status": "ok"}

        # /agenda [monto] [nombre] — Ivan cierra agenda tras llamada telefónica
        if texto_tg.strip().startswith("/agenda"):
            await _cerrar_agenda_desde_telegram(telefono, texto_tg, thread_id, group_override=_tg_grp)
            return {"status": "ok"}

        # Reenviar mensaje de Ivan al WhatsApp del lead
        await silenciar_dorita(telefono)  # silenciar mientras Ivan escribe
        ok = await proveedor.enviar_mensaje(telefono, texto_tg)
        if ok:
            await guardar_mensaje(telefono, "assistant", texto_tg)
            logger.info(f"Ivan → {telefono}: {texto_tg[:60]}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error telegram webhook: {e}")
        return {"status": "error"}


@app.get("/telegram/setup")
async def telegram_setup(url: str, _: bool = Depends(_require_admin)):
    """Registra el webhook de Telegram. Llamar una sola vez al deploy."""
    ok = await configurar_webhook(url)
    info = await obtener_info_webhook()
    return {"configurado": ok, "info": info}


# ── Follow-up masivo fotos — ONE-SHOT 6:00 AM PY 2026-05-06 ──────────────────

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

            # Espejar en Telegram
            try:
                _topic_fu_fotos = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=group_id_para_agente("ivan"))
                if _topic_fu_fotos:
                    await enviar_a_topic(_topic_fu_fotos, f"📢 1ER FOLLOWUP: [📸 2 fotos + texto enviado]", telefono=telefono, group_override=group_id_para_agente("ivan"))
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


# ── Follow-up video — ONE-SHOT 6:00 AM PY 2026-05-06 ──────────────────────

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
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
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
                _topic_vid = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=group_id_para_agente("ivan"))
                if _topic_vid:
                    await enviar_a_topic(_topic_vid, f"📢 {_fu_num} FOLLOWUP: [🎬 Video + texto enviado]", telefono=telefono, group_override=group_id_para_agente("ivan"))
            except Exception:
                pass

            enviados += 1
            logger.info(f"[FOLLOWUP-VIDEO] Enviado a {telefono} ({enviados}/{len(telefonos_ventana)})")
            await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"[FOLLOWUP-VIDEO] Error con {telefono}: {e}")

    logger.info(f"[FOLLOWUP-VIDEO] Completado: {enviados}/{len(telefonos_ventana)} enviados")


# ════════════════════════════════════════════════════════════════════════════════
# MODO FOTOS — Reconocimiento facial de niños en fotos de clase
# ════════════════════════════════════════════════════════════════════════════════


async def _iniciar_modo_fotos(telefono: str, texto: str):
    """
    Inicia una sesión de fotos para reconocimiento facial.
    Detecta: "fotos 9:30", "fotos 11", "fotos 15:30", "fotos clase"
    """
    # Extraer turno del texto
    turno = ""
    m = re.search(r'(\d{1,2}[:.]\d{2}|\d{1,2})', texto)
    if m:
        turno = m.group(1).replace(".", ":")
        if turno in ("9", "930"):
            turno = "9:30"
        elif turno in ("11", "1100"):
            turno = "11:00"
        elif turno in ("15", "1530"):
            turno = "15:30"

    _fotos_sesion[telefono] = {
        "turno": turno,
        "media_ids": [],
        "resultados": {},  # {nino_id: {"nombre": str, "fotos": int}}
        "no_identificadas": 0,
        "total_fotos": 0,
    }

    msg_inicio = f"📸 Modo fotos activado"
    if turno:
        msg_inicio += f" para la clase de {turno}"
    msg_inicio += ".\n\nMandá las fotos y cuando termines escribí *listo*."

    await proveedor.enviar_mensaje(telefono, msg_inicio)
    logger.info(f"[FOTOS] Sesión iniciada para {telefono}, turno={turno or 'sin especificar'}")


async def _acumular_foto(telefono: str, media_id: str):
    """
    Recibe una foto durante el modo fotos, la descarga y busca caras.
    """
    sesion = _fotos_sesion.get(telefono)
    if not sesion:
        return

    sesion["media_ids"].append(media_id)
    sesion["total_fotos"] += 1
    foto_num = sesion["total_fotos"]

    # Descargar imagen
    image_bytes = await proveedor.descargar_media(media_id)
    if not image_bytes:
        logger.warning(f"[FOTOS] No se pudo descargar media {media_id}")
        return

    # Buscar caras con Rekognition
    try:
        from agent.face_recognition import identificar_ninos
        matches = await identificar_ninos(image_bytes)

        if matches:
            for match in matches:
                nino_id = match["nino_id"]
                if nino_id not in sesion["resultados"]:
                    # Obtener nombre del niño
                    from agent.airtable_client import obtener_nombre_nino
                    nino_info = await obtener_nombre_nino(nino_id)
                    nombre = ""
                    if nino_info:
                        nombre = nino_info.get("apodo") or nino_info.get("nombre", "")
                        apellido = nino_info.get("apellido", "")
                        if apellido:
                            nombre = f"{nombre} {apellido}"
                    sesion["resultados"][nino_id] = {"nombre": nombre or nino_id, "fotos": 0}
                sesion["resultados"][nino_id]["fotos"] += 1
        else:
            sesion["no_identificadas"] += 1

        # Feedback breve cada 5 fotos
        if foto_num % 5 == 0:
            n_ninos = len(sesion["resultados"])
            await proveedor.enviar_mensaje(telefono, f"📸 {foto_num} fotos recibidas, {n_ninos} niño(s) identificados...")

    except Exception as e:
        logger.error(f"[FOTOS] Error procesando foto {foto_num}: {e}")
        sesion["no_identificadas"] += 1


async def _finalizar_fotos(telefono: str):
    """
    Cierra la sesión de fotos y muestra el resumen de niños identificados.
    """
    sesion = _fotos_sesion.pop(telefono, None)
    if not sesion:
        return

    total = sesion["total_fotos"]
    resultados = sesion["resultados"]
    no_id = sesion["no_identificadas"]

    if total == 0:
        await proveedor.enviar_mensaje(telefono, "No recibí fotos. Modo fotos desactivado.")
        return

    # Armar resumen
    lineas = [f"📸 *Resumen: {total} fotos procesadas*\n"]

    if resultados:
        # Ordenar por cantidad de fotos (más apariciones primero)
        ordenados = sorted(resultados.items(), key=lambda x: x[1]["fotos"], reverse=True)
        lineas.append(f"✅ *{len(resultados)} niño(s) identificados:*")
        for i, (nino_id, data) in enumerate(ordenados, 1):
            lineas.append(f"  {i}. {data['nombre']} ({data['fotos']} foto{'s' if data['fotos'] > 1 else ''})")

    if no_id > 0:
        lineas.append(f"\n⚠️ {no_id} foto(s) sin cara identificada")

    lineas.append("\n¿Confirmo y vinculo en Airtable? (si/no)")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))

    # Guardar sesión temporalmente para la confirmación
    _fotos_sesion[telefono] = {
        **sesion,
        "_esperando_confirmacion": True,
    }

    logger.info(f"[FOTOS] Sesión finalizada: {total} fotos, {len(resultados)} niños, {no_id} sin ID")


async def _confirmar_fotos(telefono: str):
    """
    Confirma la sesión de fotos y crea registros en CONTENIDO FENIX.
    """
    sesion = _fotos_sesion.pop(telefono, None)
    if not sesion:
        return

    resultados = sesion.get("resultados", {})
    turno = sesion.get("turno", "")

    if not resultados:
        await proveedor.enviar_mensaje(telefono, "No hay niños para vincular.")
        return

    # Crear registro en CONTENIDO FENIX con los niños vinculados
    from agent.airtable_client import _post, _CONTENIDO
    from datetime import datetime

    nino_ids = list(resultados.keys())
    titulo = f"Fotos clase {turno}" if turno else "Fotos de clase"
    titulo += f" — {datetime.now().strftime('%d/%m/%Y')}"

    campos = {
        "TITULO": titulo,
        "NIÑOS FENIX": nino_ids,
        "NOTIFICADO": False,
    }

    registro = await _post(_CONTENIDO, campos)
    if registro:
        nombres = [data["nombre"] for data in resultados.values()]
        await proveedor.enviar_mensaje(
            telefono,
            f"✅ Listo! Registro creado en CONTENIDO FENIX con {len(nino_ids)} niño(s): {', '.join(nombres)}\n\n"
            f"Cuando publiques el posteo, agregá el LINK al registro de Airtable y los padres recibirán WhatsApp automático."
        )
        logger.info(f"[FOTOS] CONTENIDO FENIX creado: {titulo}, {len(nino_ids)} niños")
    else:
        await proveedor.enviar_mensaje(telefono, "❌ Error creando registro en Airtable. Revisá los logs.")


async def _procesar_registro_cara(telefono: str, media_id: str):
    """
    Registra la cara de un niño en Rekognition.
    Busca al niño por nombre/apodo en NIÑOS FENIX de Airtable.
    """
    nombre_buscar = _cara_pendiente.pop(telefono, "")
    if not nombre_buscar:
        return

    # Descargar imagen
    image_bytes = await proveedor.descargar_media(media_id)
    if not image_bytes:
        await proveedor.enviar_mensaje(telefono, "❌ No pude descargar la foto")
        return

    # Buscar niño en Airtable por nombre/apodo
    from agent.airtable_client import _get_records, _NINOS, _patch
    nombre_norm = nombre_buscar.lower().strip()

    # Buscar por apodo o nombre
    records = await _get_records(
        _NINOS,
        formula=f"OR(LOWER({{APODO}})='{nombre_norm}', LOWER({{NOMBRE}})='{nombre_norm}')",
        max_records=5,
    )

    if not records:
        # Intentar búsqueda parcial
        records = await _get_records(
            _NINOS,
            formula=f"OR(FIND('{nombre_norm}', LOWER({{APODO}})), FIND('{nombre_norm}', LOWER({{NOMBRE}})))",
            max_records=5,
        )

    if not records:
        await proveedor.enviar_mensaje(telefono, f"❌ No encontré a '{nombre_buscar}' en NIÑOS FENIX")
        return

    if len(records) > 1:
        # Múltiples matches — mostrar opciones
        opciones = []
        for r in records:
            f = r.get("fields", {})
            opciones.append(f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')} ({f.get('APODO', '-')})")
        await proveedor.enviar_mensaje(
            telefono,
            f"Encontré {len(records)} niños:\n" + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(opciones)) +
            "\n\nUsá el nombre completo para ser más específico."
        )
        return

    # Un solo match — registrar cara
    nino_record = records[0]
    nino_id = nino_record["id"]
    fields = nino_record.get("fields", {})
    nombre_display = fields.get("APODO") or fields.get("NOMBRE", "")

    from agent.face_recognition import registrar_cara, actualizar_cara

    # Si ya tiene FACE_ID, actualizar
    face_id_existente = fields.get("FACE_ID", "")
    if face_id_existente:
        face_id = await actualizar_cara(nino_id, image_bytes)
        accion = "actualizada"
    else:
        face_id = await registrar_cara(nino_id, image_bytes)
        accion = "registrada"

    if face_id:
        # Guardar FACE_ID en Airtable
        await _patch(_NINOS, nino_id, {"FACE_ID": face_id})
        await proveedor.enviar_mensaje(telefono, f"✅ Cara {accion} para {nombre_display} (FaceId: {face_id[:8]}...)")
    else:
        await proveedor.enviar_mensaje(telefono, f"❌ No se detectó una cara clara en la foto de {nombre_display}. Probá con otra foto.")


# ════════════════════════════════════════════════════════════════════════════════
# BOTONES SEGUIMIENTO — marca ENVIADO o DESCARTADO en SEGUIMIENTO FENIX
# ════════════════════════════════════════════════════════════════════════════════


async def _procesar_boton_seguimiento(btn_id: str):
    """Procesa click en botón de seguimiento: seg_enviado_recXXX o seg_descartado_recXXX."""
    from agent.airtable_client import _patch

    _SEGUIMIENTO = "SEGUIMIENTO FENIX"

    if btn_id.startswith("seg_enviado_"):
        record_id = btn_id[len("seg_enviado_"):]
        ok = await _patch(_SEGUIMIENTO, record_id, {"ENVIADO": True})
        if ok:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", "595982790407"), "✅ Marcado como enviado")
        else:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", "595982790407"), "❌ Error marcando en Airtable")

    elif btn_id.startswith("seg_descartado_"):
        record_id = btn_id[len("seg_descartado_"):]
        ok = await _patch(_SEGUIMIENTO, record_id, {"DESCARTADO": True})
        if ok:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", "595982790407"), "❌ Marcado como descartado")
        else:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", "595982790407"), "❌ Error marcando en Airtable")
