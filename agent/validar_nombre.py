# agent/validar_nombre.py — Validación de nombres con filtro morfológico + lista positiva
# Generado para FENIX KIDS AGENT

"""
Valida nombres extraídos del chat para evitar guardar basura como
"Gracias Graciss", "De Dianosticaron", "Es Muy" en Airtable.

Enfoque: validación POSITIVA (aceptar lo que parece nombre real)
en vez de blacklist (rechazar palabras malas).
"""

import os
import re
import unicodedata
import logging

logger = logging.getLogger("agentkit")

# ── Filtro morfológico: sufijos que NUNCA son parte de un nombre ──────────
_SUFIJOS_NO_NOMBRE = (
    "aron", "aban", "ando", "iendo", "ado", "ido",
    "mente", "ción", "cion", "sion", "sión",
    "dad", "ente", "ante", "aría", "aria",
    "eron", "ieron", "amos", "emos", "imos",
    "aban", "ían", "ian", "ando", "endo",
    "arse", "erse", "irse", "ando", "endo",
    "iss", "oss",
)

# ── Palabras que NUNCA son nombres (cortas, comunes) ──────────────────────
_STOP_WORDS = {
    "el", "la", "un", "una", "mi", "tu", "su", "yo", "me", "te", "se",
    "le", "lo", "es", "de", "en", "no", "si", "ya", "ok", "al", "del",
    "que", "con", "por", "para", "los", "las", "muy", "mas", "pero",
    "hay", "fue", "son", "era", "ser", "ver", "dar", "van", "voy",
    "hola", "dale", "bien", "todo", "nada", "algo", "esto", "eso",
    "gracias", "genial", "perfecto", "super", "buenas", "entiendo",
    "okey", "okay", "listo", "claro", "soy",
    "tiene", "entre", "bueno", "como", "donde", "cuando", "porque",
    "quien", "cual", "cuanto", "sobre", "hasta", "desde", "mejor",
    "peor", "mucho", "poco", "otro", "otra", "cada", "mismo",
    "precio", "costo", "clase", "prueba", "horario", "fenix",
}


def _normalizar(texto: str) -> str:
    """Quita tildes y pasa a minúsculas para comparación."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# ── Cargar lista de nombres una sola vez ──────────────────────────────────
_NOMBRES_SET: set[str] = set()
_NOMBRES_LOADED = False


def _cargar_nombres():
    global _NOMBRES_SET, _NOMBRES_LOADED
    if _NOMBRES_LOADED:
        return
    ruta = os.path.join(os.path.dirname(__file__), "nombres_hispanos.txt")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            _NOMBRES_SET = {line.strip().lower() for line in f if line.strip()}
        logger.info(f"[NOMBRES] Cargados {len(_NOMBRES_SET)} nombres hispanos")
    except FileNotFoundError:
        logger.warning(f"[NOMBRES] {ruta} no encontrado — validación solo morfológica")
        _NOMBRES_SET = set()
    _NOMBRES_LOADED = True


def _pasa_filtro_morfologico(palabra: str) -> bool:
    """Retorna False si la palabra termina en un sufijo verbal/adverbial."""
    p = palabra.lower()
    for sufijo in _SUFIJOS_NO_NOMBRE:
        if len(p) > len(sufijo) + 2 and p.endswith(sufijo):
            return False
    return True


def _pasa_filtro_basico(nombre: str) -> tuple[bool, str]:
    """Validaciones básicas. Retorna (ok, razon_rechazo)."""
    if not nombre:
        return False, "vacio"
    # Solo letras (con tildes/ñ)
    if not re.match(r"^[a-záéíóúñA-ZÁÉÍÓÚÑ\s]+$", nombre):
        return False, "caracteres_invalidos"
    nombre_strip = nombre.strip()
    if len(nombre_strip) < 3:
        return False, "muy_corto"
    if len(nombre_strip) > 30:
        return False, "muy_largo"
    # Primera letra mayúscula (el candidato ya viene en Title normalmente)
    if nombre_strip[0].islower():
        return False, "no_empieza_mayuscula"
    # Sin dígitos
    if any(c.isdigit() for c in nombre_strip):
        return False, "tiene_digitos"
    # Más de 3 palabras = frase, no nombre
    if len(nombre_strip.split()) > 3:
        return False, "demasiadas_palabras"
    return True, ""


def validar_nombre(candidato: str) -> dict:
    """
    Valida un candidato a nombre.

    Retorna:
        {
            "valido": bool,
            "confianza": "alta" | "baja" | "nula",
            "razon": str  # motivo de rechazo o aceptación
        }
    """
    _cargar_nombres()

    # Filtro básico
    ok, razon = _pasa_filtro_basico(candidato)
    if not ok:
        logger.info(f"[NOMBRES] Rechazado '{candidato}': {razon}")
        return {"valido": False, "confianza": "nula", "razon": razon}

    # Verificar cada palabra del nombre
    palabras = candidato.strip().split()
    for palabra in palabras:
        p_lower = palabra.lower()

        # Stop words
        if p_lower in _STOP_WORDS:
            logger.info(f"[NOMBRES] Rechazado '{candidato}': stop_word '{palabra}'")
            return {"valido": False, "confianza": "nula", "razon": f"stop_word:{palabra}"}

        # Filtro morfológico
        if not _pasa_filtro_morfologico(palabra):
            logger.info(f"[NOMBRES] Rechazado '{candidato}': morfologia '{palabra}'")
            return {"valido": False, "confianza": "nula", "razon": f"morfologia:{palabra}"}

    # Verificar primera palabra contra lista de nombres
    primer_nombre = _normalizar(palabras[0])
    if primer_nombre in _NOMBRES_SET:
        return {"valido": True, "confianza": "alta", "razon": "en_lista"}

    # No está en la lista pero pasa todos los filtros → confianza baja
    logger.info(f"[NOMBRES] Confianza baja: '{candidato}' (no en lista, pasa morfología)")
    return {"valido": True, "confianza": "baja", "razon": "no_en_lista"}


def es_nombre_valido(candidato: str) -> bool:
    """Versión simple: True si confianza alta o baja, False si nula."""
    resultado = validar_nombre(candidato)
    return resultado["valido"]
