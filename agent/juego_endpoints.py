# agent/juego_endpoints.py — Router /juego para Mundo Fenix (tótem, TV, profe, circuito NFC)
"""
Router AISLADO y ADITIVO. NO toca el webhook ni el flujo de leads/Aurora.

Es el canal de eventos del juego de La Casona (ver mundo-fenix/SPEC-TOTEM-Y-PROFE.md y
SPEC-NFC-CIRCUITO.md). Fase A: solo el ledger de eventos + su lectura.

  POST /juego/evento            {tipo, nino_nombre?, guardian?, payload?} → crea evento
  GET  /juego/eventos?since=N   → eventos con id > N (polling de TV/mapa, CORS abierto)

La TV y el mapa hacen polling del GET cada ~2s. El POST lo usan el profe, el tótem y
(fases siguientes) los checkpoints NFC. Mantener este archivo sin lógica de leads.

Auth del POST: header `X-JUEGO-KEY` == env `JUEGO_API_KEY`. Sin la env var, el router
queda cerrado (fail-closed, 503). El GET es público: solo nombres de pila y eventos del
juego, sin teléfonos ni datos sensibles.
"""

import os
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Body
from fastapi.responses import JSONResponse
from sqlalchemy import String, Text, DateTime, Integer, select
from sqlalchemy.orm import Mapped, mapped_column

from agent.memory import Base, async_session

logger = logging.getLogger("agentkit")
router = APIRouter()

JUEGO_API_KEY = os.getenv("JUEGO_API_KEY", "")

# Tipos de evento que la TV sabe celebrar (+ los del circuito NFC)
TIPOS_VALIDOS = {"llegada", "vuelta", "dragon", "tesoro", "estacion", "progreso"}

# CORS: la TV/mapa viven en otro origen (Cloudflare Pages / localhost)
_CORS = {"Access-Control-Allow-Origin": "*"}


class JuegoEvento(Base):
    """Ledger de eventos del juego — la TV los lee por polling y los celebra."""
    __tablename__ = "juego_eventos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(20))                       # llegada|vuelta|...
    nino_nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guardian: Mapped[str | None] = mapped_column(String(30), nullable=True)  # mamba|aura|...
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON extra (estacion_id, vueltas, sub...)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _auth(x_juego_key: str | None):
    if not JUEGO_API_KEY:
        raise HTTPException(status_code=503, detail="juego no configurado")
    if not x_juego_key or x_juego_key != JUEGO_API_KEY:
        raise HTTPException(status_code=401, detail="no autorizado")


async def crear_evento(tipo: str, nino_nombre: str | None = None,
                       guardian: str | None = None, payload: dict | None = None) -> int:
    """Inserta un evento del juego. Lo usan este router y (fases B+) el checkin/NFC."""
    async with async_session() as session:
        ev = JuegoEvento(
            tipo=tipo,
            nino_nombre=(nino_nombre or None),
            guardian=(guardian or None),
            payload=json.dumps(payload, ensure_ascii=False) if payload else None,
            timestamp=datetime.utcnow(),
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        logger.info(f"[JUEGO] evento #{ev.id} {tipo} {nino_nombre or ''}")
        return ev.id


@router.post("/juego/evento")
async def juego_evento(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """Crea un evento (profe/tótem). La TV lo levanta en el próximo poll."""
    _auth(x_juego_key)
    tipo = str(payload.get("tipo", "")).strip().lower()
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"tipo inválido (usar: {', '.join(sorted(TIPOS_VALIDOS))})")
    nombre = str(payload.get("nino_nombre", "") or "").strip()[:120]
    guardian = str(payload.get("guardian", "") or "").strip()[:30]
    extra = payload.get("payload") if isinstance(payload.get("payload"), dict) else None
    ev_id = await crear_evento(tipo, nombre, guardian, extra)
    return {"ok": True, "id": ev_id}


@router.get("/juego/eventos")
async def juego_eventos(since: int = 0):
    """Polling de la TV/mapa. since=0 → no repite historia: devuelve solo el último id
    para que el cliente arranque desde 'ahora'. Con since>0 devuelve lo nuevo."""
    async with async_session() as session:
        if since <= 0:
            ultimo = await session.execute(
                select(JuegoEvento.id).order_by(JuegoEvento.id.desc()).limit(1))
            max_id = ultimo.scalar() or 0
            return JSONResponse(content={"eventos": [], "ultimo": max_id}, headers=_CORS)

        # solo eventos nuevos y recientes (una TV que vuelve de horas dormida no replay-ea el día)
        corte = datetime.utcnow() - timedelta(minutes=30)
        q = (select(JuegoEvento)
             .where(JuegoEvento.id > since, JuegoEvento.timestamp >= corte)
             .order_by(JuegoEvento.id.asc()).limit(100))
        rows = (await session.execute(q)).scalars().all()

    eventos, max_id = [], since
    for ev in rows:
        max_id = max(max_id, ev.id)
        item = {"id": ev.id, "tipo": ev.tipo, "nino_nombre": ev.nino_nombre or "",
                "guardian": ev.guardian or ""}
        if ev.payload:
            try:
                item["payload"] = json.loads(ev.payload)
            except (json.JSONDecodeError, TypeError):
                pass
        eventos.append(item)
    return JSONResponse(content={"eventos": eventos, "ultimo": max_id}, headers=_CORS)
