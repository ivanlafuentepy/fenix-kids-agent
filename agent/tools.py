# agent/tools.py — Herramientas del agente Dorita
# Generado por AgentKit para Salsa Soul Studio

"""
Herramientas específicas de Salsa Soul Studio.
Casos de uso: FAQ, conversión de leads, inscripción, atención a alumnos regulares.
"""

import os
import yaml
import logging

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horarios_principiantes() -> str:
    """Retorna los horarios de principiantes formateados."""
    return (
        "🗓️ Horarios para principiantes (desde cero):\n\n"
        "📅 Martes 🕢 19:30 — 💃 Salsa\n"
        "📅 Jueves 🕢 19:30 — 🎵 Bachata\n"
        "📅 Sábado 🕔 17:15 — 🎵 Bachata | 🕡 18:30 — 💃 Salsa\n\n"
        "✅ Podés alternar días sin problema\n"
        "⏰ Cada clase dura aproximadamente 1 hora"
    )


def obtener_precios() -> str:
    """Retorna los precios actuales formateados."""
    return (
        "🎁 Nuestros planes:\n\n"
        "✅ 130.000 gs/mes → 1 clase por semana\n"
        "✅ 150.000 gs/mes → FULL PASS (todas las clases que puedas)\n"
        "✅ Matrícula única: 100.000 gs\n"
        "✅ Garantía: si después de la 1ra clase no te gustó, devolvemos el 100% 🤝\n\n"
        "Plan pareja (primer mes): 350.000 gs total\n"
        "(150.000 los dos + 100.000 gs matrícula cada uno)"
    )


def obtener_datos_pago() -> str:
    """Retorna los datos bancarios para transferencia."""
    return (
        "Datos para transferencia:\n\n"
        "🏦 Banco Itaú\n"
        "👤 Iván Lafuente\n"
        "🔢 CI/Alias: 1604338\n"
        "📱 Cell: 0982790407"
    )


def obtener_ubicacion() -> str:
    """Retorna la dirección y links de ubicación."""
    return (
        "📍 Dr. Manuel Domínguez 634 entre Antequera y Paraguarí, Asunción\n"
        "(A 5 cuadras del Mall Excelsior)\n\n"
        "🗺️ Ver en Maps: https://goo.gl/maps/2EUTP8VHh332\n\n"
        "🚗 Hay estacionamiento frente a la academia y en los alrededores.\n"
        "Zona segura del centro — hay patrullera policial en horario de clases."
    )


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."
