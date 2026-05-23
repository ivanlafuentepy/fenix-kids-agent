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
                "👦👦 *Descuentos hermanos:*\n"
                "Paq 5 clases: 2do hijo 30% OFF (245mil), 3er hijo 50% OFF (175mil)\n"
                "Paq 12 clases: 2do hijo 40% OFF (450mil), 3er hijo GRATIS 🎁"
            ),
            "enviar_afiche": "hermanos",
        }
    elif tipo == "paquetes":
        return {
            "texto": (
                "⭐ *Paquetes (sin matrícula, sin vencimiento):*\n"
                "5 clases: 350.000 Gs | 12 clases: 750.000 Gs"
            ),
        }
    else:
        return {
            "texto": (
                "🌳 *Probá FENIX (padres entran gratis):*\n"
                "👦 Prueba: 90.000 Gs (1 sábado)\n"
                "🔥 *PROMO:* 100.000 Gs por 2 sábados\n\n"
                "⭐ *Paquetes (sin matrícula, sin vencimiento):*\n"
                "5 clases: 350.000 Gs | 12 clases: 750.000 Gs"
            ),
            "enviar_afiche": "precios",
        }


async def consultar_horarios(**kwargs) -> dict:
    """Retorna horarios disponibles."""
    return {
        "texto": "Entrenamos todos los sábados 🌳\n\nHorarios: 9:30h | 11:00h | 15:30h",
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
            "➡️Transferencia Bancaria.\n"
            "✅ALIAS CI (1604338)\n"
            "⬇️⬇️⬇️\n"
            "Ivan Lafuente\n"
            "Itaú\n"
            "Cta cte 1074574\n"
            "Ci 1604338\n"
            "Cell 0982790407\n\n"
            "🙏Muchas Gracias 🙏\n\n"
            "Mandame la foto del comprobante cuando hagas la transferencia 📸"
        ),
    }
