# agent/brain.py — Cerebro del agente: conexión con Claude API
# FENIX KIDS ACADEMY — dual agente: Profe Ivan + Nixie

"""
Genera respuestas usando la API de Anthropic Claude.
Soporta dos agentes distintos: ivan y nixie.
Lee los prompts desde config/prompts.yaml y los selecciona según el agente activo.
"""

import os
import yaml
import asyncio
import logging
from datetime import datetime
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def _contexto_fechas() -> str:
    """
    Inyecta la fecha actual y los próximos sábados disponibles.
    Se agrega al system prompt para que los agentes nunca tengan que calcular fechas.
    """
    from zoneinfo import ZoneInfo
    from datetime import date, timedelta as td

    tz_py = ZoneInfo("America/Asuncion")
    ahora = datetime.now(tz_py)
    hoy = ahora.date()

    dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    def proximos_sabados(n: int = 4) -> list[date]:
        dias_hasta = (5 - hoy.weekday()) % 7  # 5 = sábado
        if dias_hasta == 0:
            dias_hasta = 7
        primero = hoy + td(days=dias_hasta)
        return [primero + td(weeks=i) for i in range(n)]

    def fmt(d: date) -> str:
        return f"sábado {d.day} de {meses_es[d.month - 1]}"

    hoy_str = f"{dias_es[hoy.weekday()]} {hoy.day} de {meses_es[hoy.month - 1]} de {hoy.year}"
    sabados = proximos_sabados(8)
    sabados_str = "\n".join(f"  - {fmt(s)}" for s in sabados)

    return (
        f"Hoy es {hoy_str} (hora Asunción, Paraguay).\n"
        f"Próximos sábados disponibles:\n{sabados_str}\n"
        f"Horarios de cada sábado: 9:30h | 11:00h | 15:30h\n"
        f"IMPORTANTE: Usá EXACTAMENTE estas fechas al confirmar reservas."
    )


def cargar_prompt_agente(agent_actual: str) -> str:
    """Carga el system prompt del agente indicado e inyecta contexto de fechas."""
    config = cargar_config_prompts()
    clave = "nixie_prompt" if agent_actual == "nixie" else "ivan_prompt"
    prompt = config.get(clave, f"Sos {agent_actual} de FENIX KIDS ACADEMY. Respondé en español.")
    return f"{_contexto_fechas()}\n\n{prompt}"


def obtener_mensaje_error() -> str:
    config = cargar_config_prompts()
    return config.get("error_message", "Ups, algo falló de mi lado. Intentá de nuevo en unos minutitos 🙏")


def obtener_mensaje_fallback() -> str:
    config = cargar_config_prompts()
    return config.get("fallback_message", "No entendí bien tu mensaje 😊 ¿Podés reformularlo?")


async def generar_respuesta(
    mensaje: str,
    historial: list[dict],
    agent_actual: str = "ivan",
    contexto_extra: str | None = None,
) -> str:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]
        agent_actual: "ivan" o "nixie" — determina qué prompt se usa
        contexto_extra: Texto adicional inyectado al final del system prompt

    Returns:
        La respuesta generada por Claude
    """
    if not mensaje or not mensaje.strip():
        return obtener_mensaje_fallback()

    system_prompt = cargar_prompt_agente(agent_actual)

    if contexto_extra:
        system_prompt += f"\n\n{contexto_extra}"

    mensajes = [{"role": m["role"], "content": m["content"]} for m in historial]
    mensajes.append({"role": "user", "content": mensaje})

    # Retry con backoff exponencial (3 intentos)
    _MAX_REINTENTOS = 3
    for _intento in range(_MAX_REINTENTOS):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=mensajes,
            )
            respuesta = response.content[0].text
            logger.info(
                f"[{agent_actual.upper()}] Respuesta generada "
                f"({response.usage.input_tokens} in / {response.usage.output_tokens} out)"
            )
            return respuesta

        except Exception as e:
            _es_transitorio = any(k in str(e).lower() for k in ("timeout", "connect", "overloaded", "529", "rate"))
            if _es_transitorio and _intento < _MAX_REINTENTOS - 1:
                _espera = 2 ** _intento
                logger.warning(f"[Claude API] Reintento {_intento + 1}/{_MAX_REINTENTOS} en {_espera}s — {e}")
                await asyncio.sleep(_espera)
            else:
                logger.error(f"Error Claude API (intento {_intento + 1}): {e}")
                return obtener_mensaje_error()


async def extraer_datos_formulario(historial: list[dict]) -> dict:
    """
    Usa Claude Haiku para extraer datos del formulario del historial de conversación.
    Extrae: datos de hijo/s, padre y madre.

    Returns:
        {
          "ninos": [{"nombre", "apellido", "ci", "fecha_nacimiento", "sexo", "talla_remera"}],
          "padre": {"nombre", "apellido", "ci", "telefono", "email", "fecha_nacimiento"} | None,
          "madre": {"nombre", "apellido", "ci", "telefono", "email", "fecha_nacimiento"} | None,
          "completo": bool
        }
    """
    import json as _json

    historial_texto = "\n".join(
        f"{'PADRE' if m['role'] == 'user' else 'NIXIE'}: {m['content']}"
        for m in historial[-30:]
    )

    prompt_extraccion = """Analizá este historial de chat y extraé los datos de formulario.

Devolvé ÚNICAMENTE un JSON con esta estructura exacta (sin texto adicional):
{
  "ninos": [
    {
      "nombre": "string o null",
      "apellido": "string o null",
      "ci": null,
      "fecha_nacimiento": "YYYY-MM-DD o null",
      "sexo": null,
      "talla_remera": null
    }
  ],
  "padre": {
    "nombre": "string o null",
    "apellido": "string o null",
    "ci": null,
    "telefono": null,
    "email": null,
    "fecha_nacimiento": null
  },
  "madre": null
}

Reglas:
- Solo extraé: nombre y apellido del niño, fecha de nacimiento del niño, nombre y apellido del padre/madre que escribió
- Los demás campos dejálos en null (no se piden en clase de prueba)
- Para fecha_nacimiento: convertí al formato YYYY-MM-DD
- Si hay múltiples niños, incluí uno por cada uno en el array "ninos"
- El padre/madre es quien está escribiendo (poné sus datos en "padre", dejá "madre" como null)

Historial:
""" + historial_texto

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt_extraccion}],
        )
        texto = response.content[0].text.strip()
        # Limpiar posibles bloques de código markdown
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.startswith("json"):
                texto = texto[4:]
        datos = _json.loads(texto)

        # Verificar si los datos están completos
        ninos = datos.get("ninos", [])
        padre = datos.get("padre") or {}
        madre = datos.get("madre") or {}

        nino_completo = bool(
            ninos and all(
                n.get("nombre") and n.get("apellido") and n.get("fecha_nacimiento")
                for n in ninos
            )
        )
        padre_completo = bool(padre.get("nombre") and padre.get("apellido"))
        madre_completo = bool(madre.get("nombre") and madre.get("apellido"))

        datos["completo"] = nino_completo and (padre_completo or madre_completo)
        return datos

    except Exception as e:
        logger.error(f"Error extrayendo datos formulario: {e}")
        return {"ninos": [], "padre": None, "madre": None, "completo": False}
