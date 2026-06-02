# agent/inscripcion.py — Flujo de inscripción de familia (extraído de main.py)
# Paso 5 del refactor del monolito

import re
import logging

from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit")
proveedor = obtener_proveedor()

# Estado de inscripción pendiente: {telefono_admin: {datos de prueba fenix...}}
_inscripcion_pendiente: dict[str, dict] = {}


_METODO_MAP = {
    "SUB": "SUSCRIPCION", "SUSCRIPCION": "SUSCRIPCION", "SUSCRI": "SUSCRIPCION",
    "TRANS": "TRANSFER", "TRANSFER": "TRANSFER", "TRANSFERENCIA": "TRANSFER",
    "DEB": "DEB", "DEBITO": "DEB",
    "CRED": "CRED", "CREDITO": "CRED",
    "EFE": "EFECTIVO", "EFECTIVO": "EFECTIVO", "CASH": "EFECTIVO",
}


def _parsear_inscripcion(texto: str) -> dict:
    """
    Parsea texto libre de inscripción. Extrae plan, método, monto, matrícula.
    Acepta cualquier orden, con o sin keywords explícitos.
    Retorna dict con las claves encontradas (puede estar incompleto).
    """
    t = texto.lower().replace(",", " ").replace(".", " ")

    result = {}

    # ── Plan: detectar por keywords naturales ──
    # trimestral full/todos/semanal/4 = ST
    # trimestral dos/quincenal/2 = QT
    # mensual full/todos/semanal/4 = SM
    # mensual dos/quincenal/2 = QM
    # También acepta códigos: QM, SM, QT, ST
    if re.search(r'\b(st)\b', t):
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'\b(qt)\b', t):
        result["plan"] = "QUINCENAL TRIMESTRAL"
    elif re.search(r'\b(sm)\b', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\b(qm)\b', t):
        result["plan"] = "QUINCENAL MENSUAL"
    # Primero buscar "dos/quincenal" (más específico), después "full/todos"
    elif re.search(r'trimestral.{0,15}\b(dos|quincenal)\b', t):
        result["plan"] = "QUINCENAL TRIMESTRAL"
    elif re.search(r'\b(dos|quincenal)\b.{0,15}trimestral', t):
        result["plan"] = "QUINCENAL TRIMESTRAL"
    elif re.search(r'trimestral.{0,15}\b(full|todos|todas|completo|semanal)\b', t):
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'\b(full|todos|todas|completo|semanal)\b.{0,15}trimestral', t):
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'\btrimestral\b', t):
        # Solo "trimestral" sin calificador → asumir full (el más común)
        result["plan"] = "SEMANAL TRIMESTRAL"
    elif re.search(r'mensual.{0,15}\b(dos|quincenal)\b', t):
        result["plan"] = "QUINCENAL MENSUAL"
    elif re.search(r'\b(dos|quincenal)\b.{0,15}mensual', t):
        result["plan"] = "QUINCENAL MENSUAL"
    elif re.search(r'mensual.{0,15}\b(full|todos|todas|completo|semanal)\b', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\b(full|todos|todas|completo|semanal)\b.{0,15}mensual', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\bmensual\b', t):
        result["plan"] = "SEMANAL MENSUAL"
    elif re.search(r'\btrimestral\b', t):
        # Solo "trimestral" sin más → pedir aclaración
        pass
    elif re.search(r'\bmensual\b', t):
        pass

    # ── Método de pago ──
    for keyword, metodo in _METODO_MAP.items():
        if keyword.lower() in t:
            result["metodo"] = metodo
            break

    # ── Monto y matrícula: buscar "monto X" y "matricula X" ──
    m_monto = re.search(r'monto\s+(\d+)', t)
    if m_monto:
        result["monto"] = int(m_monto.group(1))

    m_matri = re.search(r'matri(?:cula)?\s+(\d+)', t)
    if m_matri:
        result["matricula"] = int(m_matri.group(1))

    # Si no encontró con keyword, buscar números sueltos y asignar por contexto
    if "monto" not in result or "matricula" not in result:
        nums = re.findall(r'\b(\d{2,4})\b', t)
        # Filtrar números que ya se asignaron
        nums_int = [int(n) for n in nums]
        assigned = {result.get("monto"), result.get("matricula")}
        remaining = [n for n in nums_int if n not in assigned and n > 10]
        if remaining and "monto" not in result:
            result["monto"] = max(remaining)  # el más grande es el monto
            remaining.remove(result["monto"])
        if remaining and "matricula" not in result:
            result["matricula"] = remaining[0]

    # Normalizar montos a guaraníes (si < 10000, multiplicar por 1000)
    for key in ("monto", "matricula"):
        if key in result and result[key] < 10000:
            result[key] = result[key] * 1000

    return result


async def _iniciar_inscripcion(admin_phone: str, texto_completo: str):
    """
    Parsea texto libre: extrae nombre + datos de inscripción.
    Si tiene todo, ejecuta directo. Si falta algo, pide lo que falta.
    """
    from agent.airtable_client import _get_records, _PRUEBAS

    # Extraer datos del texto
    parsed = _parsear_inscripcion(texto_completo)

    # Buscar nombre: todo lo que no sea keyword de plan/método/monto
    _keywords = {
        "trimestral", "mensual", "full", "todos", "todas", "semanal", "quincenal",
        "dos", "completo", "monto", "matricula", "matri",
        "sub", "suscripcion", "suscri", "trans", "transfer", "transferencia",
        "deb", "debito", "cred", "credito", "efe", "efectivo", "cash",
        "qm", "sm", "qt", "st", "mil", "bi",
    }
    palabras = texto_completo.strip().split()
    nombre_parts = []
    for p in palabras:
        p_clean = re.sub(r'[,.:;!?]', '', p).lower()
        if p_clean in _keywords or p_clean.isdigit():
            break
        nombre_parts.append(p)
    nombre_buscar = " ".join(nombre_parts).strip()

    if not nombre_buscar:
        await proveedor.enviar_mensaje(admin_phone, "No entendí el nombre. Ej: cargar familia Diana Jara trimestral full monto 690 matricula 50")
        return

    # Buscar en PRUEBA FENIX — normalizar tildes para comparación
    import unicodedata
    def _sin_tildes(s: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()

    pruebas = await _get_records(_PRUEBAS, formula="", max_records=100)
    _nombre_norm = _sin_tildes(nombre_buscar)

    matches = []
    for p in pruebas:
        f = p.get("fields", {})
        nombre_completo = _sin_tildes(f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip())
        if _nombre_norm in nombre_completo or nombre_completo in _nombre_norm:
            matches.append(p)

    if not matches:
        for p in pruebas:
            f = p.get("fields", {})
            hijo_completo = _sin_tildes(f"{f.get('NOMBRE HIJO', '')} {f.get('APELLIDO HIJO', '')}".strip())
            if _nombre_norm in hijo_completo:
                matches.append(p)

    if not matches:
        await proveedor.enviar_mensaje(admin_phone, f"No encontré prueba para '{nombre_buscar}'")
        return

    if len(matches) > 1:
        # Dedup por teléfono (hermanos = mismo tel)
        _tels_vistos = set()
        matches_uniq = []
        for m in matches:
            _tel = m.get("fields", {}).get("TELEFONO", "")
            if _tel not in _tels_vistos:
                _tels_vistos.add(_tel)
                matches_uniq.append(m)
        if len(matches_uniq) > 1:
            msg = f"Encontré {len(matches_uniq)} familias:\n\n"
            for i, m in enumerate(matches_uniq, 1):
                f = m.get("fields", {})
                msg += f"{i}. {f.get('NOMBRE', '')} {f.get('APELLIDO', '')} → {f.get('NOMBRE HIJO', '')} ({f.get('TELEFONO', '')})\n"
            msg += "\nEscribí el número para elegir:"
            _inscripcion_pendiente[admin_phone] = {"step": "elegir", "matches": matches_uniq, "parsed": parsed}
            await proveedor.enviar_mensaje(admin_phone, msg)
            return
        matches = matches_uniq

    prueba = matches[0]
    tel = prueba.get("fields", {}).get("TELEFONO", "")

    # Buscar todas las pruebas de este teléfono (hermanos)
    todas_pruebas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{tel}'", max_records=10)

    # Si tenemos todo → ejecutar directo
    faltantes = []
    if "plan" not in parsed:
        faltantes.append("PLAN (ej: trimestral full, mensual dos, QT, SM...)")
    if "monto" not in parsed:
        faltantes.append("MONTO (en miles, ej: 690)")
    if "matricula" not in parsed:
        faltantes.append("MATRICULA (en miles, ej: 50)")

    if faltantes:
        # Mostrar lo que encontró y pedir lo que falta
        fp = prueba.get("fields", {})
        hijos_txt = ", ".join(
            f"{op.get('fields', {}).get('NOMBRE HIJO', '')} ({op.get('fields', {}).get('EDAD HIJO', '?')})"
            for op in todas_pruebas if op.get("fields", {}).get("NOMBRE HIJO")
        )
        msg = (
            f"📋 Encontré: {fp.get('NOMBRE', '')} {fp.get('APELLIDO', '')} ({tel})\n"
            f"👶 {hijos_txt}\n\n"
        )
        if parsed.get("plan"):
            msg += f"✅ Plan: {parsed['plan']}\n"
        if parsed.get("monto"):
            msg += f"✅ Monto: {parsed['monto'] // 1000}mil\n"
        if parsed.get("matricula"):
            msg += f"✅ Matrícula: {parsed['matricula'] // 1000}mil\n"
        if parsed.get("metodo"):
            msg += f"✅ Método: {parsed['metodo']}\n"
        msg += f"\nFalta:\n" + "\n".join(f"• {f}" for f in faltantes)
        msg += "\n\nCompletá lo que falta (texto libre):"

        _inscripcion_pendiente[admin_phone] = {
            "step": "completar",
            "prueba": prueba,
            "todas_pruebas": todas_pruebas,
            "parsed": parsed,
        }
        await proveedor.enviar_mensaje(admin_phone, msg)
        return

    # Todo completo → mostrar resumen y pedir confirmación
    metodo = parsed.get("metodo", "TRANSFER")
    await _mostrar_confirmacion(admin_phone, prueba, todas_pruebas, parsed, metodo)


async def _procesar_respuesta_inscripcion(admin_phone: str, texto: str):
    """Procesa respuestas pendientes de inscripción (elegir match o completar datos)."""
    datos = _inscripcion_pendiente.get(admin_phone)
    if not datos:
        return

    # Elegir entre múltiples matches
    if datos["step"] == "elegir":
        try:
            idx = int(texto.strip()) - 1
            matches = datos["matches"]
            parsed = datos.get("parsed", {})
            if 0 <= idx < len(matches):
                _inscripcion_pendiente.pop(admin_phone, None)
                prueba = matches[idx]
                tel = prueba.get("fields", {}).get("TELEFONO", "")
                from agent.airtable_client import _get_records, _PRUEBAS
                todas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{tel}'", max_records=10)
                # Re-iniciar con los datos parseados originales
                faltantes = []
                if "plan" not in parsed:
                    faltantes.append("PLAN")
                if "monto" not in parsed:
                    faltantes.append("MONTO")
                if "matricula" not in parsed:
                    faltantes.append("MATRICULA")
                if faltantes:
                    _inscripcion_pendiente[admin_phone] = {
                        "step": "completar",
                        "prueba": prueba,
                        "todas_pruebas": todas,
                        "parsed": parsed,
                    }
                    await proveedor.enviar_mensaje(admin_phone, f"Falta: {', '.join(faltantes)}\nCompletá (texto libre):")
                else:
                    metodo = parsed.get("metodo", "TRANSFER")
                    await _mostrar_confirmacion(admin_phone, prueba, todas, parsed, metodo)
            else:
                await proveedor.enviar_mensaje(admin_phone, f"Elegí entre 1 y {len(matches)}")
        except ValueError:
            _inscripcion_pendiente.pop(admin_phone, None)
            await proveedor.enviar_mensaje(admin_phone, "Cancelado.")
        return

    # Completar datos faltantes
    if datos["step"] == "completar":
        nuevos = _parsear_inscripcion(texto)
        parsed = datos["parsed"]
        # Merge: lo nuevo sobreescribe
        parsed.update(nuevos)
        datos["parsed"] = parsed

        faltantes = []
        if "plan" not in parsed:
            faltantes.append("PLAN (ej: trimestral full, mensual dos)")
        if "monto" not in parsed:
            faltantes.append("MONTO (en miles)")
        if "matricula" not in parsed:
            faltantes.append("MATRICULA (en miles)")

        if faltantes:
            msg = "Todavía falta:\n" + "\n".join(f"• {f}" for f in faltantes)
            await proveedor.enviar_mensaje(admin_phone, msg)
            return

        # Todo completo → pedir confirmación
        metodo = parsed.get("metodo", "TRANSFER")
        await _mostrar_confirmacion(admin_phone, datos["prueba"], datos["todas_pruebas"], parsed, metodo)
        return

    # Confirmar con si/no
    if datos["step"] == "confirmar":
        _r = texto.strip().lower().rstrip("!.,")
        if _r in ("si", "sí", "dale", "ok", "va", "confirmar", "listo", "yes"):
            _inscripcion_pendiente.pop(admin_phone, None)
            d = datos
            await _ejecutar_inscripcion(
                admin_phone, d["prueba"], d["todas_pruebas"],
                d["plan"], d["metodo"], d["monto"], d["matricula"]
            )
        elif _r in ("no", "cancelar", "cancel", "na"):
            _inscripcion_pendiente.pop(admin_phone, None)
            await proveedor.enviar_mensaje(admin_phone, "Cancelado ❌")
        else:
            await proveedor.enviar_mensaje(admin_phone, "Respondé *si* o *no*")
        return

    _inscripcion_pendiente.pop(admin_phone, None)


async def _mostrar_confirmacion(admin_phone: str, prueba: dict, todas_pruebas: list[dict], parsed: dict, metodo: str):
    """Muestra resumen y pide confirmación si/no."""
    fp = prueba.get("fields", {})
    tel = fp.get("TELEFONO", "")
    nombre_padre = f"{fp.get('NOMBRE', '')} {fp.get('APELLIDO', '')}".strip()
    hijos_txt = ", ".join(
        f"{op.get('fields', {}).get('NOMBRE HIJO', '')} ({op.get('fields', {}).get('EDAD HIJO', '?')})"
        for op in todas_pruebas if op.get("fields", {}).get("NOMBRE HIJO")
    )
    plan = parsed["plan"]
    monto = parsed["monto"]
    matricula = parsed["matricula"]

    msg = (
        f"📋 *CONFIRMAR INSCRIPCIÓN*\n\n"
        f"👨 {nombre_padre} ({tel})\n"
        f"👶 {hijos_txt}\n\n"
        f"📋 Plan: {plan}\n"
        f"💳 Método: {metodo}\n"
        f"💰 Monto plan: {monto // 1000}mil\n"
        f"💰 Matrícula: {matricula // 1000}mil\n\n"
        f"¿Confirmar? (si/no)"
    )

    _inscripcion_pendiente[admin_phone] = {
        "step": "confirmar",
        "prueba": prueba,
        "todas_pruebas": todas_pruebas,
        "plan": plan,
        "metodo": metodo,
        "monto": monto,
        "matricula": matricula,
    }
    await proveedor.enviar_mensaje(admin_phone, msg)


async def _ejecutar_inscripcion(
    admin_phone: str, prueba: dict, todas_pruebas: list[dict],
    plan: str, metodo: str, monto: int, matricula: int
):
    """Crea FAMILIA + NIÑOS + PAGOS + marca INSCRIPTO."""
    from agent.airtable_client import (
        _get_records, _post, _patch, _PRUEBAS, _LEADS, _FAMILIAS,
        crear_familia, crear_nino,
    )

    fp = prueba.get("fields", {})
    tel = fp.get("TELEFONO", "")
    nombre_padre = fp.get("NOMBRE", "")
    apellido_padre = fp.get("APELLIDO", "")

    # ── 1. Crear FAMILIA ──────────────────────────────────────────────
    familia_id = await crear_familia({
        "padre": {
            "nombre": nombre_padre,
            "apellido": apellido_padre,
            "telefono": tel,
        }
    })
    if not familia_id:
        await proveedor.enviar_mensaje(admin_phone, "Error creando familia en Airtable")
        return

    await _patch(_FAMILIAS, familia_id, {
        "PLAN": plan,
        "METODO PAGO": metodo,
        "ESTADO PLAN": "ACTIVO",
    })

    # ── 2. Crear NIÑO(S) ─────────────────────────────────────────────
    ninos_creados = []
    for op in todas_pruebas:
        of = op.get("fields", {})
        h_nombre = of.get("NOMBRE HIJO", "")
        h_apellido = of.get("APELLIDO HIJO", "")
        h_fn = of.get("FECHA NACIMIENTO", "")
        h_genero = of.get("GENERO", "")
        if h_nombre:
            nino_id = await crear_nino({
                "nombre": h_nombre,
                "apellido": h_apellido,
                "fecha_nacimiento": h_fn,
                "sexo": h_genero,
            }, familia_id)
            if nino_id:
                ninos_creados.append(f"{h_nombre} {h_apellido}")
                # Vincular PRUEBA FENIX → NIÑO FENIX
                try:
                    await _patch(_PRUEBAS, op["id"], {"NINO FENIX": [nino_id]})
                    logger.info(f"[INSCRIPCION] Vinculado PRUEBA {op['id']} → NIÑO {nino_id}")
                except Exception as e:
                    logger.warning(f"[INSCRIPCION] Error vinculando PRUEBA→NIÑO: {e}")
                # Migrar cara de PRUEBA FENIX → NIÑOS FENIX
                prueba_face_id = of.get("FACE_ID", "")
                prueba_foto = of.get("FOTO", [])
                if prueba_face_id:
                    try:
                        import httpx
                        from agent.face_recognition import actualizar_cara
                        from agent.airtable_client import _patch, _NINOS
                        # Re-indexar con el nuevo record_id del niño
                        if prueba_foto:
                            foto_bytes = None
                            async with httpx.AsyncClient(timeout=30) as _hc:
                                _r = await _hc.get(prueba_foto[0]["url"])
                                if _r.status_code == 200:
                                    foto_bytes = _r.content
                            if foto_bytes:
                                new_face_id = await actualizar_cara(nino_id, foto_bytes)
                                if new_face_id:
                                    await _patch(_NINOS, nino_id, {"FACE_ID": new_face_id})
                                    logger.info(f"[FOTOS] Cara migrada de PRUEBA→NIÑO: {h_nombre} {h_apellido}")
                    except Exception as e:
                        logger.warning(f"[FOTOS] Error migrando cara: {e}")

    # ── 3. Crear PAGOS ───────────────────────────────────────────────
    _pagos_tabla = "PAGOS"
    pagos_creados = []

    _metodo_pagos = {
        "SUSCRIPCION": "TRANSFER", "TRANSFER": "TRANSFER",
        "DEB": "DEBIT CARD", "CRED": "CREDIT CARD", "EFECTIVO": "EFECTIVO",
    }
    metodo_pago_tabla = _metodo_pagos.get(metodo, "TRANSFER")

    _concepto_map = {
        "QUINCENAL MENSUAL": "MENSUAL",
        "SEMANAL MENSUAL": "MENSUAL",
        "QUINCENAL TRIMESTRAL": "TRIMESTRAL",
        "SEMANAL TRIMESTRAL": "TRIMESTRAL",
    }
    _matri_concepto = "MATRICULA"

    if matricula > 0:
        pago_matri = await _post(_pagos_tabla, {
            "MONTO": matricula,
            "METODO DE PAGO": metodo_pago_tabla,
            "CONCEPTO": _matri_concepto,
            "ESTADO DE PAGO": "PAGADO",
            "FUENTE": "FENIX KIDS ACADEMY",
            "FAMILIA FENIX": [familia_id],
            "EXCEL": True,
        })
        if pago_matri:
            pagos_creados.append(f"Matrícula {matricula // 1000}mil")

    if monto > 0:
        concepto_plan = _concepto_map.get(plan, "MENSUAL")
        pago_plan = await _post(_pagos_tabla, {
            "MONTO": monto,
            "METODO DE PAGO": metodo_pago_tabla,
            "CONCEPTO": concepto_plan,
            "ESTADO DE PAGO": "PAGADO",
            "FUENTE": "FENIX KIDS ACADEMY",
            "FAMILIA FENIX": [familia_id],
            "EXCEL": True,
        })
        if pago_plan:
            pagos_creados.append(f"Plan {monto // 1000}mil")

    # ── 4. Marcar INSCRIPTO ──────────────────────────────────────────
    for op in todas_pruebas:
        await _patch(_PRUEBAS, op["id"], {
            "CONVERSION": "INSCRIPTO",
            "FAMILIA": [familia_id],
        })

    leads = await _get_records(_LEADS, formula=f"{{TELEFONO}}='{tel}'", max_records=5)
    for lead in leads:
        await _patch(_LEADS, lead["id"], {
            "CONVERSION": "INSCRIPTO",
            "FAMILIA": [familia_id],
        })

    # ── Confirmar ─────────────────────────────────────────────────────
    msg = (
        f"✅ *FAMILIA CARGADA*\n\n"
        f"👨 {nombre_padre} {apellido_padre} ({tel})\n"
        f"👶 Hijos: {', '.join(ninos_creados) if ninos_creados else 'ninguno'}\n"
        f"📋 Plan: {plan}\n"
        f"💳 Método: {metodo}\n"
        f"💰 Pagos: {', '.join(pagos_creados) if pagos_creados else 'ninguno'}\n"
        f"🟢 Estado: ACTIVO\n\n"
        f"PRUEBA → INSCRIPTO ✅\n"
        f"LEAD → INSCRIPTO ✅"
    )
    await proveedor.enviar_mensaje(admin_phone, msg)
    logger.info(f"[INSCRIPCION] Familia creada: {nombre_padre} {apellido_padre} ({tel}) plan={plan} monto={monto} matri={matricula}")
