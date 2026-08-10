# tests/test_webhook_no_muda.py — El agente NUNCA se queda mudo
#
# Por qué existe: el 2026-08-09 un `import` dentro de una rama condicional de
# `_procesar_mensaje_interno` dejó al agente MUDO en producción (UnboundLocalError
# en cada mensaje que no fuera un comprobante). `import agent.main` compilaba, los
# 30 tests pasaban y el deploy quedó SUCCESS: nada lo atajó porque NINGÚN test
# ejercitaba el camino real de un mensaje entrante.
#
# Este test recorre ese camino de punta a punta con el mundo exterior mockeado
# (Claude, Airtable, Meta, Telegram) y verifica lo único que el padre nota:
# que RECIBE una respuesta. Si un cambio rompe el flujo, acá se ve — no en el
# WhatsApp de un lead real.
#
# Correr:  py -3 -m pytest tests/test_webhook_no_muda.py -q

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La DB temporal y las credenciales de mentira las fija tests/conftest.py,
# que pytest importa ANTES que cualquier módulo de agent/.

import pytest

import agent.main as main
from agent.memory import inicializar_db

TEL = "595900000123"

# Los 5 escenarios del CHECKLIST + los que ya rompieron en vivo
ESCENARIOS = [
    ("lead saluda", "Hola"),
    ("pregunta precio", "cuanto sale?"),
    ("pregunta horario", "a que hora es?"),
    ("pregunta ubicacion", "donde queda?"),
    ("da nombre y edad del hijo", "Ivan 5 años"),      # ← el mensaje que dejó mudo al agente
    ("acepta", "si quiero"),
    ("manda comprobante", "[imagen]"),
    ("texto con 'sab' que NO es reserva", "no sabemos si vamos"),
    ("pide cambiar su numero", "quiero cambiar mi numero"),
    ("nombre con coma final", "Sofia, 6 años,"),   # ← IndexError: dejaba mudo al que pagaba
    ("solo comas", ",,,"),
    ("mensaje raro", "?????"),
    ("mensaje largo", "hola " * 200),
]


llegadas_al_brain = []


@pytest.fixture(scope="module")
def enviados():
    """Captura lo que el agente le manda al padre, sin tocar la red."""
    return []


# Un solo loop para todo el módulo: las conexiones de SQLAlchemy quedan atadas
# al loop donde nacieron (py3.14 ya no crea uno implícito con get_event_loop).
_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def mundo_exterior(enviados):
    """Mockea Claude, Airtable, Meta y Telegram. Deja el flujo real intacto."""
    from unittest.mock import AsyncMock, patch

    async def _fake_claude(*a, **kw):
        """Respeta el contrato real de brain.generar_respuesta: tupla SOLO si
        recibe tools + executor; string pelado si no. Un mock infiel hacía
        fallar el test por su propia culpa (respuesta = tupla)."""
        llegadas_al_brain.append(1)
        _usa_tools = bool(kw.get("tools") and kw.get("tool_executor"))
        texto = "Respuesta simulada del agente 🌳"
        return (texto, []) if _usa_tools else texto

    async def _fake_enviar(telefono, texto, *a, **kw):
        enviados.append((telefono, texto))
        return True

    async def _fake_botones(telefono, texto, *a, **kw):
        # Mandar botones TAMBIÉN es responderle al padre
        enviados.append((telefono, f"[botones] {texto}"))
        return True

    async def _fake_imagen(telefono, *a, **kw):
        enviados.append((telefono, "[imagen enviada]"))
        return True

    async def _fake_get_records(*a, **kw):
        return []

    async def _fake_post(*a, **kw):
        return {"id": "recTEST0000000001", "fields": {}}

    async def _fake_patch(*a, **kw):
        return True

    # OJO: Telegram se parchea EN SU MÓDULO (agent.telegram_bridge), no en main —
    # los menús y tools lo importan directo y si solo se parchea main el test le
    # escribe a los topics de PRODUCCIÓN.
    parches = [
        patch.object(main, "generar_respuesta", _fake_claude),
        patch.object(main.proveedor, "enviar_mensaje", _fake_enviar),
        patch.object(main.proveedor, "enviar_imagen", _fake_imagen),
        patch.object(main.proveedor, "enviar_botones", _fake_botones),
        patch("agent.airtable_client._get_records", _fake_get_records),
        patch("agent.airtable_client._post", _fake_post),
        patch("agent.airtable_client._patch", _fake_patch),
        patch("agent.telegram_bridge.enviar_a_topic", AsyncMock(return_value=None)),
        patch("agent.telegram_bridge.obtener_o_crear_topic", AsyncMock(return_value=None)),
        patch.object(main, "enviar_a_topic", AsyncMock(return_value=None)),
        patch.object(main, "obtener_o_crear_topic", AsyncMock(return_value=None)),
        patch.object(main, "_delay_humano", AsyncMock(return_value=None)),
    ]
    for p in parches:
        p.start()
    _run(inicializar_db())
    _poner_en_modo_conversacional()
    yield
    for p in parches:
        p.stop()


def _mensaje(texto: str):
    """Objeto MensajeEntrante equivalente al que arma el proveedor real."""
    from agent.providers.base import MensajeEntrante
    _mensaje.n += 1
    return MensajeEntrante(
        telefono=TEL,
        texto=texto,
        mensaje_id=f"wamid.TEST{_mensaje.n}",
        es_propio=False,
        media_id="mediaTEST" if texto == "[imagen]" else None,
    )


_mensaje.n = 0


def _procesar(texto: str, *, btn_id: str | None = None):
    """Corre el camino real del mensaje (misma llamada que hace el webhook)."""
    msg = _mensaje(texto)
    if btn_id:
        msg.es_boton = True
        msg.btn_id = btn_id
    return _run(main._procesar_mensaje_interno(msg.telefono, msg.texto, msg))


def _poner_en_modo_conversacional():
    """Reproduce el camino real del lead de Iván: saluda, toca 'Agendar prueba'
    y a partir de ahí sus mensajes van al brain (ahí vivía el bug).

    OJO: asignar_variante PRIMERO — actualizar_estado_flags descarta el flag
    en silencio si el teléfono todavía no tiene fila en conversaciones_ab."""
    from agent.ab_test import actualizar_estado_flags, asignar_variante
    _run(asignar_variante(TEL))
    _run(actualizar_estado_flags(TEL, menu_estado="conversacional"))


@pytest.mark.parametrize("nombre,texto", ESCENARIOS, ids=[e[0] for e in ESCENARIOS])
def test_el_agente_responde(nombre, texto, enviados):
    """Cada mensaje de un padre TIENE que producir una respuesta.

    Falla si el procesamiento tira una excepción (el bug de hoy) o si termina
    sin enviarle nada al padre.
    """
    antes = len(enviados)
    _procesar(texto)
    nuevos = [t for tel, t in enviados[antes:] if tel == TEL]
    assert nuevos, f"SILENCIO en el escenario '{nombre}' ({texto[:40]!r}): el padre no recibió nada"
    # Recibir el fallback de error NO cuenta como responder: significa que una
    # excepción se comió el turno (el except del webhook ahora sí contesta, pero
    # eso es la red de seguridad, no el camino correcto).
    from agent.brain import obtener_mensaje_error
    _err = obtener_mensaje_error()
    assert not any(_err in t for t in nuevos), (
        f"EXCEPCIÓN en el escenario '{nombre}' ({texto[:40]!r}): el padre recibió "
        f"el mensaje de error, no una respuesta real. Mirá el log del test."
    )


def test_el_flujo_llega_al_brain(enviados):
    """Guard del test mismo: si NINGÚN escenario llega al brain, este archivo
    solo está probando el menú de botones y da falsa seguridad (pasó al
    escribirlo: 12 verdes con el bug de hoy reintroducido a propósito)."""
    assert llegadas_al_brain, (
        "Ningún escenario llegó a generar_respuesta: el test no ejercita el "
        "camino del brain ni el post-procesado, que es donde vivió el bug"
    )


def test_ninguna_excepcion_mata_el_flujo(enviados):
    """Una conversación completa seguida, sin resets: el flujo no debe cortarse."""
    for _, texto in ESCENARIOS:
        antes = len(enviados)
        _procesar(texto)
        assert len(enviados) > antes, f"El flujo se cortó en {texto[:30]!r}"
