# agent/lead_menu.py — Menú de botones para leads nuevos (estilo Dorita)
#
# Flujo del lead: TODO se navega por botones hasta que toca "Hablar con Aurora".
# Mientras tanto NO entra el cerebro conversacional — solo botones.
#
#   1. Foto de La Casona + el relato del DESAFÍO FENIX + 3 botones:
#        [📅 Info y precios] · [🎯 Reservar lugar] · [📞 Agendar llamada]
#   2. "Info y precios" → lista: Precios / Horarios / Ubicación / Agendar / Hablar
#   3. Precios / Horarios / Ubicación → muestran el contenido (afiche + texto) y
#      terminan SIEMPRE con botones: [Agendar prueba] · [Hablar con Aurora] · [Ver más info]
#   4. "Agendar prueba" / "Hablar con Aurora" → recién acá pasa a modo conversacional
#      (el cerebro de leads toma el control, branded Aurora).
#   5. Si el lead escribe texto libre antes de pedir "Hablar con Aurora", se le
#      insiste con los botones (no se pasa a conversacional).
#
# EXCEPCIÓN — el que llega desde el botón "pagar con tarjeta" de la web no entra
# al menú de venta: se le pregunta solo para cuántos hijos es y se le manda el
# link firmado. Ese camino se decide por CONTENIDO (ver viene_de_la_web_a_pagar).
#
# Cuando el lead pasa a conversacional (flag persistente menu_estado="conversacional"),
# el menú se aparta y el resto del flujo de main.py (interceptores + brain con
# TOOLS_IVAN) funciona igual que hoy.

import logging
import os
import unicodedata

from agent.memory import guardar_mensaje
from agent.ab_test import obtener_estado_flags, actualizar_estado_flags
from agent.telegram_bridge import obtener_o_crear_topic, enviar_a_topic
from agent.afiches import _AFICHE_PATH, _AFICHE_HORARIOS_PATH

logger = logging.getLogger("agentkit")

# Envío con reintento + fallback a texto plano: si el interactivo no sale, el
# padre igual recibe las opciones (antes se perdía el primer mensaje del lead).
from agent.envio_seguro import enviar_al_padre, enviar_botones_al_padre


# ── Contenido del menú ───────────────────────────────────────────────────────

# Foto de La Casona que acompaña al saludo: el padre ve DÓNDE entrena su hijo
# antes de leer nada (es el mismo mapa que muestra la web).
_CASONA_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "casona.jpg")


def saludo_desafio() -> str:
    """Primer contacto: cuenta el DESAFÍO FENIX, no la academia en general.

    Es función y no constante porque lleva las fechas del campus vigente, que
    se mueven cada semana — una constante congelaba el campus del deploy.
    Mismo relato que la landing: descubrir / superar / conquistar.
    """
    from agent.desafio import proximo_campus, label_campus
    return (
        "Hola! Te saluda Aurora 🌟\n\n"
        "Te cuento del DESAFÍO FENIX, nuestro campus de 3 días: viernes descubre, "
        "sábado supera y domingo conquista, con el Gran Desafío y el almuerzo en familia.\n\n"
        "Son 3 días donde tu hijo trepa, cruza obstáculos, se cae y se levanta, y se "
        "anima a cosas que no creía poder hacer 🧗\n\n"
        "Todo en La Casona Lafuente, más de 3.000 m² frente al río 🌳\n\n"
        f"📅 Próximo campus: {label_campus(proximo_campus())}"
    )


# Botones del menú principal (Meta soporta máximo 3). Títulos <= 20 chars.
_BOTONES_MENU_PRINCIPAL = [
    {"id": "lead_info", "title": "📅 Info y precios"},
    {"id": "lead_agendar", "title": "🎯 Reservar lugar"},
    {"id": "lead_llamada", "title": "📞 Agendar llamada"},
]
_TEXTO_BOTONES = "¿Qué te gustaría hacer? 👇"

# Botones que aparecen DESPUÉS de mostrar Precios / Horarios / Ubicación.
_BOTONES_POST_INFO = [
    {"id": "lead_agendar", "title": "🎯 Reservar lugar"},
    {"id": "lead_aurora", "title": "💬 Hablar con Aurora"},
    {"id": "lead_volver_info", "title": "📋 Ver más info"},
]
# Botones específicos después de Precios: ofrecen el combo de hermanos.
_BOTONES_POST_PRECIOS = [
    {"id": "lead_combo_hermanos", "title": "🧒 Combo hermanos"},
    {"id": "lead_agendar", "title": "🎯 Reservar lugar"},
    {"id": "lead_aurora", "title": "💬 Hablar con Aurora"},
]
_TEXTO_POST_INFO = "¿Qué querés hacer? 👇"

# Recordatorio cuando el lead escribe texto libre en vez de tocar un botón.
_TEXTO_RECORDATORIO = "Tocá una de las opciones 👇"

# Lista del submenú "Info sobre clases" (>3 opciones → lista). Títulos <= 24 chars.
_LISTA_INFO_CLASES = [
    {"title": "Info sobre clases", "rows": [
        {"id": "lead_precios", "title": "📅 Precios"},
        {"id": "lead_horarios", "title": "🕐 Horarios"},
        {"id": "lead_ubicacion", "title": "📍 Ubicación"},
        {"id": "lead_agendar", "title": "🎯 Reservar lugar"},
        {"id": "lead_aurora", "title": "💬 Hablar con Aurora"},
    ]},
]
_TEXTO_INFO = "Elegí una opción 👇"
_BOTON_LISTA = "Ver opciones"

# Los precios del DESAFÍO dependen del día (anticipada hasta el jueves 23:59) y las
# fechas dependen del campus que se esté vendiendo → estos textos son funciones, no
# constantes: una constante congelaba el precio del deploy y a la semana mentía.

def texto_precios() -> str:
    """Precios del Desafío para el campus vigente (sin pregunta abierta: van botones)."""
    from agent.desafio import proximo_campus, precio_desafio, label_campus
    campus = proximo_campus()
    _monto, anticipada = precio_desafio(1, campus=campus)
    precio = ("💰 *Reservando con anticipación:* 350.000 Gs\n"
              "Precio normal: 550.000 Gs\n"
              if anticipada else
              "💰 *Inversión:* 550.000 Gs\n")
    return (
        "🔥 *DESAFÍO FENIX* — campus de 3 días\n\n"
        "*Viernes:* Descubrir · *Sábado:* Superar · *Domingo:* Conquistar\n\n"
        "El domingo cerramos con el Gran Desafío, almuerzo en familia "
        "(el del niño va incluido) y reconocimiento 🏅\n\n"
        f"{precio}"
        "👦👦 Hermano adicional: +150.000 Gs\n\n"
        f"📅 Próximo campus: {label_campus(campus)}\n"
        "🔥 Cupos limitados — 10 por turno"
    )


def texto_hermanos() -> str:
    """Tabla por cantidad de hijos. Mantiene "1 hijo" / "2 hermanos" a propósito:
    monto_prueba_por_hijos_detallado() usa esas palabras para saltear los afiches
    y no confundir la lista de precios con el monto acordado."""
    from agent.desafio import precio_desafio
    anticipada = precio_desafio(1)[1]
    if anticipada:
        tabla = ("*Con reserva anticipada:*\n"
                 "1 hijo: 350.000 Gs\n"
                 "2 hermanos: 500.000 Gs\n"
                 "3 hermanos: 650.000 Gs\n\n"
                 "*Precio normal:*\n"
                 "1 hijo: 550.000 Gs\n"
                 "2 hermanos: 700.000 Gs\n"
                 "3 hermanos: 850.000 Gs")
    else:
        tabla = ("1 hijo: 550.000 Gs\n"
                 "2 hermanos: 700.000 Gs\n"
                 "3 hermanos: 850.000 Gs")
    return f"👦👦 *Hermanos en el Desafío FENIX:*\n\n{tabla}"


def texto_horarios() -> str:
    """Los 3 días del campus con sus turnos."""
    from agent.desafio import proximo_campus, label_campus
    campus = proximo_campus()
    return (
        f"🔥 *DESAFÍO FENIX* — {label_campus(campus)}\n\n"
        "*VIERNES* (elegís turno)\n17:00 a 18:30  o  19:30 a 20:45\n\n"
        "*SÁBADO* (elegís turno)\n11:00 a 12:30  o  15:30 a 17:00\n\n"
        "*DOMINGO* (todos juntos)\n"
        "12:00 Gran Desafío FENIX\n13:00 Almuerzo en familia\n15:00 Cierre y reconocimiento"
    )

# Texto de ubicación (reusado del interceptor existente en main.py).
TEXTO_UBICACION = (
    "📍 FENIX Kids Academy — Parque Fenix dentro de La Casona Lafuente\n"
    "Maestras Paraguayas 2056\n"
    "https://maps.app.goo.gl/nZT5zGA7N8B76xmD6?g_st=iwb"
)

# Mensajes puente al pasar a modo conversacional. El cerebro de leads toma el
# control en el SIGUIENTE mensaje del lead (no se llama al brain en este turno).
PUENTE_AGENDAR = (
    "¡Buenísimo! 🔥 Vamos a reservar tu lugar en el Desafío FENIX.\n\n"
    "¿Cómo se llama tu hijo/a y cuántos años tiene?"
)
PUENTE_AURORA = (
    "¡Perfecto! 🌟 Contame, ¿en qué te puedo ayudar?"
)

# Mapeo de button_id → opción lógica.
_ID_A_OPCION = {
    "lead_info": "info_clases",
    "lead_volver_info": "info_clases",
    "lead_precios": "precios",
    "lead_horarios": "horarios",
    "lead_ubicacion": "ubicacion",
    "lead_combo_hermanos": "combo_hermanos",
    "lead_agendar": "agendar",
    "lead_aurora": "aurora",
    "lead_llamada": "llamada",
}


# ── Pedido de llamada ────────────────────────────────────────────────────────
# El padre que prefiere hablar antes que escribir. No se le pregunta la hora
# (decisión de Iván 10/08): se le pide el nombre y el profe lo contacta. A Iván
# le llega el aviso con un link de wa.me que ya trae el saludo escrito, así el
# contacto es un clic y no tiene que buscar el número ni acordarse del nombre.
PEDIDO_NOMBRE_LLAMADA = (
    "¡Perfecto! 📞 El profe Iván te contacta en breve.\n\n"
    "¿Cuál es tu nombre?"
)
CONFIRMACION_LLAMADA = (
    "¡Listo {nombre}! Le paso tu contacto al profe Iván, te escribe en un rato 😊\n\n"
    "Mientras tanto, si querés algo más, contame."
)

# Prefijos que el padre suele anteponer al decir su nombre. Se recortan para que
# a Iván no le llegue "soy marta" — no es un parser de intención, es cosmética.
_PREFIJOS_NOMBRE = ("soy ", "me llamo ", "mi nombre es ", "hola soy ", "es ")


def _limpiar_nombre(texto: str) -> str:
    """El nombre tal como lo escribió el padre, sin prefijos ni exceso de largo."""
    limpio = " ".join((texto or "").split())
    bajo = limpio.lower()
    for prefijo in _PREFIJOS_NOMBRE:
        if bajo.startswith(prefijo):
            limpio = limpio[len(prefijo):]
            break
    return limpio.strip(" .,!¡").title()[:40]


# ── Camino directo: el botón "pagar con tarjeta" de la web ───────────────────
# La web (fenixkidsacademy.com y /desafio) abre WhatsApp con un texto FIJO que
# escribimos nosotros en el href, no una frase que el padre inventa. El que
# llega por ahí YA decidió: no se le vuelve a vender, solo falta saber para
# cuántos hijos es y pasarle el link firmado.
#
# Antes caía en el saludo genérico + los botones de venta (endpoint del 10/08
# 04:31): el primer contacto se resolvía por ESTADO, sin mirar el contenido. La
# instrucción del prompt tampoco alcanzaba, porque el mensaje nunca llegaba al
# brain — el menú corta antes.
_FRASE_TARJETA_WEB = "quiero pagar con tarjeta"

SALUDO_TARJETA = (
    "Hola! Te saluda Aurora 🌟 de Fenix Kids.\n\n"
    "Te paso la info para abonar con tarjeta el DESAFÍO FENIX 🔥\n\n"
    "¿Para cuántos hijos es?"
)

# Cuántos hijos, por botón: el monto tiene que ser un dato, no una adivinanza.
_BOTONES_HIJOS_TARJETA = [
    {"id": "tarjeta_1", "title": "1 hijo"},
    {"id": "tarjeta_2", "title": "2 hermanos"},
    {"id": "tarjeta_3", "title": "3 hermanos"},
]
_HIJOS_POR_BTN = {"tarjeta_1": 1, "tarjeta_2": 2, "tarjeta_3": 3}
_HIJOS_POR_PALABRA = {"1": 1, "un": 1, "uno": 1, "una": 1,
                      "2": 2, "dos": 2, "3": 3, "tres": 3}
_TEXTO_RECORDATORIO_HIJOS = "Decime para cuántos hijos es 👇"


def _sin_acentos(texto: str) -> str:
    """Minúsculas y sin tildes — 'Desafío' y 'Desafio' son el mismo mensaje."""
    limpio = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in limpio if unicodedata.category(c) != "Mn")


def viene_de_la_web_a_pagar(texto: str) -> bool:
    """¿Este mensaje es el deep-link de pago con tarjeta de la web?

    Es un match contra NUESTRA propia frase, no un detector de intención nuevo:
    el texto lo escribe el href de fenixkidsacademy.com, igual que _TURNO_POR_BTN
    matchea los ids de botón que mandamos nosotros.
    """
    return _FRASE_TARJETA_WEB in _sin_acentos(texto)


def _hijos_del_mensaje(texto: str, btn_id: str | None, es_boton: bool) -> int | None:
    """Cuántos hijos eligió el padre, o None si no se puede saber.

    Botón primero; si escribió, se acepta un 1/2/3 (o "dos") suelto — match
    contra valores conocidos, del mismo modo que la elección de turnos.
    """
    if es_boton and btn_id in _HIJOS_POR_BTN:
        return _HIJOS_POR_BTN[btn_id]
    for palabra in _sin_acentos(texto).replace(",", " ").split():
        if palabra in _HIJOS_POR_PALABRA:
            return _HIJOS_POR_PALABRA[palabra]
    return None


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
    await enviar_al_padre(proveedor, telefono, texto)
    await guardar_mensaje(telefono, "assistant", texto)
    await _espejar_telegram(telefono, texto, topic_id, tg_group)


async def _enviar_afiche(telefono: str, proveedor, path: str):
    """Envía un afiche (imagen) por WhatsApp. Best-effort: si falla, sigue."""
    try:
        with open(path, "rb") as f:
            await proveedor.enviar_imagen_bytes(telefono, f.read(), "image/png")
    except FileNotFoundError:
        logger.error(f"[MENU] Afiche no encontrado: {path}")
    except Exception as e:
        logger.error(f"[MENU] Error enviando afiche {path}: {e}")


async def _enviar_contenido_con_botones(
    telefono: str, proveedor, contenido: str, topic_id: int | None, tg_group: int,
    botones: list[dict] | None = None,
):
    """Envía un texto informativo + botones (por defecto los post-info) en un solo mensaje."""
    _botones = botones if botones is not None else _BOTONES_POST_INFO
    body = f"{contenido}\n\n{_TEXTO_POST_INFO}"
    await enviar_botones_al_padre(proveedor, telefono, body, _botones)
    await guardar_mensaje(telefono, "assistant", contenido)
    _labels = " / ".join(b["title"].split(" ", 1)[-1] for b in _botones)
    await _espejar_telegram(
        telefono, f"{contenido}\n[botones: {_labels}]", topic_id, tg_group
    )


async def _enviar_saludo_y_botones(
    telefono: str, proveedor, topic_id: int | None, tg_group: int
):
    """Primer contacto: foto de La Casona + el Desafío + botones del menú.

    La foto va primero y es best-effort: si no sale, el saludo se manda igual.
    """
    await _enviar_afiche(telefono, proveedor, _CASONA_PATH)
    saludo = saludo_desafio()
    await enviar_botones_al_padre(proveedor, telefono, f"{saludo}\n\n{_TEXTO_BOTONES}", _BOTONES_MENU_PRINCIPAL)
    await guardar_mensaje(telefono, "assistant", saludo)
    await _espejar_telegram(telefono, f"{saludo}\n[botones: Info y precios / Reservar / Llamada]", topic_id, tg_group)


async def _avisar_pedido_de_llamada(telefono: str, proveedor, nombre: str) -> bool:
    """Le manda a Iván el pedido de llamada con el link para contestar de un clic.

    El wa.me lleva el saludo ya escrito: abrir, enviar y listo. Si el aviso no
    sale, el padre NO puede quedar esperando una llamada que nadie pidió → se
    devuelve False y el flujo lo escala como cualquier otro fallo.
    """
    from urllib.parse import quote

    admin = os.getenv("ADMIN_PHONE", "")
    if not admin:
        logger.error("[LLAMADA] ADMIN_PHONE vacío — no puedo avisar del pedido de llamada")
        return False

    saludo_previo = (f"Hola {nombre}, te saluda el profe Iván de Fenix Kids. "
                     "¿Te puedo llamar ahora?")
    link = f"https://wa.me/{telefono}?text={quote(saludo_previo)}"
    aviso = (
        "📞 *PEDIDO DE LLAMADA*\n\n"
        f"*{nombre}* quiere hablar con vos.\n"
        f"Tel: {telefono}\n\n"
        f"Escribile de un clic:\n{link}"
    )
    try:
        return bool(await proveedor.enviar_mensaje(admin, aviso))
    except Exception as e:
        logger.error(f"[LLAMADA] No pude avisarle a Iván del pedido de {telefono}: {e}")
        return False


async def _enviar_lista_info(
    telefono: str, proveedor, topic_id: int | None, tg_group: int
):
    """Submenú 'Info sobre clases' como lista desplegable."""
    await proveedor.enviar_lista(telefono, _TEXTO_INFO, _BOTON_LISTA, _LISTA_INFO_CLASES)
    await guardar_mensaje(telefono, "assistant", "[menú: info sobre clases]")
    await _espejar_telegram(telefono, "[lista: Precios / Horarios / Ubicación / Agendar / Hablar]", topic_id, tg_group)


async def _enviar_recordatorio_botones(
    telefono: str, proveedor, topic_id: int | None, tg_group: int
):
    """El lead escribió texto libre: se le insiste con los botones del menú principal."""
    await enviar_botones_al_padre(proveedor, telefono, _TEXTO_RECORDATORIO, _BOTONES_MENU_PRINCIPAL)
    await guardar_mensaje(telefono, "assistant", "[recordatorio: tocá una opción]")
    await _espejar_telegram(telefono, "[recordatorio: botones del menú]", topic_id, tg_group)


# ── Handlers de cada opción informativa ──────────────────────────────────────

async def _handle_precios(telefono: str, proveedor, topic_id: int | None, tg_group: int):
    await _enviar_afiche(telefono, proveedor, _AFICHE_PATH)
    # Después de precios ofrecemos el combo de hermanos como botón.
    await _enviar_contenido_con_botones(
        telefono, proveedor, texto_precios(), topic_id, tg_group, botones=_BOTONES_POST_PRECIOS
    )


async def _handle_horarios(telefono: str, proveedor, topic_id: int | None, tg_group: int):
    await _enviar_afiche(telefono, proveedor, _AFICHE_HORARIOS_PATH)
    await _enviar_contenido_con_botones(telefono, proveedor, texto_horarios(), topic_id, tg_group)


async def _handle_combo_hermanos(telefono: str, proveedor, topic_id: int | None, tg_group: int):
    # Solo la info de hermanos (sin afiche — el afiche está desactualizado).
    await _enviar_contenido_con_botones(telefono, proveedor, texto_hermanos(), topic_id, tg_group)


async def _handle_ubicacion(telefono: str, proveedor, topic_id: int | None, tg_group: int):
    await _enviar_contenido_con_botones(telefono, proveedor, TEXTO_UBICACION, topic_id, tg_group)


# ── Handlers del camino de tarjeta ───────────────────────────────────────────

async def _enviar_saludo_tarjeta(
    telefono: str, proveedor, topic_id: int | None, tg_group: int
):
    """Saludo corto + la única pregunta que falta: para cuántos hijos es."""
    await enviar_botones_al_padre(proveedor, telefono, SALUDO_TARJETA, _BOTONES_HIJOS_TARJETA)
    await guardar_mensaje(telefono, "assistant", SALUDO_TARJETA)
    await _espejar_telegram(
        telefono, f"{SALUDO_TARJETA}\n[botones: 1 hijo / 2 hermanos / 3 hermanos]",
        topic_id, tg_group,
    )


async def _avisar_admin_sin_link(telefono: str, proveedor, monto: int):
    """El link de tarjeta no salió: es plata, no puede quedar solo en un log."""
    admin = os.getenv("ADMIN_PHONE", "")
    if not admin or admin == telefono:
        return
    try:
        await proveedor.enviar_mensaje(
            admin,
            f"⚠️ No pude armar el link de tarjeta para https://wa.me/{telefono} "
            f"(Desafío, {monto} Gs). Le pasé los datos de transferencia.",
        )
    except Exception as e:
        logger.error(f"[MENU] Tampoco pude avisarle al admin del link caído: {e}")


async def _enviar_link_tarjeta(
    telefono: str, proveedor, hijos: int, topic_id: int | None, tg_group: int
):
    """Arma el link firmado del Desafío para esa cantidad de hijos y lo manda.

    El monto sale de precio_desafio() — explícito, calculado acá. NO se deja al
    parser del historial (monto_prueba_por_hijos_detallado): la firma del link
    viaja por monto y cobrar de menos no se deshace.

    Deja el Pedido abierto: es lo que hace que /pago-confirmado reconozca el
    cobro como del campus y dispare formulario + reserva de los 3 días.
    """
    from agent.desafio import precio_desafio, proximo_campus, label_campus
    from agent.pagos import formatear_monto, DATOS_BANCARIOS
    from agent.pagos_tarjeta import link_pago_fenix, tarjeta_habilitada
    from agent.memory import crear_o_actualizar_pedido

    campus = proximo_campus()
    monto, anticipada = precio_desafio(hijos, campus=campus)
    cuantos = "tu hijo" if hijos == 1 else f"tus {hijos} hijos"
    monto_txt = f"{formatear_monto(monto)} Gs"

    link = ""
    if tarjeta_habilitada():
        try:
            link = link_pago_fenix(monto, concepto="Desafío FENIX", telefono=telefono)
            await crear_o_actualizar_pedido(
                telefono, tipo="prueba", concepto="DESAFIO", monto_total=monto)
        except Exception as e:
            link = ""
            logger.error(f"[MENU] No pude armar el link de tarjeta de {telefono}: {e}")
    else:
        logger.error("[MENU] LINK_SECRET vacío — no se puede ofrecer tarjeta")

    if link:
        texto = (
            f"Perfecto 🔥 El DESAFÍO FENIX para {cuantos} sale *{monto_txt}*"
            f"{' (reserva anticipada)' if anticipada else ''}.\n\n"
            f"📅 {label_campus(campus)}\n\n"
            f"💳 Pagá con tarjeta acá:\n{link}\n\n"
            "Apenas se acredite te pido los datos de tu hijo y elegimos los turnos 😊"
        )
    else:
        # Sin link no se corta la venta: se sigue por transferencia y se avisa.
        texto = (
            f"Perfecto 🔥 El DESAFÍO FENIX para {cuantos} sale *{monto_txt}*"
            f"{' (reserva anticipada)' if anticipada else ''}.\n\n"
            f"📅 {label_campus(campus)}\n\n"
            "Justo el pago con tarjeta no me está respondiendo, así que te paso "
            f"los datos para transferencia:\n\n{DATOS_BANCARIOS}\n"
            f"Monto: {monto_txt}\n\n"
            "Mandame la foto del comprobante y seguimos 😊"
        )
        await _avisar_admin_sin_link(telefono, proveedor, monto)

    await _enviar_y_registrar(telefono, texto, proveedor, topic_id, tg_group)
    logger.info(f"[TARJETA] {telefono}: {'link' if link else 'transferencia'} "
                f"por {monto} ({hijos} hijo/s) desde el botón de la web")


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

    # ── Camino de tarjeta: esperando saber para cuántos hijos es ──────────
    if menu_estado == "tarjeta":
        hijos = _hijos_del_mensaje(texto, btn_id, es_boton)
        if hijos is None:
            await enviar_botones_al_padre(
                proveedor, telefono, _TEXTO_RECORDATORIO_HIJOS, _BOTONES_HIJOS_TARJETA)
            await guardar_mensaje(telefono, "assistant", _TEXTO_RECORDATORIO_HIJOS)
            await _espejar_telegram(
                telefono, f"{_TEXTO_RECORDATORIO_HIJOS}\n[botones: 1 / 2 / 3 hijos]",
                topic_id, tg_group)
            return "[tarjeta: recordatorio hijos]"
        # Con el link ya enviado el menú se aparta: si el padre pregunta algo,
        # lo atiende el cerebro de leads.
        await _enviar_link_tarjeta(telefono, proveedor, hijos, topic_id, tg_group)
        await actualizar_estado_flags(telefono, menu_estado="conversacional")
        return "[tarjeta: link enviado]"

    # ── Pidió llamada: el mensaje que llega es su nombre ──────────────────
    if menu_estado == "llamada":
        nombre = "" if es_boton else _limpiar_nombre(texto)
        if not nombre:
            await _enviar_y_registrar(
                telefono, "¿Cuál es tu nombre? Así el profe sabe con quién habla 😊",
                proveedor, topic_id, tg_group)
            return "[llamada: repregunta nombre]"

        avisado = await _avisar_pedido_de_llamada(telefono, proveedor, nombre)
        # El espejo en Telegram es la segunda red: si el WhatsApp al admin no
        # salió, el pedido igual queda visible en el topic del lead.
        await _espejar_telegram(
            telefono,
            f"📞 PEDIDO DE LLAMADA — {nombre} ({telefono})"
            f"{'' if avisado else ' ⚠️ NO se pudo avisar por WhatsApp'}",
            topic_id, tg_group)
        if not avisado:
            logger.error(f"[LLAMADA] {telefono} ({nombre}) pidió llamada y el aviso a Iván NO salió")

        await _enviar_y_registrar(
            telefono, CONFIRMACION_LLAMADA.format(nombre=nombre), proveedor, topic_id, tg_group)
        await actualizar_estado_flags(telefono, menu_estado="conversacional")
        logger.info(f"[LLAMADA] {telefono}: pedido de llamada de {nombre} → avisado={avisado}")
        return "[llamada: pedido enviado]"

    # ── Llega desde el botón de la web: se responde por CONTENIDO ─────────
    # Vale en el primer contacto y también si estaba navegando el menú: el que
    # toca "pagar con tarjeta" ya decidió y no hay nada que venderle.
    if not es_boton and viene_de_la_web_a_pagar(texto):
        await _enviar_saludo_tarjeta(telefono, proveedor, topic_id, tg_group)
        await actualizar_estado_flags(telefono, menu_estado="tarjeta")
        logger.info(f"[MENU] {telefono}: viene de la web a pagar con tarjeta")
        return "[tarjeta: saludo + cuántos hijos]"

    # ── Click de botón o ítem de lista ────────────────────────────────────
    if es_boton and btn_id:
        opcion = _ID_A_OPCION.get(btn_id)

        if opcion == "info_clases":
            await _enviar_lista_info(telefono, proveedor, topic_id, tg_group)
            return "[menú: info sobre clases]"

        if opcion == "precios":
            await _handle_precios(telefono, proveedor, topic_id, tg_group)
            return "[precios + botones]"

        if opcion == "horarios":
            await _handle_horarios(telefono, proveedor, topic_id, tg_group)
            return "[horarios + botones]"

        if opcion == "ubicacion":
            await _handle_ubicacion(telefono, proveedor, topic_id, tg_group)
            return "[ubicación + botones]"

        if opcion == "combo_hermanos":
            await _handle_combo_hermanos(telefono, proveedor, topic_id, tg_group)
            return "[combo hermanos + botones]"

        if opcion == "llamada":
            # No se le pregunta la hora: se le pide el nombre y el profe lo
            # contacta. Lo único que Iván necesita para escribirle es el nombre.
            await _enviar_y_registrar(telefono, PEDIDO_NOMBRE_LLAMADA, proveedor, topic_id, tg_group)
            await actualizar_estado_flags(telefono, menu_estado="llamada")
            logger.info(f"[LLAMADA] {telefono}: pidió llamada — esperando el nombre")
            return PEDIDO_NOMBRE_LLAMADA

        if opcion in ("agendar", "aurora"):
            # Recién acá pasa a modo conversacional: el cerebro de leads toma el
            # control en el siguiente mensaje. Este turno enviamos el puente.
            await actualizar_estado_flags(telefono, menu_estado="conversacional")
            puente = PUENTE_AGENDAR if opcion == "agendar" else PUENTE_AURORA
            await _enviar_y_registrar(telefono, puente, proveedor, topic_id, tg_group)
            logger.info(f"[MENU] {telefono} → conversacional (opción={opcion})")
            return puente

        # button_id desconocido → insistir con botones.
        await _enviar_recordatorio_botones(telefono, proveedor, topic_id, tg_group)
        return "[recordatorio botones]"

    # ── Primer contacto sin estado de menú → saludo + botones ─────────────
    if es_primer_contacto and not menu_estado:
        await _enviar_saludo_y_botones(telefono, proveedor, topic_id, tg_group)
        await actualizar_estado_flags(telefono, menu_estado="menu")
        logger.info(f"[MENU] {telefono}: saludo Aurora + botones del menú principal")
        return "[saludo + menú principal]"

    # ── Texto libre mientras está en el menú → insistir con botones ───────
    # El lead escribió en vez de tocar un botón: NO pasa a conversacional.
    if menu_estado == "menu":
        await _enviar_recordatorio_botones(telefono, proveedor, topic_id, tg_group)
        logger.info(f"[MENU] {telefono}: texto libre en menú → recordatorio de botones")
        return "[recordatorio botones]"

    # Cualquier otro caso (lead viejo mid-conversación, sin menú) → flujo normal.
    return None
