# tests/test_extractor_nombres.py — Tests del validador de nombres
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.validar_nombre import validar_nombre, es_nombre_valido


class TestPositivos:
    """Nombres que DEBEN ser aceptados."""

    def test_nombre_comun_mujer(self):
        r = validar_nombre("Victoria")
        assert r["valido"] is True
        assert r["confianza"] == "alta"

    def test_nombre_y_apellido(self):
        r = validar_nombre("Victoria Lezcano")
        assert r["valido"] is True

    def test_nombre_comun_hombre(self):
        r = validar_nombre("Mateo")
        assert r["valido"] is True
        assert r["confianza"] == "alta"

    def test_nombre_angel(self):
        assert es_nombre_valido("Angel") is True

    def test_nombre_alejandra(self):
        assert es_nombre_valido("Alejandra") is True

    def test_nombre_con_tilde(self):
        assert es_nombre_valido("María") is True

    def test_nombre_guarani_arami(self):
        """Nombre guaraní — puede ser confianza baja si no está en lista."""
        r = validar_nombre("Arami")
        assert r["valido"] is True  # pasa morfología

    def test_nombre_carolina_hijo_lucas(self):
        assert es_nombre_valido("Carolina") is True
        assert es_nombre_valido("Lucas") is True

    def test_diminutivo_nico(self):
        assert es_nombre_valido("Nico") is True

    def test_diminutivo_mati(self):
        assert es_nombre_valido("Mati") is True


class TestNegativos:
    """Nombres que DEBEN ser rechazados."""

    def test_gracias_graciss(self):
        assert es_nombre_valido("Gracias") is False
        assert es_nombre_valido("Graciss") is False

    def test_de_dianosticaron(self):
        assert es_nombre_valido("Dianosticaron") is False

    def test_es_muy(self):
        assert es_nombre_valido("Muy") is False

    def test_diagnosticaron(self):
        assert es_nombre_valido("Diagnosticaron") is False

    def test_estudiando(self):
        assert es_nombre_valido("Estudiando") is False

    def test_tiene(self):
        assert es_nombre_valido("Tiene") is False

    def test_entre(self):
        assert es_nombre_valido("Entre") is False

    def test_bueno(self):
        assert es_nombre_valido("Bueno") is False

    def test_entiendo(self):
        assert es_nombre_valido("Entiendo") is False

    def test_perfecto(self):
        assert es_nombre_valido("Perfecto") is False

    def test_genial(self):
        assert es_nombre_valido("Genial") is False

    def test_muy_corto(self):
        assert es_nombre_valido("Al") is False

    def test_con_numeros(self):
        assert es_nombre_valido("Juan3") is False

    def test_frase_larga(self):
        assert es_nombre_valido("Le diagnosticaron TDAH hace poco") is False

    def test_dale(self):
        assert es_nombre_valido("Dale") is False

    def test_super(self):
        assert es_nombre_valido("Super") is False


class TestConfianza:
    """Verificar niveles de confianza."""

    def test_nombre_comun_alta(self):
        r = validar_nombre("Santiago")
        assert r["confianza"] == "alta"

    def test_nombre_raro_baja(self):
        """Nombre que pasa morfología pero no está en lista."""
        r = validar_nombre("Xyloph")
        assert r["valido"] is True
        assert r["confianza"] == "baja"

    def test_basura_nula(self):
        r = validar_nombre("Diagnosticaron")
        assert r["confianza"] == "nula"


class TestListaCargada:
    """Verificar que la lista de nombres se carga."""

    def test_lista_no_vacia(self):
        from agent.validar_nombre import _cargar_nombres, _NOMBRES_SET
        _cargar_nombres()
        assert len(_NOMBRES_SET) > 100, f"Lista tiene solo {len(_NOMBRES_SET)} nombres"
