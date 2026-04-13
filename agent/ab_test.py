# agent/ab_test.py — Estado de conversaciones FENIX KIDS ACADEMY
# Maneja: agente activo, modo Nixie, variante rompehielos, conversión, Calendar

import random
import logging
from datetime import datetime
from sqlalchemy import select
from agent.memory import async_session, ConversacionAB

logger = logging.getLogger("agentkit")

# Solo una variante de rompehielos por ahora (Ivan lo envía manualmente en su prompt)
ROMPEHIELOS: dict[str, str] = {
    "A": "",  # El rompehielos lo genera Ivan en su prompt, no se envía desde acá
}

_KEYWORDS_CONVERSION = [
    "pasame porfa los datos",
    "datos de tu hijo",
    "nombre:\napellido:",
    "fecha de nacimiento:",
    "talla remera",
    "datos de papá",
    "datos de mamá",
    "reserva confirmada",
    "quedaron reservados",
    "tiene su lugar",
]


def detectar_conversion(texto_respuesta: str) -> bool:
    """Retorna True si Nixie llegó al paso de recolección de datos o confirmación."""
    texto_lower = texto_respuesta.lower()
    return any(kw in texto_lower for kw in _KEYWORDS_CONVERSION)


# ── Estado del agente activo ──────────────────────────────────────────────────

async def obtener_agent_actual(telefono: str) -> tuple[str, str | None]:
    """
    Retorna (agent_actual, modo_nixie) para el teléfono dado.
    Default: ("ivan", None)
    """
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv.agent_actual or "ivan", conv.modo_nixie
        return "ivan", None


async def actualizar_agent_actual(telefono: str, agent: str, modo_nixie: str | None = None):
    """Cambia el agente activo para esta conversación."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.agent_actual = agent
            if modo_nixie is not None:
                conv.modo_nixie = modo_nixie
            await session.commit()
            logger.info(f"Agente cambiado a {agent} (modo: {modo_nixie}) para {telefono}")


# ── Inicialización de conversación ────────────────────────────────────────────

async def asignar_variante(telefono: str) -> tuple[str, bool]:
    """
    Inicializa la conversación si es nueva.
    Retorna (variante, es_nueva_asignacion).
    """
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()

        if conv:
            return conv.variante, False

        variante = "A"  # Solo una variante por ahora
        nueva = ConversacionAB(
            telefono=telefono,
            variante=variante,
            convertido=False,
            agent_actual="ivan",
            timestamp_inicio=datetime.utcnow(),
        )
        session.add(nueva)
        await session.commit()
        logger.info(f"Nueva conversación: {telefono} → Ivan")
        return variante, True


async def obtener_variante(telefono: str) -> str | None:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.variante).where(ConversacionAB.telefono == telefono)
        )
        return result.scalar_one_or_none()


# ── Conversión y formulario ───────────────────────────────────────────────────

async def marcar_conversion(telefono: str):
    """Marca que Nixie ya inició el proceso de recolección de datos."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv and not conv.convertido:
            conv.convertido = True
            conv.timestamp_conversion = datetime.utcnow()
            await session.commit()
            logger.info(f"Conversión registrada para {telefono}")


async def esta_convertido(telefono: str) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.convertido).where(ConversacionAB.telefono == telefono)
        )
        valor = result.scalar_one_or_none()
        return bool(valor)


# ── Airtable ──────────────────────────────────────────────────────────────────

async def guardar_airtable_record_id(telefono: str, record_id: str):
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv and not conv.airtable_record_id:
            conv.airtable_record_id = record_id
            await session.commit()


async def obtener_airtable_record_id(telefono: str) -> str | None:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.airtable_record_id).where(ConversacionAB.telefono == telefono)
        )
        return result.scalar_one_or_none()


async def guardar_familia_id(telefono: str, familia_id: str):
    """Guarda el ID del registro en FAMILIAS para esta conversación."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.familia_id = familia_id
            await session.commit()


async def obtener_familia_id(telefono: str) -> str | None:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.familia_id).where(ConversacionAB.telefono == telefono)
        )
        return result.scalar_one_or_none()


# ── Google Calendar ───────────────────────────────────────────────────────────

async def guardar_calendar_event_id(telefono: str, event_id: str):
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.calendar_event_id = event_id
            await session.commit()


async def obtener_calendar_event_id(telefono: str) -> str | None:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.calendar_event_id).where(ConversacionAB.telefono == telefono)
        )
        return result.scalar_one_or_none()


async def marcar_evento_creado(telefono: str):
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv and not conv.evento_creado:
            conv.evento_creado = True
            await session.commit()


async def ya_tiene_evento(telefono: str) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.evento_creado).where(ConversacionAB.telefono == telefono)
        )
        valor = result.scalar_one_or_none()
        return bool(valor)


# ── Estadísticas (simplificado) ───────────────────────────────────────────────

async def obtener_estadisticas() -> dict:
    from sqlalchemy import func
    async with async_session() as session:
        res_total = await session.execute(select(func.count()).select_from(ConversacionAB))
        total = res_total.scalar() or 0
        res_conv = await session.execute(
            select(func.count()).where(ConversacionAB.convertido == True)  # noqa: E712
        )
        convertidos = res_conv.scalar() or 0
        tasa = round((convertidos / total * 100), 1) if total > 0 else 0.0
        return {
            "total_conversaciones": total,
            "total_conversiones": convertidos,
            "tasa_conversion": tasa,
        }


# ── Modo nocturno ────────────────────────────────────────────────────────────

async def marcar_noche_pendiente(telefono: str):
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.noche_pendiente = True
            await session.commit()


async def tiene_noche_pendiente(telefono: str) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        return bool(conv and conv.noche_pendiente)


async def limpiar_noche_pendiente(telefono: str):
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.noche_pendiente = False
            await session.commit()


async def obtener_leads_noche_pendiente() -> list[str]:
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.telefono).where(ConversacionAB.noche_pendiente == True)
        )
        return [r[0] for r in result.all()]
