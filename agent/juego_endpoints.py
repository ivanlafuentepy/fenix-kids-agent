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
from sqlalchemy import String, Text, DateTime, Integer, Boolean, select
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


# ═══════════════════════ CIRCUITO NFC (Fase N1, SPEC-NFC-CIRCUITO) ═══════════════════════
# v1: pulseras/pasadas/vueltas en Postgres. La plata se emite como evento;
# el ledger migra a Airtable cuando exista F2 (los endpoints no cambian).

# Config del circuito — editable por env var sin tocar código
ESTACIONES_ACTIVAS = [e.strip() for e in os.getenv(
    "JUEGO_ESTACIONES", "ninja,arbol,basket,quincho,muelle").split(",") if e.strip()]
TIEMPO_MIN_SEG = int(os.getenv("JUEGO_TIEMPO_MIN_SEG", "60"))       # anti tap-tap-tap
COOLDOWN_LLEGADA_MIN = 5                                             # no duplicar llegadas
PLATA_VUELTA = 100                                                   # PLAN-MAESTRO 6
BONUS_5_VUELTAS = 200
BONUS_10_VUELTAS = 500


class Pulsera(Base):
    """Vínculo UID físico (botón NFC) → niño. El mapa físico→digital."""
    __tablename__ = "pulseras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # hex mayúsculas
    nino_nombre: Mapped[str] = mapped_column(String(120))
    guardian: Mapped[str | None] = mapped_column(String(30), nullable=True)
    nino_airtable_id: Mapped[str | None] = mapped_column(String(50), nullable=True)  # link futuro
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JuegoPasada(Base):
    """Ledger crudo: cada tap de muñequera en una estación (auditoría + VAR)."""
    __tablename__ = "juego_pasadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(40), index=True)
    estacion_id: Mapped[str] = mapped_column(String(30))
    valida: Mapped[bool] = mapped_column(Boolean, default=True)      # False = tiempo mínimo violado
    rezagada: Mapped[bool] = mapped_column(Boolean, default=False)   # cola offline del ESP32
    vuelta_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # se setea al cerrar
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)  # hora del SERVIDOR


class JuegoVuelta(Base):
    """Una fila por vuelta CERRADA en el tótem (el niño reclamó y Fenix corroboró)."""
    __tablename__ = "juego_vueltas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(40), index=True)
    nino_nombre: Mapped[str] = mapped_column(String(120))
    numero_dia: Mapped[int] = mapped_column(Integer, default=1)      # n° de vuelta del día
    estaciones_ok: Mapped[int] = mapped_column(Integer, default=0)
    plata: Mapped[int] = mapped_column(Integer, default=0)           # acreditado (evento; ledger F2)
    cerrada: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _norm_uid(uid: str) -> str:
    """UID normalizado: hex mayúsculas sin separadores (04A2B3C4D5)."""
    return "".join(c for c in str(uid).upper() if c.isalnum())[:40]


async def _pulsera_por_uid(session, uid: str) -> "Pulsera | None":
    r = await session.execute(select(Pulsera).where(Pulsera.uid == uid, Pulsera.activa == True))  # noqa: E712
    return r.scalar_one_or_none()


async def _pasadas_abiertas(session, uid: str) -> list["JuegoPasada"]:
    """Pasadas válidas del uid que aún no pertenecen a ninguna vuelta cerrada."""
    r = await session.execute(
        select(JuegoPasada).where(
            JuegoPasada.uid == uid,
            JuegoPasada.vuelta_id.is_(None),
            JuegoPasada.valida == True,  # noqa: E712
            JuegoPasada.estacion_id != "_llegada",   # las llegadas no son estaciones
        ).order_by(JuegoPasada.timestamp.asc()))
    return list(r.scalars().all())


@router.post("/juego/nfc-vincular")
async def nfc_vincular(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """Onboarding: asocia un botón NFC a un niño. Falla si el UID ya es de otro."""
    _auth(x_juego_key)
    uid = _norm_uid(payload.get("uid", ""))
    nombre = str(payload.get("nino_nombre", "") or "").strip()[:120]
    guardian = str(payload.get("guardian", "") or "").strip()[:30] or None
    if not uid or not nombre:
        raise HTTPException(status_code=422, detail="uid y nino_nombre requeridos")
    async with async_session() as session:
        existente = await session.execute(select(Pulsera).where(Pulsera.uid == uid))
        p = existente.scalar_one_or_none()
        if p and p.activa and p.nino_nombre != nombre:
            raise HTTPException(status_code=409, detail=f"UID ya vinculado a {p.nino_nombre}")
        if p:
            p.nino_nombre, p.guardian, p.activa = nombre, guardian, True
        else:
            session.add(Pulsera(uid=uid, nino_nombre=nombre, guardian=guardian))
        await session.commit()
    logger.info(f"[JUEGO] pulsera {uid} vinculada a {nombre}")
    return {"ok": True, "uid": uid, "nino_nombre": nombre}


@router.post("/juego/estacion")
async def juego_estacion(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """Tap en una estación: registra la PASADA (timestamp del servidor). NO cierra vueltas.
    Dedupe por vuelta abierta + tiempo mínimo entre estaciones (anti tap-tap-tap)."""
    _auth(x_juego_key)
    uid = _norm_uid(payload.get("uid", ""))
    estacion = str(payload.get("estacion_id", "")).strip().lower()
    rezagada = bool(payload.get("rezagada", False))
    if not uid or estacion not in ESTACIONES_ACTIVAS:
        raise HTTPException(status_code=422, detail=f"uid y estacion_id válidos requeridos ({', '.join(ESTACIONES_ACTIVAS)})")

    async with async_session() as session:
        p = await _pulsera_por_uid(session, uid)
        if not p:
            return {"ok": False, "motivo": "pulsera_no_vinculada"}

        abiertas = await _pasadas_abiertas(session, uid)
        ya_tocadas = {x.estacion_id for x in abiertas}
        if estacion in ya_tocadas:                       # dedupe: la misma estación cuenta 1
            faltan = [e for e in ESTACIONES_ACTIVAS if e not in ya_tocadas]
            return {"ok": True, "duplicada": True,
                    "estaciones_completadas": len(ya_tocadas), "faltan": faltan}

        # tiempo mínimo desde la última pasada válida (rezagadas nunca validan solas)
        valida = not rezagada
        if valida and abiertas:
            gap = (datetime.utcnow() - abiertas[-1].timestamp).total_seconds()
            if gap < TIEMPO_MIN_SEG:
                valida = False
        session.add(JuegoPasada(uid=uid, estacion_id=estacion, valida=valida, rezagada=rezagada))
        await session.commit()

        completadas = len(ya_tocadas) + (1 if valida else 0)
        faltan = [e for e in ESTACIONES_ACTIVAS if e not in ya_tocadas and (e != estacion or not valida)]

    if valida:  # el mapa mueve el avatar solo con pasadas válidas
        await crear_evento("estacion", p.nino_nombre, p.guardian, {"estacion_id": estacion})
    return {"ok": True, "valida": valida, "estaciones_completadas": completadas, "faltan": faltan}


@router.post("/juego/totem-nfc")
async def juego_totem_nfc(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """EL tap del tótem: (1) llegada del día (cooldown 5 min) y (2) SIEMPRE evalúa el
    circuito — completo → cierra la VUELTA acá (Fenix corrobora) y celebra; si no,
    evento `progreso` con lo que falta."""
    _auth(x_juego_key)
    uid = _norm_uid(payload.get("uid", ""))
    if not uid:
        raise HTTPException(status_code=422, detail="uid requerido")

    async with async_session() as session:
        p = await _pulsera_por_uid(session, uid)
        if not p:
            return {"ok": False, "motivo": "pulsera_no_vinculada"}

        hoy0 = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # (1) llegada — solo la primera del día genera evento (más estricto que el cooldown)
        llegada_evento = False
        ya = await session.execute(select(JuegoPasada.id).where(
            JuegoPasada.uid == uid, JuegoPasada.estacion_id == "_llegada",
            JuegoPasada.timestamp >= hoy0).limit(1))
        if ya.scalar() is None:
            session.add(JuegoPasada(uid=uid, estacion_id="_llegada", valida=True, vuelta_id=0))
            llegada_evento = True

        # (2) circuito — ¿tiene todas las estaciones?
        abiertas = await _pasadas_abiertas(session, uid)
        tocadas = {x.estacion_id for x in abiertas if x.estacion_id in ESTACIONES_ACTIVAS}
        faltan = [e for e in ESTACIONES_ACTIVAS if e not in tocadas]

        vuelta_info = None
        if not faltan and tocadas:
            n_hoy = await session.execute(
                select(JuegoVuelta).where(JuegoVuelta.uid == uid, JuegoVuelta.cerrada >= hoy0))
            numero = len(list(n_hoy.scalars().all())) + 1
            plata = PLATA_VUELTA + (BONUS_5_VUELTAS if numero == 5 else 0) + (BONUS_10_VUELTAS if numero == 10 else 0)
            v = JuegoVuelta(uid=uid, nino_nombre=p.nino_nombre, numero_dia=numero,
                            estaciones_ok=len(tocadas), plata=plata)
            session.add(v)
            await session.flush()
            for pas in abiertas:                          # las pasadas quedan selladas a esta vuelta
                pas.vuelta_id = v.id
            vuelta_info = {"numero": numero, "plata": plata}
        await session.commit()

    # eventos fuera de la transacción (best-effort, la TV los celebra)
    if llegada_evento:
        await crear_evento("llegada", p.nino_nombre, p.guardian, {"via": "nfc"})
    if vuelta_info:
        sub = f"¡Bonus de {vuelta_info['numero']} vueltas!" if vuelta_info["numero"] in (5, 10) else ""
        await crear_evento("vuelta", p.nino_nombre, p.guardian,
                           {"v": vuelta_info["numero"], "coins": f"+{vuelta_info['plata']} 🥈", "sub": sub})
        return {"ok": True, "vuelta_cerrada": True, **vuelta_info, "llegada": llegada_evento}
    if faltan and len(faltan) < len(ESTACIONES_ACTIVAS):
        await crear_evento("progreso", p.nino_nombre, p.guardian, {"faltan": faltan})
    return {"ok": True, "vuelta_cerrada": False, "faltan": faltan, "llegada": llegada_evento}


@router.post("/juego/checkin-face")
async def juego_checkin_face(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """El Espejo del Guardián (tablet): foto → Rekognition → llegada + asistencia.
    Cooldown 5 min por niño (toca 20 veces = 1 llegada). Ver SPEC-TOTEM 4A."""
    _auth(x_juego_key)
    foto_b64 = str(payload.get("foto_base64", ""))
    if "," in foto_b64[:80]:                      # tolera data:image/jpeg;base64,...
        foto_b64 = foto_b64.split(",", 1)[1]
    try:
        import base64
        image_bytes = base64.b64decode(foto_b64)
    except Exception:
        raise HTTPException(status_code=422, detail="foto_base64 inválida")
    if not image_bytes or len(image_bytes) > 5_000_000:
        raise HTTPException(status_code=422, detail="foto vacía o >5MB")

    from agent.face_recognition import identificar_ninos
    matches = await identificar_ninos(image_bytes, threshold=80.0)
    if not matches:
        return {"ok": False, "motivo": "no_reconocido"}
    best = max(matches, key=lambda m: m.get("confidence", 0))
    nino_id = best["nino_id"]

    # nombre del niño desde Airtable
    from agent.airtable_client import _BASE_URL, _NINOS, _headers
    import httpx
    nombre = ""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_BASE_URL}/{_NINOS}/{nino_id}", headers=_headers(), timeout=10)
            if r.status_code == 200:
                nombre = (r.json().get("fields", {}).get("NOMBRE") or "").strip()
    except Exception as e:
        logger.warning(f"[JUEGO] checkin-face: no pude leer niño {nino_id}: {e}")
    if not nombre:
        return {"ok": False, "motivo": "nino_sin_datos"}

    # cooldown 5 min por niño
    async with async_session() as session:
        corte = datetime.utcnow() - timedelta(minutes=COOLDOWN_LLEGADA_MIN)
        r = await session.execute(select(JuegoEvento.id).where(
            JuegoEvento.tipo == "llegada", JuegoEvento.nino_nombre == nombre,
            JuegoEvento.timestamp >= corte).limit(1))
        if r.scalar() is not None:
            return {"ok": True, "nino": {"id": nino_id, "nombre": nombre},
                    "repetido": True, "confidence": round(best["confidence"], 1)}

    # asistencia real (best-effort — nunca rompe el saludo)
    try:
        from zoneinfo import ZoneInfo
        from agent.airtable_client import crear_asistencia
        ahora_py = datetime.now(ZoneInfo("America/Asuncion"))
        await crear_asistencia(nombre=nombre, fecha_iso=ahora_py.date().isoformat(),
                               hora_checkin_iso=ahora_py.isoformat(),
                               nino_id=nino_id, metodo="FACE")
    except Exception as e:
        logger.warning(f"[JUEGO] checkin-face: asistencia falló para {nombre}: {e}")

    await crear_evento("llegada", nombre, None,
                       {"via": "face", "conf": round(best["confidence"], 1)})
    return {"ok": True, "nino": {"id": nino_id, "nombre": nombre},
            "confidence": round(best["confidence"], 1)}


@router.get("/juego/alumnos")
async def juego_alumnos(x_juego_key: str | None = Header(default=None)):
    """Lista {id, nombre, apodo} de NIÑOS FENIX para el selector del profe. Requiere key."""
    _auth(x_juego_key)
    from agent.airtable_client import _get_records, _NINOS
    records = await _get_records(_NINOS, max_records=500)
    alumnos = []
    for rec in records:
        f = rec.get("fields", {})
        nombre = (f.get("NOMBRE") or "").strip()
        if not nombre:
            continue
        alumnos.append({"id": rec.get("id", ""), "nombre": nombre,
                        "apodo": (f.get("APODO") or "").strip(),
                        "apellido": (f.get("APELLIDO") or "").strip()})
    alumnos.sort(key=lambda a: a["nombre"])
    return {"alumnos": alumnos}


@router.get("/juego/estaciones")
async def juego_estaciones():
    """Config del circuito activo (para /profe, el mapa y los ESP32)."""
    return JSONResponse(content={"estaciones": ESTACIONES_ACTIVAS, "tiempo_min_seg": TIEMPO_MIN_SEG},
                        headers=_CORS)


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
