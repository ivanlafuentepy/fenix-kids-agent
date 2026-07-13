# agent/facturas.py — Flujo de factura post-pago (espejo del de Dorita)
# FENIX KIDS ACADEMY

"""
Tras un pago confirmado, Aurora pregunta "🧾 ¿Necesitás factura?". Si la familia
quiere, se crea el registro en la tabla FACTURAS de la base madre — SIN marcar
FACTURA=True en el PAGO (decisión de Iván 03/07/2026: así la automatización de
Airtable que existe para Salsa no se dispara y no hay duplicados).

El robot facturador (facturador-set, la PC de Iván) emite el PDF en Marangatú
y lo sube a FACTURA PDF + FACTURADO + COMPROBANTE SET; `_envio_facturas_fenix_loop`
(loops.py) se lo hace llegar a la familia por WhatsApp.

Migración niño-eje (F6, 2026-07-13): los datos fiscales viven en el TUTOR
pagador (TUTORES FENIX.FACTURA, texto libre con RUC/CI + nombre) y la factura
linkea TUTOR → el robot lee el lookup TUTOR RUC. FAMILIAS.FACTURA y el link
FAMILIA FENIX quedan como fallback legacy hasta archivar FAMILIAS.
"""

import logging

from agent.ab_test import actualizar_estado_flags
from agent.airtable_client import _get_records, _patch, _post, _FAMILIAS, _TUTORES, _FACTURAS

logger = logging.getLogger("agentkit")

BOTONES_FACTURA = [
    {"id": "factura_si", "title": "🧾 Sí, necesito"},
    {"id": "factura_no", "title": "No, gracias"},
]

# Concepto del PAGO → opción CONCEPTO en FACTURAS (opciones EXISTENTES del
# singleSelect — verificadas en el schema; NUNCA inventar opciones nuevas)
_CONCEPTO_FACTURA = {"PRUEBA": "LEAD PRUEBA", "CLASE": "UNA CLASE"}

# Keywords (mismas de Dorita) — el cliente pasa datos para facturar a otro nombre
_KEYWORDS_DATOS = (
    "a nombre de", "otro nombre", "otra persona", "ruc", "ci ",
    "cedula", "cédula", "razon social", "razón social",
)


async def crear_factura_fenix(
    pago_rid: str, familia_id: str, monto: int, concepto: str = "PRUEBA",
    tutor_id: str = "",
) -> str | None:
    """Crea el registro en FACTURAS para que el robot facturador lo emita.
    NO toca el PAGO. Niño-eje: linkea TUTOR (el robot lee el lookup TUTOR RUC);
    FAMILIA FENIX se sigue escribiendo como fallback legacy hasta el corte.
    Retorna el record_id de la factura o None."""
    descripcion = ("Clase de prueba FENIX Kids — sábado en el parque"
                   if concepto == "PRUEBA" else "Clase FENIX Kids — sábado en el parque")
    campos = {
        "FUENTE": "FENIX KIDS ACADEMY",
        "MONTO": monto,
        "CONCEPTO": _CONCEPTO_FACTURA.get(concepto, "LEAD PRUEBA"),
        "DESCRIPCION": descripcion,
        "GENERAR FACTURA": True,
    }
    if pago_rid:
        campos["PAGO"] = [pago_rid]
    if tutor_id:
        campos["TUTOR"] = [tutor_id]
    if familia_id:
        campos["FAMILIA FENIX"] = [familia_id]
    record = await _post(_FACTURAS, campos)
    if record:
        logger.info(f"[FACTURA] Creada factura {record.get('id')} (pago {pago_rid}, tutor {tutor_id or '—'}, familia {familia_id})")
        return record.get("id")
    logger.error(f"[FACTURA] No se pudo crear la factura (pago {pago_rid}, familia {familia_id})")
    return None


async def _tutor_fiscal(telefono: str, familia_id: str = "") -> dict | None:
    """Registro CRUDO del tutor que pide la factura (niño-eje).

    Primero el tutor del teléfono que escribe (es quien pide la factura);
    fallback: el pagador de la familia (ES QUIEN PAGA → con CI → primero)."""
    from agent.airtable_client import buscar_tutor_por_telefono
    tutor = await buscar_tutor_por_telefono(telefono) if telefono else None
    if tutor:
        return tutor
    if not familia_id:
        return None
    try:
        from agent.airtable_client import obtener_tutores_de_familia
        tutores = [t for t in await obtener_tutores_de_familia(familia_id) if t.get("id")]
        _t = (next((t for t in tutores if t.get("es_quien_paga")), None)
              or next((t for t in tutores if (t.get("ci") or "").strip()), None)
              or (tutores[0] if tutores else None))
        if _t:
            recs = await _get_records(_TUTORES, formula=f"RECORD_ID()='{_t['id']}'", max_records=1)
            return recs[0] if recs else None
    except Exception as e:
        logger.error(f"[FACTURA] Error buscando tutor fiscal de {familia_id}: {e}")
    return None


async def _asegurar_datos_fiscales(telefono: str, familia_id: str) -> str:
    """Asegura los datos fiscales en TUTORES FENIX.FACTURA (niño-eje).

    El robot facturador lee el lookup TUTOR RUC (= campo FACTURA del tutor).
    Si el tutor no lo tiene: se arma con su CI + nombre, o se hereda el
    FAMILIAS.FACTURA legacy. Retorna el tutor_id listo para linkear, o ""
    si no hay datos resolubles (el caller pide RUC/CI por chat)."""
    tutor = await _tutor_fiscal(telefono, familia_id)
    if not tutor:
        return ""
    tf = tutor.get("fields", {}) or {}
    if (tf.get("FACTURA") or "").strip():
        return tutor["id"]
    # Armar con el CI del tutor
    ci = str(tf.get("CI") or "").strip()
    nombre = " ".join(x for x in ((tf.get("NOMBRE") or "").strip(),
                                  (tf.get("APELLIDO") or "").strip()) if x)
    datos = f"CI {ci}" + (f" - {nombre}" if nombre else "") if ci else ""
    # Fallback legacy: heredar el FACTURA de la familia (texto libre ya validado)
    if not datos and familia_id:
        recs = await _get_records(_FAMILIAS, formula=f"RECORD_ID()='{familia_id}'", max_records=1)
        if recs:
            datos = (recs[0].get("fields", {}).get("FACTURA") or "").strip()
    if not datos:
        return ""
    await _patch(_TUTORES, tutor["id"], {"FACTURA": datos})
    logger.info(f"[FACTURA] FACTURA del tutor {tutor['id']} completado: '{datos}'")
    return tutor["id"]


async def _limpiar_flags_factura(telefono: str):
    await actualizar_estado_flags(
        telefono, pago_esperando_factura=False, factura_esperando_datos=False)


async def manejar_respuesta_factura(
    telefono: str, texto: str, btn_id: str | None, flags: dict, proveedor,
) -> str | None:
    """Atiende la respuesta a "🧾 ¿Necesitás factura?".

    Devuelve el texto respondido si interceptó el turno, o None para que el
    mensaje siga su flujo normal. OJO: acá NO se re-pregunta en ambiguo como
    hace Dorita — en Fenix el flag convive con el flujo de agenda post-pago
    ("¿qué sábado venís?"), así que solo interceptamos señales CLARAS de
    factura: los botones, la palabra "factura", datos de RUC/CI, o cualquier
    texto cuando estamos explícitamente esperando los datos fiscales.
    """
    esperando_datos = bool(flags.get("factura_esperando_datos"))
    esperando_factura = bool(flags.get("pago_esperando_factura"))
    if not (esperando_datos or esperando_factura):
        return None

    pago_rid = flags.get("factura_pago_rid", "") or ""
    familia_id = flags.get("factura_familia_id", "") or ""
    monto = int(flags.get("factura_monto", 0) or 0)
    concepto = flags.get("factura_concepto", "PRUEBA") or "PRUEBA"
    t = (texto or "").lower().strip()

    _menciona_factura = "factura" in t
    _pide_datos = any(k in t for k in _KEYWORDS_DATOS)
    _negativo = (btn_id == "factura_no"
                 or t in ("no", "nah", "nop", "no gracias", "no quiero", "sin factura")
                 or (t.startswith("no ") and _menciona_factura))

    resp: str | None = None

    if _negativo and (btn_id == "factura_no" or esperando_datos or _menciona_factura):
        # Sin factura → el pago YA está cargado, no hay nada más que hacer
        await _limpiar_flags_factura(telefono)
        resp = "Perfecto, sin factura entonces 😊 ¡Gracias!"

    elif esperando_datos or _pide_datos:
        # Validar que el texto REALMENTE parezca un dato fiscal antes de
        # guardarlo: con el flag activo, "el sábado 11 a las 15:30" o
        # "[imagen]" se guardaban literales como RUC y el robot emitía con
        # basura (auditoría 04-07-26 M7). Documento = 5+ dígitos seguidos
        # (tolerando puntos/guiones).
        import re as _re
        _m = _re.search(r"\d(?:[.\-]?\d)+", texto or "")
        _tiene_doc = bool(_m and len(_re.sub(r"\D", "", _m.group())) >= 5)
        if t.startswith("["):
            # Mandó una imagen (probablemente la cédula) → pedir el número por texto
            resp = "Para la factura pasame el RUC o CI por escrito porfa 🙏 (ej: 1234567 - Juan Pérez)"
        elif _tiene_doc:
            # Datos fiscales válidos → guardar LITERAL en el TUTOR (niño-eje:
            # el lookup TUTOR RUC lo expone en la factura) y crear el registro.
            # Sin tutor resoluble, cae al FAMILIAS.FACTURA legacy.
            _tutor_doc = await _tutor_fiscal(telefono, familia_id)
            _tutor_doc_id = _tutor_doc["id"] if _tutor_doc else ""
            if _tutor_doc_id:
                await _patch(_TUTORES, _tutor_doc_id, {"FACTURA": texto.strip()})
                logger.info(f"[FACTURA] Datos fiscales guardados en tutor {_tutor_doc_id}: '{texto.strip()}'")
            elif familia_id:
                await _patch(_FAMILIAS, familia_id, {"FACTURA": texto.strip()})
                logger.info(f"[FACTURA] Datos fiscales guardados para familia {familia_id} (legacy): '{texto.strip()}'")
            _rid = await crear_factura_fenix(pago_rid, familia_id, monto, concepto, tutor_id=_tutor_doc_id)
            await _limpiar_flags_factura(telefono)
            resp = ("Perfecto, te preparo la factura con esos datos 😊 Te la envío en breve."
                    if _rid else "Anotado 😊 Le paso al profe Iván para que te emita la factura.")
        elif _pide_datos or _menciona_factura:
            # Habló de factura pero sin número → pedirlo explícito
            await actualizar_estado_flags(telefono, factura_esperando_datos=True)
            resp = "Genial 😊 Pasame RUC o CI (el número) y el nombre para la factura 🙏"
        else:
            # No parece dato fiscal (p.ej. está respondiendo el flujo de agenda)
            # → dejar pasar al flujo normal; el flag queda esperando.
            return None

    elif btn_id == "factura_si" or _menciona_factura:
        # Quiere factura. Dorita no pide RUC porque el alumno ya tiene CI en su
        # ficha; acá el tutor a prueba suele no tenerlo → pedirlo si falta.
        _tutor_fid = await _asegurar_datos_fiscales(telefono, familia_id)
        if _tutor_fid:
            _rid = await crear_factura_fenix(pago_rid, familia_id, monto, concepto, tutor_id=_tutor_fid)
            await _limpiar_flags_factura(telefono)
            resp = ("¡Listo! Te envío tu factura en breve 😊"
                    if _rid else "Anotado 😊 Le paso al profe Iván para que te emita la factura.")
        else:
            await actualizar_estado_flags(telefono, factura_esperando_datos=True)
            resp = "Genial 😊 Pasame RUC o CI y el nombre para la factura 🙏"

    if resp is not None:
        await proveedor.enviar_mensaje(telefono, resp)
        return resp
    return None
