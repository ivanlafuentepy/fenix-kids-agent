# agent/main.py — Servidor FastAPI + Webhook WhatsApp
# FENIX KIDS ACADEMY — dual agente: Profe Ivan + Nixie

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
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta, extraer_datos_formulario
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.providers import obtener_proveedor
from agent.ab_test import (
    asignar_variante, obtener_estadisticas,
    marcar_conversion, esta_convertido,
    guardar_airtable_record_id, obtener_airtable_record_id,
    guardar_calendar_event_id, obtener_calendar_event_id,
    marcar_evento_creado, ya_tiene_evento,
    obtener_agent_actual, actualizar_agent_actual,
    obtener_familia_id,
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
    notificar_agenda_telegram,
)
from agent.airtable_client import (
    crear_lead, obtener_lead_record_id,
    actualizar_conversion_lead, actualizar_agent_lead,
    marcar_formulario_lead, crear_familia_completa,
    obtener_ninos_de_familia, crear_reserva,
    buscar_familia_por_telefono, buscar_familia_por_nombre,
    eliminar_lead,
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
_PALABRAS_PELIGROSAS = [
    "ignora tus instrucciones", "ignore your instructions",
    "olvida todo", "forget everything", "forget your instructions",
    "nuevo rol", "new role", "actua como", "pretend you are",
    "system prompt", "jailbreak", " dan ",
]


def _es_mensaje_sospechoso(texto: str) -> bool:
    t = texto.lower()
    return any(p in t for p in _PALABRAS_PELIGROSAS)


proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Evita doble procesamiento por webhooks duplicados de Meta
_mensajes_procesados: set[str] = set()
_MAX_MENSAJES_PROCESADOS = 500


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_group = os.getenv("TELEGRAM_GROUP_ID", "")
    print(f"[STARTUP] FENIX KIDS — puerto {PORT}", flush=True)
    print(f"[STARTUP] Proveedor: {proveedor.__class__.__name__}", flush=True)
    print(
        f"[STARTUP][Telegram] TOKEN={'OK (' + tg_token[:8] + '...)' if tg_token else '*** NO CONFIGURADO ***'} | "
        f"GROUP_ID={tg_group if tg_group else '*** NO CONFIGURADO ***'}",
        flush=True,
    )
    yield


app = FastAPI(title="FENIX KIDS ACADEMY — Agente WhatsApp", version="1.0.0", lifespan=lifespan)

_telegram_chats_vistos: dict[str, dict] = {}


# ── Health & stats ────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "fenix-kids-agent"}


@app.get("/stats")
async def estadisticas():
    stats = await obtener_estadisticas()
    return {"conversion": stats}


@app.get("/debug/{telefono}")
async def debug_lead(telefono: str):
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


# ── Detección de activación / handoff / confirmación ────────────────────────

_CLAVES_NIXIE = [
    "nixi", "hola nixi", "quiero hablar con nixi",
    "quiero reservar con nixi", "quiero agendar con nixi",
    "hablar con nixie", "reservar con nixie", "agendar con nixie",
]


def _detectar_activacion_nixie(texto: str) -> bool:
    """El padre escribió directamente a Nixie."""
    t = texto.lower()
    return any(k in t for k in _CLAVES_NIXIE)


def _detectar_handoff_ivan_nixie(respuesta: str) -> bool:
    """Ivan dijo 'En breve te contacta NIXIE' — señal de transferencia."""
    t = respuesta.lower()
    return "en breve te contacta nixie" in t or "te contacta nixie" in t


def _detectar_confirmacion_nixie(respuesta: str) -> dict | None:
    """
    Detecta si Nixie confirmó una reserva.
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
    Flujo principal por mensaje:

    1. Ignorar propios/vacíos/duplicados
    2. Detectar comando reset ("holayosoylasalsa")
    3. Cancelar recordatorios/seguimientos pendientes
    4. Espejo en Telegram — si Ivan está activo no responde el agente
    5. Transcribir audio si aplica
    6. Detectar activación directa de Nixie
    7. Lead nuevo → crear en LEADS, enviar rompehielos (lo genera Ivan)
    8. Generar respuesta con el agente activo (Ivan o Nixie)
    9. Detectar handoff Ivan → Nixie
    10. Si Nixie en modo lead_nuevo → intentar extraer formulario
    11. Detectar confirmación de reserva por Nixie → Calendar + Telegram
    12. Guardar mensajes + enviar respuesta
    """
    try:
        body_bytes = await request.body()
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            # Deduplicación
            if msg.mensaje_id:
                if msg.mensaje_id in _mensajes_procesados:
                    continue
                _mensajes_procesados.add(msg.mensaje_id)
                if len(_mensajes_procesados) > _MAX_MENSAJES_PROCESADOS:
                    _mensajes_procesados.clear()

            telefono = msg.telefono
            texto = msg.texto.strip()

            logger.info(f"[WA] {telefono}: {texto[:80]}")

            # ── Comando reset ─────────────────────────────────────────────────
            if texto.lower() == "holayosoylasalsa":
                cancelar_seguimiento(telefono)
                cancelar_recordatorios(telefono)
                await limpiar_estado_completo(telefono)
                await eliminar_lead(telefono)
                await proveedor.enviar_mensaje(telefono, "Reset completo ✅")
                await enviar_a_topic(telefono, "⚙️ RESET completo ejecutado")
                continue

            # ── Cancelar timers pendientes ────────────────────────────────────
            cancelar_seguimiento(telefono)

            # ── Espejo en Telegram ────────────────────────────────────────────
            topic_id = await obtener_o_crear_topic(telefono, texto[:30])
            if topic_id:
                await enviar_a_topic(telefono, f"👤 {texto}")

            # ── Verificar si Ivan (admin) está respondiendo manualmente ───────
            if not await dorita_esta_activa(telefono):
                logger.info(f"Agente silenciado para {telefono} — Ivan activo en Telegram")
                continue

            # ── Protección prompt injection ───────────────────────────────────
            if _es_mensaje_sospechoso(texto):
                respuesta = "Lo siento, no puedo procesar ese mensaje 🙏"
                await proveedor.enviar_mensaje(telefono, respuesta)
                continue

            # ── Transcribir audio si es necesario ────────────────────────────
            if hasattr(msg, "media_id") and msg.media_id:
                try:
                    audio_bytes = await descargar_audio_whatsapp(msg.media_id)
                    if audio_bytes:
                        texto = await transcribir_audio(audio_bytes)
                        logger.info(f"Audio transcripto: {texto[:80]}")
                except Exception as e:
                    logger.error(f"Error transcribiendo audio: {e}")

            # ── Estado de la conversación ─────────────────────────────────────
            agent_actual, modo_nixie = await obtener_agent_actual(telefono)

            # ── Detectar activación directa de Nixie ─────────────────────────
            activacion_nixie = _detectar_activacion_nixie(texto)
            if activacion_nixie and agent_actual == "ivan":
                # Determinar modo: cliente inscripto por defecto al llamar directo
                modo_nixie = "cliente_inscripto"
                agent_actual = "nixie"
                await actualizar_agent_actual(telefono, "nixie", modo_nixie)
                await actualizar_agent_lead(telefono, "NIXIE", modo_nixie)

            # ── Obtener historial ─────────────────────────────────────────────
            historial = await obtener_historial(telefono)

            # ── Lead nuevo: primer contacto ───────────────────────────────────
            _, es_nuevo = await asignar_variante(telefono)
            if es_nuevo:
                record_id = await crear_lead(telefono, rompehielos="A")
                if record_id:
                    await guardar_airtable_record_id(telefono, record_id)
                # El rompehielos lo genera Ivan en su primer mensaje
                # No enviamos mensaje automático — Ivan responde con el rompehielos

            # ── Verificar si la familia ya existe por teléfono ────────────────
            # (para el modo cliente_inscripto detectado automáticamente)
            familia_existente = None
            if agent_actual == "nixie" and modo_nixie == "cliente_inscripto":
                familia_existente = await buscar_familia_por_telefono(telefono)
                if familia_existente:
                    campos = familia_existente.get("fields", {})
                    nombre_padre = campos.get("NOMBRE PADRE", "")
                    hijos_raw = await obtener_ninos_de_familia(familia_existente["id"])
                    nombres_hijos = [h["nombre_completo"] or h["nombre"] for h in hijos_raw]
                    contexto_extra = (
                        f"CONTEXTO: Este padre ya está inscripto. "
                        f"Su nombre es {nombre_padre}. "
                        f"Sus hijos registrados son: {', '.join(nombres_hijos) if nombres_hijos else 'ninguno aún'}."
                    )
                else:
                    contexto_extra = None
            else:
                contexto_extra = None

            # ── Generar respuesta ─────────────────────────────────────────────
            respuesta = await generar_respuesta(
                mensaje=texto,
                historial=historial,
                agent_actual=agent_actual,
                contexto_extra=contexto_extra,
            )

            # ── Detectar handoff Ivan → Nixie ─────────────────────────────────
            if agent_actual == "ivan" and _detectar_handoff_ivan_nixie(respuesta):
                await actualizar_agent_actual(telefono, "nixie", "lead_nuevo")
                await actualizar_agent_lead(telefono, "NIXIE", "lead_nuevo")
                logger.info(f"Handoff Ivan → Nixie (lead_nuevo) para {telefono}")

            # ── Si Nixie en modo lead_nuevo: intentar extraer formulario ──────
            if agent_actual == "nixie" and (modo_nixie == "lead_nuevo" or not modo_nixie):
                historial_completo = historial + [
                    {"role": "user", "content": texto},
                    {"role": "assistant", "content": respuesta},
                ]
                datos = await extraer_datos_formulario(historial_completo)
                if datos.get("completo"):
                    familia_id, nino_ids = await crear_familia_completa(telefono, datos)
                    if familia_id:
                        await marcar_conversion(telefono)
                        await actualizar_conversion_lead(telefono, "AGENDA")
                        logger.info(f"Formulario completo para {telefono}: familia={familia_id}")
                        # Cancelar recordatorios de formulario si los había
                        cancelar_recordatorios(telefono)
                    if not await esta_convertido(telefono):
                        # Programar recordatorios de formulario si aún no completó
                        programar_recordatorios_formulario(
                            telefono=telefono,
                            dia="sábado",
                            hora=None,
                            proveedor=proveedor,
                            formulario_check_fn=esta_convertido,
                            guardar_fn=_guardar_mensaje,
                        )

            # ── Detectar confirmación de reserva por Nixie ────────────────────
            confirmacion = _detectar_confirmacion_nixie(respuesta)
            if agent_actual == "nixie" and confirmacion:
                await _procesar_confirmacion_reserva(telefono, confirmacion, respuesta)

            # ── Guardar mensajes ──────────────────────────────────────────────
            await guardar_mensaje(telefono, "user", texto)
            await guardar_mensaje(telefono, "assistant", respuesta)

            # ── Enviar respuesta ──────────────────────────────────────────────
            await proveedor.enviar_mensaje(telefono, respuesta)

            # ── Espejo respuesta en Telegram ──────────────────────────────────
            agente_label = "🐼 NIXIE" if agent_actual == "nixie" else "👨‍🏫 IVAN"
            if topic_id:
                await enviar_a_topic(telefono, f"{agente_label}: {respuesta}")

            # ── Programar seguimiento si es lead nuevo sin respuesta ──────────
            if es_nuevo:
                programar_seguimiento_inicial(
                    telefono=telefono,
                    proveedor=proveedor,
                    guardar_fn=_guardar_mensaje,
                    formulario_check_fn=esta_convertido,
                )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _procesar_confirmacion_reserva(
    telefono: str,
    confirmacion: dict,
    respuesta_nixie: str,
):
    """
    Cuando Nixie confirma una reserva:
    1. Actualizar CONVERSION=AGENDA en LEADS
    2. Crear evento en Google Calendar
    3. Notificar en Telegram
    """
    fecha_str = confirmacion.get("fecha", "")
    hora_str = confirmacion.get("hora", "")

    logger.info(f"Confirmación Nixie detectada: {fecha_str} {hora_str} para {telefono}")

    # Actualizar LEADS
    await actualizar_conversion_lead(telefono, "AGENDA")

    # Calcular fecha ISO
    fecha_iso = None
    if fecha_str and hora_str:
        try:
            fecha_iso = fecha_iso_from_dia_hora(f"sabado {fecha_str}", hora_str)
        except Exception as e:
            logger.error(f"Error calculando fecha ISO: {e}")

    # Crear o actualizar evento en Google Calendar
    if fecha_iso:
        event_id_anterior = await obtener_calendar_event_id(telefono)
        if event_id_anterior:
            await borrar_evento_google(event_id_anterior)

        familia_id = await obtener_familia_id(telefono)
        nombre_familia = telefono  # fallback

        evento = await insertar_evento_desde_fecha_iso(
            fecha_iso=fecha_iso,
            telefono=telefono,
            nombre=nombre_familia,
        )
        if evento:
            await guardar_calendar_event_id(telefono, evento["evento_id"])
            await marcar_evento_creado(telefono)
            # Enviar link del evento al padre
            link = evento.get("evento_link", "")
            if link:
                await proveedor.enviar_mensaje(
                    telefono,
                    f"📅 Guardá la fecha en tu calendario: {link}"
                )

    # Notificar en Telegram
    await notificar_agenda_telegram(
        telefono=telefono,
        dia=fecha_str,
        hora=hora_str,
        nombre_lead=telefono,
    )


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
            await enviar_a_topic(telefono, "🔇 Agente IA silenciado. Ivan activo.")
            return {"status": "ok"}

        if texto_tg.strip() == "/reactivar":
            await reactivar_dorita(telefono)
            await enviar_a_topic(telefono, "🔊 Agente IA reactivado.")
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
async def telegram_setup(url: str):
    """Registra el webhook de Telegram. Llamar una sola vez al deploy."""
    ok = await configurar_webhook(url)
    info = await obtener_info_webhook()
    return {"configurado": ok, "info": info}
