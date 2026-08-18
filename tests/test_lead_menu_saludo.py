# tests/test_lead_menu_saludo.py — El primer contacto presenta el DESAFÍO FENIX
#
# Por qué existe: el saludo contaba la academia en general ("es tu hijo trepando
# árboles...") y ofrecía "Hablar con Aurora". Desde el 09/08 la única puerta de
# entrada es el campus (2 días desde el 17/08), así que el primer mensaje tiene que contar ESO
# y ofrecer llamada con el profe, que es lo que pide el padre que no quiere
# escribir. Las fechas del campus se mueven cada semana: van calculadas.
#
# Correr:  py -3 -m pytest tests/test_lead_menu_saludo.py -q

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import agent.lead_menu as menu

TEL = "595900000999"
ADMIN = "595999999999"


class _ProveedorFalso:
    def __init__(self):
        self.textos: list[tuple[str, str]] = []
        self.botones: list[tuple[str, list]] = []
        self.imagenes: list[tuple[str, int, str]] = []
        self.falla_admin = False

    async def enviar_mensaje(self, telefono, texto):
        if self.falla_admin and telefono == ADMIN:
            return False
        self.textos.append((telefono, texto))
        return True

    async def enviar_botones(self, telefono, texto, botones):
        self.botones.append((telefono, botones))
        self.textos.append((telefono, texto))
        return True

    async def enviar_imagen_bytes(self, telefono, contenido, mime):
        self.imagenes.append((telefono, len(contenido), mime))
        return True


@pytest.fixture
def prov(monkeypatch):
    flags: dict = {}
    p = _ProveedorFalso()

    async def fake_obtener(telefono):
        return dict(flags)

    async def fake_actualizar(telefono, **kw):
        flags.update(kw)

    async def nada(*a, **kw):
        return None

    monkeypatch.setattr(menu, "obtener_estado_flags", fake_obtener)
    monkeypatch.setattr(menu, "actualizar_estado_flags", fake_actualizar)
    monkeypatch.setattr(menu, "guardar_mensaje", nada)
    monkeypatch.setattr(menu, "_espejar_telegram", nada)
    monkeypatch.setenv("ADMIN_PHONE", ADMIN)
    p.flags = flags
    return p


def _procesar(prov, texto, **kw):
    return asyncio.new_event_loop().run_until_complete(
        menu.procesar_menu_lead(TEL, texto, prov, **kw)
    )


def _al_padre(prov):
    return [t for tel, t in prov.textos if tel == TEL]


def _al_admin(prov):
    return [t for tel, t in prov.textos if tel == ADMIN]


# ── El saludo ────────────────────────────────────────────────────────────────

def test_el_saludo_cuenta_el_campus_y_no_la_academia_en_general():
    """Desde el 12/08 el saludo usa el copy de la web ("Una experiencia
    transformadora"), no el relato descubre/supera/conquista."""
    s = menu.saludo_desafio()
    assert "DESAFÍO FENIX" in s
    assert "2 días" in s
    assert "experiencia transformadora" in s
    for frase in ("trepa, corre, se cuelga", "hace amigos en el camino",
                  "de qué es capaz", "transformación profunda",
                  "todos los fines de semana"):
        assert frase in s, f"falta el copy de la web: {frase}"
    assert "trepando árboles" not in s, "ese era el saludo viejo de la academia"


def test_el_saludo_lleva_las_fechas_del_campus_vigente():
    """Calculadas, no escritas a mano: el campus se mueve cada semana."""
    from agent.desafio import proximo_campus, label_campus
    assert label_campus(proximo_campus()) in menu.saludo_desafio()


def test_entra_en_el_limite_de_whatsapp():
    """Body de un interactivo con botones: 1024 caracteres."""
    cuerpo = f"{menu.saludo_desafio()}\n\n{menu._TEXTO_BOTONES}"
    assert len(cuerpo) <= 1024, f"{len(cuerpo)} caracteres — WhatsApp lo rechaza"


def test_los_botones_respetan_el_limite_de_meta():
    for b in menu._BOTONES_MENU_PRINCIPAL:
        assert len(b["title"]) <= 20, f"{b['title']} pasa los 20 caracteres"
    assert len(menu._BOTONES_MENU_PRINCIPAL) <= 3


def test_el_primer_contacto_manda_la_foto_de_la_casona(prov):
    r = _procesar(prov, "Hola", es_primer_contacto=True)
    assert r == "[saludo + menú principal]"
    assert len(prov.imagenes) == 1, "tenía que ir la foto de La Casona"
    titulos = [b["title"] for b in prov.botones[0][1]]
    assert titulos == ["📅 Info y precios", "🎯 Reservar lugar", "📞 Agendar llamada"]


# ── "Info y precios" manda todo ──────────────────────────────────────────────

def test_info_y_precios_manda_todo_sin_hacerlo_elegir_de_una_lista(prov):
    """El que toca el botón ya pidió toda la info: no se le devuelve un menú."""
    _procesar(prov, "Hola", es_primer_contacto=True)
    prov.imagenes.clear()
    r = _procesar(prov, "", btn_id="lead_info", es_boton=True)

    assert r == "[info completa: precios + horarios + ubicación]"
    cuerpo = "\n".join(_al_padre(prov)[-3:])
    assert "300.000" in cuerpo or "450.000" in cuerpo, "faltan los precios"
    assert "SÁBADO" in cuerpo and "11:00" in cuerpo, "faltan los horarios"
    assert "Maestras Paraguayas" in cuerpo, "falta la ubicación"
    assert len(prov.imagenes) == 1, "el afiche de precios, una sola vez"


def test_la_info_va_en_mensajes_separados_no_en_un_ladrillo(prov):
    _procesar(prov, "Hola", es_primer_contacto=True)
    antes = len(_al_padre(prov))
    _procesar(prov, "", btn_id="lead_info", es_boton=True)
    assert len(_al_padre(prov)) - antes == 3, "precios, horarios y ubicación separados"


def test_el_ultimo_mensaje_cierra_con_botones(prov):
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "", btn_id="lead_info", es_boton=True)
    titulos = [b["title"] for b in prov.botones[-1][1]]
    assert titulos == ["🎯 Reservar lugar", "🧒 Combo hermanos", "📞 Agendar llamada"]


def test_ya_no_queda_ningun_boton_de_hablar_con_aurora():
    """Iván los reemplazó todos por 'Agendar llamada'."""
    for grupo in (menu._BOTONES_MENU_PRINCIPAL, menu._BOTONES_POST_INFO):
        for b in grupo:
            assert "Aurora" not in b["title"], f"quedó un botón viejo: {b['title']}"


# ── Pedido de llamada ────────────────────────────────────────────────────────

def test_el_boton_de_llamada_pide_el_nombre_sin_preguntar_hora(prov):
    _procesar(prov, "Hola", es_primer_contacto=True)
    r = _procesar(prov, "", btn_id="lead_llamada", es_boton=True)
    assert r == menu.PEDIDO_NOMBRE_LLAMADA
    texto = _al_padre(prov)[-1]
    assert "nombre" in texto.lower()
    assert "hora" not in texto.lower(), "Iván no quiere que se pregunte la hora"
    assert prov.flags["menu_estado"] == "llamada"


def test_con_el_nombre_le_llega_a_ivan_el_link_de_un_clic(prov):
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "", btn_id="lead_llamada", es_boton=True)
    r = _procesar(prov, "soy marta gonzález")

    assert r == "[llamada: pedido enviado]"
    aviso = _al_admin(prov)[-1]
    assert "Marta González" in aviso, "el nombre va limpio, sin el 'soy'"
    assert f"https://wa.me/{TEL}?text=" in aviso, "el link tiene que ser de un clic"
    assert "profe%20Iv" in aviso, "el saludo va prellenado en el link"
    # Y el padre queda avisado y libre para seguir conversando.
    assert "Marta González" in _al_padre(prov)[-1]
    assert prov.flags["menu_estado"] == "conversacional"


def test_sin_nombre_no_se_manda_el_pedido(prov):
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "", btn_id="lead_llamada", es_boton=True)
    r = _procesar(prov, "   ")
    assert r == "[llamada: repregunta nombre]"
    assert _al_admin(prov) == [], "sin nombre no se molesta a Iván"
    assert prov.flags["menu_estado"] == "llamada", "sigue esperando"


def test_si_el_aviso_a_ivan_no_sale_queda_registrado(prov, caplog):
    """El padre no puede quedar esperando una llamada que nadie pidió."""
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "", btn_id="lead_llamada", es_boton=True)
    prov.falla_admin = True
    with caplog.at_level("ERROR"):
        r = _procesar(prov, "Juan")
    assert r == "[llamada: pedido enviado]"
    assert any("NO salió" in m for m in caplog.messages), "tiene que gritar en los logs"


# ── El menú no es una jaula ──────────────────────────────────────────────────
# Caso real 18/08 (595982862766): el padre tocó "Info y precios", leyó todo y
# preguntó "Hacen todos los meses.?" — el sistema le contestó "Tocá una de las
# opciones 👇" y su pregunta se perdió. Ningún botón contestaba eso.

def test_al_primer_texto_libre_se_le_insiste_una_vez(prov):
    """Puede haber escrito sin mirar los botones: la primera vez se le recuerdan."""
    _procesar(prov, "Hola", es_primer_contacto=True)
    r = _procesar(prov, "hola?")
    assert r == "[recordatorio botones]"
    assert prov.flags["menu_estado"] == "menu_libre", "ya no queda atrapado en el menú"


def test_al_segundo_texto_libre_lo_atiende_el_cerebro(prov):
    """None = main.py sigue el flujo normal y responde ESTE mismo mensaje."""
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "hola?")
    antes = len(_al_padre(prov))
    r = _procesar(prov, "¿hacen todos los meses?")
    assert r is None, "el menú tiene que soltarlo, no insistir de nuevo"
    assert prov.flags["menu_estado"] == "conversacional"
    assert len(_al_padre(prov)) == antes, "el menú no manda nada: contesta el cerebro"


def test_el_que_ya_recibio_la_info_pregunta_y_le_contestan(prov):
    """El caso de 595982862766: tocó el botón, leyó todo y preguntó. Sin
    recordatorio de por medio — ya usó el menú."""
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "", btn_id="lead_info", es_boton=True)
    assert prov.flags["menu_estado"] == "menu_libre"

    antes = len(_al_padre(prov))
    r = _procesar(prov, "Hacen todos los meses.?")
    assert r is None, "la pregunta la contesta el cerebro, no un botón"
    assert prov.flags["menu_estado"] == "conversacional"
    assert len(_al_padre(prov)) == antes


def test_los_botones_siguen_andando_despues_de_escribir(prov):
    """El padre escribió, se le insistió, y después sí tocó un botón."""
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "hola?")
    r = _procesar(prov, "", btn_id="lead_info", es_boton=True)
    assert r == "[info completa: precios + horarios + ubicación]"


def test_el_camino_de_llamada_no_se_afloja(prov):
    """Ahí el texto libre ES el dato que se espera (el nombre): no suelta al cerebro."""
    _procesar(prov, "Hola", es_primer_contacto=True)
    _procesar(prov, "", btn_id="lead_llamada", es_boton=True)
    r = _procesar(prov, "   ")
    assert r == "[llamada: repregunta nombre]"
    assert prov.flags["menu_estado"] == "llamada"
