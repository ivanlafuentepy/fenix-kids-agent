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
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
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
    obtener_estado_flags, actualizar_estado_flags,
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
    group_id_para_agente, grupo_telegram_para,
)
from agent.meta_capi import enviar_evento_agenda, enviar_evento_pago
from agent.monitor import (
    monitor_conversaciones_loop, monitor_salud_loop,
    registrar_error_webhook, background_tasks as _monitor_bg_tasks,
)
from agent.tools.detectores import (
    padre_pregunta_precios, padre_pregunta_hermanos, padre_pregunta_horarios,
    padre_pregunta_ubicacion, padre_pregunta_duracion, padre_pregunta_que_llevar,
    padre_pregunta_devolucion, padre_pregunta_efectivo, padre_dice_ya_transfiri,
    padre_pregunta_alias,
)
from agent.tool_definitions import TOOLS_IVAN, TOOLS_AURORA
from agent.tool_executor import ejecutar_tool

# Feature flag: Tool Use (Fase 3 migración)
_USE_TOOL_USE = os.getenv("USE_TOOL_USE", "false").lower() == "true"
from agent.pagos import (
    es_posible_comprobante, detectar_tipo_pago,
    registrar_pago_pendiente, tiene_pago_pendiente,
    obtener_pago_pendiente, confirmar_pago, rechazar_pago,
    formatear_monto, PRECIOS, CI_BANCARIO,
)
from agent.airtable_client import (
    crear_lead, obtener_lead_record_id,
    actualizar_conversion_lead, actualizar_agent_lead,
    marcar_formulario_lead, crear_familia_completa, crear_familia, crear_nino,
    obtener_ninos_de_familia, obtener_tutores_de_familia, crear_reserva,
    buscar_familia_por_telefono, buscar_familia_por_nombre, familia_es_activa,
    es_cliente_activo_por_telefono, obtener_grupo_familiar, buscar_tutor_por_telefono,
    eliminar_lead, eliminar_todo_de_telefono,
    obtener_o_crear_horario,
    actualizar_datos_lead, actualizar_diagnostico_lead,
    actualizar_reserva_lead, marcar_control_datos,
    obtener_ninos_por_horario, formatear_lista_ninos,
    obtener_horarios_disponibles, obtener_redes,
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

# ── Seguridad (extraído a agent/seguridad.py) ──
from agent.seguridad import _es_mensaje_sospechoso, _es_spam_o_scam, detectar_diagnostico


proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# ── Concurrencia (extraído a agent/concurrencia.py) ──
from agent.concurrencia import _obtener_lock, _check_rate_limit, _fire_and_forget, _RATE_LIMIT_MAX, _RATE_LIMIT_WINDOW

# ── Resúmenes admin (extraído a agent/resumenes.py) ──
from agent.resumenes import (
    _parsear_filtro_fecha, _generar_slug, _fecha_py,
    _generar_resumen_reservas, _generar_resumen_flias, _generar_resumen_telegram,
    _generar_lista_asistencia, _procesar_respuesta_asistencia,
    _agregar_presentes_por_nombres, _marcar_presente_por_nombre,
    _enviar_asistencia_automatica,
    _generar_resumen_asistencia,
    _generar_resumen_seguimiento, _generar_resumen_followup,
    _generar_resumen_anuncios,
    _asistencia_pendiente,
)

# ── Loops y funciones de background (extraídos a agent/loops.py) ──
from agent.loops import (
    _delay_humano,
    _programar_recordatorio_clase, _programar_llamada,
    _enviar_recordatorio, _recordatorios_loop,
    _resumen_diario_loop, _asistencia_auto_loop,
    _horarios_mensuales_loop,
    _keepalive_ventana_admin_loop,
    _envio_facturas_fenix_loop,
    _confirmacion_sabado_loop,
    _procesar_pendientes_noche,
    _followup_loop, _ejecutar_followup,
    _resetear_seguimiento, _incrementar_seguimiento,
)


# Guard: formulario ya procesado (prueba_creada) → persistido en estado_json (DB)

# Admin en modo padre (flujo normal): si no está acá, admin queda en modo secre (solo comandos)
_admin_modo_padre: set[str] = set()

# ── Inscripción de familia (extraído a agent/inscripcion.py) ──
from agent.inscripcion import (
    _iniciar_inscripcion, _procesar_respuesta_inscripcion,
    _inscripcion_pendiente,
)

# ── Cargar niño: alta directa a FAMILIAS via Meta Flow (agent/cargar_nino.py) ──
from agent.cargar_nino import (
    enviar_formulario_cargar_nino, procesar_formulario_cargar_nino,
)

# ── Formulario de reserva del lead via Meta Flow (agent/formulario_reserva.py) ──
from agent.formulario_reserva import procesar_formulario_reserva

# ── Fotos y reconocimiento facial (extraído a agent/fotos.py) ──
from agent.fotos import (
    _iniciar_modo_fotos, _acumular_foto, _finalizar_fotos, _confirmar_fotos,
    _procesar_registro_cara, _procesar_boton_seguimiento,
    _fotos_sesion, _cara_pendiente, _cara_candidatos,
    _cara_record_preseleccionado, _cara_media_pendiente,
)

# ── Afiches y follow-up (extraído a agent/afiches.py) ──
from agent.afiches import (
    _enviar_afiche_horarios, _armar_mensaje_agenda_post_pago,
    _armar_followup_afiche, _enviar_afiche_hermanos_y_followup,
    _enviar_afiche_y_followup,
)

# ── Menú de botones para leads nuevos (agent/lead_menu.py) ──
from agent.lead_menu import procesar_menu_lead
# ── Menú de botones para familias inscriptas (agent/alumno_menu.py) ──
from agent.alumno_menu import procesar_menu_inscripto

# ── Promo Madre (DESACTIVADA 2026-05-16 — venció 15/5 20h) ──
_PROMO_MADRE_ACTIVA = False  # cambiar a True para reactivar
_esperando_pago_promo_madre: set[str] = set()       # leads esperando comprobante
_leads_promo_madre_enviada: set[str] = set()         # leads que recibieron plantilla
_esperando_formulario_promo: set[str] = set()        # leads que enviaron comprobante, esperan datos
_promo_masiva_estado: dict = {"activo": False, "total": 0, "enviados": 0, "errores": 0, "ultimo_enviado": ""}


# Números que no reciben delay de análisis (admin/pruebas)
_PHONES_SIN_DELAY = {os.getenv("ADMIN_PHONE", "")}

import re

# (eliminado: _normalizar_numeros_lead_viejo, _contar_numeros_rompehielos, _delay_por_numeros
#  — ya no se usa menú de dolor 1-15/1-10)


import json
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

_TZ_PY = ZoneInfo("America/Asuncion")



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

    # Follow-up masivos fotos/video: ONE-SHOTs de mayo 2026, YA ejecutados.
    # Se lanzaban en cada boot y solo la fecha vencida los frenaba — retirados
    # del lifespan (las funciones quedan en loops.py como patrón reutilizable).

    # Resumen diario 8:00 AM PY: anuncios + reservas (reemplaza keepalive)
    _keepalive_task = _fire_and_forget(_resumen_diario_loop())

    # Contenido social: polling CONTENIDO FENIX + calendario diario
    from agent.contenido_social import iniciar_contenido_social
    iniciar_contenido_social(proveedor)

    # Asistencia automática: enviar lista al terminar cada turno (sábados)
    _asistencia_task = _fire_and_forget(_asistencia_auto_loop())

    # Horarios mensuales: auto-crea sábados × turnos del mes siguiente (último día del mes 9AM)
    _horarios_task = _fire_and_forget(_horarios_mensuales_loop())

    # Monitor de producción (Capa 1): conversaciones sin respuesta + salud del sistema
    _monitor_conv_task = _fire_and_forget(monitor_conversaciones_loop())
    _monitor_salud_task = _fire_and_forget(monitor_salud_loop())

    # Keep-alive ventana 24h: todos los días a las 9 AM PY manda botón "Sí" al admin
    # para que las alertas urgentes le lleguen por WhatsApp (Meta solo deja texto libre <24h)
    _keepalive_ventana_task = _fire_and_forget(_keepalive_ventana_admin_loop())

    # Facturas Fenix: reparte a la familia el PDF que emitió el robot facturador
    _facturas_task = _fire_and_forget(_envio_facturas_fenix_loop())

    # Confirmación sábado: jueves 9AM manda plantilla a familias al día (al que paga).
    # APAGADO por default — requiere CONFIRMACION_SABADO_ACTIVA=true para enviar.
    _conf_sabado_task = _fire_and_forget(_confirmacion_sabado_loop())

    # Registrar todos los background tasks para que el monitor los vigile
    _monitor_bg_tasks.update({
        "recordatorios": _recordatorios_task,
        "noche": _noche_task,
        "keepalive": _keepalive_task,
        "asistencia": _asistencia_task,
        "horarios_mensuales": _horarios_task,
        "monitor_conv": _monitor_conv_task,
        "monitor_salud": _monitor_salud_task,
        "keepalive_ventana": _keepalive_ventana_task,
        "facturas_fenix": _facturas_task,
        # Estaba lanzado pero SIN registrar: si moría, nadie alertaba
        # (auditoría 2026-07-12, A20)
        "confirmacion_sabado": _conf_sabado_task,
    })

    print(f"[STARTUP] FENIX KIDS — puerto {PORT}", flush=True)
    print(f"[STARTUP] Proveedor: {proveedor.__class__.__name__}", flush=True)
    print(
        f"[STARTUP][Telegram] TOKEN={'OK (' + tg_token[:8] + '...)' if tg_token else '*** NO CONFIGURADO ***'} | "
        f"GROUP_ID={tg_group if tg_group else '*** NO CONFIGURADO ***'}",
        flush=True,
    )
    print("[STARTUP] Monitor de producción: conversaciones + salud activos", flush=True)
    yield
    # Cancelar TODOS los tasks registrados (antes solo se cancelaban 5 de ~10)
    for _t in _monitor_bg_tasks.values():
        _t.cancel()


app = FastAPI(title="FENIX KIDS ACADEMY — Agente WhatsApp", version="1.0.0", lifespan=lifespan)

# Router aislado /hq para el Centro de Comando (enviar, media, silencio, asistencia)
from agent.hq_endpoints import router as hq_router
app.include_router(hq_router)

# Router aislado /juego para Mundo Fenix (eventos de tótem/TV/profe/circuito NFC)
from agent.juego_endpoints import router as juego_router
app.include_router(juego_router)

# Servir archivos estaticos (catalogo de videos, afiches, etc.)
_static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
app.mount("/static", StaticFiles(directory=_static_dir, html=True), name="static")

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


async def _require_admin_o_key(
    x_admin_key: str | None = Header(default=None, alias="X-ADMIN-KEY"),
    k: str = "",
):
    """Como _require_admin pero acepta también ?k= (para abrir en el navegador).

    Protege los /api/* que exponen datos de niños: dejaron de ser públicos
    (auditoría 2026-07-12 — la web pública ya no los consume desde que se
    quitaron las páginas con datos de menores del sitio).
    """
    import hmac as _hmac
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY no configurada en el servidor")
    candidato = x_admin_key or k
    if not candidato or not _hmac.compare_digest(candidato, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# ── Health & stats ────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "fenix-kids-agent"}


# ── QR Check-in ──────────────────────────────────────────────────────────────

def _render_checkin_html(nombre: str, edad: str, hora: str, foto_url: str, estado: str, checkin_hora: str = "", confirmar_action: str = "") -> str:
    """Genera HTML de ficha/credencial del niño para la página de check-in QR.

    estado "confirmar": muestra un botón que POSTea a `confirmar_action` —
    el GET ya no marca PRESENTE (un prefetch de navegador/bot marcaba
    asistencia solo, auditoría 2026-07-12)."""
    if estado == "ok":
        badge_color, badge_icon, badge_text = "#27ae60", "✅", "Check-in confirmado"
        if checkin_hora:
            badge_text += f" — {checkin_hora}"
    elif estado == "ya_presente":
        badge_color, badge_icon, badge_text = "#f39c12", "⚠️", "Ya registrado"
    elif estado == "confirmar":
        badge_color, badge_icon, badge_text = "#2980b9", "👋", "Confirmar llegada"
    else:
        badge_color, badge_icon, badge_text = "#e74c3c", "❌", "Reserva no encontrada"

    foto_html = ""
    if foto_url:
        foto_html = f'<img src="{foto_url}" style="width:120px;height:120px;border-radius:50%;object-fit:cover;border:4px solid {badge_color};margin-bottom:16px" />'
    else:
        iniciales = "".join(p[0] for p in nombre.split()[:2] if p).upper() or "?"
        foto_html = f'<div style="width:120px;height:120px;border-radius:50%;background:{badge_color};display:flex;align-items:center;justify-content:center;margin:0 auto 16px;font-size:48px;color:white;font-weight:bold;border:4px solid {badge_color}">{iniciales}</div>'

    detalles = []
    if edad:
        detalles.append(f'<span style="background:#f0f0f0;padding:6px 14px;border-radius:20px;font-size:14px">🎂 {edad}</span>')
    if hora:
        detalles.append(f'<span style="background:#f0f0f0;padding:6px 14px;border-radius:20px;font-size:14px">🕐 {hora}h</span>')
    detalles_html = f'<div style="display:flex;gap:8px;justify-content:center;margin:12px 0">{"".join(detalles)}</div>' if detalles else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fenix Kids — {nombre}</title>
</head>
<body style="margin:0;padding:20px;min-height:100vh;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#e8f5e9 0%,#fff8e1 100%);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="background:white;border-radius:20px;padding:32px 24px;max-width:360px;width:100%;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,0.12)">
  <div style="font-size:28px;margin-bottom:20px">🌳</div>
  <div style="font-size:12px;text-transform:uppercase;letter-spacing:2px;color:#888;margin-bottom:20px">Fenix Kids Academy</div>
  {foto_html}
  <h1 style="margin:0 0 4px;font-size:24px;color:#333">{nombre}</h1>
  {detalles_html}
  {(f'<form method="post" action="{confirmar_action}" style="margin:20px 0"><button type="submit" style="width:100%;border:none;padding:16px 20px;background:{badge_color};color:white;border-radius:12px;font-size:18px;font-weight:600;cursor:pointer">{badge_icon} {badge_text}</button></form>' if estado == "confirmar" and confirmar_action else f'<div style="margin:20px 0;padding:12px 20px;background:{badge_color};color:white;border-radius:12px;font-size:18px;font-weight:600">{badge_icon} {badge_text}</div>')}
  <p style="color:#aaa;font-size:12px;margin:16px 0 0">Maestras Paraguayas 2056 — Asuncion</p>
</div>
</body>
</html>"""


async def _buscar_ficha_checkin(record_id: str):
    """Busca la RESERVA del QR y arma la ficha (2.D: PRUEBA ya no se consulta).

    Retorna (tabla, fields, nombre, edad, hora, foto_url) o None si no existe.
    Compartido por el GET (mostrar) y el POST (confirmar) de /checkin/{record_id}.
    """
    from agent.airtable_client import _get_records, _RESERVAS, _NINOS

    formula = f"RECORD_ID()='{record_id}'"
    nombre = "Alumno"
    edad = ""
    hora = ""
    foto_url = ""

    # Buscar en RESERVAS FENIX (inscriptos)
    records = await _get_records(_RESERVAS, formula=formula, max_records=1)
    tabla = _RESERVAS
    if records:
        fields = records[0].get("fields", {})
        nombre_list = fields.get("NOMBRE COMPLETO", [])
        nombre = nombre_list[0] if nombre_list else "Alumno"
        hora_list = fields.get("HORA", [])
        hora = hora_list[0] if hora_list else ""
        # Buscar foto y edad del niño vinculado
        nino_ids = fields.get("NINO", [])
        if nino_ids:
            try:
                nino_recs = await _get_records(_NINOS, formula=f"RECORD_ID()='{nino_ids[0]}'", max_records=1)
                if nino_recs:
                    nf = nino_recs[0].get("fields", {})
                    fotos = nf.get("FOTO", [])
                    if fotos and isinstance(fotos, list):
                        foto_url = fotos[0].get("url", "")
                    fn = nf.get("FECHA NACIMIENTO", "")
                    if fn:
                        from datetime import date
                        nac = date.fromisoformat(fn)
                        hoy = date.today()
                        edad = f"{hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))} años"
            except Exception:
                pass
    if not records:
        return None
    return tabla, fields, nombre, edad, hora, foto_url


@app.get("/checkin/{record_id}")
async def checkin(record_id: str):
    """Ficha del niño al escanear QR. Ya NO marca presente en el GET (un
    prefetch de navegador/bot marcaba asistencia solo — auditoría 2026-07-12):
    muestra un botón que confirma con POST."""
    ficha = await _buscar_ficha_checkin(record_id)
    if not ficha:
        return HTMLResponse(_render_checkin_html("", "", "", "", "no_encontrado"), status_code=404)
    tabla, fields, nombre, edad, hora, foto_url = ficha

    if fields.get("PRESENTE"):
        return HTMLResponse(_render_checkin_html(nombre, edad, hora, foto_url, "ya_presente"))
    return HTMLResponse(_render_checkin_html(
        nombre, edad, hora, foto_url, "confirmar",
        confirmar_action=f"/checkin/{record_id}/confirmar",
    ))


@app.post("/checkin/{record_id}/confirmar")
async def checkin_confirmar(record_id: str):
    """Marca PRESENTE (patch + fila en ASISTENCIA) al tocar el botón de la ficha."""
    from agent.airtable_client import _patch, _RESERVAS

    ficha = await _buscar_ficha_checkin(record_id)
    if not ficha:
        return HTMLResponse(_render_checkin_html("", "", "", "", "no_encontrado"), status_code=404)
    tabla, fields, nombre, edad, hora, foto_url = ficha

    if fields.get("PRESENTE"):
        return HTMLResponse(_render_checkin_html(nombre, edad, hora, foto_url, "ya_presente"))

    from datetime import datetime
    from zoneinfo import ZoneInfo
    ahora = datetime.now(ZoneInfo("America/Asuncion"))
    await _patch(tabla, record_id, {
        "PRESENTE": True,
        "HORA_CHECKIN": ahora.isoformat(),
    })

    # Fila en ASISTENCIA FENIX (modelo "una fila por presente") — antes solo
    # la creaban los check-ins por familia/prueba (migración 2.B). Best-effort.
    if tabla == _RESERVAS:
        try:
            from agent.airtable_client import crear_asistencia
            _nino_id_ci = (fields.get("NINO") or [""])[0]
            await crear_asistencia(
                nombre=nombre, fecha_iso=ahora.date().isoformat(),
                hora_checkin_iso=ahora.isoformat(), nino_id=_nino_id_ci,
                reserva_id=record_id, turno=hora, metodo="QR",
            )
        except Exception as _e_asis_ci:
            logger.warning(f"[CHECKIN] Asistencia no creada para {record_id}: {_e_asis_ci}")

    return HTMLResponse(_render_checkin_html(nombre, edad, hora, foto_url, "ok", ahora.strftime("%H:%M")))


@app.get("/fu/{nombre_archivo}")
async def servir_followup(nombre_archivo: str, key: str = ""):
    """Sirve páginas HTML estáticas de follow-up (protegido con ?key=ADMIN_API_KEY)."""
    import os
    from fastapi.responses import HTMLResponse
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if not key or key != admin_key:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    ruta = os.path.join("static", f"{nombre_archivo}.html")
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Página no encontrada")
    with open(ruta, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/reservas")
async def api_reservas(fecha: str = "", _: bool = Depends(_require_admin_o_key)):
    """Devuelve reservas de un sábado agrupadas por turno. ?fecha=2026-05-24 o próximo sábado.

    Protegido (X-ADMIN-KEY o ?k=): expone niños por turno + teléfono del padre."""
    from datetime import date, timedelta, datetime, timezone
    from agent.airtable_client import obtener_ninos_por_horario
    import unicodedata

    _PY_TZ = timezone(timedelta(hours=-3))
    hoy = datetime.now(_PY_TZ).date()

    if fecha:
        try:
            sabado = date.fromisoformat(fecha)
        except ValueError:
            sabado = None
    else:
        sabado = None

    if not sabado:
        dias_hasta_sabado = (5 - hoy.weekday()) % 7
        if dias_hasta_sabado == 0 and hoy.weekday() != 5:
            dias_hasta_sabado = 7
        sabado = hoy + timedelta(days=dias_hasta_sabado)

    fecha_iso = sabado.isoformat()
    turnos = ["9:30", "11:00", "15:30"]

    def _slug(nombre, apellido):
        raw = f"{nombre} {apellido}".lower().strip()
        norm = unicodedata.normalize("NFD", raw)
        norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
        return re.sub(r"[^a-z0-9]+", "-", norm).strip("-")

    resultado = {"fecha": fecha_iso, "fecha_label": f"Sábado {sabado.day}/{sabado.month}", "turnos": []}

    # Cargar niños + tutores para fotos, nombres y teléfonos (niño-eje:
    # PADRE/MADRE del niño → TUTORES; FAMILIAS ya no se consulta)
    from agent.airtable_client import _get_records, _NINOS, _TUTORES
    _ninos_recs = await _get_records(_NINOS, max_records=1000)
    _ninos_map = {}
    for _nr in _ninos_recs:
        _nf = _nr.get("fields", {})
        _ninos_map[_nr["id"]] = {
            "foto": (_nf.get("FOTO") or [{}])[0].get("url", "") if _nf.get("FOTO") else "",
            "tutor_ids": (_nf.get("PADRE") or []) + (_nf.get("MADRE") or []),
        }
    _tut_recs = await _get_records(_TUTORES, max_records=1000)
    _tut_map = {}
    for _tr in _tut_recs:
        _tf = _tr.get("fields", {})
        _tut_map[_tr["id"]] = {
            "nombre": _tf.get("NOMBRE", ""),
            "cell": _tf.get("CELL", ""),
        }

    # Fuente única: RESERVAS FENIX — inscriptos y pruebas split por es_prueba
    # (migración 2.B: PRUEBA FENIX ya no se consulta; los datos del niño de
    # prueba salen de NIÑOS y su familia, como los inscriptos).
    for hora in turnos:
        ninos_hora = await obtener_ninos_por_horario(fecha_iso, hora)
        turno_data = {"hora": hora, "aurora": [], "prueba": []}
        for n in ninos_hora:
            _nino_extra = _ninos_map.get(n.get("id", ""), {})
            _tuts_n = [_tut_map.get(tid, {}) for tid in _nino_extra.get("tutor_ids", [])]
            _destino = "prueba" if n.get("es_prueba") else "aurora"
            turno_data[_destino].append({
                "nombre": n.get("nombre", ""),
                "apellido": n.get("apellido", ""),
                "apodo": n.get("apodo", ""),
                "edad": n.get("edad", ""),
                "slug": _slug(n.get("nombre", ""), n.get("apellido", "")),
                "foto": _nino_extra.get("foto", ""),
                "padre": next((t["nombre"] for t in _tuts_n if t.get("nombre")), ""),
                "cell": next((t["cell"] for t in _tuts_n if t.get("cell")), ""),
            })
        resultado["turnos"].append(turno_data)

    from fastapi.responses import JSONResponse
    return JSONResponse(content=resultado, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/stats")
async def estadisticas(_: bool = Depends(_require_admin)):
    stats = await obtener_estadisticas()
    return {"conversion": stats}


# ── API fichas de alumnos (protegida — datos de menores) ─────────────────────

@app.get("/api/alumnos")
async def api_alumnos(_: bool = Depends(_require_admin_o_key)):
    """Devuelve todos los alumnos (NIÑOS FENIX). Protegido: X-ADMIN-KEY o ?k=."""
    from agent.airtable_client import _get_records, _NINOS, _TUTORES
    from datetime import date
    import unicodedata
    import re

    records = await _get_records(_NINOS, max_records=1000)

    # Cargar tutores para nombres y teléfonos (niño-eje: PADRE/MADRE del niño;
    # FAMILIAS ya no se consulta — el estado sale de NIÑOS.ESTADO)
    tutores_cache = {}
    tutores_recs = await _get_records(_TUTORES, max_records=1000)
    for tut in tutores_recs:
        tf = tut.get("fields", {})
        tutores_cache[tut["id"]] = {
            "nombre": tf.get("NOMBRE", ""),
            "cell": tf.get("CELL", ""),
        }

    alumnos = []
    for rec in records:
        f = rec.get("fields", {})
        nombre = f.get("NOMBRE", "").strip()
        apellido = f.get("APELLIDO", "").strip()
        if not nombre:
            continue
        # Slug para URL
        _slug_raw = f"{nombre} {apellido}".lower().strip()
        _slug_norm = unicodedata.normalize("NFD", _slug_raw)
        _slug_norm = "".join(c for c in _slug_norm if unicodedata.category(c) != "Mn")
        slug = re.sub(r"[^a-z0-9]+", "-", _slug_norm).strip("-")
        # Edad
        fn = f.get("FECHA NACIMIENTO", "")
        edad = None
        if fn:
            try:
                nacimiento = date.fromisoformat(fn)
                hoy = date.today()
                edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
            except ValueError:
                pass
        # Foto
        foto_url = ""
        fotos_raw = f.get("FOTO", [])
        if fotos_raw and isinstance(fotos_raw, list):
            foto_url = fotos_raw[0].get("url", "")
        # Reservas count
        reservas = f.get("RESERVAS FENIX", [])
        n_reservas = len(reservas) if isinstance(reservas, list) else 0
        # Tutores del niño (niño-eje): PADRE/MADRE son links a TUTORES
        _padre_t = tutores_cache.get((f.get("PADRE") or [None])[0] or "", {})
        _madre_t = tutores_cache.get((f.get("MADRE") or [None])[0] or "", {})

        # es_prueba: el ESTADO vive en el niño (migración niño-eje — antes se
        # miraba el ESTADO PLAN de su familia)
        _es_prueba_al = (f.get("ESTADO") or "") == "A PRUEBA"
        alumnos.append({
            "id": rec["id"],
            "nombre": nombre,
            "apellido": apellido,
            "apodo": f.get("APODO", ""),
            "slug": slug,
            "edad": edad,
            "sexo": f.get("SEXO", ""),
            "foto": foto_url,
            "reservas": n_reservas,
            "fecha_nacimiento": fn,
            "padre": _padre_t.get("nombre", ""),
            "madre": _madre_t.get("nombre", ""),
            "cell_padre": _padre_t.get("cell", ""),
            "cell_madre": _madre_t.get("cell", ""),
            **({"es_prueba": True} if _es_prueba_al else {}),
        })

    # CORS header para Cloudflare Pages
    from fastapi.responses import JSONResponse
    return JSONResponse(content=alumnos, headers={"Access-Control-Allow-Origin": "*"})


@app.get("/api/alumno/{slug}")
async def api_alumno_detalle(slug: str, _: bool = Depends(_require_admin_o_key)):
    """Devuelve detalle de un alumno por slug (nombre-apellido). Protegido: X-ADMIN-KEY o ?k=."""
    from agent.airtable_client import _get_records, _NINOS
    from datetime import date
    import unicodedata
    import re

    # Buscar en NIÑOS FENIX
    records = await _get_records(_NINOS, max_records=1000)
    alumno = None
    for rec in records:
        f = rec.get("fields", {})
        nombre = f.get("NOMBRE", "").strip()
        apellido = f.get("APELLIDO", "").strip()
        if not nombre:
            continue
        _slug_raw = f"{nombre} {apellido}".lower().strip()
        _slug_norm = unicodedata.normalize("NFD", _slug_raw)
        _slug_norm = "".join(c for c in _slug_norm if unicodedata.category(c) != "Mn")
        _s = re.sub(r"[^a-z0-9]+", "-", _slug_norm).strip("-")
        if _s == slug:
            fn = f.get("FECHA NACIMIENTO", "")
            edad = None
            if fn:
                try:
                    nacimiento = date.fromisoformat(fn)
                    hoy = date.today()
                    edad = hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
                except ValueError:
                    pass
            foto_url = ""
            fotos_raw = f.get("FOTO", [])
            if fotos_raw and isinstance(fotos_raw, list):
                foto_url = fotos_raw[0].get("url", "")
            alumno = {
                "id": rec["id"],
                "nombre": nombre,
                "apellido": apellido,
                "apodo": f.get("APODO", ""),
                "slug": _s,
                "edad": edad,
                "sexo": f.get("SEXO", ""),
                "foto": foto_url,
                "fecha_nacimiento": fn,
                "reservas_ids": f.get("RESERVAS FENIX", []),
            }
            break

    if not alumno:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    from fastapi.responses import JSONResponse
    return JSONResponse(content=alumno, headers={"Access-Control-Allow-Origin": "*"})


# ── Promo Madre: envío masivo + progreso ───────────────────────────────────────

@app.get("/debug/estado-promo-masiva")
async def debug_estado_promo_masiva(_: bool = Depends(_require_admin)):
    """Progreso del envío masivo en curso."""
    return _promo_masiva_estado


@app.get("/debug/parar-promo-masiva")
async def debug_parar_promo_masiva(_: bool = Depends(_require_admin)):
    """Detiene el envío masivo en curso."""
    _promo_masiva_estado["activo"] = False
    return {"mensaje": "DETENIDO", "estado": _promo_masiva_estado}


async def _enviar_promo_background(all_leads: list[dict], plantilla: str):
    """Tarea background: envía plantilla a todos los leads."""
    import httpx as _httpx_pm
    _promo_masiva_estado.update({"activo": True, "total": len(all_leads), "enviados": 0, "errores": 0, "ultimo_enviado": ""})

    promo_image_handle = os.getenv("PROMO_MADRE_IMAGE_HANDLE", "1348826603758035")
    componentes_pm = [{"type": "header", "parameters": [{"type": "image", "image": {"id": promo_image_handle}}]}]

    for i, lead in enumerate(all_leads):
        ok = await proveedor.enviar_plantilla(lead["telefono"], plantilla, componentes=componentes_pm, language="es_AR")
        if ok:
            _promo_masiva_estado["enviados"] += 1
            _promo_masiva_estado["ultimo_enviado"] = lead["nombre"] or lead["telefono"]
            _leads_promo_madre_enviada.add(lead["telefono"])
            # Marcar PROMOMADRE en LEADS FENIX
            try:
                from agent.airtable_client import obtener_lead_record_id, _patch, _LEADS
                _rec = await obtener_lead_record_id(lead["telefono"])
                if _rec:
                    await _patch(_LEADS, _rec, {"PROMOMADRE": True})
            except Exception:
                pass
            # Notificar Telegram
            try:
                _t_pm = await obtener_o_crear_topic(lead["telefono"], lead["nombre"] or lead["telefono"])
                if _t_pm:
                    await enviar_a_topic(_t_pm, "📢 Plantilla PROMO MADRE enviada", telefono=lead["telefono"])
            except Exception:
                pass
        else:
            _promo_masiva_estado["errores"] += 1
        if not _promo_masiva_estado.get("activo"):
            logger.info(f"[PROMO-MASIVA] Detenido manualmente en {i+1}/{len(all_leads)}")
            break
        if (i + 1) % 50 == 0:
            await asyncio.sleep(2)

    _promo_masiva_estado["activo"] = False
    logger.info(f"[PROMO-MASIVA] Terminado: {_promo_masiva_estado['enviados']}/{_promo_masiva_estado['total']}")


@app.get("/debug/enviar-promo-masiva")
async def debug_enviar_promo_masiva(
    plantilla: str = "fenixpromomadre",
    dry_run: str = "true",
    telefono_test: str = "",
    excluir: str = "",
    _: bool = Depends(_require_admin),
):
    """Envía plantilla promo madre a TODOS los leads. Background + progreso en /debug/estado-promo-masiva."""
    if _promo_masiva_estado.get("activo"):
        return {"error": "Ya hay un envío en curso", "estado": _promo_masiva_estado}

    import httpx as _httpx_leads
    from agent.airtable_client import _LEADS, _BASE_URL, _headers
    all_leads: list[dict] = []
    _offset_at = None
    async with _httpx_leads.AsyncClient(timeout=30) as _cl_at:
        while True:
            _params_at: dict = {"pageSize": "100"}
            if _offset_at:
                _params_at["offset"] = _offset_at
            _r_at = await _cl_at.get(f"{_BASE_URL}/{_LEADS}", headers=_headers(), params=_params_at)
            if _r_at.status_code != 200:
                return {"error": f"Airtable HTTP {_r_at.status_code}"}
            _data_at = _r_at.json()
            for rec in _data_at.get("records", []):
                fields = rec.get("fields", {})
                tel = fields.get("TELEFONO", "")
                nombre = fields.get("NOMBRE RESPONSABLE", "") or fields.get("NOMBRE NIÑO", "")
                ya_enviado = fields.get("PROMOMADRE", False)
                if tel and not ya_enviado:
                    all_leads.append({"telefono": tel, "nombre": nombre})
            _offset_at = _data_at.get("offset")
            if not _offset_at:
                break

    # Excluir números específicos
    if excluir:
        _excluir_set = set(excluir.split(","))
        all_leads = [l for l in all_leads if l["telefono"] not in _excluir_set]

    if not all_leads:
        return {"total": 0, "mensaje": "No hay leads pendientes en LEADS FENIX (todos ya enviados o excluidos)"}
    if telefono_test:
        all_leads = [{"telefono": telefono_test, "nombre": "Test"}]

    es_dry_run = dry_run.lower() in ("true", "1", "si", "sí")
    if es_dry_run:
        return {"modo": "DRY RUN", "plantilla": plantilla, "total_leads": len(all_leads),
                "leads": [{"telefono": l["telefono"], "nombre": l["nombre"]} for l in all_leads]}

    asyncio.create_task(_enviar_promo_background(all_leads, plantilla))
    return {"mensaje": f"🚀 Envío masivo iniciado — {len(all_leads)} leads", "plantilla": plantilla,
            "total": len(all_leads), "progreso_en": "/debug/estado-promo-masiva"}


@app.get("/debug/revertir-pago-promomadre")
async def debug_revertir_pago_promomadre(
    dry_run: str = "true",
    _: bool = Depends(_require_admin),
):
    """Desmarca PAGO PROMOMADRE de todos los leads que lo tengan."""
    import httpx as _httpx_rev
    from agent.airtable_client import _LEADS, _BASE_URL, _headers, _patch

    candidatos: list[dict] = []
    _offset_rev = None
    async with _httpx_rev.AsyncClient(timeout=30) as _cl_rev:
        while True:
            _params_rev: dict = {"pageSize": "100", "filterByFormula": "{PAGO PROMOMADRE}=TRUE()"}
            if _offset_rev:
                _params_rev["offset"] = _offset_rev
            _r_rev = await _cl_rev.get(f"{_BASE_URL}/{_LEADS}", headers=_headers(), params=_params_rev)
            if _r_rev.status_code != 200:
                return {"error": f"Airtable HTTP {_r_rev.status_code}"}
            _data_rev = _r_rev.json()
            for rec in _data_rev.get("records", []):
                fields = rec.get("fields", {})
                candidatos.append({"id": rec["id"], "telefono": fields.get("TELEFONO", "")})
            _offset_rev = _data_rev.get("offset")
            if not _offset_rev:
                break

    es_dry_run = dry_run.lower() in ("true", "1", "si", "sí")
    if es_dry_run:
        return {"modo": "DRY RUN", "por_revertir": len(candidatos), "leads": candidatos}

    revertidos = 0
    for c in candidatos:
        try:
            await _patch(_LEADS, c["id"], {"PAGO PROMOMADRE": False})
            revertidos += 1
        except Exception:
            pass
    return {"revertidos": revertidos}


@app.get("/debug/auditoria-promomadre")
async def debug_auditoria_promomadre(
    _: bool = Depends(_require_admin),
):
    """Auditoría: escanea TODOS los leads con PROMOMADRE y verifica historial real en PostgreSQL."""
    import httpx as _httpx_aud
    from agent.airtable_client import _LEADS, _BASE_URL, _headers

    todos: list[dict] = []
    _offset_aud = None
    async with _httpx_aud.AsyncClient(timeout=30) as _cl_aud:
        while True:
            _params_aud: dict = {"pageSize": "100", "filterByFormula": "{PROMOMADRE}=TRUE()"}
            if _offset_aud:
                _params_aud["offset"] = _offset_aud
            _r_aud = await _cl_aud.get(f"{_BASE_URL}/{_LEADS}", headers=_headers(), params=_params_aud)
            if _r_aud.status_code != 200:
                return {"error": f"Airtable HTTP {_r_aud.status_code}"}
            _data_aud = _r_aud.json()
            for rec in _data_aud.get("records", []):
                f = rec.get("fields", {})
                todos.append({
                    "id": rec["id"],
                    "telefono": f.get("TELEFONO", ""),
                    "boton_airtable": bool(f.get("BOTON PROMOMADRE")),
                    "pago_airtable": bool(f.get("PAGO PROMOMADRE")),
                })
            _offset_aud = _data_aud.get("offset")
            if not _offset_aud:
                break

    # Verificar historial de cada lead en PostgreSQL
    respondieron_real = []
    pagaron_real = []
    for lead in todos:
        tel = lead["telefono"]
        if not tel:
            continue
        historial = await obtener_historial(tel, limite=50)
        # Respondió = recibió datos bancarios promo madre
        recibio_datos_banco = any(
            "promo madre" in m.get("content", "").lower() and "350" in m.get("content", "")
            for m in historial if m.get("role") == "assistant"
        )
        # Pagó = envió comprobante DESPUÉS de datos bancarios promo
        envio_comprobante = any(
            m.get("content", "") in ("[imagen]", "[documento]")
            for m in historial if m.get("role") == "user"
        )
        if recibio_datos_banco:
            respondieron_real.append(tel)
            if envio_comprobante:
                pagaron_real.append(tel)

    # Comparar con Airtable
    boton_airtable = [l["telefono"] for l in todos if l["boton_airtable"]]
    faltantes_boton = [t for t in respondieron_real if t not in boton_airtable]

    return {
        "total_enviados": len(todos),
        "respondieron_airtable": len(boton_airtable),
        "respondieron_historial": len(respondieron_real),
        "faltantes_boton": faltantes_boton,
        "pagaron_airtable": len([l for l in todos if l["pago_airtable"]]),
        "pagaron_historial": len(pagaron_real),
        "detalle_pagaron": pagaron_real,
    }


@app.get("/debug/marcar-pago-promomadre")
async def debug_marcar_pago_promomadre(
    dry_run: str = "true",
    _: bool = Depends(_require_admin),
):
    """Escanea leads que pagaron la promo madre (verificando historial de conversación) → marca PAGO PROMOMADRE."""
    import httpx as _httpx_ppm
    from agent.airtable_client import _LEADS, _BASE_URL, _headers, _patch

    # Buscar leads con BOTON PROMOMADRE (respondieron a la promo)
    marcados = 0
    ya_marcados = 0
    candidatos: list[dict] = []
    _offset_ppm = None

    async with _httpx_ppm.AsyncClient(timeout=30) as _cl_ppm:
        while True:
            _params_ppm: dict = {
                "pageSize": "100",
                "filterByFormula": "{BOTON PROMOMADRE}=TRUE()",
            }
            if _offset_ppm:
                _params_ppm["offset"] = _offset_ppm
            _r_ppm = await _cl_ppm.get(f"{_BASE_URL}/{_LEADS}", headers=_headers(), params=_params_ppm)
            if _r_ppm.status_code != 200:
                return {"error": f"Airtable HTTP {_r_ppm.status_code}"}
            _data_ppm = _r_ppm.json()
            for rec in _data_ppm.get("records", []):
                fields = rec.get("fields", {})
                if fields.get("PAGO PROMOMADRE"):
                    ya_marcados += 1
                    continue
                tel = fields.get("TELEFONO", "")
                if not tel:
                    continue
                # Verificar en historial si envió comprobante promo madre
                # El bot responde "gracias por tu pago" SOLO cuando recibe comprobante promo madre
                historial = await obtener_historial(tel, limite=50)
                tiene_datos_banco_promo = any(
                    "promo madre" in m.get("content", "").lower() and "350" in m.get("content", "")
                    for m in historial if m.get("role") == "assistant"
                )
                tiene_comprobante = any(
                    m.get("content", "") in ("[imagen]", "[documento]")
                    for m in historial if m.get("role") == "user"
                )
                pago_confirmado = tiene_datos_banco_promo and tiene_comprobante
                if pago_confirmado:
                    candidatos.append({
                        "id": rec["id"],
                        "telefono": tel,
                        "nombre": fields.get("NOMBRE RESPONSABLE", "") or fields.get("NOMBRE NIÑO", ""),
                    })
            _offset_ppm = _data_ppm.get("offset")
            if not _offset_ppm:
                break

    es_dry_run = dry_run.lower() in ("true", "1", "si", "sí")
    if es_dry_run:
        return {
            "modo": "DRY RUN",
            "por_marcar": len(candidatos),
            "ya_marcados": ya_marcados,
            "leads": candidatos,
        }

    for c in candidatos:
        try:
            await _patch(_LEADS, c["id"], {"PAGO PROMOMADRE": True})
            marcados += 1
        except Exception as _e_ppm:
            logger.error(f"[PROMO-MADRE] Error marcando PAGO para {c['telefono']}: {_e_ppm}")

    return {
        "marcados": marcados,
        "ya_marcados": ya_marcados,
        "total_procesados": marcados + ya_marcados,
    }


@app.get("/test-envio/{telefono}")
async def test_envio(telefono: str, msg: str = "Test desde Railway", _: bool = Depends(_require_admin)):
    """Envía un mensaje de prueba DESDE el servidor de Railway."""
    ok = await proveedor.enviar_mensaje(telefono, msg)
    return {"enviado": ok, "telefono": telefono, "mensaje": msg}


@app.get("/enviar-qr/{telefono}")
async def enviar_qr_admin(telefono: str, destino: str = "", _: bool = Depends(_require_admin)):
    """
    Genera y envía QR de check-in — uno por RESERVA futura de la familia
    (migración 2.B: el QR apunta a /checkin/{reserva_id}). Fallback temporal a
    (2.D: sin fallback a PRUEBA — solo reservas futuras reales del grupo).
    Si se pasa ?destino=XXXX, envía al número destino en vez de al lead (preview).
    """
    from agent.qr import generar_qr
    from agent.airtable_client import marcar_qr_enviado_reserva
    from agent.telegram_bridge import obtener_o_crear_topic, enviar_a_topic, group_id_para_agente
    enviar_a = destino or telefono
    es_preview = bool(destino)
    enviados = 0

    # Reservas futuras por los links del niño (2.D: buscar_reservas_familia
    # usaba FIND(record_id) sobre el link y NUNCA matcheaba; PRUEBA se retiró)
    from agent.airtable_client import obtener_grupo_familiar, _get_records, _RESERVAS
    from datetime import datetime as _dt_qr
    from zoneinfo import ZoneInfo as _ZI_qr
    _grupo_qr = await obtener_grupo_familiar(telefono)
    _reservas_qr = []
    _rids_qr = [rid for h in (_grupo_qr or {}).get("hijos", []) for rid in (h.get("reserva_ids") or [])][-20:]
    if _rids_qr:
        _hoy_qr = _dt_qr.now(_ZI_qr("America/Asuncion")).date().isoformat()
        _or_qr = ",".join(f"RECORD_ID()='{r}'" for r in _rids_qr)
        for _r_qr in await _get_records(_RESERVAS, formula=(f"OR({_or_qr})" if len(_rids_qr) > 1 else _or_qr), max_records=len(_rids_qr)):
            _fe_qr = _r_qr.get("fields", {}).get("FECHA", "")
            _fe_qr = (_fe_qr[0] if _fe_qr else "") if isinstance(_fe_qr, list) else _fe_qr
            if _fe_qr >= _hoy_qr:
                _reservas_qr.append(_r_qr["id"])
    if not _reservas_qr:
        return {"error": "No tiene reservas futuras"}
    for _rq_id in _reservas_qr:
        qr_bytes = generar_qr(_rq_id)
        await proveedor.enviar_imagen_bytes(
            enviar_a, qr_bytes, "image/png",
            caption="Mostrá este QR cuando llegues a Fenix Kids Academy 📱"
        )
        if not es_preview:
            await marcar_qr_enviado_reserva(_rq_id)
        enviados += 1
    # Espejar en Telegram — grupo según el agente REAL del número (agent_actual),
    # no forzar leads: una familia reserva por QR y quedaría en el grupo equivocado,
    # haciendo rebotar su topic (se crea uno nuevo en cada salto de grupo).
    try:
        _tg_group = await grupo_telegram_para(telefono)
        topic_id = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=_tg_group)
        if topic_id:
            await enviar_a_topic(topic_id, f"🎟️ QR Reserva enviado ({enviados})", telefono=telefono, group_override=_tg_group)
    except Exception:
        pass
    return {"enviado": True, "telefono": telefono, "qrs": enviados}


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


@app.post("/reset/{telefono}")
async def reset_total_admin(telefono: str, _: bool = Depends(_require_admin)):
    """
    Reset TOTAL de un número (solo admin): borra el historial de conversación local
    (mensajes + A/B) Y todo en Airtable en cascada (familia, niños, reservas, pruebas,
    lead). El número queda como lead 100% nuevo.

    Equivale al comando 'holayosoyfenix' pero ejecutable de forma remota por admin
    (con header X-ADMIN-KEY), sin que la persona tenga que escribir nada.
    """
    contador_airtable = await eliminar_todo_de_telefono(telefono)
    await limpiar_estado_completo(telefono)
    logger.info(f"[RESET] Reset total admin para {telefono}: {contador_airtable}")
    return {
        "telefono": telefono,
        "reset": "total",
        "airtable": contador_airtable,
        "conversacion": "borrada",
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


@app.post("/pago-confirmado")
async def pago_confirmado(request: Request):
    """La pasarela (pagos-bancard) avisa que un pago con TARJETA se confirmó.
    Dispara EL MISMO flujo que el comprobante de transferencia, con método
    CREDIT CARD y el monto EXACTO que cobró Bancard (viene firmado).

    Contrato con la pasarela: respondemos {"ok": true, "gestionado": true|false}.
    gestionado=true → Aurora registra el PAGO en Airtable (como siempre) y la
    pasarela NO registra (evita el pago doble). gestionado=false (sin Pedido —
    ej. link del panel /admin de la pasarela) → confirmamos + avisamos al admin
    y la pasarela registra ella en la caja central.
    Firma HMAC(LINK_SECRET) + dedup por shop_process_id.
    """
    import hashlib
    import hmac as _hmac
    from agent.memory import obtener_pedido_activo, marcar_pedido_cargado
    from agent.flujo_pagos import _procesar_comprobante

    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="body inválido")

    telefono = str(data.get("telefono", "")).strip()
    monto = int(data.get("monto", 0) or 0)
    concepto = str(data.get("concepto", ""))
    spid = str(data.get("shop_process_id", ""))
    auth = str(data.get("authorization_number", ""))
    sig = str(data.get("sig", ""))

    # 1) firma
    secret = os.getenv("LINK_SECRET", "")
    esperada = _hmac.new(secret.encode(), f"{spid}:{telefono}:{monto}".encode(), hashlib.sha256).hexdigest()
    if not (secret and sig and _hmac.compare_digest(esperada, sig)):
        logger.warning(f"[PAGO-CONFIRMADO] firma inválida spid={spid} tel={telefono}")
        raise HTTPException(status_code=403, detail="firma inválida")
    if not telefono or not spid:
        raise HTTPException(status_code=400, detail="faltan datos")

    # 2) dedup ATÓMICA (Bancard reintenta → la pasarela renotifica): el primer
    # webhook inserta y procesa; un reintento concurrente ve False y hace ack.
    # gestionado=True en el duplicado: la pasarela no debe registrar de nuevo.
    # Si el flujo falla más abajo, respondemos gestionado=False y la pasarela
    # registra en la caja central + se alerta al admin (no hace falta reintento).
    _dedup = f"pago-tarjeta:{spid}"
    if not await registrar_mensaje_procesado(_dedup):
        logger.info(f"[PAGO-CONFIRMADO] duplicado spid={spid}, ack")
        return {"ok": True, "dedup": True, "gestionado": True}

    logger.info(f"[PAGO-CONFIRMADO] tel={telefono} monto={monto} concepto={concepto} spid={spid}")
    _monto_txt = f"{monto:,} Gs".replace(",", ".")
    admin_phone = os.getenv("ADMIN_PHONE", "")
    gestionado = False

    # 3) solo gestionamos pagos que Aurora inició (Pedido abierto al mandar el link).
    # Lock por teléfono: que el flujo del pago no corra en paralelo con un
    # mensaje entrante del mismo lead (mismo candado que el webhook de Meta).
    async with _obtener_lock(telefono):
        _pedido = await obtener_pedido_activo(telefono)
        if _pedido:
            gestionado = True
            try:
                historial = await obtener_historial(telefono, limite=40)
                _grupo = await grupo_telegram_para(telefono)
                _nombre_topic = _extraer_nombre_del_historial(historial, "") or telefono
                topic_id = await obtener_o_crear_topic(telefono, _nombre_topic, group_override=_grupo)
                await _procesar_comprobante(
                    telefono, "[pago con tarjeta]", None, historial, topic_id,
                    group_override=_grupo,
                    metodo_pago="CREDIT CARD",
                    monto_override=monto,
                    tipo_override=_pedido.tipo,
                    concepto_pago=_pedido.concepto or "PRUEBA",
                    auth_number=auth,
                )
                await marcar_pedido_cargado(telefono)
            except Exception as e:
                logger.exception(f"[PAGO-CONFIRMADO] flujo falló para {telefono}: {e}")
                gestionado = False
                try:
                    await proveedor.enviar_mensaje(
                        admin_phone,
                        f"⚠️ Pago TARJETA de {telefono} ({_monto_txt}) confirmado "
                        f"pero el flujo falló — revisar y cargar manual. spid {spid}")
                except Exception:
                    pass

        if not gestionado and not _pedido:
            # Sin Pedido (link del panel /admin de la pasarela, etc.): confirmar +
            # avisar al admin. La pasarela registra en la caja central (gestionado=false).
            _msg = f"✅ ¡Pago confirmado! Recibimos tus *{_monto_txt}* 🎉 ¡Gracias!"
            await guardar_mensaje(telefono, "assistant", _msg)
            await proveedor.enviar_mensaje(telefono, _msg)
            try:
                await proveedor.enviar_mensaje(
                    admin_phone,
                    f"💳 *Pago con TARJETA confirmado* (sin pedido de Aurora)\n"
                    f"Tel: {telefono}\n{_monto_txt} — {concepto}\naut {auth}\n"
                    f"La pasarela lo registra en la caja central.",
                )
            except Exception:
                pass

    return {"ok": True, "gestionado": gestionado}


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


# ── Detectores de conversación (extraído a agent/detectores_conv.py) ──
from agent.detectores_conv import (
    _cancelar_diagnostico_pendiente, _diagnostico_pendiente, _DELAY_DIAGNOSTICO,
    _diagnostico_ya_enviado, _padre_muestra_interes,
    _padre_ya_pidio_precios, _detectar_pedido_llamada,
    _extraer_nombre_del_historial, _es_nombre_hijo_valido,
    _extraer_nombre_hijo_historial, _extraer_edad_historial,
    _detectar_confirmacion_aurora,
)


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

    # Link al topic de Telegram del lead
    tg_link = ""
    try:
        from agent.telegram_bridge import obtener_topic
        topic = await obtener_topic(telefono)
        if topic and topic.topic_id and topic.group_id:
            gid = str(topic.group_id).replace("-100", "", 1)
            tg_link = f"\n💬 https://t.me/c/{gid}/{topic.topic_id}"
    except Exception:
        pass

    alerta = (
        f"🚨 Urgente: Llamar a {nombre_padre}\n\n"
        f"👦 Hijo/a: {nombre_hijo}\n"
        f"🎂 Edad: {edad_hijo}\n\n"
        f"📲 {wa_link}"
        f"{tg_link}"
    )

    # Canal 1: WhatsApp al admin
    admin_phone = os.getenv("ADMIN_PHONE", "")
    wa_ok = False
    try:
        wa_ok = await proveedor.enviar_mensaje(admin_phone, alerta)
        if wa_ok:
            logger.info(f"[LLAMADA] Alerta WhatsApp al admin: OK")
        else:
            logger.warning(f"[LLAMADA] Alerta WhatsApp al admin FALLÓ")
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


async def _alertar_silencio_ivan(telefono: str, ultimo_msg: str, historial: list[dict]):
    """
    Alerta al admin cuando Claude no supo responder y dijo "te respondo en un minuto".
    Doble canal: WhatsApp (ADMIN_PHONE) + Telegram.
    """
    from urllib.parse import quote

    nombre_padre = _extraer_nombre_del_historial(historial, ultimo_msg) or "Lead"
    primer_nombre = nombre_padre.split()[0] if nombre_padre != "Lead" else ""
    mensaje_pre = f"Que tal {primer_nombre}, soy el profe Ivan" if primer_nombre else "Que tal, soy el profe Ivan"
    wa_link = f"https://wa.me/{telefono}?text={quote(mensaje_pre)}"

    # Link al topic de Telegram del lead
    tg_link = ""
    try:
        from agent.telegram_bridge import obtener_topic
        topic = await obtener_topic(telefono)
        if topic and topic.topic_id and topic.group_id:
            gid = str(topic.group_id).replace("-100", "", 1)
            tg_link = f"\n💬 https://t.me/c/{gid}/{topic.topic_id}"
    except Exception:
        pass

    alerta = (
        f"⚠️ IVAN NO SUPO RESPONDER\n\n"
        f"👤 Padre: {nombre_padre}\n"
        f"💬 Último mensaje: {ultimo_msg[:200]}\n\n"
        f"📲 {wa_link}"
        f"{tg_link}"
    )

    # Canal 1: WhatsApp al admin
    admin_phone = os.getenv("ADMIN_PHONE", "")
    try:
        await proveedor.enviar_mensaje(admin_phone, alerta)
        logger.info(f"[SILENCIO] Alerta WhatsApp al admin: OK")
    except Exception as e:
        logger.error(f"[SILENCIO] Error WhatsApp admin: {e}")

    # Canal 2: Telegram
    try:
        await notificar_llamada_urgente(telefono, nombre_padre, wa_link)
        logger.info(f"[SILENCIO] Alerta Telegram: OK")
    except Exception as e:
        logger.error(f"[SILENCIO] Error Telegram: {e}")



# (_detectar_confirmacion_aurora movido a agent/detectores_conv.py)


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
        # ── Firma de Meta (X-Hub-Signature-256) ──
        # Log-only por defecto; con META_FIRMA_RECHAZAR=1 rechaza con 403.
        # Leer el body crudo ANTES de parsear (Starlette lo cachea → el
        # request.json() de parsear_webhook sigue funcionando).
        if hasattr(proveedor, "verificar_firma"):
            body_bytes = await request.body()
            _firma_ok = proveedor.verificar_firma(
                body_bytes, request.headers.get("X-Hub-Signature-256")
            )
            if not _firma_ok:
                if os.getenv("META_FIRMA_RECHAZAR", "").strip() == "1":
                    logger.warning("[FIRMA-INVALIDA] Webhook rechazado (403)")
                    from fastapi.responses import JSONResponse
                    return JSONResponse(status_code=403, content={"error": "firma invalida"})
                logger.warning("[FIRMA-INVALIDA] Firma no coincide — modo log-only, se procesa igual")

        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            # Deduplicación: skip si ya se procesó (Meta reenvía duplicados)
            if msg.mensaje_id and await mensaje_ya_procesado(msg.mensaje_id):
                continue

            # Rate limit por teléfono — ANTES de registrar la dedup: si el mensaje
            # se descarta acá, no debe quedar marcado como procesado (un comprobante
            # descartado quedaba perdido para siempre — auditoría 04-07-26 C3).
            if _check_rate_limit(msg.telefono):
                logger.warning(f"[RATE LIMIT] {msg.telefono} excede {_RATE_LIMIT_MAX} msgs/{_RATE_LIMIT_WINDOW}s")
                continue

            # Registrar dedup en PostgreSQL (insert-como-candado: si dos webhooks
            # duplicados llegan casi juntos, ambos pasaban el check de arriba y el
            # lead recibía la respuesta DOS veces — auditoría 04-07-26 M1; el
            # índice único garantiza que solo uno procesa).
            # Si el procesamiento falla, se borra la dedup para permitir reintento.
            # IMPORTANTE: responder 200 rápido (<5s) para que Meta no reintente.
            if msg.mensaje_id and not await registrar_mensaje_procesado(msg.mensaje_id):
                continue  # otro webhook concurrente ya lo tomó

            # Procesamiento en background — responder 200 rápido a Meta
            _fire_and_forget(_procesar_mensaje_webhook(msg))

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}", exc_info=True)
        registrar_error_webhook("desconocido", str(e))
        return {"status": "error"}


async def _build_contexto_aurora(tutores: list[dict], hijos_raw: list[dict], telefono: str = "") -> str:
    """Arma el contexto del grupo familiar para inyectar en Aurora.

    Niño-eje: recibe tutores e hijos ya resueltos (obtener_grupo_familiar) —
    las reservas salen de los links del niño. FAMILIAS no participa.
    """

    def _primer_nombre(nombre: str) -> str:
        """Retorna solo el primer nombre (sin apellido ni segundo nombre)."""
        return nombre.strip().split()[0] if nombre and nombre.strip() else ""

    def _genero_de(parentesco: str) -> str:
        return {"Papá": "papá", "Mamá": "mamá"}.get(parentesco, "padre/madre")

    # Detectar quién escribe por teléfono — apodo primero, sino solo primer nombre
    _quien = None
    if telefono:
        _quien = next(
            (t for t in tutores if telefono in (t.get("cell"), t.get("cell_limpio"))),
            None,
        )
    if _quien:
        quien_escribe = (_quien.get("apodo") or "").strip() or _primer_nombre(_quien.get("nombre", ""))
        es_genero = _genero_de(_quien.get("parentesco", ""))
    else:
        # No identificado por teléfono: usar el primer tutor que tenga nombre
        _primero = next((t for t in tutores if (t.get("nombre") or "").strip()), None)
        quien_escribe = (
            (_primero.get("apodo") or "").strip() or _primer_nombre(_primero.get("nombre", ""))
            if _primero else ""
        )
        es_genero = "padre/madre"

    # Datos de quien escribe
    nombre_desconocido = not quien_escribe
    if nombre_desconocido:
        datos_quien_escribe = "Nombre: (no registrado todavía — PEDIRLO PRIMERO), género: desconocido"
    else:
        datos_quien_escribe = f"Nombre: {quien_escribe}, género: {es_genero}"

    # Datos de los tutores (para verificación) — desde TUTORES FENIX
    datos_padre = []
    for t in tutores:
        if not (t.get("nombre") or "").strip():
            continue
        _label = {"Papá": "PADRE", "Mamá": "MADRE"}.get(t.get("parentesco", ""), "TUTOR")
        linea = f"{_label}: {t.get('nombre', '')} {t.get('apellido', '')}".strip()
        if t.get("apodo"):
            linea += f" (apodo: {t['apodo']})"
        if t.get("ci"):
            linea += f", CI: {t['ci']}"
        if t.get("cell"):
            linea += f", cel: {t['cell']}"
        if t.get("email"):
            linea += f", email: {t['email']}"
        if t.get("fecha_nacimiento"):
            linea += f", nac: {t['fecha_nacimiento']}"
        datos_padre.append(linea)

    # Datos de los hijos
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

    # Reservas activas de esta familia (solo futuras) — se retorna por separado
    # Niño-eje: se buscan por el link RESERVAS FENIX de cada hijo (RECORD_ID),
    # no por FIND del nombre de la familia (bug A8: familia sin nombre matcheaba
    # cualquier reserva con 'FAMILIA' en el lookup).
    _reservas_texto = ""
    try:
        from agent.airtable_client import _get_records, _RESERVAS
        from datetime import datetime as _dt_cls
        from zoneinfo import ZoneInfo
        _hoy_py = _dt_cls.now(ZoneInfo("America/Asuncion")).date()
        _hoy_str = _hoy_py.isoformat()
        _reserva_ids = [rid for h in hijos_raw for rid in (h.get("reserva_ids") or [])]
        # Tope defensivo: los links guardan orden de alta → las últimas son las
        # más nuevas (acá solo interesan las futuras). Evita fórmulas kilométricas.
        if len(_reserva_ids) > 60:
            _reserva_ids = _reserva_ids[-60:]
        _reservas_raw = []
        if _reserva_ids:
            _or_res = ",".join(f"RECORD_ID()='{rid}'" for rid in _reserva_ids)
            _formula = f"OR({_or_res})" if len(_reserva_ids) > 1 else _or_res
            _reservas_raw = await _get_records(_RESERVAS, formula=_formula, max_records=len(_reserva_ids))
        reservas_futuras = []
        for _rr in _reservas_raw:
            _rf = _rr.get("fields", {})
            _fecha = _rf.get("FECHA", "")
            if isinstance(_fecha, list):
                _fecha = _fecha[0] if _fecha else ""
            _hora = _rf.get("HORA", "")
            if isinstance(_hora, list):
                _hora = _hora[0] if _hora else ""
            _nombre = _rf.get("NOMBRE COMPLETO", "")
            if isinstance(_nombre, list):
                _nombre = _nombre[0] if _nombre else ""
            if _fecha >= _hoy_str:
                reservas_futuras.append({"nombre_nino": _nombre, "fecha": _fecha, "hora": _hora})
        if reservas_futuras:
            _reservas_texto = "RESERVAS ACTIVAS DE ESTA FAMILIA:\n"
            for r in sorted(reservas_futuras, key=lambda x: x.get("fecha", "")):
                _nombre = r.get("nombre_nino", "?")
                _fecha = r.get("fecha", "?")
                _hora = r.get("hora", "?")
                try:
                    # _hoy_cls no existía (NameError tragado por el except):
                    # Aurora mostraba SIEMPRE la fecha ISO cruda (auditoría 12/07)
                    _fd = _dt_cls.fromisoformat(_fecha)
                    _fecha_label = f"Sábado {_fd.day}/{_fd.month}"
                except Exception:
                    _fecha_label = _fecha
                _reservas_texto += f"📅 {_nombre}: {_fecha_label} a las {_hora}h\n"
        else:
            _reservas_texto = "RESERVAS ACTIVAS: ninguna"
    except Exception as e:
        logger.error(f"[AURORA] Error cargando reservas familia: {e}")

    # Total agendados por horario (inscriptos + prueba, sin nombres)
    # Fuente ÚNICA: RESERVAS FENIX via obtener_ninos_por_horario (migración 2.B —
    # antes se sumaban además los registros PRUEBA FENIX y los niños de prueba
    # con dual-write se contaban DOS veces). Las consultas son independientes
    # entre horarios → paralelo con semáforo de 5 (rate de Airtable).
    try:
        from datetime import date as _date_cls
        horarios = await obtener_horarios_disponibles(max_horarios=6)
        if horarios:
            _sem_airtable = asyncio.Semaphore(5)

            async def _contar_agendados(hor: dict):
                fecha_iso = hor.get("fecha", "")
                hora = hor.get("hora", "")
                if not fecha_iso or not hora:
                    return None
                _fd = _date_cls.fromisoformat(fecha_iso)
                fecha_texto = f"{_fd.day}/{_fd.month}"
                async with _sem_airtable:
                    ninos_hor = await obtener_ninos_por_horario(fecha_iso, hora)
                total = len(ninos_hor)
                return f"  Sábado {fecha_texto} {hora}h: {total} agendados\n"

            # gather preserva el orden de los horarios
            _lineas = await asyncio.gather(*[_contar_agendados(h) for h in horarios])
            _lineas = [l for l in _lineas if l]
            if _lineas:
                contexto += "\nTOTAL AGENDADOS POR HORARIO:\n" + "".join(_lineas)
    except Exception as e:
        logger.error(f"[AURORA] Error cargando agendados por horario: {e}")

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

    return contexto, _reservas_texto


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


# Referral CTWA pendiente de persistir: el referral viene SOLO en el primer
# mensaje del lead, pero guardar_ctwa_clid es no-op si la fila ConversacionAB
# no existe todavía (se crea recién en asignar_variante) → la atribución de
# anuncios se perdía para TODO lead nuevo (auditoría 04-07-26 A2). Se stashea
# acá y se re-persiste después de asignar_variante.
_referral_pendiente: dict[str, dict] = {}


async def _flush_referral_pendiente(telefono: str):
    """Persiste el referral stasheado una vez que la fila ConversacionAB existe."""
    datos = _referral_pendiente.pop(telefono, None)
    if not datos:
        return
    try:
        from agent.memory import guardar_ctwa_clid, guardar_ad_source_id
        if datos.get("ctwa"):
            await guardar_ctwa_clid(telefono, datos["ctwa"])
        if datos.get("ad"):
            await guardar_ad_source_id(telefono, datos["ad"])
        logger.info(f"[CAPI] Referral persistido post-asignación para {telefono}")
    except Exception as e:
        logger.error(f"[CAPI] Error persistiendo referral pendiente: {e}")


async def _procesar_mensaje_interno(telefono: str, texto: str, msg):
    """Procesamiento real del mensaje, protegido por lock de teléfono."""
    try:
        # Capturar ctwa_clid del anuncio CTWA (viene en el primer mensaje del lead)
        if hasattr(msg, 'ctwa_clid') and msg.ctwa_clid:
            from agent.memory import guardar_ctwa_clid
            await guardar_ctwa_clid(msg.telefono, msg.ctwa_clid)
            _referral_pendiente.setdefault(telefono, {})["ctwa"] = msg.ctwa_clid
            logger.info(f"[CAPI] ctwa_clid capturado para {msg.telefono}")

        # Capturar ad_source_id (ID del anuncio Meta) del referral
        if hasattr(msg, 'ad_source_id') and msg.ad_source_id:
            from agent.memory import guardar_ad_source_id
            await guardar_ad_source_id(msg.telefono, msg.ad_source_id)
            _referral_pendiente.setdefault(telefono, {})["ad"] = msg.ad_source_id
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

        # ── Admin phone + atajo numérico del menú secre ──
        admin_phone = os.getenv("ADMIN_PHONE", "")
        # Si hay un flujo pendiente que espera respuesta numérica (selección de
        # candidato de cara, lista de asistencia, inscripción), el número es para
        # ese flujo — NO remapear al menú secre.
        _admin_espera_respuesta = (
            telefono in _cara_candidatos
            or telefono in _asistencia_pendiente
            or telefono in _inscripcion_pendiente
        )
        if telefono == admin_phone and telefono not in _admin_modo_padre and not _admin_espera_respuesta:
            _MENU_SECRE = {
                "1": "resumen reservas", "2": "resumen anuncios", "3": "resumen flias",
                "4": "resumen asis", "6": "resumen seguimiento",
                "7": "resumen telegram", "8": "resumen followup",
                "12": "modo padre", "13": "modo alumno",
            }
            _num = texto.strip()
            if _num in _MENU_SECRE:
                texto = _MENU_SECRE[_num]

        # ── Comando "comandos" (solo admin) — lista de comandos disponibles ──
        if texto.lower().strip() == "comandos" and telefono == admin_phone:
            msg_comandos = (
                "⚙️ *COMANDOS ADMIN*\n\n"
                "📊 *Resumenes:*\n"
                "• `resumen anuncios` — métricas de anuncios Meta\n"
                "• `resumen anuncios hoy` / `ayer` / `[mes]`\n"
                "• `resumen reservas` — reservas del sábado próximo por turno\n"
                "• `resumen flias` — familias con nombre hijo + padre + link wa.me\n"
                "• `resumen asis` / `resumen asis 10/5` — quién vino (presentes por turno)\n"
                "• `resumen seguimiento` / `seguimiento 9/5` — estado mensajes personalizados\n"
                "• `resumen telegram` — reservas + link Telegram de cada conversación\n"
                "• `resumen followup` — mapa completo de FU\n\n"
                "✅ *Asistencia:*\n"
                "• `asis 9.30` / `asis 11` / `asis 15.30` — pasar lista por turno\n"
                "• `asistencia` — lista completa todos los turnos\n"
                "• `PRESENTE nombre` — marca presente (inscripto)\n"
                "• `PRESENTE PRUEBA nombre` — marca presente (prueba)\n\n"
                "👨‍👩‍👧 *Inscripción:*\n"
                "• `cargar familia [nombre padre]` — inscribir familia desde PRUEBA\n\n"
                "📸 *Fotos (reconocimiento facial):*\n"
                "• `fotos 9:30` / `fotos 11` / `fotos 15:30` — modo fotos de clase\n"
                "• `selfie [nombre]` (o `registrar cara [nombre]`) — registrar cara de un niño\n\n"
                "🔄 *Reset:*\n"
                "• `modo padre` — reset completo + entrar como padre nuevo\n"
                "• `modo alumno` — reset conversación, simular padre inscripto\n"
                "• `modo secre` — volver a solo comandos (default)\n\n"
                "📋 *Info:*\n"
                "• `comandos` — esta lista\n\n"
                "💬 *Telegram (dentro del topic del lead):*\n"
                "• `/silenciar` — silenciar agente, vos tomás control\n"
                "• `/reactivar` — reactivar agente\n"
                "• `/aprobado` — evaluación aprobada, Ivan sigue\n"
                "• `/rechazado` — evaluación rechazada\n"
                "• `/fenix` — reset conversación + reactivar\n"
                "• `/registro` — activar Aurora para registrar familia\n"
                "• `/agenda 100mil|150mil|200mil|gratis nombre` — cerrar agenda manual\n"
                "• _(texto libre)_ — se reenvía como mensaje de Ivan al padre"
            )
            await proveedor.enviar_mensaje(telefono, msg_comandos)
            return

        # ── Comando "promo madre" (solo admin) — stats del envío masivo (solo totales) ──
        if texto.lower().strip() == "promo madre" and telefono == admin_phone:
            import httpx as _httpx_pm_cmd
            from agent.airtable_client import _LEADS, _BASE_URL, _headers as _at_headers
            _total_env_f = 0
            _total_resp_f = 0
            _total_pago_f = 0
            _pagaron_detalle: list[dict] = []
            _offset_pmf = None
            try:
                async with _httpx_pm_cmd.AsyncClient(timeout=30) as _cl_pmf:
                    while True:
                        _params_pmf: dict = {"pageSize": "100", "filterByFormula": "{PROMOMADRE}=TRUE()"}
                        if _offset_pmf:
                            _params_pmf["offset"] = _offset_pmf
                        _r_pmf = await _cl_pmf.get(f"{_BASE_URL}/{_LEADS}", headers=_at_headers(), params=_params_pmf)
                        if _r_pmf.status_code != 200:
                            break
                        _data_pmf = _r_pmf.json()
                        for _rec_pmf in _data_pmf.get("records", []):
                            _f_pmf = _rec_pmf.get("fields", {})
                            _total_env_f += 1
                            if _f_pmf.get("BOTON PROMOMADRE"):
                                _total_resp_f += 1
                            if _f_pmf.get("PAGO PROMOMADRE"):
                                _total_pago_f += 1
                                _pagaron_detalle.append({
                                    "nombre": _f_pmf.get("NOMBRE RESPONSABLE", "") or _f_pmf.get("NOMBRE NIÑO", "") or "Sin nombre",
                                    "telefono": _f_pmf.get("TELEFONO", ""),
                                })
                        _offset_pmf = _data_pmf.get("offset")
                        if not _offset_pmf:
                            break
            except Exception as _e_pmf:
                await proveedor.enviar_mensaje(telefono, f"Error: {_e_pmf}")
                return

            # Generar links de Telegram para cada lead que pagó
            from agent.telegram_bridge import obtener_topic
            _lineas_pagaron = []
            for _pd in _pagaron_detalle:
                _tg_lnk = ""
                try:
                    _tp = await obtener_topic(_pd["telefono"])
                    if _tp and _tp.topic_id and _tp.group_id:
                        _gid = str(_tp.group_id).replace("-100", "", 1)
                        _tg_lnk = f" → https://t.me/c/{_gid}/{_tp.topic_id}"
                except Exception:
                    pass
                _lineas_pagaron.append(f"  • {_pd['nombre']}{_tg_lnk}\n    📱 {_pd['telefono']}")

            _pct_resp = (_total_resp_f / _total_env_f * 100) if _total_env_f else 0
            _pct_pago_total = (_total_pago_f / _total_env_f * 100) if _total_env_f else 0
            _pct_pago_click = (_total_pago_f / _total_resp_f * 100) if _total_resp_f else 0
            _detalle_txt = "\n".join(_lineas_pagaron) if _lineas_pagaron else "  (ninguno)"
            _msg_stats_f = (
                f"🎁 *PROMO DÍA DE LA MADRE — FENIX*\n\n"
                f"📨 Enviados: *{_total_env_f}*\n"
                f"👆 Respondieron: *{_total_resp_f}* ({_pct_resp:.1f}%)\n"
                f"💰 Pagaron: *{_total_pago_f}* ({_pct_pago_total:.1f}% del total · {_pct_pago_click:.1f}% de clicks)\n\n"
                f"{_detalle_txt}"
            )
            await proveedor.enviar_mensaje(telefono, _msg_stats_f)
            return

        # ── Comando reset (solo admin) ────────────────────────────────────
        _reset_phones = {admin_phone, "595982844548"}
        _texto_reset = texto.lower().strip()
        if _texto_reset in ("holayosoyfenix", "modo padre", "modopadre") and telefono in _reset_phones:
            cancelar_seguimiento(telefono)
            cancelar_recordatorios(telefono)
            _cancelar_diagnostico_pendiente(telefono)
            _admin_modo_padre.discard(telefono)
            _esperando_pago_promo_madre.discard(telefono)
            _leads_promo_madre_enviada.discard(telefono)
            _esperando_formulario_promo.discard(telefono)
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
            # Si es admin, activar modo padre automáticamente después del reset
            if telefono == admin_phone:
                _admin_modo_padre.add(telefono)
                resumen += "\n\nModo padre activado — te respondo como si fueras un padre. Escribí 'modo secre' para volver."
            await proveedor.enviar_mensaje(telefono, resumen)
            topic_reset = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            if topic_reset:
                await enviar_a_topic(topic_reset, f"⚙️ RESET — {resumen}", telefono=telefono)
            return

        # ── Comando PRESENTE nombre (solo admin) ──────────────────────────
        if telefono == admin_phone and texto.strip().upper().startswith("PRESENTE "):
            _args_presente = texto.strip()[len("PRESENTE "):].strip()
            # "PRESENTE PRUEBA nombre" (hábito viejo): el prefijo se acepta y se
            # ignora — la búsqueda unificada en RESERVAS ya incluye a los de prueba.
            if _args_presente.upper().startswith("PRUEBA "):
                _args_presente = _args_presente[len("PRUEBA "):].strip()
            try:
                await _marcar_presente_por_nombre(telefono, _args_presente)
            except Exception as e:
                logger.error(f"[PRESENTE] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error: {e}")
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
            # Si no es "ok" ni números, interpretar como nombres adicionales UNA VEZ y salir del modo
            elif not _resp_asis.startswith(("resumen", "endpoint", "fotos", "registrar", "cargar")):
                try:
                    await _agregar_presentes_por_nombres(telefono, texto.strip())
                except Exception as e:
                    logger.error(f"[ASISTENCIA+] Error: {e}")
                    await proveedor.enviar_mensaje(telefono, f"Error: {e}")
                # Salir del modo asistencia
                _asistencia_pendiente.pop(telefono, None)
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

        # ── Comando "selfie [nombre]" / "registrar cara [nombre]" (solo admin) ────
        # Acepta: texto "selfie matheo" (sin foto) O imagen con caption "selfie matheo".
        # "selfie" es el alias que Iván ya usa con Dorita — mismo hábito en los dos agentes.
        _caption_cara = getattr(msg, "caption", "") or ""

        def _nombre_tras_prefijo_cara(s: str) -> str | None:
            """Nombre tras "selfie"/"registrar cara"; None si no es el comando.
            Match estricto (prefijo exacto o prefijo + espacio) — "selfies..." no dispara."""
            s = s.strip()
            for _p in ("registrar cara", "selfie"):
                if s.lower() == _p or s.lower().startswith(_p + " "):
                    return s[len(_p):].strip()
            return None

        _cara_texto = _nombre_tras_prefijo_cara(texto) if telefono == admin_phone else None
        _cara_caption = (_nombre_tras_prefijo_cara(_caption_cara)
                         if telefono == admin_phone and texto == "[imagen]" and msg.media_id
                         else None)
        if _cara_texto is not None or _cara_caption is not None:
            _nombre_cara = _cara_caption if _cara_caption is not None else _cara_texto
            if _nombre_cara:
                if _cara_caption is not None:
                    # Foto + nombre en un solo mensaje → procesar directo
                    _cara_pendiente[telefono] = _nombre_cara
                    _cara_media_pendiente[telefono] = msg.media_id
                    await _procesar_registro_cara(telefono, msg.media_id)
                else:
                    # Solo texto → esperar foto
                    _cara_pendiente[telefono] = _nombre_cara
                    await proveedor.enviar_mensaje(telefono, f"Dale, mandá la foto de {_nombre_cara} para registrar su cara")
            else:
                await proveedor.enviar_mensaje(telefono, "Usá: selfie [nombre del niño] (también vale: registrar cara [nombre])")
            return

        # ── Selección numérica de candidato para registrar cara ──────────
        if telefono == admin_phone and telefono in _cara_candidatos and texto.strip().isdigit():
            _idx = int(texto.strip()) - 1
            _candidatos = _cara_candidatos[telefono]
            if 0 <= _idx < len(_candidatos):
                _sel = _candidatos[_idx]
                del _cara_candidatos[telefono]
                _cara_pendiente[telefono] = _sel["nombre_completo"]
                _cara_record_preseleccionado[telefono] = _sel
                # Si ya tenía foto pendiente (mandó foto+nombre y hubo múltiples), usar esa foto
                _media_guardado = _cara_media_pendiente.pop(telefono, None)
                if _media_guardado:
                    await _procesar_registro_cara(telefono, _media_guardado)
                else:
                    await proveedor.enviar_mensaje(telefono, f"Dale, mandá la foto de {_sel['nombre_completo']} para registrar su cara")
            else:
                await proveedor.enviar_mensaje(telefono, f"Número inválido. Elegí entre 1 y {len(_candidatos)}")
            return

        # ── Recibir foto para registrar cara ──────────────────────────────
        if telefono == admin_phone and telefono in _cara_pendiente and texto == "[imagen]" and msg.media_id:
            await _procesar_registro_cara(telefono, msg.media_id)
            return

        # ── Comando cargar niño (solo admin): formulario Meta → FAMILIAS ──
        _texto_cn = texto.lower().strip().replace("ñ", "n")
        if telefono == admin_phone and _texto_cn.startswith("cargar nino"):
            try:
                await enviar_formulario_cargar_nino(telefono)
            except Exception as e:
                logger.error(f"[CARGAR-NINO] Error enviando formulario: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error: {e}")
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
        # "resumen" excluido: "resumen asistencia" debe llegar a SU comando más
        # abajo — este bloque lo capturaba antes y pasaba lista en vez de resumir
        if telefono == admin_phone and "resumen" not in _texto_cmd and ("asistencia" in _texto_cmd or "control asis" in _texto_cmd or _texto_cmd.startswith("asis ")):
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

        # ── Comando resumen flias (solo admin) ─────────────────────────
        if telefono == admin_phone and "resumen" in _texto_cmd and "flia" in _texto_cmd:
            _fecha_override_fl = None
            _m_fecha_fl = re.search(r'(\d{1,2})/(\d{1,2})', _texto_cmd)
            if _m_fecha_fl:
                from datetime import date as _date_cls, datetime as _dt_cls, timezone as _tz_cls, timedelta as _td_cls
                _anio = _dt_cls.now(_tz_cls(_td_cls(hours=-3))).year
                try:
                    _fecha_override_fl = _date_cls(_anio, int(_m_fecha_fl.group(2)), int(_m_fecha_fl.group(1)))
                except ValueError:
                    pass
            try:
                await _generar_resumen_flias(telefono, fecha_override=_fecha_override_fl)
            except Exception as e:
                logger.error(f"[RESUMEN FLIAS] Error: {e}")
                await proveedor.enviar_mensaje(telefono, f"Error generando resumen flias: {e}")
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

        # ── Comando resumen prueba: RETIRADO (migración 2.B) ───────────────
        # El dashboard salía de PRUEBA FENIX (en retiro). Decisión de Ivan
        # 2026-07-12: se elimina, no se reconstruye.
        if telefono == admin_phone and "resumen" in _texto_cmd and "prueba" in _texto_cmd:
            await proveedor.enviar_mensaje(
                telefono,
                "El comando *resumen prueba* fue retirado (migración PRUEBA FENIX).\n"
                "Usá: resumen reservas · resumen asis · resumen flias · resumen seguimiento"
            )
            return

        # ── Comando resumen seguimiento (solo admin) ─────────────────────
        # Acepta: "resumen seguimiento", "seguimiento 9/5"
        # (había un segundo bloque idéntico e inalcanzable más abajo — eliminado 12/07)
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

        # ── Comando modo alumno (solo admin) — reset sin tocar Airtable ───
        if texto.lower().replace(" ", "") == "modoalumno" and telefono == admin_phone:
            cancelar_seguimiento(telefono)
            cancelar_recordatorios(telefono)
            _cancelar_diagnostico_pendiente(telefono)
            await limpiar_estado_completo(telefono)
            # Pre-setear Aurora + cliente_inscripto para que el router no lo mande a Ivan
            await asignar_variante(telefono)  # crea la fila en ConversacionAB
            # Asegurar el grupo de prueba (tutor + Mateo) para que Aurora
            # reconozca al admin (si 'modo padre' lo borró, se recrea acá).
            from agent.airtable_client import asegurar_grupo_prueba_admin
            _tutor_prueba_id = await asegurar_grupo_prueba_admin(telefono)
            if _tutor_prueba_id:
                await actualizar_estado_flags(telefono, tutor_id=_tutor_prueba_id)
            await actualizar_agent_actual(telefono, "aurora", "cliente_inscripto")
            _admin_modo_padre.add(telefono)  # activar flujo normal para que responda
            await proveedor.enviar_mensaje(
                telefono,
                "Modo alumno ✅\nFamilia de prueba lista (Mateo Lafuente).\nEscribí como si fueras un padre inscripto.\nEscribí 'modo secre' para volver a comandos."
            )
            topic_alumno = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            if topic_alumno:
                await enviar_a_topic(topic_alumno, "⚙️ MODO ALUMNO — reset conversación sin tocar Airtable", telefono=telefono)
            return

        # ── Formulario de reserva completado por un LEAD (Meta Flow → nfm_reply) ──
        # Llega como es_boton + btn_id="flow_completado". Se procesa SIEMPRE (el único
        # Flow que reciben los leads es este); el flag esperando_formulario_reserva solo
        # regula la agenda adentro del handler. Antes, con el flag apagado, el flow_data
        # caía al pipeline como "[formulario]" y se perdía. El alta admin va por su rama.
        if (telefono != admin_phone and getattr(msg, "es_boton", False)
                and (getattr(msg, "btn_id", "") or "") == "flow_completado"):
            _flow_data_r = getattr(msg, "flow_data", None) or {}
            # El contenido del formulario SIEMPRE queda en DB — nunca más un
            # formulario perdido sin rastro (595981941407, 25/07)
            try:
                import json as _json_form
                await guardar_mensaje(
                    telefono, "user",
                    "[formulario reserva] " + _json_form.dumps(_flow_data_r, ensure_ascii=False),
                )
            except Exception as _e_ff:
                logger.error(f"[RESERVA-FORM] no pude guardar el flow_data en DB: {_e_ff}")
            try:
                await procesar_formulario_reserva(telefono, _flow_data_r)
            except Exception as e:
                logger.error(f"[RESERVA-FORM] Error procesando formulario de reserva: {e}")
            return

        # ── Botones del admin ──────────────────────────────────────────────
        if telefono == admin_phone and msg.es_boton:
            # Botones de seguimiento (seg_enviado_recXXX / seg_descartado_recXXX)
            btn_raw_id = getattr(msg, 'btn_id', '') or ''
            # Formulario "cargar niño" completado (Meta Flow → nfm_reply)
            if btn_raw_id == "flow_completado":
                _flow_data = getattr(msg, "flow_data", None) or {}
                if _flow_data.get("flow") == "cargar_nino":
                    try:
                        await procesar_formulario_cargar_nino(telefono, _flow_data)
                    except Exception as e:
                        logger.error(f"[CARGAR-NINO] Error procesando formulario: {e}")
                        await proveedor.enviar_mensaje(telefono, f"Error cargando el alumno: {e}")
                    return
            # Keep-alive ventana 24h: el admin apretó "Sí" → el mensaje entrante
            # ya reabrió la ventana de Meta. Solo confirmamos y cortamos (no se
            # procesa como lead ni se espeja a Telegram).
            if btn_raw_id == "activar_ventana":
                await proveedor.enviar_mensaje(
                    telefono,
                    "Ventana activa ✅ — vas a recibir las alertas urgentes por WhatsApp las próximas 24h."
                )
                logger.info("[KEEPALIVE-VENTANA] Admin reabrió la ventana 24h")
                return
            if btn_raw_id.startswith("seg_enviado_") or btn_raw_id.startswith("seg_descartado_"):
                await _procesar_boton_seguimiento(btn_raw_id)
                return
            # NOTA: el botón legacy "confirmar/rechazar pago" se retiró (auditoría
            # 04-07-26 C2): confirmaba el pago pendiente MÁS RECIENTE de cualquier
            # teléfono. El pago se auto-confirma en _procesar_comprobante desde
            # el flujo actual — un botón viejo ya no dispara nada.

        # ── Modo secre: admin siempre en modo comando, no responde como agente ─
        # Si el admin escribe algo que no matcheó ningún comando arriba, ignorar.
        # Solo "modo padre" activa el flujo normal (diagnóstico/Claude).
        if telefono == admin_phone:
            _texto_admin = texto.strip().lower().replace(" ", "")
            if _texto_admin == "modosecre":
                _admin_modo_padre.discard(telefono)
                msg_secre = (
                    "Modo secre ✅\n\n"
                    "📊 *Resúmenes:*\n"
                    "1. Reservas — sábado próximo\n"
                    "2. Anuncios — métricas Meta\n"
                    "3. Familias — nombre + wa.me\n"
                    "4. Asistencia — quién vino\n"
                    "6. Seguimiento — mensajes post-clase\n"
                    "7. Telegram — reservas + links TG\n"
                    "8. Follow-up — mapa FU\n\n"
                    "👨‍👩‍👧 *Inscripción:*\n"
                    "9. `cargar familia [nombre]`\n\n"
                    "📸 *Fotos:*\n"
                    "10. `fotos 11` / `fotos 15:30`\n"
                    "11. `selfie [nombre]` (o `registrar cara`)\n\n"
                    "🔄 *Modos:*\n"
                    "12. Modo padre — simular lead nuevo\n"
                    "13. Modo alumno — simular inscripto\n\n"
                    "📋 `comandos` — lista completa\n"
                    "Respondé con el número para ejecutar."
                )
                await proveedor.enviar_mensaje(telefono, msg_secre)
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
                # topic_id/_tg_group todavía NO existen acá (se asignan más abajo):
                # usarlos directo crasheaba con UnboundLocalError y el except
                # general borraba la dedup → mensaje duplicado (auditoría A17).
                try:
                    _tg_group_ack = await grupo_telegram_para(telefono)
                    _topic_ack = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=_tg_group_ack)
                    if _topic_ack:
                        await enviar_a_topic(_topic_ack, f"👤 {texto} (esperando diagnóstico)", telefono=telefono, group_override=_tg_group_ack)
                except Exception:
                    pass
                logger.info(f"[DIAG] Padre dijo '{texto}' — ignorando, diagnóstico pendiente")
                return

        # (Transcripción de audio ya se hizo al inicio de la función)


        # ── Preparar nombre para Telegram (se usa después del router) ─────
        _topic_nombre = f"📱 {telefono}"
        try:
            # Niño-eje: el tutor que escribe se busca directo en TUTORES por su
            # CELL LIMPIO — match exacto (antes: rollups de FAMILIAS alineados
            # por índice, con riesgo de desalineación).
            _tut_tg = await buscar_tutor_por_telefono(telefono)
            if _tut_tg:
                _tf_tg = _tut_tg.get("fields", {}) or {}
                _n = (_tf_tg.get("NOMBRE COMPLETO") or _tf_tg.get("NOMBRE") or "").strip()
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
        # Determinar grupo Telegram según el agent_actual persistente (fuente
        # única). No depende del texto ni de Airtable vivo → el topic no rebota.
        _tg_group = await grupo_telegram_para(telefono)
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

        # ── PROMO MADRE: formulario (nombre+apellido responsable, nombre+apellido+fnac hijo) ──
        if (_PROMO_MADRE_ACTIVA
                and telefono in _esperando_formulario_promo
                and texto not in ("[imagen]", "[documento]", "[audio]")
                and texto.lower() not in ("holayosoyfenix", "modo padre", "modopadre")):
            await guardar_mensaje(telefono, "user", texto)
            _esperando_formulario_promo.discard(telefono)

            # Respuesta PRIMERO
            _resp_pm = (
                "¡Muchas gracias! 🎉 Ya estás dentro de la promo 💪\n\n"
                "La promo cubre del *15 de mayo al 15 de julio* 📅\n"
                "¡Nos vemos el sábado! 🌳"
            )
            await guardar_mensaje(telefono, "assistant", _resp_pm)
            await proveedor.enviar_mensaje(telefono, _resp_pm)

            # Guardar en Airtable (2.C-C4: LEADS + FAMILIA A PRUEBA — PRUEBA
            # FENIX ya no se crea; el pago de la promo vive en PAGOS)
            try:
                from agent.airtable_client import obtener_lead_record_id as _olri_pm, _patch as _p_pm, _LEADS as _L_pm
                _rec_pm = await _olri_pm(telefono)
                if _rec_pm:
                    await _p_pm(_L_pm, _rec_pm, {"CONVERSION": ["PAGO"], "PROMOMADRE": True, "PAGO PROMOMADRE": True})
                datos_pm = await extraer_datos_formulario(await obtener_historial(telefono))
                padre_pm = datos_pm.get("padre") or {}
                ninos_pm = datos_pm.get("ninos", [])
                _nom_pm = padre_pm.get("nombre", "")
                _ape_pm = padre_pm.get("apellido", "")
                # ── GRUPO A PRUEBA: TUTOR + NIÑOS (F7.b, registro primario niño-eje) ──
                try:
                    from agent.airtable_client import crear_grupo_a_prueba as _cgap_pm
                    _ninos_pm_fam = [
                        {
                            "nombre": n.get("nombre", ""),
                            "apellido": n.get("apellido", ""),
                            "fecha_nacimiento": n.get("fecha_nacimiento", ""),
                        }
                        for n in ninos_pm if n.get("nombre")
                    ] if ninos_pm else []
                    _tutor_id_pm, _grupo_ninos_pm = await _cgap_pm(
                        telefono=telefono,
                        nombre_tutor=_nom_pm,
                        apellido_tutor=_ape_pm,
                        ninos=_ninos_pm_fam,
                    )
                    logger.info(f"[PROMO-MADRE] Grupo A PRUEBA: tutor={_tutor_id_pm}, niños={_grupo_ninos_pm}")
                except Exception as _e_fam_pm:
                    logger.error(f"[PROMO-MADRE] Error creando grupo A PRUEBA: {_e_fam_pm}")
            except Exception as _e_pm:
                logger.error(f"[PROMO-MADRE] Error Airtable: {_e_pm}")

            # Notificar admin + Telegram
            try:
                await proveedor.enviar_mensaje(admin_phone, f"🎁 PROMO MADRE registrada\n📱 https://wa.me/{telefono}\nDatos: {texto}")
                if topic_id:
                    await enviar_a_topic(topic_id, f"🎁 PROMO MADRE completada — {texto}", telefono=telefono)
            except Exception:
                pass
            logger.info(f"[PROMO-MADRE] Formulario completado: {telefono} — {texto}")
            return

        # ── PROMO MADRE: lead respondió a plantilla O escribe "quiero la promo" ──
        _texto_lower_pm = texto.strip().lower()
        _es_quiero_promo = "quiero" in _texto_lower_pm and "promo" in _texto_lower_pm
        if (_PROMO_MADRE_ACTIVA
                and (_es_quiero_promo or telefono in _leads_promo_madre_enviada)
                and telefono not in _esperando_pago_promo_madre
                and texto.lower() not in ("holayosoyfenix", "modo padre", "modopadre")):
            _leads_promo_madre_enviada.discard(telefono)
            await guardar_mensaje(telefono, "user", texto)
            from agent.airtable_client import obtener_lead_record_id as _olri_pm2
            if not await _olri_pm2(telefono):
                from agent.airtable_client import crear_lead as _cl_pm
                await _cl_pm(telefono)
            _esperando_pago_promo_madre.add(telefono)
            # Marcar BOTON PROMOMADRE en Airtable
            try:
                _rec_btn_fx = await _olri_pm2(telefono)
                if _rec_btn_fx:
                    from agent.airtable_client import _patch as _p_btn_fx, _LEADS as _L_btn_fx
                    await _p_btn_fx(_L_btn_fx, _rec_btn_fx, {"BOTON PROMOMADRE": True})
            except Exception:
                pass
            _resp_banco = (
                "¡Genial! 🎉 Espero tu transferencia para asegurar el lugar "
                "de tu hijo/a porque quedan pocos cupos!\n\n"
                "🏦 *Datos bancarios:*\n"
                "Alias | CI 1604338\n"
                "Itaú | Iván Lafuente\n\n"
                "💰 *Promo Madre: 350.000 Gs*\n"
                "✅ 2 meses de clases\n"
                "✅ Matrícula exonerada\n\n"
                "Enviame la foto del comprobante cuando hagas la transferencia 📸"
            )
            await guardar_mensaje(telefono, "assistant", _resp_banco)
            await proveedor.enviar_mensaje(telefono, _resp_banco)
            if topic_id:
                await enviar_a_topic(topic_id, "🎁 Lead respondió a promo madre", telefono=telefono)
            logger.info(f"[PROMO-MADRE] {telefono} respondió a plantilla")
            return

        # ── PROMO MADRE: comprobante ──
        if _PROMO_MADRE_ACTIVA and telefono in _esperando_pago_promo_madre and texto in ("[imagen]", "[documento]"):
            await guardar_mensaje(telefono, "user", texto)
            _esperando_pago_promo_madre.discard(telefono)
            _leads_promo_madre_enviada.discard(telefono)
            _esperando_formulario_promo.add(telefono)

            # Reenviar imagen al admin
            if msg.media_id and hasattr(proveedor, "enviar_imagen"):
                await proveedor.enviar_imagen(admin_phone, msg.media_id, caption=f"🎁 Comprobante PROMO MADRE — {telefono}")

            # Espejo Telegram
            if topic_id and msg.media_id:
                try:
                    _mb_pm, _mm_pm = await descargar_audio_whatsapp(msg.media_id)
                    if _mb_pm:
                        await enviar_media_a_topic(topic_id=topic_id, media_bytes=_mb_pm, tipo="imagen",
                                                   caption=f"🎁 Comprobante PROMO MADRE", telefono=telefono)
                except Exception:
                    pass

            _msg_gracias_pm = "¡Muchas gracias por tu pago! 🎉\n\nAhora necesito los datos para registrar:"
            _msg_form_pm = (
                "Completá los datos 👇\n\n"
                "• Nombre y apellido del responsable\n"
                "• Nombre y apellido del hijo/a\n"
                "• Fecha de nacimiento del hijo/a"
            )
            await proveedor.enviar_mensaje(telefono, _msg_gracias_pm)
            await guardar_mensaje(telefono, "assistant", _msg_gracias_pm)
            await proveedor.enviar_mensaje(telefono, _msg_form_pm)
            await guardar_mensaje(telefono, "assistant", _msg_form_pm)

            await proveedor.enviar_mensaje(admin_phone, f"🎁 *PROMO MADRE — Pago recibido*\nLead: {telefono}\nMonto: 350.000 Gs")
            if topic_id:
                await enviar_a_topic(topic_id, "🎁 Comprobante promo madre — formulario enviado", telefono=telefono)
            logger.info(f"[PROMO-MADRE] Comprobante recibido de {telefono}")
            return

        # ── Detección de comprobante de pago ───────���─────────────────────
        # Ventana amplia (50): la detección exige el CI bancario en el historial;
        # si el padre chateó 20+ mensajes tras recibir los datos, el CI salía de
        # la ventana default y el comprobante no se detectaba (auditoría A6).
        historial_pago = await obtener_historial(telefono, limite=50)
        if es_posible_comprobante(texto, historial_pago):
            await _procesar_comprobante(telefono, texto, msg.media_id, historial_pago, topic_id, _tg_group)
            return

        # Imagen/documento de alguien que YA pagó: puede ser un pago nuevo
        # (cuota, hermano, inscripción) — avisar al admin y seguir el flujo
        # normal, sin disparar nada automático (auditoría 2026-07-12, A3).
        from agent.pagos import es_segundo_comprobante
        if es_segundo_comprobante(texto, historial_pago):
            try:
                await enviar_a_topic(
                    topic_id,
                    "💳 OJO: llegó una imagen/documento de un número que YA tiene pago confirmado. "
                    "Puede ser un pago nuevo (cuota, hermano, inscripción) — revisar manualmente.",
                    telefono=telefono,
                    group_override=_tg_group,
                )
            except Exception as _e_2c:
                logger.warning(f"[PAGOS] No se pudo avisar segundo comprobante de {telefono}: {_e_2c}")

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
            # Padres inscriptos no tienen restricción nocturna (niño-eje:
            # decide el tutor por teléfono → hijos con ESTADO, fallback FAMILIAS)
            if not await es_cliente_activo_por_telefono(telefono):
                # De noche el lead SIEMPRE corta acá: antes, el 2do mensaje de la
                # noche (con noche_pendiente ya marcado) caía al flujo normal y
                # Claude respondía a las 2:30 AM — y night_mode respondía OTRA vez
                # a las 06:00 (auditoría 04-07-26 A16). El mensaje "te respondo a
                # las 06:00" sale solo la primera vez; los siguientes solo se
                # guardan (early save) y los responde night_mode a la mañana.
                if not await tiene_noche_pendiente(telefono):
                    await proveedor.enviar_mensaje(telefono, MENSAJE_NOCHE)
                    await guardar_mensaje(telefono, "assistant", MENSAJE_NOCHE)
                    # Espejar mensaje nocturno a Telegram
                    if topic_id:
                        await enviar_a_topic(topic_id, f"🌙 IVAN: {MENSAJE_NOCHE}", telefono=telefono, group_override=_tg_group)
                await asignar_variante(telefono)
                await _flush_referral_pendiente(telefono)
                await marcar_noche_pendiente(telefono)
                return

        # ── Obtener historial (20 msgs — suficiente para contexto, reduce costos API)
        historial = await obtener_historial(telefono, limite=20)
        # El mensaje actual ya se guardó arriba (early save) y brain.py lo agrega
        # de nuevo al final de messages: sin este recorte, Claude veía el último
        # mensaje del padre DUPLICADO en cada llamada, y la extracción de
        # nombre/edad (que hace historial + [texto]) lo veía dos veces
        # (auditoría 04-07-26 A1). historial = solo lo ANTERIOR al mensaje actual.
        if historial and historial[-1].get("role") == "user" and historial[-1].get("content") == texto:
            historial = historial[:-1]

        # ── Asignar variante (crea fila en ConversacionAB si no existe) ───
        _, es_nuevo = await asignar_variante(telefono)
        # Persistir el referral CTWA capturado arriba (la fila recién ahora existe)
        await _flush_referral_pendiente(telefono)

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

        # ── El modo (leads/alumno) lo decide SIEMPRE el router por teléfono ──
        # (abajo). La palabra "aurora" en el texto ya NO fuerza nada: confundía
        # el botón "Hablar con Aurora" con "soy familia" y creaba fichas fantasma.

        # ── Lead nuevo: router leads/alumno por teléfono ──────────────────
        if es_nuevo:
            if agent_actual != "aurora":
                # Niño-eje: tutor por teléfono → hijos con ESTADO (fallback FAMILIAS)
                if await es_cliente_activo_por_telefono(telefono):
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

        # ── Factura post-pago: interceptación determinística ──────────────
        # El flag pago_esperando_factura convive con el flujo de agenda
        # (modo_agenda fuerza gestionar_prueba en el brain) → la respuesta de
        # factura (botón 🧾, la palabra "factura" o los datos de RUC) se corta
        # ACÁ, antes de los menús y del brain. Señales ambiguas ("si", "no")
        # siguen de largo: pueden ser respuesta a la agenda.
        _flags_factura = await obtener_estado_flags(telefono)
        if _flags_factura.get("pago_esperando_factura") or _flags_factura.get("factura_esperando_datos"):
            from agent.facturas import manejar_respuesta_factura
            _resp_factura = await manejar_respuesta_factura(
                telefono, texto, getattr(msg, "btn_id", None), _flags_factura, proveedor)
            if _resp_factura is not None:
                await guardar_mensaje(telefono, "assistant", _resp_factura)
                if topic_id:
                    await enviar_a_topic(topic_id, f"🧾 AURORA: {_resp_factura}",
                                         telefono=telefono, group_override=_tg_group)
                logger.info(f"[FACTURA] {telefono}: respuesta de factura interceptada")
                return {"status": "ok"}

        # ── Menú de botones para leads nuevos (Aurora, estilo Dorita) ─────
        # Reemplaza la apertura conversacional del lead: primer contacto →
        # saludo cortado + botones [Info / Agendar / Hablar]. El menú decide:
        #   - retorna texto → ya respondió este turno (saludo, lista, afiche,
        #     ubicación o puente); cortamos acá, no llamamos al brain.
        #   - retorna None → el lead va en modo conversacional (o ya conversaba,
        #     o es un lead viejo): seguimos el flujo normal de Ivan/Aurora.
        if agent_actual == "ivan":
            _menu_resp = await procesar_menu_lead(
                telefono, texto, proveedor,
                btn_id=getattr(msg, "btn_id", None),
                es_boton=getattr(msg, "es_boton", False),
                es_primer_contacto=(len(historial) == 0),
                topic_id=topic_id,
                tg_group=_tg_group,
            )
            if _menu_resp is not None:
                logger.info(f"[MENU] {telefono}: manejado por menú ({_menu_resp[:40]})")
                return {"status": "ok"}

        # ── Si es Aurora cliente_inscripto: inyectar contexto con sus hijos ──
        contexto_extra = None
        _reservas_airtable = None
        if agent_actual == "aurora" and modo_nixie == "cliente_inscripto":
            # Grupo familiar niño-eje: tutor por teléfono → hijos → tutores.
            # El familia_id guardado (modo padre admin) alimenta el fallback
            # legacy por FAMILIAS dentro de obtener_grupo_familiar.
            fam_id = await obtener_familia_id(telefono)
            grupo = await obtener_grupo_familiar(telefono, familia_id=fam_id or "")

            # ── Menú de botones para inscriptos (Aurora) ──────────────────
            # Si el menú maneja el turno (saludo+botones o una acción como QR),
            # cortamos acá. Si retorna None, sigue el flujo conversacional normal.
            if grupo:
                # ── Confirmación proactiva del sábado (respuesta a la plantilla del jueves) ──
                # Se intercepta ANTES del menú: el "Sí"/"No" de la plantilla y el turno
                # elegido no deben caer en el flujo conversacional ni en el menú genérico.
                from agent.confirmacion_sabado import manejar_respuesta as _manejar_conf_sab
                _flags_sab = await obtener_estado_flags(telefono)
                _resp_sab = await _manejar_conf_sab(
                    telefono, texto,
                    getattr(msg, "btn_id", None),
                    getattr(msg, "es_boton", False),
                    _flags_sab, proveedor,
                    topic_id=topic_id, tg_group=_tg_group,
                )
                if _resp_sab is not None:
                    logger.info(f"[CONF-SAB] {telefono}: {_resp_sab}")
                    return {"status": "ok"}

                _menu_alum = await procesar_menu_inscripto(
                    telefono, texto, proveedor,
                    tutores=grupo["tutores"],
                    nino_ids=[h["id"] for h in grupo["hijos"] if h.get("id")],
                    btn_id=getattr(msg, "btn_id", None),
                    es_boton=getattr(msg, "es_boton", False),
                    es_primer_contacto=(len(historial) == 0),
                    topic_id=topic_id,
                    tg_group=_tg_group,
                )
                if _menu_alum is not None:
                    logger.info(f"[ALUMNO] {telefono}: manejado por menú ({_menu_alum[:40]})")
                    return {"status": "ok"}

            if grupo:
                contexto_extra, _reservas_airtable = await _build_contexto_aurora(
                    grupo["tutores"], grupo["hijos"], telefono)

        # ── Sin delays artificiales — Claude responde directo ────────────
                # El flujo continúa abajo con la llamada normal a generar_respuesta()

        # ── Inyectar instrucción de pitch si tenemos nombre+edad y padre pidió precios ──
        # PERO: si el padre ya dijo SÍ al precio, NO repetir pitch → ir a FASE 3 (cobrar)
        _padre_ya_acepto = False
        if agent_actual == "ivan" and _padre_ya_pidio_precios(historial):
            # Detectar si el padre ya aceptó (dijo "si/dale/ok" DESPUÉS del afiche)
            _vio_afiche = False
            for _m_hist in historial:
                if _m_hist.get("role") == "assistant" and "te paso un afiche" in _m_hist.get("content", "").lower():
                    _vio_afiche = True
                elif _vio_afiche and _m_hist.get("role") == "user":
                    _resp_padre = _m_hist.get("content", "").strip().lower().rstrip("!.,")
                    if _resp_padre in ("si", "sí", "dale", "ok", "bueno", "va", "vamos", "quiero", "me interesa", "claro"):
                        _padre_ya_acepto = True
                        break

            if not _padre_ya_acepto:
                # Solo inyectar pitch si el padre NO aceptó todavía
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
                        "Cerrá con: '¿Qué te parece la idea? ¿Te gustaría regalarte un sábado diferente en el Parque Fenix? 🌳' "
                        "NO des precio todavía. NO preguntes nombre del padre. NO vuelvas al rompehielos. "
                        "NO preguntes qué quiere reforzar.]"
                    )

        # ── FASE 1: mensaje de apertura fijo para leads nuevos de Ivan ─────
        # No llamamos a Claude — el mensaje está hardcodeado y es siempre igual.
        _interceptado = False
        _acciones_interceptadas = []  # lista de acciones a ejecutar post-respuesta
        if es_nuevo and agent_actual == "ivan" and len(historial) == 0:
            _interceptado = True
            respuesta = (
                "Hola! Te saluda el profe Iván.\n\n"
                "Te resumo rápido qué es Fenix Kids Academy.\n\n"
                "Es tu hijo trepando árboles, enfrentando desafíos reales, aprendiendo a superar miedos "
                "y desarrollando confianza a través de experiencias transformadoras.\n\n"
                "Todo esto sucede en nuestra mansión de más de 3.000 m2, rodeada de naturaleza "
                "y frente al río, en el barrio Itá Enramada de Asunción, a 10 min del centro.\n\n"
                "Acá los chicos:\n"
                "💪 Fortalecen su cuerpo\n"
                "🧠 Construyen autoestima y confianza real\n"
                "⚡ Aprenden a adaptarse y resolver situaciones por sí mismos\n\n"
                "Acá los niños van a temblar, llorar, caerse, lastimarse y sentir miedo. "
                "Porque eso es exactamente lo que buscamos en cada entrenamiento, experiencias reales "
                "que le desafíen de verdad a tu hijo. Solo en esa situación ocurre el cambio dentro de "
                "cada niño, cuando se enfrenta a un peligro real y lo supera... descubrir que sí puede "
                "es TRANSFORMADOR.\n\n"
                "Y todo eso mientras se divierten como nunca y construyen recuerdos que les quedan para "
                "siempre... porque trepar una casa del árbol, saltar, ensuciarse y conquistar sus propios "
                "miedos marca la infancia de verdad. 🌳✨\n\n"
                "¿Cómo se llama tu hijo/a y cuántos años tiene?"
            )
            logger.info(f"[FASE1] {telefono}: mensaje de apertura fijo (sin Claude)")

        # ── Intercepción pre-Claude: respuestas fijas que no necesitan IA ──
        # Si el padre pregunta algo que el código puede responder solo,
        # ni llamamos a Claude — ahorra tokens y evita respuestas duplicadas.
        if not _interceptado and agent_actual == "ivan":
            # Leer flags de DB una sola vez (evita N queries)
            _flags = await obtener_estado_flags(telefono)
            _ya_envio_afiche = _flags.get("afiche_enviado", False)
            _ya_envio_hermanos = _flags.get("afiche_hermanos_enviado", False)
            _ya_envio_horarios = _flags.get("afiche_horarios_enviado", False)

            _pide_precios = padre_pregunta_precios(texto)
            _pide_hermanos = padre_pregunta_hermanos(texto)
            _pide_horarios = padre_pregunta_horarios(texto)
            _pide_ubicacion = padre_pregunta_ubicacion(texto)
            _pide_duracion = padre_pregunta_duracion(texto)
            _pide_que_llevar = padre_pregunta_que_llevar(texto)
            _pide_devolucion = padre_pregunta_devolucion(texto)
            _pide_efectivo = padre_pregunta_efectivo(texto)
            _dice_ya_transfiri = padre_dice_ya_transfiri(texto)
            _pide_alias = padre_pregunta_alias(texto)
            _interes_post_diag = (
                _diagnostico_ya_enviado(historial)
                and _padre_muestra_interes(texto)
                and not _ya_envio_afiche
            )

            _hay_intercepcion = (
                _pide_precios or _pide_hermanos or _pide_horarios or _pide_ubicacion or _interes_post_diag
                or _pide_duracion or _pide_que_llevar or _pide_devolucion
                or _pide_efectivo or _dice_ya_transfiri or _pide_alias
            )

            if _hay_intercepcion:
                _interceptado = True
                _partes = []  # texto de respuesta

                # Interés post-diagnóstico → afiche precios (es lo que corresponde)
                if _interes_post_diag and not _pide_precios and not _pide_hermanos:
                    _pide_precios = True  # tratar como pedido de precios

                # Hermanos tiene prioridad sobre precios generales
                if _pide_hermanos and not _ya_envio_hermanos:
                    _acciones_interceptadas.append("afiche_hermanos")
                    _partes.append("Tenemos un plan especial para familias 💪 Te paso el afiche de hermanos")
                elif _pide_hermanos:
                    _partes.append(
                        "👦👦 *Hermanos:*\n"
                        "Prueba: 100mil +50mil c/u extra\n"
                        "Mensual: 240mil +100mil c/u extra\n"
                        "Matrícula: 100mil por niño\n"
                        "¿Cuántos hijos tenés? Así te armo el combo exacto 🤝"
                    )
                elif _pide_precios and not _ya_envio_afiche:
                    _acciones_interceptadas.append("afiche_precios")
                    _partes.append("Te paso un afiche para que veas todas las opciones 😊")
                elif _pide_precios:
                    _partes.append("Prueba: 100mil (1 sábado). Mensual: 240mil (4 sábados) + matrícula 100mil por niño. +50mil/+100mil por hermano 🌳 Padres entran gratis")

                if _pide_horarios and not _ya_envio_horarios:
                    _acciones_interceptadas.append("afiche_horarios")
                    _partes.append("Entrenamos todos los sábados 🌳 Te paso el afiche con los horarios")
                elif _pide_horarios:
                    # OJO: no invitar a ELEGIR horario pre-pago (regla: cobrar
                    # primero, agendar después — auditoría 04-07-26 A13)
                    _partes.append("Turnos de los sábados: 11:00h | 15:30h 🌳 El horario lo confirmamos al reservar — ¿te paso los datos para asegurar el lugar? 🤝")

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
                    _partes.append("La prueba es para venir a conocer el parque y entrenar en familia. No se descuenta de ningún paquete ni se devuelve. Si después se enganchan, compran un paquete aparte. Si no, no hay compromiso 🤝")

                if _pide_efectivo:
                    _partes.append("Podés pagar por transferencia o con tarjeta 💳 Al confirmar tu lugar te paso el alias y el link de pago 😊")

                if _dice_ya_transfiri:
                    _partes.append("Genial! Mandame foto del comprobante así te confirmo 😊")

                if _pide_alias:
                    _partes.append("El alias es el CI: 1604338")

                respuesta = "\n\n".join(_partes)
                logger.info(f"[INTERCEPCIÓN] {telefono}: precios={_pide_precios} horarios={_pide_horarios} ubi={_pide_ubicacion} duracion={_pide_duracion} que_llevar={_pide_que_llevar} devolucion={_pide_devolucion} efectivo={_pide_efectivo} ya_transfiri={_dice_ya_transfiri} alias={_pide_alias}")

        # ── Generar respuesta con Claude (solo si no fue interceptado) ────
        _tool_acciones = []  # inicializar para guards de regex más abajo
        if not _interceptado:
            if _USE_TOOL_USE and agent_actual in ("ivan", "aurora"):
                # Flujo con Tool Use — Ivan y Aurora usan tools distintas
                _tools_lista = TOOLS_AURORA if agent_actual == "aurora" else TOOLS_IVAN
                # Forzar gestionar_reserva cuando Aurora está en flujo de reservas
                _tool_choice_override = None
                _texto_lower = texto.lower().strip()
                # Detectar si el último mensaje del agente ofreció horarios
                _ultimo_agente = ""
                for _m in reversed(historial):
                    if _m.get("role") == "assistant":
                        _ultimo_agente = _m.get("content", "").lower()
                        break
                _agente_ofrecio_horarios = "11:00" in _ultimo_agente or "15:30" in _ultimo_agente
                # Keywords explícitas de reservas
                _keywords_reserva = any(k in _texto_lower for k in (
                    "agendar", "reagendar", "cancelar", "cambiar", "reservar",
                    "11:00", "15:30", "11h", "15h", "sab", "sábado",
                ))
                # Respuesta a oferta de horarios: "11", "15", "si", fecha, etc.
                _responde_horario = _agente_ofrecio_horarios and (
                    re.match(r'^(si|sí|dale|ok|va|11|15|sab)', _texto_lower)
                    or re.search(r'\d{1,2}[/\s:h]', _texto_lower)
                    or re.match(r'^\d{1,2}$', _texto_lower)
                )

                # Ivan: forzar solo cuando modo_agenda está activo (post-pago)
                if agent_actual == "ivan":
                    _flags_ivan = await obtener_estado_flags(telefono)
                    if _flags_ivan.get("modo_agenda"):
                        _tool_choice_override = {"type": "tool", "name": "gestionar_prueba"}
                        logger.info(f"[IVAN] modo_agenda activo — forzando gestionar_prueba para: {texto[:50]}")
                # Aurora: forzar cuando hay keywords o respuesta a horarios
                elif agent_actual == "aurora" and (_keywords_reserva or _responde_horario):
                    _tool_choice_override = {"type": "tool", "name": "gestionar_reserva"}
                    logger.info(f"[AURORA] Forzando gestionar_reserva para: {texto[:50]}")
                respuesta, _tool_acciones = await generar_respuesta(
                    mensaje=texto,
                    historial=historial,
                    agent_actual=agent_actual,
                    contexto_extra=contexto_extra,
                    reservas_airtable=_reservas_airtable,
                    tools=_tools_lista,
                    tool_executor=lambda n, p: ejecutar_tool(n, p, telefono),
                    context={"telefono": telefono, "agent_actual": agent_actual},
                    tool_choice=_tool_choice_override,
                )
                # Procesar acciones de tools
                for _ta in _tool_acciones:
                    _ta_result = _ta["result"]
                    # Afiches: reusar el mecanismo existente
                    _afiche_tipo = _ta_result.get("enviar_afiche")
                    if _afiche_tipo:
                        _afiche_key = f"afiche_{_afiche_tipo}"
                        if _afiche_key not in _acciones_interceptadas:
                            _acciones_interceptadas.append(_afiche_key)
                            _interceptado = True
                            await actualizar_estado_flags(telefono, **{f"{_afiche_key}_enviado": True})
                    # Notificaciones al admin
                    if _ta_result.get("enviar_admin") and _ta_result.get("mensaje_admin"):
                        _admin_phone_tool = os.getenv("ADMIN_PHONE", "")
                        if telefono != _admin_phone_tool:
                            await proveedor.enviar_mensaje(_admin_phone_tool, _ta_result["mensaje_admin"])
                    # QR Check-in: enviar QR al padre cuando se confirma/reagenda reserva.
                    # Solo para LEADS (ivan): las familias inscriptas (aurora) ya NO usan
                    # QR — su check-in de asistencia es facial (Mundo Fenix). El resultado
                    # del lead puede traer reserva_ids por el dual-write a RESERVAS, por eso
                    # se filtra por agent_actual, no por el tipo de id.
                    _reserva_ids = _ta_result.get("reserva_ids", [])
                    if _reserva_ids and agent_actual != "aurora" and (_ta_result.get("agendada") or _ta_result.get("reagendada") or _ta_result.get("confirmada")):
                        try:
                            from agent.qr import generar_qr
                            from agent.airtable_client import marcar_qr_enviado_reserva
                            for _rid in _reserva_ids:
                                _qr_bytes = generar_qr(_rid)
                                _qr_ok = await proveedor.enviar_imagen_bytes(
                                    telefono, _qr_bytes, "image/png",
                                    caption="Mostrá este QR cuando llegues a Fenix Kids Academy 📱"
                                )
                                # Marcar SOLO si el envío salió: antes quedaba
                                # QR ENVIADO=True sin que el padre tenga el QR (M10)
                                if not _qr_ok:
                                    logger.error(f"[QR] Envío falló para {_rid} — NO se marca enviado")
                                    continue
                                await marcar_qr_enviado_reserva(_rid)
                            logger.info(f"[QR] Enviado {len(_reserva_ids)} QR(s) a {telefono}")
                            if topic_id:
                                await enviar_a_topic(topic_id, f"🎟️ QR Reserva enviado ({len(_reserva_ids)})", telefono=telefono, group_override=_tg_group)
                        except Exception as _qr_err:
                            logger.error(f"[QR] Error enviando QR a {telefono}: {_qr_err}")
                        # Limpiar modo_agenda después de confirmar
                        if _ta_result.get("confirmada"):
                            await actualizar_estado_flags(telefono, modo_agenda=False)
                            logger.info(f"[AGENDA] modo_agenda desactivado para {telefono}")
                logger.info(f"[TOOL-USE] {telefono}: {len(_tool_acciones)} tools, interceptado={_interceptado}")
            else:
                # Flujo original: Claude sin tools
                respuesta = await generar_respuesta(
                    mensaje=texto,
                    historial=historial,
                    agent_actual=agent_actual,
                    contexto_extra=contexto_extra,
                    reservas_airtable=_reservas_airtable,
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

            # Guard: si la limpieza dejó la respuesta VACÍA (Claude solo repitió
            # la pregunta que se recortó), no mandar "" a Meta (400 silencioso,
            # lead sin respuesta — auditoría 04-07-26 M4). Fallback neutro.
            if not respuesta:
                respuesta = "Contame en qué te puedo ayudar 😊"
                logger.warning(f"[ANTI-REP] Respuesta quedó vacía tras limpieza para {telefono} — fallback")

        # ── Nota: FAMILIAS FENIX solo se crea en inscripción directa,
        #    no en clase de prueba (los leads tienen su propio flujo). ──

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

        # ── Guards: si un tool ya manejó la acción, no duplicar con regex ──
        _tool_names_used = {ta["tool"] for ta in _tool_acciones} if _tool_acciones else set()

        # ── Detectar registro de nombre del padre/madre por Aurora ─────
        # F7.b: delega en la tool registrar_familia (tutor por CELL LIMPIO,
        # FAMILIAS ya no se escribe).
        if agent_actual == "aurora" and "REGISTRO PADRE:" in respuesta and "registrar_familia" not in _tool_names_used:
            try:
                reg_padre = re.search(r'REGISTRO PADRE:\s*(.+?)(?:\n|$)', respuesta)
                if reg_padre:
                    nombre_completo = reg_padre.group(1).strip()
                    partes_nombre = nombre_completo.split(maxsplit=1)
                    nombre_p = partes_nombre[0] if partes_nombre else ""
                    apellido_p = partes_nombre[1] if len(partes_nombre) > 1 else ""
                    if nombre_p:
                        from agent.tools.registro import registrar_familia as _reg_fam_inline
                        _res_reg = await _reg_fam_inline(telefono, nombre_p, apellido_p)
                        logger.info(f"[REGISTRO] inline: {_res_reg.get('texto') or _res_reg.get('message')}")
            except Exception as e:
                logger.error(f"[REGISTRO] Error actualizando nombre padre/madre: {e}")

        # ── Detectar registro de hijos por Aurora ─────────────────────────
        # F7.b: delega en la tool registrar_hijo (niño linkeado al tutor).
        if agent_actual == "aurora" and "REGISTRO HIJO:" in respuesta and "registrar_hijo" not in _tool_names_used:
            try:
                from agent.tools.registro import registrar_hijo as _reg_hijo_inline
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
                        _res_h = await _reg_hijo_inline(
                            telefono,
                            datos_nino["nombre"],
                            apellido=datos_nino.get("apellido"),
                            fecha_nacimiento=datos_nino.get("fecha_nacimiento"),
                            ci=datos_nino.get("ci"),
                            talla_remera=datos_nino.get("talla_remera"),
                        )
                        if _res_h.get("registrado"):
                            logger.info(f"[AURORA] Niño creado: {datos_nino.get('nombre')} (tutor {_res_h.get('tutor_id')})")
                        else:
                            logger.warning(f"[AURORA] Niño NO creado ({datos_nino.get('nombre')}): {_res_h.get('message')}")
            except Exception as e:
                logger.error(f"[AURORA] Error creando niño: {e}")

        # ── Detectar cancelación de reserva por Aurora ─────────────────────
        if agent_actual == "aurora" and "cancelé la reserva" in respuesta.lower() and "gestionar_reserva" not in _tool_names_used:
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
                        # F7.b: cancela por el grupo familiar (links del niño) —
                        # el camino viejo por FAMILIAS nunca matcheaba reservas.
                        from agent.tools.agenda import gestionar_reserva as _gr_cancel
                        _res_cancel = await _gr_cancel(telefono, "cancelar", fecha=_fecha_iso, hora=_hora_cancel or None)
                        logger.info(f"[CANCELAR] {_res_cancel.get('cantidad_borradas', 0)} reservas canceladas para {telefono} el {_fecha_iso} {_hora_cancel}")
            except Exception as e:
                logger.error(f"[CANCELAR] Error cancelando reserva: {e}")

        # ── Detectar confirmación de reserva (Ivan o Aurora) ───────────────
        # Guard: para Ivan, solo procesar si el lead YA pagó (comprobante recibido).
        # Sin esto, frases pre-pago como "tiene su lugar el sábado X" disparan
        # notificación de agenda + PAGO en Airtable antes de que el lead pague.
        confirmaciones = _detectar_confirmacion_aurora(respuesta) if "gestionar_reserva" not in _tool_names_used and "gestionar_prueba" not in _tool_names_used else []
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
        if agent_actual == "ivan" and "programar_llamada" not in _tool_names_used:
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

        # ── (M3) La respuesta se guarda AL ENVIARSE, en cada rama de abajo.
        # Antes se guardaba acá (pre-decisión) y el historial mentía: fila
        # duplicada en el camino silencio, "Reserva confirmada" guardado con
        # texto distinto al enviado, y respuesta guardada que nunca se envió
        # en el camino afiche (auditoría 04-07-26 M3).

        # ── Marcar CONVERSION=CONTACTADO si Ivan mandó datos bancarios ──
        if agent_actual == "ivan" and CI_BANCARIO in respuesta:
            try:
                await actualizar_conversion_lead(telefono, "CONTACTADO")
                await _resetear_seguimiento(telefono)
            except Exception as e:
                logger.error(f"[FOLLOWUP] Error marcando CONTACTADO: {e}")

        # ── Detectar si el padre mandó datos del formulario post-pago ──────
        _es_formulario_completo = False
        if agent_actual == "ivan" and not (await obtener_estado_flags(telefono)).get("prueba_creada"):
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
            import re as _re_form
            _meses_texto = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
            # Fecha real: dd/mm/yyyy, dd-mm-yyyy, o nombre de mes — NO confundir con RUC (7dígitos-1dígito)
            _tiene_fecha_slash = bool(_re_form.search(r"\d{1,2}/\d{1,2}", texto))
            _tiene_fecha_guion = bool(_re_form.search(r"\d{1,2}-\d{1,2}-\d{2,4}", texto))
            _tiene_mes_texto = any(m in texto.lower() for m in _meses_texto)
            _tiene_fechas = (_tiene_fecha_slash or _tiene_fecha_guion or _tiene_mes_texto)
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
        if agent_actual == "ivan" and not (await obtener_estado_flags(telefono)).get("afiche_enviado") and not _interceptado:
            _resp_lower = respuesta.lower()
            if "te paso un afiche" in _resp_lower:
                _va_a_enviar_afiche = True
            # NOTA: eliminado el trigger automático por "100.000" en respuesta.
            # Si Claude ya dio precios en texto, no duplicar con afiche encima.

        # ── Detectar SILENCIO: Claude no sabe y dice "te respondo en un minuto" ──
        _es_silencio = "te respondo en un minuto" in respuesta.lower()
        if _es_silencio and not _interceptado:
            logger.warning(f"[SILENCIO] {telefono}: Claude no supo responder, alertando admin")
            # Enviar el mensaje al padre tal cual
            await proveedor.enviar_mensaje(telefono, respuesta)
            await guardar_mensaje(telefono, "assistant", respuesta)
            # Alertar al admin con contexto
            await _alertar_silencio_ivan(telefono, texto, historial)
            # Espejar en Telegram
            if topic_id:
                await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {respuesta}", telefono=telefono, group_override=_tg_group)
            # Salir — no procesar más
            return {"status": "ok"}

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
            await guardar_mensaje(telefono, "assistant", respuesta)
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
        elif _interceptado:
            # Respuesta interceptada por código — enviar texto + afiches
            await guardar_mensaje(telefono, "assistant", respuesta)
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)
            # Ejecutar acciones (enviar afiches)
            for _accion in _acciones_interceptadas:
                if _accion == "afiche_hermanos":
                    await actualizar_estado_flags(telefono, afiche_hermanos_enviado=True)
                    await _enviar_afiche_hermanos_y_followup(telefono, topic_id, _tg_group)
                elif _accion == "afiche_precios":
                    await actualizar_estado_flags(telefono, afiche_enviado=True)
                    await _enviar_afiche_y_followup(telefono, topic_id, _tg_group)
                elif _accion == "afiche_horarios":
                    await actualizar_estado_flags(telefono, afiche_horarios_enviado=True)
                    await _enviar_afiche_horarios(telefono, topic_id, _tg_group)
        elif _va_a_enviar_afiche:
            # Post-diagnóstico interés → afiche precios (el texto de Claude se
            # omite, va la imagen). Se guarda igual el texto "te paso un afiche"
            # porque _padre_ya_pidio_precios lo busca en el historial.
            await guardar_mensaje(telefono, "assistant", respuesta)
            await actualizar_estado_flags(telefono, afiche_enviado=True)
            await _enviar_afiche_y_followup(telefono, topic_id, _tg_group)
        else:
            await guardar_mensaje(telefono, "assistant", respuesta)
            await _delay_humano(respuesta)
            await proveedor.enviar_mensaje(telefono, respuesta)

        # ── Espejo respuesta en Telegram ──────────────────────────────────
        agente_label = "🌟 AURORA" if agent_actual == "aurora" else "👨‍🏫 IVAN"
        if topic_id:
            await enviar_a_topic(topic_id, f"{agente_label}: {respuesta}", telefono=telefono, group_override=_tg_group)

        # ── Materializar al lead si completó el formulario (2.C: sin PRUEBA) ──
        if _es_formulario_completo:
            # Guard (2.C-C2, volteado): el formulario ya se procesó si quedó el
            # flag prueba_creada o si el lead ya tiene una RESERVA futura (señal
            # por familia/reservas, B7). PRUEBA FENIX ya no se consulta.
            _flags_form_g = await obtener_estado_flags(telefono)
            _reservas_fut_g: list[str] = []
            try:
                from agent.airtable_client import obtener_grupo_familiar as _ogf_g, _get_records as _gr_g, _RESERVAS as _RES_G
                from datetime import datetime as _dt_fg
                from zoneinfo import ZoneInfo as _zi_fg
                _grupo_g = await _ogf_g(telefono)
                _rids_g = [rid for h in (_grupo_g or {}).get("hijos", []) for rid in (h.get("reserva_ids") or [])][-20:]
                if _rids_g:
                    _hoy_fg = _dt_fg.now(_zi_fg("America/Asuncion")).date().isoformat()
                    _or_fg = ",".join(f"RECORD_ID()='{r}'" for r in _rids_g)
                    _f_fg = f"OR({_or_fg})" if len(_rids_g) > 1 else _or_fg
                    for _r_fg in await _gr_g(_RES_G, formula=_f_fg, max_records=len(_rids_g)):
                        _fe = _r_fg.get("fields", {}).get("FECHA", "")
                        _fe = (_fe[0] if _fe else "") if isinstance(_fe, list) else _fe
                        if _fe >= _hoy_fg:
                            _reservas_fut_g.append(_r_fg["id"])
            except Exception as _e_fg:
                logger.error(f"[FORMULARIO] Guard reservas: {_e_fg}")

            if _flags_form_g.get("prueba_creada") or _reservas_fut_g:
                logger.info(f"[FORMULARIO] {telefono} ya procesado (flag/reserva futura) — asegurar familia + QR")
                _es_formulario_completo = False
                await actualizar_estado_flags(telefono, prueba_creada=True)
                try:
                    # Asegurar GRUPO A PRUEBA (tutor + niños, F7.b) con los
                    # datos frescos del historial (idempotente)
                    from agent.airtable_client import crear_grupo_a_prueba
                    _hist_upd = await obtener_historial(telefono, limite=40)
                    _datos_upd = await extraer_datos_formulario(_hist_upd)
                    _padre_upd = _datos_upd.get("padre") or {}
                    _ninos_upd = _datos_upd.get("ninos", [])
                    _ninos_fam_upd = [
                        {"nombre": n.get("nombre", ""), "apellido": n.get("apellido", ""),
                         "fecha_nacimiento": n.get("fecha_nacimiento", "")}
                        for n in _ninos_upd if n.get("nombre")
                    ]
                    _tutor_id_upd, _ = await crear_grupo_a_prueba(
                        telefono=telefono,
                        nombre_tutor=_padre_upd.get("nombre", ""),
                        apellido_tutor=_padre_upd.get("apellido", ""),
                        ninos=_ninos_fam_upd,
                    )
                    logger.info(f"[FORMULARIO] Grupo A PRUEBA (guard): tutor={_tutor_id_upd}")
                    # Reenviar el QR de las reservas futuras (antes el guard lo cortaba)
                    try:
                        from agent.qr import generar_qr
                        from agent.airtable_client import marcar_qr_enviado_reserva
                        _qr_enviados_upd = 0
                        for _rid_qr in _reservas_fut_g:
                            _qr_bytes = generar_qr(_rid_qr)
                            _qr_ok = await proveedor.enviar_imagen_bytes(
                                telefono, _qr_bytes, "image/png",
                                caption="Mostrá este QR cuando llegues a Fenix Kids Academy 📱"
                            )
                            if not _qr_ok:
                                logger.error(f"[QR] Envío falló para {_rid_qr} — NO se marca enviado")
                                continue
                            await marcar_qr_enviado_reserva(_rid_qr)
                            _qr_enviados_upd += 1
                        logger.info(f"[QR] Enviado {_qr_enviados_upd} QR(s) post-actualización a {telefono}")
                        if topic_id and _qr_enviados_upd:
                            await enviar_a_topic(topic_id, f"🎟️ QR Reserva enviado ({_qr_enviados_upd})", telefono=telefono, group_override=_tg_group)
                    except Exception as _qr_err:
                        logger.error(f"[QR] Error enviando QR post-actualización: {_qr_err}")
                except Exception as e:
                    logger.error(f"[FORMULARIO] Error en rama guard del formulario: {e}")
        if _es_formulario_completo:
            await actualizar_estado_flags(telefono, prueba_creada=True)
            try:
                from urllib.parse import quote
                admin_phone = os.getenv("ADMIN_PHONE", "")
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
                        # Intentar "sábado X a las Yh" o "Sábado X | Yh"
                        _match_fecha = re.search(r"s[aá]bado\s+(.+?)\s+(?:a las|[|])\s+(\d{1,2}[:h]\d{0,2})", _m_res["content"].lower())
                        if _match_fecha:
                            _fecha_txt = _match_fecha.group(1)  # "16 de mayo"
                            _hora_res = _match_fecha.group(2).replace("h", ":").rstrip(":")
                            # Convertir "16 de mayo" → ISO. Año calculado (el
                            # 2026 hardcodeado era bomba de tiempo para enero
                            # 2027 — auditoría 2026-07-12, A17). Rollover: si
                            # el día/mes ya pasó hace más de una semana, es
                            # del año que viene (reserva siempre futura).
                            _mf = re.match(r"(\d{1,2})\s+de\s+(\w+)", _fecha_txt)
                            if _mf and _mf.group(2) in _MESES_A_NUM:
                                _dia = _mf.group(1).zfill(2)
                                _mes = _MESES_A_NUM[_mf.group(2)]
                                from datetime import date as _date_fr, datetime as _dt_fr, timedelta as _td_fr
                                from zoneinfo import ZoneInfo as _zi_fr
                                _hoy_fr = _dt_fr.now(_zi_fr("America/Asuncion")).date()
                                _anio_fr = _hoy_fr.year
                                try:
                                    if _date_fr(_anio_fr, int(_mes), int(_dia)) < _hoy_fr - _td_fr(days=7):
                                        _anio_fr += 1
                                except ValueError:
                                    pass
                                _fecha_res = f"{_anio_fr}-{_mes}-{_dia}"
                            else:
                                _fecha_res = _fecha_txt  # fallback
                            break
                        # Si tiene "reserva confirmada" pero no matchea fecha, seguir buscando
                fecha_hora = f"el sábado {_fecha_res} a las {_hora_res}" if _fecha_res else "el sábado"

                # ── Materializar el lead (2.C-C2): FAMILIA A PRUEBA + NIÑOS +
                # RESERVA real + QR. PRUEBA FENIX ya no se crea — el dinero ya
                # quedó en PAGOS (registrar_pago_fenix al confirmar el comprobante).
                try:
                    # Usar Haiku para extraer datos completos del historial
                    datos_form = await extraer_datos_formulario(historial_completo)
                    padre_data = datos_form.get("padre") or {}
                    nombre_resp = padre_data.get("nombre", "") or (_np.split()[0] if _np else "")
                    apellido_resp = padre_data.get("apellido", "") or (_np.split()[1] if _np and " " in _np else "")
                    ninos_form = datos_form.get("ninos", [])

                    # GRUPO A PRUEBA: TUTOR + NIÑOS (F7.b, idempotente — el lead
                    # ya puede tenerlo desde el pago). Aurora lo sigue atendiendo
                    # en modo leads hasta que se inscriba.
                    try:
                        from agent.airtable_client import crear_grupo_a_prueba
                        if ninos_form:
                            _ninos_familia = [
                                {
                                    "nombre": n.get("nombre", ""),
                                    "apellido": n.get("apellido", ""),
                                    "fecha_nacimiento": n.get("fecha_nacimiento", ""),
                                }
                                for n in ninos_form if n.get("nombre")
                            ]
                        else:
                            _ninos_familia = [{"nombre": _hijo}] if _hijo else []
                        _tutor_id_pf, _grupo_ninos_pf = await crear_grupo_a_prueba(
                            telefono=telefono,
                            nombre_tutor=nombre_resp,
                            apellido_tutor=apellido_resp,
                            ninos=_ninos_familia,
                        )
                        logger.info(f"[FORMULARIO] Grupo A PRUEBA: tutor={_tutor_id_pf}, niños={_grupo_ninos_pf}")
                    except Exception as _e_fam_pf:
                        logger.error(f"[FORMULARIO] Error creando grupo A PRUEBA: {_e_fam_pf}")

                    # RESERVA real + QR si la reserva ya se confirmó con fecha+hora
                    _reserva_ids_pf: list[str] = []
                    if _fecha_res and _hora_res:
                        try:
                            from agent.tools.agenda import gestionar_reserva
                            from agent.tools.reservas import _parsear_fecha, _vincular_reservas_lead
                            _f_iso = _parsear_fecha(_fecha_res)
                            if _f_iso:
                                _res_pf = await gestionar_reserva(telefono, "agendar", fecha=_f_iso, hora=_hora_res)
                                if _res_pf.get("error"):
                                    logger.warning(f"[A1] Reserva real NO creada para {telefono}: {_res_pf.get('message')}")
                                else:
                                    _reserva_ids_pf = _res_pf.get("reserva_ids", [])
                                    await _vincular_reservas_lead(telefono, _reserva_ids_pf)
                                    logger.info(f"[A1] Reserva real OK para {telefono}: {_f_iso} {_hora_res}")
                        except Exception as _e_res_pf:
                            logger.error(f"[FORMULARIO] Error creando RESERVA real: {_e_res_pf}")

                    # Actualizar LEADS a PAGO
                    await actualizar_conversion_lead(telefono, "PAGO")
                    # CAPI: evento LeadSubmitted + Purchase
                    await enviar_evento_agenda(telefono)
                    await enviar_evento_pago(telefono)
                    logger.info(f"[FORMULARIO] Lead materializado post-formulario (2.C, sin PRUEBA) {telefono}")
                    # QR Check-in por cada RESERVA creada
                    try:
                        from agent.qr import generar_qr
                        from agent.airtable_client import marcar_qr_enviado_reserva
                        _qr_enviados_pf = 0
                        for _rid_pf in _reserva_ids_pf:
                            _qr_bytes = generar_qr(_rid_pf)
                            _qr_ok = await proveedor.enviar_imagen_bytes(
                                telefono, _qr_bytes, "image/png",
                                caption="Mostrá este QR cuando llegues a Fenix Kids Academy 📱"
                            )
                            if not _qr_ok:
                                logger.error(f"[QR] Envío falló para {_rid_pf} — NO se marca enviado")
                                continue
                            await marcar_qr_enviado_reserva(_rid_pf)
                            _qr_enviados_pf += 1
                        logger.info(f"[QR] Enviado {_qr_enviados_pf} QR(s) post-formulario a {telefono}")
                        if topic_id and _qr_enviados_pf:
                            await enviar_a_topic(topic_id, f"🎟️ QR Reserva enviado ({_qr_enviados_pf})", telefono=telefono, group_override=_tg_group)
                    except Exception as _qr_err:
                        logger.error(f"[QR] Error enviando QR post-formulario: {_qr_err}")
                except Exception as e:
                    logger.error(f"[FORMULARIO] Error materializando post-formulario: {e}")
                    # Alertar a Ivan en Telegram para que no se pierda
                    try:
                        if topic_id:
                            await enviar_a_topic(topic_id, f"⚠️ ERROR: No se pudo materializar el formulario — {e}", telefono=telefono, group_override=_tg_group)
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
                # Armar detalle de hijos con fechas de nacimiento
                _hijos_detalle = ""
                if datos_form and datos_form.get("ninos"):
                    _lineas_hijos = []
                    for _n_form in datos_form["ninos"]:
                        _hn = f"{_n_form.get('nombre', '')} {_n_form.get('apellido', '')}".strip()
                        _fn = _n_form.get("fecha_nacimiento", "")
                        _lineas_hijos.append(f"👦 {_hn}" + (f" ({_fn})" if _fn else ""))
                    _hijos_detalle = "\n".join(_lineas_hijos)
                else:
                    _hijos_detalle = f"👦 {_hijo_form or 'hijo/a'}"

                alerta_admin = (
                    f"📋 FORMULARIO COMPLETADO\n\n"
                    f"👤 {_np or 'Lead'}\n"
                    f"{_hijos_detalle}\n"
                    f"📆 {fecha_hora}"
                    f"{_tg_link_reserva}"
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
        registrar_error_webhook(telefono, str(e))
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
    - Ivan (leads): la RESERVA real la crea el flujo post-formulario/reagendamiento
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

    # ── Verificar si es REAGENDAMIENTO ─────────────────────────────────────────
    # Señal OR (migración 2.B/B7): PRUEBA existente (modelo viejo, se corta en
    # 2.C) o familia A PRUEBA con reservas futuras (modelo nuevo). Un lead nuevo
    # en su primera confirmación tiene familia (creada al pagar) pero NO reservas
    # → False, correcto.
    # Señal (2.C-C2): reagendamiento = el lead ya tiene una RESERVA futura.
    # PRUEBA FENIX ya no se consulta. OJO: buscar_reservas_familia (FIND del
    # record_id sobre el link) NUNCA matcheaba — la señal real son los links
    # RESERVAS FENIX de los hijos (niño-eje).
    _es_reagendamiento = False
    _reservas_previas_conf: list[dict] = []
    _tutor_conf_nombre = ""
    if agent_actual == "ivan":
        try:
            from agent.airtable_client import obtener_grupo_familiar as _ogf_c, _get_records as _gr_c, _RESERVAS as _RES_C
            from datetime import datetime as _dt_conf
            from zoneinfo import ZoneInfo as _ZI_conf
            _grupo_c = await _ogf_c(telefono)
            _tuts_c = (_grupo_c or {}).get("tutores") or []
            if _tuts_c:
                _tutor_conf_nombre = f"{_tuts_c[0].get('nombre', '')} {_tuts_c[0].get('apellido', '')}".strip()
            _rids_c = [rid for h in (_grupo_c or {}).get("hijos", []) for rid in (h.get("reserva_ids") or [])][-20:]
            if _rids_c:
                _hoy_conf = _dt_conf.now(_ZI_conf("America/Asuncion")).date().isoformat()
                _or_c = ",".join(f"RECORD_ID()='{r}'" for r in _rids_c)
                _f_c = f"OR({_or_c})" if len(_rids_c) > 1 else _or_c
                for _r_c in await _gr_c(_RES_C, formula=_f_c, max_records=len(_rids_c)):
                    _fc = _r_c.get("fields", {})
                    _fe_c = _fc.get("FECHA", "")
                    _fe_c = (_fe_c[0] if _fe_c else "") if isinstance(_fe_c, list) else _fe_c
                    if _fe_c < _hoy_conf:
                        continue
                    _ho_c = _fc.get("HORA", "")
                    _ho_c = (_ho_c[0] if _ho_c else "") if isinstance(_ho_c, list) else _ho_c
                    _no_c = _fc.get("NOMBRE COMPLETO", "")
                    _no_c = (_no_c[0] if _no_c else "") if isinstance(_no_c, list) else _no_c
                    _reservas_previas_conf.append({"fecha": _fe_c, "hora": _ho_c, "nombre": _no_c})
            _es_reagendamiento = len(_reservas_previas_conf) > 0
        except Exception as _e_reag:
            logger.warning(f"[REAGENDAR] Señal reservas falló para {telefono}: {_e_reag}")

    # Solo Ivan toca LEADS FENIX — Aurora NUNCA toca LEADS ni PRUEBA
    if agent_actual == "ivan" and not _es_reagendamiento:
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

    # ── Obtener niños del grupo familiar (para nombre real + RESERVAS) ────────
    # F7.b: tutor → hijos (fallback legacy FAMILIAS adentro de obtener_grupo_familiar)
    from agent.airtable_client import obtener_grupo_familiar as _ogf_res
    _grupo_res = await _ogf_res(telefono, familia_id=(await obtener_familia_id(telefono)) or "")
    ninos = (_grupo_res or {}).get("hijos", [])

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
                    # Detectar reserva doble (mismo niño, mismo día, otro horario)
                    from agent.airtable_client import _get_records as _gr_dup, _RESERVAS as _RES_DUP
                    _nid = nino["id"]
                    _reservas_dia = await _gr_dup(
                        _RES_DUP,
                        formula=f"AND(FIND('{_nid}', ARRAYJOIN({{NINO}})), DATESTR({{FECHA}})='{fecha_iso}')",
                        max_records=5,
                    )
                    if _reservas_dia:
                        # Ya tiene reserva ese día — alertar admin
                        _horas_existentes = [r.get("fields", {}).get("HORA", ["?"])[0] if isinstance(r.get("fields", {}).get("HORA"), list) else r.get("fields", {}).get("HORA", "?") for r in _reservas_dia]
                        _admin_phone_dup = os.getenv("ADMIN_PHONE", "")
                        _nombre_nino = nino.get("nombre_completo") or nino.get("nombre") or "?"
                        await proveedor.enviar_mensaje(
                            _admin_phone_dup,
                            f"⚠️ RESERVA DOBLE\n{_nombre_nino} ya tiene reserva el {fecha_iso} a las {', '.join(_horas_existentes)}.\nSe intentó agregar a las {hora_str}.\n📱 https://wa.me/{telefono}"
                        )
                        logger.warning(f"[RESERVA DOBLE] {_nombre_nino} ya tiene reserva {fecha_iso} {_horas_existentes}, nueva {hora_str}")

                    rid = await crear_reserva(nino["id"], horario_id)
                    if rid:
                        logger.info(f"Reserva creada: {nino.get('nombre_completo', nino['id'])} → {rid}")
            else:
                logger.warning(f"No se pudo obtener/crear HORARIO {fecha_airtable} {hora_str}")
        except Exception as e:
            logger.error(f"Error creando RESERVA para {telefono}: {e}")

    # ── Reagendamiento (Ivan): ya tenía RESERVA futura → mover la RESERVA real ──
    # 2.C-C2: PRUEBA FENIX ya no se patchea; _crear_reserva_real(reagendar=True)
    # es incondicional (crea la nueva antes de borrar la vieja, fail-safe).
    if agent_actual == "ivan" and fecha_str and hora_str and _es_reagendamiento:
        try:
            _hora_norm = hora_str.replace("h", "").replace(".", ":")
            if ":" not in _hora_norm:
                _hora_norm = f"{_hora_norm}:00"
            _fecha_anterior = _reservas_previas_conf[0]["fecha"] if _reservas_previas_conf else "?"
            _hora_anterior = _reservas_previas_conf[0]["hora"] if _reservas_previas_conf else "?"
            _hijos_txt = ", ".join(sorted({r["nombre"] for r in _reservas_previas_conf if r.get("nombre")})) or nombre_display
            logger.info(f"[REAGENDAR] {_hijos_txt} ({telefono}): {_fecha_anterior} {_hora_anterior} → {fecha_str} {_hora_norm}")

            # Notificar admin por WhatsApp
            _admin_phone_re = os.getenv("ADMIN_PHONE", "")
            _msg_re = (
                f"🔄 REAGENDAMIENTO\n"
                f"👤 {_tutor_conf_nombre or '?'}\n"
                f"👧 {_hijos_txt}\n"
                f"❌ De: {_fecha_anterior} {_hora_anterior}\n"
                f"✅ A: {fecha_str} {_hora_norm}\n"
                f"📱 https://wa.me/{telefono}"
            )
            if telefono != _admin_phone_re:
                await proveedor.enviar_mensaje(_admin_phone_re, _msg_re)
            if fecha_iso:
                from agent.tools.reservas import _crear_reserva_real
                await _crear_reserva_real(telefono, fecha_iso, _hora_norm, reagendar=True)
            return  # No seguir procesando (no crear RESERVAS duplicadas, no actualizar LEADS)
        except Exception as e:
            logger.error(f"[REAGENDAR] Error reagendando RESERVA real: {e}")

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



# ── Cargar familia (comando admin) — extraído a agent/inscripcion.py ──────────


# ── Afiches y follow-up → extraídos a agent/afiches.py ──

# ── Flujo de pagos → extraído a agent/flujo_pagos.py ──
from agent.flujo_pagos import (
    _procesar_comprobante, _cerrar_agenda_desde_telegram,
)


# ── Telegram webhook (admin → WhatsApp) ──────────────────────────────────────

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Recibe mensajes del bot de Telegram y los reenvía al WhatsApp del lead.
    Permite a Ivan responder manualmente desde Telegram.
    Auth: si TELEGRAM_WEBHOOK_SECRET está seteado, se exige el header
    X-Telegram-Bot-Api-Secret-Token (Telegram lo manda desde que el webhook
    se registró con secret_token). Sin la variable → fail-open con warning,
    para no romper prod antes de cargarla (mismo patrón que la firma Meta).
    """
    try:
        _tg_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        if _tg_secret:
            import hmac as _hmac_tg
            _header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not _hmac_tg.compare_digest(_header, _tg_secret):
                logger.warning("[TELEGRAM] webhook rechazado: secret token inválido o ausente")
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403, content={"error": "forbidden"})
        else:
            logger.warning("[TELEGRAM] TELEGRAM_WEBHOOK_SECRET no configurado — webhook SIN auth (cargar la variable y re-registrar via /telegram/setup)")

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
            await actualizar_estado_flags(telefono, registro_ya_iniciado=False)
            await reactivar_dorita(telefono)
            await enviar_a_topic(thread_id, "🔄 Conversación reseteada + agente activado.\nUsá /registro para iniciar registro.", telefono=telefono, group_override=_tg_grp)
            return {"status": "ok"}

        # /registro — verificar datos o registrar familia desde Telegram
        # F7.b: resuelve el grupo familiar (tutor → hijos, fallback legacy);
        # si no hay nadie, Aurora pide el nombre y el tutor se crea recién con
        # la respuesta (registrar_familia) — ya no se crea una FAMILIA vacía.
        if texto_tg.strip() == "/registro":
            logger.info(f"[/registro] telefono={telefono} thread_id={thread_id} chat_id={chat_id}")
            from agent.airtable_client import obtener_grupo_familiar as _ogf_reg
            grupo_reg = await _ogf_reg(telefono)
            logger.info(f"[/registro] grupo={'ENCONTRADO' if grupo_reg else 'NO ENCONTRADO'}")
            # Preparar Aurora para manejar las respuestas
            await actualizar_estado_flags(telefono, registro_ya_iniciado=False)
            await asignar_variante(telefono)
            await actualizar_agent_actual(telefono, "aurora", "cliente_inscripto")
            await reactivar_dorita(telefono)

            if grupo_reg:
                # Nombre para saludar (apodo o primer nombre) — desde TUTORES FENIX
                _tutores_wa = grupo_reg.get("tutores", [])
                _t_wa = next(
                    (t for t in _tutores_wa if telefono in (t.get("cell"), t.get("cell_limpio"))),
                    None,
                ) or next((t for t in _tutores_wa if (t.get("nombre") or "").strip()), None)
                if _t_wa:
                    _ap_wa = (_t_wa.get("apodo") or "").strip()
                    _no_wa = (_t_wa.get("nombre") or "").strip()
                    _nombre_wa = _ap_wa or (_no_wa.split()[0] if _no_wa else "")
                else:
                    _nombre_wa = ""

                # Armar resumen de datos para WhatsApp
                hijos = grupo_reg.get("hijos", [])
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
                # No registrado → Aurora pide el nombre; el tutor se crea con la
                # respuesta (registrar_familia). Ya no se crea FAMILIA vacía (F7.b).
                msg_registro = (
                    "Hola! 🤗 Soy Aurora 🌟, asistente de Fenix Kids.\n"
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




