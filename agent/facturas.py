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

Etapa 2 (09/08/2026): los datos fiscales viven en la fila del tutor en
ALUMNOS (campo FACTURA FENIX, texto libre con RUC/CI + nombre) y la factura
linkea TUTOR (ALUMNOS) → el robot lee el lookup TUTOR RUC (ALUMNOS).
TUTORES FENIX quedó legacy y este flujo ya no lo toca.
"""

import logging

from agent.ab_test import actualizar_estado_flags
from agent.airtable_client import _patch, _post, _ALUMNOS, _FACTURAS

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
    pago_rid: str, monto: int, concepto: str = "PRUEBA",
    tutor_id: str = "",
) -> str | None:
    """Crea el registro en FACTURAS para que el robot facturador lo emita.
    NO toca el PAGO. tutor_id es una fila de ALUMNOS → linkea TUTOR (ALUMNOS);
    el robot lee el lookup TUTOR RUC (ALUMNOS). Retorna el record_id o None."""
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
        campos["TUTOR (ALUMNOS)"] = [tutor_id]
    record = await _post(_FACTURAS, campos)
    if record:
        logger.info(f"[FACTURA] Creada factura {record.get('id')} (pago {pago_rid}, tutor {tutor_id or '—'})")
        return record.get("id")
    logger.error(f"[FACTURA] No se pudo crear la factura (pago {pago_rid})")
    return None


async def _tutor_fiscal(telefono: str) -> dict | None:
    """La fila de ALUMNOS del tutor pagador — ahí viven FACTURA FENIX (texto
    fiscal) y el link FACTURAS.TUTOR (ALUMNOS) que lee el robot facturador.
    Etapa 2: se acabaron los stubs en TUTORES (duplicaban personas)."""
    if not telefono:
        return None
    from agent.airtable_client import buscar_tutor_por_telefono
    return await buscar_tutor_por_telefono(telefono)


async def _asegurar_datos_fiscales(telefono: str) -> str:
    """Asegura los datos fiscales en ALUMNOS.FACTURA FENIX (niño-eje).

    El robot facturador lee el lookup TUTOR RUC (ALUMNOS) (= campo FACTURA
    FENIX del tutor). Si el tutor no lo tiene, se arma con su CI + nombre.
    Retorna el tutor_id listo para linkear, o "" si no hay datos resolubles
    (el caller pide RUC/CI por chat)."""
    tutor = await _tutor_fiscal(telefono)
    if not tutor:
        return ""
    tf = tutor.get("fields", {}) or {}
    if (tf.get("FACTURA FENIX") or "").strip():
        return tutor["id"]
    # Armar con el CI del tutor
    ci = str(tf.get("CI") or "").strip()
    nombre = " ".join(x for x in ((tf.get("NOMBRE") or "").strip(),
                                  (tf.get("APELLIDO") or "").strip()) if x)
    datos = f"CI {ci}" + (f" - {nombre}" if nombre else "") if ci else ""
    if not datos:
        return ""
    await _patch(_ALUMNOS, tutor["id"], {"FACTURA FENIX": datos})
    logger.info(f"[FACTURA] FACTURA FENIX del tutor {tutor['id']} completado: '{datos}'")
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
            _tutor_doc = await _tutor_fiscal(telefono)
            _tutor_doc_id = _tutor_doc["id"] if _tutor_doc else ""
            if _tutor_doc_id:
                await _patch(_ALUMNOS, _tutor_doc_id, {"FACTURA FENIX": texto.strip()})
                logger.info(f"[FACTURA] Datos fiscales guardados en tutor {_tutor_doc_id}: '{texto.strip()}'")
            _rid = await crear_factura_fenix(pago_rid, monto, concepto, tutor_id=_tutor_doc_id)
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
        _tutor_fid = await _asegurar_datos_fiscales(telefono)
        if _tutor_fid:
            _rid = await crear_factura_fenix(pago_rid, monto, concepto, tutor_id=_tutor_fid)
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
