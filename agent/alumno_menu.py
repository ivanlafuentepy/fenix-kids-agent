# agent/alumno_menu.py — Menú de botones para familias inscriptas (Aurora)
#
# Análogo a lead_menu.py pero para clientes inscriptos. Cuando una familia
# inscripta escribe, Aurora ofrece botones en vez del menú numerado viejo:
#   [📸 Contenido Fenix] · [💬 Hablar con Aurora]
#
# A diferencia de los leads, los inscriptos SIEMPRE pueden hablar con Aurora
# (texto libre → conversacional). El menú es una ayuda, no un gate:
#   - botón Contenido → envía el contenido reciente de los hijos + redes Fenix
#   - texto libre     → Aurora conversacional con el contexto de la familia
#
# El check-in de asistencia de familias es facial (Mundo Fenix); las familias
# ya NO usan QR — el QR quedó solo para leads.

import logging

from agent.memory import guardar_mensaje
from agent.telegram_bridge import obtener_o_crear_topic, enviar_a_topic

logger = logging.getLogger("agentkit")


# ── Botones del menú de inscriptos ───────────────────────────────────────────
_BOTONES_ALUMNO = [
    {"id": "alum_contenido", "title": "📸 Contenido Fenix"},
    {"id": "alum_aurora", "title": "💬 Hablar con Aurora"},
]
_TEXTO_BOTONES = "¿En qué te puedo ayudar? 👇"

# Botones individuales para armar el menú post-acción (sin repetir el recién usado).
_BTN_CONTENIDO = {"id": "alum_contenido", "title": "📸 Contenido Fenix"}
_BTN_AURORA = {"id": "alum_aurora", "title": "💬 Hablar con Aurora"}

_ID_A_OPCION = {
    "alum_contenido": "contenido",
    "alum_aurora": "aurora",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _primer_nombre(tutores: list[dict]) -> str:
    """Saca el primer nombre de un tutor para personalizar el saludo.

    Niño-eje: recibe los tutores del grupo ya resueltos (obtener_grupo_familiar)
    — el primero es siempre el tutor que matchea el teléfono que escribe.
    """
    if not tutores:
        return ""
    t = tutores[0]
    nombre = (t.get("nombre") or "").strip()
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
    telefono: str, proveedor, tutores: list[dict], topic_id: int | None, tg_group: int
):
    """Primer contacto del inscripto: saludo personalizado + botones."""
    nombre = _primer_nombre(tutores)
    saludo = f"Hola {nombre}! 🌟 Soy Aurora, tu asistente de Fenix Kids." if nombre \
        else "Hola! 🌟 Soy Aurora, tu asistente de Fenix Kids."
    await proveedor.enviar_botones(telefono, f"{saludo}\n\n{_TEXTO_BOTONES}", _BOTONES_ALUMNO)
    await guardar_mensaje(telefono, "assistant", saludo)
    await _espejar_telegram(telefono, f"{saludo}\n[botones: Contenido / Hablar con Aurora]", topic_id, tg_group)


async def _enviar_botones(telefono: str, proveedor, texto: str, botones: list[dict], topic_id: int | None, tg_group: int):
    """Muestra los botones indicados con un texto arriba."""
    await proveedor.enviar_botones(telefono, texto, botones)
    _labels = " / ".join(b["title"].split(" ", 1)[-1] for b in botones)
    await _espejar_telegram(telefono, f"{texto}\n[botones: {_labels}]", topic_id, tg_group)


async def _handle_contenido(
    telefono: str, proveedor, nino_ids: list[str], topic_id: int | None, tg_group: int
):
    """Envía el contenido reciente de los hijos del grupo + las redes de Fenix."""
    from agent.airtable_client import obtener_contenido_de_ninos, obtener_redes

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
    # Tras el contenido, ofrecer hablar con Aurora (sin repetir Contenido).
    await _enviar_botones(telefono, proveedor, "¿Algo más? 👇", [_BTN_AURORA], topic_id, tg_group)


# ── Orquestador ──────────────────────────────────────────────────────────────

async def procesar_menu_inscripto(
    telefono: str,
    texto: str,
    proveedor,
    *,
    tutores: list[dict],
    nino_ids: list[str],
    btn_id: str | None = None,
    es_boton: bool = False,
    es_primer_contacto: bool = False,
    topic_id: int | None = None,
    tg_group: int = 0,
) -> str | None:
    """Maneja el menú de botones para un grupo familiar inscripto (niño-eje:
    recibe tutores e hijos ya resueltos por obtener_grupo_familiar).

    Returns:
        str  → el menú ya respondió este turno; main.py NO debe llamar al brain.
        None → seguir el flujo normal de Aurora conversacional (con contexto).
    """
    # ── Click de botón ────────────────────────────────────────────────────
    if es_boton and btn_id:
        opcion = _ID_A_OPCION.get(btn_id)

        if opcion == "contenido":
            await _handle_contenido(telefono, proveedor, nino_ids, topic_id, tg_group)
            return "[contenido fenix]"

        if opcion == "aurora":
            # Deja al inscripto escribir; el siguiente mensaje va a Aurora conversacional.
            msg = "¡Dale! Contame, ¿en qué te puedo ayudar? 😊"
            await proveedor.enviar_mensaje(telefono, msg)
            await guardar_mensaje(telefono, "assistant", msg)
            await _espejar_telegram(telefono, msg, topic_id, tg_group)
            return "[hablar aurora]"

        # btn_id desconocido → flujo conversacional de Aurora.
        return None

    # ── Primer contacto → saludo + botones ────────────────────────────────
    if es_primer_contacto:
        await _enviar_saludo_y_botones(telefono, proveedor, tutores, topic_id, tg_group)
        logger.info(f"[ALUMNO] {telefono}: saludo + botones del menú inscripto")
        return "[saludo + menú inscripto]"

    # ── Texto libre → Aurora conversacional (los inscriptos pueden consultar) ──
    return None
