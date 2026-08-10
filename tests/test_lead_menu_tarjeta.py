# tests/test_lead_menu_tarjeta.py — El que llega de la web a pagar con tarjeta
#
# Por qué existe: hasta el 2026-08-10 el botón "💳 Quiero pagar con tarjeta" de
# fenixkidsacademy.com abría WhatsApp con "Hola, quiero pagar con tarjeta el
# Desafío FENIX" y Aurora contestaba el saludo genérico de venta + los botones
# del menú. El primer contacto se resolvía por ESTADO (lead_menu.py:346) sin
# mirar el contenido, así que la instrucción del prompt nunca se evaluaba: el
# mensaje jamás llegaba al brain.
#
# Correr:  py -3 -m pytest tests/test_lead_menu_tarjeta.py -q

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import agent.lead_menu as menu

TEL = "595900000888"
TEXTO_WEB = "Hola, quiero pagar con tarjeta el Desafío FENIX"


class _ProveedorFalso:
    """Registra lo que se le manda a cada teléfono; nunca sale a la red."""

    def __init__(self):
        self.textos: list[tuple[str, str]] = []
        self.botones: list[tuple[str, list]] = []

    async def enviar_mensaje(self, telefono, texto):
        self.textos.append((telefono, texto))
        return True

    async def enviar_botones(self, telefono, texto, botones):
        self.botones.append((telefono, botones))
        self.textos.append((telefono, texto))
        return True


@pytest.fixture
def prov(monkeypatch):
    """Aísla el menú: flags en memoria, sin DB, sin Telegram, sin Airtable."""
    flags: dict = {}
    p = _ProveedorFalso()

    async def fake_obtener(telefono):
        return dict(flags)

    async def fake_actualizar(telefono, **kw):
        flags.update(kw)

    async def nada(*a, **kw):
        return None

    async def fake_pedido(telefono, tipo, *, concepto="PRUEBA", monto_total=None):
        p.pedido = {"tipo": tipo, "concepto": concepto, "monto_total": monto_total}
        return 1

    monkeypatch.setattr(menu, "obtener_estado_flags", fake_obtener)
    monkeypatch.setattr(menu, "actualizar_estado_flags", fake_actualizar)
    monkeypatch.setattr(menu, "guardar_mensaje", nada)
    monkeypatch.setattr(menu, "_espejar_telegram", nada)
    import agent.memory as memoria
    monkeypatch.setattr(memoria, "crear_o_actualizar_pedido", fake_pedido)
    monkeypatch.setenv("LINK_SECRET", "testsecret")
    p.flags = flags
    p.pedido = None
    return p


def _procesar(prov, texto, **kw):
    return asyncio.new_event_loop().run_until_complete(
        menu.procesar_menu_lead(TEL, texto, prov, **kw)
    )


# ── El detector: matchea nuestro deep-link, no cualquier frase ───────────────

def test_reconoce_el_texto_de_la_web():
    assert menu.viene_de_la_web_a_pagar(TEXTO_WEB)
    assert menu.viene_de_la_web_a_pagar("hola, QUIERO PAGAR CON TARJETA el desafio fenix")


def test_no_confunde_una_pregunta_normal():
    assert not menu.viene_de_la_web_a_pagar("Hola, quiero información")
    assert not menu.viene_de_la_web_a_pagar("¿aceptan tarjeta?")
    assert not menu.viene_de_la_web_a_pagar("")


# ── El flujo completo ────────────────────────────────────────────────────────

def test_el_primer_contacto_desde_la_web_no_recibe_el_saludo_de_venta(prov):
    """El bug del endpoint 10/08 04:31: contestaba SALUDO_AURORA + menú."""
    r = _procesar(prov, TEXTO_WEB, es_primer_contacto=True)
    assert r == "[tarjeta: saludo + cuántos hijos]"
    enviado = prov.textos[0][1]
    assert menu.SALUDO_AURORA not in enviado, "no se le vuelve a vender la academia"
    assert "tarjeta" in enviado.lower()
    titulos = [b["title"] for b in prov.botones[0][1]]
    assert titulos == ["1 hijo", "2 hermanos", "3 hermanos"]
    assert prov.flags["menu_estado"] == "tarjeta"


def test_elegir_los_hijos_manda_el_link_con_el_monto_exacto(prov):
    from agent.desafio import precio_desafio

    _procesar(prov, TEXTO_WEB, es_primer_contacto=True)
    r = _procesar(prov, "", btn_id="tarjeta_2", es_boton=True)

    assert r == "[tarjeta: link enviado]"
    texto = prov.textos[-1][1]
    assert "/pagar/fenix" in texto, "tenía que mandar el link firmado"
    monto, _ = precio_desafio(2)
    assert f"monto={monto}" in texto, "el monto del link sale de precio_desafio, no del parser"
    # El Pedido abierto es lo que hace que /pago-confirmado inscriba de verdad.
    assert prov.pedido == {"tipo": "prueba", "concepto": "DESAFIO", "monto_total": monto}
    assert prov.flags["menu_estado"] == "conversacional"


def test_responder_por_texto_tambien_vale(prov):
    from agent.desafio import precio_desafio

    _procesar(prov, TEXTO_WEB, es_primer_contacto=True)
    _procesar(prov, "somos 3")
    monto, _ = precio_desafio(3)
    assert f"monto={monto}" in prov.textos[-1][1]


def test_si_no_se_entiende_cuantos_hijos_no_inventa_monto(prov):
    _procesar(prov, TEXTO_WEB, es_primer_contacto=True)
    r = _procesar(prov, "buenas, cómo va?")
    assert r == "[tarjeta: recordatorio hijos]"
    assert "/pagar/fenix" not in prov.textos[-1][1], "sin dato de hijos NO se manda link"
    assert prov.flags["menu_estado"] == "tarjeta", "sigue esperando la respuesta"


def test_el_lead_normal_sigue_recibiendo_el_menu_de_siempre(prov):
    """El camino de tarjeta no puede robarle el primer contacto a nadie más."""
    r = _procesar(prov, "Hola", es_primer_contacto=True)
    assert r == "[saludo + menú principal]"
    assert menu.SALUDO_AURORA in prov.textos[0][1]
    assert prov.flags["menu_estado"] == "menu"
