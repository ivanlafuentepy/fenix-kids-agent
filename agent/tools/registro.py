# agent/tools/registro.py — Registrar familia e hijos
# Solo Aurora. Reemplaza la detección regex de "REGISTRO PADRE:" y "REGISTRO HIJO:".

import logging

from agent.airtable_client import (
    buscar_familia_por_telefono,
    crear_familia,
    crear_o_actualizar_tutor,
    crear_nino,
    deducir_genero,
    _patch,
    _FAMILIAS,
)
from agent.ab_test import obtener_familia_id, guardar_familia_id

logger = logging.getLogger("agentkit")


async def registrar_familia(
    telefono: str,
    nombre: str,
    apellido: str | None = None,
    familia_id: str | None = None,
) -> dict:
    """
    Registra o actualiza el nombre del padre/madre en FAMILIAS FENIX.
    Usa deducir_genero() para determinar si es PADRE o MADRE.
    Si la familia ya existe, actualiza. Si no, crea nueva.
    """
    nombre = nombre.strip().title()
    apellido = (apellido or "").strip().title()

    genero = deducir_genero(nombre)
    es_madre = genero == "MUJER"
    rol = "MADRE" if es_madre else "PADRE"

    # Resolver familia existente
    if not familia_id:
        fam_id_db = await obtener_familia_id(telefono)
        if fam_id_db:
            familia_id = fam_id_db
        else:
            fam = await buscar_familia_por_telefono(telefono)
            if fam:
                familia_id = fam["id"]
                await guardar_familia_id(telefono, familia_id)

    if familia_id:
        # Actualizar familia existente
        if es_madre:
            campos = {"NOMBRE MADRE": nombre, "CELL MADRE": telefono, "CELL PADRE": ""}
            if apellido:
                campos["APELLIDO MADRE"] = apellido
        else:
            campos = {"NOMBRE PADRE": nombre, "CELL PADRE": telefono, "CELL MADRE": ""}
            if apellido:
                campos["APELLIDO PADRE"] = apellido

        ok = await _patch(_FAMILIAS, familia_id, campos)
        if ok:
            logger.info(f"[REGISTRO] {rol} actualizado: {nombre} {apellido} → familia {familia_id}")
            # Escritura dual (EJE B) — reflejar en TUTORES FENIX. Aislado, nunca rompe el registro.
            try:
                persona = {"nombre": nombre, "apellido": apellido, "telefono": telefono}
                await crear_o_actualizar_tutor(familia_id, persona, "Mamá" if es_madre else "Papá")
            except Exception as e:
                logger.error(f"[TUTORES] dual-write en registrar_familia falló: {e}")
            return {
                "texto": f"{rol.title()} registrado: {nombre} {apellido}".strip(),
                "registrada": True,
                "familia_id": familia_id,
                "rol": rol,
                "actualizado": True,
            }
        return {
            "error": True,
            "error_category": "transient",
            "is_retryable": True,
            "message": "Error actualizando la familia en Airtable.",
        }

    # Crear familia nueva
    datos = {}
    if es_madre:
        datos["madre"] = {"nombre": nombre, "apellido": apellido, "telefono": telefono}
    else:
        datos["padre"] = {"nombre": nombre, "apellido": apellido, "telefono": telefono}

    nuevo_id = await crear_familia(datos)
    if nuevo_id:
        await guardar_familia_id(telefono, nuevo_id)
        logger.info(f"[REGISTRO] Familia creada: {nombre} {apellido} → {nuevo_id}")
        return {
            "texto": f"Familia registrada. {rol.title()}: {nombre} {apellido}".strip(),
            "registrada": True,
            "familia_id": nuevo_id,
            "rol": rol,
            "actualizado": False,
        }

    return {
        "error": True,
        "error_category": "transient",
        "is_retryable": True,
        "message": "Error creando la familia en Airtable.",
    }


async def registrar_hijo(
    telefono: str,
    nombre: str,
    apellido: str | None = None,
    fecha_nacimiento: str | None = None,
    ci: str | None = None,
    talla_remera: str | None = None,
    familia_id: str | None = None,
) -> dict:
    """
    Registra un hijo vinculado a la familia.
    Requiere familia_id (inyectado por executor o resuelto por teléfono).
    """
    # Resolver familia
    if not familia_id:
        fam_id_db = await obtener_familia_id(telefono)
        if fam_id_db:
            familia_id = fam_id_db
        else:
            fam = await buscar_familia_por_telefono(telefono)
            if fam:
                familia_id = fam["id"]
                await guardar_familia_id(telefono, familia_id)

    if not familia_id:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No encontré una familia registrada para este número. Primero hay que registrar la familia con registrar_familia.",
        }

    datos_nino = {"nombre": nombre.strip().title()}
    if apellido:
        datos_nino["apellido"] = apellido.strip().title()
    if fecha_nacimiento:
        datos_nino["fecha_nacimiento"] = fecha_nacimiento
    if ci:
        datos_nino["ci"] = ci.strip()
    if talla_remera:
        datos_nino["talla_remera"] = talla_remera.strip().upper()

    nino_id = await crear_nino(datos_nino, familia_id)
    if nino_id:
        nombre_display = f"{datos_nino['nombre']} {datos_nino.get('apellido', '')}".strip()
        logger.info(f"[REGISTRO] Hijo creado: {nombre_display} → familia {familia_id}")
        return {
            "texto": f"Hijo registrado: {nombre_display}",
            "registrado": True,
            "nino_id": nino_id,
            "familia_id": familia_id,
        }

    return {
        "error": True,
        "error_category": "transient",
        "is_retryable": True,
        "message": "Error creando el hijo en Airtable.",
    }
