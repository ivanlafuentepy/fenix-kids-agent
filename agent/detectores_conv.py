# agent/detectores_conv.py — Detectores de conversación (funciones puras)
# Extraído de main.py — sin cambios de lógica
# Detectan patrones en texto/historial. No tocan estado global ni envían mensajes.

import re
import asyncio
import logging

from agent.validar_nombre import es_nombre_valido as _validar_nombre_positivo

logger = logging.getLogger("agentkit")


# ── Detección de activación / handoff / confirmación ────────────────────────

_CLAVES_AURORA = [
    "nixi", "hola nixi", "quiero hablar con nixi",
    "quiero reservar con nixi", "quiero agendar con nixi",
    "hablar con aurora", "reservar con aurora", "agendar con aurora",
]


def _detectar_registro(texto: str) -> bool:
    """El padre quiere registrarse. Solo si menciona 'aurora' explícitamente."""
    return "aurora" in texto.lower()


def _detectar_activacion_aurora(texto: str) -> bool:
    """El padre escribió directamente a Aurora."""
    t = texto.lower()
    return any(k in t for k in _CLAVES_AURORA)


def _detectar_handoff_ivan_aurora(respuesta: str) -> bool:
    """Ivan dijo 'En breve te contacta AURORA' — señal de transferencia."""
    t = respuesta.lower()
    return "en breve te contacta aurora" in t or "te contacta aurora" in t


# ── Diagnóstico diferido (delay 3 min después de recibir edad) ────────────────

_diagnostico_pendiente: dict[str, asyncio.Task] = {}
_DELAY_DIAGNOSTICO = 180  # 3 minutos


def _cancelar_diagnostico_pendiente(telefono: str):
    """Cancela el diagnóstico pendiente si existe."""
    task = _diagnostico_pendiente.pop(telefono, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"[DIAG] Diagnóstico pendiente cancelado para {telefono}")


def _detectar_respuesta_edad(texto: str, historial: list[dict]) -> bool:
    """Detecta si el padre está respondiendo a la pregunta de edad de Ivan."""
    if not historial:
        return False
    ultimo = historial[-1]
    if ultimo.get("role") != "assistant":
        return False
    contenido = ultimo.get("content", "").lower()
    if not re.search(r'cu[aá]ntos\s+a[ñn]os', contenido):
        return False
    # El padre respondió con número o "X años"
    t = texto.strip()
    if re.fullmatch(r'\d{1,2}', t) and 2 <= int(t) <= 15:
        return True
    if re.search(r'\b\d{1,2}\s*(?:años|añitos|a[ñn]os)', t, re.IGNORECASE):
        return True
    return False


def _diagnostico_ya_enviado(historial: list[dict]) -> bool:
    """Detecta si Ivan ya envió el diagnóstico/cierre emocional mirando el historial."""
    for msg in historial:
        if msg.get("role") == "assistant":
            t = msg.get("content", "").lower()
            # Ivan cierra con propuesta de probar/precios
            if "te parece" in t and "fenix" in t and ("prueb" in t or "parte de" in t):
                return True
            # Nueva PARTE 2: "aprovecho y te paso los precios?"
            if "te paso los precios" in t:
                return True
    return False


def _padre_muestra_interes(texto: str) -> bool:
    """Detecta si el padre muestra interés después del diagnóstico."""
    t = texto.lower().strip()
    # Limpiar puntuación final para que "si!", "dale!", "ok." matcheen
    t_limpio = re.sub(r'[!.,?¡¿]+$', '', t).strip()
    # Respuestas afirmativas exactas (palabra sola o con puntuación)
    afirmativos_exactos = {
        'si', 'sí', 'dale', 'ok', 'bueno', 'va', 'vamos',
        'genial', 'perfecto', 'claro', 'obvio', 'por supuesto',
        'yes', 'sip', 'sep', 'oka', 'okey', 'okay',
        'me encanta', 'listo',
    }
    if t_limpio in afirmativos_exactos:
        return True
    # Patrones que matchean en cualquier posición
    patrones = [
        r'\bs[ií]\b.*\bs[ií]\b',       # "si si", "sí sí"
        r'\bsi+\b',                      # "sii", "siii"
        r'\bdale\b', r'\bok\b', r'\bbueno\b', r'\bclaro\b', r'\bobvio\b',
        r'me interesa', r'quiero', r'quier[oa]', r'nos interesa',
        r'cuando', r'cuándo', r'cu[aá]ndo', r'horario', r'dias', r'días',
        r'a qu[eé] hora',
        r'agendar', r'reservar', r'inscrib', r'anotar',
        r'cómo es', r'como es', r'cómo hago', r'como hago',
        r'cuánto', r'cuanto', r'precio', r'costo', r'sale',
        r'probamos', r'prueba', r'puede probar', r'le gustar',
        r'que necesito', r'qué necesito',
        r'\bsi\b.*porfa', r'\bsi\b.*por favor',
    ]
    return any(re.search(p, t) for p in patrones)


def _padre_ya_pidio_precios(historial: list[dict]) -> bool:
    """Detecta si Ivan ya envió el afiche (padre pidió precios antes del diagnóstico)."""
    for msg in historial:
        if msg.get("role") == "assistant":
            t = msg.get("content", "").lower()
            if "te paso un afiche" in t:
                return True
    return False


# ── Detección de pedido de llamada ───────────────────────────────────────────

_PATRONES_LLAMADA = [
    r"\bte\s+pued[oe]s?\s+llamar",
    r"\bpued[oe]\s+llamart?e",
    r"\bpodr[ií]a\s+llamart?e",
    r"\bpodemos\s+(?:llamar|hablar|llamarnos)",
    r"\bpod[eé]s\s+(?:llamar|hablar)",
    r"\bllamart?e(?:\s|$|\?)",
    r"\bllamarnos",
    r"\bhablar\s+(?:con\s+)?(?:vos|usted|contigo|ud|ivan|iván|el profe)",
    r"\buna\s+llamada",
    r"\bpor\s+tel[eé]fono",
    r"\btel[eé]fono\s+(?:tuyo|del profe|de iv[aá]n|personal)",
    r"\btu\s+n[uú]mero",
    r"\bme\s+llam[aá]s\??",
    r"\bque\s+te\s+llame",
    r"\bquiero\s+(?:hablar\s+(?:con\s+(?:vos|usted|contigo|ud|ivan|iván|el profe)|por\s+tel|personalmente)|llamar(?:te|lo)?)",
    r"\bhablar\s+personalmente",
    r"\bllamada\s+telef[oó]nica",
    # Padre acepta oferta de llamada de Ivan
    r"\bpuedo\s+hablar\s+(?:con\s+(?:vos|usted|contigo|ud|ivan|iván|el profe)|por\s+tel)",
    r"\bprefiero\s+(?:llamar|que me llam)",
    r"\bllamame",
    r"\bllam[aá]me",
    r"\bla\s+segunda",
    r"\bla\s+2da",
    r"\bsi\s*,?\s*llamame",
    r"\bdale\s+llamame",
    r"\bsi\s*,?\s*(?:podemos|podes)\s+hablar",
]

_REGEX_NOMBRE_PRESENTACION = re.compile(
    r"\b(?:soy|me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    re.IGNORECASE,
)


def _detectar_pedido_llamada(texto: str) -> bool:
    """Detecta si el padre está pidiendo hablar por teléfono / llamada."""
    t = texto.lower()
    return any(re.search(p, t) for p in _PATRONES_LLAMADA)


def _extraer_nombre_del_historial(historial: list[dict], texto_nuevo: str = "") -> str | None:
    """Busca el nombre del padre en mensajes 'soy X', 'me llamo X', etc."""
    textos = [texto_nuevo] if texto_nuevo else []
    textos += [m.get("content", "") for m in reversed(historial) if m.get("role") == "user"]
    for t in textos:
        m = _REGEX_NOMBRE_PRESENTACION.search(t)
        if not m:
            continue
        cand = m.group(1).strip().title()
        if _validar_nombre_positivo(cand):
            return cand
    return None


_REGEX_NOMBRE_HIJO = re.compile(
    r"(?:mi\s+hij[oa]\s+(?:se\s+llama\s+)?|se\s+llama\s+|(?:hijo|hija|nene|nena|niño|niña)\s+)([a-záéíóúñA-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[a-záéíóúñA-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    re.IGNORECASE,
)


def _es_nombre_hijo_valido(nombre: str) -> bool:
    """Valida nombre del hijo usando validación positiva (morfología + lista)."""
    return _validar_nombre_positivo(nombre)


def _extraer_nombre_hijo_historial(historial: list[dict]) -> str:
    """Busca nombre del hijo en mensajes del padre y respuestas del agente."""
    # Buscar en mensajes del padre primero (regex explícito)
    for m in reversed(historial):
        if m.get("role") == "user":
            match = _REGEX_NOMBRE_HIJO.search(m.get("content", ""))
            if match:
                candidato = match.group(1).strip().title()
                if _es_nombre_hijo_valido(candidato):
                    return candidato

    # Buscar cuando Ivan preguntó "cómo se llama tu hijo" y el padre respondió
    for i, m in enumerate(historial):
        if m.get("role") == "assistant" and re.search(
            r"c[oó]mo\s+se\s+llama\s+tu\s+hij[oa]", m.get("content", ""), re.IGNORECASE
        ):
            # El siguiente mensaje del usuario es la respuesta
            for j in range(i + 1, len(historial)):
                if historial[j].get("role") == "user":
                    resp = historial[j]["content"].strip()
                    # Ignorar si es una pregunta o pedido (no es un nombre)
                    _resp_lower = resp.lower()
                    _skip_words = ["precio", "costo", "como funciona", "horario",
                                   "ubicación", "ubicacion", "donde", "cuanto",
                                   "cuánto", "?", "info", "información",
                                   "tiene tdah", "tiene tea", "hiperactividad",
                                   "entre semana", "el monto"]
                    if any(sw in _resp_lower for sw in _skip_words):
                        break
                    # Puede ser "Maria", "se llama Maria", "Ivan, Maria", etc.
                    # Si tiene coma, el nombre del hijo suele ser la segunda parte
                    if "," in resp:
                        partes = [p.strip() for p in resp.split(",")]
                        # Tomar la última parte que parece nombre
                        for p in reversed(partes):
                            candidato = p.split()[0]
                            if _es_nombre_hijo_valido(candidato):
                                return candidato.title()
                    # Si es un nombre solo o "se llama X"
                    m_nombre = re.search(r"(?:se\s+llama\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", resp, re.IGNORECASE)
                    if m_nombre:
                        candidato = m_nombre.group(1).strip()
                        if _es_nombre_hijo_valido(candidato):
                            return candidato.title()
                    break

    # Buscar cuando Ivan usó el nombre del hijo en su respuesta ("cuántos años tiene Maria")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            match_edad = re.search(
                r"cu[aá]ntos\s+a[ñn]os\s+tiene\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
                m.get("content", ""), re.IGNORECASE,
            )
            if match_edad:
                nombre = match_edad.group(1).strip().title()
                if _es_nombre_hijo_valido(nombre):
                    return nombre

    # Buscar en respuestas del agente (ej: "Reserva confirmada ✅ Mateo...")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            contenido = m.get("content", "")
            match_conf = re.search(r"reserva confirmada[!✅\s]*\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", contenido, re.IGNORECASE)
            if match_conf:
                candidato = match_conf.group(1).strip().title()
                if _es_nombre_hijo_valido(candidato):
                    return candidato
    return "no mencionó"


_REGEX_EDAD = re.compile(
    r"(?:tiene|de|son)\s+(\d{1,2})\s*(?:años|añitos|a[ñn]os)",
    re.IGNORECASE,
)


def _extraer_edad_historial(historial: list[dict]) -> str:
    """Busca la edad del hijo en los mensajes del padre y respuestas de Ivan."""
    # 1. Buscar en mensajes del padre ("tiene 7 años", "7 añitos")
    for m in reversed(historial):
        if m.get("role") == "user":
            match = _REGEX_EDAD.search(m.get("content", ""))
            if match:
                return f"{match.group(1)} años"

    # 2. Buscar cuando Ivan preguntó edad y padre respondió solo un número
    for i, m in enumerate(historial):
        if m.get("role") == "assistant" and re.search(r'cu[aá]ntos\s+a[ñn]os', m.get("content", ""), re.IGNORECASE):
            for j in range(i + 1, len(historial)):
                if historial[j].get("role") == "user":
                    num_match = re.fullmatch(r'\d{1,2}', historial[j]["content"].strip())
                    if num_match and 2 <= int(num_match.group()) <= 15:
                        return f"{num_match.group()} años"
                    break

    # 3. Buscar en respuestas de Ivan ("a los 7 años", "Maria a los 5 años")
    for m in reversed(historial):
        if m.get("role") == "assistant":
            match = re.search(r'a los\s+(\d{1,2})\s+a[ñn]os', m.get("content", ""), re.IGNORECASE)
            if match and 2 <= int(match.group(1)) <= 15:
                return f"{match.group(1)} años"

    return "no mencionó"


def _detectar_confirmacion_aurora(respuesta: str) -> list[dict]:
    """
    Detecta si Aurora confirmó una o más reservas.
    Retorna lista de {"fecha": ..., "hora": ...} (puede tener 0, 1 o más).
    """
    patrones = [
        r"reserva (?:confirmada|reagendada)[!✅\s]*.*?(?:el\s+)?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"tiene su lugar.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"quedaron reservados.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"listo[!✅\s🙌]*.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"qued[aá]s confirmad[oa].*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"agendam.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"est[aá] confirmado.*?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2}).*?(?:confirmad[oa]|reagendad[oa])",
        # Reagendamientos: "entrena el sábado X a las Y", "se pasa al sábado X a las Y"
        r"entrena (?:el\s+)?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"se pasa (?:al|para el)\s+s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"te (?:paso|cambio|muevo) (?:al|para el)\s+s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
        r"(?:queda|quedás) (?:para (?:el )?|el )?s[aá]bado\s+(.+?)\s+a las\s+(\d{1,2}[:h]\d{0,2})",
    ]
    # Patrones sin fecha (cambio de hora mismo día): capturan solo hora, fecha = "hoy"
    patrones_sin_fecha = [
        r"se pasa a las\s+(\d{1,2}[:h]\d{0,2})",
        r"te cambio a las\s+(\d{1,2}[:h]\d{0,2})",
        r"nos vemos a las\s+(\d{1,2}[:h]\d{0,2}).*?(?:hoy|mismo)",
        r"a las\s+(\d{1,2}[:h]\d{0,2}).*?hoy mismo",
        r"a las\s+(\d{1,2}[:h]\d{0,2})\s+en vez de",
        r"te (?:paso|muevo|cambio) a las\s+(\d{1,2}[:h]\d{0,2})",
    ]
    texto_lower = respuesta.lower()
    resultados = []
    fechas_vistas = set()
    for patron in patrones:
        for match in re.finditer(patron, texto_lower):
            fecha = match.group(1).strip()
            hora = match.group(2).strip()
            key = f"{fecha}|{hora}"
            if key not in fechas_vistas:
                fechas_vistas.add(key)
                resultados.append({"fecha": fecha, "hora": hora})
    # Cambio de hora sin fecha → usar "hoy" como fecha
    if not resultados:
        for patron in patrones_sin_fecha:
            match = re.search(patron, texto_lower)
            if match:
                hora = match.group(1).strip()
                resultados.append({"fecha": "hoy", "hora": hora})
                break
    return resultados
