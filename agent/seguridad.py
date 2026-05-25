# agent/seguridad.py — Detección de amenazas, spam y diagnóstico
# Extraído de main.py — sin cambios de lógica

import re


# ── Protección contra prompt injection ─────────────────────────────────────
# Solo frases inequívocas de jailbreak. Se evitan palabras comunes que causan
# falsos positivos en lenguaje cotidiano (ej: "dan" matchea "¿dan clases?").
_PALABRAS_PELIGROSAS = [
    "ignora tus instrucciones", "ignore your instructions",
    "olvida todo", "forget everything", "forget your instructions",
    "nuevo rol", "new role", "actua como", "pretend you are",
    "system prompt", "jailbreak",
]


def _es_mensaje_sospechoso(texto: str) -> bool:
    t = texto.lower()
    return any(p in t for p in _PALABRAS_PELIGROSAS)


# ── Detección de spam / scam / cuenta hackeada ──────────────────────────────
# Links sospechosos, cadenas de estafa, mensajes masivos reenviados.
# Cuando se detecta: NO responder, silenciar conversación, alertar admin.
_PATRONES_SPAM = [
    re.compile(r'https?://[^\s]*\.buzz(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.xyz(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.top(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.click(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.link(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.win(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'https?://[^\s]*\.loan(?:[/\s]|$)', re.IGNORECASE),
    re.compile(r'me dieron los?\s*[\₲$]\s*[\d.,]+.*pru[eé]balo', re.IGNORECASE),
    re.compile(r'gan[eéa]\s+[\₲$]?\s*[\d.,]+.*(?:link|haz\s*clic|prueba)', re.IGNORECASE),
    re.compile(r'(?:regalo|gané|ganaste|sorteo|premio).*https?://', re.IGNORECASE),
]


def _es_spam_o_scam(texto: str) -> bool:
    """Detecta mensajes de spam, scam o cuenta hackeada."""
    return any(p.search(texto) for p in _PATRONES_SPAM)


# ── Detección de diagnóstico / neurodivergencia ──────────────────────────────
_KEYWORDS_DIAGNOSTICO = [
    r'\btdah\b', r'\btea\b', r'\bautism', r'\bespectro\b', r'\basperger\b',
    r'\bd[eé]ficit\b', r'\bs[ií]ndrome\b', r'\bneurodiv', r'\bdiagn[oó]stic',
    r'\bpsic[oó]log', r'\bpsicopedag', r'\bfonoaudi[oó]log',
    r'\btera(pist|peuta|pia)\b', r'\bmedicad', r'\bmedicaci[oó]n\b',
    r'\bconcerta\b', r'\britalina\b', r'\batomoxetina\b',
]


def detectar_diagnostico(texto: str) -> bool:
    """Retorna True si el texto menciona diagnósticos o tratamientos neurodivergentes."""
    return any(re.search(p, texto.lower()) for p in _KEYWORDS_DIAGNOSTICO)
