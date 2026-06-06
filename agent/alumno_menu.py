# agent/alumno_menu.py — Menú de botones para familias inscriptas (Aurora)
#
# Análogo a lead_menu.py pero para clientes inscriptos. Cuando una familia
# inscripta escribe, Aurora ofrece botones en vez del menú numerado viejo:
#   [📅 Agendar clase] · [📱 QR familia] · [📸 Contenido Fenix]
#
# A diferencia de los leads, los inscriptos SIEMPRE pueden hablar con Aurora
# (texto libre → conversacional). El menú es una ayuda, no un gate:
#   - botón QR familia      → envía el QR fijo de la familia (para check-in al llegar)
#   - botón Agendar/Contenido → (pasos 2 y 3) por ahora caen al flujo conversacional
#   - texto libre            → Aurora conversacional con el contexto de la familia
#
# Paso 1: saludo + botones + QR familia. Contenido y Agendar se completan después.

import logging

from agent.memory import guardar_mensaje
from agent.telegram_bridge import obtener_o_crear_topic, enviar_a_topic
from agent.qr import generar_qr_familia

logger = logging.getLogger("agentkit")


# ── Botones del menú de inscriptos ───────────────────────────────────────────
_BOTONES_ALUMNO = [
    {"id": "alum_qr", "title": "📱 QR familia"},
    {"id": "alum_contenido", "title": "📸 Contenido Fenix"},
]
_TEXTO_BOTONES = "¿En qué te puedo ayudar? 👇"

_ID_A_OPCION = {
    "alum_qr": "qr",
    "alum_contenido": "contenido",
}

# Caption del QR de la familia (mismo QR siempre — para check-in al llegar).
_CAPTION_QR = (
    "Este es el QR de tu familia para Fenix Kids 📱\n"
    "Mostralo cuando llegues y cargamos la asistencia de tus hijos."
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _primer_nombre(familia: dict) -> str:
    """Saca el primer nombre del padre/madre para personalizar el saludo."""
    f = familia.get("fields", {})
    nombre = f.get("NOMBRE PADRE") or f.get("NOMBRE MADRE") or ""
    return nombre.split()[0] if nombre else ""


async def _espejar_telegram(telefono: str, texto: str, topic_id: int | None, tg_group: int):
    _tid = topic_id
    if not _tid:
        try:
            _tid = await obtener_o_crear_topic(telefono, f"📱 {telefono}", group_override=tg_group)
        except Exception:
            _tid = None
    if _tid:
        try:
            await enviar_a_topic(_tid, f"🌟 AURORA: {texto}", telefono=telefono, group_override=tg_group)
        except Exception as e:
            logger.warning(f"[ALUMNO] No se pudo espejar en Telegram: {e}")


async def _enviar_saludo_y_botones(
    telefono: str, proveedor, familia: dict, topic_id: int | None, tg_group: int
):
    """Primer contacto del inscripto: saludo personalizado + botones."""
    nombre = _primer_nombre(familia)
    saludo = f"Hola {nombre}! 🌟 Soy Aurora, tu asistente de Fenix Kids." if nombre \
        else "Hola! 🌟 Soy Aurora, tu asistente de Fenix Kids."
    await proveedor.enviar_botones(telefono, f"{saludo}\n\n{_TEXTO_BOTONES}", _BOTONES_ALUMNO)
    await guardar_mensaje(telefono, "assistant", saludo)
    await _espejar_telegram(telefono, f"{saludo}\n[botones: Agendar / QR / Contenido]", topic_id, tg_group)


async def _enviar_botones(telefono: str, proveedor, texto: str, topic_id: int | None, tg_group: int):
    """Re-muestra los botones del menú con un texto arriba."""
    await proveedor.enviar_botones(telefono, texto, _BOTONES_ALUMNO)
    await _espejar_telegram(telefono, f"{texto}\n[botones: Agendar / QR / Contenido]", topic_id, tg_group)


async def _handle_qr(
    telefono: str, proveedor, familia: dict, topic_id: int | None, tg_group: int
):
    """Envía el QR fijo de la familia + caption, y vuelve a mostrar los botones."""
    familia_id = familia.get("id")
    if not familia_id:
        logger.error(f"[ALUMNO] {telefono}: familia sin id, no se puede generar QR")
        return
    try:
        qr_bytes = generar_qr_familia(familia_id)
        await proveedor.enviar_imagen_bytes(telefono, qr_bytes, "image/png", caption=_CAPTION_QR)
        await guardar_mensaje(telefono, "assistant", "[QR de la familia enviado]")
        await _espejar_telegram(telefono, "[📱 QR de la familia enviado]", topic_id, tg_group)
    except Exception as e:
        logger.error(f"[ALUMNO] {telefono}: error generando/enviando QR: {e}")
        await proveedor.enviar_mensaje(telefono, "Tuve un problema generando el QR, probá de nuevo en un ratito 🙏")
    # Volver a ofrecer el menú
    await _enviar_botones(telefono, proveedor, "¿Algo más? 👇", topic_id, tg_group)


async def _handle_contenido(
    telefono: str, proveedor, familia: dict, topic_id: int | None, tg_group: int
):
    """Envía el contenido reciente de los hijos de la familia + las redes de Fenix."""
    from agent.airtable_client import obtener_contenido_de_ninos, obtener_redes

    nino_ids = familia.get("fields", {}).get("NIÑOS FENIX", []) or []
    contenido = await obtener_contenido_de_ninos(nino_ids, max_items=5)
    redes = await obtener_redes()

    partes: list[str] = []
    if contenido:
        partes.append("📸 *Contenido reciente de tus hijos:*")
        for c in contenido:
            red = c.get("red", "")
            partes.append(f"• {red}: {c['link']}" if red else f"• {c['link']}")
    else:
        partes.append("Todavía no tenemos fotos/videos cargados de tus hijos, pero se vienen pronto 📸")

    if redes:
        partes.append("\n📱 *Seguinos en redes:*")
        for r in redes:
            perfil = r.get("perfil", "")
            if not perfil:
                continue
            icono = r.get("icono", "")
            red = r.get("red", "")
            partes.append(f"{icono} {red}: {perfil}".strip())

    msg = "\n".join(partes)
    await proveedor.enviar_mensaje(telefono, msg)
    await guardar_mensaje(telefono, "assistant", msg)
    await _espejar_telegram(telefono, msg, topic_id, tg_group)
    # Volver a ofrecer el menú
    await _enviar_botones(telefono, proveedor, "¿Algo más? 👇", topic_id, tg_group)


# ── Orquestador ──────────────────────────────────────────────────────────────

async def procesar_menu_inscripto(
    telefono: str,
    texto: str,
    proveedor,
    *,
    familia: dict,
    btn_id: str | None = None,
    es_boton: bool = False,
    es_primer_contacto: bool = False,
    topic_id: int | None = None,
    tg_group: int = 0,
) -> str | None:
    """Maneja el menú de botones para una familia inscripta.

    Returns:
        str  → el menú ya respondió este turno; main.py NO debe llamar al brain.
        None → seguir el flujo normal de Aurora conversacional (con contexto).
    """
    # ── Click de botón ────────────────────────────────────────────────────
    if es_boton and btn_id:
        opcion = _ID_A_OPCION.get(btn_id)

        if opcion == "qr":
            await _handle_qr(telefono, proveedor, familia, topic_id, tg_group)
            return "[QR familia]"

        if opcion == "contenido":
            await _handle_contenido(telefono, proveedor, familia, topic_id, tg_group)
            return "[contenido fenix]"

        # btn_id desconocido → flujo conversacional de Aurora.
        return None

    # ── Primer contacto → saludo + botones ────────────────────────────────
    if es_primer_contacto:
        await _enviar_saludo_y_botones(telefono, proveedor, familia, topic_id, tg_group)
        logger.info(f"[ALUMNO] {telefono}: saludo + botones del menú inscripto")
        return "[saludo + menú inscripto]"

    # ── Texto libre → Aurora conversacional (los inscriptos pueden consultar) ──
    return None
