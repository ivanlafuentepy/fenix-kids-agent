# agent/facturas.py — Flujo de factura post-pago (espejo del de Dorita)
# FENIX KIDS ACADEMY

"""
Tras un pago confirmado, Aurora pregunta "🧾 ¿Necesitás factura?". Si la familia
quiere, se crea el registro en la tabla FACTURAS de la base madre — SIN marcar
FACTURA=True en el PAGO (decisión de Iván 03/07/2026: así la automatización de
Airtable que existe para Salsa no se dispara y no hay duplicados).

El robot facturador (otra máquina) emite el PDF en eKuatia/Marangatú y lo sube
a FACTURA PDF + FACTURADO + COMPROBANTE SET; `_envio_facturas_fenix_loop`
(loops.py) se lo hace llegar a la familia por WhatsApp.

Los datos fiscales de la familia viven en FAMILIAS FENIX → campo FACTURA
(texto libre con RUC/CI + nombre): el lookup FLIA FENIX RUC de FACTURAS lo lee.
"""

import logging

from agent.ab_test import actualizar_estado_flags
from agent.airtable_client import _get_records, _patch, _post, _FAMILIAS, _FACTURAS

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
) -> str | None:
    """Crea el registro en FACTURAS para que el robot facturador lo emita.
    NO toca el PAGO. Retorna el record_id de la factura o None."""
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
    if familia_id:
        campos["FAMILIA FENIX"] = [familia_id]
    record = await _post(_FACTURAS, campos)
    if record:
        logger.info(f"[FACTURA] Creada factura {record.get('id')} (pago {pago_rid}, familia {familia_id})")
        return record.get("id")
    logger.error(f"[FACTURA] No se pudo crear la factura (pago {pago_rid}, familia {familia_id})")
    return None


async def _asegurar_datos_fiscales(familia_id: str) -> bool:
    """True si la familia queda con datos para facturar en FAMILIAS FENIX.FACTURA.

    El robot facturador lee SOLO el lookup FLIA FENIX RUC (= campo FACTURA de la
    familia). Si FACTURA está vacío pero hay CI PADRE, se escribe FACTURA con el
    CI + nombre — así la factura nunca queda invisible para el robot."""
    if not familia_id:
        return False
    recs = await _get_records(_FAMILIAS, formula=f"RECORD_ID()='{familia_id}'", max_records=1)
    if not recs:
        return False
    f = recs[0].get("fields", {})
    if (f.get("FACTURA") or "").strip():
        return True
    # CI del padre, con fallback a CI MADRE y a TUTORES FENIX (EJE B): antes
    # solo miraba CI PADRE y las familias donde paga la madre o las migradas
    # a tutores quedaban "invisibles" para el robot (auditoría 04-07-26 M8).
    ci = (f.get("CI PADRE") or "").strip()
    nombre = " ".join(x for x in ((f.get("NOMBRE PADRE") or "").strip(),
                                  (f.get("APELLIDO PADRE") or "").strip()) if x)
    if not ci:
        ci = (f.get("CI MADRE") or "").strip()
        nombre = " ".join(x for x in ((f.get("NOMBRE MADRE") or "").strip(),
                                      (f.get("APELLIDO MADRE") or "").strip()) if x)
    if not ci:
        try:
            from agent.airtable_client import obtener_tutores_de_familia
            tutores = await obtener_tutores_de_familia(familia_id)
            _con_ci = [t for t in tutores if (t.get("ci") or "").strip()]
            _t = next((t for t in _con_ci if t.get("es_quien_paga")), None) or (_con_ci[0] if _con_ci else None)
            if _t:
                ci = str(_t["ci"]).strip()
                nombre = " ".join(x for x in ((_t.get("nombre") or "").strip(),
                                              (_t.get("apellido") or "").strip()) if x)
        except Exception as e:
            logger.error(f"[FACTURA] Error buscando CI en TUTORES para {familia_id}: {e}")
    if not ci:
        return False
    datos = f"CI {ci}" + (f" - {nombre}" if nombre else "")
    await _patch(_FAMILIAS, familia_id, {"FACTURA": datos})
    logger.info(f"[FACTURA] FACTURA de familia {familia_id} completado con CI: '{datos}'")
    return True


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
            # Datos fiscales válidos → guardar LITERAL en FAMILIAS FENIX.FACTURA
            # (el lookup FLIA FENIX RUC lo expone en la factura) y crear el registro.
            if familia_id:
                await _patch(_FAMILIAS, familia_id, {"FACTURA": texto.strip()})
                logger.info(f"[FACTURA] Datos fiscales guardados para familia {familia_id}: '{texto.strip()}'")
            _rid = await crear_factura_fenix(pago_rid, familia_id, monto, concepto)
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
        # ficha; acá la familia a prueba suele no tenerlo → pedirlo si falta.
        if await _asegurar_datos_fiscales(familia_id):
            _rid = await crear_factura_fenix(pago_rid, familia_id, monto, concepto)
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
