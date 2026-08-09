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
from sqlalchemy import String, Text, DateTime, Integer, Boolean, Float, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from agent.memory import Base, async_session

logger = logging.getLogger("agentkit")
router = APIRouter()

JUEGO_API_KEY = os.getenv("JUEGO_API_KEY", "")

# Tipos de evento que la TV sabe celebrar (+ los del circuito NFC)
TIPOS_VALIDOS = {"llegada", "vuelta", "dragon", "tesoro", "estacion", "progreso"}

# CORS: la TV/mapa/app viven en otro origen (Cloudflare Pages / localhost)
_CORS = {"Access-Control-Allow-Origin": "*"}
_CORS_PREFLIGHT = {**_CORS, "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                   "Access-Control-Allow-Headers": "Content-Type, X-JUEGO-KEY"}


class JuegoEvento(Base):
    """Ledger de eventos del juego — la TV los lee por polling y los celebra."""
    __tablename__ = "juego_eventos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(20))                       # llegada|vuelta|...
    nino_nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guardian: Mapped[str | None] = mapped_column(String(30), nullable=True)  # mamba|aura|...
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON extra (estacion_id, vueltas, sub...)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FotoWebTag(Base):
    """Mapeo foto pública del catálogo web → niño que aparece en ella.
    PRIVADO: solo se sirve tras validar el código de familia (link mágico).
    Lo escribe scripts/taggear_fotos_web.py (Rekognition batch, local)."""
    __tablename__ = "fotos_web_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    archivo: Mapped[str] = mapped_column(String(60), index=True)        # "foto-0123.jpg"
    nino_id: Mapped[str] = mapped_column(String(30), index=True)        # record id Airtable — NUNCA nombre
    confidence: Mapped[float] = mapped_column(Float)
    fecha_foto: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "2026-03-21" (manifest EXIF)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("archivo", "nino_id", name="uq_fotoweb_archivo_nino"),)


class FotoWebProcesada(Base):
    """Fotos ya pasadas por Rekognition (incluye las sin match) — permite
    corridas incrementales semanales sin re-procesar ni re-pagar."""
    __tablename__ = "fotos_web_procesadas"

    archivo: Mapped[str] = mapped_column(String(60), primary_key=True)
    caras_detectadas: Mapped[int] = mapped_column(Integer, default=0)
    matches: Mapped[int] = mapped_column(Integer, default=0)
    procesado_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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


# ═══════════════════ MUNDO FENIX APP — F2: identidad de familia (link mágico) ═══════════════════
# Tablas creadas 07/07 vía MCP. Regla: la app NUNCA escribe Airtable directo — solo Railway.

_T_GUARDIANES = "GUARDIANES FENIX"
_T_MOVIMIENTOS = "MOVIMIENTOS BRASAS FENIX"
_T_DESAFIOS = "DESAFIOS CUMPLIDOS FENIX"
APP_URL = "https://mundo-fenix.pages.dev"

# alfabeto sin ambiguos (0/O, 1/I/L) — el código lo tipean padres en un celular
_ALFA_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _limpiar_codigo(codigo: str) -> str:
    return "".join(c for c in str(codigo).upper() if c.isalnum())[:12]


async def _tutor_por_codigo(codigo: str) -> dict | None:
    """Etapa 2 (2026-08-09): el código del link mágico vive en la fila del
    tutor en ALUMNOS ({CODIGO FENIX}). TUTORES FENIX quedó legacy y ya no se
    consulta — los códigos repartidos se backfillearon a ALUMNOS
    (scripts/backfill_tutores_a_alumnos.py)."""
    from agent.airtable_client import _get_records, _ALUMNOS
    codigo = _limpiar_codigo(codigo)
    if len(codigo) < 4:
        return None
    recs = await _get_records(_ALUMNOS, formula=f"{{CODIGO FENIX}}='{codigo}'", max_records=1)
    return recs[0] if recs else None


async def _hijo_ids_de_tutor(tutor: dict) -> list[str]:
    """IDs de los hijos del tutor (fila de ALUMNOS): links directos
    HIJOS FENIX (PADRE)/(MADRE). Fallback por teléfono para personas con más
    de una fila en ALUMNOS (los hijos pueden estar linkeados en la otra —
    buscar_tutor_por_telefono elige la mejor)."""
    from agent.airtable_client import buscar_tutor_por_telefono, _hijos_de_tutor
    tf = tutor.get("fields", {}) or {}
    hijos = _hijos_de_tutor(tf)
    if hijos:
        return hijos
    tel = (tf.get("TELEFONO LIMPIO") or tf.get("TELEFONO2 LIMPIO") or "").strip()
    if not tel:
        return []
    alumno = await buscar_tutor_por_telefono(tel)
    if not alumno:
        return []
    return _hijos_de_tutor(alumno.get("fields", {}) or {})


async def _guardian_de_nino(nino_id: str, nombre: str) -> dict | None:
    """Busca (o crea stub) la fila GUARDIANES del niño. Filtra por NINO ID texto
    (los campos link no se pueden filtrar — regla airtable-seguro)."""
    from agent.airtable_client import _get_records, _post
    recs = await _get_records(_T_GUARDIANES, formula=f"{{NINO ID}}='{nino_id}'", max_records=1)
    if recs:
        return recs[0]
    return await _post(_T_GUARDIANES, {
        "NOMBRE": nombre, "NINO ID": nino_id, "NIÑO": [nino_id],
        "STAGE": "builder", "ORO": 0, "PLATA": 0, "DRAGONES TOTAL": 0,
        "RETO DIA": 1, "RETO DONE": 0, "MES": 1, "ESTADO JSON": "{}",
    })


def _guardian_publico(g: dict) -> dict:
    """Proyección del guardian para la app (sin nada sensible)."""
    f = g.get("fields", {})
    try:
        estado = json.loads(f.get("ESTADO JSON") or "{}")
    except (json.JSONDecodeError, TypeError):
        estado = {}
    return {
        "guardian_id": g.get("id", ""),
        "robot": f.get("ROBOT") or None,
        "stage": f.get("STAGE") or "builder",
        "oro": int(f.get("ORO") or 0),
        "plata": int(f.get("PLATA") or 0),
        "dragones_total": int(f.get("DRAGONES TOTAL") or 0),
        "reto_dia": int(f.get("RETO DIA") or 1),
        "reto_done": int(f.get("RETO DONE") or 0),
        "mes": int(f.get("MES") or 1),
        "estado": estado,
    }


@router.post("/juego/familia-codigo")
async def juego_familia_codigo(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """Genera (o devuelve) el link mágico de un tutor (F5: código por tutor).
    Body: {telefono | tutor_id}."""
    _auth(x_juego_key)
    from agent.airtable_client import (
        _patch, _ALUMNOS, _BASE_URL, _headers, buscar_tutor_por_telefono,
    )
    import httpx, secrets

    # Etapa 2 (09/08): el código vive en la fila de ALUMNOS del tutor — se
    # acabaron los stubs en TUTORES (creaban filas duplicadas de la persona).
    # payload.tutor_id ahora es un record id de ALUMNOS.
    tutor = None
    if payload.get("tutor_id"):
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_BASE_URL}/{_ALUMNOS}/{payload['tutor_id']}", headers=_headers(), timeout=10)
            if r.status_code == 200:
                tutor = r.json()
    elif payload.get("telefono"):
        tutor = await buscar_tutor_por_telefono(str(payload["telefono"]))
    if not tutor:
        raise HTTPException(status_code=404, detail="tutor no encontrado")

    codigo = (tutor.get("fields", {}).get("CODIGO FENIX") or "").strip()
    if not codigo:
        for _ in range(5):  # colisión improbable (31^6) pero verificamos
            candidato = "".join(secrets.choice(_ALFA_CODIGO) for _ in range(6))
            if not await _tutor_por_codigo(candidato):
                codigo = candidato
                break
        if not codigo:
            raise HTTPException(status_code=500, detail="no pude generar código único")
        ok = await _patch(_ALUMNOS, tutor["id"], {"CODIGO FENIX": codigo})
        if not ok:
            raise HTTPException(status_code=502, detail="no pude guardar el código")
        logger.info(f"[JUEGO] código {codigo} → tutor {tutor['id']}")
    return {"ok": True, "codigo": codigo, "url": f"{APP_URL}/?f={codigo}"}


@router.get("/juego/familia/{codigo}")
async def juego_familia(codigo: str):
    """La app arranca acá: código → tutor → sus hijos con su guardian (stub si
    es nuevo). Público con CORS — el código ES la auth del tutor. Sin datos
    sensibles. (F5: los hijos salen de los links del tutor, no de FAMILIAS.)"""
    tutor = await _tutor_por_codigo(codigo)
    if not tutor:
        return JSONResponse(content={"ok": False, "motivo": "codigo_invalido"}, status_code=404, headers=_CORS)

    from agent.airtable_client import _BASE_URL, _headers, _NINOS, _nino_a_dict
    from zoneinfo import ZoneInfo
    import httpx
    hoy = datetime.now(ZoneInfo("America/Asuncion")).date()
    hijos = []
    async with httpx.AsyncClient() as client:
        for hid in await _hijo_ids_de_tutor(tutor):
            try:
                r = await client.get(f"{_BASE_URL}/{_NINOS}/{hid}", headers=_headers(), timeout=10)
                if r.status_code != 200:
                    continue
                nino = _nino_a_dict(hid, r.json().get("fields", {}))
            except Exception as e:
                logger.error(f"[JUEGO] Error leyendo hijo {hid}: {e}")
                continue
            if not nino.get("nombre"):
                continue
            edad = None
            if nino.get("fecha_nacimiento"):
                try:
                    nac = datetime.fromisoformat(nino["fecha_nacimiento"]).date()
                    edad = hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
                except (ValueError, TypeError):
                    pass
            g = await _guardian_de_nino(nino["id"], nino["nombre"])
            if not g:
                continue
            hijos.append({"nino_id": nino["id"], "nombre": nino["nombre"],
                          "apodo": nino.get("apodo") or "", "edad": edad,
                          "guardian": _guardian_publico(g)})
    _apellido_t = (tutor.get("fields", {}).get("APELLIDO") or "").strip()
    return JSONResponse(content={
        "ok": True, "codigo": _limpiar_codigo(codigo),
        "familia": f"Familia {_apellido_t}".strip() if _apellido_t else "Familia",
        "hijos": hijos,
    }, headers=_CORS)


# ═══════════════════ FOTOS POR FAMILIA — catálogo web filtrado por hijos ═══════════════════
# Las fotos son públicas en fenixkidsacademy.com/fotos/; lo PRIVADO es el mapeo
# foto→niño (fotos_web_tags). Solo se sirve tras validar el código del tutor.

FOTOS_MIN_CONF = 80.0   # los tags se guardan desde 70 (auditables); se sirven desde 80
FOTOS_BASE_URL = "https://cdn.fenixkidsacademy.com"   # bucket R2 fenix-fotos (thumb/ y full/)


@router.get("/juego/fotos/{codigo}")
async def juego_fotos_familia(codigo: str):
    """Fotos del catálogo web donde aparecen los hijos del tutor. Público con
    CORS — el código ES la auth (mismo modelo que /juego/familia). Response
    mínimo: sin apellidos ni teléfonos, nombres solo de los propios hijos."""
    tutor = await _tutor_por_codigo(codigo)
    if not tutor:
        return JSONResponse(content={"ok": False, "motivo": "codigo_invalido"}, status_code=404, headers=_CORS)

    hijo_ids = await _hijo_ids_de_tutor(tutor)
    hijos = []
    if hijo_ids:
        from agent.airtable_client import _BASE_URL, _headers, _NINOS
        import httpx
        async with httpx.AsyncClient() as client:
            for hid in hijo_ids:
                try:
                    r = await client.get(f"{_BASE_URL}/{_NINOS}/{hid}", headers=_headers(), timeout=10)
                    if r.status_code != 200:
                        continue
                    f = r.json().get("fields", {})
                    nombre = (f.get("APODO") or f.get("NOMBRE") or "").strip()
                    if nombre:
                        hijos.append({"nino_id": hid, "nombre": nombre})
                except Exception as e:
                    logger.warning(f"[JUEGO] fotos: no pude leer hijo {hid}: {e}")

    fotos: dict[str, dict] = {}
    if hijo_ids:
        async with async_session() as session:
            rows = (await session.execute(
                select(FotoWebTag.archivo, FotoWebTag.fecha_foto, FotoWebTag.nino_id)
                .where(FotoWebTag.nino_id.in_(hijo_ids))
                .where(FotoWebTag.confidence >= FOTOS_MIN_CONF)
            )).all()
        for archivo, fecha_foto, nino_id in rows:
            item = fotos.setdefault(archivo, {"archivo": archivo, "fecha": fecha_foto, "ninos": []})
            if nino_id not in item["ninos"]:
                item["ninos"].append(nino_id)

    orden = sorted(fotos.values(), key=lambda x: (x["fecha"] or "", x["archivo"]), reverse=True)
    return JSONResponse(content={
        "ok": True,
        "familia": "Familia",
        "hijos": hijos,
        "base_url": FOTOS_BASE_URL,
        "fotos": orden,
    }, headers=_CORS)


# ═══════════════════ MUNDO FENIX APP — F2/P3: acciones del juego (el dinero vive acá) ═══════════════════
# Montos del PLAN-MAESTRO §6. La app manda {codigo, nino_id, accion, detalle} y repinta
# con la verdad del servidor. Anti-duplicado diario en ESTADO JSON (fecha PY).

ROBOTS_VALIDOS = {"mamba", "sophie", "apolo", "furia", "maikol", "nina",
                  "drakon", "flash", "shakira", "aura"}
DRAGONES_IDS = {"pigrus", "timor", "khaos", "dubius"}
PLATA_RETO_DIA = 50
BONUS_RETO_5 = 250
ENTRADA_CEREMONIA = 500
PLATA_MISION_CASA = 50
PLATA_PISTA = 50
PLATA_TESORO = 300
PLATA_DRAGON = 200
CASA_META = 3
ORO_LLEGADA = 10          # PLAN-MAESTRO §6: "el oro es por VENIR" — asistir al sábado


def _hoy_py() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Asuncion")).date().isoformat()


def _hoy0_utc() -> datetime:
    """Medianoche de HOY en Paraguay expresada en UTC naive — comparable con los
    timestamps de la DB (que se guardan con utcnow)."""
    from zoneinfo import ZoneInfo
    from datetime import timezone
    hoy0 = datetime.now(ZoneInfo("America/Asuncion")).replace(hour=0, minute=0,
                                                              second=0, microsecond=0)
    return hoy0.astimezone(timezone.utc).replace(tzinfo=None)


async def _validar_nino_de_familia(codigo: str, nino_id: str):
    """codigo → tutor; el niño DEBE ser hijo suyo (links PADRE/MADRE, F5).
    Devuelve (tutor, guardian)."""
    tutor = await _tutor_por_codigo(codigo)
    if not tutor:
        raise HTTPException(status_code=404, detail="codigo_invalido")
    if nino_id not in await _hijo_ids_de_tutor(tutor):
        raise HTTPException(status_code=403, detail="nino_no_es_de_esta_familia")
    from agent.airtable_client import _get_records
    recs = await _get_records(_T_GUARDIANES, formula=f"{{NINO ID}}='{nino_id}'", max_records=1)
    if not recs:
        raise HTTPException(status_code=404, detail="guardian_no_existe")
    return tutor, recs[0]


async def _acreditar(guardian: dict, moneda: str, monto: int, motivo: str,
                     cambios_extra: dict | None = None, desafio: dict | None = None) -> dict:
    """Única puerta al dinero: PATCH saldo en GUARDIANES + fila en MOVIMIENTOS
    (+DESAFIOS si aplica). Devuelve los fields actualizados."""
    from agent.airtable_client import _patch, _post
    f = guardian.get("fields", {})
    campo = "ORO" if moneda == "oro" else "PLATA"
    nuevo_saldo = int(f.get(campo) or 0) + monto
    if nuevo_saldo < 0:
        raise HTTPException(status_code=409, detail=f"saldo_insuficiente_{moneda}")
    cambios = {campo: nuevo_saldo}
    if cambios_extra:
        cambios.update(cambios_extra)
    # "Ganado hoy" para el video: acumula SOLO ganancias (monto>0), reset por día PY.
    # Merge sobre el ESTADO JSON que el caller ya haya puesto en cambios_extra (para
    # no pisar ult_oro_llegada / ult_reto_dia / etc.). Cae también en oro y plata.
    if monto > 0:
        _src = cambios.get("ESTADO JSON")
        if _src is None:
            _src = f.get("ESTADO JSON") or "{}"
        try:
            _est_hoy = json.loads(_src)
        except (json.JSONDecodeError, TypeError):
            _est_hoy = {}
        _hoy = _hoy_py()
        if _est_hoy.get("hoy_fecha") != _hoy:
            _est_hoy["hoy_fecha"] = _hoy
            _est_hoy["hoy_oro"] = 0
            _est_hoy["hoy_plata"] = 0
        _est_hoy["hoy_" + moneda] = int(_est_hoy.get("hoy_" + moneda, 0)) + monto
        cambios["ESTADO JSON"] = json.dumps(_est_hoy, ensure_ascii=False)
    ok = await _patch(_T_GUARDIANES, guardian["id"], cambios)
    if not ok:
        raise HTTPException(status_code=502, detail="airtable_no_respondio")
    await _post(_T_MOVIMIENTOS, {"MOTIVO": motivo, "GUARDIAN": [guardian["id"]],
                                 "GUARDIAN ID": guardian["id"], "MONEDA": moneda, "MONTO": monto})
    if desafio:
        await _post(_T_DESAFIOS, {**desafio, "GUARDIAN": [guardian["id"]],
                                  "GUARDIAN ID": guardian["id"], "ESTADO": "acreditado"})
    f.update(cambios)
    return f


def _estado_de(guardian: dict) -> dict:
    try:
        return json.loads(guardian.get("fields", {}).get("ESTADO JSON") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


async def _guardar_estado(guardian: dict, estado: dict, extra: dict | None = None):
    from agent.airtable_client import _patch
    cambios = {"ESTADO JSON": json.dumps(estado, ensure_ascii=False)}
    if extra:
        cambios.update(extra)
    await _patch(_T_GUARDIANES, guardian["id"], cambios)
    guardian.get("fields", {}).update(cambios)


async def _dias_entrenados_7d(nino_id: str) -> int:
    """Días DISTINTOS con entrenamiento en casa (reto-dia o mision-casa acreditados)
    en los últimos 7 días. Para el saludo del tótem: 'entrenaste N días esta semana'."""
    from agent.airtable_client import _get_records
    recs = await _get_records(_T_GUARDIANES, formula=f"{{NINO ID}}='{nino_id}'", max_records=1)
    if not recs:
        return 0
    gid = recs[0]["id"]
    # IS_AFTER es estricto → -8 para incluir los 7 días completos (regla airtable-seguro)
    formula = (f"AND({{GUARDIAN ID}}='{gid}', {{ESTADO}}='acreditado', "
               f"OR({{TIPO}}='reto-dia', {{TIPO}}='mision-casa'), "
               f"IS_AFTER({{FECHA}}, DATEADD(TODAY(), -8, 'days')))")
    desafios = await _get_records(_T_DESAFIOS, formula=formula, max_records=100)
    dias = {str(d.get("fields", {}).get("FECHA", ""))[:10] for d in desafios}
    dias.discard("")
    return len(dias)


def _payload_llegada_con_dias(dias: int, extra: dict | None = None) -> dict:
    p = dict(extra or {})
    if dias > 0:
        p["dias_casa"] = dias
        p["sub"] = f"Entrenaste en casa {dias} día{'s' if dias != 1 else ''} esta semana 💪"
    return p


async def _acreditar_oro_llegada(nino_id: str, nombre: str) -> int:
    """+10 oro por llegar a La Casona (PLAN §6). Máx 1 por día PY, cross-canal
    (facial y NFC comparten el gate en ESTADO JSON). Devuelve el oro acreditado (0 si
    ya cobró hoy). Los callers la envuelven en try/except: el saludo NUNCA se rompe."""
    guardian = await _guardian_de_nino(nino_id, nombre)
    if not guardian:
        return 0
    estado = _estado_de(guardian)
    if estado.get("ult_oro_llegada") == _hoy_py():
        return 0
    estado["ult_oro_llegada"] = _hoy_py()
    await _acreditar(guardian, "oro", ORO_LLEGADA, "Asistencia — llegada a La Casona",
                     cambios_extra={"ESTADO JSON": json.dumps(estado, ensure_ascii=False)})
    return ORO_LLEGADA


async def _acreditar_plata_vuelta(nino_id: str | None, nombre: str, vuelta_info: dict) -> None:
    """Plata REAL a la billetera al cerrar una vuelta del circuito (best-effort, nunca
    rompe el tap/saludo). Antes de esto, el cierre de vuelta por NFC solo emitía el
    evento de celebración para la TV sin pasar por _acreditar — la única puerta al
    dinero — así que la billetera nunca se actualizaba de verdad."""
    if not nino_id:
        return
    try:
        guardian = await _guardian_de_nino(nino_id, nombre)
        if guardian:
            await _acreditar(guardian, "plata", vuelta_info["plata"],
                             f"Vuelta {vuelta_info['numero']} del circuito (NFC)")
    except Exception as e:
        logger.warning(f"[JUEGO] acreditar plata de vuelta falló para {nombre}: {e}")


async def _accion_reto_dia(guardian: dict, video_key: str) -> dict:
    """Un día del reto cumplido (la llama reto-video en P5 — SIEMPRE con video).
    +50 plata, +250 bonus al 5to. Máx 1 por día PY."""
    f = guardian.get("fields", {})
    estado = _estado_de(guardian)
    done = int(f.get("RETO DONE") or 0)
    if done >= 5:
        raise HTTPException(status_code=409, detail="reto_ya_completo")
    if estado.get("ult_reto_dia") == _hoy_py():
        raise HTTPException(status_code=409, detail="ya_entrenaste_hoy")
    done += 1
    estado["ult_reto_dia"] = _hoy_py()
    monto = PLATA_RETO_DIA + (BONUS_RETO_5 if done == 5 else 0)
    motivo = f"Reto día {done}" + (" + bonus 5 seguidos" if done == 5 else "")
    await _acreditar(guardian, "plata", monto, motivo,
                     cambios_extra={"RETO DONE": done, "RETO DIA": min(done + 1, 5),
                                    "ESTADO JSON": json.dumps(estado, ensure_ascii=False),
                                    **({"STAGE": "reto"} if f.get("STAGE") == "builder" else {})},
                     desafio={"DETALLE": f"Reto día {done}", "TIPO": "reto-dia", "VIDEO KEY": video_key})
    return {"reto_done": done, "plata_acreditada": monto, "reto_completo": done == 5}


@router.options("/juego/{_resto:path}")
async def juego_preflight(_resto: str):
    """Preflight CORS de la app (POST con JSON desde pages.dev)."""
    return JSONResponse(content={}, headers=_CORS_PREFLIGHT)


@router.post("/juego/accion")
async def juego_accion(payload: dict = Body(...)):
    """Acciones del juego desde la app. Auth = el código de familia. Una acción por request.
    TODAS las respuestas (éxito y error) llevan CORS — el navegador no lee errores sin eso."""
    try:
        return await _juego_accion_inner(payload)
    except HTTPException as e:
        return JSONResponse(content={"ok": False, "detail": e.detail},
                            status_code=e.status_code, headers=_CORS)


async def _juego_accion_inner(payload: dict):
    codigo = _limpiar_codigo(payload.get("codigo", ""))
    nino_id = str(payload.get("nino_id", "")).strip()
    accion = str(payload.get("accion", "")).strip().lower()
    detalle = str(payload.get("detalle", "") or "").strip().lower()
    if not codigo or not nino_id or not accion:
        raise HTTPException(status_code=422, detail="codigo, nino_id y accion requeridos")

    tutor, guardian = await _validar_nino_de_familia(codigo, nino_id)
    f = guardian.get("fields", {})
    estado = _estado_de(guardian)
    nombre = f.get("NOMBRE") or ""
    robot = f.get("ROBOT") or None
    acreditado = {}

    if accion == "elegir-robot":
        if detalle not in ROBOTS_VALIDOS:
            raise HTTPException(status_code=422, detail="robot_invalido")
        await _guardar_estado(guardian, estado, extra={
            "ROBOT": detalle, **({"STAGE": "reto"} if f.get("STAGE") == "builder" else {})})

    elif accion == "entrada-ceremonia":
        if int(f.get("RETO DONE") or 0) < 5:
            raise HTTPException(status_code=409, detail="reto_incompleto")
        if f.get("STAGE") == "in":
            raise HTTPException(status_code=409, detail="ya_entraste")
        await _acreditar(guardian, "plata", -ENTRADA_CEREMONIA, "Entrada al entrenamiento (ceremonia)",
                         cambios_extra={"STAGE": "in"})
        acreditado = {"plata": -ENTRADA_CEREMONIA}

    elif accion == "mision-casa":
        if detalle not in DRAGONES_IDS:
            raise HTTPException(status_code=422, detail="dragon_invalido")
        drag = estado.setdefault("dragones", {}).setdefault(detalle, {"casa": 0, "venc": False})
        if drag["venc"]:
            raise HTTPException(status_code=409, detail="dragon_ya_vencido")
        if drag["casa"] >= CASA_META:
            raise HTTPException(status_code=409, detail="misiones_completas")
        if estado.get(f"ult_mision_{detalle}") == _hoy_py():
            raise HTTPException(status_code=409, detail="ya_hiciste_la_mision_hoy")
        drag["casa"] += 1
        estado[f"ult_mision_{detalle}"] = _hoy_py()
        await _acreditar(guardian, "plata", PLATA_MISION_CASA, f"Misión en casa vs {detalle} ({drag['casa']}/3)",
                         cambios_extra={"ESTADO JSON": json.dumps(estado, ensure_ascii=False)},
                         desafio={"DETALLE": f"Misión {detalle} {drag['casa']}/3", "TIPO": "mision-casa", "VIDEO KEY": ""})
        acreditado = {"plata": PLATA_MISION_CASA}

    elif accion == "pista":
        try:
            idx = int(detalle)
            assert 0 <= idx <= 2
        except (ValueError, AssertionError):
            raise HTTPException(status_code=422, detail="pista_invalida")
        tesoro = estado.setdefault("tesoro", {"p": [False, False, False], "hallado": False})
        if tesoro["p"][idx]:
            raise HTTPException(status_code=409, detail="pista_ya_resuelta")
        tesoro["p"][idx] = True
        await _acreditar(guardian, "plata", PLATA_PISTA, f"Pista {idx+1} del tesoro",
                         cambios_extra={"ESTADO JSON": json.dumps(estado, ensure_ascii=False)},
                         desafio={"DETALLE": f"Pista {idx+1}", "TIPO": "pista", "VIDEO KEY": ""})
        acreditado = {"plata": PLATA_PISTA}

    elif accion == "tesoro":
        tesoro = estado.setdefault("tesoro", {"p": [False, False, False], "hallado": False})
        if not all(tesoro["p"]):
            raise HTTPException(status_code=409, detail="faltan_pistas")
        if tesoro["hallado"]:
            raise HTTPException(status_code=409, detail="tesoro_ya_hallado")
        tesoro["hallado"] = True
        await _acreditar(guardian, "plata", PLATA_TESORO, "Cofre del tesoro hallado",
                         cambios_extra={"ESTADO JSON": json.dumps(estado, ensure_ascii=False)},
                         desafio={"DETALLE": "Tesoro de la semana", "TIPO": "tesoro", "VIDEO KEY": ""})
        acreditado = {"plata": PLATA_TESORO}
        await crear_evento("tesoro", nombre, robot, {"coins": f"+{PLATA_TESORO} 🥈"})

    elif accion == "dragon-vencido":
        if detalle not in DRAGONES_IDS:
            raise HTTPException(status_code=422, detail="dragon_invalido")
        drag = estado.setdefault("dragones", {}).setdefault(detalle, {"casa": 0, "venc": False})
        if drag["venc"]:
            raise HTTPException(status_code=409, detail="dragon_ya_vencido")
        if drag["casa"] < CASA_META:
            raise HTTPException(status_code=409, detail="faltan_misiones_en_casa")
        drag["venc"] = True
        estado.setdefault("insignias", {})[detalle] = estado.get("insignias", {}).get(detalle, 0) + 1
        total = int(f.get("DRAGONES TOTAL") or 0) + 1
        extra = {"DRAGONES TOTAL": total}
        if all(estado.get("dragones", {}).get(d, {}).get("venc") for d in DRAGONES_IDS):
            extra["MES"] = int(f.get("MES") or 1) + 1     # mes vencido → reinicia la batalla
            for d in DRAGONES_IDS:
                estado["dragones"][d] = {"casa": 0, "venc": False}
        await _acreditar(guardian, "plata", PLATA_DRAGON, f"Dragón {detalle} vencido",
                         cambios_extra={"ESTADO JSON": json.dumps(estado, ensure_ascii=False), **extra},
                         desafio={"DETALLE": f"Dragón {detalle}", "TIPO": "desafio-sabado", "VIDEO KEY": ""})
        acreditado = {"plata": PLATA_DRAGON, "dragones_total": total}
        await crear_evento("dragon", nombre, robot, {"d": detalle.capitalize(), "coins": f"+{PLATA_DRAGON} 🥈"})

    else:
        raise HTTPException(status_code=422, detail=f"accion_desconocida ({accion})")

    return JSONResponse(content={"ok": True, "acreditado": acreditado,
                                 "guardian": _guardian_publico(guardian)}, headers=_CORS)


# ═══════════════════ MUNDO FENIX APP — F3/P5: video del reto (acreditación inmediata) ═══════════════════

@router.post("/juego/reto-video")
async def juego_reto_video(payload: dict = Body(...)):
    """La app ya subió el video a R2 (Function de Cloudflare) y acá lo registra:
    checks automáticos → DESAFIO CUMPLIDO + acreditación inmediata (+50/+250) →
    muestreo espejado a Telegram. La IA de control llega en iteración 2."""
    try:
        return await _juego_reto_video_inner(payload)
    except HTTPException as e:
        return JSONResponse(content={"ok": False, "detail": e.detail},
                            status_code=e.status_code, headers=_CORS)


async def _juego_reto_video_inner(payload: dict):
    codigo = _limpiar_codigo(payload.get("codigo", ""))
    nino_id = str(payload.get("nino_id", "")).strip()
    video_key = str(payload.get("video_key", "")).strip()
    if not codigo or not nino_id or not video_key:
        raise HTTPException(status_code=422, detail="codigo, nino_id y video_key requeridos")
    # el key DEBE ser de esta familia y este niño (la Function lo generó así)
    if not video_key.startswith(f"videos/{codigo}/{nino_id}/"):
        raise HTTPException(status_code=403, detail="video_key_no_corresponde")

    tutor, guardian = await _validar_nino_de_familia(codigo, nino_id)
    resultado = await _accion_reto_dia(guardian, video_key)   # 1/día + bonus + ledger adentro
    nombre = guardian.get("fields", {}).get("NOMBRE") or ""

    # muestreo: espejo a Telegram con el link del video (best-effort, jamás rompe la acreditación)
    try:
        _tf_video = tutor.get("fields", {}) or {}
        telefono = (_tf_video.get("TELEFONO LIMPIO") or _tf_video.get("TELEFONO2 LIMPIO") or "").strip()
        if telefono:
            from agent.telegram_bridge import obtener_o_crear_topic, enviar_a_topic
            link = f"{APP_URL}/api/video/{video_key}?f={codigo}"
            topic = await obtener_o_crear_topic(telefono, f"📱 {telefono}")
            tid = topic.topic_id if hasattr(topic, "topic_id") else topic
            if tid:
                await enviar_a_topic(tid, f"🎬 Video Reto Día {resultado['reto_done']} de {nombre}"
                                          f" (+{resultado['plata_acreditada']} 🥈 acreditadas)\n{link}",
                                     telefono=telefono)
    except Exception as e:
        logger.warning(f"[JUEGO] muestreo Telegram falló: {e}")

    return JSONResponse(content={"ok": True, **resultado,
                                 "guardian": _guardian_publico(guardian)}, headers=_CORS)


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


async def _pulsera_por_nino_id(session, nino_id: str) -> "Pulsera | None":
    r = await session.execute(select(Pulsera).where(
        Pulsera.nino_airtable_id == nino_id, Pulsera.activa == True))  # noqa: E712
    return r.scalar_one_or_none()


async def _evaluar_circuito(session, p: "Pulsera") -> dict:
    """¿La pulsera de p ya completó las estaciones activas? Si sí, cierra la vuelta acá
    mismo (INSERT JuegoVuelta + sella las pasadas abiertas) — el caller commitea y emite
    los eventos después. Usado por el tap del tótem Y por el check-in facial (misma
    regla, dos formas de "llegar al tótem"). Devuelve {"faltan": [...], "vuelta_info": {...}|None}."""
    hoy0 = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    abiertas = await _pasadas_abiertas(session, p.uid)
    tocadas = {x.estacion_id for x in abiertas if x.estacion_id in ESTACIONES_ACTIVAS}
    faltan = [e for e in ESTACIONES_ACTIVAS if e not in tocadas]

    vuelta_info = None
    if not faltan and tocadas:
        n_hoy = await session.execute(
            select(JuegoVuelta).where(JuegoVuelta.uid == p.uid, JuegoVuelta.cerrada >= hoy0))
        numero = len(list(n_hoy.scalars().all())) + 1
        plata = PLATA_VUELTA + (BONUS_5_VUELTAS if numero == 5 else 0) + (BONUS_10_VUELTAS if numero == 10 else 0)
        v = JuegoVuelta(uid=p.uid, nino_nombre=p.nino_nombre, numero_dia=numero,
                        estaciones_ok=len(tocadas), plata=plata)
        session.add(v)
        await session.flush()
        for pas in abiertas:                          # las pasadas quedan selladas a esta vuelta
            pas.vuelta_id = v.id
        vuelta_info = {"numero": numero, "plata": plata}
    return {"faltan": faltan, "vuelta_info": vuelta_info}


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
    nino_id = str(payload.get("nino_id", "") or "").strip()[:50] or None
    if not uid or not nombre:
        raise HTTPException(status_code=422, detail="uid y nino_nombre requeridos")
    async with async_session() as session:
        existente = await session.execute(select(Pulsera).where(Pulsera.uid == uid))
        p = existente.scalar_one_or_none()
        if p and p.activa and p.nino_nombre != nombre:
            raise HTTPException(status_code=409, detail=f"UID ya vinculado a {p.nino_nombre}")
        if p:
            p.nino_nombre, p.guardian, p.activa = nombre, guardian, True
            if nino_id:
                p.nino_airtable_id = nino_id
        else:
            session.add(Pulsera(uid=uid, nino_nombre=nombre, guardian=guardian,
                                nino_airtable_id=nino_id))
        await session.commit()
    logger.info(f"[JUEGO] pulsera {uid} vinculada a {nombre}")
    return {"ok": True, "uid": uid, "nino_nombre": nombre}


@router.post("/juego/nfc-desvincular")
async def nfc_desvincular(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """Libera la pulsera de un niño (fin de temporada, se pierde, pasa a otro chico). NO borra
    el historial de pasadas/vueltas — solo la marca inactiva; nfc-vincular puede reactivar el
    mismo UID para OTRO niño después sin chocar con el 409."""
    _auth(x_juego_key)
    nino_id = str(payload.get("nino_id", "") or "").strip()
    if not nino_id:
        raise HTTPException(status_code=422, detail="nino_id requerido")
    async with async_session() as session:
        p = await _pulsera_por_nino_id(session, nino_id)
        if not p:
            return {"ok": False, "motivo": "sin_pulsera"}
        uid, nombre = p.uid, p.nino_nombre
        p.activa = False
        await session.commit()
    logger.info(f"[JUEGO] pulsera {uid} desvinculada de {nombre}")
    return {"ok": True, "uid": uid, "nino_nombre": nombre}


@router.post("/juego/nfc-desvincular-todas")
async def nfc_desvincular_todas(x_juego_key: str | None = Header(default=None)):
    """Libera TODAS las pulseras activas de una — fin del entrenamiento/temporada, resetea el
    pool completo de muñequeras para la próxima vez. NO borra historial de pasadas/vueltas."""
    _auth(x_juego_key)
    async with async_session() as session:
        r = await session.execute(select(Pulsera).where(Pulsera.activa == True))  # noqa: E712
        activas = list(r.scalars().all())
        for p in activas:
            p.activa = False
        await session.commit()
    logger.info(f"[JUEGO] desvinculadas {len(activas)} pulseras de una")
    return {"ok": True, "cantidad": len(activas)}


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
        resultado = await _evaluar_circuito(session, p)
        faltan = resultado["faltan"]
        vuelta_info = resultado["vuelta_info"]
        await session.commit()

    # eventos fuera de la transacción (best-effort, la TV los celebra)
    if llegada_evento:
        dias = 0
        if p.nino_airtable_id:
            try:  # +10 oro por venir (gate diario compartido con el facial)
                await _acreditar_oro_llegada(p.nino_airtable_id, p.nino_nombre)
            except Exception as e:
                logger.warning(f"[JUEGO] totem-nfc: oro de llegada falló para {p.nino_nombre}: {e}")
            try:
                dias = await _dias_entrenados_7d(p.nino_airtable_id)
            except Exception as e:
                logger.warning(f"[JUEGO] dias_entrenados falló: {e}")
        else:
            logger.info(f"[JUEGO] totem-nfc: pulsera {uid} sin nino_airtable_id — llegada sin oro")
        await crear_evento("llegada", p.nino_nombre, p.guardian,
                           _payload_llegada_con_dias(dias, {"via": "nfc"}))
    if vuelta_info:
        await _acreditar_plata_vuelta(p.nino_airtable_id, p.nino_nombre, vuelta_info)
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
    TODAS las respuestas llevan CORS — el tótem vive en otro origen (Cloudflare Pages) y
    el navegador NO lee la respuesta sin ese header (aunque el back reconozca y responda 200).
    Cooldown 5 min por niño (toca 20 veces = 1 llegada). Ver SPEC-TOTEM 4A."""
    try:
        return await _checkin_face_inner(payload, x_juego_key)
    except HTTPException as e:
        return JSONResponse(content={"ok": False, "detail": e.detail},
                            status_code=e.status_code, headers=_CORS)


async def _checkin_face_inner(payload: dict, x_juego_key: str | None):
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
        return JSONResponse(content={"ok": False, "motivo": "no_reconocido"}, headers=_CORS)
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
        return JSONResponse(content={"ok": False, "motivo": "nino_sin_datos"}, headers=_CORS)

    # ¿ya llegó HOY? — gate DIARIO por NIÑO: ult_oro_llegada en el estado del guardián
    # (lo setea el oro de llegada, cross-canal con el NFC). OJO: NO mirar juego_eventos
    # por nombre — dos niñas "Fiorella" se pisaban y la segunda quedaba sin oro ni
    # asistencia (bug 11/07). Si el oro falló, el gate no queda y el próximo escaneo
    # reintenta como primera llegada: preferible a perderle las monedas al niño.
    guardian = None
    try:
        guardian = await _guardian_de_nino(nino_id, nombre)
    except Exception as e:
        logger.warning(f"[JUEGO] guardian no disponible para {nombre}: {e}")

    # circuito NFC: si el niño tiene pulsera y ya tocó todas las estaciones activas,
    # el rostro frente al tótem CIERRA LA VUELTA — no depende del gate de llegada
    # diaria, un niño puede cerrar varias vueltas por día volviendo al espejo.
    circuito = None
    p_pulsera = None
    try:
        async with async_session() as session:
            p_pulsera = await _pulsera_por_nino_id(session, nino_id)
            if p_pulsera:
                circuito = await _evaluar_circuito(session, p_pulsera)
                await session.commit()
    except Exception as e:
        logger.warning(f"[JUEGO] checkin-face: evaluar circuito falló para {nombre}: {e}")
    if circuito and circuito["vuelta_info"]:
        vi = circuito["vuelta_info"]
        if guardian:  # la ÚNICA puerta al dinero es _acreditar — el evento solo la anima
            try:
                await _acreditar(guardian, "plata", vi["plata"],
                                 f"Vuelta {vi['numero']} del circuito (NFC)")
            except Exception as e:
                logger.warning(f"[JUEGO] checkin-face: acreditar plata falló para {nombre}: {e}")
        sub = f"¡Bonus de {vi['numero']} vueltas!" if vi["numero"] in (5, 10) else ""
        await crear_evento("vuelta", nombre, p_pulsera.guardian if p_pulsera else None,
                           {"v": vi["numero"], "coins": f"+{vi['plata']} 🥈", "sub": sub})
    circuito_pub = ({"faltan": circuito["faltan"], "vuelta_cerrada": bool(circuito["vuelta_info"])}
                     if circuito else None)

    estado_g = _estado_de(guardian) if guardian else {}
    repetido = estado_g.get("ult_oro_llegada") == _hoy_py()

    if repetido:
        # el guardián viaja igual: si re-escanea sin avatar, el selector aparece igual.
        # Si recién eligió su Guardián en la tablet y volvió al espejo → PRESENTACIÓN:
        # evento llegada para la TV (celebra con monedas) + flag para la tablet.
        robot_g = guardian.get("fields", {}).get("ROBOT")
        if robot_g and estado_g.get("presentar_avatar") == _hoy_py():
            try:
                estado_g.pop("presentar_avatar", None)
                await _guardar_estado(guardian, estado_g)
                await crear_evento("llegada", nombre, robot_g,
                                   {"via": "avatar", "sub": "¡Ya tiene a su Guardián! 🛡️"})
                return JSONResponse(content={"ok": True, "nino": {"id": nino_id, "nombre": nombre},
                        "repetido": True, "presentacion": True,
                        "confidence": round(best["confidence"], 1),
                        "guardian": _guardian_publico(guardian),
                        "circuito": circuito_pub}, headers=_CORS)
            except Exception as e:
                logger.warning(f"[JUEGO] presentación falló para {nombre}: {e}")
        return JSONResponse(content={"ok": True, "nino": {"id": nino_id, "nombre": nombre},
                "repetido": True, "confidence": round(best["confidence"], 1),
                "guardian": _guardian_publico(guardian) if guardian else None,
                "circuito": circuito_pub}, headers=_CORS)

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

    # Descontar una clase del pack y avisarle al padre que su hijo entró
    # (best-effort — nunca frena la entrada del niño). saldo None = familia del
    # plan mensual viejo: no tiene pack, no se le toca nada y el aviso le habla
    # de su vencimiento en vez de clases. El aviso sale solo si Ivan lo prendió
    # con AVISO_CHECKIN_ACTIVO.
    try:
        from agent.airtable_client import obtener_saldo_clases, padre_de_nino
        from agent.checkin_aviso import aviso_activo, enviar_aviso_checkin, frase_estado

        # La asistencia ya se creó arriba: el saldo calculado la refleja.
        _saldo = await obtener_saldo_clases(nino_id)

        if aviso_activo():
            _nombre_padre, _tel_padre, _vence = await padre_de_nino(nino_id)
            if _tel_padre:
                from agent.providers import obtener_proveedor
                await enviar_aviso_checkin(
                    _tel_padre, obtener_proveedor(), _nombre_padre, nombre,
                    frase_estado(_saldo, _vence),
                )
            else:
                logger.warning(f"[JUEGO] checkin-face: {nombre} sin teléfono de padre — no aviso")
    except Exception as e:
        logger.warning(f"[JUEGO] checkin-face: pack/aviso falló para {nombre}: {e}")

    # +10 oro por venir (best-effort — nunca rompe el saludo)
    oro = 0
    try:
        oro = await _acreditar_oro_llegada(nino_id, nombre)
    except Exception as e:
        logger.warning(f"[JUEGO] checkin-face: oro de llegada falló para {nombre}: {e}")

    dias = 0
    try:
        dias = await _dias_entrenados_7d(nino_id)
    except Exception as e:
        logger.warning(f"[JUEGO] dias_entrenados falló: {e}")
    await crear_evento("llegada", nombre, None,
                       _payload_llegada_con_dias(dias, {"via": "face", "conf": round(best["confidence"], 1)}))
    return JSONResponse(content={"ok": True, "nino": {"id": nino_id, "nombre": nombre}, "dias_casa": dias,
            "oro": oro, "confidence": round(best["confidence"], 1),
            "guardian": await _guardian_publico_seguro(nino_id, nombre),
            "circuito": circuito_pub}, headers=_CORS)


async def _guardian_publico_seguro(nino_id: str, nombre: str) -> dict | None:
    """Guardián proyectado para la tablet (robot + billetera). None si Airtable
    falla — el saludo del check-in NUNCA se rompe por esto."""
    try:
        g = await _guardian_de_nino(nino_id, nombre)
        return _guardian_publico(g) if g else None
    except Exception as e:
        logger.warning(f"[JUEGO] guardian no disponible para {nombre}: {e}")
        return None


@router.post("/juego/elegir-robot")
async def juego_elegir_robot(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """El niño elige su Guardián en la tablet tras el check-in facial (SPEC-TOTEM).
    Idempotente: si ya tiene ROBOT devuelve el actual con ya_tenia=true (tocar dos
    veces no lo pisa). TODAS las respuestas llevan CORS — el tótem vive en pages.dev."""
    try:
        return await _elegir_robot_inner(payload, x_juego_key)
    except HTTPException as e:
        return JSONResponse(content={"ok": False, "detail": e.detail},
                            status_code=e.status_code, headers=_CORS)


async def _elegir_robot_inner(payload: dict, x_juego_key: str | None):
    _auth(x_juego_key)
    nino_id = str(payload.get("nino_id", "")).strip()
    robot = str(payload.get("robot", "")).strip().lower()
    nombre = str(payload.get("nombre", "") or "").strip()[:120]
    if not nino_id or robot not in ROBOTS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"nino_id y robot válido requeridos ({', '.join(sorted(ROBOTS_VALIDOS))})")

    guardian = await _guardian_de_nino(nino_id, nombre or "Guardián")
    if not guardian:
        raise HTTPException(status_code=404, detail="guardian_no_existe")
    f = guardian.get("fields", {})
    if f.get("ROBOT"):
        return JSONResponse(content={"ok": True, "ya_tenia": True,
                                     "guardian": _guardian_publico(guardian)}, headers=_CORS)

    # mismo comportamiento que elegir-robot de la app: ROBOT + salir de builder.
    # presentar_avatar: el próximo escaneo del día dispara la celebración en la TV
    # (el niño elige en la tablet, vuelve al espejo, y la TV lo presenta con monedas).
    from agent.airtable_client import _patch
    estado = _estado_de(guardian)
    estado["presentar_avatar"] = _hoy_py()
    cambios = {"ROBOT": robot, "ESTADO JSON": json.dumps(estado, ensure_ascii=False),
               **({"STAGE": "reto"} if f.get("STAGE") == "builder" else {})}
    ok = await _patch(_T_GUARDIANES, guardian["id"], cambios)
    if not ok:
        raise HTTPException(status_code=502, detail="airtable_no_respondio")
    f.update(cambios)
    logger.info(f"[JUEGO] {f.get('NOMBRE') or nino_id} eligió su Guardián: {robot}")
    return JSONResponse(content={"ok": True, "ya_tenia": False,
                                 "guardian": _guardian_publico(guardian)}, headers=_CORS)


# ═══════════════ VUELTAS POR CARA — puente hasta que lleguen los lectores NFC ═══════════════
# El niño completa la vuelta, se escanea, y confirma en la tablet ("¿completaste una
# vuelta?") con el profe supervisando. Cada SÍ acredita plata REAL a la billetera.

VUELTA_FACE_MIN_SEG = int(os.getenv("JUEGO_VUELTA_FACE_MIN_SEG", "120"))  # anti doble-tap


@router.post("/juego/vuelta-face")
async def juego_vuelta_face(payload: dict = Body(...), x_juego_key: str | None = Header(default=None)):
    """Vuelta del circuito confirmada en la tablet (sin NFC): plata a la billetera +
    registro en juego_vueltas (uid FACE:{nino_id}) + evento para la TV. CORS siempre."""
    try:
        return await _vuelta_face_inner(payload, x_juego_key)
    except HTTPException as e:
        return JSONResponse(content={"ok": False, "detail": e.detail},
                            status_code=e.status_code, headers=_CORS)


async def _vuelta_face_inner(payload: dict, x_juego_key: str | None):
    _auth(x_juego_key)
    nino_id = str(payload.get("nino_id", "")).strip()
    nombre = str(payload.get("nombre", "") or "").strip()[:120]
    if not nino_id or not nombre:
        raise HTTPException(status_code=422, detail="nino_id y nombre requeridos")
    uid = f"FACE:{nino_id}"[:40]

    # Cantidad de vueltas que el profe cuenta en la tablet (default 1). Tope de
    # seguridad para que un typo no acredite miles: máx 20 de una.
    try:
        cantidad = int(payload.get("cantidad", 1) or 1)
    except (TypeError, ValueError):
        cantidad = 1
    cantidad = max(1, min(cantidad, 20))

    async with async_session() as session:
        # anti doble-tap: mínimo N segundos entre registros del mismo niño
        ult = await session.execute(select(JuegoVuelta.cerrada).where(JuegoVuelta.uid == uid)
                                    .order_by(JuegoVuelta.cerrada.desc()).limit(1))
        ultima = ult.scalar()
        if ultima and (datetime.utcnow() - ultima).total_seconds() < VUELTA_FACE_MIN_SEG:
            raise HTTPException(status_code=409, detail="vuelta_muy_rapida")
        hechas = await session.execute(select(JuegoVuelta.id).where(
            JuegoVuelta.uid == uid, JuegoVuelta.cerrada >= _hoy0_utc()))
        ya_hechas = len(list(hechas.scalars().all()))

    # plata de las N vueltas — el bonus es por acumulado del día (la vuelta 5 y la 10)
    def _plata_de(numero: int) -> int:
        return PLATA_VUELTA + (BONUS_5_VUELTAS if numero == 5 else 0) + (BONUS_10_VUELTAS if numero == 10 else 0)
    numeros = [ya_hechas + 1 + k for k in range(cantidad)]
    numero_final = numeros[-1]
    plata_total = sum(_plata_de(n) for n in numeros)

    # plata REAL a la billetera (el guardián ya existe por el flujo de llegada/avatar)
    guardian = await _guardian_de_nino(nino_id, nombre)
    if not guardian:
        raise HTTPException(status_code=404, detail="guardian_no_existe")
    motivo = (f"{cantidad} vueltas del circuito (#{numeros[0]}–#{numero_final})"
              if cantidad > 1 else f"Vuelta {numero_final} del circuito")
    await _acreditar(guardian, "plata", plata_total, motivo)

    async with async_session() as session:
        for numero in numeros:
            session.add(JuegoVuelta(uid=uid, nino_nombre=nombre, numero_dia=numero,
                                    estaciones_ok=0, plata=_plata_de(numero)))
        await session.commit()

    # totales de billetera + lo ganado hoy (lo puso _acreditar en ESTADO JSON)
    gp = _guardian_publico(guardian)
    _est = gp.get("estado", {}) or {}
    hoy_oro = int(_est.get("hoy_oro", 0))
    hoy_plata = int(_est.get("hoy_plata", 0))
    robot = guardian.get("fields", {}).get("ROBOT") or None
    _bonus = [n for n in numeros if n in (5, 10)]
    sub = (f"¡Bonus de {_bonus[-1]} vueltas!" if _bonus
           else (f"¡{cantidad} vueltas de una! 🔥" if cantidad > 1 else ""))
    await crear_evento("vuelta", nombre, robot, {
        "v": numero_final, "cantidad": cantidad, "coins": f"+{plata_total} 🥈", "sub": sub,
        "oro_total": gp["oro"], "plata_total": gp["plata"],
        "hoy_oro": hoy_oro, "hoy_plata": hoy_plata})
    logger.info(f"[JUEGO] vuelta-face x{cantidad} de {nombre} (#{numero_final}, +{plata_total} plata)")
    return JSONResponse(content={"ok": True, "numero": numero_final, "cantidad": cantidad,
                                 "plata": plata_total, "guardian": gp}, headers=_CORS)


@router.get("/juego/alumnos")
async def juego_alumnos(x_juego_key: str | None = Header(default=None)):
    """Lista {id, nombre, apodo, tiene_pulsera} de NIÑOS FENIX para el selector del profe.
    tiene_pulsera marca quién ya tiene una pulsera NFC vinculada (para que el check quede
    visible en la lista, no solo en un toast que se pierde). Requiere key."""
    _auth(x_juego_key)
    from agent.airtable_client import _get_records, _NINOS
    records = await _get_records(_NINOS, max_records=500)

    async with async_session() as session:
        r = await session.execute(select(Pulsera.nino_airtable_id).where(
            Pulsera.activa == True, Pulsera.nino_airtable_id.isnot(None)))  # noqa: E712
        con_pulsera = {row[0] for row in r.all()}

    alumnos = []
    for rec in records:
        f = rec.get("fields", {})
        nombre = (f.get("NOMBRE") or "").strip()
        if not nombre:
            continue
        nino_id = rec.get("id", "")
        alumnos.append({"id": nino_id, "nombre": nombre,
                        "apodo": (f.get("APODO") or "").strip(),
                        "apellido": (f.get("APELLIDO") or "").strip(),
                        "tiene_pulsera": nino_id in con_pulsera})
    alumnos.sort(key=lambda a: a["nombre"])
    return {"alumnos": alumnos}


@router.get("/juego/estaciones")
async def juego_estaciones():
    """Config del circuito activo (para /profe, el mapa y los ESP32)."""
    return JSONResponse(content={"estaciones": ESTACIONES_ACTIVAS, "tiempo_min_seg": TIEMPO_MIN_SEG},
                        headers=_CORS)


@router.get("/juego/dia")
async def juego_dia():
    """Resumen del día para la TV lista: niños que llegaron HOY con sus vueltas,
    monedas ganadas en el día y saldo total. Público con CORS (misma política que
    /juego/eventos: nombres de pila + números del juego, sin datos sensibles).

    Fuentes: GUARDIANES (gate ult_oro_llegada en ESTADO JSON = llegó hoy, y saldos
    ORO/PLATA), MOVIMIENTOS BRASAS (ganado hoy por CREATED_TIME) y juego_vueltas
    en Postgres (vueltas cerradas hoy, uid FACE:{nino_id} o pulsera NFC)."""
    from agent.airtable_client import _get_records
    hoy = _hoy_py()

    # 1) Quiénes llegaron hoy — el gate diario vive como texto dentro de ESTADO JSON
    #    (json.dumps escribe exactamente '"ult_oro_llegada": "YYYY-MM-DD"')
    formula_g = f"FIND('\"ult_oro_llegada\": \"{hoy}\"', {{ESTADO JSON}})"
    guardianes = await _get_records(_T_GUARDIANES, formula=formula_g, max_records=300)

    ninos: dict[str, dict] = {}          # guardian_id → item
    por_nino_id: dict[str, dict] = {}    # nino_id → item (para cruzar vueltas)
    por_nombre: dict[str, dict] = {}     # nombre lower → item (fallback pulseras viejas)
    for g in guardianes:
        f = g.get("fields", {})
        item = {
            "nino_id": (f.get("NINO ID") or "").strip(),
            "nombre": (f.get("NOMBRE") or "").strip(),
            "apellido": "",
            "robot": f.get("ROBOT") or None,
            "vueltas_hoy": 0, "oro_hoy": 0, "plata_hoy": 0,
            "oro_total": int(f.get("ORO") or 0),
            "plata_total": int(f.get("PLATA") or 0),
        }
        if not item["nombre"]:
            continue
        ninos[g["id"]] = item
        if item["nino_id"]:
            por_nino_id[item["nino_id"]] = item
        por_nombre[item["nombre"].lower()] = item

    # 1b) Apellido — GUARDIANES no lo guarda; lo trae NIÑOS FENIX vía NINO ID.
    #     Solo la INICIAL: el endpoint es público (TV) y el apellido completo de
    #     menores no debe salir sin auth (auditoría 2026-07-12). La inicial
    #     alcanza para desambiguar tocayos en pantalla ("Fiorella G.").
    if por_nino_id:
        from agent.airtable_client import _NINOS
        for r in await _get_records(_NINOS, max_records=500):
            item = por_nino_id.get(r.get("id", ""))
            if item:
                _ape = (r.get("fields", {}).get("APELLIDO") or "").strip()
                item["apellido"] = f"{_ape[0].upper()}." if _ape else ""

    # 2) Monedas ganadas hoy — movimientos positivos desde la medianoche PY (en UTC)
    if ninos:
        corte_utc = _hoy0_utc().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        movs = await _get_records(
            _T_MOVIMIENTOS, formula=f"IS_AFTER(CREATED_TIME(), '{corte_utc}')", max_records=1000)
        for m in movs:
            fm = m.get("fields", {})
            item = ninos.get((fm.get("GUARDIAN ID") or "").strip())
            monto = int(fm.get("MONTO") or 0)
            if not item or monto <= 0:
                continue
            if fm.get("MONEDA") == "oro":
                item["oro_hoy"] += monto
            else:
                item["plata_hoy"] += monto

    # 3) Vueltas cerradas hoy (Postgres) — FACE:{nino_id} directo; NFC via pulsera
    async with async_session() as session:
        rows = (await session.execute(
            select(JuegoVuelta).where(JuegoVuelta.cerrada >= _hoy0_utc()))).scalars().all()
        for v in rows:
            item = None
            if v.uid.startswith("FACE:"):
                item = por_nino_id.get(v.uid[5:])
            else:
                p = await _pulsera_por_uid(session, v.uid)
                if p and p.nino_airtable_id:
                    item = por_nino_id.get(p.nino_airtable_id)
            if not item:
                item = por_nombre.get((v.nino_nombre or "").strip().lower())
            if item:
                item["vueltas_hoy"] += 1

    lista = sorted(ninos.values(),
                   key=lambda x: (-(x["oro_hoy"] + x["plata_hoy"]), -x["vueltas_hoy"], x["nombre"]))
    return JSONResponse(content={"ok": True, "fecha": hoy, "ninos": lista}, headers=_CORS)


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
