# agent/memory.py — Memoria de conversaciones
# FENIX KIDS ACADEMY

"""
Sistema de memoria del agente. Guarda el historial de conversaciones
por número de teléfono usando PostgreSQL (producción) o SQLite (desarrollo).
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer, BigInteger, Boolean, text
from dotenv import load_dotenv

load_dotenv()

# Configuración de base de datos
# Railway provee DATABASE_URL apuntando a PostgreSQL.
# Fallback: SQLite local para desarrollo.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

# Normalizar esquema para asyncpg (Railway puede dar postgresql:// o postgres://)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

_es_postgres = DATABASE_URL.startswith("postgresql+asyncpg://")

# Pool settings distintos para PostgreSQL vs SQLite
_engine_kwargs: dict = {"echo": False}
if _es_postgres:
    _engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,   # verifica conexión antes de usarla
        "pool_recycle": 300,     # recicla conexiones cada 5 min
    })

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

import logging as _logging
_logging.getLogger("agentkit").info(
    f"[DB] {'PostgreSQL' if _es_postgres else 'SQLite'} — URL={'postgresql+asyncpg://***' if _es_postgres else DATABASE_URL}"
)


class Base(DeclarativeBase):
    pass


class ConversacionAB(Base):
    """Estado de cada conversación: agente activo, modo Nixie, datos de familia."""
    __tablename__ = "conversaciones_ab"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    variante: Mapped[str] = mapped_column(String(1), default="A")   # rompehielos A/B/C
    convertido: Mapped[bool] = mapped_column(Boolean, default=False)
    evento_creado: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp_inicio: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    timestamp_conversion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Airtable — ID del registro en LEADS
    airtable_record_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Airtable — ID del registro en FAMILIAS (una vez creada)
    familia_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Google Calendar — ID del evento activo (para borrarlo en reagendamientos)
    calendar_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Agente activo: "ivan" o "nixie"
    agent_actual: Mapped[str] = mapped_column(String(10), default="ivan")
    # Modo de Nixie: "lead_nuevo" o "cliente_inscripto"
    modo_nixie: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Ventanas de 24hs
    ventana_1_mensajes: Mapped[int] = mapped_column(Integer, default=0)
    ventana_2_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ventana_2_mensajes: Mapped[int] = mapped_column(Integer, default=0)
    ventana_3_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ventana_3_mensajes: Mapped[int] = mapped_column(Integer, default=0)
    # Modo nocturno
    noche_pendiente: Mapped[bool] = mapped_column(Boolean, default=False)

    # Meta CAPI — Click ID del anuncio Click-to-WhatsApp
    ctwa_clid: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # ID del anuncio Meta (referral.source_id)
    ad_source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class TopicTelegram(Base):
    """Mapea cada número de WhatsApp a su topic en un grupo de Telegram."""
    __tablename__ = "topics_telegram"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    topic_id: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(String(200))
    group_id: Mapped[int] = mapped_column(BigInteger, default=0)  # 0 = grupo leads (default)
    agente_silenciado: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_mensaje_ivan: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Mensaje(Base):
    """Modelo de mensaje en la base de datos."""
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" o "assistant"
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Recordatorio(Base):
    """Recordatorio persistente — sobrevive reinicios de Railway."""
    __tablename__ = "recordatorios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    tipo: Mapped[str] = mapped_column(String(50))  # "clase", etc.
    programado_para: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC
    enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelado: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PagoPendiente(Base):
    """Pagos esperando confirmación del admin — persistente en PostgreSQL."""
    __tablename__ = "pagos_pendientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # "prueba" / "inscripcion"
    plan: Mapped[str] = mapped_column(String(50), default="")
    monto: Mapped[int] = mapped_column(Integer, default=0)
    media_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente/confirmado/rechazado
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MensajeProcesado(Base):
    """Deduplicación persistente de webhooks — sobrevive reinicios."""
    __tablename__ = "mensajes_procesados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mensaje_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    procesado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def crear_recordatorio(telefono: str, tipo: str, programado_para: datetime, payload: str) -> int:
    """Inserta un recordatorio y retorna su ID."""
    async with async_session() as session:
        rec = Recordatorio(telefono=telefono, tipo=tipo, programado_para=programado_para, payload=payload)
        session.add(rec)
        await session.commit()
        await session.refresh(rec)
        return rec.id


async def obtener_recordatorios_pendientes(ahora_utc: datetime) -> list[Recordatorio]:
    """Retorna recordatorios no enviados ni cancelados cuyo momento ya llegó."""
    async with async_session() as session:
        result = await session.execute(
            select(Recordatorio).where(
                Recordatorio.enviado == False,
                Recordatorio.cancelado == False,
                Recordatorio.programado_para <= ahora_utc,
            )
        )
        return list(result.scalars().all())


async def marcar_recordatorio_enviado(recordatorio_id: int):
    """Marca un recordatorio como enviado."""
    async with async_session() as session:
        result = await session.execute(
            select(Recordatorio).where(Recordatorio.id == recordatorio_id)
        )
        rec = result.scalar_one_or_none()
        if rec:
            rec.enviado = True
            await session.commit()


async def cancelar_recordatorios_por_telefono(telefono: str, tipo: str):
    """Marca como cancelados todos los recordatorios pendientes de este tipo."""
    async with async_session() as session:
        result = await session.execute(
            select(Recordatorio).where(
                Recordatorio.telefono == telefono,
                Recordatorio.tipo == tipo,
                Recordatorio.enviado == False,
                Recordatorio.cancelado == False,
            )
        )
        for rec in result.scalars().all():
            rec.cancelado = True
        await session.commit()


async def _migrar_columnas_nuevas():
    """
    Agrega columnas nuevas a tablas existentes (para bases de datos ya creadas).
    Solo se ejecuta en PostgreSQL — SQLite recrea el schema completo via create_all().
    SQLite no soporta ADD COLUMN IF NOT EXISTS.
    """
    if not _es_postgres:
        return
    nuevas = [
        ("conversaciones_ab", "airtable_record_id", "VARCHAR(50)"),
        ("conversaciones_ab", "familia_id",          "VARCHAR(50)"),
        ("conversaciones_ab", "agent_actual",        "VARCHAR(10) DEFAULT 'ivan'"),
        ("conversaciones_ab", "modo_nixie",          "VARCHAR(20)"),
        ("conversaciones_ab", "ventana_1_mensajes",  "INTEGER DEFAULT 0"),
        ("conversaciones_ab", "ventana_2_inicio",    "TIMESTAMP"),
        ("conversaciones_ab", "ventana_2_mensajes",  "INTEGER DEFAULT 0"),
        ("conversaciones_ab", "ventana_3_inicio",    "TIMESTAMP"),
        ("conversaciones_ab", "ventana_3_mensajes",  "INTEGER DEFAULT 0"),
        ("conversaciones_ab", "calendar_event_id",   "VARCHAR(200)"),
        ("conversaciones_ab", "noche_pendiente",     "BOOLEAN DEFAULT FALSE"),
        ("topics_telegram",   "group_id",             "BIGINT DEFAULT 0"),
        ("conversaciones_ab", "ctwa_clid",             "VARCHAR(200)"),
        ("conversaciones_ab", "ad_source_id",          "VARCHAR(100)"),
    ]
    for tabla, columna, tipo in nuevas:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}")
            )
    # Migrar group_id de INTEGER a BIGINT (IDs de Telegram exceden int32)
    async with engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE topics_telegram ALTER COLUMN group_id TYPE BIGINT")
        )


async def inicializar_db():
    """Crea las tablas si no existen y migra columnas nuevas."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrar_columnas_nuevas()


async def guardar_mensaje(telefono: str, role: str, content: str):
    """Guarda un mensaje en el historial de conversación."""
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    """
    Recupera los últimos N mensajes de una conversación.

    Args:
        telefono: Número de teléfono del cliente
        limite: Máximo de mensajes a recuperar (default: 20)

    Returns:
        Lista de diccionarios con role y content
    """
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()

        # Invertir para orden cronológico (los más recientes están primero)
        mensajes.reverse()

        return [
            {"role": msg.role, "content": msg.content}
            for msg in mensajes
        ]


# ── Pagos persistentes ────────────────────────────────────────────────────────

async def registrar_pago_pendiente_db(
    telefono: str, tipo: str, plan: str = "", monto: int = 0, media_id: str | None = None
):
    """Registra un pago pendiente en PostgreSQL."""
    async with async_session() as session:
        pago = PagoPendiente(
            telefono=telefono, tipo=tipo, plan=plan,
            monto=monto, media_id=media_id, estado="pendiente",
        )
        session.add(pago)
        await session.commit()


async def obtener_pago_pendiente_db(telefono: str | None = None) -> tuple[str | None, dict | None]:
    """Retorna (telefono, datos) del pago pendiente más reciente."""
    async with async_session() as session:
        q = select(PagoPendiente).where(PagoPendiente.estado == "pendiente")
        if telefono:
            q = q.where(PagoPendiente.telefono == telefono)
        q = q.order_by(PagoPendiente.creado_en.desc()).limit(1)
        result = await session.execute(q)
        pago = result.scalar_one_or_none()
        if not pago:
            return None, None
        return pago.telefono, {
            "id": pago.id, "tipo": pago.tipo, "plan": pago.plan,
            "monto": pago.monto, "media_id": pago.media_id,
            "ts": pago.creado_en,
        }


async def tiene_pago_pendiente_db(telefono: str | None = None) -> bool:
    """Verifica si hay pagos pendientes."""
    tel, datos = await obtener_pago_pendiente_db(telefono)
    return tel is not None


async def resolver_pago_db(telefono: str, estado: str) -> dict | None:
    """Confirma o rechaza un pago (estado='confirmado' o 'rechazado'). Retorna datos o None."""
    async with async_session() as session:
        q = (
            select(PagoPendiente)
            .where(PagoPendiente.telefono == telefono, PagoPendiente.estado == "pendiente")
            .order_by(PagoPendiente.creado_en.desc())
            .limit(1)
        )
        result = await session.execute(q)
        pago = result.scalar_one_or_none()
        if not pago:
            return None
        pago.estado = estado
        pago.resuelto_en = datetime.utcnow()
        await session.commit()
        return {"tipo": pago.tipo, "plan": pago.plan, "monto": pago.monto, "media_id": pago.media_id}


# ── Deduplicación persistente ─────────────────────────────────────────────────

async def mensaje_ya_procesado(mensaje_id: str) -> bool:
    """Verifica si un mensaje ya fue procesado (dedup persistente)."""
    async with async_session() as session:
        result = await session.execute(
            select(MensajeProcesado).where(MensajeProcesado.mensaje_id == mensaje_id)
        )
        return result.scalar_one_or_none() is not None


async def registrar_mensaje_procesado(mensaje_id: str):
    """Registra un mensaje como procesado."""
    async with async_session() as session:
        try:
            session.add(MensajeProcesado(mensaje_id=mensaje_id))
            await session.commit()
        except Exception:
            await session.rollback()  # duplicado — OK, ya estaba


async def borrar_mensaje_procesado(mensaje_id: str):
    """Borra un mensaje de la dedup (permite reintento si el procesamiento falló)."""
    async with async_session() as session:
        result = await session.execute(
            select(MensajeProcesado).where(MensajeProcesado.mensaje_id == mensaje_id)
        )
        msg = result.scalar_one_or_none()
        if msg:
            await session.delete(msg)
            await session.commit()


async def limpiar_mensajes_procesados_antiguos():
    """Limpia mensajes procesados de más de 24h (evitar que la tabla crezca infinito)."""
    from datetime import timedelta
    limite = datetime.utcnow() - timedelta(hours=24)
    async with async_session() as session:
        result = await session.execute(
            select(MensajeProcesado).where(MensajeProcesado.procesado_en < limite)
        )
        for m in result.scalars().all():
            await session.delete(m)
        await session.commit()


async def limpiar_historial(telefono: str):
    """Borra todo el historial de una conversación."""
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            await session.delete(msg)
        await session.commit()


async def limpiar_estado_completo(telefono: str):
    """
    Reset completo para un número: borra mensajes + fila de ConversacionAB.
    Después de llamar esto, el número se trata como lead 100% nuevo.
    """
    async with async_session() as session:
        # Borrar mensajes
        r1 = await session.execute(select(Mensaje).where(Mensaje.telefono == telefono))
        for msg in r1.scalars().all():
            await session.delete(msg)
        # Borrar fila de A/B test (variante, convertido, evento_creado, airtable_record_id…)
        r2 = await session.execute(select(ConversacionAB).where(ConversacionAB.telefono == telefono))
        conv = r2.scalar_one_or_none()
        if conv:
            await session.delete(conv)
        await session.commit()


# ── Meta CAPI — ctwa_clid ────────────────────────────────────────────────────

async def guardar_ctwa_clid(telefono: str, ctwa_clid: str):
    """Guarda el ctwa_clid del anuncio CTWA para este teléfono."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv and not conv.ctwa_clid:
            conv.ctwa_clid = ctwa_clid
            await session.commit()
            logger.info(f"[CAPI] ctwa_clid guardado para {telefono}: {ctwa_clid[:20]}...")


async def obtener_ctwa_clid(telefono: str) -> str | None:
    """Retorna el ctwa_clid guardado para este teléfono, o None."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.ctwa_clid).where(ConversacionAB.telefono == telefono)
        )
        return result.scalar_one_or_none()


# ── Ad Source ID (referral.source_id) ────────────────────────────────────────

async def guardar_ad_source_id(telefono: str, ad_source_id: str):
    """Guarda el ID del anuncio Meta que trajo a este lead."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB).where(ConversacionAB.telefono == telefono)
        )
        conv = result.scalar_one_or_none()
        if conv and not conv.ad_source_id:
            conv.ad_source_id = ad_source_id
            await session.commit()
            logger.info(f"[AD] ad_source_id guardado para {telefono}: {ad_source_id}")


async def obtener_ad_source_id(telefono: str) -> str | None:
    """Retorna el ID del anuncio Meta para este teléfono, o None."""
    async with async_session() as session:
        result = await session.execute(
            select(ConversacionAB.ad_source_id).where(ConversacionAB.telefono == telefono)
        )
        return result.scalar_one_or_none()
