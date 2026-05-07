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
    # Normalizar separadores: puntos, guiones, espacios → comas
    texto_norm = re.sub(r'[.\-/\s]+', ',', texto.strip())
    # Buscar números del 1 al 15
    numeros = re.findall(r'\b(1[0-5]|[1-9])\b', texto_norm)
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

    # Follow-up leads: 9:00 AM PY, recorre leads con datos bancarios sin pago
    _followup_task = _fire_and_forget(_followup_loop())

    # Follow-up masivo fotos: ONE-SHOT (ya ejecutado 5/5)
    _followup_fotos_task = _fire_and_forget(_followup_fotos_oneshot())
    # Follow-up video: ONE-SHOT 6:00 AM PY 2026-05-06
    _followup_video_task = _fire_and_forget(_followup_video_oneshot())

    # Keepalive: mantener ventana WhatsApp del admin abierta (cada 6h)
    _keepalive_task = _fire_and_forget(_keepalive_admin_loop())

    # Contenido social: polling CONTENIDO FENIX + calendario diario
    from agent.contenido_social import iniciar_contenido_social
    iniciar_contenido_social(proveedor)

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
    return {
        "telefono": telefono,
        "mensajes_totales": len(historial),
        "agent_actual": agent,
        "modo_nixie": modo,
        "familia_id": familia_id,
        "esta_convertido": convertido,
        "ultimos_5": historial[-5:] if len(historial) >= 5 else historial,
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


def _contar_numeros_rompehielos_historial(historial: list[dict]) -> tuple[int, list[int]]:
    """Busca en el historial los números del rompehielos que eligió el padre."""
    for m in historial:
        if m.get("role") == "user":
            _cont = re.sub(r'[.\-/\s]+', ',', m.get("content", "").strip())
            nums = [int(n) for n in re.findall(r'\b(1[0-5]|[1-9])\b', _cont)]
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

        # ── Comando resumen anuncios (solo admin) ──────────────────────────
        _texto_cmd = texto.lower().strip().rstrip(".,!?")
        if telefono == admin_phone and "resumen" in _texto_cmd and "anuncio" in _texto_cmd:
            try:
                await _generar_resumen_anuncios(telefono, _texto_cmd)
            except Exception as e:
                logger.error(f"[RESUMEN] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando resumen: {e}")
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
            await proveedor.enviar_mensaje(
                telefono,
                "Modo alumno ✅\nConversación limpia, Airtable intacto.\nEscribí como si fueras un padre inscripto."
            )
            topic_alumno = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            if topic_alumno:
                await enviar_a_topic(topic_alumno, "⚙️ MODO ALUMNO — reset conversación sin tocar Airtable", telefono=telefono)
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

        # ── Generar respuesta ─────────────────────────────────────────────
        respuesta = await generar_respuesta(
            mensaje=texto,
            historial=historial,
            agent_actual=agent_actual,
            contexto_extra=contexto_extra,
        )

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

        # ── Detectar si el afiche va a enviarse (para no duplicar precios) ──
        _va_a_enviar_afiche = False
        if agent_actual == "ivan" and telefono not in _afiche_enviado:
            _ivan_dice_afiche_check = "te paso un afiche" in respuesta.lower()
            _interes_post_diag_check = (
                _diagnostico_ya_enviado(historial)
                and _padre_muestra_interes(texto)
            )
            if _ivan_dice_afiche_check or _interes_post_diag_check:
                _va_a_enviar_afiche = True

        # ── Enviar respuesta (con delay humano) ────────────────────────────
        if _va_a_enviar_afiche:
            # Afiche + msg_precios (hardcoded) — respuesta de Claude se omite
            # porque el afiche ya cubre precios/horarios/CTA
            _afiche_enviado.add(telefono)
            await _enviar_afiche_y_followup(telefono, topic_id, _tg_group)
        else:
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)

        # ── Espejo respuesta en Telegram ──────────────────────────────────
        agente_label = "🌟 AURORA" if agent_actual == "aurora" else "👨‍🏫 IVAN"
        if topic_id:
            await enviar_a_topic(topic_id, f"{agente_label}: {respuesta}", telefono=telefono, group_override=_tg_group)

        # ── Crear PRUEBA + link wa.me DESPUÉS de que el padre completó el formulario ──
        _resp_lower_link = respuesta.lower()
        # Detectar: Ivan responde al formulario completo del padre.
        # Condiciones: (1) Ivan dice "los esperamos" o "esperamos el" o "listo"
        #              (2) hay "reserva confirmada" en historial
        #              (3) el PADRE (no Ivan) mandó datos en su ÚLTIMO mensaje (nombre/fecha)
        #              (4) Ivan NO está pidiendo datos en esta respuesta (no dice "pasame" ni "📋")
        #              (5) no se creó ya
        _padre_mando_datos = len(texto) > 10 and ("/" in texto or any(c.isdigit() for c in texto))
        _ivan_no_pide_datos = "pasame" not in _resp_lower_link and "📋" not in respuesta
        # Guard: solo crear PRUEBA FENIX si el lead YA pagó
        _pago_confirmado_cierre = any(
            "pago confirmado" in m.get("content", "").lower()
            for m in historial if m.get("role") == "assistant"
        )
        _es_cierre_formulario = (
            agent_actual == "ivan"
            and ("los esperamos" in _resp_lower_link or "esperamos el" in _resp_lower_link or "listo" in _resp_lower_link)
            and _ivan_no_pide_datos
            and _pago_confirmado_cierre
            and any("reserva confirmada" in m.get("content", "").lower() for m in historial if m.get("role") == "assistant")
            and telefono not in _prueba_creada
        )
        if _es_cierre_formulario:
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
                for _m_res in reversed(historial_completo):
                    if _m_res.get("role") == "assistant" and "reserva confirmada" in _m_res.get("content", "").lower():
                        _match_fecha = re.search(r"s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})", _m_res["content"].lower())
                        if _match_fecha:
                            _fecha_res = _match_fecha.group(1)
                            _hora_res = _match_fecha.group(2)
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

        # ── Enviar afiche de horarios si el padre pregunta frecuencia/días ──
        if (agent_actual == "ivan"
                and telefono not in _afiche_horarios_enviado
                and _padre_pregunta_horarios(texto)):
            _afiche_horarios_enviado.add(telefono)
            await _enviar_afiche_horarios(telefono, topic_id, _tg_group)

        # ── Enviar afiche de precios cuando Ivan dice "te paso un afiche" o padre muestra interés post-diagnóstico ──
        _ivan_dice_afiche = (
            agent_actual == "ivan"
            and "te paso un afiche" in respuesta.lower()
        )
        _interes_post_diag = (
            agent_actual == "ivan"
            and _diagnostico_ya_enviado(historial)
            and _padre_muestra_interes(texto)
        )
        if telefono not in _afiche_enviado and (_ivan_dice_afiche or _interes_post_diag):
            _afiche_enviado.add(telefono)
            await _enviar_afiche_y_followup(telefono, topic_id, _tg_group)

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
                    f"Preguntá si sigue interesado en la clase de prueba para {nombre_hijo or 'su hijo/a'}. "
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
            f"¿Te gustaría agendar una clase de prueba para {nombre_hijo}?\n\n"
            "Te puedo reservar un sábado por acá, o si preferís te llamo un rato "
            "así te explico todo 😊"
        )
    else:
        # Sin nombre del hijo → CTA genérico sin preguntar nombre de nuevo
        return (
            "¿Te gustaría agendar una clase de prueba?\n\n"
            "Te puedo reservar un sábado por acá, o si preferís te llamo "
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
            "🏷️ Clase de prueba: 90.000 Gs (se descuenta si te inscribís)\n\n"
            "📅 *PLAN MENSUAL Todos los sábados:* 350.000/mes + matrícula 200.000 (incluye camisilla)\n\n"
            "🔥 *PROMO TRIMESTRAL — (40% OFF) 🔥*\n\n"
            "📅 *Todos los sábados:* 690.000 + matrícula 140.000\n"
            "   💰 Total: 830.000 Gs\n"
            "   ➡️ Ahorrás 420.000 Gs (40% OFF) 🔥\n\n"
            "¿Te gustaría reservar una clase de prueba? 😊"
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
                f"Tu clase de prueba es GRATIS 🎉 (cortesía referidos FENIX Kids)\n\n"
                f"Te confirmo el horario en breve, muchas gracias {nombre_padre} 🤝"
            )
        else:
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
