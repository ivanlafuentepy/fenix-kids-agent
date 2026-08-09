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
import asyncio
import logging
import unicodedata
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appWwCQxALdMMV4MA")

_BASE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"

# Nombres de tablas (en base Salsa Soul)
_LEADS     = "LEADS FENIX"
_NINOS     = "NIÑOS FENIX"
_HORARIOS  = "HORARIOS FENIX"
_RESERVAS  = "RESERVAS FENIX"
_PAGOS     = "PAGOS"
# El select de estado del niño se llama ESTADO2 desde el cambio de schema del
# 2026-08-08: "ESTADO" pasó a ser una FORMULA (✅ AL DÍA / ❌ VENCIDO) y Airtable
# rechaza con 422 cualquier escritura sobre ella. Una sola constante para que el
# proximo renombre sea un solo lugar.
_CAMPO_ESTADO_NINO = "ESTADO2"
_TUTORES   = "TUTORES FENIX"  # LEGACY: solo CODIGO del juego y datos de factura viven acá
_ALUMNOS   = "ALUMNOS"        # compartida con Salsa — los tutores de Fenix viven acá
_NEGOCIO_FENIX = "FENIX KIDS ACADEMY"  # opción del multi-select NEGOCIO que marca al tutor
_CONTENIDO = "CONTENIDO FENIX"
_ANUNCIOS  = "ANUNCIOS FENIX"
_REDES     = "REDES FENIX"
_ASISTENCIA = "ASISTENCIA FENIX"
_FACTURAS  = "FACTURAS"  # compartida con Salsa — las de Fenix llevan link TUTOR


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


async def _request_con_reintento_429(client: httpx.AsyncClient, metodo: str, url: str, **kwargs):
    """Ejecuta un request a Airtable; ante 429 espera Retry-After y reintenta
    UNA vez. Airtable limita 5 req/s POR BASE (compartida con Dorita) y penaliza
    ~30s tras un 429. Sin esto, un 429 en un guard "buscar antes de crear" se
    veía como 'no existe' → PAGO/FAMILIA duplicados (auditoría 04-07-26 C4)."""
    r = await client.request(metodo, url, **kwargs)
    if r.status_code == 429:
        try:
            espera = min(float(r.headers.get("Retry-After") or 30), 35.0)
        except (TypeError, ValueError):
            espera = 30.0
        logger.warning(f"[Airtable] 429 rate limit ({metodo} {url.rsplit('/v0/', 1)[-1]}) — reintento en {espera:.0f}s")
        await asyncio.sleep(espera)
        r = await client.request(metodo, url, **kwargs)
    return r


async def _post(table: str, campos: dict) -> dict | None:
    """Crea un registro nuevo. Retorna el registro creado o None."""
    if not AIRTABLE_API_KEY:
        logger.warning("AIRTABLE_API_KEY no configurado")
        return None
    url = f"{_BASE_URL}/{table}"
    async with httpx.AsyncClient() as client:
        try:
            r = await _request_con_reintento_429(client, "POST", url, json={"fields": campos}, headers=_headers(), timeout=10)
            if r.status_code in (200, 201):
                return r.json()
            logger.error(f"POST {table} → {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"POST {table} error: {e}")
    return None


async def subir_attachment_airtable(
    record_id: str,
    field_name: str,
    image_bytes: bytes,
    filename: str = "foto.jpg",
    content_type: str = "image/jpeg",
) -> bool:
    """Sube un archivo binario como attachment a un registro existente en Airtable.
    Usa el endpoint content.airtable.com con JSON + base64.
    """
    if not AIRTABLE_API_KEY or not record_id:
        return False
    import base64
    url = (
        f"https://content.airtable.com/v0/{AIRTABLE_BASE_ID}"
        f"/{record_id}/{field_name}/uploadAttachment"
    )
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    file_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "contentType": content_type,
        "filename": filename,
        "file": file_b64,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code in (200, 201):
                logger.info(f"[Airtable] Attachment subido a {record_id}/{field_name}")
                return True
            logger.error(
                f"[Airtable] Upload attachment {record_id}/{field_name} "
                f"→ {r.status_code}: {r.text[:300]}"
            )
            return False
    except Exception as e:
        logger.error(f"[Airtable] Upload attachment error: {e}")
        return False


async def _patch(table: str, record_id: str, campos: dict) -> bool:
    """Actualiza campos de un registro existente. Retorna True si fue exitoso."""
    if not AIRTABLE_API_KEY or not record_id:
        return False
    url = f"{_BASE_URL}/{table}/{record_id}"
    async with httpx.AsyncClient() as client:
        try:
            r = await _request_con_reintento_429(client, "PATCH", url, json={"fields": campos}, headers=_headers(), timeout=10)
            if r.status_code == 200:
                return True
            logger.error(f"PATCH {table}/{record_id} → {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"PATCH {table}/{record_id} error: {e}")
    return False


async def _get_records(table: str, formula: str = "", max_records: int = 10) -> list[dict]:
    """Busca registros con un filtro formula. Retorna lista de records.
    Pagina siguiendo `offset` (Airtable devuelve máx 100 por página): antes
    max_records>100 truncaba silenciosamente a 100 — ya duplicó tutores y
    dejaba familias/pagos invisibles. Si falla a mitad de la paginación,
    retorna lo acumulado (mismo contrato de siempre: lista, nunca excepción)."""
    if not AIRTABLE_API_KEY:
        return []
    url = f"{_BASE_URL}/{table}"
    params = {"maxRecords": max_records, "pageSize": min(max_records, 100)}
    if formula:
        params["filterByFormula"] = formula
    registros: list[dict] = []
    offset = None
    async with httpx.AsyncClient() as client:
        try:
            while True:
                p = dict(params)
                if offset:
                    p["offset"] = offset
                r = await _request_con_reintento_429(client, "GET", url, params=p, headers=_headers(), timeout=10)
                if r.status_code != 200:
                    logger.error(f"GET {table} → {r.status_code}: {r.text[:200]}")
                    break
                data = r.json()
                registros.extend(data.get("records", []))
                offset = data.get("offset")
                if not offset or len(registros) >= max_records:
                    break
        except Exception as e:
            logger.error(f"GET {table} error: {e}")
    return registros


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
    # Airtable select tiene "IVAN" y "NIXIE" (no "AURORA")
    _agent_airtable = "NIXIE" if agent.upper() == "AURORA" else agent.upper()
    campos: dict = {"AGENT_ACTUAL": _agent_airtable}
    return await _patch(_LEADS, record_id, campos)


async def marcar_formulario_lead(telefono: str) -> bool:
    """Marca FORMULARIO=True en LEADS."""
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return False
    return await _patch(_LEADS, record_id, {"FORMULARIO": True})


async def vincular_tutor_a_lead(telefono: str, tutor_id: str) -> bool:
    """Vincula el LEAD con su tutor (niño-eje). El tutor es una fila de ALUMNOS
    → va al link TUTOR (ALUMNOS); el viejo TUTOR FENIX (→TUTORES) quedó legacy."""
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return False
    return await _patch(_LEADS, record_id, {"TUTOR (ALUMNOS)": [tutor_id]})


async def eliminar_lead(telefono: str) -> bool:
    """Elimina el registro de LEADS para este teléfono."""
    record_id = await obtener_lead_record_id(telefono)
    if not record_id:
        return True
    return await _delete(_LEADS, record_id)


async def eliminar_todo_de_telefono(telefono: str) -> dict:
    """
    Reset completo en Airtable para un teléfono (niño-eje):
      1. TUTOR (fila ALUMNOS) por TELEFONO LIMPIO → borra sus NIÑOS con las
         RESERVAS de cada uno (links RESERVAS FENIX del niño). La fila de
         ALUMNOS no se borra (compartida con Salsa): se le quita NEGOCIO=FENIX
      2. Borra el LEAD

    Retorna dict con contadores: {"familia", "ninos", "reservas", "lead", "tutor"}
    ("familia" queda siempre 0 — la tabla FAMILIAS FENIX fue eliminada).
    """
    contador = {"familia": 0, "ninos": 0, "reservas": 0, "lead": 0, "tutor": 0}

    async def _borrar_nino_con_reservas(nino_id: str, reserva_ids: list[str]):
        # Los links del niño son la fuente (el FIND viejo sobre ARRAYJOIN({NINO})
        # comparaba record_id contra NOMBRES → nunca matcheaba, bug conocido).
        for rid in reserva_ids or []:
            if await _delete(_RESERVAS, rid):
                contador["reservas"] += 1
        if await _delete(_NINOS, nino_id):
            contador["ninos"] += 1

    # 1. Camino niño-eje: tutor (fila ALUMNOS) → hijos → reservas
    tutor = await buscar_tutor_por_telefono(telefono)
    if tutor:
        tf = tutor.get("fields", {}) or {}
        hijo_ids = _hijos_de_tutor(tf)
        async with httpx.AsyncClient() as client:
            for hid in hijo_ids:
                reserva_ids: list[str] = []
                try:
                    r = await client.get(f"{_BASE_URL}/{_NINOS}/{hid}", headers=_headers(), timeout=10)
                    if r.status_code == 200:
                        reserva_ids = r.json().get("fields", {}).get("RESERVAS FENIX", []) or []
                except Exception as e:
                    logger.error(f"[RESET] Error leyendo niño {hid}: {e}")
                await _borrar_nino_con_reservas(hid, reserva_ids)
        # La fila de ALUMNOS es COMPARTIDA con Salsa/Impulso — NUNCA se borra.
        # Reset = quitarle la marca FENIX (el router deja de reconocerlo).
        _negocios = [n for n in (tf.get("NEGOCIO") or []) if n != _NEGOCIO_FENIX]
        if await _patch(_ALUMNOS, tutor["id"], {"NEGOCIO": _negocios}):
            contador["tutor"] += 1

    # 2. Borrar lead
    lead_id = await obtener_lead_record_id(telefono)
    if lead_id and await _delete(_LEADS, lead_id):
        contador["lead"] += 1

    logger.info(f"[AIRTABLE] Reset total para {telefono}: {contador}")
    return contador


async def asegurar_grupo_prueba_admin(telefono: str) -> str | None:
    """Garantiza el grupo de prueba para 'modo alumno' (niño-eje, F7.b).

    Si el tutor del teléfono ya existe con hijos linkeados, lo devuelve sin
    tocar nada. Si no existe (ej: lo borró 'modo padre'), crea el tutor Iván +
    Mateo (ACTIVO) linkeado, para que Aurora reconozca al admin como inscripto.

    Retorna el tutor_id (existente o recién creado), o None si falló.
    """
    tutor = await buscar_tutor_por_telefono(telefono)
    if tutor:
        tf = tutor.get("fields", {}) or {}
        if _hijos_de_tutor(tf):
            return tutor["id"]
        tutor_id = tutor["id"]
    else:
        tutor_id = await crear_o_actualizar_tutor(
            {"nombre": "Iván", "apellido": "Lafuente", "telefono": telefono}, "Papá",
        )
    if not tutor_id:
        logger.error(f"[PRUEBA] No se pudo crear el tutor de prueba para {telefono}")
        return None

    await crear_nino(
        {"nombre": "Mateo", "apellido": "Lafuente", "fecha_nacimiento": "2019-03-15"},
        padre_id=tutor_id, estado="ACTIVO",
    )
    logger.info(f"[PRUEBA] Grupo de prueba admin creado: tutor={tutor_id}")
    return tutor_id


# ── TUTORES (identidad niño-eje — viven en ALUMNOS desde la migración 08/26) ──
# Los padres/madres son filas de ALUMNOS marcadas con NEGOCIO=FENIX KIDS ACADEMY.
# El niño linkea a sus tutores por PADRE (ALUMNOS)/MADRE (ALUMNOS); el tutor
# tiene los inversos HIJOS FENIX (PADRE)/(MADRE). TUTORES FENIX quedó LEGACY
# (los campos HIJOS de esa tabla son TEXTO — sumarlos como listas fue el crash
# str+list del 07/08).


def _hijos_de_tutor(f: dict) -> list[str]:
    """IDs de NIÑOS FENIX linkeados a un tutor (fila de ALUMNOS)."""
    return (f.get("HIJOS FENIX (PADRE)") or []) + (f.get("HIJOS FENIX (MADRE)") or [])


def _tutores_de_nino(f: dict) -> list[str]:
    """IDs de tutores (filas de ALUMNOS) linkeados a un NIÑO."""
    return (f.get("PADRE (ALUMNOS)") or []) + (f.get("MADRE (ALUMNOS)") or [])


def _parentesco_de_alumno(f: dict) -> str:
    """ALUMNOS no tiene PARENTESCO — se deriva del GENERO de la fila."""
    return {"HOMBRE": "Papá", "MUJER": "Mamá"}.get((f.get("GENERO") or "").strip().upper(), "")


def tutor_tiene_telefono(tutor: dict, telefono: str) -> bool:
    """¿Este teléfono es de este tutor? — única fuente de verdad del criterio.

    Contempla los DOS números de la fila (TELEFONO y TELEFONO2): un padre puede
    hablarle a Aurora desde una línea distinta a la cargada para Salsa/Impulso
    (la fila de ALUMNOS es compartida y su TELEFONO no siempre es el de Fenix).
    Recibe un tutor ya mapeado por _tutor_a_dict.
    """
    if not telefono:
        return False
    conocidos = {
        (tutor.get("cell") or "").strip(),
        (tutor.get("cell_limpio") or "").strip(),
        (tutor.get("cell2") or "").strip(),
        (tutor.get("cell2_limpio") or "").strip(),
    }
    return telefono in (conocidos - {""})


async def buscar_tutor_por_telefono(telefono: str) -> dict | None:
    """Busca al TUTOR (fila de ALUMNOS) por su teléfono — TELEFONO o TELEFONO2.

    Se miran los dos números porque la fila de ALUMNOS es compartida con
    Salsa/Impulso: el TELEFONO principal puede ser el de esos negocios y el
    WhatsApp con el que la familia le habla a Aurora vivir en TELEFONO2
    (control de identidad 07/08 — Gaudi escribía desde un número invisible).

    Un mismo teléfono puede tener varias filas en ALUMNOS (Salsa/Impulso/Fenix)
    — se elige por prioridad: con hijos FENIX linkeados > con NEGOCIO Fenix.
    Sin ninguna de las dos marcas → no es tutor de Fenix (retorna None).
    """
    if not telefono:
        return None
    formula = (f"OR(FIND('{telefono}', {{TELEFONO LIMPIO}} & '')>0, "
               f"FIND('{telefono}', {{TELEFONO2 LIMPIO}} & '')>0)")
    records = await _get_records(_ALUMNOS, formula=formula, max_records=10)
    con_hijos = [r for r in records if _hijos_de_tutor(r.get("fields", {}) or {})]
    if con_hijos:
        return con_hijos[0]
    con_negocio = [r for r in records
                   if _NEGOCIO_FENIX in ((r.get("fields", {}) or {}).get("NEGOCIO") or [])]
    return con_negocio[0] if con_negocio else None


async def buscar_tutor_legacy_por_telefono(telefono: str) -> dict | None:
    """Fila LEGACY del tutor en TUTORES FENIX (ahí siguen viviendo el CODIGO
    del juego y los datos de facturación). Solo para esos dos flujos."""
    if not telefono:
        return None
    records = await _get_records(_TUTORES, formula=f"FIND('{telefono}', {{CELL LIMPIO}})>0", max_records=1)
    return records[0] if records else None


async def es_cliente_activo_por_telefono(telefono: str) -> bool:
    """Router niño-eje: ¿este teléfono es de un cliente (Aurora) o un lead (Ivan)?

    TUTOR (fila ALUMNOS) por TELEFONO LIMPIO → sus hijos (links HIJOS FENIX)
    → cliente si al menos un hijo tiene ESTADO != 'A PRUEBA' (vacío = cliente).
    Todos A PRUEBA, sin tutor o sin hijos → lead.

    (El fallback legacy por FAMILIAS se eliminó con la tabla — pre-check 03/08:
    cero tutores sin hijos linkeados, cero teléfonos solo-en-FAMILIAS.)
    """
    tutor = await buscar_tutor_por_telefono(telefono)
    if tutor:
        f = tutor.get("fields", {}) or {}
        hijo_ids = _hijos_de_tutor(f)
        if hijo_ids:
            async with httpx.AsyncClient() as client:
                for hid in hijo_ids:
                    try:
                        r = await client.get(f"{_BASE_URL}/{_NINOS}/{hid}", headers=_headers(), timeout=10)
                        if r.status_code == 200:
                            estado = (r.json().get("fields", {}).get(_CAMPO_ESTADO_NINO) or "").strip().upper()
                            if estado != "A PRUEBA":
                                return True
                    except Exception as e:
                        logger.error(f"[ROUTER] Error leyendo hijo {hid} de tutor {tutor.get('id')}: {e}")
            return False
    return False


# Planes reales que acepta el select NIÑOS FENIX.PLAN. Hoy solo se venden el
# pack de 5 y la clase de prueba (Iván, 2026-08-08); los mensual/trimestral
# quedan porque el select todavia los tiene y hay niños viejos con ese plan.
# Si el texto no se reconoce se devuelve "" y el llamador NO manda el campo:
# un valor invalido hace que Airtable rechace el PATCH ENTERO con 422, y ahi
# se pierde tambien el ESTADO2 que iba en el mismo request.
_PLANES_NINO = ("Suscripcion", "Mensual", "Paquete5", "Trimestral", "Una clase")


def plan_a_airtable(plan: str) -> str:
    """Traduce el plan que sale del parser de inscripcion al select real."""
    p = (plan or "").strip().upper()
    if not p:
        return ""
    if "PACK" in p or "PAQUETE" in p:
        return "Paquete5"
    if "PRUEBA" in p or "UNA CLASE" in p:
        return "Una clase"
    if "MENSUAL" in p:
        return "Mensual"
    if "TRIMESTRAL" in p:
        return "Trimestral"
    if "SUSCRIP" in p:
        return "Suscripcion"
    logger.warning(f"[PLAN] '{plan}' no matchea ningun plan del select — no se manda")
    return ""


async def crear_o_actualizar_tutor(persona: dict, parentesco: str) -> str | None:
    """
    Crea/actualiza al tutor como fila de ALUMNOS con NEGOCIO=FENIX KIDS ACADEMY.
    Idempotente por TELEFONO LIMPIO + GENERO (el análogo del viejo
    CELL LIMPIO + PARENTESCO: una pareja puede compartir teléfono).

    La fila puede ser COMPARTIDA con Salsa/Impulso → al reutilizarla solo se
    completan campos vacíos y se suma la opción FENIX al NEGOCIO; nunca se
    pisan datos existentes de otro negocio.

    persona = {nombre, apellido, ci, telefono, email, fecha_nacimiento}
    parentesco = "Papá" | "Mamá" | "Tutor"
    """
    if not persona.get("nombre"):
        return None

    import re
    campos: dict = {"NOMBRE": persona["nombre"]}
    if persona.get("apellido"):
        campos["APELLIDO"] = persona["apellido"]
    if persona.get("ci"):
        campos["CI"] = str(persona["ci"]).strip()
    tel = ""
    if persona.get("telefono"):
        tel = str(persona["telefono"]).strip()
        campos["TELEFONO"] = tel
    if persona.get("email"):
        campos["EMAIL"] = persona["email"]
    if persona.get("fecha_nacimiento"):
        campos["FECHA NACIMIENTO"] = persona["fecha_nacimiento"]

    genero_esperado = {"Papá": "HOMBRE", "Mamá": "MUJER"}.get(parentesco, "")

    # Idempotencia: candidatos por TELEFONO LIMPIO; se prefiere la fila cuyo
    # GENERO matchea el parentesco (o sin GENERO), priorizando las que ya
    # tienen hijos FENIX o la marca de NEGOCIO.
    if tel:
        tel_norm = re.sub(r"[^0-9]", "", tel)
        if tel_norm.startswith("0"):
            tel_norm = "595" + tel_norm[1:]
        candidatos = await _get_records(_ALUMNOS, formula=f"{{TELEFONO LIMPIO}}='{tel_norm}'", max_records=10)

        def _compatible(c: dict) -> bool:
            g = ((c.get("fields", {}) or {}).get("GENERO") or "").strip().upper()
            return not genero_esperado or not g or g == genero_esperado

        compatibles = [c for c in candidatos if _compatible(c)]
        compatibles.sort(key=lambda c: (
            not _hijos_de_tutor(c.get("fields", {}) or {}),
            _NEGOCIO_FENIX not in ((c.get("fields", {}) or {}).get("NEGOCIO") or []),
        ))
        if compatibles:
            elegido = compatibles[0]
            ef = elegido.get("fields", {}) or {}
            upd: dict = {}
            for k, v in campos.items():
                if not str(ef.get(k) or "").strip():
                    upd[k] = v
            if _NEGOCIO_FENIX not in (ef.get("NEGOCIO") or []):
                upd["NEGOCIO"] = list(ef.get("NEGOCIO") or []) + [_NEGOCIO_FENIX]
            if genero_esperado and not (ef.get("GENERO") or "").strip():
                upd["GENERO"] = genero_esperado
            if upd:
                await _patch(_ALUMNOS, elegido["id"], upd)
            return elegido["id"]

    campos["NEGOCIO"] = [_NEGOCIO_FENIX]
    if genero_esperado:
        campos["GENERO"] = genero_esperado
    resultado = await _post(_ALUMNOS, campos)
    if resultado:
        logger.info(f"Tutor creado en ALUMNOS: {resultado['id']} ({parentesco})")
        return resultado["id"]
    return None


# ── NIÑOS ─────────────────────────────────────────────────────────────────────

async def crear_nino(
    datos_nino: dict,
    *,
    padre_id: str = "",
    madre_id: str = "",
    estado: str = "",
) -> str | None:
    """
    Crea un registro en NIÑOS (niño-eje, F7.b).

    - padre_id / madre_id: links directos a los tutores (filas de ALUMNOS).
    - estado: ESTADO explícito del niño (A PRUEBA / ACTIVO / ...). SIEMPRE debe
      venir del flujo que crea al niño — sin estado el niño queda vacío = cliente
      y el router mandaría un lead a Aurora.

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

    # Links niño-eje: el niño apunta directo a sus tutores (filas de ALUMNOS).
    if padre_id:
        campos["PADRE (ALUMNOS)"] = [padre_id]
    if madre_id:
        campos["MADRE (ALUMNOS)"] = [madre_id]

    if estado:
        campos[_CAMPO_ESTADO_NINO] = estado.strip()
    else:
        logger.warning(f"[NIÑO] crear_nino sin ESTADO explícito ({datos_nino.get('nombre')}) — queda vacío (= cliente)")

    resultado = await _post(_NINOS, campos)
    if resultado:
        logger.info(f"Niño creado: {resultado['id']} padre={padre_id or '-'} madre={madre_id or '-'} estado={campos.get(_CAMPO_ESTADO_NINO, '-')}")
        if datos_nino.get("nombre"):
            from agent.concurrencia import _fire_and_forget
            from agent.voces_alumnos import generar_audios_nino
            _fire_and_forget(generar_audios_nino(datos_nino["nombre"]))
        return resultado["id"]
    return None


async def actualizar_nino(nino_id: str, campos: dict) -> bool:
    """Actualiza campos de un NIÑO (ej: talla_remera, apodo)."""
    return await _patch(_NINOS, nino_id, campos)


def _nino_a_dict(nino_id: str, f: dict) -> dict:
    """Mapea los fields crudos de un NIÑO al formato uniforme del código."""
    return {
        "id": nino_id,
        "nombre_completo": f.get("NOMBRE COMPLETO", ""),
        "nombre": f.get("NOMBRE", ""),
        "apellido": f.get("APELLIDO", ""),
        "apodo": f.get("APODO", ""),
        "ci": f.get("CI", ""),
        "fecha_nacimiento": f.get("FECHA NACIMIENTO", ""),
        "sexo": f.get("SEXO", ""),
        "talla_remera": f.get("TALLA REMERA", ""),
        # Niño-eje: links directos del niño (reservas por link,
        # no por FIND del nombre de la familia — bug A8)
        "reserva_ids": f.get("RESERVAS FENIX", []) or [],
        "estado": f.get(_CAMPO_ESTADO_NINO, ""),
    }


def _tutor_a_dict(tutor_id: str, f: dict) -> dict:
    """Mapea los fields crudos de un TUTOR (fila de ALUMNOS) al formato uniforme.
    Se mantienen las claves cell/cell_limpio para no romper a los consumidores."""
    return {
        "id": tutor_id,
        "nombre": f.get("NOMBRE", ""),
        "apellido": f.get("APELLIDO", ""),
        "apodo": f.get("APODO", ""),
        "ci": f.get("CI", ""),
        "cell": f.get("TELEFONO", ""),
        "cell_limpio": f.get("TELEFONO LIMPIO", ""),
        # Segundo número: el WhatsApp con el que le habla a Aurora cuando el
        # TELEFONO principal es el de Salsa/Impulso (fila compartida).
        "cell2": f.get("TELEFONO2", ""),
        "cell2_limpio": f.get("TELEFONO2 LIMPIO", ""),
        "email": f.get("EMAIL", ""),
        "fecha_nacimiento": f.get("FECHA NACIMIENTO", ""),
        "parentesco": _parentesco_de_alumno(f),
        "es_quien_paga": bool(f.get("ES QUIEN PAGA")),  # no existe en ALUMNOS → False
    }


async def obtener_grupo_familiar(telefono: str) -> dict | None:
    """Grupo familiar por teléfono (niño-eje): tutor (fila ALUMNOS) por
    TELEFONO LIMPIO → sus hijos (links HIJOS FENIX) → todos los tutores de esos
    hijos (papá y mamá aunque escriba uno solo).

    Retorna {"tutores": [...], "hijos": [...]} en formato uniforme
    (_tutor_a_dict / _nino_a_dict), o None si el teléfono no es de nadie conocido.
    """
    tutor = await buscar_tutor_por_telefono(telefono)
    if tutor:
        tf = tutor.get("fields", {}) or {}
        hijo_ids = _hijos_de_tutor(tf)
        if hijo_ids:
            hijos: list[dict] = []
            tutor_ids: list[str] = [tutor["id"]]
            async with httpx.AsyncClient() as client:
                for hid in hijo_ids:
                    try:
                        r = await client.get(f"{_BASE_URL}/{_NINOS}/{hid}", headers=_headers(), timeout=10)
                        if r.status_code == 200:
                            f = r.json().get("fields", {})
                            hijos.append(_nino_a_dict(hid, f))
                            for tid in _tutores_de_nino(f):
                                if tid not in tutor_ids:
                                    tutor_ids.append(tid)
                    except Exception as e:
                        logger.error(f"[GRUPO] Error leyendo hijo {hid}: {e}")
                tutores: list[dict] = []
                for tid in tutor_ids:
                    try:
                        r = await client.get(f"{_BASE_URL}/{_ALUMNOS}/{tid}", headers=_headers(), timeout=10)
                        if r.status_code == 200:
                            tutores.append(_tutor_a_dict(tid, r.json().get("fields", {})))
                    except Exception as e:
                        logger.error(f"[GRUPO] Error leyendo tutor {tid}: {e}")
            if hijos:
                return {"tutores": tutores, "hijos": hijos}
    return None


async def obtener_ninos_al_dia() -> list[dict]:
    """Niños con pago AL DÍA para la confirmación proactiva del sábado (niño-eje).

    Migración FAMILIAS→NIÑO: el vencimiento vive en el NIÑO ({ESTADO} =
    fórmula sobre VENCE EL, rollup de sus PAGOS). Ojo con el nombre: el
    2026-08-08 la fórmula pasó de llamarse {AL DÍA?} a {ESTADO} (y el select
    editable pasó a {ESTADO2}) — leer el nombre viejo devolvía vacío en todas
    las filas y la confirmación del sábado salía sin destinatarios.

    El campo {ESTADO} devuelve "✅ AL DÍA" / "❌ VENCIDO" / vacío. Se traen
    TODOS los niños (paginando con max_records alto) y se filtra en Python:
    un FIND sobre un campo fórmula con emoji + acento en filterByFormula da
    422 silenciosos (ver reference_airtable_errores).

    Devuelve los records crudos (id + fields, incluye PADRE/MADRE).
    El armado del envío (tutor pagador, agrupado por teléfono) lo hace
    agent/confirmacion_sabado.py.
    """
    ninos = await _get_records(_NINOS, max_records=2000)
    return [
        n for n in ninos
        if "AL DÍA" in ((n.get("fields", {}) or {}).get("ESTADO") or "")
    ]


# ── HORARIOS ──────────────────────────────────────────────────────────────────

async def obtener_horarios_disponibles(max_horarios: int = 8) -> list[dict]:
    """
    Retorna los próximos HORARIOS disponibles.
    Cada item: {"id", "horario", "fecha", "hora", "dia"}

    Incluye los turnos de HOY: si la persona quiere venir en el día, la agenda
    decide ella (11:00 o 15:30), no importa si una de las horas ya pasó.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    # Hora de Paraguay, NO la del server (Railway corre en UTC)
    hoy = datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()
    # fecha >= hoy — incluye hoy (IS_AFTER lo excluía y rechazaba agendar en el día)
    formula = f"NOT(IS_BEFORE({{FECHA}}, '{hoy}'))"
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


async def crear_horarios_mes(anio: int, mes: int, horas: tuple[str, ...] = ("11:00", "15:30")) -> dict:
    """
    Crea los HORARIOS de un mes completo: cada sábado × cada hora.
    Idempotente — los que ya existen no se duplican.

    Retorna {"creados": [...], "existentes": [...], "sabados": [...]}
    donde creados/existentes son strings "YYYY-MM-DD HH:MM".
    """
    from datetime import date, timedelta

    # Todos los sábados del mes
    d = date(anio, mes, 1)
    d += timedelta(days=(5 - d.weekday()) % 7)  # avanzar al primer sábado
    sabados = []
    while d.month == mes:
        sabados.append(d)
        d += timedelta(days=7)

    creados, existentes = [], []
    for s in sabados:
        fecha_iso = s.isoformat()
        for hora in horas:
            # ¿Ya existe? (misma fórmula que obtener_o_crear_horario)
            formula = f"AND(DATESTR({{FECHA}})='{fecha_iso}', {{HORA}}='{hora}')"
            ya = await _get_records(_HORARIOS, formula=formula, max_records=1)
            if ya:
                existentes.append(f"{fecha_iso} {hora}")
                continue
            rid = await obtener_o_crear_horario(fecha_iso, hora)
            if rid:
                creados.append(f"{fecha_iso} {hora}")
            else:
                logger.error(f"[HORARIOS-MES] No se pudo crear {fecha_iso} {hora}")

    logger.info(f"[HORARIOS-MES] {anio}-{mes:02d}: {len(creados)} creados, {len(existentes)} ya existían")
    return {"creados": creados, "existentes": existentes, "sabados": [s.isoformat() for s in sabados]}


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
                        # es_prueba (niño-eje, F7.b): el ESTADO vive en el NIÑO
                        # (backfilleado C0, se setea al crear).
                        _estado_nino = (nf.get(_CAMPO_ESTADO_NINO) or "").strip()
                        ninos.append({
                            "id": nino_id,
                            "reserva_id": res_id,
                            "nombre": nf.get("NOMBRE", ""),
                            "apellido": nf.get("APELLIDO", ""),
                            "edad": edad,
                            "apodo": nf.get("APODO", ""),
                            # clave conservada por compat con consumidores (HQ):
                            # FAMILIAS FENIX ya no existe, siempre vacío
                            "familia_id": "",
                            "presente": res_fields.get("PRESENTE", False),
                            "ausente": res_fields.get("AUSENTE", False),
                            "es_prueba": _estado_nino == "A PRUEBA",
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

async def crear_reserva(nino_id: str, horario_id: str) -> str | None:
    """
    Crea una RESERVA vinculando NINO + HORARIO (F7.b: FAMILIAS ya no se linkea;
    el es_prueba sale del ESTADO del niño y las búsquedas van por los links
    RESERVAS FENIX del niño).
    Siempre 1 reserva = 1 niño + 1 horario.
    Si ya existe una reserva para ese niño en ese horario, no crea duplicado.
    Retorna el record_id de la RESERVA (existente o nueva).
    """
    # Guard anti-duplicado por los links RESERVAS FENIX del niño. El guard
    # viejo usaba FIND(record_id, ARRAYJOIN({NINO})) — ARRAYJOIN de un link
    # devuelve NOMBRES, no ids → nunca matcheaba (reference_arrayjoin_link).
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_BASE_URL}/{_NINOS}/{nino_id}", headers=_headers(), timeout=10)
            if r.status_code == 200:
                for rid in r.json().get("fields", {}).get("RESERVAS FENIX", []) or []:
                    rr = await client.get(f"{_BASE_URL}/{_RESERVAS}/{rid}", headers=_headers(), timeout=10)
                    if rr.status_code == 200 and horario_id in (rr.json().get("fields", {}).get("HORARIO") or []):
                        logger.info(f"Reserva ya existe: {rid} nino={nino_id} horario={horario_id} — no se crea duplicado")
                        return rid
    except Exception as e:
        logger.warning(f"[RESERVA] Guard anti-dup falló (creo igual): {e}")

    campos = {
        "NINO": [nino_id],
        "HORARIO": [horario_id],
    }

    resultado = await _post(_RESERVAS, campos)
    if resultado:
        logger.info(f"Reserva creada: {resultado['id']} nino={nino_id} horario={horario_id}")
        return resultado["id"]
    return None


async def eliminar_reserva(reserva_id: str) -> bool:
    """Elimina una RESERVA."""
    return await _delete(_RESERVAS, reserva_id)


async def crear_grupo_a_prueba(
    telefono: str,
    nombre_tutor: str,
    apellido_tutor: str = "",
    ninos: list[dict] | None = None,
) -> tuple[str | None, list[str]]:
    """
    Alta niño-eje (F7.b) del lead que pagó/agendó la clase de prueba:
    TUTOR (fila ALUMNOS, idempotente por TELEFONO LIMPIO) + NIÑOS con ESTADO='A PRUEBA'
    linkeados directo al tutor (PADRE/MADRE). NO crea registro en FAMILIAS.

    El router niño-eje (es_cliente_activo_por_telefono) mantiene al lead con
    Ivan mientras todos sus hijos estén A PRUEBA; al inscribirse pasan a
    ACTIVO → Aurora. Reemplaza a crear_familia_a_prueba.

    Idempotente: si el tutor del teléfono ya tiene hijos linkeados (cliente o
    prueba previa), no crea nada — misma semántica que la reutilización de
    familia del flujo viejo. Ficha de tutor sin hijos → se completa.

    ninos = [{"nombre", "apellido", "fecha_nacimiento", "sexo"}, ...]
    Retorna (tutor_id, [nino_ids nuevos]).
    """
    from agent.ab_test import actualizar_estado_flags

    nombre_tutor = (nombre_tutor or "").strip() or "Lead"
    apellido_tutor = (apellido_tutor or "").strip()

    tutor_existente = await buscar_tutor_por_telefono(telefono)
    parentesco = ""
    tutor_id = None
    if tutor_existente:
        tf = tutor_existente.get("fields", {}) or {}
        tutor_id = tutor_existente["id"]
        parentesco = _parentesco_de_alumno(tf)
        hijos_prev = _hijos_de_tutor(tf)
        if hijos_prev:
            await actualizar_estado_flags(telefono, tutor_id=tutor_id)
            logger.info(f"[A PRUEBA] Tutor ya existe con hijos para {telefono}: {tutor_id} — reutilizo")
            return tutor_id, []
        # Ficha sin hijos → completar el nombre si el existente está vacío o es 'Lead'
        _nom_prev = (tf.get("NOMBRE") or "").strip()
        if nombre_tutor != "Lead" and (not _nom_prev or _nom_prev.lower() == "lead"):
            _campos_upd = {"NOMBRE": nombre_tutor}
            if apellido_tutor:
                _campos_upd["APELLIDO"] = apellido_tutor
            await _patch(_ALUMNOS, tutor_id, _campos_upd)
    else:
        genero = deducir_genero(nombre_tutor)
        parentesco = "Mamá" if genero == "MUJER" else "Papá"
        tutor_id = await crear_o_actualizar_tutor(
            {"nombre": nombre_tutor, "apellido": apellido_tutor, "telefono": telefono},
            parentesco,
        )
    if not tutor_id:
        logger.error(f"[A PRUEBA] No se pudo crear el TUTOR para {telefono}")
        return None, []

    # Estado local + vínculo al LEAD (reemplaza el link FAMILIA)
    await actualizar_estado_flags(telefono, tutor_id=tutor_id)
    await vincular_tutor_a_lead(telefono, tutor_id)

    _link = {"madre_id": tutor_id} if parentesco == "Mamá" else {"padre_id": tutor_id}
    nino_ids = []
    for n in (ninos or []):
        if not n.get("nombre"):
            continue
        nid = await crear_nino(n, estado="A PRUEBA", **_link)
        if nid:
            nino_ids.append(nid)

    logger.info(f"[A PRUEBA] Grupo niño-eje creado para {telefono}: tutor={tutor_id}, niños={nino_ids}")
    return tutor_id, nino_ids


async def registrar_pago_fenix(
    monto: int,
    concepto: str = "PRUEBA",
    metodo: str = "TRANSFER",
    lead_id: str | None = None,
    telefono: str = "",
) -> str | None:
    """Crea un registro de PAGO en la tabla PAGOS (niño-eje, corte F7): linkea
    a NIÑOS FENIX (los hermanos que cubre — un pago, un monto, N hermanos;
    NUNCA se parte), a PAGA (ALUMNOS) (el tutor que puso la plata — fila de
    ALUMNOS; el link viejo PAGA→TUTORES quedó legacy) y al LEAD FENIX si se
    pasa lead_id.

    El código es la ÚNICA fuente del pago. Idempotente: si ya hay un PAGO de
    prueba registrado HOY (visto por los PAGOS de los niños), no lo duplica.

    Retorna el record_id del PAGO (nuevo o el existente) o None si falla.
    """
    if monto <= 0 or not telefono:
        logger.warning(f"[PAGO] registrar_pago_fenix sin teléfono o monto<=0: tel={telefono} monto={monto}")
        return None

    # Niños que cubre el pago: grupo familiar (tutor → hijos)
    grupo = await obtener_grupo_familiar(telefono)
    nino_ids = [h["id"] for h in (grupo or {}).get("hijos", []) if h.get("id")]

    # Guard anti-duplicado: ¿ya hay un PAGO de prueba creado hoy? (unión de los
    # PAGOS de los niños, link inverso)
    pago_ids: list[str] = []
    if nino_ids:
        async with httpx.AsyncClient() as client:
            for nid in nino_ids:
                try:
                    r = await client.get(f"{_BASE_URL}/{_NINOS}/{nid}", headers=_headers(), timeout=10)
                    if r.status_code == 200:
                        for pid in r.json().get("fields", {}).get("PAGOS", []) or []:
                            if pid not in pago_ids:
                                pago_ids.append(pid)
                except Exception as e:
                    logger.warning(f"[PAGO] Guard: no pude leer PAGOS del niño {nid}: {e}")
    if pago_ids:
        _or = ",".join(f"RECORD_ID()='{pid}'" for pid in pago_ids)
        _formula = f"OR({_or})" if len(pago_ids) > 1 else _or
        pagos = await _get_records(_PAGOS, formula=_formula, max_records=len(pago_ids))
        from datetime import datetime
        from zoneinfo import ZoneInfo
        hoy = datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()
        for p in pagos:
            pf = p.get("fields", {})
            pconc = (pf.get("CONCEPTO") or "")
            pfecha = (pf.get("FECHA") or "")[:10]
            if pconc.startswith("PRUEBA") and pfecha == hoy:
                logger.info(f"[PAGO] Ya existe PAGO {pconc} hoy para {telefono} → no duplico ({p['id']})")
                return p["id"]

    # Tutor pagador (PAGA (ALUMNOS)): el tutor cuyo cel coincide con quien mandó
    # el comprobante; si no, el marcado ES QUIEN PAGA; si no, el único tutor.
    # Con 2+ tutores sin señal clara, no se adivina (queda sin pagador).
    tutor_paga_id = None
    try:
        tutores = [t for t in (grupo or {}).get("tutores", []) if t.get("id")]
        _por_cell = next(
            (t for t in tutores if tutor_tiene_telefono(t, telefono)),
            None,
        ) if telefono else None
        _marcado = next((t for t in tutores if t.get("es_quien_paga")), None)
        _elegido = _por_cell or _marcado or (tutores[0] if len(tutores) == 1 else None)
        tutor_paga_id = _elegido["id"] if _elegido else None
    except Exception as e:
        logger.warning(f"[PAGO] No pude resolver el tutor pagador ({telefono}): {e}")

    campos_pago = {
        "MONTO": monto,
        "METODO DE PAGO": metodo,
        "CONCEPTO": concepto,
        "ESTADO DE PAGO": "PAGADO",
        "FUENTE": "FENIX KIDS ACADEMY",
        # NEGOCIO identifica el pago por unidad de negocio (migración 28/07).
        "NEGOCIO": "FENIX KIDS ACADEMY",
        "EXCEL": True,
    }
    if nino_ids:
        campos_pago["NIÑOS FENIX"] = nino_ids
    if tutor_paga_id:
        # El tutor es una fila de ALUMNOS: va en PAGA (ALUMNOS). Escribir el
        # link viejo PAGA (→TUTORES FENIX) con este id tumba el POST entero (422).
        campos_pago["PAGA (ALUMNOS)"] = [tutor_paga_id]
    if lead_id:
        campos_pago["LEAD FENIX"] = [lead_id]
    record = await _post(_PAGOS, campos_pago)
    if record:
        rid = record.get("id")
        logger.info(f"[PAGO] Creado PAGO {concepto} {monto} para {telefono} → {rid}")
        return rid
    logger.error(f"[PAGO] No se pudo crear PAGO para {telefono}")
    return None


_CHECKIN_BASE = os.getenv("CHECKIN_BASE_URL", "https://fenix-kids-agent-production.up.railway.app")


async def marcar_qr_enviado_reserva(record_id: str) -> bool:
    """Marca QR ENVIADO=true y guarda la URL del QR en RESERVAS FENIX."""
    url_qr = f"{_CHECKIN_BASE}/checkin/{record_id}"
    return await _patch(_RESERVAS, record_id, {"QR RESERVA": url_qr, "QR ENVIADO": True})


# ── ASISTENCIA FENIX (check-in por QR de familia) ────────────────────────────

async def crear_asistencia(
    nombre: str,
    fecha_iso: str,
    hora_checkin_iso: str,
    nino_id: str = "",
    reserva_id: str = "",
    turno: str = "",
    telefono: str = "",
    metodo: str = "QR",
) -> str | None:
    """
    Crea una fila de asistencia en ASISTENCIA FENIX (una fila = un niño presente
    en un sábado). F7.b: los links FAMILIA y PRUEBA ya no se escriben (el niño
    es el eje). Retorna el record_id creado o None.

    UN SÁBADO = UNA FILA: si el niño ya tiene asistencia ese día, se devuelve la
    existente sin crear otra. Hay TRES puntos que llaman acá (cara en el tótem,
    QR de la reserva y marcado manual del HQ) y un niño puede pasar por más de
    uno el mismo sábado. Antes eso dejaba filas duplicadas; ahora importa además
    porque el saldo del pack se cuenta por filas de esta tabla, y duplicarlas le
    comería clases al niño.
    """
    if nino_id and fecha_iso:
        ya = await obtener_asistencias_ninos_fecha([nino_id], fecha_iso)
        if ya.get(nino_id):
            logger.info(f"[ASISTENCIA] {nino_id} ya estaba presente el {fecha_iso} → no duplico")
            return ya[nino_id]

    campos: dict = {
        "REGISTRO": nombre,
        "FECHA": fecha_iso,
        "HORA_CHECKIN": hora_checkin_iso,
        "MÉTODO": metodo,
    }
    if nino_id:
        campos["NIÑO"] = [nino_id]
    if reserva_id:
        campos["RESERVA"] = [reserva_id]
    if turno:
        campos["TURNO"] = turno
    if telefono:
        campos["TELEFONO"] = telefono
    rec = await _post(_ASISTENCIA, campos)
    return rec["id"] if rec else None


async def borrar_asistencia(asistencia_id: str) -> bool:
    """Borra una fila de asistencia (desmarcar presente — corregir un error)."""
    return await _delete(_ASISTENCIA, asistencia_id)


async def obtener_asistencias_ninos_fecha(nino_ids: list[str], fecha_iso: str) -> dict[str, str]:
    """
    Retorna un mapa {nino_id: asistencia_id} de las asistencias ya cargadas
    para esos niños en esa fecha. Sirve para saber quién ya está presente hoy.
    """
    if not nino_ids:
        return {}
    formula = f"DATETIME_FORMAT({{FECHA}}, 'YYYY-MM-DD')='{fecha_iso}'"
    registros = await _get_records(_ASISTENCIA, formula=formula, max_records=500)
    nino_set = set(nino_ids)
    mapa: dict[str, str] = {}
    for r in registros:
        for nid in r.get("fields", {}).get("NIÑO", []):
            if nid in nino_set:
                mapa[nid] = r["id"]
    return mapa


# ── PACK DE CLASES (5 sábados que NO vencen — desde 28/07/2026) ──────────────
# El saldo NO se guarda en ningún lado: se CALCULA en Airtable, y por eso se
# puede auditar. Las dos mitades salen de filas reales que Ivan puede abrir:
#
#   CLASES COMPRADAS  ← suma de sus pagos PAQUETE5 (PAGOS.CLASES FENIX (PACK))
#   CLASES USADAS     ← sus asistencias desde PACK DESDE (ASISTENCIA.GASTA CLASE)
#   SALDO CALCULADO   = COMPRADAS − USADAS
#
# Antes el saldo era un contador que el código pisaba (descontar_clase /
# recargar_pack): si se descontaba dos veces, o alguien lo editaba a mano, no
# quedaba rastro de por qué el número era ese. Ahora el código NO escribe el
# saldo — solo lo lee (obtener_saldo_clases) y deja marcado desde cuándo cuenta
# el pack (marcar_inicio_pack). Descontar una clase = crear la asistencia, que
# es idempotente por día (ver crear_asistencia).
#
# SALDO CALCULADO vacío = la familia sigue con el plan mensual viejo (decisión
# de Ivan 28/07: los del mensual siguen aparte) → se devuelve None para que el
# llamador no le hable de saldo al padre.
#
# CLASES DISPONIBLES y ULTIMO DESCUENTO son el contador viejo: quedan en
# Airtable como referencia histórica, ya no los lee ni los escribe nadie.

_CAMPO_PACK_DESDE = "PACK DESDE"
_CAMPO_PACK_DESDE = "PACK DESDE"
# El saldo NO se guarda: se calcula en Airtable como CLASES COMPRADAS (suma de
# los pagos PAQUETE5) − CLASES USADAS (asistencias desde PACK DESDE). Cada
# número se puede abrir hasta la fila que lo explica; el contador viejo
# CLASES DISPONIBLES quedó de referencia hasta que se apague.
_CAMPO_SALDO = "SALDO CALCULADO"


async def _leer_nino(nino_id: str) -> dict | None:
    """Lee un registro de NIÑOS FENIX por record_id. None si falla o no existe."""
    if not AIRTABLE_API_KEY or not nino_id:
        return None
    url = f"{_BASE_URL}/{_NINOS}/{nino_id}"
    async with httpx.AsyncClient() as client:
        try:
            r = await _request_con_reintento_429(client, "GET", url, headers=_headers(), timeout=10)
            if r.status_code == 200:
                return r.json()
            logger.error(f"GET {_NINOS}/{nino_id} → {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.error(f"GET {_NINOS}/{nino_id} error: {e}")
    return None


async def obtener_saldo_clases(nino_id: str) -> int | None:
    """Clases que le quedan del pack. None = el niño no está en el modelo pack.

    Sale de SALDO CALCULADO (CLASES COMPRADAS − CLASES USADAS), no del contador
    viejo: así el número que se le dice al padre es el mismo que Ivan ve en la
    ficha, y cada mitad se puede abrir hasta el pago o la asistencia que la
    explica. El campo queda vacío cuando el niño no tiene pagos de pack, que es
    justo el caso "familia del mensual viejo" → None.
    """
    rec = await _leer_nino(nino_id)
    if not rec:
        return None
    valor = rec.get("fields", {}).get(_CAMPO_SALDO)
    return int(valor) if valor is not None else None


async def padre_de_nino(nino_id: str) -> tuple[str, str, str]:
    """(nombre_padre, telefono, vence_el) del tutor del niño.

    Para avisarle al padre cuando el hijo entra. Prioriza el tutor que paga
    (ES QUIEN PAGA); si no hay, el primero con celular cargado. El teléfono
    sale de TELEFONO LIMPIO (fórmula ya normalizada a 595...), que es el mismo
    número con el que la familia habla por WhatsApp.
    Devuelve ("", "", "") si no se puede resolver — el llamador no avisa.
    """
    rec = await _leer_nino(nino_id)
    if not rec:
        return "", "", ""
    campos = rec.get("fields", {})
    vence = campos.get("VENCE EL") or ""
    if isinstance(vence, list):
        vence = vence[0] if vence else ""

    tutor_ids = _tutores_de_nino(campos)
    if not tutor_ids:
        return "", "", str(vence)

    candidatos = []
    for tid in tutor_ids[:4]:
        recs = await _get_records(_ALUMNOS, formula=f"RECORD_ID()='{tid}'", max_records=1)
        if not recs:
            continue
        tf = recs[0].get("fields", {})
        tel = (tf.get("TELEFONO LIMPIO") or "").strip()
        if tel:
            candidatos.append((bool(tf.get("ES QUIEN PAGA")), (tf.get("NOMBRE") or "").strip(), tel))
    if not candidatos:
        return "", "", str(vence)
    # el que paga primero; si ninguno lo es, el primero con celular
    candidatos.sort(key=lambda c: not c[0])
    _, nombre, telefono = candidatos[0]
    return nombre, telefono, str(vence)


async def marcar_inicio_pack(nino_id: str, fecha_iso: str) -> bool:
    """Deja marcado desde qué día cuentan las clases del pack para este niño.

    Reemplaza a la vieja recargar_pack: las clases ya NO se suman a mano, las
    aporta el propio pago (PAGOS.CLASES FENIX (PACK) → NIÑOS.CLASES COMPRADAS).
    Lo único que el pago no puede saber solo es desde cuándo empezar a contar
    las asistencias, porque PAGOS.FECHA es la fecha de CARGA: si Ivan carga el
    pago tres días tarde, arrancar ahí le regalaría las clases de esos días.

    Solo se escribe si está vacío — el primer pack manda y los siguientes no lo
    mueven. Ivan lo corrige a mano cuando la familia pagó otro día (el caso de
    Máximo: pagó el 01/08, cargado el 04/08).
    """
    if not nino_id or not fecha_iso:
        return False
    rec = await _leer_nino(nino_id)
    if not rec:
        return False
    if (rec.get("fields", {}).get(_CAMPO_PACK_DESDE) or "").strip():
        return False
    if not await _patch(_NINOS, nino_id, {_CAMPO_PACK_DESDE: fecha_iso}):
        return False
    logger.info(f"[PACK] {nino_id}: el pack cuenta desde {fecha_iso}")
    return True


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


async def obtener_contenido_de_ninos(nino_ids: list[str], max_items: int = 5) -> list[dict]:
    """Retorna el contenido (CONTENIDO FENIX) más reciente donde aparece alguno
    de los niños dados, ordenado por FECHA descendente.

    Cada item: {"titulo", "red", "link", "fecha"}.
    Filtra en Python porque el match es por record_id (no por display value).
    """
    if not nino_ids:
        return []
    nset = set(nino_ids)
    records = await _get_records(_CONTENIDO, max_records=1000)
    items = []
    for r in records:
        f = r.get("fields", {})
        if not (nset & set(f.get("NIÑOS FENIX", []))):
            continue
        link = f.get("LINK", "")
        if not link:
            continue
        items.append({
            "titulo": f.get("TITULO", ""),
            "red": f.get("RED", ""),
            "link": link,
            "fecha": f.get("FECHA", ""),
        })
    items.sort(key=lambda x: x.get("fecha", ""), reverse=True)
    return items[:max_items]


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
    Retorna los grupos familiares con al menos un hijo activo y teléfono, para
    broadcasts (niño-eje: derivados de NIÑOS + TUTORES; FAMILIAS ya no se consulta).
    Cada item: {"id", "telefono", "nombre_padre", "apellido_padre", "apodo_padre",
                "nombre_madre", "apellido_madre", "apodo_madre", "nino_ids"}

    Excluye niños con ESTADO A PRUEBA (leads que pagaron la prueba pero aún no
    se inscribieron — no reciben broadcasts). Los hermanos se agrupan por el
    teléfono de contacto (papá primero, como el criterio viejo CELL PADRE), así
    un mismo número nunca recibe el broadcast dos veces. El teléfono es CELL
    LIMPIO (595..., lo que Meta espera) con fallback al CELL crudo.
    De paso arregla A15: las familias sin los campos CELL PADRE/MADRE legacy
    eran invisibles para los broadcasts.
    """
    ninos = await _get_records(_NINOS, max_records=2000)
    # Tutores = filas de ALUMNOS con marca Fenix (NEGOCIO o hijos linkeados) —
    # NUNCA traer la tabla entera: es compartida con Salsa y es enorme.
    _f_tut = (f"OR(FIND('{_NEGOCIO_FENIX}', ARRAYJOIN({{NEGOCIO}}))>0, "
              "{HIJOS FENIX (PADRE)}!='', {HIJOS FENIX (MADRE)}!='')")
    tutores = await _get_records(_ALUMNOS, formula=_f_tut, max_records=2000)
    tut = {t["id"]: (t.get("fields", {}) or {}) for t in tutores}

    def _tel_de(tid: str) -> str:
        tf = tut.get(tid, {})
        return (tf.get("TELEFONO LIMPIO") or tf.get("TELEFONO") or "").strip()

    # Agrupar niños activos por teléfono de contacto (papá primero, después mamá/tutor)
    grupos: dict[str, dict] = {}
    for n in ninos:
        f = n.get("fields", {}) or {}
        if (f.get(_CAMPO_ESTADO_NINO) or "").strip().upper() == "A PRUEBA":
            continue
        tutor_ids = _tutores_de_nino(f)
        telefono = next((t for t in (_tel_de(tid) for tid in tutor_ids) if t), "")
        if not telefono:
            continue
        g = grupos.setdefault(telefono, {"tutor_ids": [], "nino_ids": []})
        for tid in tutor_ids:
            if tid not in g["tutor_ids"]:
                g["tutor_ids"].append(tid)
        g["nino_ids"].append(n["id"])

    resultado = []
    for telefono, g in grupos.items():
        def _por(parentesco: str) -> dict:
            return next(
                (tut[tid] for tid in g["tutor_ids"]
                 if tid in tut and _parentesco_de_alumno(tut[tid]) == parentesco),
                {},
            )
        padre, madre = _por("Papá"), _por("Mamá")
        if not padre and not madre and g["tutor_ids"]:
            # Tutor sin parentesco Papá/Mamá: usarlo como contacto principal
            padre = tut.get(g["tutor_ids"][0], {})
        resultado.append({
            "id": g["tutor_ids"][0] if g["tutor_ids"] else "",
            "telefono": telefono,
            "nombre_padre": padre.get("NOMBRE", ""),
            "apellido_padre": padre.get("APELLIDO", ""),
            "apodo_padre": padre.get("APODO", ""),
            "nombre_madre": madre.get("NOMBRE", ""),
            "apellido_madre": madre.get("APELLIDO", ""),
            "apodo_madre": madre.get("APODO", ""),
            "nino_ids": g["nino_ids"],
        })
    return resultado


async def obtener_nombre_nino(nino_id: str) -> dict | None:
    """Retorna nombre y apodo de un niño por su record_id (NIÑOS FENIX).
    El fallback a PRUEBA FENIX se retiró (migración 2.B): todo niño vive en
    NIÑOS por el dual-write, y los links de contenido apuntan a NIÑOS."""
    async with httpx.AsyncClient() as client:
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
        logger.error(f"GET NIÑO {nino_id}: no encontrado")
    return None


# ── FACTURAS (facturación a familias — flujo espejo del de Dorita) ────────────

async def listar_facturas_fenix_para_enviar() -> list[dict]:
    """Facturas de FENIX emitidas por el robot facturador (FACTURADO=True +
    COMPROBANTE SET + PDF cargado) que todavía no se enviaron.
    Niño-eje: la fila de Fenix se detecta por el link TUTOR; las de Salsa
    (link ALUMNO) las reparte Dorita."""
    formula = ("AND({FACTURADO}=TRUE(), {ENVIADO}=FALSE(), {COMPROBANTE SET}!='', "
               "{TUTOR}!='')")
    records = await _get_records(_FACTURAS, formula=formula, max_records=20)
    out = []
    for r in records:
        f = r.get("fields", {})
        adj = f.get("FACTURA PDF") or []
        out.append({
            "record_id": r["id"],
            "tutor_ids": f.get("TUTOR") or [],
            "pdf_url": adj[0].get("url", "") if adj else "",
            "pdf_filename": (adj[0].get("filename") or "factura.pdf") if adj else "factura.pdf",
        })
    return out


async def obtener_contacto_tutor(tutor_id: str) -> tuple[str, str]:
    """(telefono, nombre) de un TUTOR — para mandarle la factura (niño-eje).
    Los ids nuevos son filas de ALUMNOS; las FACTURAS viejas siguen linkeando
    a TUTORES FENIX → se intenta ALUMNOS primero y TUTORES como fallback."""
    if not tutor_id:
        return "", ""
    recs = await _get_records(_ALUMNOS, formula=f"RECORD_ID()='{tutor_id}'", max_records=1)
    if recs:
        f = recs[0].get("fields", {})
        tel = "".join(c for c in str(f.get("TELEFONO LIMPIO") or f.get("TELEFONO") or "") if c.isdigit())
    else:
        recs = await _get_records(_TUTORES, formula=f"RECORD_ID()='{tutor_id}'", max_records=1)
        if not recs:
            return "", ""
        f = recs[0].get("fields", {})
        tel = "".join(c for c in str(f.get("CELL LIMPIO") or f.get("CELL") or "") if c.isdigit())
    nombre = (f.get("APODO") or f.get("NOMBRE") or "").strip()
    return tel, nombre



async def marcar_factura_fenix_enviada(record_id: str) -> bool:
    """Marca ENVIADO=True — la familia ya recibió su PDF por WhatsApp."""
    return await _patch(_FACTURAS, record_id, {"ENVIADO": True})
