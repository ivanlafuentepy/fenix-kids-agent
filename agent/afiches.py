# agent/afiches.py — Envío de afiches y follow-up
# Extraído de main.py (refactor paso 7)

import os
import asyncio
import logging

from agent.providers import obtener_proveedor
from agent.memory import obtener_historial, guardar_mensaje
from agent.telegram_bridge import obtener_o_crear_topic, enviar_a_topic
from agent.detectores_conv import _extraer_nombre_hijo_historial, _es_nombre_hijo_valido

logger = logging.getLogger("agentkit")
proveedor = obtener_proveedor()


# ── Afiche de precios ────────────────────────────────────────────────────────

_AFICHE_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "afiche_fenix.png")
_AFICHE_HERMANOS_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "afiche_hermanos.png")
_AFICHE_HORARIOS_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "afiche_horarios.png")
# Guard: afiche_horarios_enviado → persistido en estado_json (DB)

async def _enviar_afiche_horarios(telefono: str, topic_id: int | None, tg_group: int = 0):
    """Envía el afiche de horarios cuando el padre pregunta por frecuencia/días/horarios."""
    try:
        with open(_AFICHE_HORARIOS_PATH, "rb") as f:
            image_bytes = f.read()
        ok = await proveedor.enviar_imagen_bytes(telefono, image_bytes, "image/png")
        if ok:
            logger.info(f"[AFICHE HORARIOS] Imagen enviada a {telefono}")
            await asyncio.sleep(3)
            await proveedor.enviar_mensaje(telefono, "¿Te gustaría agendar un sábado? 🌳")
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


# Detectores de intención del padre → movidos a agent/tools/detectores.py


async def _armar_mensaje_agenda_post_pago() -> str:
    """Arma mensaje determinístico con sábados disponibles para agendar post-pago."""
    from agent.airtable_client import obtener_horarios_disponibles
    from datetime import date

    horarios = await obtener_horarios_disponibles(max_horarios=8)

    # Agrupar por fecha
    fechas = {}
    for h in horarios:
        fecha = h.get("fecha", "")
        hora = h.get("hora", "")
        if fecha and hora:
            if fecha not in fechas:
                fechas[fecha] = []
            fechas[fecha].append(hora)

    if not fechas:
        return (
            "¡Pago recibido ✅ Gracias!\n\n"
            "Para agendar tu clase de prueba, escribime qué sábado y horario te viene mejor 🌳\n\n"
            "Horarios: 11:00h | 15:30h"
        )

    lineas = []
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    for fecha_iso in sorted(fechas.keys()):
        try:
            d = date.fromisoformat(fecha_iso)
            label = f"Sábado {d.day} de {meses[d.month - 1]}"
            horas = " | ".join(f"{h}h" for h in sorted(fechas[fecha_iso]))
            lineas.append(f"• {label} — {horas}")
        except (ValueError, IndexError):
            pass

    sabados_txt = "\n".join(lineas)
    return (
        f"¡Pago recibido ✅ Gracias!\n\n"
        f"Ahora agendamos tu clase de prueba 🌳\n\n"
        f"📅 Sábados disponibles:\n{sabados_txt}\n\n"
        f"¿Qué día y horario te viene mejor?"
    )


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
            f"Por solo 100mil gs ya podés traerle a {nombre_hijo} a probar, o podés inscribirte de una. ¿Cuál te interesa más? 😊\n\n"
            "Te puedo reservar por acá, o si preferís te llamo un rato "
            "así te explico todo 🤝"
        )
    else:
        return (
            "Por solo 100mil gs ya podés venir a probar, o podés inscribirte de una. ¿Cuál te interesa más? 😊\n\n"
            "Te puedo reservar por acá, o si preferís te llamo "
            "un rato así te explico todo 🤝"
        )


async def _enviar_afiche_hermanos_y_followup(telefono: str, topic_id: int | None, tg_group: int = 0):
    """Envía el afiche HERMANOS + descuentos por hijo + CTA."""
    try:
        with open(_AFICHE_HERMANOS_PATH, "rb") as f:
            image_bytes = f.read()

        ok = await proveedor.enviar_imagen_bytes(telefono, image_bytes, "image/png")
        if ok:
            logger.info(f"[AFICHE HERMANOS] Imagen enviada a {telefono}")
        else:
            logger.error(f"[AFICHE HERMANOS] Error enviando imagen a {telefono}")

        await asyncio.sleep(3)

        msg_hermanos = (
            "👦👦 *Hermanos:*\n\n"
            "*Prueba (+50mil c/u extra):*\n"
            "1 hijo: 100.000 Gs\n"
            "2 hermanos: 150.000 Gs\n"
            "3 hermanos: 200.000 Gs\n\n"
            "*Mensual (+100mil c/u extra):*\n"
            "1 hijo: 230.000 Gs\n"
            "2 hermanos: 330.000 Gs\n"
            "3 hermanos: 430.000 Gs\n\n"
            "📋 *Matrícula anual:* 100.000 Gs (una sola vez por familia)"
        )
        await proveedor.enviar_mensaje(telefono, msg_hermanos)
        await guardar_mensaje(telefono, "assistant", msg_hermanos)

        # Espejar en Telegram
        _tid = topic_id
        if not _tid:
            try:
                _tid = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=tg_group)
            except Exception:
                pass
        if _tid:
            await enviar_a_topic(_tid, "👨‍🏫 IVAN: [📸 Afiche HERMANOS enviado]", telefono=telefono, group_override=tg_group)
            await enviar_a_topic(_tid, f"👨‍🏫 IVAN: {msg_hermanos}", telefono=telefono, group_override=tg_group)

        logger.info(f"[AFICHE HERMANOS] Follow-up enviado a {telefono}")

    except FileNotFoundError:
        logger.error(f"[AFICHE HERMANOS] Archivo no encontrado: {_AFICHE_HERMANOS_PATH}")
    except Exception as e:
        logger.error(f"[AFICHE HERMANOS] Error: {e}")


async def _enviar_afiche_y_followup(telefono: str, topic_id: int | None, tg_group: int = 0):
    """Envía el afiche de precios + precios escritos + promo hoy + CTA."""
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

        # Mensaje corto después del afiche
        msg_precios = (
            "🌳 *Probá FENIX (padres entran gratis):*\n\n"
            "👦 *Clase de prueba:* 100.000 Gs (1 sábado)\n"
            "📅 *Mensual:* 230.000 Gs (4 sábados)\n"
            "📋 *Matrícula anual:* 100.000 Gs (una vez por familia)\n\n"
            "+50mil por hermano en prueba | +100mil por hermano en mensual\n\n"
            "¿Querés venir a probar o inscribirte de una?"
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

        logger.info(f"[AFICHE] Follow-up enviado a {telefono}")

    except FileNotFoundError:
        logger.error(f"[AFICHE] Archivo no encontrado: {_AFICHE_PATH}")
    except Exception as e:
        logger.error(f"[AFICHE] Error: {e}")
