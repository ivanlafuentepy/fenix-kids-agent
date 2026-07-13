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


async def _candidatos_a_prueba() -> list[dict]:
    """Candidatos a inscribir (F7.b): NIÑOS con ESTADO='A PRUEBA' agrupados por
    tutor (links PADRE/MADRE del niño) — FAMILIAS ya no se enumera. Cubre los
    dos modelos: altas niño-eje nuevas y fichas legacy (C0 backfilleó el ESTADO
    de todos los niños; si un niño no tiene tutor linkeado, se agrupa por su
    FAMILIA legacy).

    Cada candidato tiene el formato pseudo-PRUEBA que espera el resto del flujo:
    {"prueba": {"id": "", "fields": {TELEFONO, NOMBRE, APELLIDO}},
     "todas_pruebas": [{"id": "", "_nino_id", "fields": {NOMBRE HIJO, APELLIDO HIJO,
                        EDAD HIJO, FECHA NACIMIENTO, GENERO}}, ...],
     "tutor_id": rec del tutor (si se resolvió), "familia_id": rec legacy o ""}
    """
    from agent.airtable_client import _get_records, _FAMILIAS, _NINOS, _TUTORES

    ninos = await _get_records(_NINOS, formula="{ESTADO}='A PRUEBA'", max_records=1000)
    if not ninos:
        return []

    # Agrupar niños que comparten algún tutor; sin tutor → por familia legacy;
    # sin nada → grupo propio.
    grupos: list[dict] = []
    for n in ninos:
        nf = n.get("fields", {}) or {}
        if not (nf.get("NOMBRE") or "").strip():
            continue
        tutor_ids = (nf.get("PADRE") or []) + (nf.get("MADRE") or [])
        familia_id = (nf.get("FAMILIA") or [""])[0]
        destino = None
        for g in grupos:
            if (tutor_ids and set(tutor_ids) & set(g["tutor_ids"])) or \
               (not tutor_ids and familia_id and familia_id == g["familia_id"]):
                destino = g
                break
        if not destino:
            destino = {"tutor_ids": [], "familia_id": familia_id if not tutor_ids else "", "ninos": []}
            grupos.append(destino)
        destino["ninos"].append(n)
        for t in tutor_ids:
            if t not in destino["tutor_ids"]:
                destino["tutor_ids"].append(t)

    candidatos = []
    for g in grupos:
        tel, nombre, apellido, tutor_id = "", "", "", ""
        if g["tutor_ids"]:
            tutor_id = g["tutor_ids"][0]
            trec = await _get_records(_TUTORES, formula=f"RECORD_ID()='{tutor_id}'", max_records=1)
            if trec:
                tf = trec[0].get("fields", {}) or {}
                nombre = (tf.get("NOMBRE") or "").strip()
                apellido = (tf.get("APELLIDO") or "").strip()
                tel = (tf.get("CELL LIMPIO") or "").strip()
        elif g["familia_id"]:
            frec = await _get_records(_FAMILIAS, formula=f"RECORD_ID()='{g['familia_id']}'", max_records=1)
            if frec:
                ff = frec[0].get("fields", {}) or {}
                nombres_tut = ff.get("NOMBRES TUTORES", []) or []
                if not isinstance(nombres_tut, list):
                    nombres_tut = [nombres_tut]
                cells_tut = ff.get("CELLS LIMPIOS TUTORES", []) or []
                if not isinstance(cells_tut, list):
                    cells_tut = [cells_tut]
                _partes = (nombres_tut[0] if nombres_tut else "").strip().split()
                nombre = _partes[0] if _partes else ""
                apellido = " ".join(_partes[1:]) if len(_partes) > 1 else ""
                tel = (cells_tut[0] if cells_tut else "").strip()

        hijos = []
        for n in g["ninos"]:
            nf = n.get("fields", {}) or {}
            hijos.append({
                "id": "",  # sin registro PRUEBA — nada que patchear ahí
                "_nino_id": n["id"],
                "fields": {
                    "NOMBRE HIJO": nf.get("NOMBRE", ""),
                    "APELLIDO HIJO": nf.get("APELLIDO", ""),
                    "EDAD HIJO": nf.get("EDAD", "?"),
                    "FECHA NACIMIENTO": nf.get("FECHA NACIMIENTO", ""),
                    "GENERO": nf.get("SEXO", ""),
                },
            })

        candidatos.append({
            "prueba": {
                "id": "",
                "fields": {
                    "TELEFONO": tel,
                    "NOMBRE": nombre,
                    "APELLIDO": apellido,
                },
            },
            "todas_pruebas": hijos,
            "tutor_id": tutor_id,
            "familia_id": g["familia_id"],
        })
    return candidatos


async def _iniciar_inscripcion(admin_phone: str, texto_completo: str):
    """
    Parsea texto libre: extrae nombre + datos de inscripción.
    Si tiene todo, ejecuta directo. Si falta algo, pide lo que falta.
    """
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

    # Buscar en FAMILIAS A PRUEBA + NIÑOS (2.C-C5: PRUEBA FENIX ya no se lee)
    # — normalizar tildes para comparación
    import unicodedata
    def _sin_tildes(s: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()

    candidatos = await _candidatos_a_prueba()
    _nombre_norm = _sin_tildes(nombre_buscar)

    matches = []
    for c in candidatos:
        f = c["prueba"]["fields"]
        nombre_completo = _sin_tildes(f"{f.get('NOMBRE', '')} {f.get('APELLIDO', '')}".strip())
        if nombre_completo and (_nombre_norm in nombre_completo or nombre_completo in _nombre_norm):
            matches.append(c)

    if not matches:
        for c in candidatos:
            for op in c["todas_pruebas"]:
                hf = op["fields"]
                hijo_completo = _sin_tildes(f"{hf.get('NOMBRE HIJO', '')} {hf.get('APELLIDO HIJO', '')}".strip())
                if hijo_completo and _nombre_norm in hijo_completo:
                    matches.append(c)
                    break

    if not matches:
        await proveedor.enviar_mensaje(admin_phone, f"No encontré familia A PRUEBA para '{nombre_buscar}'")
        return

    if len(matches) > 1:
        msg = f"Encontré {len(matches)} familias:\n\n"
        for i, c in enumerate(matches, 1):
            f = c["prueba"]["fields"]
            _h0 = c["todas_pruebas"][0]["fields"].get("NOMBRE HIJO", "") if c["todas_pruebas"] else ""
            msg += f"{i}. {f.get('NOMBRE', '')} {f.get('APELLIDO', '')} → {_h0} ({f.get('TELEFONO', '')})\n"
        msg += "\nEscribí el número para elegir:"
        _inscripcion_pendiente[admin_phone] = {"step": "elegir", "matches": matches, "parsed": parsed}
        await proveedor.enviar_mensaje(admin_phone, msg)
        return

    prueba = matches[0]["prueba"]
    todas_pruebas = matches[0]["todas_pruebas"]
    tel = prueba.get("fields", {}).get("TELEFONO", "")

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
                # 2.C-C5: los matches ya traen prueba + hijos (pseudo-PRUEBA
                # armados desde FAMILIAS A PRUEBA/NIÑOS) — nada que re-consultar
                prueba = matches[idx]["prueba"]
                todas = matches[idx]["todas_pruebas"]
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
        _get_records, _post, _patch, _LEADS, _FAMILIAS,
        crear_familia, crear_nino,
        buscar_familia_por_telefono, obtener_ninos_de_familia,
    )

    fp = prueba.get("fields", {})
    tel = fp.get("TELEFONO", "")
    nombre_padre = fp.get("NOMBRE", "")
    apellido_padre = fp.get("APELLIDO", "")

    # ── 1. Buscar o crear FAMILIA ─────────────────────────────────────
    # Si la familia ya existe (creada al pagar la prueba, en estado A PRUEBA),
    # la reutilizamos y la promovemos a ACTIVO en vez de crear una duplicada.
    # Hoy todavía no se crea familia en la prueba → esta rama queda dormida
    # hasta que se active el flujo de pago (deploy siguiente de la Fase 2).
    familia_existente = await buscar_familia_por_telefono(tel)
    ninos_previos = []
    if familia_existente:
        familia_id = familia_existente["id"]
        ninos_previos = await obtener_ninos_de_familia(familia_id)
        logger.info(f"[INSCRIPCION] Reutilizando FAMILIA existente {familia_id} para {tel}")
    else:
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

    # ── 2. Crear o reutilizar NIÑO(S) ─────────────────────────────────
    # Si la familia ya traía niños (creados en la prueba), los matcheamos
    # por NOMBRE para no duplicar; igual linkeamos PRUEBA→NIÑO y migramos cara.
    def _match_nino_previo(nombre_hijo: str) -> str | None:
        nh = (nombre_hijo or "").strip().lower()
        if not nh:
            return None
        for np in ninos_previos:
            if (np.get("nombre") or "").strip().lower() == nh:
                return np.get("id")
        return None

    ninos_creados = []
    for op in todas_pruebas:
        of = op.get("fields", {})
        h_nombre = of.get("NOMBRE HIJO", "")
        h_apellido = of.get("APELLIDO HIJO", "")
        h_fn = of.get("FECHA NACIMIENTO", "")
        h_genero = of.get("GENERO", "")
        if h_nombre:
            # 2.C-C5: si el candidato vino de NIÑOS (pseudo-PRUEBA), ya trae el id
            nino_id = op.get("_nino_id") or _match_nino_previo(h_nombre)
            if nino_id:
                logger.info(f"[INSCRIPCION] Reutilizando NIÑO existente {nino_id} ({h_nombre})")
            else:
                nino_id = await crear_nino({
                    "nombre": h_nombre,
                    "apellido": h_apellido,
                    "fecha_nacimiento": h_fn,
                    "sexo": h_genero,
                }, familia_id)
            if nino_id:
                ninos_creados.append(f"{h_nombre} {h_apellido}")
    # ── 3. Crear PAGOS ───────────────────────────────────────────────
    _pagos_tabla = "PAGOS"
    pagos_creados = []

    # Guard anti-duplicado (mismo patrón que registrar_pago_fenix): si el admin
    # corre "cargar familia" dos veces (timeout, reintento), los POST directos
    # duplicaban matrícula + cuota en PAGOS (auditoría 2026-07-12, A1).
    # Se saltea la creación si la familia ya tiene un PAGO con ese CONCEPTO hoy.
    # Migración niño-eje: el guard mira la UNIÓN FAMILIAS.PAGOS ∪ NIÑOS.PAGOS
    # (sobrevive al corte futuro de FAMILIA FENIX en los pagos).
    _conceptos_hoy: set[str] = set()
    _nino_ids_pago: list[str] = []
    _ninos_a_promover: list[str] = []
    try:
        _fam_g = await _get_records(_FAMILIAS, formula=f"RECORD_ID()='{familia_id}'", max_records=1)
        _fam_g_fields = (_fam_g[0].get("fields", {}) or {}) if _fam_g else {}
        # Los niños de la familia (previos + recién creados: el link inverso ya los ve)
        _nino_ids_pago = _fam_g_fields.get("NIÑOS FENIX", []) or []
        _pago_ids_g = list(_fam_g_fields.get("PAGOS", []) or [])
        if _nino_ids_pago:
            import httpx as _httpx_g
            from agent.airtable_client import _BASE_URL as _BURL_g, _headers as _hdrs_g, _NINOS as _NINOS_g
            async with _httpx_g.AsyncClient() as _cl_g:
                for _nid_g in _nino_ids_pago:
                    try:
                        _r_g = await _cl_g.get(f"{_BURL_g}/{_NINOS_g}/{_nid_g}", headers=_hdrs_g(), timeout=10)
                        if _r_g.status_code == 200:
                            _f_n_g = _r_g.json().get("fields", {})
                            for _pid_g in _f_n_g.get("PAGOS", []) or []:
                                if _pid_g not in _pago_ids_g:
                                    _pago_ids_g.append(_pid_g)
                            # Niño-eje: los reutilizados de la prueba quedaron A PRUEBA
                            # → al inscribirse la familia, el niño pasa a ACTIVO.
                            if (_f_n_g.get("ESTADO") or "") != "ACTIVO":
                                _ninos_a_promover.append(_nid_g)
                    except Exception as _e_n:
                        logger.warning(f"[INSCRIPCION] Guard: no pude leer PAGOS del niño {_nid_g}: {_e_n}")
        if _pago_ids_g:
            _or_g = ",".join(f"RECORD_ID()='{pid}'" for pid in _pago_ids_g)
            _formula_g = f"OR({_or_g})" if len(_pago_ids_g) > 1 else _or_g
            _pagos_g = await _get_records(_pagos_tabla, formula=_formula_g, max_records=len(_pago_ids_g))
            from datetime import datetime as _dt_g
            from zoneinfo import ZoneInfo as _ZI_g
            _hoy_g = _dt_g.now(_ZI_g("America/Asuncion")).date().isoformat()
            for _p_g in _pagos_g:
                _pf_g = _p_g.get("fields", {})
                if (_pf_g.get("FECHA") or "")[:10] == _hoy_g:
                    _conceptos_hoy.add(_pf_g.get("CONCEPTO") or "")
    except Exception as _e_g:
        logger.warning(f"[INSCRIPCION] Guard anti-dup no pudo leer PAGOS: {_e_g}")

    # Promover los niños a ACTIVO (espejo del ESTADO PLAN de la familia, paso 1).
    # Best-effort: si falla, el niño queda A PRUEBA y se corrige a mano.
    for _nid_p in _ninos_a_promover:
        try:
            from agent.airtable_client import _NINOS as _NINOS_p
            await _patch(_NINOS_p, _nid_p, {"ESTADO": "ACTIVO"})
            logger.info(f"[INSCRIPCION] NIÑO {_nid_p} promovido a ESTADO=ACTIVO")
        except Exception as _e_p:
            logger.warning(f"[INSCRIPCION] No pude promover ESTADO del niño {_nid_p}: {_e_p}")

    # Tutor pagador (PAGA, niño-eje): el marcado ES QUIEN PAGA; si no, el del
    # teléfono de la prueba; si no, el único tutor. Best-effort: si falla, los
    # PAGOS se crean igual (solo con FAMILIA FENIX + NIÑOS FENIX).
    _tutor_paga_id = None
    try:
        from agent.airtable_client import obtener_tutores_de_familia
        _tuts = [t for t in await obtener_tutores_de_familia(familia_id) if t.get("id")]
        _marcado = next((t for t in _tuts if t.get("es_quien_paga")), None)
        _por_cell = next(
            (t for t in _tuts if tel and tel in (t.get("cell_limpio"), t.get("cell"))),
            None,
        ) if tel else None
        _elegido = _marcado or _por_cell or (_tuts[0] if len(_tuts) == 1 else None)
        _tutor_paga_id = _elegido["id"] if _elegido else None
    except Exception as _e_t:
        logger.warning(f"[INSCRIPCION] No pude resolver el tutor pagador: {_e_t}")

    # Campos niño-eje comunes a matrícula y plan (dual-write: FAMILIA FENIX sigue)
    _campos_nino_eje: dict = {}
    if _nino_ids_pago:
        _campos_nino_eje["NIÑOS FENIX"] = _nino_ids_pago
    if _tutor_paga_id:
        _campos_nino_eje["PAGA"] = [_tutor_paga_id]

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

    if matricula > 0 and _matri_concepto in _conceptos_hoy:
        pagos_creados.append("Matrícula ya registrada hoy — no dupliqué")
        logger.info(f"[INSCRIPCION] PAGO MATRICULA ya existe hoy para familia {familia_id} → no duplico")
    elif matricula > 0:
        pago_matri = await _post(_pagos_tabla, {
            "MONTO": matricula,
            "METODO DE PAGO": metodo_pago_tabla,
            "CONCEPTO": _matri_concepto,
            "ESTADO DE PAGO": "PAGADO",
            "FUENTE": "FENIX KIDS ACADEMY",
            "EXCEL": True,
            **_campos_nino_eje,
        })
        if pago_matri:
            pagos_creados.append(f"Matrícula {matricula // 1000}mil")

    concepto_plan = _concepto_map.get(plan, "MENSUAL")
    if monto > 0 and concepto_plan in _conceptos_hoy:
        pagos_creados.append(f"Plan {concepto_plan} ya registrado hoy — no dupliqué")
        logger.info(f"[INSCRIPCION] PAGO {concepto_plan} ya existe hoy para familia {familia_id} → no duplico")
    elif monto > 0:
        pago_plan = await _post(_pagos_tabla, {
            "MONTO": monto,
            "METODO DE PAGO": metodo_pago_tabla,
            "CONCEPTO": concepto_plan,
            "ESTADO DE PAGO": "PAGADO",
            "FUENTE": "FENIX KIDS ACADEMY",
            "EXCEL": True,
            **_campos_nino_eje,
        })
        if pago_plan:
            pagos_creados.append(f"Plan {monto // 1000}mil")

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
