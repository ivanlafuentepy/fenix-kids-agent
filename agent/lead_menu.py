# agent/lead_menu.py — Menú de botones para leads nuevos (estilo Dorita)
#
# Flujo del primer contacto de un lead:
#   1. Saludo cortado de Aurora + 3 botones:
#        [Info sobre clases] · [Agendar prueba] · [Hablar con Aurora]
#   2. "Info sobre clases" → lista: Precios / Horarios / Ubicación / Agendar / Hablar
#   3. "Agendar prueba" / "Hablar con Aurora" → pasa a modo conversacional (el
#      cerebro de leads actual toma el control, branded Aurora).
#
# Este módulo SOLO maneja la capa de botones. Cuando el lead pasa a conversacional
# (flag persistente menu_estado="conversacional"), el menú se aparta y el resto del
# flujo de main.py (interceptores + brain con TOOLS_IVAN) funciona igual que hoy.

import logging

from agent.memory import guardar_mensaje
from agent.ab_test import obtener_estado_flags, actualizar_estado_flags
from agent.telegram_bridge import obtener_o_crear_topic, enviar_a_topic
from agent.afiches import _enviar_afiche_y_followup, _enviar_afiche_horarios

logger = logging.getLogger("agentkit")


# ── Contenido del menú ───────────────────────────────────────────────────────

# Saludo cortado de Aurora (versión recortada del mensaje FASE 1 del profe Iván,
# rebrandeado a Aurora y sin la pregunta final — ahora la hacen los botones).
SALUDO_AURORA = (
    "Hola! Te saluda Aurora 🌟\n\n"
    "Te resumo rápido qué es Fenix Kids Academy.\n\n"
    "Es tu hijo trepando árboles, enfrentando desafíos reales, aprendiendo a superar "
    "miedos y desarrollando confianza a través de experiencias transformadoras.\n\n"
    "Todo esto sucede en nuestra mansión de más de 3.000 m2, rodeada de naturaleza "
    "y frente al río, en el barrio Itá Enramada de Asunción, a 10 min del centro.\n\n"
    "Acá los chicos:\n"
    "💪 Fortalecen su cuerpo\n"
    "🧠 Construyen autoestima y confianza real\n"
    "⚡ Aprenden a adaptarse y resolver situaciones por sí mismos 🌳"
)

# Botones del menú principal (Meta soporta máximo 3). Títulos <= 20 chars.
_BOTONES_MENU_PRINCIPAL = [
    {"id": "lead_info", "title": "📋 Info sobre clases"},
    {"id": "lead_agendar", "title": "🎯 Agendar prueba"},
    {"id": "lead_aurora", "title": "💬 Hablar con Aurora"},
]
_TEXTO_BOTONES = "¿Qué te gustaría hacer? 👇"

# Lista del submenú "Info sobre clases" (>3 opciones → lista). Títulos <= 24 chars.
_LISTA_INFO_CLASES = [
    {"title": "Info sobre clases", "rows": [
        {"id": "lead_precios", "title": "📅 Precios"},
        {"id": "lead_horarios", "title": "🕐 Horarios"},
        {"id": "lead_ubicacion", "title": "📍 Ubicación"},
        {"id": "lead_agendar", "title": "🎯 Agendar prueba"},
        {"id": "lead_aurora", "title": "💬 Hablar con Aurora"},
    ]},
]
_TEXTO_INFO = "Elegí una opción 👇"
_BOTON_LISTA = "Ver opciones"

# Texto de ubicación (reusado del interceptor existente en main.py).
TEXTO_UBICACION = (
    "📍 FENIX Kids Academy — Parque Fenix dentro de La Casona Lafuente\n"
    "Maestras Paraguayas 2056\n"
    "https://maps.app.goo.gl/nZT5zGA7N8B76xmD6?g_st=iwb"
)

# Mensajes puente al pasar a modo conversacional. El cerebro de leads toma el
# control en el SIGUIENTE mensaje del lead (no se llama al brain en este turno).
PUENTE_AGENDAR = (
    "¡Buenísimo! 🎯 Vamos a agendar la clase de prueba.\n\n"
    "¿Cómo se llama tu hijo/a y cuántos años tiene?"
)
PUENTE_AURORA = (
    "¡Perfecto! 🌟 Contame, ¿en qué te puedo ayudar?"
)

# Mapeo de button_id → opción lógica.
_ID_A_OPCION = {
    "lead_info": "info_clases",
    "lead_precios": "precios",
    "lead_horarios": "horarios",
    "lead_ubicacion": "ubicacion",
    "lead_agendar": "agendar",
    "lead_aurora": "aurora",
}


# ── Helpers de envío ─────────────────────────────────────────────────────────

async def _espejar_telegram(telefono: str, texto: str, topic_id: int | None, tg_group: int):
    """Espeja un mensaje del agente en el topic de Telegram del lead."""
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
            logger.warning(f"[MENU] No se pudo espejar en Telegram: {e}")


async def _enviar_y_registrar(
    telefono: str, texto: str, proveedor, topic_id: int | None, tg_group: int
):
    """Envía un texto por WhatsApp, lo guarda como mensaje del agente y lo espeja."""
    await proveedor.enviar_mensaje(telefono, texto)
    await guardar_mensaje(telefono, "assistant", texto)
    await _espejar_telegram(telefono, texto, topic_id, tg_group)


async def _enviar_saludo_y_botones(
    telefono: str, proveedor, topic_id: int | None, tg_group: int
):
    """Primer contacto: saludo cortado de Aurora + botones del menú principal."""
    await proveedor.enviar_botones(telefono, f"{SALUDO_AURORA}\n\n{_TEXTO_BOTONES}", _BOTONES_MENU_PRINCIPAL)
    await guardar_mensaje(telefono, "assistant", SALUDO_AURORA)
    await _espejar_telegram(telefono, f"{SALUDO_AURORA}\n[botones: Info / Agendar / Hablar]", topic_id, tg_group)


async def _enviar_lista_info(
    telefono: str, proveedor, topic_id: int | None, tg_group: int
):
    """Submenú 'Info sobre clases' como lista desplegable."""
    await proveedor.enviar_lista(telefono, _TEXTO_INFO, _BOTON_LISTA, _LISTA_INFO_CLASES)
    await guardar_mensaje(telefono, "assistant", "[menú: info sobre clases]")
    await _espejar_telegram(telefono, "[lista: Precios / Horarios / Ubicación / Agendar / Hablar]", topic_id, tg_group)


# ── Orquestador principal ────────────────────────────────────────────────────

async def procesar_menu_lead(
    telefono: str,
    texto: str,
    proveedor,
    *,
    btn_id: str | None = None,
    es_boton: bool = False,
    es_primer_contacto: bool = False,
    topic_id: int | None = None,
    tg_group: int = 0,
) -> str | None:
    """Maneja el menú de botones para un lead nuevo.

    Returns:
        str  → el menú ya respondió este turno; main.py NO debe llamar al brain.
        None → el lead va en modo conversacional; main.py sigue el flujo normal
               (interceptores + brain con TOOLS_IVAN, branded Aurora).
    """
    flags = await obtener_estado_flags(telefono)
    menu_estado = flags.get("menu_estado")

    # Ya está conversando con el cerebro de leads → el menú no interviene.
    if menu_estado == "conversacional":
        return None

    # ── Click de botón o ítem de lista ────────────────────────────────────
    if es_boton and btn_id:
        opcion = _ID_A_OPCION.get(btn_id)

        if opcion == "info_clases":
            await _enviar_lista_info(telefono, proveedor, topic_id, tg_group)
            return "[menú: info sobre clases]"

        if opcion == "precios":
            await _enviar_afiche_y_followup(telefono, topic_id, tg_group)
            return "[afiche precios]"

        if opcion == "horarios":
            await _enviar_afiche_horarios(telefono, topic_id, tg_group)
            return "[afiche horarios]"

        if opcion == "ubicacion":
            await _enviar_y_registrar(telefono, TEXTO_UBICACION, proveedor, topic_id, tg_group)
            return TEXTO_UBICACION

        if opcion in ("agendar", "aurora"):
            # Pasa a modo conversacional: el cerebro de leads toma el control
            # en el siguiente mensaje del lead. Este turno enviamos el puente.
            await actualizar_estado_flags(telefono, menu_estado="conversacional")
            puente = PUENTE_AGENDAR if opcion == "agendar" else PUENTE_AURORA
            await _enviar_y_registrar(telefono, puente, proveedor, topic_id, tg_group)
            logger.info(f"[MENU] {telefono} → conversacional (opción={opcion})")
            return puente

        # button_id desconocido → dejar pasar al brain por las dudas.
        return None

    # ── Primer contacto sin estado de menú → saludo + botones ─────────────
    if es_primer_contacto and not menu_estado:
        await _enviar_saludo_y_botones(telefono, proveedor, topic_id, tg_group)
        await actualizar_estado_flags(telefono, menu_estado="menu")
        logger.info(f"[MENU] {telefono}: saludo Aurora + botones del menú principal")
        return "[saludo + menú principal]"

    # ── Texto libre mientras está en el menú → pasar a conversacional ─────
    # El lead escribió en vez de tocar un botón: el brain lo atiende directo.
    if menu_estado == "menu":
        await actualizar_estado_flags(telefono, menu_estado="conversacional")
        logger.info(f"[MENU] {telefono} → conversacional (escribió texto libre)")
        return None

    # Cualquier otro caso → flujo normal (brain).
    return None
