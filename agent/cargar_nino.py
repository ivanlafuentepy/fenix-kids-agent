# agent/cargar_nino.py — Comando admin "cargar niño": alta directa a FAMILIAS via Meta Flow
"""
Flujo: el admin escribe "cargar niño" → recibe el formulario nativo de Meta
(Flow fenix_cargar_nino, 3 pantallas: niño obligatorio, papá/mamá opcionales)
→ al enviarlo, el webhook recibe el nfm_reply con flow="cargar_nino" y acá se
crean TUTORES + NIÑO (ESTADO=ACTIVO, niño-eje F7.b) en Airtable.

El audio del Guardián Fenix se genera solo: crear_nino() lo dispara en
background (agent/voces_alumnos.py).

Env: FLOW_CARGAR_NINO_ID (Flow publicado en el WABA compartido con Salsa).
"""

import os
import logging
from datetime import datetime, timezone

from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit")
proveedor = obtener_proveedor()

FLOW_CARGAR_NINO_ID = os.getenv("FLOW_CARGAR_NINO_ID", "")


def _fecha_desde_flow(valor: str) -> str:
    """DatePicker de Meta devuelve epoch en milisegundos (string).

    Convierte a YYYY-MM-DD (formato que Airtable espera). Acepta también
    YYYY-MM-DD directo por si el formato del Flow cambia. Vacío → "".
    """
    v = (valor or "").strip()
    if not v:
        return ""
    if v.isdigit():
        try:
            return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return ""
    return v  # ya viene como fecha (YYYY-MM-DD)


async def enviar_formulario_cargar_nino(admin_phone: str) -> None:
    """Envía el Flow de cargar alumno al admin."""
    if not FLOW_CARGAR_NINO_ID:
        await proveedor.enviar_mensaje(admin_phone, "Falta configurar FLOW_CARGAR_NINO_ID en Railway.")
        return
    ok = await proveedor.enviar_flow(
        telefono=admin_phone,
        flow_id=FLOW_CARGAR_NINO_ID,
        screen="NINO",
        texto="Alta directa de alumno a FAMILIAS. Datos del niño obligatorios; papá y mamá opcionales.",
        boton_texto="Cargar alumno",
    )
    if not ok:
        await proveedor.enviar_mensaje(admin_phone, "No pude enviar el formulario (¿token Meta?). Mirá los logs.")


def _tutor_desde_flow(d: dict, prefijo: str) -> dict:
    """Arma el dict de padre/madre para crear_o_actualizar_tutor desde los campos del Flow."""
    tutor = {
        "nombre": (d.get(f"{prefijo}_nombre") or "").strip(),
        "apellido": (d.get(f"{prefijo}_apellido") or "").strip(),
        "ci": (d.get(f"{prefijo}_ci") or "").strip(),
        "telefono": (d.get(f"{prefijo}_telefono") or "").strip(),
        "email": (d.get(f"{prefijo}_email") or "").strip(),
        "fecha_nacimiento": _fecha_desde_flow(d.get(f"{prefijo}_fecha_nacimiento", "")),
    }
    return {k: v for k, v in tutor.items() if v}


async def procesar_formulario_cargar_nino(admin_phone: str, flow_data: dict) -> None:
    """Crea TUTORES + NIÑO ACTIVO (niño-eje, F7.b — FAMILIAS ya no se crea)
    desde la respuesta del Flow y confirma al admin."""
    from agent.airtable_client import crear_o_actualizar_tutor, crear_nino

    nino_nombre = (flow_data.get("nino_nombre") or "").strip()
    nino_apellido = (flow_data.get("nino_apellido") or "").strip()
    if not nino_nombre:
        await proveedor.enviar_mensaje(admin_phone, "El formulario llegó sin nombre del niño — no cargué nada.")
        return

    padre = _tutor_desde_flow(flow_data, "padre")
    madre = _tutor_desde_flow(flow_data, "madre")

    # Tutores (filas ALUMNOS) — idempotentes por TELEFONO LIMPIO; el niño los
    # linkea PADRE/MADRE (ALUMNOS).
    # Sin datos de tutores el niño se crea igual (ficha incompleta, se completa después).
    padre_id = await crear_o_actualizar_tutor(padre, "Papá") if padre.get("nombre") else None
    madre_id = await crear_o_actualizar_tutor(madre, "Mamá") if madre.get("nombre") else None

    # NIÑO — crear_nino dispara la generación del audio en background
    nino_id = await crear_nino({
        "nombre": nino_nombre,
        "apellido": nino_apellido,
        "ci": (flow_data.get("nino_ci") or "").strip(),
        "fecha_nacimiento": _fecha_desde_flow(flow_data.get("nino_fecha_nacimiento", "")),
    }, padre_id=padre_id or "", madre_id=madre_id or "", estado="ACTIVO")
    if not nino_id:
        await proveedor.enviar_mensaje(
            admin_phone,
            "⚠️ Falló la creación del NIÑO — revisá Airtable."
        )
        return

    def _resumen_tutor(t: dict, etiqueta: str) -> str:
        if not t:
            return f"{etiqueta}: (sin datos)"
        partes = [f"{t.get('nombre', '')} {t.get('apellido', '')}".strip()]
        if t.get("ci"):
            partes.append(f"CI {t['ci']}")
        if t.get("telefono"):
            partes.append(t["telefono"])
        if t.get("email"):
            partes.append(t["email"])
        return f"{etiqueta}: " + " · ".join(p for p in partes if p)

    msg = (
        f"✅ *ALUMNO CARGADO*\n\n"
        f"👶 {nino_nombre} {nino_apellido}"
        + (f" — CI {flow_data.get('nino_ci', '').strip()}" if (flow_data.get("nino_ci") or "").strip() else "")
        + (f"\n🎂 {_fecha_desde_flow(flow_data.get('nino_fecha_nacimiento', ''))}" if _fecha_desde_flow(flow_data.get("nino_fecha_nacimiento", "")) else "")
        + f"\n👨 {_resumen_tutor(padre, 'Papá')}"
        + f"\n👩 {_resumen_tutor(madre, 'Mamá')}"
        + f"\n\n🟢 NIÑO en estado ACTIVO"
        + f"\n🔊 Audio del Guardián generándose..."
    )
    await proveedor.enviar_mensaje(admin_phone, msg)
    logger.info(f"[CARGAR-NINO] Alumno cargado: {nino_nombre} {nino_apellido} nino={nino_id} padre={padre_id} madre={madre_id}")
