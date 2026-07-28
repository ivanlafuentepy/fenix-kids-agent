# agent/checkin_aviso.py — Aviso al padre cuando el niño entra a FENIX
"""
Cuando el niño hace check-in (cara, QR o carga manual del HQ) el padre recibe
un WhatsApp: que su hijo ya entró, cuántas clases del pack le quedan (o cuándo
vence su plan mensual) y la pregunta de si quiere las fotos del día.

Fuera de la ventana de 24h hace falta plantilla → `checkin_fenix` (aprobada el
28/07/2026, es_AR, UTILITY, botones "Sí, mandame fotos" / "No, gracias").

El botón que toca el padre ABRE la ventana de 24h. Por eso el aviso de "las
fotos ya están" sale después como mensaje libre, sin plantilla y sin costo,
siempre que las fotos se publiquen dentro de las 24h del check-in.

APAGADO POR DEFECTO: se prende con AVISO_CHECKIN_ACTIVO=true en Railway.
Nada que le hable a las familias se activa solo.
"""

import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from agent.ab_test import actualizar_estado_flags
from agent.memory import async_session, guardar_mensaje, ConversacionAB

logger = logging.getLogger("agentkit")

_PLANTILLA = "checkin_fenix"
_TZ_PY = ZoneInfo("America/Asuncion")

# Textos EXACTOS de los botones de la plantilla (Meta los devuelve tal cual).
# Son distintos de los "Sí"/"No" de confirmacion_sabado_fenix a propósito: la
# respuesta del botón llega sin id, solo con el texto, y se confundirían.
_BTN_SI_FOTOS = "sí, mandame fotos"
_BTN_NO_FOTOS = "no, gracias"


def aviso_activo() -> bool:
    """El aviso del check-in solo sale si Ivan lo prendió explícitamente."""
    return os.getenv("AVISO_CHECKIN_ACTIVO", "false").strip().lower() == "true"


def frase_estado(saldo: int | None, vence_el: str = "") -> str:
    """Arma la variable {{3}} de la plantilla según el plan de la familia.

    - saldo (pack de 5): cuántas clases le quedan, con el aviso de renovar en
      la última.
    - saldo None (plan mensual viejo): la fecha en que vence, si la sabemos.
    """
    if saldo is None:
        if vence_el:
            try:
                d = datetime.fromisoformat(str(vence_el)[:10]).strftime("%d/%m")
                return f"Su plan mensual vence el {d}."
            except ValueError:
                pass
        return "Sigue con su plan mensual."
    if saldo <= 0:
        return "Era la última clase de su pack — cuando quieras lo renovamos 🔥"
    if saldo == 1:
        return "Le queda 1 clase de su pack."
    return f"Le quedan {saldo} clases de su pack."


async def enviar_aviso_checkin(
    telefono: str,
    proveedor,
    nombre_padre: str,
    nombre_hijo: str,
    frase: str,
) -> bool:
    """Manda la plantilla del check-in y deja el flag esperando la respuesta.

    Devuelve True si Meta aceptó el envío. El flag solo se marca si salió: si
    no salió, no esperamos ninguna respuesta.
    """
    if not aviso_activo():
        logger.info(f"[CHECKIN-AVISO] apagado (AVISO_CHECKIN_ACTIVO) — no aviso a {telefono}")
        return False
    if not telefono:
        return False

    ok = await proveedor.enviar_plantilla(
        telefono, _PLANTILLA,
        variables=[nombre_padre or "familia", nombre_hijo or "tu hijo", frase],
        language="es_AR",
    )
    if ok:
        await actualizar_estado_flags(telefono, esperando_respuesta_fotos=True)
        await guardar_mensaje(telefono, "assistant", f"[plantilla check-in enviada] {frase}")
        logger.info(f"[CHECKIN-AVISO] plantilla enviada a {telefono} ({nombre_hijo}) — {frase}")
    return ok


async def _espejar(topic_id: int | None, texto: str, telefono: str, tg_group: int) -> None:
    """Espeja en el topic de Telegram lo que se le respondió al padre."""
    if not topic_id:
        return
    try:
        from agent.telegram_bridge import enviar_a_topic
        await enviar_a_topic(topic_id, f"🤖 {texto}", telefono=telefono, group_override=tg_group)
    except Exception as e:
        logger.warning(f"[CHECKIN-AVISO] no pude espejar a Telegram: {e}")


async def manejar_respuesta_fotos(
    telefono: str,
    texto: str,
    flags: dict,
    proveedor,
    *,
    topic_id: int | None = None,
    tg_group: int = 0,
) -> str | None:
    """Intercepta la respuesta a la plantilla del check-in.

    Returns:
        str  → este handler ya respondió; main.py NO debe seguir al menú/brain.
        None → no aplica; seguir el flujo normal de Aurora.
    """
    if not flags.get("esperando_respuesta_fotos"):
        return None

    _norm = (texto or "").strip().lower()

    if _norm == _BTN_SI_FOTOS:
        hoy = datetime.now(_TZ_PY).date().isoformat()
        await actualizar_estado_flags(
            telefono, esperando_respuesta_fotos=False, fotos_pedidas=hoy,
        )
        msg = "¡Dale! 📸 Apenas subamos las fotos de hoy te paso el link por acá 🌳"
        await proveedor.enviar_mensaje(telefono, msg)
        await guardar_mensaje(telefono, "assistant", msg)
        await _espejar(topic_id, msg, telefono, tg_group)
        logger.info(f"[CHECKIN-AVISO] {telefono}: pidió las fotos del {hoy}")
        return "[pidió fotos del día]"

    if _norm == _BTN_NO_FOTOS:
        await actualizar_estado_flags(telefono, esperando_respuesta_fotos=False)
        msg = "¡Listo! Que disfrute el entrenamiento 🌳"
        await proveedor.enviar_mensaje(telefono, msg)
        await guardar_mensaje(telefono, "assistant", msg)
        await _espejar(topic_id, msg, telefono, tg_group)
        logger.info(f"[CHECKIN-AVISO] {telefono}: no quiere fotos")
        return "[no quiere fotos]"

    # Cualquier otra cosa (el padre escribe una pregunta): que siga Aurora.
    # El flag queda vivo por si después toca el botón.
    return None


async def telefonos_que_piden_fotos() -> list[tuple[str, str]]:
    """(telefono, fecha_pedida) de las familias que pidieron las fotos.

    Se filtra en Python en vez de con un LIKE sobre el JSON: el estado es un
    texto serializado y un LIKE se rompe con cualquier cambio de formato.
    """
    pendientes: list[tuple[str, str]] = []
    async with async_session() as session:
        filas = (await session.execute(
            select(ConversacionAB.telefono, ConversacionAB.estado_json)
        )).all()
    for telefono, raw in filas:
        if not raw or "fotos_pedidas" not in raw:
            continue
        try:
            fecha = (json.loads(raw) or {}).get("fotos_pedidas")
        except (json.JSONDecodeError, TypeError):
            continue
        if fecha:
            pendientes.append((telefono, str(fecha)))
    return pendientes


async def avisar_fotos_listas(proveedor, link: str, fecha_iso: str = "") -> dict:
    """Le pasa el link de las fotos a cada familia que las pidió.

    fecha_iso vacío = avisar a todas las que estén esperando. El flag se limpia
    solo si el envío salió, así un fallo de red no le come el aviso a la familia.
    """
    pendientes = await telefonos_que_piden_fotos()
    if fecha_iso:
        pendientes = [(t, f) for t, f in pendientes if f == fecha_iso]

    enviados, fallidos = [], []
    msg = f"¡Ya están las fotos de hoy! 📸🌳\n\nMirálas acá: {link}"
    for telefono, _fecha in pendientes:
        try:
            ok = await proveedor.enviar_mensaje(telefono, msg)
        except Exception as e:
            logger.error(f"[CHECKIN-AVISO] fotos: error enviando a {telefono}: {e}")
            ok = False
        if ok:
            await actualizar_estado_flags(telefono, fotos_pedidas=None)
            await guardar_mensaje(telefono, "assistant", msg)
            enviados.append(telefono)
        else:
            fallidos.append(telefono)

    logger.info(f"[CHECKIN-AVISO] fotos avisadas: {len(enviados)} ok, {len(fallidos)} fallidas")
    return {"enviados": len(enviados), "fallidos": len(fallidos), "telefonos": enviados}
