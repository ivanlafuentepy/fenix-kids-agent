# agent/brain.py — Cerebro del agente: conexión con Claude API
# FENIX KIDS ACADEMY — dual agente: Profe Ivan + Nixie

"""
Genera respuestas usando la API de Anthropic Claude.
Soporta dos agentes distintos: ivan y aurora.
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

# Clients separados: Ivan (leads) y Aurora (familias)
_key_ivan = os.getenv("ANTHROPIC_API_KEY")
_key_aurora = os.getenv("ANTHROPIC_API_KEY_AURORA") or _key_ivan  # fallback a la misma si no hay
client_ivan = AsyncAnthropic(api_key=_key_ivan)
client_aurora = AsyncAnthropic(api_key=_key_aurora)


def _client_para(agent_actual: str) -> AsyncAnthropic:
    """Retorna el client de Anthropic según el agente."""
    return client_aurora if agent_actual == "aurora" else client_ivan


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
    Inyecta la fecha actual, los sábados restantes del MES CORRIENTE,
    y los sábados del mes siguiente (como backup por si al padre no le queda
    bien ninguno del mes actual).

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

    def sabados_de_mes(anio: int, mes: int, desde: date | None = None) -> list[date]:
        """Retorna todos los sábados del (anio, mes). Si desde está dado, solo los >= desde."""
        # Primer día del mes
        d = date(anio, mes, 1)
        # Avanzar hasta el primer sábado
        dias_hasta_sabado = (5 - d.weekday()) % 7
        primer_sabado = d + td(days=dias_hasta_sabado)
        # Generar todos los sábados del mes
        sabados = []
        s = primer_sabado
        while s.month == mes:
            if desde is None or s > desde:  # estrictamente posterior a hoy (no incluir si ya es hoy)
                sabados.append(s)
            s += td(days=7)
        return sabados

    def fmt(d: date) -> str:
        return f"sábado {d.day} de {meses_es[d.month - 1]}"

    # Mes actual (solo sábados futuros, excluyendo hoy si es sábado)
    sabados_actual = sabados_de_mes(hoy.year, hoy.month, desde=hoy)

    # Mes siguiente (todos)
    if hoy.month == 12:
        mes_sig, anio_sig = 1, hoy.year + 1
    else:
        mes_sig, anio_sig = hoy.month + 1, hoy.year
    sabados_siguiente = sabados_de_mes(anio_sig, mes_sig)

    hoy_str = f"{dias_es[hoy.weekday()]} {hoy.day} de {meses_es[hoy.month - 1]} de {hoy.year}"
    nombre_mes_actual = meses_es[hoy.month - 1]
    nombre_mes_sig = meses_es[mes_sig - 1]

    if sabados_actual:
        sabados_actual_str = "\n".join(f"  - {fmt(s)}" for s in sabados_actual)
        bloque_actual = (
            f"Sábados DISPONIBLES del MES CORRIENTE ({nombre_mes_actual}):\n{sabados_actual_str}"
        )
    else:
        bloque_actual = f"No quedan sábados en {nombre_mes_actual}. Ofrecé directo los de {nombre_mes_sig}."

    sabados_siguiente_str = "\n".join(f"  - {fmt(s)}" for s in sabados_siguiente)

    return (
        f"Hoy es {hoy_str} (hora Asunción, Paraguay).\n"
        f"{bloque_actual}\n"
        f"Sábados del mes siguiente ({nombre_mes_sig}) — USAR SOLO SI el padre dice que no le queda bien ninguno del mes corriente:\n{sabados_siguiente_str}\n"
        f"Horarios de cada sábado: 9:30h | 11:00h | 15:30h\n"
        f"REGLA CRÍTICA: Ofrecé PRIMERO solo los sábados del mes corriente. "
        f"Recién si el padre dice que no le queda bien ninguno, ofrecé los del mes siguiente. "
        f"NO tires todos los meses juntos."
    )


def cargar_prompt_agente(agent_actual: str) -> str:
    """Carga el system prompt del agente indicado e inyecta contexto de fechas."""
    config = cargar_config_prompts()
    clave = "aurora_prompt" if agent_actual == "aurora" else "ivan_prompt"
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
        agent_actual: "ivan" o "aurora" — determina qué prompt se usa
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
            _client = _client_para(agent_actual)
            response = await _client.messages.create(
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
                # Alerta a Telegram si fallan todos los reintentos
                asyncio.create_task(_alertar_fallo_api(str(e)))
                return obtener_mensaje_error()


async def _alertar_fallo_api(error: str):
    """Envía alerta a Telegram cuando Claude API falla tras todos los reintentos."""
    try:
        from agent.telegram_bridge import notificar_llamada_urgente
        # Reutilizamos el canal de alertas urgentes de Telegram
        import httpx
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        group_id = os.getenv("TELEGRAM_AGENDA_GROUP_ID", "")
        if bot_token and group_id:
            async with httpx.AsyncClient() as http:
                await http.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": int(group_id),
                        "text": f"⚠️ ALERTA: Claude API falló tras 3 reintentos\n\nError: {error[:200]}",
                    },
                    timeout=10,
                )
    except Exception as e:
        logger.error(f"[ALERTA] Error enviando alerta de fallo API: {e}")


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
        f"{'PADRE' if m['role'] == 'user' else 'AURORA'}: {m['content']}"
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
        response = await client_ivan.messages.create(
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


async def resumir_conversacion_para_alerta(historial: list[dict]) -> str:
    """
    Genera un resumen corto de la conversación para la alerta de llamada al admin.
    Usa Haiku para extraer: nombre padre, nombre/edad hijo, números elegidos, estado.
    """
    if not historial:
        return "Sin historial previo."

    historial_texto = "\n".join(
        f"{'PADRE' if m['role'] == 'user' else 'AGENTE'}: {m['content']}"
        for m in historial[-20:]
    )

    prompt = """Resumí esta conversación de WhatsApp entre un padre y el agente de FENIX KIDS ACADEMY.
Formato EXACTO (sin markdown, sin asteriscos, sin comillas):

Padre: [nombre si lo dijo, sino "no se presentó"]
Hijo/a: [nombre y edad si los dijo, sino "no mencionó"]

Conversacion:
[Copiá y pegá TEXTUAL la respuesta más larga que el agente le dio al padre sobre los números/temas que eligió. Si no hay respuesta de análisis, poné "todavía no se analizaron los temas".]

Conversación:
""" + historial_texto

    try:
        response = await client_ivan.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Error resumiendo conversación: {e}")
        return "No se pudo generar resumen."
