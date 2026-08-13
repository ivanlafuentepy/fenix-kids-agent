# agent/tools/registro.py — Registrar tutor e hijos (niño-eje, F7.b)
# Solo Aurora. Reemplaza la detección regex de "REGISTRO PADRE:" y "REGISTRO HIJO:".

import logging

from agent.airtable_client import (
    buscar_tutor_por_telefono,
    crear_o_actualizar_tutor,
    crear_nino,
    deducir_genero,
    _parentesco_de_alumno,
    _patch,
    _ALUMNOS,
)
from agent.ab_test import actualizar_estado_flags

logger = logging.getLogger("agentkit")


async def registrar_familia(
    telefono: str,
    nombre: str,
    apellido: str | None = None,
    familia_id: str | None = None,
    **_extra,   # argumento alucinado por el LLM → se ignora, no TypeError
) -> dict:
    """
    Registra o actualiza el nombre del tutor de este teléfono (fila de ALUMNOS
    con NEGOCIO=FENIX; F7.b: FAMILIAS ya no se escribe). deducir_genero() decide Mamá/Papá.
    familia_id queda en la firma por compatibilidad de la tool — se ignora.
    """
    nombre = nombre.strip().title()
    apellido = (apellido or "").strip().title()

    genero = deducir_genero(nombre)
    es_madre = genero == "MUJER"
    rol = "MADRE" if es_madre else "PADRE"

    tutor = await buscar_tutor_por_telefono(telefono)
    if tutor:
        # Tutor existente para este cel → actualizar nombre/apellido
        # (no se toca PARENTESCO: los links PADRE/MADRE de los niños mandan)
        campos = {"NOMBRE": nombre}
        if apellido:
            campos["APELLIDO"] = apellido
        # GENERO vacío debilita la identidad: el contexto de Aurora pierde
        # MADRE/PADRE y el saludo queda genérico (caso Jazmin 13/08).
        # Se completa solo si falta y el nombre lo deduce con confianza.
        if genero and not ((tutor.get("fields", {}) or {}).get("GENERO") or "").strip():
            campos["GENERO"] = genero
        ok = await _patch(_ALUMNOS, tutor["id"], campos)
        tutor_id = tutor["id"] if ok else None
        actualizado = True
    else:
        tutor_id = await crear_o_actualizar_tutor(
            {"nombre": nombre, "apellido": apellido, "telefono": telefono},
            "Mamá" if es_madre else "Papá",
        )
        actualizado = False

    if tutor_id:
        await actualizar_estado_flags(telefono, tutor_id=tutor_id)
        logger.info(f"[REGISTRO] {rol} registrado: {nombre} {apellido} → tutor {tutor_id}")
        return {
            "texto": f"{rol.title()} registrado: {nombre} {apellido}".strip(),
            "registrada": True,
            "tutor_id": tutor_id,
            "rol": rol,
            "actualizado": actualizado,
        }

    return {
        "error": True,
        "error_category": "transient",
        "is_retryable": True,
        "message": "Error registrando el tutor en Airtable.",
    }


async def registrar_hijo(
    telefono: str,
    nombre: str,
    apellido: str | None = None,
    fecha_nacimiento: str | None = None,
    ci: str | None = None,
    talla_remera: str | None = None,
    familia_id: str | None = None,
    **_extra,   # argumento alucinado por el LLM → se ignora, no TypeError
) -> dict:
    """
    Registra un hijo linkeado directo al tutor del teléfono (PADRE o MADRE
    según su parentesco, niño-eje). familia_id se ignora (compatibilidad).
    """
    tutor = await buscar_tutor_por_telefono(telefono)
    if not tutor:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No encontré un tutor registrado para este número. Primero hay que registrar al padre/madre con registrar_familia.",
        }

    # El tutor es una fila de ALUMNOS (sin PARENTESCO): se deriva del GENERO.
    parentesco = _parentesco_de_alumno(tutor.get("fields", {}) or {})
    _link = {"madre_id": tutor["id"]} if parentesco == "Mamá" else {"padre_id": tutor["id"]}

    datos_nino = {"nombre": nombre.strip().title()}
    if apellido:
        datos_nino["apellido"] = apellido.strip().title()
    if fecha_nacimiento:
        datos_nino["fecha_nacimiento"] = fecha_nacimiento
    if ci:
        datos_nino["ci"] = ci.strip()
    if talla_remera:
        datos_nino["talla_remera"] = talla_remera.strip().upper()

    nino_id = await crear_nino(datos_nino, estado="ACTIVO", **_link)
    if nino_id:
        nombre_display = f"{datos_nino['nombre']} {datos_nino.get('apellido', '')}".strip()
        logger.info(f"[REGISTRO] Hijo creado: {nombre_display} → tutor {tutor['id']}")
        return {
            "texto": f"Hijo registrado: {nombre_display}",
            "registrado": True,
            "nino_id": nino_id,
            "tutor_id": tutor["id"],
        }

    return {
        "error": True,
        "error_category": "transient",
        "is_retryable": True,
        "message": "Error creando el hijo en Airtable.",
    }
