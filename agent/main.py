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
from collections import OrderedDict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta, extraer_datos_formulario
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial,
    crear_recordatorio, obtener_recordatorios_pendientes,
    marcar_recordatorio_enviado, cancelar_recordatorios_por_telefono,
    mensaje_ya_procesado, registrar_mensaje_procesado,
    limpiar_mensajes_procesados_antiguos,
)
from agent.providers import obtener_proveedor
from agent.ab_test import (
    asignar_variante, obtener_estadisticas,
    marcar_conversion, esta_convertido,
    guardar_airtable_record_id, obtener_airtable_record_id,
    guardar_calendar_event_id, obtener_calendar_event_id,
    marcar_evento_creado, ya_tiene_evento,
    obtener_agent_actual, actualizar_agent_actual,
    obtener_familia_id,
    marcar_noche_pendiente, tiene_noche_pendiente,
)
from agent.night_mode import (
    es_horario_nocturno, MENSAJE_NOCHE,
    wakeup_loop as _noche_wakeup_loop,
    procesar_leads_pendientes as _noche_procesar_pendientes,
)
from agent.calendar_google import (
    insertar_evento_desde_fecha_iso, borrar_evento_google,
    fecha_iso_from_dia_hora,
)
from agent.telegram_bridge import (
    obtener_o_crear_topic, enviar_a_topic,
    dorita_esta_activa, silenciar_dorita, reactivar_dorita,
    obtener_telefono_por_topic,
    configurar_webhook, obtener_info_webhook,
    notificar_agenda_telegram, notificar_llamada_urgente,
    notificar_pago_telegram,
)
from agent.pagos import (
    es_posible_comprobante, detectar_tipo_pago,
    registrar_pago_pendiente, tiene_pago_pendiente,
    obtener_pago_pendiente, confirmar_pago, rechazar_pago,
    formatear_monto, PRECIOS, CI_BANCARIO,
)
from agent.airtable_client import (
    crear_lead, obtener_lead_record_id,
    actualizar_conversion_lead, actualizar_agent_lead,
    marcar_formulario_lead, crear_familia_completa,
    obtener_ninos_de_familia, crear_reserva,
    buscar_familia_por_telefono, buscar_familia_por_nombre,
    eliminar_lead, eliminar_todo_de_telefono,
    obtener_o_crear_horario, crear_prueba_fenix,
    actualizar_datos_lead, actualizar_diagnostico_lead,
    actualizar_reserva_lead,
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


# Cache local rápido para dedup (complementa PostgreSQL)
_dedup_cache: OrderedDict = OrderedDict()
_MAX_DEDUP_CACHE = 500


async def _delay_humano(texto: str):
    """Simula tiempo de tipeo para que el agente no parezca un bot."""
    base = 1.0 + random.uniform(-0.5, 0.5)
    bonus = min(2.0, len(texto) / 150 * 0.5)
    await asyncio.sleep(max(0.3, base + bonus))


# Números que no reciben delay de análisis (admin/pruebas)
_PHONES_SIN_DELAY = {os.getenv("ADMIN_PHONE", "595982790407")}

import re

def _contar_numeros_rompehielos(texto: str) -> int:
    """Cuenta cuántos números del 1 al 15 envió el lead (respuesta al rompehielos)."""
    # Buscar números del 1 al 15 en el texto
    numeros = re.findall(r'\b(1[0-5]|[1-9])\b', texto)
    # Deduplicar
    return len(set(numeros))


def _delay_por_numeros(cantidad: int) -> int:
    """Retorna el delay en segundos según cantidad de números elegidos."""
    if cantidad <= 1:
        return 30
    elif cantidad == 2:
        return 60
    elif cantidad == 3:
        return 120
    elif cantidad == 4:
        return 180
    else:
        return 240


import json
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

_TZ_PY = ZoneInfo("America/Asuncion")


async def _programar_recordatorio_clase(telefono: str, fecha_iso: str):
    """Programa recordatorio de clase para las 07:00 PY del día de la reserva."""
    await cancelar_recordatorios_por_telefono(telefono, tipo="clase")
    dt_clase = datetime.fromisoformat(fecha_iso)
    dia_clase = dt_clase.astimezone(_TZ_PY).date()
    envio_local = datetime.combine(dia_clase, time(7, 0), tzinfo=_TZ_PY)
    envio_utc = envio_local.astimezone(timezone.utc).replace(tzinfo=None)
    if envio_utc <= datetime.utcnow():
        logger.info(f"[RECORDATORIO] 07:00 PY ya pasó para {telefono} — omitido")
        return
    hora_clase = dt_clase.strftime("%H:%M")
    payload = json.dumps({"template": "recordatorio_clase", "hora": hora_clase})
    rec_id = await crear_recordatorio(telefono, "clase", envio_utc, payload)
    logger.info(f"[RECORDATORIO] Clase programado id={rec_id} para {telefono} — {dia_clase} 07:00 PY")


async def _enviar_recordatorio(rec):
    """Envía un recordatorio pendiente como mensaje de texto."""
    data = json.loads(rec.payload)
    hora = data.get("hora", "")
    msg = f"Hola! Te recordamos que hoy tenés tu clase a las {hora} en Fenix Kids 🥋 Te esperamos!"
    ok = await proveedor.enviar_mensaje(rec.telefono, msg)
    if ok:
        await guardar_mensaje(rec.telefono, "assistant", msg)
    return ok


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
    evento = await ya_tiene_evento(telefono)
    convertido = await esta_convertido(telefono)
    return {
        "telefono": telefono,
        "mensajes_totales": len(historial),
        "agent_actual": agent,
        "modo_nixie": modo,
        "familia_id": familia_id,
        "ya_tiene_evento": evento,
        "esta_convertido": convertido,
        "ultimos_5": historial[-5:] if len(historial) >= 5 else historial,
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


def _detectar_activacion_aurora(texto: str) -> bool:
    """El padre escribió directamente a Aurora."""
    t = texto.lower()
    return any(k in t for k in _CLAVES_AURORA)


def _detectar_handoff_ivan_aurora(respuesta: str) -> bool:
    """Ivan dijo 'En breve te contacta AURORA' — señal de transferencia."""
    t = respuesta.lower()
    return "en breve te contacta aurora" in t or "te contacta aurora" in t


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
]

_REGEX_NOMBRE_PRESENTACION = re.compile(
    r"\b(?:soy|me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    re.IGNORECASE,
)
_PALABRAS_NO_NOMBRE = {
    "el", "la", "un", "una", "mi", "la mama", "la mamá", "el papa", "el papá",
    "papa", "papá", "mama", "mamá", "mami", "papi", "de",
}


def _detectar_pedido_llamada(texto: str) -> bool:
    """Detecta si el padre está pidiendo hablar por teléfono / llamada."""
    t = texto.lower()
    return any(re.search(p, t) for p in _PATRONES_LLAMADA)


def _extraer_nombre_del_historial(historial: list[dict], texto_nuevo: str = "") -> str | None:
    """Busca el nombre del padre en mensajes 'soy X', 'me llamo X', etc."""
    # Empezar por el mensaje nuevo, después historial de más reciente a más viejo
    textos = [texto_nuevo] if texto_nuevo else []
    textos += [m.get("content", "") for m in reversed(historial) if m.get("role") == "user"]
    for t in textos:
        m = _REGEX_NOMBRE_PRESENTACION.search(t)
        if not m:
            continue
        cand = m.group(1).strip()
        if cand.lower() in _PALABRAS_NO_NOMBRE:
            continue
        # Evitar capturas tipo "la mamá de Juan"
        primera = cand.split()[0].lower()
        if primera in _PALABRAS_NO_NOMBRE:
            continue
        return cand.title()
    return None


_REGEX_NOMBRE_HIJO = re.compile(
    r"(?:mi\s+hij[oa]\s+(?:se\s+llama\s+)?|se\s+llama\s+|(?:hijo|hija|nene|nena|niño|niña)\s+)([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    re.IGNORECASE,
)


def _extraer_nombre_hijo_historial(historial: list[dict]) -> str:
    """Busca nombre del hijo en mensajes del padre y respuestas del agente."""
    # Buscar en mensajes del padre primero
    for m in reversed(historial):
        if m.get("role") == "user":
            match = _REGEX_NOMBRE_HIJO.search(m.get("content", ""))
            if match:
                return match.group(1).strip().title()
    # Buscar en respuestas del agente (ej: "Reserva confirmada ✅ Mateo...")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            contenido = m.get("content", "")
            match_conf = re.search(r"reserva confirmada[!✅\s]*\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", contenido, re.IGNORECASE)
            if match_conf:
                return match_conf.group(1).strip().title()
    return "no mencionó"


async def _alertar_pedido_llamada(telefono: str, historial: list[dict], texto_nuevo: str):
    """
    Manda alerta al admin cuando un lead pide hablar por teléfono.
    Doble canal: WhatsApp (ADMIN_PHONE) + Telegram (grupo agenda).
    """
    from urllib.parse import quote

    nombre_padre = _extraer_nombre_del_historial(historial, texto_nuevo) or "no se presentó"
    primer_nombre = nombre_padre.split()[0] if nombre_padre != "no se presentó" else ""
    mensaje_pre = f"Hola {primer_nombre}, soy el profe Ivan otra vez, te puedo llamar ahora?" if primer_nombre else "Hola, soy el profe Ivan otra vez, te puedo llamar ahora?"
    wa_link = f"https://wa.me/{telefono}?text={quote(mensaje_pre)}"

    # Extraer nombre del hijo del historial (busca "mi hijo X", "se llama X", etc.)
    nombre_hijo = _extraer_nombre_hijo_historial(historial)

    alerta = (
        f"🚨 URGENTE, UN PADRE FENIX QUIERE HABLAR CONTIGO\n\n"
        f"👤 Padre: {nombre_padre}\n"
        f"👦 Hijo/a: {nombre_hijo}\n"
        f"📱 {telefono}\n\n"
        f"📲 {wa_link}"
    )

    # Canal 1: WhatsApp al admin
    admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
    try:
        ok = await proveedor.enviar_mensaje(admin_phone, alerta)
        logger.info(f"[LLAMADA] Alerta WhatsApp al admin {admin_phone}: {'OK' if ok else 'FAIL'}")
    except Exception as e:
        logger.error(f"[LLAMADA] Error WhatsApp admin: {e}")

    # Canal 2: Telegram grupo (respaldo)
    try:
        await notificar_llamada_urgente(telefono, nombre_padre, wa_link)
    except Exception as e:
        logger.error(f"[LLAMADA] Error Telegram: {e}")


def _detectar_confirmacion_aurora(respuesta: str) -> dict | None:
    """
    Detecta si Aurora confirmó una reserva.
    Retorna {"fecha": ..., "hora": ...} o None.
    """
    patrones = [
        r"reserva confirmada[!✅\s]*.*?(?:el\s+)?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"tiene su lugar.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"quedaron reservados.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"listo[!✅\s🙌]*.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"qued[aá]s confirmad[oa].*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"agendam.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
    ]
    texto_lower = respuesta.lower()
    for patron in patrones:
        match = re.search(patron, texto_lower)
        if match:
            return {"fecha": match.group(1).strip(), "hora": match.group(2).strip()}
    return None


# ── WhatsApp webhook ──────────────────────────────────────────────────────────

@app.get("/webhook")
async def webhook_verificacion(request: Request):
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Handler ultra-rápido: parsea, deduplica, lanza tasks async y responde 200 OK.
    Meta espera respuesta en < 20s — el procesamiento real puede tardar minutos
    (delays por números del rompehielos, Claude API, etc.) así que va en background.
    """
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            # Deduplicación: cache local rápido + PostgreSQL persistente
            if msg.mensaje_id:
                if msg.mensaje_id in _dedup_cache:
                    continue
                _dedup_cache[msg.mensaje_id] = True
                while len(_dedup_cache) > _MAX_DEDUP_CACHE:
                    _dedup_cache.popitem(last=False)
                if await mensaje_ya_procesado(msg.mensaje_id):
                    continue
                await registrar_mensaje_procesado(msg.mensaje_id)

            # Rate limit por teléfono
            if _check_rate_limit(msg.telefono):
                logger.warning(f"[RATE LIMIT] {msg.telefono} excede {_RATE_LIMIT_MAX} msgs/{_RATE_LIMIT_WINDOW}s")
                continue

            # Lanzar procesamiento en background — no bloquear el webhook
            _fire_and_forget(_procesar_mensaje_webhook(msg))

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error parseando webhook: {e}", exc_info=True)
        # Retornar 200 igualmente para que Meta no reintente por errores de parsing
        return {"status": "error"}


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
        # ── Comando reset (solo admin) ────────────────────────────────────
        admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
        if texto.lower() == "holayosoyfenix" and telefono == admin_phone:
            cancelar_seguimiento(telefono)
            cancelar_recordatorios(telefono)
            event_id_prev = await obtener_calendar_event_id(telefono)
            if event_id_prev:
                try:
                    await borrar_evento_google(event_id_prev)
                except Exception as e:
                    logger.error(f"Error borrando evento Calendar en reset: {e}")
            contador = await eliminar_todo_de_telefono(telefono)
            await limpiar_estado_completo(telefono)
            resumen = (
                f"Reset completo ✅\n"
                f"Borrados: lead={contador['lead']}, familia={contador['familia']}, "
                f"niños={contador['ninos']}, reservas={contador['reservas']}"
            )
            await proveedor.enviar_mensaje(telefono, resumen)
            topic_reset = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            if topic_reset:
                await enviar_a_topic(topic_reset, f"⚙️ RESET completo — {resumen}", telefono=telefono)
            return

        # ── Botones del admin (confirmar/rechazar pago) ────────────────────
        admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
        if telefono == admin_phone and msg.es_boton:
            btn_titulo = texto.lower().strip()
            if "confirmar" in btn_titulo or "rechazar" in btn_titulo:
                await _procesar_boton_pago(btn_titulo)
                return

        # ── Cancelar timers pendientes ────────────────────────────────────
        cancelar_seguimiento(telefono)

        # ── Transcribir audio ANTES de todo (para que detectores usen texto real)
        if hasattr(msg, "media_id") and msg.media_id:
            try:
                audio_bytes, mime_type = await descargar_audio_whatsapp(msg.media_id)
                if audio_bytes:
                    transcripcion = await transcribir_audio(audio_bytes, mime_type)
                    if transcripcion:
                        texto = transcripcion
                        logger.info(f"Audio transcripto: {texto[:80]}")
                    else:
                        logger.warning(f"Transcripción vacía para {msg.media_id}")
            except Exception as e:
                logger.error(f"Error transcribiendo audio: {e}")

        # ── Espejo en Telegram ────────────────────────────────────────────
        topic_id = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
        if topic_id:
            await enviar_a_topic(topic_id, f"👤 {texto}", telefono=telefono)

        # ── Verificar si Ivan (admin) está respondiendo manualmente ──��────
        if not await dorita_esta_activa(telefono):
            logger.info(f"Agente silenciado para {telefono} — Ivan activo en Telegram")
            return

        # ── Detección de comprobante de pago ───────���─────────────────────
        historial_pago = await obtener_historial(telefono)
        if es_posible_comprobante(texto, historial_pago):
            await _procesar_comprobante(telefono, texto, msg.media_id, historial_pago, topic_id)
            return

        # ── Pedido de llamada → respuesta fija + alerta urgente al admin ──
        if _detectar_pedido_llamada(texto):
            historial_previo = await obtener_historial(telefono)
            nombre_padre = _extraer_nombre_del_historial(historial_previo, texto)
            primer_nombre = nombre_padre.split()[0] if nombre_padre else ""
            if primer_nombre:
                respuesta = (
                    f"Ahora mismo no puedo atender llamadas, aguantame un ratito "
                    f"{primer_nombre} y te llamo desde mi línea personal 🤝"
                )
            else:
                respuesta = (
                    "Ahora mismo no puedo atender llamadas, aguantame un ratito "
                    "y te llamo desde mi línea personal 🤝"
                )
            await guardar_mensaje(telefono, "user", texto)
            await guardar_mensaje(telefono, "assistant", respuesta)
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
            # Alerta al admin (WhatsApp + Telegram)
            await _alertar_pedido_llamada(telefono, historial_previo, texto)
            # Espejar en Telegram del lead
            if topic_id:
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {respuesta}", telefono=telefono)
                await enviar_a_topic(topic_id, f"🚨 Alerta de llamada enviada al admin", telefono=telefono)
            logger.info(f"[LLAMADA] Pedido de llamada detectado de {telefono}")
            return

        # ── Protección prompt injection ───────────────────────────────────
        if _es_mensaje_sospechoso(texto):
            respuesta = "Lo siento, no puedo procesar ese mensaje 🙏"
            await proveedor.enviar_mensaje(telefono, respuesta)
            return

        # ── Modo nocturno (23:00–07:00 PY) — admin puede testear siempre
        if es_horario_nocturno() and telefono not in _PHONES_SIN_DELAY:
            historial_noche = await obtener_historial(telefono, limite=5)
            _tiene_actividad = len(historial_noche) > 0
            if not _tiene_actividad or not await tiene_noche_pendiente(telefono):
                await guardar_mensaje(telefono, "user", texto)
                if not await tiene_noche_pendiente(telefono):
                    await proveedor.enviar_mensaje(telefono, MENSAJE_NOCHE)
                    await guardar_mensaje(telefono, "assistant", MENSAJE_NOCHE)
                await asignar_variante(telefono)
                await marcar_noche_pendiente(telefono)
                return

        # ── Estado de la conversación ─────────────────────────────────────
        agent_actual, modo_nixie = await obtener_agent_actual(telefono)

        # ── Obtener historial (40 msgs para no perder contexto en charlas largas)
        historial = await obtener_historial(telefono, limite=40)

        # ── Lead nuevo: primer contacto + router Ivan/Aurora por teléfono ──
        _, es_nuevo = await asignar_variante(telefono)
        if es_nuevo:
            # Router: si el teléfono ya está en FAMILIAS (inscripto) → Aurora.
            # Si no → Ivan (lead de anuncios / nuevo).
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
            # Crear lead en Airtable con el agente correcto
            record_id = await crear_lead(telefono, rompehielos="A")
            if record_id:
                await guardar_airtable_record_id(telefono, record_id)
            await actualizar_agent_lead(telefono, agent_actual.upper(), modo_nixie)

        # ── Si es Aurora cliente_inscripto: inyectar contexto con sus hijos ──
        contexto_extra = None
        if agent_actual == "aurora" and modo_nixie == "cliente_inscripto":
            familia_existente = await buscar_familia_por_telefono(telefono)
            if familia_existente:
                campos = familia_existente.get("fields", {})
                nombre_padre = campos.get("NOMBRE PADRE", "") or campos.get("NOMBRE MADRE", "")
                hijos_raw = await obtener_ninos_de_familia(familia_existente["id"])
                nombres_hijos = [h["nombre_completo"] or h["nombre"] for h in hijos_raw]
                contexto_extra = (
                    f"CONTEXTO: Este padre ya está inscripto. "
                    f"Su nombre es {nombre_padre}. "
                    f"Sus hijos registrados son: {', '.join(nombres_hijos) if nombres_hijos else 'ninguno aún'}."
                )

        # ── Delay de análisis (respuesta a números del rompehielos) ────────
        cant_numeros = _contar_numeros_rompehielos(texto)
        if agent_actual == "ivan" and cant_numeros > 0:
            # Guardar diagnóstico en Airtable
            numeros_elegidos = [int(n) for n in re.findall(r'\b(1[0-5]|[1-9])\b', texto)]
            if numeros_elegidos:
                try:
                    await actualizar_diagnostico_lead(telefono, list(set(numeros_elegidos)))
                except Exception as e:
                    logger.error(f"[DIAGNOSTICO] Error guardando para {telefono}: {e}")
            # Delay solo para leads reales (no admin)
            if not es_nuevo and telefono not in _PHONES_SIN_DELAY:
                delay_s = _delay_por_numeros(cant_numeros)
                logger.info(f"Delay análisis: {cant_numeros} números → {delay_s}s para {telefono}")
                await asyncio.sleep(delay_s)

        # ── Generar respuesta ─────────────────────────────────────────────
        respuesta = await generar_respuesta(
            mensaje=texto,
            historial=historial,
            agent_actual=agent_actual,
            contexto_extra=contexto_extra,
        )

        # ── Si Ivan está manejando un lead nuevo (no inscripto):
        #    intentar extraer formulario para crear FAMILIA+NIÑOS ──────────
        if agent_actual == "ivan":
            historial_completo = historial + [
                {"role": "user", "content": texto},
                {"role": "assistant", "content": respuesta},
            ]
            try:
                datos = await extraer_datos_formulario(historial_completo)
                if datos.get("completo") and not await esta_convertido(telefono):
                    familia_id, nino_ids = await crear_familia_completa(telefono, datos)
                    if familia_id:
                        await marcar_conversion(telefono)
                        await actualizar_conversion_lead(telefono, "AGENDA")
                        logger.info(f"Formulario completo para {telefono}: familia={familia_id}")
                        cancelar_recordatorios(telefono)
            except Exception as e:
                logger.error(f"[FORMULARIO] Error extrayendo datos para {telefono}: {e}")

        # ── Actualizar datos del lead en Airtable (nombre, hijo, edad) ────
        if agent_actual == "ivan":
            try:
                _nombre_resp = _extraer_nombre_del_historial(historial, texto)
                _nombre_hijo = _extraer_nombre_hijo_historial(historial + [{"role": "user", "content": texto}])
                # Extraer edad: buscar número tras "tiene X años" o respuesta a "cuántos años"
                _edad = ""
                import re as _re
                for _m in reversed(historial + [{"role": "user", "content": texto}]):
                    if _m.get("role") == "user":
                        _match_edad = _re.search(r'\b(\d{1,2})\s*(?:años|ano|a[ñn]os)?\b', _m["content"])
                        if _match_edad and 2 <= int(_match_edad.group(1)) <= 15:
                            _edad = _match_edad.group(1)
                            break
                if _nombre_resp or (_nombre_hijo and _nombre_hijo != "no mencionó") or _edad:
                    await actualizar_datos_lead(
                        telefono,
                        nombre_responsable=_nombre_resp or "",
                        nombre_nino=_nombre_hijo if _nombre_hijo != "no mencionó" else "",
                        edad=_edad,
                    )
            except Exception as e:
                logger.error(f"[LEAD DATA] Error actualizando datos lead {telefono}: {e}")

        # ── Detectar confirmación de reserva (Ivan o Aurora) ───────────────
        confirmacion = _detectar_confirmacion_aurora(respuesta)
        if confirmacion:
            await _procesar_confirmacion_reserva(telefono, confirmacion, respuesta)

        # ── Guardar mensajes ──────────────────────────────────────────────
        await guardar_mensaje(telefono, "user", texto)
        await guardar_mensaje(telefono, "assistant", respuesta)

        # ── Enviar respuesta (con delay humano) ────────────────────────────
        await _delay_humano(respuesta)
        await proveedor.enviar_mensaje(telefono, respuesta)

        # ── Espejo respuesta en Telegram ──────────────────────────────────
        agente_label = "🌟 AURORA" if agent_actual == "aurora" else "👨‍🏫 IVAN"
        if topic_id:
            await enviar_a_topic(topic_id, f"{agente_label}: {respuesta}", telefono=telefono)

        # ── Enviar afiche si Ivan dijo "te paso un afiche" ───────────────
        if "te paso un afiche" in respuesta.lower():
            await _enviar_afiche_y_followup(telefono, topic_id)

        # ── Programar seguimiento si es lead nuevo sin respuesta ──────────
        if es_nuevo:
            programar_seguimiento_inicial(
                telefono=telefono,
                proveedor=proveedor,
                guardar_fn=_guardar_mensaje,
                formulario_check_fn=esta_convertido,
            )

    except Exception as e:
        logger.error(f"[WEBHOOK-TASK] Error procesando mensaje de {telefono}: {e}", exc_info=True)


async def _procesar_confirmacion_reserva(
    telefono: str,
    confirmacion: dict,
    respuesta_aurora: str,
):
    """
    Cuando Aurora confirma una reserva:
    1. Actualizar CONVERSION=AGENDA en LEADS
    2. Obtener/crear HORARIO en Airtable
    3. Crear RESERVA(s) en Airtable — una por cada niño de la familia
    4. Crear evento en Google Calendar con nombre real del/los niño/s
    5. Notificar en Telegram
    6. Programar recordatorio 07:00 PY del día de la clase
    """
    fecha_str = confirmacion.get("fecha", "")
    hora_str = confirmacion.get("hora", "")

    logger.info(f"Confirmación Aurora detectada: {fecha_str} {hora_str} para {telefono}")

    # Actualizar LEADS con conversión + datos de reserva
    await actualizar_conversion_lead(telefono, "AGENDA")
    await actualizar_reserva_lead(telefono, fecha_str, hora_str)

    # Calcular fecha ISO
    fecha_iso = None
    if fecha_str and hora_str:
        try:
            fecha_iso = fecha_iso_from_dia_hora(f"sabado {fecha_str}", hora_str)
        except Exception as e:
            logger.error(f"Error calculando fecha ISO: {e}")

    # ── Obtener niños de la familia (para nombre real + RESERVAS) ──────────────
    familia_id = await obtener_familia_id(telefono)
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

    # ── Crear RESERVA en Airtable por cada niño ─────────────────────────────────
    if fecha_iso and ninos:
        # fecha_iso viene como "YYYY-MM-DDTHH:MM:SS-04:00" → extraer YYYY-MM-DD
        fecha_airtable = fecha_iso.split("T")[0]
        try:
            horario_id = await obtener_o_crear_horario(fecha_airtable, hora_str)
            if horario_id:
                for nino in ninos:
                    rid = await crear_reserva(nino["id"], horario_id)
                    if rid:
                        logger.info(f"Reserva creada: {nino.get('nombre_completo', nino['id'])} → {rid}")
            else:
                logger.warning(f"No se pudo obtener/crear HORARIO {fecha_airtable} {hora_str}")
        except Exception as e:
            logger.error(f"Error creando RESERVA para {telefono}: {e}")

    # ── Crear registro en PRUEBA FENIX ──────────────────────────────────────────
    try:
        historial_completo = await obtener_historial(telefono, limite=40)
        nombre_responsable = _extraer_nombre_del_historial(historial_completo) or ""
        apellido_responsable = ""
        if nombre_responsable and " " in nombre_responsable:
            partes = nombre_responsable.split(" ", 1)
            nombre_responsable = partes[0]
            apellido_responsable = partes[1]

        # Crear un registro PRUEBA FENIX por cada niño
        if ninos:
            for n in ninos:
                await crear_prueba_fenix(
                    telefono=telefono,
                    nombre_responsable=nombre_responsable,
                    apellido_responsable=apellido_responsable,
                    nombre_hijo=n.get("nombre", ""),
                    apellido_hijo=n.get("apellido", ""),
                    edad_hijo="",
                    fecha_reserva=fecha_str,
                    hora=hora_str,
                )
        else:
            # Sin familia creada — extraer del historial
            nh = _extraer_nombre_hijo_historial(historial_completo)
            await crear_prueba_fenix(
                telefono=telefono,
                nombre_responsable=nombre_responsable,
                apellido_responsable=apellido_responsable,
                nombre_hijo=nh if nh != "no mencionó" else "",
                apellido_hijo="",
                edad_hijo="",
                fecha_reserva=fecha_str,
                hora=hora_str,
            )
    except Exception as e:
        logger.error(f"[PRUEBA FENIX] Error creando registro: {e}")

    # ── Crear o actualizar evento en Google Calendar ───────────────────────────
    if fecha_iso:
        event_id_anterior = await obtener_calendar_event_id(telefono)
        if event_id_anterior:
            await borrar_evento_google(event_id_anterior)

        try:
            evento = await insertar_evento_desde_fecha_iso(
                fecha_iso=fecha_iso,
                telefono=telefono,
                nombre=nombre_display,
            )
        except Exception as e:
            logger.error(f"[CALENDAR] Error creando evento para {telefono}: {e}")
            evento = None
        if evento and evento.get("evento_id"):
            await guardar_calendar_event_id(telefono, evento["evento_id"])
            await marcar_evento_creado(telefono)
            # Enviar link del evento al padre
            link = evento.get("evento_link", "")
            if link:
                await proveedor.enviar_mensaje(
                    telefono,
                    f"📅 Guardá la fecha en tu calendario: {link}"
                )
        elif fecha_iso:
            logger.error(f"[CALENDAR] Evento no creado para {telefono} — fecha_iso={fecha_iso}")

    # Notificar en Telegram
    await notificar_agenda_telegram(
        telefono=telefono,
        dia=fecha_str,
        hora=hora_str,
        nombre=nombre_display if ninos else None,
    )

    # Programar recordatorio persistente para el día de la clase (07:00 PY)
    if fecha_iso:
        try:
            await _programar_recordatorio_clase(telefono, fecha_iso)
        except Exception as _e_rec:
            logger.error(f"[RECORDATORIO] Error programando para {telefono}: {_e_rec}")



# ── Afiche de precios ────────────────────────────────────────────────────────

_AFICHE_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "afiche_fenix.png")

_AFICHE_FOLLOWUP = (
    "Con la opción trimestral como verás tenemos un gran descuento, "
    "tb tenés la opción de venir a probar un sábado en cualquiera de los horarios por 90.000 Gs 🔥\n\n"
    "¿Te gustaría ser parte de Fenix Kids Academy?"
)


async def _enviar_afiche_y_followup(telefono: str, topic_id: int | None):
    """Envía el afiche de precios y después de 3s el mensaje de follow-up."""
    try:
        with open(_AFICHE_PATH, "rb") as f:
            image_bytes = f.read()

        ok = await proveedor.enviar_imagen_bytes(telefono, image_bytes, "image/png")
        if ok:
            logger.info(f"[AFICHE] Imagen enviada a {telefono}")
        else:
            logger.error(f"[AFICHE] Error enviando imagen a {telefono}")

        # Delay de 3 segundos antes del follow-up
        await asyncio.sleep(3)

        # Follow-up
        await proveedor.enviar_mensaje(telefono, _AFICHE_FOLLOWUP)
        await guardar_mensaje(telefono, "assistant", _AFICHE_FOLLOWUP)

        if topic_id:
            await enviar_a_topic(topic_id, f"📋 Afiche enviado + follow-up", telefono=telefono)

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

    # Responder al lead
    respuesta = "Recibido! Estamos verificando tu comprobante 😊"
    await guardar_mensaje(telefono, "user", texto)
    await guardar_mensaje(telefono, "assistant", respuesta)
    await proveedor.enviar_mensaje(telefono, respuesta)

    # Espejar en Telegram
    if topic_id:
        await enviar_a_topic(topic_id, f"💳 Comprobante detectado — esperando confirmación admin", telefono=telefono)

    # Registrar pago pendiente
    await registrar_pago_pendiente(
        telefono=telefono,
        tipo=tipo,
        plan=tipo,
        monto=PRECIOS.get("prueba", {}).get("total", 90_000) if tipo == "prueba" else 0,
        media_id=media_id,
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

    # Enviar botones al admin
    tipo_label = "PRUEBA 90K" if tipo == "prueba" else "INSCRIPCIÓN"
    msg_admin = (
        f"🔔 Comprobante recibido\n\n"
        f"👤 Padre: {nombre_padre}\n"
        f"👦 Hijo/a: {nombre_hijo}\n"
        f"📱 {telefono}\n"
        f"💰 Tipo: {tipo_label}\n\n"
        f"¿Confirmás el pago?"
    )
    botones = [
        {"id": f"pago_ok_{telefono}", "title": "✅ Confirmar"},
        {"id": f"pago_no_{telefono}", "title": "❌ Rechazar"},
    ]
    try:
        await proveedor.enviar_botones(admin_phone, msg_admin, botones)
    except Exception as e:
        logger.error(f"[PAGOS] Error enviando botones al admin: {e}")
        # Fallback: mensaje de texto normal
        await proveedor.enviar_mensaje(admin_phone, msg_admin + "\n\n(Respondé 'confirmar' o 'rechazar')")

    # Notificar en Telegram
    try:
        await notificar_pago_telegram(
            telefono=telefono,
            nombre=nombre_padre,
            estado="comprobante_recibido",
            tipo=tipo_label,
        )
    except Exception as e:
        logger.error(f"[PAGOS] Error notificando Telegram: {e}")

    logger.info(f"[PAGOS] Comprobante procesado para {telefono} tipo={tipo}")


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

        # Notificar en Telegram
        topic_id = await obtener_o_crear_topic(tel_lead, f"📱 {tel_lead}")
        if topic_id:
            await enviar_a_topic(topic_id, f"✅ PAGO CONFIRMADO — {tipo_label}", telefono=tel_lead)

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
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {respuesta_ivan}", telefono=tel_lead)
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

        # Notificar en Telegram
        topic_id = await obtener_o_crear_topic(tel_lead, f"📱 {tel_lead}")
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

        # Comandos de control
        if texto_tg.strip() == "/silenciar":
            await silenciar_dorita(telefono)
            await enviar_a_topic(thread_id, "🔇 Agente IA silenciado. Ivan activo.", telefono=telefono)
            return {"status": "ok"}

        if texto_tg.strip() in ("/reactivar", "/fenix"):
            await reactivar_dorita(telefono)
            await enviar_a_topic(thread_id, "🔊 Agente Fénix activado.", telefono=telefono)
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
