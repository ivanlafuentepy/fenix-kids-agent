# tests/test_pago_web.py — El pago con tarjeta hecho desde la WEB inscribe de verdad
#
# Por qué existe: hasta el 2026-08-10 un pago desde fenixkidsacademy.com cobraba
# bien pero moría ahí. /pago-confirmado solo gestionaba pagos con "Pedido activo"
# (los que el agente inicia cuando manda el link por WhatsApp); el de la web caía
# al else, le respondía "¡Pago confirmado!" y no creaba el PAGO en Airtable, no
# pedía los datos del niño y no reservaba ninguno de los días del campus.
#
# Correr:  py -3 -m pytest tests/test_pago_web.py -q

import asyncio
import hashlib
import hmac
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import agent.main as main

TEL = "595900000777"
SECRET = os.environ.get("LINK_SECRET", "testsecret")

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _firma(spid, telefono, monto):
    return hmac.new(SECRET.encode(), f"{spid}:{telefono}:{monto}".encode(),
                    hashlib.sha256).hexdigest()


def _aviso(spid, concepto, monto=300000, telefono=TEL):
    """El cuerpo que manda la pasarela cuando Bancard confirma el cobro."""
    return {
        "telefono": telefono, "monto": monto, "concepto": concepto,
        "shop_process_id": spid, "authorization_number": "123456",
        "sig": _firma(spid, telefono, monto),
    }


class _Req:
    """Request mínimo: /pago-confirmado solo lee el body crudo."""
    def __init__(self, payload):
        import json
        self._body = json.dumps(payload).encode()

    async def body(self):
        return self._body


@pytest.fixture
def espia(monkeypatch):
    """Intercepta el flujo de comprobante y los envíos, sin tocar la red."""
    llamadas = []

    async def fake_comprobante(telefono, texto, media_id, historial, topic_id, **kw):
        llamadas.append({"telefono": telefono, "texto": texto, **kw})

    async def ok(*a, **kw):
        return True

    async def nada(*a, **kw):
        return None

    async def sin_pedido(*a, **kw):
        return None

    # OJO: pago_confirmado importa estos DENTRO de la función, así que hay que
    # parchearlos en su módulo de origen — en main.* no existen.
    import agent.memory as memoria
    import agent.flujo_pagos as flujo
    monkeypatch.setattr(flujo, "_procesar_comprobante", fake_comprobante)
    monkeypatch.setattr(memoria, "obtener_pedido_activo", sin_pedido)
    monkeypatch.setattr(memoria, "marcar_pedido_cargado", nada)
    # La dedup escribe en DB; acá solo interesa el ruteo del pago
    monkeypatch.setattr(main, "registrar_mensaje_procesado", lambda *a, **kw: _fut(True))
    monkeypatch.setattr(main, "obtener_historial", lambda *a, **kw: _fut([]))
    monkeypatch.setattr(main, "grupo_telegram_para", lambda *a, **kw: _fut(0))
    monkeypatch.setattr(main, "obtener_o_crear_topic", lambda *a, **kw: _fut(None))
    monkeypatch.setattr(main, "guardar_mensaje", nada)
    monkeypatch.setattr(main.proveedor, "enviar_mensaje", ok)
    monkeypatch.setenv("LINK_SECRET", SECRET)
    return llamadas


def _fut(valor):
    f = asyncio.Future(loop=_LOOP)
    f.set_result(valor)
    return f


def _llamar(payload):
    return _LOOP.run_until_complete(main.pago_confirmado(_Req(payload)))


def test_pago_del_desafio_desde_la_web_dispara_el_flujo_completo(espia):
    """Sin Pedido, pero con concepto de Desafío: tiene que inscribirlo igual."""
    r = _llamar(_aviso("spid-web-1", "Desafío FENIX"))
    assert r["gestionado"] is True, "la pasarela no debe registrarlo por su cuenta"
    assert len(espia) == 1, "tenía que entrar al flujo de comprobante"
    assert espia[0]["tipo_override"] == "prueba"
    assert espia[0]["concepto_pago"] == "DESAFIO"
    assert espia[0]["monto_override"] == 300000
    assert espia[0]["metodo_pago"] == "CREDIT CARD"


def test_el_precio_normal_tambien_entra(espia):
    r = _llamar(_aviso("spid-web-2", "Desafío FENIX", monto=450000))
    assert r["gestionado"] is True
    assert espia[0]["monto_override"] == 450000


def test_sin_tilde_tambien_matchea(espia):
    """El concepto puede llegar sin acento según cómo se arme el link."""
    _llamar(_aviso("spid-web-3", "Desafio FENIX"))
    assert len(espia) == 1


def test_un_pago_del_panel_admin_NO_crea_reservas(espia):
    """Un cobro suelto hecho a mano no debe anotar a nadie en el campus."""
    r = _llamar(_aviso("spid-admin-1", "Matrícula anual", monto=100000))
    assert espia == [], "no tenía que entrar al flujo del campus"
    assert r["gestionado"] is False, "la pasarela lo registra en la caja central"


def test_firma_invalida_se_rechaza(espia):
    from fastapi import HTTPException
    payload = _aviso("spid-web-4", "Desafío FENIX")
    payload["sig"] = "0" * 64
    with pytest.raises(HTTPException) as e:
        _llamar(payload)
    assert e.value.status_code == 403
    assert espia == []
