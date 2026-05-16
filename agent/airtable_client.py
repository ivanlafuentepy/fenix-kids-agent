# agent/airtable_client.py — Integración con Airtable
# FENIX KIDS ACADEMY — tablas: LEADS, FAMILIAS, NIÑOS, HORARIOS, RESERVAS

"""
Gestiona las tablas de Airtable para FENIX KIDS ACADEMY.

Flujo LEAD_NUEVO:
  1. Primer mensaje → crear registro en LEADS (TELEFONO + CONVERSION=CONSULTA + AGENT_ACTUAL=IVAN)
  2. Ivan cierra → AGENT_ACTUAL=AURORA, MODO_AURORA=lead_nuevo
  3. Aurora recolecta datos → crear FAMILIA + NIÑOS
  4. Aurora confirma horario → CONVERSION=AGENDA + crear RESERVA
  5. Crear evento Google Calendar

Flujo CLIENTE_INSCRIPTO:
  1. Padre escribe directo → AURORA busca en FAMILIAS por nombre
  2. Recupera NIÑOS vinculados
  3. Padre elige horario → crear RESERVA
  4. Crear evento Google Calendar

Variables de entorno:
  AIRTABLE_API_KEY   → Personal Access Token
  AIRTABLE_BASE_ID   → apph96UwbdbHoEdYr
"""

import os
import logging
import unicodedata
from difflib import SequenceMatcher
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appWwCQxALdMMV4MA")

_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"

# Nombres de tablas (en base Salsa Soul)
_LEADS     = "LEADS FENIX"
_FAMILIAS  = "FAMILIAS FENIX"
_NINOS     = "NIÑOS FENIX"
_HORARIOS  = "HORARIOS FENIX"
_RESERVAS  = "RESERVAS FENIX"
_PRUEBAS   = "PRUEBA FENIX"
_CONTENIDO = "CONTENIDO FENIX"
_ANUNCIOS  = "ANUNCIOS FENIX"
_REDES     = "REDES FENIX"


# ── Deducción de género por nombre ────────────────────────────────────────────

# Nombres que terminan en 'a' suelen ser femeninos, pero hay excepciones
_NOMBRES_MASCULINOS_EN_A = {
    "josua", "joshua", "luca", "nikita", "elia", "garcia", "borja", "sasha",
}
# Nombres que terminan en 'o/e/consonante' pero son femeninos
_NOMBRES_FEMENINOS_EXCEPCION = {
    "rocio", "carmen", "pilar", "ines", "dolores", "mercedes", "marisol",
    "rosario", "soledad", "flor", "mar", "iris", "luz", "paz", "noor",
    "miriam", "judith", "raquel", "esther", "ester", "nairim", "karen",
}


def deducir_genero(nombre: str) -> str | None:
    """
    Deduce HOMBRE/MUJER a partir del primer nombre.
    Retorna None si no puede determinar con confianza.
    """
    if not nombre:
        return None
    # Tomar solo el primer nombre, normalizar
    primer = nombre.strip().split()[0].lower()
    primer = unicodedata.normalize("NFD", primer)
    primer = "".join(c for c in primer if unicodedata.category(c) != "Mn")  # quitar tildes

    if primer in _NOMBRES_MASCULINOS_EN_A:
        return "HOMBRE"
    if primer in _NOMBRES_FEMENINOS_EXCEPCION:
        return "MUJER"

    # Heurística por terminación
    if primer.endswith("a"):
        return "MUJER"
    if primer.endswith(("o", "os")):
        return "HOMBRE"
    # Terminaciones comunes masculinas
    if primer.endswith(("el", "an", "on", "io", "iel", "uel")):
        return "HOMBRE"
    # Terminaciones comunes femeninas
    if primer.endswith(("is", "es", "iz")):
        return "MUJER"

    return None


# ── Helpers de bajo nivel ──────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }


async def _post(table: str, campos: dict) -> dict | None:
    """Crea un registro nuevo. Retorna el registro creado o None."""
    if not AIRTABLE_API_KEY:
        logger.warning("AIRTABLE_API_KEY no configurado")
        return None
    url = f"{_BASE_URL}/{table}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json={"fields": campos}, headers=_headers(), timeout=10)
            if r.status_code in (200, 201):
                return r.json()
            logger.error(f"POST {table} → {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"POST {table} error: {e}")
    return None


async def _patch(table: str, record_id: str, campos: dict) -> bool:
    """Actualiza campos de un registro existente. Retorna True si fue exitoso."""
    if not AIRTABLE_API_KEY or not record_id:
        return False
    url = f"{_BASE_URL}/{table}/{record_id}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.patch(url, json={"fields": campos}, headers=_headers(), timeout=10)
            if r.status_code == 200:
                return True
            logger.error(f"PATCH {table}/{record_id} → {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"PATCH {table}/{record_id} error: {e}")
    return False


async def _get_records(table: str, formula: str = "", max_records: int = 10) -> list[dict]:
    """Busca registros con un filtro formula. Retorna lista de records."""
    if not AIRTABLE_API_KEY:
        return []
    url = f"{_BASE_URL}/{table}"
    params = {"maxRecords": max_records}
    if formula:
        params["filterByFormula"] = formula
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, params=params, headers=_headers(), timeout=10)
            if r.status_code == 200:
                return r.json().get("records", [])
            logger.error(f"GET {table} → {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"GET {table} error: {e}")
    return []


async def _delete(table: str, record_id: str) -> bool:
    """Elimina un registro. Retorna True si fue exitoso."""
    if not AIRTABLE_API_KEY or not record_id:
        return False
    url = f"{_BASE_URL}/{table}/{record_id}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.delete(url, headers=_headers(), timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"DELETE {table}/{record_id} error: {e}")
    return False


# ── LEADS ─────────────────────────────────────────────────────────────────────

async def buscar_anuncio_por_ad_id(meta_ad_id: str) -> str | None:
    """Busca el record ID de un anuncio en ANUNCIOS FENIX por su Meta Ad ID."""
    records = await _get_records(_ANUNCIOS, formula=f"{{META AD ID}}='{meta_ad_id}'", max_records=1)
    if records:
        return records[0]["id"]
    return None


async def crear_lead(telefono: str, rompehielos: str = "A") -> str | None:
    """
    Crea un registro nuevo en LEADS.
    Retorna el record_id del registro creado, o None si falla.
    """
    # Verificar si ya existe
    records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    if records:
        return records[0]["id"]

    from datetime import datetime, timezone, timedelta
    _PY_TZ = timezone(timedelta(hours=-3))

    campos = {
        "TELEFONO": telefono,
        "ROMPEHIELOS": rompehielos,
        "CONVERSION": "CONSULTA",
        "AGENT_ACTUAL": "IVAN",
        "FECHA CREACION": datetime.now(_PY_TZ).isoformat(),
    }

    # Vincular anuncio si hay ad_source_id en la DB
    try:
        from agent.memory import obtener_ad_source_id
        ad_id = await obtener_ad_source_id(telefono)
        if ad_id:
            anuncio_record = await buscar_anuncio_por_ad_id(ad_id)
            if anuncio_record:
                campos["ANUNCIO"] = [anuncio_record]
                logger.info(f"[AD] Lead {telefono} vinculado a anuncio {ad_id}")
    except Exception as e:
        logger.warning(f"[AD] Error vinculando anuncio para {telefono}: {e}")

    resultado = await _post(_LEADS, campos)
    if resultado:
        record_id = resultado["id"]
        logger.info(f"Lead creado en Airtable: {telefono} → {record_id}")
        return record_id
    return None


# Mapeo número rompehielos → record ID en DIAGNOSTICO FENIX
_DIAGNOSTICO_MAP = {
    1: "recbslONudH8ue7GJ", 2: "rec2rZhYc66lruB24", 3: "recujDup74w7jfHHa",
    4: "reccI23SAUX3RLgBq", 5: "recpuZN4JHJw9ay7U", 6: "recCkqI2EMwB5iEkj",
    7: "recEENwOs4WdkaOnH", 8: "recO9DRxqktfPqczU", 9: "rec22T28IFfVNoFNw",
    10: "rec8BZJFathVxaads", 11: "recJuhT5tHqOlFVvI", 12: "recaV3I8LoKq9KJKE",
    13: "recQ7sD9xYtMfLnJv", 14: "recJzk1SfWuZominQ", 15: "reclb2atSeA3kMq6n",
}


async def actualizar_diagnostico_lead(telefono: str, numeros: list[int]) -> bool:
    """Linkea los números del rompehielos al lead en DIAGNOSTICO FENIX. Acumula, no sobreescribe."""
    records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    if not records:
        return False
    nuevos_ids = [_DIAGNOSTICO_MAP[n] for n in numeros if n in _DIAGNOSTICO_MAP]
    if not nuevos_ids:
        return False
    # Leer los existentes y acumular
    existentes = records[0].get("fields", {}).get("DIAGNOSTICO", [])
    todos = list(set(existentes + nuevos_ids))
    return await _patch(_LEADS, records[0]["id"], {"DIAGNOSTICO": todos})


async def actualizar_reserva_lead(telefono: str, fecha_reserva: str, hora_reserva: str) -> bool:
    """Actualiza FECHA RESERVA y HORA RESERVA en LEADS FENIX."""
    records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    if not records:
        return False
    return await _patch(_LEADS, records[0]["id"], {
        "FECHA RESERVA": fecha_reserva,
        "HORA RESERVA": hora_reserva,
    })


async def actualizar_datos_lead(telefono: str, nombre_responsable: str = "", nombre_nino: str = "", edad: str = "") -> bool:
    """Actualiza NOMBRE RESPONSABLE, NOMBRE NIÑO y EDAD en LEADS FENIX."""
    records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    if not records:
        return False
    campos = {}
    if nombre_responsable:
        campos["NOMBRE RESPONSABLE"] = nombre_responsable
    if nombre_nino:
        campos["NOMBRE NIÑO"] = nombre_nino
    if edad:
        campos["EDAD"] = edad
    if not campos:
        return False
    return await _patch(_LEADS, records[0]["id"], campos)


async def obtener_lead_record_id(telefono: str) -> str | None:
    """Retorna el record_id del LEAD para este teléfono, o None."""
    records = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    return records[0]["id"] if records else None


async def actualizar_conversion_lead(telefono: str, estado: str) -> bool:
    """
    Actualiza el campo CONVERSION del LEAD.
    Estado puede ser: CONSULTA, CONTACTADO, PAGO, GRATIS, INSCRIPTO, DESCARTADO
    """
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return False
    return await _patch(_LEADS, record_id, {"CONVERSION": estado})


async def actualizar_agent_lead(telefono: str, agent: str, modo_nixie: str | None = None) -> bool:
    """Actualiza AGENT_ACTUAL en LEADS."""
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return False
    campos: dict = {"AGENT_ACTUAL": agent.upper()}
    return await _patch(_LEADS, record_id, campos)


async def marcar_formulario_lead(telefono: str) -> bool:
    """Marca FORMULARIO=True en LEADS."""
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return False
    return await _patch(_LEADS, record_id, {"FORMULARIO": True})


async def vincular_familia_a_lead(telefono: str, familia_record_id: str) -> bool:
    """Vincula el LEAD con el registro de FAMILIA creado."""
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return False
    return await _patch(_LEADS, record_id, {"FAMILIA": [familia_record_id]})


async def eliminar_lead(telefono: str) -> bool:
    """Elimina el registro de LEADS para este teléfono."""
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return True
    return await _delete(_LEADS, record_id)


async def eliminar_todo_de_telefono(telefono: str) -> dict:
    """
    Reset completo en Airtable para un teléfono:
      1. Busca FAMILIA por teléfono
      2. Borra todas las RESERVAS de cada NIÑO de esa familia
      3. Borra los NIÑOS
      4. Borra la FAMILIA
      5. Borra el LEAD

    Retorna dict con contadores: {"familia", "ninos", "reservas", "lead"}.
    """
    contador = {"familia": 0, "ninos": 0, "reservas": 0, "lead": 0}

    familia = await buscar_familia_por_telefono(telefono)
    if familia:
        familia_id = familia["id"]
        # Borrar niños y sus reservas
        ninos = await obtener_ninos_de_familia(familia_id)
        for nino in ninos:
            nino_id = nino["id"]
            # Las reservas del niño
            formula = f"FIND('{nino_id}', ARRAYJOIN({{NINO}}))"
            reservas = await _get_records(_RESERVAS, formula=formula, max_records=20)
            for r in reservas:
                if await _delete(_RESERVAS, r["id"]):
                    contador["reservas"] += 1
            if await _delete(_NINOS, nino_id):
                contador["ninos"] += 1
        # Borrar familia
        if await _delete(_FAMILIAS, familia_id):
            contador["familia"] += 1

    # Borrar registros de PRUEBA FENIX
    pruebas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{telefono}'", max_records=10)
    contador["pruebas"] = 0
    for p in pruebas:
        if await _delete(_PRUEBAS, p["id"]):
            contador["pruebas"] += 1

    # Borrar lead
    lead_id = await obtener_lead_record_id(telefono)
    if lead_id and await _delete(_LEADS, lead_id):
        contador["lead"] += 1

    logger.info(f"[AIRTABLE] Reset total para {telefono}: {contador}")
    return contador


# ── FAMILIAS ──────────────────────────────────────────────────────────────────

def _sin_acentos(texto: str) -> str:
    """Elimina acentos y convierte a minúsculas para comparación."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto.lower())
        if unicodedata.category(c) != 'Mn'
    )


# Fórmula Airtable para normalizar acentos en NOMBRE COMPLETO del padre/madre
_NORM_PADRE = (
    'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE('
    'LOWER(CONCATENATE({NOMBRE PADRE}," ",{APELLIDO PADRE}," ",{NOMBRE MADRE}," ",{APELLIDO MADRE}))'
    ', "á", "a"), "é", "e"), "í", "i"), "ó", "o"), "ú", "u")'
)


async def buscar_familia_por_nombre(nombre: str, apellido: str = "") -> dict | None:
    """
    Búsqueda fuzzy de FAMILIA por nombre (y opcionalmente apellido).
    Ignora acentos, no requiere nombre completo exacto.
    Retorna el record con mejor match o None.
    """
    texto_busqueda = f"{nombre} {apellido}".strip()
    palabras = [_sin_acentos(p) for p in texto_busqueda.replace("-", " ").replace(".", " ").split() if len(p) > 1]
    if not palabras:
        return None

    # Búsqueda AND: todas las palabras deben matchear
    condiciones_and = [f'SEARCH("{p}", {_NORM_PADRE})>0' for p in palabras]
    formula_and = f"AND({','.join(condiciones_and)})"
    records = await _get_records(_FAMILIAS, formula=formula_and, max_records=10)

    # Fallback OR: cualquier palabra matchea
    if not records:
        condiciones_or = [f'SEARCH("{p}", {_NORM_PADRE})>0' for p in palabras]
        formula_or = f"OR({','.join(condiciones_or)})"
        records = await _get_records(_FAMILIAS, formula=formula_or, max_records=10)

    if not records:
        return None
    if len(records) == 1:
        return records[0]

    # Scoring: elegir el mejor candidato
    def _nombre_completo_familia(rec: dict) -> str:
        f = rec.get("fields", {})
        return _sin_acentos(
            f"{f.get('NOMBRE PADRE', '')} {f.get('APELLIDO PADRE', '')} "
            f"{f.get('NOMBRE MADRE', '')} {f.get('APELLIDO MADRE', '')}"
        )

    def _puntaje(rec: dict) -> tuple[int, float, float]:
        candidato = _nombre_completo_familia(rec)
        palabras_candidato = set(candidato.split())
        palabras_candidato_lista = list(palabras_candidato)
        palabras_set = set(palabras)
        exactas = sum(1 for p in palabras_set if p in palabras_candidato)
        fuzzy = sum(
            max(
                (SequenceMatcher(None, p, c).ratio() for c in palabras_candidato_lista),
                default=0.0,
            )
            for p in palabras
        )
        ratio = exactas / len(palabras_candidato) if palabras_candidato else 0.0
        return (exactas, round(fuzzy, 3), round(ratio, 3))

    records.sort(key=_puntaje, reverse=True)
    return records[0]


async def buscar_familia_por_telefono(telefono: str) -> dict | None:
    """Busca una FAMILIA por CELL PADRE, CELL MADRE o CELL LIMPIO."""
    # Buscar por número exacto y también por CELL LIMPIO (formato normalizado)
    formula = (
        f"OR("
        f"{{CELL PADRE}}='{telefono}', {{CELL MADRE}}='{telefono}', "
        f"{{CELL LIMPIO PADRE}}='{telefono}', {{CELL LIMPIO MADRE}}='{telefono}'"
        f")"
    )
    records = await _get_records(_FAMILIAS, formula=formula, max_records=1)
    return records[0] if records else None


async def marcar_control_datos(familia_id: str) -> bool:
    """Marca CONTROL DATOS = True en FAMILIAS FENIX."""
    return await _patch(_FAMILIAS, familia_id, {"CONTROL DATOS": True})


async def crear_familia(datos: dict) -> str | None:
    """
    Crea un registro en FAMILIAS con los datos de padre y madre.

    datos = {
        "padre": {"nombre", "apellido", "ci", "telefono", "email", "fecha_nacimiento"},
        "madre": {"nombre", "apellido", "ci", "telefono", "email", "fecha_nacimiento"},
    }

    Retorna el record_id de la FAMILIA creada.
    """
    campos: dict = {}

    padre = datos.get("padre") or {}
    if padre.get("nombre"):
        campos["NOMBRE PADRE"] = padre["nombre"]
    if padre.get("apellido"):
        campos["APELLIDO PADRE"] = padre["apellido"]
    if padre.get("ci"):
        campos["CI PADRE"] = str(padre["ci"]).strip()
    if padre.get("email"):
        campos["EMAIL PADRE"] = padre["email"]
    if padre.get("telefono"):
        campos["CELL PADRE"] = str(padre["telefono"]).strip()
    if padre.get("fecha_nacimiento"):
        campos["FECHA NACIMIENTO PADRE"] = padre["fecha_nacimiento"]

    madre = datos.get("madre") or {}
    if madre.get("nombre"):
        campos["NOMBRE MADRE"] = madre["nombre"]
    if madre.get("apellido"):
        campos["APELLIDO MADRE"] = madre["apellido"]
    if madre.get("ci"):
        campos["CI MADRE"] = str(madre["ci"]).strip()
    if madre.get("email"):
        campos["EMAIL MADRE"] = madre["email"]
    if madre.get("telefono"):
        campos["CELL MADRE"] = str(madre["telefono"]).strip()
    if madre.get("fecha_nacimiento"):
        campos["FECHA NACIMIENTO MADRE"] = madre["fecha_nacimiento"]

    if not campos:
        logger.warning("crear_familia: no hay datos suficientes")
        return None

    resultado = await _post(_FAMILIAS, campos)
    if resultado:
        logger.info(f"Familia creada: {resultado['id']}")
        return resultado["id"]
    return None


# ── NIÑOS ─────────────────────────────────────────────────────────────────────

async def crear_nino(datos_nino: dict, familia_id: str) -> str | None:
    """
    Crea un registro en NIÑOS vinculado a una FAMILIA.

    datos_nino = {nombre, apellido, ci, fecha_nacimiento, sexo, talla_remera}
    Retorna el record_id del NIÑO creado.
    """
    campos: dict = {}

    if datos_nino.get("nombre"):
        campos["NOMBRE"] = datos_nino["nombre"]
    if datos_nino.get("apellido"):
        campos["APELLIDO"] = datos_nino["apellido"]
    if datos_nino.get("ci"):
        campos["CI"] = str(datos_nino["ci"]).strip()
    if datos_nino.get("fecha_nacimiento"):
        # Convertir dd/mm/yyyy o d/m/yyyy a yyyy-mm-dd (Airtable espera ISO)
        _fn = datos_nino["fecha_nacimiento"].strip()
        try:
            from datetime import datetime as _dt
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"):
                try:
                    _parsed = _dt.strptime(_fn, fmt)
                    _fn = _parsed.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
        except Exception:
            pass
        campos["FECHA NACIMIENTO"] = _fn
    if datos_nino.get("sexo"):
        sexo = datos_nino["sexo"].upper()
        if sexo in ("H", "HOMBRE", "MASCULINO", "M", "BOY"):
            campos["SEXO"] = "HOMBRE"
        elif sexo in ("F", "MUJER", "FEMENINO", "GIRL"):
            campos["SEXO"] = "MUJER"
    elif datos_nino.get("nombre"):
        # Deducir género del nombre si no vino explícito
        genero = deducir_genero(datos_nino["nombre"])
        if genero:
            campos["SEXO"] = genero
    if datos_nino.get("talla_remera"):
        campos["TALLA REMERA"] = str(datos_nino["talla_remera"]).strip()

    campos["FAMILIA"] = [familia_id]

    resultado = await _post(_NINOS, campos)
    if resultado:
        logger.info(f"Niño creado: {resultado['id']} en familia {familia_id}")
        return resultado["id"]
    return None


async def actualizar_nino(nino_id: str, campos: dict) -> bool:
    """Actualiza campos de un NIÑO (ej: talla_remera, apodo)."""
    return await _patch(_NINOS, nino_id, campos)


async def obtener_ninos_de_familia(familia_id: str) -> list[dict]:
    """
    Retorna la lista de NIÑOS vinculados a una FAMILIA con todos sus datos.
    Lee los IDs de niños del registro de la familia y los fetchea uno por uno.
    """
    # Leer el registro de la familia para obtener los IDs de NIÑOS FENIX
    url = f"{_BASE_URL}/{_FAMILIAS}/{familia_id}"
    nino_ids = []
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, headers=_headers(), timeout=10)
            if r.status_code == 200:
                nino_ids = r.json().get("fields", {}).get("NIÑOS FENIX", [])
        except Exception as e:
            logger.error(f"Error obteniendo familia {familia_id}: {e}")

    if not nino_ids:
        return []

    # Fetchear cada niño por ID
    resultado = []
    async with httpx.AsyncClient() as client:
        for nino_id in nino_ids:
            try:
                url_nino = f"{_BASE_URL}/{_NINOS}/{nino_id}"
                r = await client.get(url_nino, headers=_headers(), timeout=10)
                if r.status_code == 200:
                    f = r.json().get("fields", {})
                    resultado.append({
                        "id": nino_id,
                        "nombre_completo": f.get("NOMBRE COMPLETO", ""),
                        "nombre": f.get("NOMBRE", ""),
                        "apellido": f.get("APELLIDO", ""),
                        "apodo": f.get("APODO", ""),
                        "ci": f.get("CI", ""),
                        "fecha_nacimiento": f.get("FECHA NACIMIENTO", ""),
                        "sexo": f.get("SEXO", ""),
                        "talla_remera": f.get("TALLA REMERA", ""),
                    })
            except Exception as e:
                logger.error(f"Error obteniendo niño {nino_id}: {e}")
    return resultado


# ── HORARIOS ──────────────────────────────────────────────────────────────────

async def obtener_horarios_disponibles(max_horarios: int = 8) -> list[dict]:
    """
    Retorna los próximos HORARIOS disponibles.
    Cada item: {"id", "horario", "fecha", "hora", "dia"}
    """
    from datetime import date
    hoy = date.today().isoformat()
    formula = f"IS_AFTER({{FECHA}}, '{hoy}')"
    records = await _get_records(_HORARIOS, formula=formula, max_records=max_horarios)
    resultado = []
    for r in records:
        f = r.get("fields", {})
        resultado.append({
            "id": r["id"],
            "horario": f.get("HORARIO", ""),
            "fecha": f.get("FECHA", ""),
            "hora": f.get("HORA", ""),
            "dia": f.get("DÍA", ""),
        })
    return resultado


async def obtener_o_crear_horario(fecha_iso: str, hora: str) -> str | None:
    """
    Busca un HORARIO por FECHA + HORA. Si no existe, lo crea.

    Args:
        fecha_iso: Fecha en formato YYYY-MM-DD (campo FECHA de Airtable)
        hora: Hora como "9:30" | "11:00" | "15:30" (campo select HORA)

    Retorna el record_id del HORARIO, o None si falla.
    """
    # Normalizar hora: el campo HORA en Airtable es select con valores "9:30", "11:00", "15:30"
    hora_norm = hora.strip().lower().replace("hs", "").replace("h", ":").rstrip(":")
    # Quitar ceros a la izquierda ("09:30" → "9:30") porque así está en Airtable
    if hora_norm.startswith("0"):
        hora_norm = hora_norm[1:]

    # Buscar HORARIO existente — FECHA es tipo Date, usar DATESTR para comparar
    formula = f"AND(DATESTR({{FECHA}})='{fecha_iso}', {{HORA}}='{hora_norm}')"
    records = await _get_records(_HORARIOS, formula=formula, max_records=1)
    if records:
        return records[0]["id"]

    # No existe — crearlo
    resultado = await _post(_HORARIOS, {
        "FECHA": fecha_iso,
        "HORA": hora_norm,
    })
    if resultado:
        logger.info(f"Horario creado: {fecha_iso} {hora_norm} → {resultado['id']}")
        return resultado["id"]
    logger.error(f"No se pudo crear HORARIO {fecha_iso} {hora_norm}")
    return None


async def obtener_horario_por_id(horario_id: str) -> dict | None:
    """Retorna los datos de un HORARIO por su record_id."""
    url = f"{_BASE_URL}/{_HORARIOS}/{horario_id}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, headers=_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                f = data.get("fields", {})
                return {
                    "id": data["id"],
                    "horario": f.get("HORARIO", ""),
                    "fecha": f.get("FECHA", ""),
                    "hora": f.get("HORA", ""),
                    "dia": f.get("DÍA", ""),
                }
        except Exception as e:
            logger.error(f"GET HORARIO {horario_id}: {e}")
    return None


async def obtener_ninos_por_horario(fecha_iso: str, hora: str) -> list[dict]:
    """
    Retorna la lista de niños reservados para un horario específico (fecha + hora).
    Cada item: {"nombre": "...", "apellido": "...", "edad": "...", "apodo": "..."}
    Ordenados alfabéticamente por apellido + nombre.
    """
    from datetime import date

    # Normalizar hora
    hora_norm = hora.strip().lower().replace("hs", "").replace("h", ":").rstrip(":")
    if hora_norm.startswith("0"):
        hora_norm = hora_norm[1:]

    # Buscar el HORARIO — FECHA es tipo Date en Airtable, usar DATESTR para comparar
    formula = f"AND(DATESTR({{FECHA}})='{fecha_iso}', {{HORA}}='{hora_norm}')"
    horarios = await _get_records(_HORARIOS, formula=formula, max_records=1)
    if not horarios:
        return []

    horario_id = horarios[0]["id"]
    reserva_ids = horarios[0].get("fields", {}).get("RESERVAS FENIX", [])
    if not reserva_ids:
        return []

    # Obtener cada reserva y su niño
    ninos = []
    for res_id in reserva_ids:
        url = f"{_BASE_URL}/{_RESERVAS}/{res_id}"
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(url, headers=_headers(), timeout=10)
                if r.status_code != 200:
                    continue
                res_fields = r.json().get("fields", {})
                nino_ids = res_fields.get("NINO", [])
                for nino_id in nino_ids:
                    url_nino = f"{_BASE_URL}/{_NINOS}/{nino_id}"
                    rn = await client.get(url_nino, headers=_headers(), timeout=10)
                    if rn.status_code == 200:
                        nf = rn.json().get("fields", {})
                        # Edad: usar campo EDAD de Airtable (formato "años,meses") o calcular
                        edad = str(nf.get("EDAD", "")) if nf.get("EDAD") else ""
                        if not edad:
                            fecha_nac = nf.get("FECHA NACIMIENTO", "")
                            if fecha_nac:
                                try:
                                    nac = date.fromisoformat(fecha_nac)
                                    hoy = date.today()
                                    _anios = hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
                                    _meses = (hoy.month - nac.month - (hoy.day < nac.day)) % 12
                                    edad = f"{_anios},{_meses}"
                                except ValueError:
                                    pass
                        familia_ids = res_fields.get("FAMILIAS", []) or nf.get("FAMILIA", [])
                        ninos.append({
                            "id": nino_id,
                            "reserva_id": res_id,
                            "nombre": nf.get("NOMBRE", ""),
                            "apellido": nf.get("APELLIDO", ""),
                            "edad": edad,
                            "apodo": nf.get("APODO", ""),
                            "familia_id": familia_ids[0] if familia_ids else "",
                        })
            except Exception as e:
                logger.error(f"Error obteniendo reserva/niño: {e}")

    # Ordenar alfabéticamente por nombre + apellido
    ninos.sort(key=lambda n: f"{n['nombre']} {n['apellido']}".lower())
    return ninos


def formatear_lista_ninos(ninos: list[dict], fecha_label: str = "", hora: str = "") -> str:
    """Formatea la lista de niños para mostrar en WhatsApp — linda y dinámica."""
    if not ninos:
        return "Todavía no hay nadie agendado para ese horario 😊"

    header = f"🌳 *Fenix Kids"
    if fecha_label and hora:
        header += f" — {fecha_label} {hora}h"
    header += f"*\n"
    header += f"👧👦 *{len(ninos)} guerrero{'s' if len(ninos) > 1 else ''} agendado{'s' if len(ninos) > 1 else ''}:*\n\n"

    emojis = ["🦁", "🐯", "🦊", "🐻", "🐼", "🦋", "🌟", "⚡", "🔥", "🎯", "🦅", "🐺", "🌈", "🎪", "🏆"]
    lineas = []
    for i, n in enumerate(ninos):
        emoji = emojis[i % len(emojis)]
        primer_nombre = (n.get('apodo') or n['nombre']).split()[0]
        primer_apellido = n['apellido'].split()[0] if n['apellido'] else ""
        nombre = f"{primer_nombre} {primer_apellido}".strip()
        edad_str = f" — {n['edad']} años" if n['edad'] else ""
        lineas.append(f"{emoji} {nombre}{edad_str}")

    return header + "\n".join(lineas) + "\n\n💪 ¡Va a estar buenísimo!"


# ── RESERVAS ──────────────────────────────────────────────────────────────────

async def crear_reserva(nino_id: str, horario_id: str, familia_id: str = "") -> str | None:
    """
    Crea una RESERVA vinculando NINO + HORARIO + FAMILIAS.
    Siempre 1 reserva = 1 niño + 1 horario.
    Si ya existe una reserva para ese niño en ese horario, no crea duplicado.
    Retorna el record_id de la RESERVA (existente o nueva).
    """
    # Guard: verificar si ya existe reserva de este niño en este horario
    formula = f"AND(FIND('{nino_id}', ARRAYJOIN({{NINO}})), FIND('{horario_id}', ARRAYJOIN({{HORARIO}})))"
    existentes = await _get_records(_RESERVAS, formula=formula, max_records=1)
    if existentes:
        rid = existentes[0]["id"]
        logger.info(f"Reserva ya existe: {rid} nino={nino_id} horario={horario_id} — no se crea duplicado")
        return rid

    campos = {
        "NINO": [nino_id],
        "HORARIO": [horario_id],
    }
    if familia_id:
        campos["FAMILIAS"] = [familia_id]

    resultado = await _post(_RESERVAS, campos)
    if resultado:
        logger.info(f"Reserva creada: {resultado['id']} nino={nino_id} horario={horario_id}")
        return resultado["id"]
    return None


async def eliminar_reserva(reserva_id: str) -> bool:
    """Elimina una RESERVA."""
    return await _delete(_RESERVAS, reserva_id)


async def buscar_reservas_familia(familia_id: str) -> list[dict]:
    """Busca todas las RESERVAS de una familia. Retorna lista con id, nino, fecha, hora."""
    formula = f"FIND('{familia_id}', ARRAYJOIN({{FAMILIAS}}))"
    records = await _get_records(_RESERVAS, formula=formula, max_records=50)
    reservas = []
    for r in records:
        f = r.get("fields", {})
        reservas.append({
            "id": r["id"],
            "nombre_nino": f.get("NOMBRE COMPLETO", [""])[0] if isinstance(f.get("NOMBRE COMPLETO"), list) else f.get("NOMBRE COMPLETO", ""),
            "fecha": f.get("FECHA", [""])[0] if isinstance(f.get("FECHA"), list) else f.get("FECHA", ""),
            "hora": f.get("HORA", [""])[0] if isinstance(f.get("HORA"), list) else f.get("HORA", ""),
        })
    return reservas


async def cancelar_reservas_familia_fecha(familia_id: str, fecha: str, hora: str = "") -> int:
    """
    Cancela (borra) todas las reservas de una familia para una fecha y hora.
    Si hora está vacío, borra todas las de ese día.
    Retorna cantidad de reservas borradas.
    """
    reservas = await buscar_reservas_familia(familia_id)
    borradas = 0
    for res in reservas:
        if res["fecha"] == fecha:
            if not hora or res["hora"] == hora:
                if await eliminar_reserva(res["id"]):
                    borradas += 1
                    logger.info(f"Reserva cancelada: {res['id']} ({res['nombre_nino']} {res['fecha']} {res['hora']})")
    return borradas


# ── Flujo completo: crear familia + niños desde datos del formulario ──────────

async def crear_familia_completa(
    telefono: str,
    datos_formulario: dict,
) -> tuple[str | None, list[str]]:
    """
    Crea FAMILIA + NIÑOS a partir de los datos extraídos por Haiku.
    Vincula la FAMILIA al LEAD.

    Retorna (familia_id, [nino_ids])
    """
    from agent.ab_test import guardar_familia_id

    # Crear FAMILIA
    familia_id = await crear_familia({
        "padre": datos_formulario.get("padre"),
        "madre": datos_formulario.get("madre"),
    })

    if not familia_id:
        logger.error(f"No se pudo crear FAMILIA para {telefono}")
        return None, []

    # Guardar familia_id en estado local
    await guardar_familia_id(telefono, familia_id)

    # Vincular LEAD → FAMILIA
    await vincular_familia_a_lead(telefono, familia_id)

    # Crear NIÑOS
    nino_ids = []
    for nino_data in datos_formulario.get("ninos", []):
        nino_id = await crear_nino(nino_data, familia_id)
        if nino_id:
            nino_ids.append(nino_id)

    # Marcar formulario completo en LEADS
    await marcar_formulario_lead(telefono)

    logger.info(f"Familia completa creada para {telefono}: familia={familia_id}, niños={nino_ids}")
    return familia_id, nino_ids


# ── PRUEBA FENIX (leads que agendan/pagan clase de prueba) ────────────────────

def _deducir_genero(nombre: str) -> str:
    """Deduce HOMBRE o MUJER por el nombre. Default HOMBRE si no está claro."""
    if not nombre:
        return ""
    n = nombre.lower().strip().split()[0]
    # Nombres que terminan en 'a' suelen ser mujer (con excepciones)
    excepciones_masc = {"joshua", "luca", "santana", "isa", "josua", "nikita"}
    excepciones_fem = {"sol", "flor", "ines", "mercedes", "pilar", "mar", "luz", "paz", "noel"}
    if n in excepciones_fem:
        return "MUJER"
    if n in excepciones_masc:
        return "HOMBRE"
    if n.endswith("a") or n.endswith("i"):
        return "MUJER"
    return "HOMBRE"


async def crear_prueba_fenix(
    telefono: str,
    nombre_responsable: str,
    apellido_responsable: str,
    nombre_hijo: str,
    apellido_hijo: str,
    edad_hijo: str,
    fecha_reserva: str,
    hora: str,
    fecha_nacimiento: str = "",
    conversion: str = "PAGO",
    monto: int = 0,
    concepto: str = "PRUEBA 1HIJO",
    diagnostico_ids: list[str] | None = None,
    lead_record_id: str | None = None,
    metodo_pago: str = "TRANSFER",
) -> str | None:
    """Crea un registro en PRUEBA FENIX con todos los campos. Retorna record_id o None."""
    from datetime import datetime, timezone, timedelta
    _PY_TZ = timezone(timedelta(hours=-3))

    # Deducir género del nombre del hijo
    genero = _deducir_genero(nombre_hijo)

    # Normalizar fecha de nacimiento a ISO
    _fn_norm = fecha_nacimiento
    if _fn_norm:
        for _fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"):
            try:
                _fn_norm = datetime.strptime(_fn_norm.strip(), _fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    campos = {
        "TELEFONO": telefono,
        "NOMBRE": nombre_responsable,
        "APELLIDO": apellido_responsable,
        "NOMBRE HIJO": nombre_hijo,
        "APELLIDO HIJO": apellido_hijo,
        "FECHA RESERVA": fecha_reserva,
        "HORA": hora,
        "FECHA NACIMIENTO": _fn_norm,
        "CONVERSION": conversion,
        "CONCEPTO": concepto,
        "MONTO": monto,
        "METODO DE PAGO": [metodo_pago] if metodo_pago else [],
        "GENERO": genero,
        "ORIGEN LEAD": "ANUNCIO",
        "REGISTRAR": True,
        "FECHA CREACION": datetime.now(_PY_TZ).isoformat(),
    }
    if diagnostico_ids:
        campos["DIAGNOSTICO"] = diagnostico_ids
    if lead_record_id:
        campos["LEAD"] = [lead_record_id]
    # Limpiar campos vacíos (excepto links)
    campos = {k: v for k, v in campos.items() if v}
    record = await _post(_PRUEBAS, campos)
    if record:
        rid = record.get("id")
        logger.info(f"[PRUEBA FENIX] Creado: {nombre_hijo} {apellido_hijo} ({telefono}) → {rid}")
        return rid
    return None


# ── CONTENIDO FENIX (posteos de redes sociales vinculados a niños) ───────────

async def obtener_contenido_no_notificado() -> list[dict]:
    """
    Retorna registros de CONTENIDO FENIX con NOTIFICADO = false (o vacío).
    Cada item: {"id", "titulo", "red", "tipo", "link", "nino_ids"}
    """
    formula = "OR(NOT({NOTIFICADO}), {NOTIFICADO}=FALSE())"
    records = await _get_records(_CONTENIDO, formula=formula, max_records=20)
    resultado = []
    for r in records:
        f = r.get("fields", {})
        resultado.append({
            "id": r["id"],
            "titulo": f.get("TITULO", ""),
            "red": f.get("RED", ""),
            "tipo": f.get("TIPO", ""),
            "link": f.get("LINK", ""),
            "nino_ids": f.get("NIÑOS FENIX", []),
        })
    return resultado


async def marcar_contenido_notificado(record_id: str) -> bool:
    """Marca NOTIFICADO = True en CONTENIDO FENIX."""
    return await _patch(_CONTENIDO, record_id, {"NOTIFICADO": True})


async def obtener_ultimo_contenido_por_red(red: str) -> dict | None:
    """
    Retorna el contenido más reciente de una red social específica.
    Útil para el calendario diario (ej: lunes → último post de Instagram).
    """
    formula = f"AND({{RED}}='{red}', {{NOTIFICADO}}=FALSE())"
    records = await _get_records(_CONTENIDO, formula=formula, max_records=1)
    if not records:
        return None
    r = records[0]
    f = r.get("fields", {})
    return {
        "id": r["id"],
        "titulo": f.get("TITULO", ""),
        "red": f.get("RED", ""),
        "tipo": f.get("TIPO", ""),
        "link": f.get("LINK", ""),
        "nino_ids": f.get("NIÑOS FENIX", []),
    }


# ── REDES FENIX (perfiles de redes sociales) ─────────────────────────────────

async def obtener_redes() -> list[dict]:
    """
    Retorna todos los perfiles de redes sociales de FENIX.
    Cada item: {"red", "perfil", "icono"}
    """
    records = await _get_records(_REDES, max_records=10)
    return [
        {
            "red": r.get("fields", {}).get("RED", ""),
            "perfil": r.get("fields", {}).get("PERFIL", ""),
            "icono": r.get("fields", {}).get("ICONO", ""),
        }
        for r in records
    ]


# ── Helpers para contenido social → familias ─────────────────────────────────

async def obtener_familias_inscriptas() -> list[dict]:
    """
    Retorna todas las FAMILIAS con al menos un teléfono cargado.
    Cada item: {"id", "telefono", "nombre_padre", "apodo_padre",
                "nombre_madre", "apodo_madre", "nino_ids"}
    """
    formula = "OR(LEN({CELL PADRE})>0, LEN({CELL MADRE})>0)"
    records = await _get_records(_FAMILIAS, formula=formula, max_records=100)
    resultado = []
    for r in records:
        f = r.get("fields", {})
        # Preferir CELL PADRE, fallback a CELL MADRE
        telefono = f.get("CELL PADRE", "") or f.get("CELL MADRE", "")
        if not telefono:
            continue
        resultado.append({
            "id": r["id"],
            "telefono": telefono,
            "nombre_padre": f.get("NOMBRE PADRE", ""),
            "apellido_padre": f.get("APELLIDO PADRE", ""),
            "apodo_padre": f.get("APODO PADRE", ""),
            "nombre_madre": f.get("NOMBRE MADRE", ""),
            "apellido_madre": f.get("APELLIDO MADRE", ""),
            "apodo_madre": f.get("APODO MADRE", ""),
            "nino_ids": f.get("NIÑOS FENIX", []),
        })
    return resultado


async def obtener_nombre_nino(nino_id: str) -> dict | None:
    """Retorna nombre y apodo de un niño por su record_id (busca en NIÑOS y PRUEBA)."""
    async with httpx.AsyncClient() as client:
        # Primero buscar en NIÑOS FENIX
        try:
            r = await client.get(f"{_BASE_URL}/{_NINOS}/{nino_id}", headers=_headers(), timeout=10)
            if r.status_code == 200:
                f = r.json().get("fields", {})
                return {
                    "id": nino_id,
                    "tabla": _NINOS,
                    "nombre": f.get("NOMBRE", ""),
                    "apellido": f.get("APELLIDO", ""),
                    "apodo": f.get("APODO", ""),
                }
        except Exception:
            pass
        # Buscar en PRUEBA FENIX
        try:
            r = await client.get(f"{_BASE_URL}/{_PRUEBAS}/{nino_id}", headers=_headers(), timeout=10)
            if r.status_code == 200:
                f = r.json().get("fields", {})
                return {
                    "id": nino_id,
                    "tabla": _PRUEBAS,
                    "nombre": f.get("NOMBRE HIJO", ""),
                    "apellido": f.get("APELLIDO HIJO", ""),
                    "apodo": "",
                }
        except Exception:
            pass
        logger.error(f"GET NIÑO/PRUEBA {nino_id}: no encontrado")
    return None
