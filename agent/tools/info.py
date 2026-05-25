# agent/tools/info.py — Respuestas de información para leads
# Funciones puras que retornan datos. No envían WhatsApp ni Telegram.

import os
import logging

logger = logging.getLogger("agentkit")


async def consultar_precios(tipo: str = "prueba", **kwargs) -> dict:
    """Retorna precios según tipo."""
    if tipo == "hermanos":
        return {
            "texto": (
                "👦👦 *Hermanos (cada hijo extra +50mil):*\n"
                "Prueba: 1 hijo 100mil | 2 hermanos 150mil | 3 hermanos 200mil\n"
                "Mensual: 1 hijo 300mil | 2 hermanos 350mil | 3 hermanos 400mil"
            ),
            "enviar_afiche": "hermanos",
        }
    elif tipo == "paquetes":
        return {
            "texto": (
                "🌳 *Plan Invierno FENIX:*\n"
                "Clase de prueba (1 sábado): 100.000 Gs\n"
                "Mensual (4 sábados): 300.000 Gs\n"
                "+50.000 por cada hijo extra"
            ),
        }
    else:
        return {
            "texto": (
                "🌳 *Probá FENIX (padres entran gratis):*\n"
                "👦 *Clase de prueba:* 100.000 Gs (1 sábado)\n"
                "📅 *Mensual:* 300.000 Gs (4 sábados)\n"
                "+50.000 por cada hijo extra"
            ),
            "enviar_afiche": "precios",
        }


async def consultar_horarios(**kwargs) -> dict:
    """Retorna horarios disponibles."""
    return {
        "texto": "Entrenamos todos los sábados 🌳\n\nHorarios invierno: 11:00h | 15:30h",
        "enviar_afiche": "horarios",
    }


async def consultar_ubicacion(**kwargs) -> dict:
    """Retorna ubicación y mapa."""
    return {
        "texto": (
            "📍 FENIX Kids Academy — Parque Fenix dentro de La Casona Lafuente\n"
            "Maestras Paraguayas 2056\n"
            "https://maps.app.goo.gl/nZT5zGA7N8B76xmD6?g_st=iwb"
        ),
    }


async def consultar_duracion(**kwargs) -> dict:
    """Retorna duración de la clase."""
    return {
        "texto": "La clase dura 80 minutos 💪 Y mientras tu hijo entrena, vos también podés entrenar con nuestro profe en el mismo parque 🌳",
    }


async def consultar_que_llevar(**kwargs) -> dict:
    """Retorna qué llevar a la clase."""
    return {
        "texto": "Traé ropa cómoda, zapatillas y agua 💧 Nosotros ponemos todo el equipamiento 🌳",
    }


async def consultar_devolucion(**kwargs) -> dict:
    """Retorna política de devolución."""
    return {
        "texto": "La clase de prueba no tiene compromiso. Si no se enganchan, no hay problema 🤝",
    }


async def consultar_medios_pago(**kwargs) -> dict:
    """Retorna medios de pago aceptados."""
    return {
        "texto": "Para reservar el sábado, solo transferencia bancaria. Después aceptamos todos los medios de pago 🤝",
    }


async def enviar_datos_bancarios(**kwargs) -> dict:
    """Retorna datos bancarios para transferencia."""
    return {
        "texto": (
            "ALIAS: 1604338\n"
            "Banco: Itaú\n"
            "Ivan Lafuente\n\n"
            "Mandame la foto del comprobante cuando hagas la transferencia 📸"
        ),
    }
