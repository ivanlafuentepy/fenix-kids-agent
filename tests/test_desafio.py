# tests/test_desafio.py — Tests del DESAFÍO FENIX (campus de 3 días)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from agent.desafio import (
    proximo_campus, es_anticipada, precio_desafio, turnos_del_campus,
    label_campus, crear_reservas_campus,
    PRECIO_ANTICIPADA, PRECIO_NORMAL, TURNOS_VIERNES, TURNOS_SABADO, HORA_DOMINGO,
)

TZ = ZoneInfo("America/Asuncion")


def py(anio, mes, dia, hora=12, minuto=0):
    """Un momento concreto en hora de Paraguay."""
    return datetime(anio, mes, dia, hora, minuto, tzinfo=TZ)


class TestProximoCampus:
    """Qué fin de semana se está vendiendo."""

    def test_domingo_previo_ofrece_el_finde_siguiente(self):
        # Domingo 09/08/2026 a la noche → campus 14, 15 y 16
        c = proximo_campus(py(2026, 8, 9, 22, 30))
        assert c == {"viernes": date(2026, 8, 14),
                     "sabado": date(2026, 8, 15),
                     "domingo": date(2026, 8, 16)}

    def test_lunes_ofrece_el_viernes_de_esa_semana(self):
        c = proximo_campus(py(2026, 8, 10, 9))
        assert c["viernes"] == date(2026, 8, 14)

    def test_jueves_todavia_ofrece_el_de_manana(self):
        c = proximo_campus(py(2026, 8, 13, 23, 50))
        assert c["viernes"] == date(2026, 8, 14)

    def test_viernes_antes_de_las_17_sigue_vendiendo_el_de_hoy(self):
        # Iván: se puede reservar hasta el viernes a la tarde
        c = proximo_campus(py(2026, 8, 14, 16, 59))
        assert c["viernes"] == date(2026, 8, 14)

    def test_viernes_ya_empezado_salta_al_siguiente(self):
        c = proximo_campus(py(2026, 8, 14, 17, 0))
        assert c["viernes"] == date(2026, 8, 21)

    def test_sabado_del_campus_en_curso_ofrece_el_siguiente(self):
        # El campus 14-16 está en su día 2: ya no se puede vender
        c = proximo_campus(py(2026, 8, 15, 10))
        assert c["viernes"] == date(2026, 8, 21)

    def test_los_cuatro_campus_anunciados_caen_viernes_sabado_domingo(self):
        for viernes in (date(2026, 8, 14), date(2026, 8, 21),
                        date(2026, 8, 28), date(2026, 9, 4)):
            c = proximo_campus(py(viernes.year, viernes.month, viernes.day, 8))
            assert c["viernes"] == viernes
            assert c["viernes"].weekday() == 4
            assert c["sabado"].weekday() == 5
            assert c["domingo"].weekday() == 6


class TestPrecio:
    """350.000 hasta el jueves 23:59; 550.000 desde el viernes. +150.000 por hermano."""

    def test_anticipada_un_hijo(self):
        monto, anticipada = precio_desafio(1, py(2026, 8, 10, 9))
        assert (monto, anticipada) == (350_000, True)

    def test_anticipada_dos_hermanos(self):
        assert precio_desafio(2, py(2026, 8, 10, 9))[0] == 500_000

    def test_anticipada_tres_hermanos(self):
        assert precio_desafio(3, py(2026, 8, 10, 9))[0] == 650_000

    def test_jueves_2359_todavia_es_anticipada(self):
        monto, anticipada = precio_desafio(1, py(2026, 8, 13, 23, 59))
        assert (monto, anticipada) == (350_000, True)

    def test_viernes_00_01_ya_es_precio_normal(self):
        monto, anticipada = precio_desafio(1, py(2026, 8, 14, 0, 1))
        assert (monto, anticipada) == (550_000, False)

    def test_normal_con_hermanos(self):
        assert precio_desafio(2, py(2026, 8, 14, 10))[0] == 700_000
        assert precio_desafio(3, py(2026, 8, 14, 10))[0] == 850_000

    def test_sabado_vende_el_campus_siguiente_a_precio_anticipado(self):
        # Ya no se vende el campus en curso → el siguiente todavía es anticipada
        monto, anticipada = precio_desafio(1, py(2026, 8, 15, 11))
        assert (monto, anticipada) == (350_000, True)

    def test_hijos_cero_o_none_cuenta_como_uno(self):
        assert precio_desafio(0, py(2026, 8, 10))[0] == PRECIO_ANTICIPADA
        assert precio_desafio(None, py(2026, 8, 10))[0] == PRECIO_ANTICIPADA

    def test_es_anticipada_coherente_con_el_precio(self):
        momento = py(2026, 8, 14, 9)
        assert es_anticipada(momento) is False
        assert precio_desafio(1, momento)[0] == PRECIO_NORMAL


class TestTurnosYLabel:

    def test_cinco_slots_en_orden(self):
        slots = turnos_del_campus(proximo_campus(py(2026, 8, 10)))
        assert slots == [
            ("2026-08-14", "17:00"), ("2026-08-14", "19:30"),
            ("2026-08-15", "11:00"), ("2026-08-15", "15:30"),
            ("2026-08-16", "12:00"),
        ]

    def test_label_mismo_mes(self):
        assert label_campus(proximo_campus(py(2026, 8, 10))) == \
            "viernes 14, sábado 15 y domingo 16 de agosto"

    def test_label_cruzando_de_mes(self):
        # Campus del 28, 29 y 30 de agosto → mismo mes; el que cruza es otro caso
        campus = {"viernes": date(2026, 8, 30), "sabado": date(2026, 8, 31),
                  "domingo": date(2026, 9, 1)}
        label = label_campus(campus)
        assert "agosto" in label and "septiembre" in label


class TestCrearReservas:
    """Tres reservas por niño; un turno inventado no se adivina."""

    @pytest.mark.asyncio
    async def test_turno_viernes_invalido_explota(self):
        with pytest.raises(ValueError):
            await crear_reservas_campus(["recX"], "18:00", "11:00")

    @pytest.mark.asyncio
    async def test_turno_sabado_invalido_explota(self):
        with pytest.raises(ValueError):
            await crear_reservas_campus(["recX"], "17:00", "9:30")

    @pytest.mark.asyncio
    async def test_crea_tres_reservas_por_nino(self, monkeypatch):
        pedidos = []

        async def fake_horario(fecha_iso, hora):
            pedidos.append((fecha_iso, hora))
            return f"horario:{fecha_iso}:{hora}"

        async def fake_reserva(nino_id, horario_id):
            return f"reserva:{nino_id}:{horario_id}"

        import agent.airtable_client as ac
        monkeypatch.setattr(ac, "obtener_o_crear_horario", fake_horario)
        monkeypatch.setattr(ac, "crear_reserva", fake_reserva)

        campus = proximo_campus(py(2026, 8, 10))
        reservas = await crear_reservas_campus(["nino1", "nino2"], "19:30", "15:30", campus)

        assert len(reservas) == 6  # 2 niños × 3 días
        assert pedidos[:3] == [("2026-08-14", "19:30"),
                               ("2026-08-15", "15:30"),
                               ("2026-08-16", HORA_DOMINGO)]

    @pytest.mark.asyncio
    async def test_si_falla_un_horario_los_otros_dos_dias_igual_se_reservan(self, monkeypatch):
        async def fake_horario(fecha_iso, hora):
            return None if hora == HORA_DOMINGO else f"horario:{hora}"

        async def fake_reserva(nino_id, horario_id):
            return f"reserva:{horario_id}"

        import agent.airtable_client as ac
        monkeypatch.setattr(ac, "obtener_o_crear_horario", fake_horario)
        monkeypatch.setattr(ac, "crear_reserva", fake_reserva)

        reservas = await crear_reservas_campus(["nino1"], "17:00", "11:00",
                                               proximo_campus(py(2026, 8, 10)))
        assert len(reservas) == 2


class ProveedorFalso:
    """Captura lo que se le manda al padre, sin tocar la red."""

    def __init__(self):
        self.mensajes = []
        self.botones = []

    async def enviar_mensaje(self, telefono, texto, *a, **kw):
        self.mensajes.append((telefono, texto))
        return True

    async def enviar_botones(self, telefono, texto, botones, *a, **kw):
        self.botones.append((telefono, texto, [b["id"] for b in botones]))
        return True


@pytest.fixture
def sin_mundo_exterior(monkeypatch):
    """Neutraliza DB, Airtable y Telegram; devuelve los flags que se fueron escribiendo."""
    from agent import desafio
    escritos = {}

    async def fake_flags(telefono, **kw):
        escritos.update(kw)

    async def fake_guardar(*a, **kw):
        return None

    async def fake_cupo(fecha_iso, hora):
        return "libre", 0

    async def fake_grupo(telefono):
        return {"hijos": [{"id": "ninoA"}], "tutores": []}

    async def fake_reservas(nino_ids, tv, ts, campus=None):
        escritos["_reservas"] = (list(nino_ids), tv, ts)
        return ["r1", "r2", "r3"]

    import agent.ab_test as ab
    import agent.memory as mem
    import agent.airtable_client as ac
    monkeypatch.setattr(ab, "actualizar_estado_flags", fake_flags)
    monkeypatch.setattr(mem, "guardar_mensaje", fake_guardar)
    monkeypatch.setattr(ac, "obtener_grupo_familiar", fake_grupo)
    monkeypatch.setattr(desafio, "estado_cupo", fake_cupo)
    monkeypatch.setattr(desafio, "crear_reservas_campus", fake_reservas)
    return escritos


class TestEleccionDeTurno:
    """El padre pagó: elige turno del viernes y del sábado con botones."""

    @pytest.mark.asyncio
    async def test_sin_flag_no_intercepta_nada(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        r = await manejar_eleccion_turno("595", "hola", None, False, {}, ProveedorFalso())
        assert r is None  # el mensaje sigue su curso normal

    @pytest.mark.asyncio
    async def test_boton_viernes_guarda_y_pregunta_el_sabado(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "", "desafio_vie_1930", True,
                                         {"desafio_espera_turno": "viernes"}, p)
        assert r == "[turno viernes elegido]"
        assert sin_mundo_exterior["desafio_turno_viernes"] == "19:30"
        assert sin_mundo_exterior["desafio_espera_turno"] == "sabado"
        assert p.botones[-1][2] == ["desafio_sab_1100", "desafio_sab_1530"]

    @pytest.mark.asyncio
    async def test_boton_sabado_crea_las_tres_reservas_y_confirma(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "", "desafio_sab_1100", True,
                                         {"desafio_espera_turno": "sabado",
                                          "desafio_turno_viernes": "17:00"}, p)
        assert r == "[campus reservado]"
        assert sin_mundo_exterior["_reservas"] == (["ninoA"], "17:00", "11:00")
        assert sin_mundo_exterior["desafio_espera_turno"] is None
        confirmacion = p.mensajes[-1][1]
        for parte in ("17:00", "11:00", "12:00", "Casona"):
            assert parte in confirmacion

    @pytest.mark.asyncio
    async def test_texto_con_la_hora_tambien_vale(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "prefiero 19:30", None, False,
                                         {"desafio_espera_turno": "viernes"}, p)
        assert r == "[turno viernes elegido]"
        assert sin_mundo_exterior["desafio_turno_viernes"] == "19:30"

    @pytest.mark.asyncio
    async def test_respuesta_que_no_es_un_turno_reofrece_los_botones(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "y el domingo a qué hora?", None, False,
                                         {"desafio_espera_turno": "viernes"}, p)
        assert r == "[turno: recordatorio]"
        assert p.botones[-1][2] == ["desafio_vie_1700", "desafio_vie_1930"]

    @pytest.mark.asyncio
    async def test_turno_lleno_no_se_ofrece(self, monkeypatch, sin_mundo_exterior):
        """20 reservas = cerrado: ese botón no aparece."""
        from agent import desafio

        async def cupo_1700_cerrado(fecha_iso, hora):
            return ("cerrado", 20) if hora == "17:00" else ("libre", 3)

        monkeypatch.setattr(desafio, "estado_cupo", cupo_1700_cerrado)
        p = ProveedorFalso()
        ok = await desafio.ofrecer_turnos_viernes("595", p)
        assert ok is True
        assert p.botones[-1][2] == ["desafio_vie_1930"]
