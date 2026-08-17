# tests/test_desafio.py — Tests del DESAFÍO FENIX (campus de 2 días: sábado + domingo)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from agent.desafio import (
    proximo_campus, es_anticipada, precio_desafio, turnos_del_campus,
    label_campus, crear_reservas_campus,
    turnos_sabado_de, aviso_horario_especial, dias_especiales_proximos,
    campus_agotado_visible, nota_sold_out,
    PRECIO_ANTICIPADA, PRECIO_NORMAL, TURNOS_SABADO, HORA_DOMINGO,
)

TZ = ZoneInfo("America/Asuncion")


def py(anio, mes, dia, hora=12, minuto=0):
    """Un momento concreto en hora de Paraguay."""
    return datetime(anio, mes, dia, hora, minuto, tzinfo=TZ)


class TestProximoCampus:
    """Qué fin de semana se está vendiendo.

    La mecánica se prueba sobre la semana del 22/08: los diccionarios de
    excepciones (feriados, sold-outs) están vacíos, así que las excepciones
    se inyectan con monkeypatch en sus propias clases.
    """

    def test_domingo_previo_ofrece_el_finde_siguiente(self):
        # Domingo 23/08/2026 a la noche → campus 29 y 30
        c = proximo_campus(py(2026, 8, 23, 22, 30))
        assert c == {"sabado": date(2026, 8, 29),
                     "domingo": date(2026, 8, 30)}

    def test_lunes_ofrece_el_sabado_de_esa_semana(self):
        c = proximo_campus(py(2026, 8, 17, 9))
        assert c["sabado"] == date(2026, 8, 22)

    def test_viernes_todavia_ofrece_el_de_manana(self):
        c = proximo_campus(py(2026, 8, 21, 23, 50))
        assert c["sabado"] == date(2026, 8, 22)

    def test_sabado_antes_de_las_11_sigue_vendiendo_el_de_hoy(self):
        # Iván: se puede reservar hasta que arranca el turno 1 del sábado
        c = proximo_campus(py(2026, 8, 22, 10, 59))
        assert c["sabado"] == date(2026, 8, 22)

    def test_sabado_ya_empezado_salta_al_siguiente(self):
        c = proximo_campus(py(2026, 8, 22, 11, 0))
        assert c["sabado"] == date(2026, 8, 29)

    def test_domingo_del_campus_en_curso_ofrece_el_siguiente(self):
        # El campus 22-23 está en su día 2: ya no se puede vender
        c = proximo_campus(py(2026, 8, 23, 10))
        assert c["sabado"] == date(2026, 8, 29)

    def test_los_campus_anunciados_caen_sabado_y_domingo(self):
        for sabado in (date(2026, 8, 22), date(2026, 8, 29), date(2026, 9, 5)):
            c = proximo_campus(py(sabado.year, sabado.month, sabado.day, 8))
            assert c["sabado"] == sabado
            assert c["sabado"].weekday() == 5
            assert c["domingo"].weekday() == 6

    def test_el_campus_ya_no_tiene_viernes(self):
        # El dict perdió la clave a propósito: un consumidor olvidado tiene
        # que explotar ruidoso, no seguir anclado al viernes en silencio.
        c = proximo_campus(py(2026, 8, 17))
        assert "viernes" not in c


class TestPrecio:
    """300.000 hasta el viernes 23:59; 450.000 desde el sábado. +150.000 por hermano."""

    def test_anticipada_un_hijo(self):
        monto, anticipada = precio_desafio(1, py(2026, 8, 17, 9))
        assert (monto, anticipada) == (300_000, True)

    def test_anticipada_dos_hermanos(self):
        assert precio_desafio(2, py(2026, 8, 17, 9))[0] == 450_000

    def test_anticipada_tres_hermanos(self):
        assert precio_desafio(3, py(2026, 8, 17, 9))[0] == 600_000

    def test_viernes_2359_todavia_es_anticipada(self):
        monto, anticipada = precio_desafio(1, py(2026, 8, 21, 23, 59))
        assert (monto, anticipada) == (300_000, True)

    def test_sabado_00_01_ya_es_precio_normal(self):
        monto, anticipada = precio_desafio(1, py(2026, 8, 22, 0, 1))
        assert (monto, anticipada) == (450_000, False)

    def test_normal_con_hermanos(self):
        assert precio_desafio(2, py(2026, 8, 22, 9))[0] == 600_000
        assert precio_desafio(3, py(2026, 8, 22, 9))[0] == 750_000

    def test_domingo_vende_el_campus_siguiente_a_precio_anticipado(self):
        # Ya no se vende el campus en curso → el siguiente todavía es anticipada
        monto, anticipada = precio_desafio(1, py(2026, 8, 23, 11))
        assert (monto, anticipada) == (300_000, True)

    def test_hijos_cero_o_none_cuenta_como_uno(self):
        assert precio_desafio(0, py(2026, 8, 17))[0] == PRECIO_ANTICIPADA
        assert precio_desafio(None, py(2026, 8, 17))[0] == PRECIO_ANTICIPADA

    def test_es_anticipada_coherente_con_el_precio(self):
        momento = py(2026, 8, 22, 9)
        assert es_anticipada(momento) is False
        assert precio_desafio(1, momento)[0] == PRECIO_NORMAL


class TestTurnosYLabel:

    def test_tres_slots_en_orden(self):
        slots = turnos_del_campus(proximo_campus(py(2026, 8, 17)))
        assert slots == [
            ("2026-08-22", "11:00"), ("2026-08-22", "15:30"),
            ("2026-08-23", "15:30"),
        ]

    def test_label_mismo_mes(self):
        assert label_campus(proximo_campus(py(2026, 8, 17))) == \
            "sábado 22 y domingo 23 de agosto"

    def test_label_cruzando_de_mes(self):
        campus = {"sabado": date(2026, 10, 31), "domingo": date(2026, 11, 1)}
        label = label_campus(campus)
        assert "octubre" in label and "noviembre" in label


class TestTurnosEspeciales:
    """Un feriado corre con un solo turno el sábado.

    La excepción va por FECHA, así que se apaga sola: el campus siguiente
    vuelve a tener los dos turnos sin que nadie toque el código. Como el dict
    real está vacío, cada test inyecta su feriado sintético.
    """

    CAMPUS_FERIADO = {"sabado": date(2026, 8, 22), "domingo": date(2026, 8, 23)}
    ESPECIALES = {"2026-08-22": ("11:00",)}

    @pytest.fixture
    def finde_feriado(self, monkeypatch):
        from agent import desafio
        monkeypatch.setattr(desafio, "TURNOS_ESPECIALES", dict(self.ESPECIALES))

    def test_el_sabado_feriado_tiene_un_solo_turno(self, finde_feriado):
        assert turnos_sabado_de(self.CAMPUS_FERIADO) == ("11:00",)

    def test_el_campus_siguiente_vuelve_a_los_dos_turnos(self, finde_feriado):
        c = proximo_campus(py(2026, 8, 24))
        assert turnos_sabado_de(c) == TURNOS_SABADO

    def test_el_finde_feriado_tiene_dos_slots_y_no_tres(self, finde_feriado):
        assert turnos_del_campus(self.CAMPUS_FERIADO) == [
            ("2026-08-22", "11:00"), ("2026-08-23", "15:30"),
        ]

    @pytest.mark.asyncio
    async def test_no_se_puede_reservar_un_turno_que_no_corre_ese_finde(self, finde_feriado):
        with pytest.raises(ValueError):
            await crear_reservas_campus(["recX"], "15:30", self.CAMPUS_FERIADO)

    def test_el_feriado_no_tiene_entrenamiento_regular(self, finde_feriado):
        from agent.desafio import hay_entrenamiento_regular
        assert hay_entrenamiento_regular("2026-08-22") is False
        assert hay_entrenamiento_regular("2026-08-29") is True

    def test_el_aviso_dice_que_no_hay_entrenamiento(self, finde_feriado):
        # Regla de Iván (12/08): feriado = nadie entrena, solo corre el campus.
        aviso = aviso_horario_especial(date(2026, 8, 19))
        assert aviso and "NO HAY ENTRENAMIENTO REGULAR" in aviso
        assert "la respuesta es NO" in aviso

    def test_el_aviso_menciona_que_el_campus_esta_lleno(self, finde_feriado, monkeypatch):
        from agent import desafio
        monkeypatch.setattr(desafio, "CAMPUS_AGOTADOS", {"2026-08-22"})
        aviso = aviso_horario_especial(date(2026, 8, 19))
        assert aviso and "COMPLETO" in aviso

    def test_el_aviso_sigue_vigente_el_sabado_a_la_mañana(self, finde_feriado):
        # proximo_campus() ese día puede apuntar al finde siguiente, pero la mamá
        # que pregunta "¿hay entrenamiento hoy?" tiene que escuchar que NO hay.
        aviso = aviso_horario_especial(date(2026, 8, 22))
        assert aviso and "NO HAY ENTRENAMIENTO REGULAR" in aviso

    def test_el_aviso_desaparece_solo_cuando_pasa_el_finde(self, finde_feriado):
        assert aviso_horario_especial(date(2026, 8, 24)) is None
        assert dias_especiales_proximos(date(2026, 8, 24)) == []

    def test_el_aviso_no_aparece_con_mucha_anticipacion(self, finde_feriado):
        assert aviso_horario_especial(date(2026, 7, 20)) is None

    @pytest.mark.asyncio
    async def test_horarios_disponibles_saltea_el_feriado_entero(self, finde_feriado, monkeypatch):
        """Los slots del feriado EXISTEN en Airtable (son las sesiones del campus),
        pero como entrenamiento regular no se ofrece NINGUNO: ese día nadie entrena."""
        import agent.airtable_client as ac

        async def fake_get_records(tabla, formula=None, max_records=None, **kw):
            return [
                {"id": "r1", "fields": {"FECHA": "2026-08-22", "HORA": "11:00"}},  # feriado: campus
                {"id": "r2", "fields": {"FECHA": "2026-08-22", "HORA": "15:30"}},  # feriado: ni existe
                {"id": "r3", "fields": {"FECHA": "2026-08-29", "HORA": "15:30"}},  # normal: sí
            ]

        monkeypatch.setattr(ac, "_get_records", fake_get_records)
        horarios = await ac.obtener_horarios_disponibles()
        slots = [(h["fecha"], h["hora"]) for h in horarios]
        assert ("2026-08-22", "11:00") not in slots
        assert ("2026-08-22", "15:30") not in slots
        assert ("2026-08-29", "15:30") in slots

    @pytest.mark.asyncio
    async def test_el_hook_rebota_el_sabado_feriado(self, finde_feriado):
        """Ni agendar ni reagendar al sábado feriado: no hay entrenamiento ese día."""
        from agent.hooks import validar_fecha_hora
        r = await validar_fecha_hora("gestionar_reserva",
                                     {"fecha": "2026-08-22", "hora": "11:00"}, {})
        assert r and r["error"] and "feriado" in r["message"]
        # El sábado siguiente pasa normal
        r = await validar_fecha_hora("gestionar_reserva",
                                     {"fecha": "2026-08-29", "hora": "11:00"}, {})
        assert r is None


class TestCampusAgotado:
    """Un campus SOLD OUT no se vende, pero se anuncia con orgullo.

    proximo_campus() lo saltea, así que precio, turnos y textos pasan solos al
    campus siguiente. El aviso de sold out vive hasta su domingo y muere solo.
    Como el set real está vacío, el sold out se inyecta con monkeypatch.
    """

    @pytest.fixture
    def sold_out_22(self, monkeypatch):
        from agent import desafio
        monkeypatch.setattr(desafio, "CAMPUS_AGOTADOS", {"2026-08-22"})

    def test_el_miercoles_ya_se_vende_el_29(self, sold_out_22):
        c = proximo_campus(py(2026, 8, 19, 22))
        assert c["sabado"] == date(2026, 8, 29)

    def test_el_sabado_agotado_a_la_manana_tampoco_se_vende(self, sold_out_22):
        # Sin sold out, el 22 antes de las 11:00 todavía se vendía
        c = proximo_campus(py(2026, 8, 22, 9))
        assert c["sabado"] == date(2026, 8, 29)

    def test_el_precio_es_el_promocional_del_campus_siguiente(self, sold_out_22):
        # Anticipada del 29: vale hasta el viernes 28 a las 23:59
        assert precio_desafio(1, py(2026, 8, 19, 23)) == (300_000, True)
        assert precio_desafio(1, py(2026, 8, 28, 23, 59)) == (300_000, True)
        assert precio_desafio(1, py(2026, 8, 29, 0, 1)) == (450_000, False)

    def test_el_campus_que_se_vende_tiene_los_turnos_completos(self, sold_out_22):
        slots = turnos_del_campus(proximo_campus(py(2026, 8, 19, 22)))
        assert slots == [
            ("2026-08-29", "11:00"), ("2026-08-29", "15:30"),
            ("2026-08-30", "15:30"),
        ]

    def test_el_sold_out_es_visible_hasta_su_domingo(self, sold_out_22):
        assert campus_agotado_visible(date(2026, 8, 19))["sabado"] == date(2026, 8, 22)
        assert campus_agotado_visible(date(2026, 8, 23)) is not None
        assert campus_agotado_visible(date(2026, 8, 24)) is None

    def test_la_nota_de_sold_out_aparece_y_se_apaga_sola(self, sold_out_22):
        nota = nota_sold_out(date(2026, 8, 19))
        assert nota and "SOLD OUT" in nota and "22" in nota
        assert nota_sold_out(date(2026, 8, 24)) is None


class TestCrearReservas:
    """Dos reservas por niño; un turno inventado no se adivina."""

    @pytest.mark.asyncio
    async def test_turno_sabado_invalido_explota(self):
        with pytest.raises(ValueError):
            await crear_reservas_campus(["recX"], "9:30")

    @pytest.mark.asyncio
    async def test_crea_dos_reservas_por_nino(self, monkeypatch):
        pedidos = []

        async def fake_horario(fecha_iso, hora):
            pedidos.append((fecha_iso, hora))
            return f"horario:{fecha_iso}:{hora}"

        async def fake_reserva(nino_id, horario_id):
            return f"reserva:{nino_id}:{horario_id}"

        import agent.airtable_client as ac
        monkeypatch.setattr(ac, "obtener_o_crear_horario", fake_horario)
        monkeypatch.setattr(ac, "crear_reserva", fake_reserva)

        campus = proximo_campus(py(2026, 8, 17))   # finde normal, dos turnos el sábado
        reservas = await crear_reservas_campus(["nino1", "nino2"], "15:30", campus)

        assert len(reservas) == 4  # 2 niños × 2 días
        assert pedidos[:2] == [("2026-08-22", "15:30"),
                               ("2026-08-23", HORA_DOMINGO)]

    @pytest.mark.asyncio
    async def test_si_falla_el_domingo_el_sabado_igual_se_reserva(self, monkeypatch):
        async def fake_horario(fecha_iso, hora):
            # El domingo es el segundo pedido: falla ese, no el del sábado
            return None if fecha_iso.endswith("-23") else f"horario:{hora}"

        async def fake_reserva(nino_id, horario_id):
            return f"reserva:{horario_id}"

        import agent.airtable_client as ac
        monkeypatch.setattr(ac, "obtener_o_crear_horario", fake_horario)
        monkeypatch.setattr(ac, "crear_reserva", fake_reserva)

        reservas = await crear_reservas_campus(["nino1"], "11:00",
                                               proximo_campus(py(2026, 8, 17)))
        assert len(reservas) == 1


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


CAMPUS_NORMAL = {"sabado": date(2026, 8, 22), "domingo": date(2026, 8, 23)}


@pytest.fixture
def sin_mundo_exterior(monkeypatch):
    """Neutraliza DB, Airtable y Telegram; devuelve los flags que se fueron escribiendo.

    Congela además el campus en uno NORMAL: si no, estos tests prueban la mecánica
    de elección de turno contra el calendario real y se rompen solos cuando cae un
    fin de semana con turno único (pasó con el feriado del 14/08).
    """
    from agent import desafio
    escritos = {}

    monkeypatch.setattr(desafio, "proximo_campus", lambda *a, **kw: CAMPUS_NORMAL)

    async def fake_flags(telefono, **kw):
        escritos.update(kw)

    async def fake_guardar(*a, **kw):
        return None

    async def fake_cupo(fecha_iso, hora):
        return "libre", 0

    async def fake_grupo(telefono):
        return {"hijos": [{"id": "ninoA"}], "tutores": []}

    async def fake_reservas(nino_ids, ts, campus=None):
        escritos["_reservas"] = (list(nino_ids), ts)
        return ["r1", "r2"]

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
    """El padre pagó: elige el turno del sábado con botones, en UN paso."""

    @pytest.mark.asyncio
    async def test_sin_flag_no_intercepta_nada(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        r = await manejar_eleccion_turno("595", "hola", None, False, {}, ProveedorFalso())
        assert r is None  # el mensaje sigue su curso normal

    @pytest.mark.asyncio
    async def test_ofrecer_turnos_deja_el_flag_en_sabado(self, sin_mundo_exterior):
        from agent import desafio
        p = ProveedorFalso()
        ok = await desafio.ofrecer_turnos_campus("595", p)
        assert ok is True
        assert p.botones[-1][2] == ["desafio_sab_1100", "desafio_sab_1530"]
        assert sin_mundo_exterior["desafio_espera_turno"] == "sabado"

    @pytest.mark.asyncio
    async def test_boton_sabado_crea_las_reservas_y_confirma_en_un_paso(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "", "desafio_sab_1100", True,
                                         {"desafio_espera_turno": "sabado"}, p)
        assert r == "[campus reservado]"
        assert sin_mundo_exterior["_reservas"] == (["ninoA"], "11:00")
        assert sin_mundo_exterior["desafio_espera_turno"] is None
        confirmacion = p.mensajes[-1][1]
        for parte in ("11:00", "15:30", "merienda", "Casona"):
            assert parte in confirmacion

    @pytest.mark.asyncio
    async def test_flag_viejo_de_viernes_entra_al_paso_del_sabado(self, sin_mundo_exterior):
        # Residuo del flujo de 3 días: un padre que quedó a mitad de la elección
        # vieja en el momento del deploy no puede quedar mudo ni colgado.
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "", "desafio_sab_1530", True,
                                         {"desafio_espera_turno": "viernes"}, p)
        assert r == "[campus reservado]"
        assert sin_mundo_exterior["_reservas"] == (["ninoA"], "15:30")

    @pytest.mark.asyncio
    async def test_texto_con_la_hora_tambien_vale(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "prefiero 15:30", None, False,
                                         {"desafio_espera_turno": "sabado"}, p)
        assert r == "[campus reservado]"
        assert sin_mundo_exterior["_reservas"] == (["ninoA"], "15:30")

    @pytest.mark.asyncio
    async def test_respuesta_que_no_es_un_turno_reofrece_los_botones(self, sin_mundo_exterior):
        from agent.desafio import manejar_eleccion_turno
        p = ProveedorFalso()
        r = await manejar_eleccion_turno("595", "y el domingo a qué hora?", None, False,
                                         {"desafio_espera_turno": "sabado"}, p)
        assert r == "[turno: recordatorio]"
        assert p.botones[-1][2] == ["desafio_sab_1100", "desafio_sab_1530"]

    @pytest.mark.asyncio
    async def test_turno_lleno_no_se_ofrece(self, monkeypatch, sin_mundo_exterior):
        """20 reservas = cerrado: ese botón no aparece."""
        from agent import desafio

        async def cupo_1100_cerrado(fecha_iso, hora):
            return ("cerrado", 20) if hora == "11:00" else ("libre", 3)

        monkeypatch.setattr(desafio, "estado_cupo", cupo_1100_cerrado)
        p = ProveedorFalso()
        ok = await desafio.ofrecer_turnos_campus("595", p)
        assert ok is True
        assert p.botones[-1][2] == ["desafio_sab_1530"]
        # Quedó UN turno por cupo, no por feriado: el texto no puede decir feriado
        assert "feriado" not in p.botones[-1][1]
        assert "un solo turno con lugar" in p.botones[-1][1]

    @pytest.mark.asyncio
    async def test_el_finde_feriado_ofrece_un_solo_boton(self, monkeypatch, sin_mundo_exterior):
        """Feriado: el padre ve un botón, no dos, y el texto le explica por qué."""
        from agent import desafio

        monkeypatch.setattr(desafio, "TURNOS_ESPECIALES", {"2026-08-22": ("11:00",)})
        p = ProveedorFalso()
        ok = await desafio.ofrecer_turnos_campus("595", p)
        assert ok is True
        assert p.botones[-1][2] == ["desafio_sab_1100"]
        assert "un solo turno" in p.botones[-1][1]

    @pytest.mark.asyncio
    async def test_el_finde_feriado_no_acepta_el_turno_que_no_corre(self, monkeypatch, sin_mundo_exterior):
        """Si el padre escribe "15:30" ese sábado, se le reofrece el único turno."""
        from agent import desafio

        monkeypatch.setattr(desafio, "TURNOS_ESPECIALES", {"2026-08-22": ("11:00",)})
        p = ProveedorFalso()
        r = await desafio.manejar_eleccion_turno("595", "prefiero 15:30", None, False,
                                                 {"desafio_espera_turno": "sabado"}, p)
        assert r == "[turno: recordatorio]"
        assert p.botones[-1][2] == ["desafio_sab_1100"]
