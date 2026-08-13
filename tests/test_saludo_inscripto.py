# tests/test_saludo_inscripto.py — Saludo determinístico del menú inscripto
# Casos sacados de la conversación real de Jazmin (13/08/2026): los saludos
# van por template con el nombre de Airtable; todo lo demás sigue a Haiku.

from agent.alumno_menu import _es_saludo_simple, _primer_nombre


def test_saludos_reales_matchean():
    # Mensajes reales que abrieron conversaciones de inscriptos
    assert _es_saludo_simple("Holaa")
    assert _es_saludo_simple("Holaa Aurora")
    assert _es_saludo_simple("Hola Aurora!")
    assert _es_saludo_simple("Buen dia")
    assert _es_saludo_simple("Buen diaa")
    assert _es_saludo_simple("Buenas tardes")
    assert _es_saludo_simple("hola, qué tal?")
    assert _es_saludo_simple("Hola! Todo bien?")


def test_mensajes_con_contenido_no_matchean():
    # Mensajes reales de la misma conversación que DEBEN ir al flujo conversacional
    assert not _es_saludo_simple("El sabado es feriado!")
    assert not _es_saludo_simple("Hoy hay clase normal!?")
    assert not _es_saludo_simple("Me falta un dia mas de class")
    assert not _es_saludo_simple("Puedo cambiar la fecha de la clase")
    assert not _es_saludo_simple("Soy Jazmin, para que puedas anotar bien el nombre")
    assert not _es_saludo_simple("Gracias")
    assert not _es_saludo_simple("1")          # atajo numérico del menú legacy
    assert not _es_saludo_simple("Ok ok")
    assert not _es_saludo_simple("")
    assert not _es_saludo_simple("Hola, puedo reagendar la clase del sabado?")


def test_primer_nombre_title_case():
    # En Airtable los nombres pueden venir en mayúsculas ("JAZMIN")
    assert _primer_nombre([{"nombre": "JAZMIN"}]) == "Jazmin"
    assert _primer_nombre([{"nombre": "Jorge Andrés"}]) == "Jorge"
    assert _primer_nombre([{"nombre": ""}]) == ""
    assert _primer_nombre([]) == ""
