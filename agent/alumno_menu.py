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

# Envío con reintento + fallback a texto plano: si el interactivo no sale, el
# padre igual recibe las opciones (antes se perdía el primer mensaje del lead).
from agent.envio_seguro import enviar_al_padre, enviar_botones_al_padre


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
    En Airtable el nombre puede venir en mayúsculas ("JAZMIN") → Title Case.
    """
    if not tutores:
        return ""
    t = tutores[0]
    nombre = (t.get("nombre") or "").strip()
    return nombre.split()[0].title() if nombre else ""


# ── Saludo simple (determinístico) ───────────────────────────────────────────
# La identidad de quien escribe la decide el SISTEMA (teléfono → Airtable),
# nunca el LLM. Un saludo sin contenido se responde acá con el nombre real del
# tutor que escribe — caso Jazmin 13/08: el historial viejo (lleno de "Jorge",
# el papá) le ganaba al contexto inyectado y Haiku saludaba con el nombre del
# otro tutor. Cualquier mensaje con contenido real sigue al flujo conversacional.

# Al menos un token de núcleo tiene que estar para que sea saludo.
_SALUDO_NUCLEO = {"hola", "holis", "buenas", "buenos", "buen"}
# Tokens de relleno tolerados junto al saludo ("hola aurora", "buen dia, todo bien?").
_SALUDO_RELLENO = {
    "dia", "dias", "tarde", "tardes", "noche", "noches",
    "que", "tal", "como", "estas", "estan", "va", "todo", "bien",
    "aurora", "profe", "fenix", "hey",
}


def _es_saludo_simple(texto: str) -> bool:
    """¿El mensaje es SOLO un saludo? (sin pedido ni contenido real).

    Normaliza: minúsculas, sin acentos, solo letras, letras repetidas
    colapsadas ("Holaaa" → "hola", "Buen diaa" → "buen dia"). Es saludo si
    todos los tokens son de saludo/relleno y al menos uno es del núcleo.
    """
    import unicodedata

    plano = unicodedata.normalize("NFKD", (texto or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    plano = "".join(c if c.isalpha() else " " for c in plano)
    # Colapsar letras consecutivas repetidas (ningún token de saludo las tiene)
    colapsado = []
    for c in plano:
        if not colapsado or colapsado[-1] != c:
            colapsado.append(c)
    tokens = "".join(colapsado).split()

    if not tokens or len(tokens) > 5:
        return False
    if not all(t in _SALUDO_NUCLEO or t in _SALUDO_RELLENO for t in tokens):
        return False
    return any(t in _SALUDO_NUCLEO for t in tokens)


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
    await enviar_botones_al_padre(proveedor, telefono, f"{saludo}\n\n{_TEXTO_BOTONES}", _BOTONES_ALUMNO)
    await guardar_mensaje(telefono, "assistant", saludo)
    await _espejar_telegram(telefono, f"{saludo}\n[botones: Contenido / Hablar con Aurora]", topic_id, tg_group)


async def _enviar_botones(telefono: str, proveedor, texto: str, botones: list[dict], topic_id: int | None, tg_group: int):
    """Muestra los botones indicados con un texto arriba."""
    await enviar_botones_al_padre(proveedor, telefono, texto, botones)
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
    await enviar_al_padre(proveedor, telefono, msg)
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
            await enviar_al_padre(proveedor, telefono, msg)
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

    # ── Saludo simple → respuesta determinística con el nombre de Airtable ──
    # No pasa por Haiku: el nombre sale del tutor que matchea el teléfono.
    if _es_saludo_simple(texto):
        nombre = _primer_nombre(tutores)
        saludo = f"¡Hola {nombre}! 🌟" if nombre else "¡Hola! 🌟"
        await _enviar_botones(telefono, proveedor, f"{saludo}\n\n{_TEXTO_BOTONES}", _BOTONES_ALUMNO, topic_id, tg_group)
        await guardar_mensaje(telefono, "assistant", f"{saludo} {_TEXTO_BOTONES}")
        logger.info(f"[ALUMNO] {telefono}: saludo determinístico ({nombre or 'sin nombre'})")
        return "[saludo determinístico]"

    # ── Texto libre → Aurora conversacional (los inscriptos pueden consultar) ──
    return None
