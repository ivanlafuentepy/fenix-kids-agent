# agent/monitor.py — Monitor interno de producción (Capa 1)
# FENIX KIDS ACADEMY
#
# Dos loops asyncio que corren dentro del proceso FastAPI:
#   1. Monitor de conversaciones: detecta leads sin respuesta >10 min
#   2. Monitor de salud: DB, detectores, background tasks, errores webhook
#
# Alerta por Telegram topic. "Todo OK" solo a las 09, 15, 21h PY.

import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, and_, text

from agent.memory import async_session, Mensaje
from agent.telegram_bridge import (
    obtener_o_crear_topic, enviar_a_topic,
)

logger = logging.getLogger("agentkit")

_TZ_PY = ZoneInfo("America/Asuncion")
_INTERVALO_SEGUNDOS = 3600  # 1 hora
_UMBRAL_SIN_RESPUESTA_MIN = 10
_ADMIN_PHONE = os.getenv("ADMIN_PHONE", "595982790407")

# Estado en memoria (se pierde al reiniciar — intencional)
webhook_errors: list[dict] = []
meta_send_errors: list[dict] = []  # Fallos de envío a Meta (401 token muerto, etc.)
_MAX_ERRORS = 100
background_tasks: dict[str, asyncio.Task] = {}

# Topic de Telegram para el monitor (se cachea en memoria)
_monitor_topic_id: int | None = None


def registrar_error_webhook(telefono: str, error: str):
    """Llamar desde el except del webhook en main.py."""
    webhook_errors.append({
        "ts": datetime.utcnow(),
        "telefono": telefono,
        "error": error,
    })
    if len(webhook_errors) > _MAX_ERRORS:
        webhook_errors[:] = webhook_errors[-_MAX_ERRORS:]


def registrar_error_meta(status: int, error: str, contexto: str = "envio"):
    """Llamar desde providers/meta.py cuando un envío a Meta falla (status != 200).

    Esto es lo que el monitor de salud mira para detectar el token muerto (401).
    """
    meta_send_errors.append({
        "ts": datetime.utcnow(),
        "status": status,
        "error": error[:200],
        "contexto": contexto,
    })
    if len(meta_send_errors) > _MAX_ERRORS:
        meta_send_errors[:] = meta_send_errors[-_MAX_ERRORS:]


def _contar_errores_meta() -> dict:
    """Resume los fallos de envío a Meta de la última hora.

    Returns dict con: total, auth (cantidad de 401 = token muerto), otros.
    """
    hace_1h = datetime.utcnow() - timedelta(hours=1)
    recientes = [e for e in meta_send_errors if e["ts"] >= hace_1h]
    auth = sum(1 for e in recientes if e["status"] == 401)
    return {
        "total": len(recientes),
        "auth": auth,
        "otros": len(recientes) - auth,
    }


def _monitor_group_id() -> int:
    """Grupo dedicado de Telegram para alertas del monitor y guardian."""
    return int(os.getenv("TELEGRAM_MONITOR_GROUP_ID", "0"))


async def _obtener_topic_monitor() -> int | None:
    """Obtiene o crea el topic del monitor en el grupo dedicado."""
    global _monitor_topic_id
    if _monitor_topic_id:
        return _monitor_topic_id
    group = _monitor_group_id()
    if not group:
        logger.warning("[MONITOR] TELEGRAM_MONITOR_GROUP_ID no configurado")
        return None
    topic_id = await obtener_o_crear_topic(
        telefono="monitor-fenix",
        nombre="Monitor FENIX",
        group_override=group,
    )
    _monitor_topic_id = topic_id
    return topic_id


async def _enviar_alerta(texto: str):
    """Envía mensaje al topic del monitor en el grupo dedicado."""
    topic_id = await _obtener_topic_monitor()
    if not topic_id:
        logger.warning("[MONITOR] Sin topic de Telegram — alerta descartada")
        return
    group = _monitor_group_id()
    await enviar_a_topic(topic_id, texto, telefono="monitor-fenix", group_override=group)


def _ahora_py() -> datetime:
    return datetime.now(_TZ_PY)


def _en_horario_reporte_ok() -> bool:
    """Solo reportar 'todo OK' a las 09, 15, 21h PY."""
    hora = _ahora_py().hour
    return hora in (9, 15, 21)


# ── Loop 1: Monitor de Conversaciones ────────────────────────────────────────

async def _detectar_sin_respuesta() -> list[dict]:
    """
    Encuentra teléfonos cuyo último mensaje es del user y tiene >10 min sin respuesta.
    Solo mira la última hora para no cargar toda la DB.
    """
    hace_1h = datetime.utcnow() - timedelta(hours=1)
    resultados = []

    async with async_session() as session:
        # Obtener teléfonos activos en la última hora
        stmt = (
            select(Mensaje.telefono)
            .where(Mensaje.timestamp >= hace_1h)
            .group_by(Mensaje.telefono)
        )
        result = await session.execute(stmt)
        telefonos = [row[0] for row in result.all()]

        for tel in telefonos:
            # Excluir admin
            if tel == _ADMIN_PHONE:
                continue

            # Obtener último mensaje de este teléfono
            stmt_ultimo = (
                select(Mensaje)
                .where(and_(
                    Mensaje.telefono == tel,
                    Mensaje.timestamp >= hace_1h,
                ))
                .order_by(Mensaje.timestamp.desc())
                .limit(1)
            )
            result_ultimo = await session.execute(stmt_ultimo)
            ultimo = result_ultimo.scalars().first()

            if not ultimo:
                continue

            # Si el último mensaje es del user y tiene >10 min
            if ultimo.role == "user":
                edad_min = (datetime.utcnow() - ultimo.timestamp).total_seconds() / 60
                if edad_min >= _UMBRAL_SIN_RESPUESTA_MIN:
                    # Truncar contenido para el reporte
                    preview = ultimo.content[:60] + "..." if len(ultimo.content) > 60 else ultimo.content
                    resultados.append({
                        "telefono": tel,
                        "mensaje": preview,
                        "hace_min": int(edad_min),
                    })

    return resultados


def _contar_errores_recientes() -> list[dict]:
    """Cuenta errores webhook de la última hora."""
    hace_1h = datetime.utcnow() - timedelta(hours=1)
    recientes = [e for e in webhook_errors if e["ts"] >= hace_1h]

    # Agrupar por mensaje de error
    conteo: dict[str, int] = {}
    for e in recientes:
        key = e["error"][:80]
        conteo[key] = conteo.get(key, 0) + 1

    return [{"error": k, "count": v} for k, v in conteo.items()]


async def _contar_mensajes_hora() -> tuple[int, int]:
    """Cuenta conversaciones y mensajes de la última hora."""
    hace_1h = datetime.utcnow() - timedelta(hours=1)
    async with async_session() as session:
        # Total mensajes
        stmt_msgs = select(func.count()).select_from(Mensaje).where(Mensaje.timestamp >= hace_1h)
        total_msgs = (await session.execute(stmt_msgs)).scalar() or 0

        # Total conversaciones distintas
        stmt_convs = (
            select(func.count(func.distinct(Mensaje.telefono)))
            .select_from(Mensaje)
            .where(Mensaje.timestamp >= hace_1h)
        )
        total_convs = (await session.execute(stmt_convs)).scalar() or 0

    return total_convs, total_msgs


async def monitor_conversaciones_loop():
    """Loop principal: cada 1 hora revisa conversaciones sin respuesta."""
    # Delay inicial post-deploy para no saturar al arrancar
    await asyncio.sleep(120)
    logger.info("[MONITOR] Loop conversaciones iniciado")

    while True:
        try:
            hora_py = _ahora_py().strftime("%H:%M")
            sin_respuesta = await _detectar_sin_respuesta()
            errores = _contar_errores_recientes()
            total_convs, total_msgs = await _contar_mensajes_hora()

            hay_problemas = bool(sin_respuesta) or bool(errores)

            if hay_problemas:
                # SIEMPRE alertar si hay problemas
                lineas = [f"MONITOR CONVERSACIONES — {hora_py}\n"]
                lineas.append(f"Ultimas 1h: {total_convs} convs, {total_msgs} msgs\n")

                if sin_respuesta:
                    lineas.append("Sin respuesta (>10 min):")
                    for s in sin_respuesta:
                        lineas.append(f"  - {s['telefono']} — \"{s['mensaje']}\" (hace {s['hace_min']} min)")

                if errores:
                    total_err = sum(e["count"] for e in errores)
                    lineas.append(f"\nErrores webhook ({total_err} en ultimas 1h):")
                    for e in errores:
                        lineas.append(f"  - {e['error']} (x{e['count']})")

                await _enviar_alerta("\n".join(lineas))

            elif _en_horario_reporte_ok():
                # "Todo OK" solo 3 veces al día
                await _enviar_alerta(
                    f"MONITOR — {hora_py}\n"
                    f"Todo OK. {total_convs} convs, {total_msgs} msgs en la ultima hora."
                )

        except Exception as e:
            logger.error(f"[MONITOR] Error en loop conversaciones: {e}", exc_info=True)

        await asyncio.sleep(_INTERVALO_SEGUNDOS)


# ── Loop 2: Monitor de Salud ─────────────────────────────────────────────────

async def _check_db() -> str | None:
    """Verifica conectividad con PostgreSQL."""
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return None
    except Exception as e:
        return f"DB caida: {e}"


def _check_detectores() -> list[str]:
    """Verifica que todos los detectores funcionan sin crashear."""
    problemas = []
    try:
        from agent.tools.detectores import (
            padre_pregunta_precios, padre_pregunta_hermanos, padre_pregunta_horarios,
            padre_pregunta_ubicacion, padre_pregunta_duracion, padre_pregunta_que_llevar,
            padre_pregunta_devolucion, padre_pregunta_efectivo, padre_dice_ya_transfiri,
            padre_pregunta_alias,
        )
        detectores = {
            "precios": padre_pregunta_precios,
            "hermanos": padre_pregunta_hermanos,
            "horarios": padre_pregunta_horarios,
            "ubicacion": padre_pregunta_ubicacion,
            "duracion": padre_pregunta_duracion,
            "que_llevar": padre_pregunta_que_llevar,
            "devolucion": padre_pregunta_devolucion,
            "efectivo": padre_pregunta_efectivo,
            "ya_transfiri": padre_dice_ya_transfiri,
            "alias": padre_pregunta_alias,
        }
        for nombre, fn in detectores.items():
            try:
                fn("hola esto es un test")
            except Exception as e:
                problemas.append(f"Detector '{nombre}' crashea: {e}")
    except ImportError as e:
        problemas.append(f"Import detectores falló: {e}")
    return problemas


def _check_background_tasks() -> list[str]:
    """Verifica que los background tasks siguen vivos."""
    problemas = []
    for nombre, task in background_tasks.items():
        if task.done():
            exc = task.exception() if not task.cancelled() else None
            if task.cancelled():
                problemas.append(f"Task '{nombre}' fue cancelado")
            elif exc:
                problemas.append(f"Task '{nombre}' crasheó: {exc}")
            else:
                # Terminó normalmente (puede ser un one-shot, no alertar)
                pass
    return problemas


def _check_prompts_yaml() -> str | None:
    """Verifica que prompts.yaml es parseable."""
    try:
        import yaml
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            return "prompts.yaml está vacío"
        if "system_prompt" not in data and "ivan_prompt" not in data:
            return "prompts.yaml no tiene system_prompt ni ivan_prompt"
        return None
    except FileNotFoundError:
        return "prompts.yaml no encontrado"
    except yaml.YAMLError as e:
        return f"prompts.yaml tiene error de sintaxis: {e}"


async def monitor_salud_loop():
    """Loop de salud: cada 1 hora verifica DB, detectores, tasks, prompts."""
    # Delay inicial (3 min, diferente al de conversaciones)
    await asyncio.sleep(180)
    logger.info("[MONITOR] Loop salud iniciado")

    while True:
        try:
            hora_py = _ahora_py().strftime("%H:%M")
            problemas = []

            # 1. DB
            db_err = await _check_db()
            if db_err:
                problemas.append(db_err)

            # 2. Detectores
            det_errs = _check_detectores()
            problemas.extend(det_errs)

            # 3. Background tasks
            task_errs = _check_background_tasks()
            problemas.extend(task_errs)

            # 4. prompts.yaml
            yaml_err = _check_prompts_yaml()
            if yaml_err:
                problemas.append(yaml_err)

            # 5. Errores webhook acumulados
            errores_recientes = _contar_errores_recientes()
            total_errores = sum(e["count"] for e in errores_recientes)
            if total_errores >= 5:
                problemas.append(f"Acumulación de errores webhook: {total_errores} en la última hora")

            # 6. Fallos de envío a Meta (401 = token muerto, Aurora no responde a los papás)
            meta_errs = _contar_errores_meta()
            if meta_errs["auth"] > 0:
                problemas.append(
                    f"🔴 TOKEN META MUERTO — {meta_errs['auth']} envíos rechazados con 401 en la última hora. "
                    f"Aurora NO está respondiendo a los papás. "
                    f"Acción: renovar META_ACCESS_TOKEN en Railway y REINICIAR el servicio."
                )
            elif meta_errs["otros"] >= 3:
                problemas.append(
                    f"Fallos de envío a Meta: {meta_errs['otros']} en la última hora (no-auth, revisar logs)."
                )

            if problemas:
                lineas = [f"MONITOR SALUD — {hora_py}\n"]
                for p in problemas:
                    lineas.append(f"  - {p}")
                await _enviar_alerta("\n".join(lineas))

            elif _en_horario_reporte_ok():
                await _enviar_alerta(
                    f"SALUD — {hora_py}\n"
                    f"Todo OK. DB conectada, 10 detectores OK, {len(background_tasks)} tasks vivos, "
                    f"prompts.yaml valido, envios Meta OK."
                )

        except Exception as e:
            logger.error(f"[MONITOR] Error en loop salud: {e}", exc_info=True)

        await asyncio.sleep(_INTERVALO_SEGUNDOS)
