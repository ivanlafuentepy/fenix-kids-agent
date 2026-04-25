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
    formatear_monto, PRECIOS, CI_BANCARIO, monto_prueba_por_hijos,
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
    actualizar_reserva_lead, marcar_control_datos,
    obtener_ninos_por_horario, formatear_lista_ninos,
    obtener_horarios_disponibles,
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
        mensaje_pre = f"Que tal {primer_nombre}, soy el profe Ivan, te puedo llamar ahora?" if primer_nombre else "Que tal, soy el profe Ivan, te puedo llamar ahora?"
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
    convertido = await esta_convertido(telefono)
    return {
        "telefono": telefono,
        "mensajes_totales": len(historial),
        "agent_actual": agent,
        "modo_nixie": modo,
        "familia_id": familia_id,
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


def _contar_numeros_rompehielos_historial(historial: list[dict]) -> tuple[int, list[int]]:
    """Busca en el historial los números del rompehielos que eligió el padre."""
    for m in historial:
        if m.get("role") == "user":
            nums = [int(n) for n in re.findall(r'\b(1[0-5]|[1-9])\b', m.get("content", ""))]
            if nums and len(nums) >= 1:
                # Verificar que sea respuesta al rompehielos (no cualquier número suelto)
                contenido = m.get("content", "").strip()
                # Si tiene 2+ números o el texto es mayormente números, es rompehielos
                if len(nums) >= 2 or re.fullmatch(r'[\d,.\s y]+', contenido):
                    return len(nums), nums
    return 0, []


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
    r"(?:mi\s+hij[oa]\s+(?:se\s+llama\s+)?|se\s+llama\s+|(?:hijo|hija|nene|nena|niño|niña)\s+)([a-záéíóúñA-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[a-záéíóúñA-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    re.IGNORECASE,
)


def _extraer_nombre_hijo_historial(historial: list[dict]) -> str:
    """Busca nombre del hijo en mensajes del padre y respuestas del agente."""
    # Buscar en mensajes del padre primero (regex explícito)
    for m in reversed(historial):
        if m.get("role") == "user":
            match = _REGEX_NOMBRE_HIJO.search(m.get("content", ""))
            if match:
                return match.group(1).strip().title()

    # Buscar cuando Ivan preguntó "cómo se llama tu hijo" y el padre respondió
    for i, m in enumerate(historial):
        if m.get("role") == "assistant" and re.search(
            r"c[oó]mo\s+se\s+llama\s+tu\s+hij[oa]", m.get("content", ""), re.IGNORECASE
        ):
            # El siguiente mensaje del usuario es la respuesta
            for j in range(i + 1, len(historial)):
                if historial[j].get("role") == "user":
                    resp = historial[j]["content"].strip()
                    # Puede ser "Maria", "se llama Maria", "Ivan, Maria", etc.
                    # Si tiene coma, el nombre del hijo suele ser la segunda parte
                    if "," in resp:
                        partes = [p.strip() for p in resp.split(",")]
                        # Tomar la última parte que parece nombre
                        for p in reversed(partes):
                            if p and p[0].isupper() and not any(c.isdigit() for c in p):
                                return p.split()[0].title()
                    # Si es un nombre solo o "se llama X"
                    m_nombre = re.search(r"(?:se\s+llama\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", resp, re.IGNORECASE)
                    if m_nombre:
                        return m_nombre.group(1).strip().title()
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
                # Excluir palabras genéricas
                if nombre.lower() not in ("tu", "el", "la", "su"):
                    return nombre

    # Buscar en respuestas del agente (ej: "Reserva confirmada ✅ Mateo...")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            contenido = m.get("content", "")
            match_conf = re.search(r"reserva confirmada[!✅\s]*\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", contenido, re.IGNORECASE)
            if match_conf:
                return match_conf.group(1).strip().title()
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
    mensaje_pre = f"Que tal {primer_nombre}, soy el profe Ivan desde mi personal, te puedo llamar ahora?" if primer_nombre else "Que tal, soy el profe Ivan desde mi personal, te puedo llamar ahora?"
    wa_link = f"https://wa.me/{telefono}?text={quote(mensaje_pre)}"

    alerta = (
        f"🚨 Urgente: Llamar a {nombre_padre}\n\n"
        f"👦 Hijo/a: {nombre_hijo}\n"
        f"🎂 Edad: {edad_hijo}\n\n"
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


def _detectar_confirmacion_aurora(respuesta: str) -> list[dict]:
    """
    Detecta si Aurora confirmó una o más reservas.
    Retorna lista de {"fecha": ..., "hora": ...} (puede tener 0, 1 o más).
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
    return resultados


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


async def _build_contexto_aurora(familia: dict, telefono: str = "") -> str:
    """Arma el contexto completo de una familia para inyectar en Aurora."""
    campos = familia.get("fields", {})

    # Detectar quién escribe por teléfono
    if telefono and campos.get("CELL PADRE") == telefono:
        quien_escribe = campos.get("APODO PADRE", "") or campos.get("NOMBRE PADRE", "")
        es_genero = "papá"
    elif telefono and campos.get("CELL MADRE") == telefono:
        quien_escribe = campos.get("APODO MADRE", "") or campos.get("NOMBRE MADRE", "")
        es_genero = "mamá"
    else:
        quien_escribe = (
            campos.get("APODO PADRE", "") or campos.get("NOMBRE PADRE", "")
            or campos.get("APODO MADRE", "") or campos.get("NOMBRE MADRE", "")
        )
        es_genero = "padre/madre"

    # Datos de quien escribe
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

    # Estado de verificación de datos
    control_datos = "verificado" if campos.get("CONTROL DATOS") else "pendiente"

    contexto = (
        f"CONTEXTO FAMILIA INSCRIPTA:\n"
        f"CONTROL_DATOS: {control_datos}\n"
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
        # ── Comando reset (solo admin) ────────────────────────────────────
        admin_phone = os.getenv("ADMIN_PHONE", "595982790407")
        _reset_phones = {admin_phone, "595982844548"}
        if texto.lower() == "holayosoyfenix" and telefono in _reset_phones:
            cancelar_seguimiento(telefono)
            cancelar_recordatorios(telefono)
            _cancelar_diagnostico_pendiente(telefono)
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

        # ── Botones del admin (confirmar/rechazar pago) ────────────────────
        if telefono == admin_phone and msg.es_boton:
            btn_titulo = texto.lower().strip()
            if "confirmar" in btn_titulo or "rechazar" in btn_titulo:
                await _procesar_boton_pago(btn_titulo)
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
                if topic_id:
                    await enviar_a_topic(topic_id, f"👤 {texto} (esperando diagnóstico)", telefono=telefono)
                logger.info(f"[DIAG] Padre dijo '{texto}' — ignorando, diagnóstico pendiente")
                return

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


        # ── Espejo en Telegram (con nombre de Airtable si existe) ─────────
        _topic_nombre = f"📱 {telefono}"
        try:
            # Buscar nombre en FAMILIAS o LEADS
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
        topic_id = await obtener_o_crear_topic(telefono, _topic_nombre)
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
            await guardar_mensaje(telefono, "user", texto)
            await guardar_mensaje(telefono, "assistant", respuesta)
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
            # Alerta al admin (WhatsApp + Telegram) — busca datos en Airtable
            await _alertar_pedido_llamada(telefono, historial_previo, texto)
            # Espejar en Telegram del lead (datos ya están en la alerta)
            if topic_id:
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {respuesta}", telefono=telefono)
            logger.info(f"[LLAMADA] Pedido de llamada detectado de {telefono}")
            return

        # ── Protección prompt injection ───────────────────────────────────
        if _es_mensaje_sospechoso(texto):
            respuesta = "Lo siento, no puedo procesar ese mensaje 🙏"
            await proveedor.enviar_mensaje(telefono, respuesta)
            return

        # ── Modo nocturno (23:00–07:00 PY) — admin y padres inscriptos sin límite
        if es_horario_nocturno() and telefono not in _PHONES_SIN_DELAY:
            # Padres inscriptos no tienen restricción nocturna
            _familia_nocturno = await buscar_familia_por_telefono(telefono)
            if not _familia_nocturno:
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

        # ── Diagnóstico diferido: si el padre responde la edad y eligió 2+ números,
        #    enviar "dame unos minutitos" y programar el diagnóstico con delay ──────
        if agent_actual == "ivan" and _detectar_respuesta_edad(texto, historial):
            cant_romp, nums_romp = _contar_numeros_rompehielos_historial(historial)
            if cant_romp >= 2:
                # Buscar nombre del hijo en Airtable
                _nombre_hijo_diag = ""
                try:
                    from agent.airtable_client import _get_records, _LEADS
                    _lr = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
                    if _lr:
                        _nombre_hijo_diag = _lr[0].get("fields", {}).get("NOMBRE NIÑO", "") or ""
                except Exception:
                    pass
                if not _nombre_hijo_diag:
                    _nombre_hijo_diag = _extraer_nombre_hijo_historial(historial)
                    if _nombre_hijo_diag == "no mencionó":
                        _nombre_hijo_diag = ""

                nums_str = ", ".join(str(n) for n in sorted(set(nums_romp)))
                sobre = f" sobre {_nombre_hijo_diag}" if _nombre_hijo_diag else ""
                msg_espera = f"Genial, dame unos minutitos y te respondo bien sobre los temas {nums_str} que me comentaste{sobre} 🙌"

                await guardar_mensaje(telefono, "user", texto)
                await guardar_mensaje(telefono, "assistant", msg_espera)
                await _delay_humano(msg_espera)
                await proveedor.enviar_mensaje(telefono, msg_espera)
                if topic_id:
                    await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {msg_espera}", telefono=telefono)

                # Programar diagnóstico diferido
                async def _enviar_diagnostico_diferido(tel, hist, ctx_extra, tid):
                    delay = _DELAY_DIAGNOSTICO if tel not in _PHONES_SIN_DELAY else 5
                    logger.info(f"[DIAG] Diagnóstico diferido para {tel} en {delay}s")
                    await asyncio.sleep(delay)
                    # Re-obtener historial (puede haber nuevos msgs intermedios)
                    hist_actual = await obtener_historial(tel, limite=40)
                    respuesta_diag = await generar_respuesta(
                        mensaje="(continuar con el diagnóstico completo que prometí)",
                        historial=hist_actual,
                        agent_actual="ivan",
                        contexto_extra=ctx_extra,
                    )
                    await guardar_mensaje(tel, "assistant", respuesta_diag)
                    await _delay_humano(respuesta_diag)
                    await proveedor.enviar_mensaje(tel, respuesta_diag)
                    if tid:
                        await enviar_a_topic(tid, f"👨‍🏫 IVAN: {respuesta_diag}", telefono=tel)
                    logger.info(f"[DIAG] Diagnóstico enviado a {tel}")
                    _diagnostico_pendiente.pop(tel, None)

                _cancelar_diagnostico_pendiente(telefono)
                task = _fire_and_forget(_enviar_diagnostico_diferido(telefono, historial, contexto_extra, topic_id))
                _diagnostico_pendiente[telefono] = task

                # Actualizar datos del lead (edad)
                try:
                    await actualizar_datos_lead(telefono, edad=texto.strip())
                except Exception:
                    pass

                logger.info(f"[DIAG] Esperando {_DELAY_DIAGNOSTICO}s para diagnóstico de {telefono} ({cant_romp} números)")
                return

        # ── Generar respuesta ─────────────────────────────────────────────
        respuesta = await generar_respuesta(
            mensaje=texto,
            historial=historial,
            agent_actual=agent_actual,
            contexto_extra=contexto_extra,
        )

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

        # ── Detectar cierre de onboarding Aurora (CONTROL DATOS) ──────────
        if agent_actual == "aurora" and "todo confirmado" in respuesta.lower():
            try:
                familia = await buscar_familia_por_telefono(telefono)
                if familia and not familia.get("fields", {}).get("CONTROL DATOS"):
                    await marcar_control_datos(familia["id"])
                    logger.info(f"[AURORA] CONTROL DATOS marcado para {telefono}")
            except Exception as e:
                logger.error(f"[AURORA] Error marcando CONTROL DATOS: {e}")

        # ── Detectar confirmación de reserva (Ivan o Aurora) ───────────────
        confirmaciones = _detectar_confirmacion_aurora(respuesta)
        for confirmacion in confirmaciones:
            await _procesar_confirmacion_reserva(telefono, confirmacion, respuesta)

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

        # ── Enviar afiche cuando padre muestra interés post-diagnóstico ──
        if (agent_actual == "ivan"
                and telefono not in _afiche_enviado
                and _diagnostico_ya_enviado(historial)
                and _padre_muestra_interes(texto)):
            _afiche_enviado.add(telefono)
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
    4. Enviar lista de niños agendados para ese horario
    5. Notificar en Telegram
    6. Programar recordatorio 07:00 PY del día de la clase
    """
    fecha_str = confirmacion.get("fecha", "")
    hora_str = confirmacion.get("hora", "")

    logger.info(f"Confirmación Aurora detectada: {fecha_str} {hora_str} para {telefono}")

    # Actualizar LEADS con conversión + datos de reserva
    await actualizar_conversion_lead(telefono, "AGENDA")
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

    # ── Crear registro en PRUEBA FENIX ──────────────────────────────────────────
    try:
        historial_completo = await obtener_historial(telefono, limite=40)

        # Obtener diagnóstico y lead_id
        from agent.airtable_client import _get_records, _LEADS
        lead_records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        lead_record_id = lead_records[0]["id"] if lead_records else None
        diagnostico_ids = lead_records[0].get("fields", {}).get("DIAGNOSTICO", []) if lead_records else []

        # Usar Haiku para extraer TODOS los datos del historial de forma confiable
        datos_form = await extraer_datos_formulario(historial_completo)
        padre_data = datos_form.get("padre") or {}
        nombre_resp = padre_data.get("nombre", "") or ""
        apellido_resp = padre_data.get("apellido", "") or ""
        ninos_form = datos_form.get("ninos", [])

        # Calcular monto correcto según cantidad de hijos
        _monto_prueba = monto_prueba_por_hijos(historial_completo)

        # Crear un registro PRUEBA FENIX por cada niño (monto solo en el primero)
        if ninos_form:
            for i, n in enumerate(ninos_form):
                await crear_prueba_fenix(
                    telefono=telefono,
                    nombre_responsable=nombre_resp,
                    apellido_responsable=apellido_resp,
                    nombre_hijo=n.get("nombre", ""),
                    apellido_hijo=n.get("apellido", ""),
                    edad_hijo="",
                    fecha_reserva=fecha_str,
                    hora=hora_str,
                    fecha_nacimiento=n.get("fecha_nacimiento", ""),
                    monto=_monto_prueba if i == 0 else 0,
                    diagnostico_ids=diagnostico_ids,
                    lead_record_id=lead_record_id,
                )
        else:
            # Fallback: extraer nombre del hijo del historial
            nh = _extraer_nombre_hijo_historial(historial_completo)
            nombre_responsable = _extraer_nombre_del_historial(historial_completo) or ""
            apellido_responsable = ""
            if nombre_responsable and " " in nombre_responsable:
                partes = nombre_responsable.split(" ", 1)
                nombre_responsable = partes[0]
                apellido_responsable = partes[1]
            await crear_prueba_fenix(
                telefono=telefono,
                nombre_responsable=nombre_responsable,
                apellido_responsable=apellido_responsable,
                nombre_hijo=nh if nh != "no mencionó" else "",
                apellido_hijo="",
                edad_hijo="",
                fecha_reserva=fecha_str,
                hora=hora_str,
                monto=_monto_prueba,
                diagnostico_ids=diagnostico_ids,
                lead_record_id=lead_record_id,
            )
    except Exception as e:
        logger.error(f"[PRUEBA FENIX] Error creando registro: {e}")

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
            await _programar_recordatorio_clase(telefono, fecha_iso, hora_str)
        except Exception as _e_rec:
            logger.error(f"[RECORDATORIO] Error programando para {telefono}: {_e_rec}")



# ── Afiche de precios ────────────────────────────────────────────────────────

_AFICHE_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "afiche_fenix.png")

async def _armar_followup_afiche(telefono: str) -> str:
    """Arma el follow-up del afiche con nombre del hijo desde Airtable."""
    nombre_hijo = ""
    try:
        from agent.airtable_client import _get_records, _LEADS
        records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
        if records:
            nombre_hijo = records[0].get("fields", {}).get("NOMBRE NIÑO", "") or ""
    except Exception:
        pass
    if nombre_hijo:
        parte_nombre = f"¿Te gustaría que {nombre_hijo} sea parte de Fenix Kids?"
    else:
        parte_nombre = "¿Te gustaría que tu hijo sea parte de Fenix Kids?"
    return (
        f"{parte_nombre}\n\n"
        "Te puedo agendar una clase de prueba por acá, o te gustaría que te llame "
        "un rato así te explico todo? 😊"
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

        # Follow-up dinámico con nombre del hijo (desde Airtable)
        followup = await _armar_followup_afiche(telefono)
        await proveedor.enviar_mensaje(telefono, followup)
        await guardar_mensaje(telefono, "assistant", followup)

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

    # Calcular monto correcto (multi-hijo)
    if tipo == "prueba":
        monto = monto_prueba_por_hijos(historial)
    else:
        monto = 0

    # Registrar pago pendiente
    await registrar_pago_pendiente(
        telefono=telefono,
        tipo=tipo,
        plan=tipo,
        monto=monto,
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
    monto_fmt = formatear_monto(monto) if monto else ""
    tipo_label = f"PRUEBA {monto_fmt}" if tipo == "prueba" and monto else "PRUEBA" if tipo == "prueba" else "INSCRIPCIÓN"
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


# ── /agenda — Ivan cierra agenda tras llamada telefónica ──────────────────────

_MONTOS_AGENDA = {"90mil": 90_000, "120mil": 120_000, "150mil": 150_000}


async def _cerrar_agenda_desde_telegram(telefono: str, comando: str, thread_id: int):
    """
    /agenda 90mil Carolina   → 1 hijo, 90k
    /agenda 120mil Carolina  → 2 hijos, 120k
    /agenda 150mil Carolina  → 3 hijos, 150k

    Ivan usa esto cuando cierra la agenda por llamada telefónica.
    Crea PRUEBA FENIX, reactiva el agente, y le manda al padre
    el formulario + datos bancarios para el comprobante.
    """
    partes = comando.strip().split(maxsplit=2)
    if len(partes) < 3 or partes[1].lower() not in _MONTOS_AGENDA:
        await enviar_a_topic(
            thread_id,
            "⚠️ Uso: /agenda 90mil|120mil|150mil nombre\nEj: /agenda 90mil Carolina",
            telefono=telefono,
        )
        return

    monto = _MONTOS_AGENDA[partes[1].lower()]
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

        # Actualizar conversión a AGENDA
        await actualizar_conversion_lead(telefono, "AGENDA")

        # Crear PRUEBA FENIX por cada niño (monto solo en primero)
        creados = 0
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

        # ── Datos bancarios para el comprobante ───────────────────────────
        from agent.pagos import DATOS_BANCARIOS
        monto_fmt = f"{monto:,}".replace(",", ".")

        msg_whatsapp = (
            f"{texto_form} 📋\n\n"
            f"El monto de la clase de prueba es {monto_fmt} Gs\n\n"
            f"{DATOS_BANCARIOS}\n\n"
            f"Pasame nomas acá el comprobante de transferencia, muchas gracias {nombre_padre} 🤝"
        )

        # Enviar al padre por WhatsApp
        await proveedor.enviar_mensaje(telefono, msg_whatsapp)
        await guardar_mensaje(telefono, "assistant", msg_whatsapp)

        # Reactivar el agente para que procese el comprobante
        await reactivar_dorita(telefono)

        # Notificar en Telegram
        monto_label = f"{monto_fmt} Gs"
        await enviar_a_topic(
            thread_id,
            f"✅ Agenda cerrada — {creados} PRUEBA FENIX — {monto_label}\n"
            f"📲 Mensaje enviado a {nombre_padre} con formulario + datos bancarios\n"
            f"🔊 Agente reactivado (esperando comprobante)",
            telefono=telefono,
        )
        logger.info(f"[AGENDA] {telefono}: {creados} registros, {monto_label}, msg enviado a {nombre_padre}")

    except Exception as e:
        logger.error(f"[CERRAR_AGENDA] Error: {e}")
        await enviar_a_topic(thread_id, f"❌ Error cerrando agenda: {e}", telefono=telefono)


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

        # /agenda [monto] [nombre] — Ivan cierra agenda tras llamada telefónica
        if texto_tg.strip().startswith("/agenda"):
            await _cerrar_agenda_desde_telegram(telefono, texto_tg, thread_id)
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
