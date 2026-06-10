# agent/fotos.py — Modo fotos + reconocimiento facial + botones seguimiento
# Extraído de main.py (refactor paso 6)

import os
import re
import logging

from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()

# ── Estado global de fotos ──

# Estado de sesión de fotos (reconocimiento facial):
# {telefono: {"turno": "9:30", "media_ids": [...], "resultados": [...]}}
_fotos_sesion: dict[str, dict] = {}

# Estado de registro de cara pendiente: {telefono: "nombre del niño"}
_cara_pendiente: dict[str, str] = {}
# Candidatos múltiples para registrar cara: {telefono: [{"id":..., "nombre_completo":..., "es_prueba":...}, ...]}
_cara_candidatos: dict[str, list[dict]] = {}
# Record preseleccionado por número: {telefono: {"id":..., "nombre_completo":..., "es_prueba":...}}
_cara_record_preseleccionado: dict[str, dict] = {}
# Media ID pendiente cuando se envió foto+nombre pero hubo múltiples matches
_cara_media_pendiente: dict[str, str] = {}


# ════════════════════════════════════════════════════════════════════════════════
# MODO FOTOS — Reconocimiento facial de niños en fotos de clase
# ════════════════════════════════════════════════════════════════════════════════


async def _iniciar_modo_fotos(telefono: str, texto: str):
    """
    Inicia una sesión de fotos para reconocimiento facial.
    Detecta: "fotos 9:30", "fotos 11", "fotos 15:30", "fotos clase"
    """
    # Extraer turno del texto
    turno = ""
    m = re.search(r'(\d{1,2}[:.]\d{2}|\d{1,2})', texto)
    if m:
        turno = m.group(1).replace(".", ":")
        if turno in ("9", "930"):
            turno = "9:30"
        elif turno in ("11", "1100"):
            turno = "11:00"
        elif turno in ("15", "1530"):
            turno = "15:30"

    _fotos_sesion[telefono] = {
        "turno": turno,
        "media_ids": [],
        "resultados": {},  # {nino_id: {"nombre": str, "fotos": int}}
        "no_identificadas": 0,
        "total_fotos": 0,
    }

    msg_inicio = f"📸 Modo fotos activado"
    if turno:
        msg_inicio += f" para la clase de {turno}"
    msg_inicio += ".\n\nMandá las fotos y cuando termines escribí *listo*."

    await proveedor.enviar_mensaje(telefono, msg_inicio)
    logger.info(f"[FOTOS] Sesión iniciada para {telefono}, turno={turno or 'sin especificar'}")


async def _acumular_foto(telefono: str, media_id: str):
    """
    Recibe una foto durante el modo fotos, la descarga y busca caras.
    """
    sesion = _fotos_sesion.get(telefono)
    if not sesion:
        return

    sesion["media_ids"].append(media_id)
    sesion["total_fotos"] += 1
    foto_num = sesion["total_fotos"]

    # Descargar imagen
    image_bytes = await proveedor.descargar_media(media_id)
    if not image_bytes:
        logger.warning(f"[FOTOS] No se pudo descargar media {media_id}")
        return

    # Buscar caras con Rekognition
    try:
        from agent.face_recognition import identificar_ninos
        matches = await identificar_ninos(image_bytes)

        if matches:
            for match in matches:
                nino_id = match["nino_id"]
                if nino_id not in sesion["resultados"]:
                    # Obtener nombre del niño
                    from agent.airtable_client import obtener_nombre_nino
                    nino_info = await obtener_nombre_nino(nino_id)
                    nombre = ""
                    if nino_info:
                        nombre = nino_info.get("apodo") or nino_info.get("nombre", "")
                        apellido = nino_info.get("apellido", "")
                        if apellido:
                            nombre = f"{nombre} {apellido}"
                    sesion["resultados"][nino_id] = {"nombre": nombre or nino_id, "fotos": 0}
                sesion["resultados"][nino_id]["fotos"] += 1
        else:
            sesion["no_identificadas"] += 1

        # Feedback breve cada 5 fotos
        if foto_num % 5 == 0:
            n_ninos = len(sesion["resultados"])
            await proveedor.enviar_mensaje(telefono, f"📸 {foto_num} fotos recibidas, {n_ninos} niño(s) identificados...")

    except Exception as e:
        logger.error(f"[FOTOS] Error procesando foto {foto_num}: {e}")
        sesion["no_identificadas"] += 1


async def _finalizar_fotos(telefono: str):
    """
    Cierra la sesión de fotos y muestra el resumen de niños identificados.
    """
    sesion = _fotos_sesion.pop(telefono, None)
    if not sesion:
        return

    total = sesion["total_fotos"]
    resultados = sesion["resultados"]
    no_id = sesion["no_identificadas"]

    if total == 0:
        await proveedor.enviar_mensaje(telefono, "No recibí fotos. Modo fotos desactivado.")
        return

    # Armar resumen
    lineas = [f"📸 *Resumen: {total} fotos procesadas*\n"]

    if resultados:
        # Ordenar por cantidad de fotos (más apariciones primero)
        ordenados = sorted(resultados.items(), key=lambda x: x[1]["fotos"], reverse=True)
        lineas.append(f"✅ *{len(resultados)} niño(s) identificados:*")
        for i, (nino_id, data) in enumerate(ordenados, 1):
            lineas.append(f"  {i}. {data['nombre']} ({data['fotos']} foto{'s' if data['fotos'] > 1 else ''})")

    if no_id > 0:
        lineas.append(f"\n⚠️ {no_id} foto(s) sin cara identificada")

    lineas.append("\n¿Confirmo y vinculo en Airtable? (si/no)")

    await proveedor.enviar_mensaje(telefono, "\n".join(lineas))

    # Guardar sesión temporalmente para la confirmación
    _fotos_sesion[telefono] = {
        **sesion,
        "_esperando_confirmacion": True,
    }

    logger.info(f"[FOTOS] Sesión finalizada: {total} fotos, {len(resultados)} niños, {no_id} sin ID")


async def _confirmar_fotos(telefono: str):
    """
    Confirma la sesión de fotos y crea registros en CONTENIDO FENIX.
    """
    sesion = _fotos_sesion.pop(telefono, None)
    if not sesion:
        return

    resultados = sesion.get("resultados", {})
    turno = sesion.get("turno", "")

    if not resultados:
        await proveedor.enviar_mensaje(telefono, "No hay niños para vincular.")
        return

    # Crear registro en CONTENIDO FENIX con los niños vinculados
    from agent.airtable_client import _post, _CONTENIDO
    from datetime import datetime

    nino_ids = list(resultados.keys())
    titulo = f"Fotos clase {turno}" if turno else "Fotos de clase"
    titulo += f" — {datetime.now().strftime('%d/%m/%Y')}"

    campos = {
        "TITULO": titulo,
        "NIÑOS FENIX": nino_ids,
        "NOTIFICADO": False,
    }

    registro = await _post(_CONTENIDO, campos)
    if registro:
        nombres = [data["nombre"] for data in resultados.values()]
        await proveedor.enviar_mensaje(
            telefono,
            f"✅ Listo! Registro creado en CONTENIDO FENIX con {len(nino_ids)} niño(s): {', '.join(nombres)}\n\n"
            f"Cuando publiques el posteo, agregá el LINK al registro de Airtable y los padres recibirán WhatsApp automático."
        )
        logger.info(f"[FOTOS] CONTENIDO FENIX creado: {titulo}, {len(nino_ids)} niños")
    else:
        await proveedor.enviar_mensaje(telefono, "❌ Error creando registro en Airtable. Revisá los logs.")


async def _procesar_registro_cara(telefono: str, media_id: str):
    """
    Registra la cara de un niño en Rekognition.
    Busca al niño por nombre/apodo en NIÑOS FENIX de Airtable.
    """
    nombre_buscar = _cara_pendiente.pop(telefono, "")
    if not nombre_buscar:
        return

    # Descargar imagen
    image_bytes = await proveedor.descargar_media(media_id)
    if not image_bytes:
        await proveedor.enviar_mensaje(telefono, "❌ No pude descargar la foto")
        return

    from agent.airtable_client import _get_records, _NINOS, _PRUEBAS, _patch

    # Si hay record preseleccionado (eligió de la lista numerada), usarlo directo
    _presel = _cara_record_preseleccionado.pop(telefono, None)
    if _presel:
        _es_prueba = _presel["es_prueba"]
        _tabla = _PRUEBAS if _es_prueba else _NINOS
        _rec = await _get_records(_tabla, formula=f"RECORD_ID()='{_presel['id']}'", max_records=1)
        if _rec:
            records = _rec
        else:
            await proveedor.enviar_mensaje(telefono, f"❌ No encontré el registro preseleccionado")
            return
    else:
        # Buscar niño en Airtable por nombre/apodo (NIÑOS FENIX + PRUEBA FENIX)
        import unicodedata
        nombre_norm = nombre_buscar.lower().strip()
        # Variante sin acentos para búsqueda tolerante
        nombre_sin_acento = ''.join(
            c for c in unicodedata.normalize('NFD', nombre_norm)
            if unicodedata.category(c) != 'Mn'
        )
        # Variante con acentos comunes (cesar→césar, etc.)
        _acento_map = {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú'}
        _variantes_acento = set()
        for i, c in enumerate(nombre_sin_acento):
            if c in _acento_map:
                _variantes_acento.add(nombre_sin_acento[:i] + _acento_map[c] + nombre_sin_acento[i+1:])

        # Construir búsqueda: nombre exacto + sin acento + variantes con acento
        _buscar_nombres = [nombre_norm]
        if nombre_sin_acento != nombre_norm:
            _buscar_nombres.append(nombre_sin_acento)
        _buscar_nombres.extend(_variantes_acento)
        # Eliminar duplicados manteniendo orden
        _buscar_nombres = list(dict.fromkeys(_buscar_nombres))

        # Buscar en AMBAS tablas siempre (NIÑOS + PRUEBA) y juntar resultados
        # Si hay múltiples palabras ("max lee"), buscar registros que contengan TODAS
        _palabras = nombre_norm.split()
        if len(_palabras) > 1:
            # Multi-palabra: AND de cada palabra en NOMBRE/APODO (o NOMBRE HIJO/APELLIDO HIJO)
            _and_ninos = [f"OR(FIND('{p}', LOWER({{NOMBRE}})), FIND('{p}', LOWER({{APODO}})), FIND('{p}', LOWER({{APELLIDO}})))" for p in _palabras]
            _formula_ninos = f"AND({','.join(_and_ninos)})"
            _and_prueba = [f"OR(FIND('{p}', LOWER({{NOMBRE HIJO}})), FIND('{p}', LOWER({{APELLIDO HIJO}})))" for p in _palabras]
            _formula_prueba = f"AND({','.join(_and_prueba)})"
        else:
            # Una palabra: OR de variantes con/sin acentos
            _or_parts_ninos = []
            for _bn in _buscar_nombres:
                _or_parts_ninos.append(f"FIND('{_bn}', LOWER({{APODO}}))")
                _or_parts_ninos.append(f"FIND('{_bn}', LOWER({{NOMBRE}}))")
                _or_parts_ninos.append(f"FIND('{_bn}', LOWER({{APELLIDO}}))")
            _formula_ninos = f"OR({','.join(_or_parts_ninos)})"
            _or_parts_prueba = []
            for _bn in _buscar_nombres:
                _or_parts_prueba.append(f"FIND('{_bn}', LOWER({{NOMBRE HIJO}}))")
                _or_parts_prueba.append(f"FIND('{_bn}', LOWER({{APELLIDO HIJO}}))")
            _formula_prueba = f"OR({','.join(_or_parts_prueba)})"

        _records_ninos = await _get_records(_NINOS, formula=_formula_ninos, max_records=5)
        _records_prueba = await _get_records(_PRUEBAS, formula=_formula_prueba, max_records=5)

        # Juntar resultados marcando origen
        records = []
        _es_prueba = False
        # Agregar records de NIÑOS (no son prueba)
        for _r in _records_ninos:
            _r["_es_prueba"] = False
            records.append(_r)
        # Agregar records de PRUEBA
        for _r in _records_prueba:
            _r["_es_prueba"] = True
            records.append(_r)
        # Si todos son de prueba, marcar flag
        if records and all(r.get("_es_prueba") for r in records):
            _es_prueba = True

        if not records:
            await proveedor.enviar_mensaje(telefono, f"❌ No encontré a '{nombre_buscar}' en NIÑOS ni PRUEBA FENIX")
            return

    if len(records) > 1:
        # Múltiples matches — mostrar lista numerada y esperar selección
        opciones = []
        candidatos_lista = []
        for r in records:
            f = r.get("fields", {})
            _r_es_prueba = r.get("_es_prueba", _es_prueba)
            if _r_es_prueba:
                nombre_c = f"{f.get('NOMBRE HIJO', '')} {f.get('APELLIDO HIJO', '')}".strip()
                opciones.append(f"{nombre_c} 🔥")
            else:
                nombre_c = f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip()
                apodo = f.get('APODO', '')
                opciones.append(f"{nombre_c} ({apodo})" if apodo else nombre_c)
            candidatos_lista.append({"id": r["id"], "nombre_completo": nombre_c, "es_prueba": _r_es_prueba})
        _cara_candidatos[telefono] = candidatos_lista
        await proveedor.enviar_mensaje(
            telefono,
            f"Encontré {len(records)} niños:\n" + "\n".join(f"  {i+1}. {o}" for i, o in enumerate(opciones)) +
            "\n\nResponde con el número para seleccionar."
        )
        return

    # Un solo match — registrar cara
    nino_record = records[0]
    nino_id = nino_record["id"]
    fields = nino_record.get("fields", {})
    _es_prueba = nino_record.get("_es_prueba", _es_prueba)

    if _es_prueba:
        nombre_display = fields.get("NOMBRE HIJO", "")
        tabla_destino = _PRUEBAS
    else:
        nombre_display = fields.get("APODO") or fields.get("NOMBRE", "")
        tabla_destino = _NINOS

    from agent.face_recognition import registrar_cara, actualizar_cara

    # Si ya tiene FACE_ID, actualizar
    face_id_existente = fields.get("FACE_ID", "")
    if face_id_existente:
        face_id = await actualizar_cara(nino_id, image_bytes)
        accion = "actualizada"
    else:
        face_id = await registrar_cara(nino_id, image_bytes)
        accion = "registrada"

    if face_id:
        # Guardar FACE_ID en Airtable (NIÑOS o PRUEBA según corresponda)
        await _patch(tabla_destino, nino_id, {"FACE_ID": face_id})
        # Subir foto como attachment al campo FOTO
        from agent.airtable_client import subir_attachment_airtable
        _foto_ok = await subir_attachment_airtable(
            record_id=nino_id,
            field_name="FOTO",
            image_bytes=image_bytes,
            filename=f"{nombre_display.replace(' ', '_')}.jpg",
        )
        _label = "🔥 PRUEBA" if _es_prueba else "NIÑOS"
        _foto_msg = " + foto subida" if _foto_ok else " (foto no subió)"
        await proveedor.enviar_mensaje(telefono, f"✅ Cara {accion} para {nombre_display} [{_label}]{_foto_msg}")
    else:
        await proveedor.enviar_mensaje(telefono, f"❌ No se detectó una cara clara en la foto de {nombre_display}. Probá con otra foto.")


# ════════════════════════════════════════════════════════════════════════════════
# BOTONES SEGUIMIENTO — marca ENVIADO o DESCARTADO en SEGUIMIENTO FENIX
# ════════════════════════════════════════════════════════════════════════════════


async def _procesar_boton_seguimiento(btn_id: str):
    """Procesa click en botón de seguimiento: seg_enviado_recXXX o seg_descartado_recXXX."""
    from agent.airtable_client import _patch

    _SEGUIMIENTO = "SEGUIMIENTO FENIX"

    if btn_id.startswith("seg_enviado_"):
        record_id = btn_id[len("seg_enviado_"):]
        ok = await _patch(_SEGUIMIENTO, record_id, {"ENVIADO": True})
        if ok:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", ""), "✅ Marcado como enviado")
        else:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", ""), "❌ Error marcando en Airtable")

    elif btn_id.startswith("seg_descartado_"):
        record_id = btn_id[len("seg_descartado_"):]
        ok = await _patch(_SEGUIMIENTO, record_id, {"DESCARTADO": True})
        if ok:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", ""), "❌ Marcado como descartado")
        else:
            await proveedor.enviar_mensaje(os.getenv("ADMIN_PHONE", ""), "❌ Error marcando en Airtable")
