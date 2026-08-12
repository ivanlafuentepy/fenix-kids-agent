# agent/desafio.py — DESAFÍO FENIX: el campus de 3 días que reemplaza la clase de prueba
"""
Desde 2026-08-09 la puerta de entrada a FENIX no es una clase de prueba de un sábado:
es el DESAFÍO FENIX, un campus de fin de semana completo.

    VIERNES  17:00-18:30  o  19:30-20:45   (el padre elige turno) — DESCUBRIR
    SÁBADO   11:00-12:30  o  15:30-17:00   (el padre elige turno) — SUPERAR
    DOMINGO  12:00 Gran Desafío · 13:00 almuerzo · 15:00 cierre   — CONQUISTAR

Un campus se identifica por la fecha de su VIERNES; no hay tabla nueva. La inscripción
de un niño son TRES reservas sobre el modelo de siempre (NINO + HORARIO), así que el QR,
la asistencia y el check-in siguen funcionando sin migrar nada.

Precio: 350.000 con reserva anticipada (hasta el jueves 23:59 PY), 550.000 después;
+150.000 por cada hermano en los dos casos. El almuerzo del domingo del NIÑO va incluido.

Cupos: se comunican 10 por turno, pero el límite real es 20. Entre 10 y 19 el agente dice
que está lleno y escala al admin ("vamos a ver si entra uno más"), NO bloquea.
"""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("agentkit")

_TZ = ZoneInfo("America/Asuncion")

# Turnos que el padre elige. El domingo es uno solo para todos.
TURNOS_VIERNES = ("17:00", "19:30")
TURNOS_SABADO = ("11:00", "15:30")
HORA_DOMINGO = "12:00"

# Excepciones por fecha: días que corren con otros turnos que los de arriba.
# La clave es la fecha ISO del día, así que la excepción se apaga SOLA cuando ese
# campus pasa — nadie tiene que acordarse de revertir nada el lunes. Las constantes
# de arriba nunca se tocan: siguen siendo la regla general.
TURNOS_ESPECIALES: dict[str, tuple[str, ...]] = {
    "2026-08-14": ("17:00",),   # feriado: un solo turno
    "2026-08-15": ("11:00",),   # feriado: un solo turno (también el entrenamiento regular)
}
MOTIVO_ESPECIAL = "es feriado"

# El rango horario que se le comunica al padre para cada turno.
RANGO_TURNO = {"17:00": "17:00 a 18:30", "19:30": "19:30 a 20:45",
               "11:00": "11:00 a 12:30", "15:30": "15:30 a 17:00"}

# El campus en curso se deja de vender cuando arranca el turno 1 del viernes.
_INICIO_VIERNES = time(17, 0)

PRECIO_ANTICIPADA = 350_000
PRECIO_NORMAL = 550_000
EXTRA_HERMANO = 150_000

# 10 es el número que se comunica (a los 10 se anuncia SOLD OUT); 20 es el techo real.
CUPO_COMUNICADO = 10
CUPO_REAL = 20

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def ahora_py() -> datetime:
    """La hora de Paraguay. Railway corre en UTC: nunca usar datetime.now() pelado."""
    return datetime.now(_TZ)


def proximo_campus(ahora: datetime | None = None) -> dict:
    """El campus que se está vendiendo ahora mismo.

    Devuelve {"viernes": date, "sabado": date, "domingo": date}.

    Se puede reservar hasta el viernes a la tarde (decisión de Iván 09/08): mientras el
    turno 1 del viernes no arrancó, el campus de este fin de semana sigue en venta. Una
    vez que empezó, se ofrece el del fin de semana siguiente — un padre que escribe el
    sábado ya no puede sumarse al campus en curso.
    """
    ahora = ahora or ahora_py()
    hoy = ahora.date()
    viernes = hoy + timedelta(days=(4 - hoy.weekday()) % 7)
    if viernes == hoy and ahora.time() >= _INICIO_VIERNES:
        viernes += timedelta(days=7)
    return {
        "viernes": viernes,
        "sabado": viernes + timedelta(days=1),
        "domingo": viernes + timedelta(days=2),
    }


def es_anticipada(ahora: datetime | None = None, campus: dict | None = None) -> bool:
    """¿Todavía vale el precio de reserva anticipada?

    El corte es el JUEVES 23:59 PY previo al campus: desde el viernes 00:00 se cobra el
    precio normal, aunque el campus recién arranque a las 17:00.
    """
    ahora = ahora or ahora_py()
    campus = campus or proximo_campus(ahora)
    return ahora.date() < campus["viernes"]


def precio_desafio(hijos: int = 1, ahora: datetime | None = None,
                   campus: dict | None = None) -> tuple[int, bool]:
    """(monto, es_anticipada) para esa cantidad de hermanos.

    Anticipada: 350.000 · 500.000 · 650.000    Normal: 550.000 · 700.000 · 850.000
    """
    hijos = max(1, int(hijos or 1))
    anticipada = es_anticipada(ahora, campus)
    base = PRECIO_ANTICIPADA if anticipada else PRECIO_NORMAL
    return base + EXTRA_HERMANO * (hijos - 1), anticipada


def turnos_de(fecha_iso: str, normales: tuple[str, ...]) -> tuple[str, ...]:
    """Los turnos que corren ESE día: la excepción si la hay, si no los de siempre."""
    return TURNOS_ESPECIALES.get(fecha_iso, normales)


def turnos_viernes_de(campus: dict | None = None) -> tuple[str, ...]:
    """Turnos del viernes de ese campus (puede ser uno solo si es feriado)."""
    campus = campus or proximo_campus()
    return turnos_de(campus["viernes"].isoformat(), TURNOS_VIERNES)


def turnos_sabado_de(campus: dict | None = None) -> tuple[str, ...]:
    """Turnos del sábado de ese campus (puede ser uno solo si es feriado)."""
    campus = campus or proximo_campus()
    return turnos_de(campus["sabado"].isoformat(), TURNOS_SABADO)


def turnos_del_campus(campus: dict | None = None) -> list[tuple[str, str]]:
    """Los slots (fecha_iso, hora) del campus, en orden cronológico.

    Normalmente son 5; un fin de semana con turno único tiene menos.
    """
    campus = campus or proximo_campus()
    v, s, d = campus["viernes"].isoformat(), campus["sabado"].isoformat(), campus["domingo"].isoformat()
    slots = [(v, h) for h in turnos_viernes_de(campus)]
    slots += [(s, h) for h in turnos_sabado_de(campus)]
    slots.append((d, HORA_DOMINGO))
    return slots


def label_campus(campus: dict | None = None) -> str:
    """"viernes 14, sábado 15 y domingo 16 de agosto" — para los mensajes al padre.

    Si el campus cruza de mes, cada día lleva el suyo ("viernes 29 de agosto, sábado 30
    de agosto y domingo 31 de agosto" no se acorta mal).
    """
    campus = campus or proximo_campus()
    v, s, d = campus["viernes"], campus["sabado"], campus["domingo"]
    if v.month == d.month:
        return f"viernes {v.day}, sábado {s.day} y domingo {d.day} de {_MESES[v.month - 1]}"
    return (f"viernes {v.day} de {_MESES[v.month - 1]}, sábado {s.day} de {_MESES[s.month - 1]} "
            f"y domingo {d.day} de {_MESES[d.month - 1]}")


_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def _label_dia(d: date) -> str:
    """"sábado 15" — para nombrar un día suelto en los avisos."""
    return f"{_DIAS[d.weekday()]} {d.day}"


def dias_especiales_proximos(hoy: date | None = None, dentro_de: int = 7) -> list[tuple[date, tuple[str, ...]]]:
    """Los días con turno especial que todavía no pasaron, ordenados.

    Se mira por FECHA y no por campus a propósito: el sábado a la mañana
    proximo_campus() ya devuelve el fin de semana siguiente, y justo ese sábado
    es cuando una mamá pregunta "¿hay entrenamiento hoy?".
    """
    hoy = hoy or ahora_py().date()
    dias = []
    for fecha_iso, turnos in TURNOS_ESPECIALES.items():
        try:
            d = date.fromisoformat(fecha_iso)
        except ValueError:
            logger.error(f"[DESAFIO] Fecha inválida en TURNOS_ESPECIALES: {fecha_iso!r}")
            continue
        if 0 <= (d - hoy).days <= dentro_de:
            dias.append((d, turnos))
    return sorted(dias)


def aviso_horario_especial(hoy: date | None = None) -> str | None:
    """El bloque que se le inyecta al LLM cuando hay días con turno especial.

    Devuelve None si no hay ninguno cerca — así el aviso aparece y desaparece
    solo, sin tocar el prompt (que además está cacheado).
    """
    dias = dias_especiales_proximos(hoy)
    if not dias:
        return None

    lineas = []
    for d, turnos in dias:
        normales = TURNOS_VIERNES if d.weekday() == 4 else TURNOS_SABADO if d.weekday() == 5 else ()
        caidos = [h for h in normales if h not in turnos]
        linea = f"· {_label_dia(d)}: SOLO {' y '.join(turnos)}"
        if caidos:
            linea += f" (NO hay turno de {' ni de '.join(caidos)} ese día)"
        lineas.append(linea)

    return (
        f"[SISTEMA — HORARIO ESPECIAL, {MOTIVO_ESPECIAL}. Esto MANDA sobre cualquier "
        "horario que figure en tus instrucciones:\n"
        + "\n".join(lineas)
        + "\nEl domingo no cambia. Aplica tanto al DESAFÍO FENIX como al entrenamiento "
        "regular de las familias inscriptas.\n"
        "Si un padre pregunta si hay entrenamiento ese día, la respuesta es SÍ: hay uno "
        "solo, en el horario de arriba. NUNCA ofrezcas ni menciones los turnos que no "
        "corren ese día.]"
    )


async def estado_cupo(fecha_iso: str, hora: str) -> tuple[str, int]:
    """(estado, reservados) de un turno. Estados: "libre" | "sold_out" | "cerrado".

    - libre    (< 10): se vende normal.
    - sold_out (10-19): al padre se le dice que ese turno se llenó y que consultamos con
      el profe; el admin decide. NO se bloquea sola.
    - cerrado  (>= 20): el turno no entra más gente.

    Ante un error de Airtable devuelve ("libre", 0): preferimos vender y que el admin
    corrija a cortar la venta por una caída de red.
    """
    from agent.airtable_client import _get_records, _HORARIOS
    try:
        formula = f"AND(DATESTR({{FECHA}})='{fecha_iso}', {{HORA}}='{hora}')"
        registros = await _get_records(_HORARIOS, formula=formula, max_records=1)
        if not registros:
            return "libre", 0
        reservados = len((registros[0].get("fields", {}) or {}).get("RESERVAS FENIX", []) or [])
    except Exception as e:
        logger.error(f"[DESAFIO] No pude leer el cupo de {fecha_iso} {hora}: {e}")
        return "libre", 0
    if reservados >= CUPO_REAL:
        return "cerrado", reservados
    if reservados >= CUPO_COMUNICADO:
        return "sold_out", reservados
    return "libre", reservados


async def crear_reservas_campus(nino_ids: list[str], turno_viernes: str, turno_sabado: str,
                                campus: dict | None = None) -> list[str]:
    """Inscribe a los niños en los TRES días del campus.

    Reusa obtener_o_crear_horario() y crear_reserva(), que ya son idempotentes: repetir
    la llamada no duplica reservas. Devuelve los record_id de las reservas creadas.

    Si un turno no es válido no se adivina: se levanta ValueError. Un turno inventado
    crearía un HORARIO fantasma y el niño quedaría anotado en un día que no existe.
    """
    from agent.airtable_client import obtener_o_crear_horario, crear_reserva

    campus = campus or proximo_campus()
    _validos_v, _validos_s = turnos_viernes_de(campus), turnos_sabado_de(campus)
    if turno_viernes not in _validos_v:
        raise ValueError(f"Turno de viernes inválido: {turno_viernes!r} (esperaba {_validos_v})")
    if turno_sabado not in _validos_s:
        raise ValueError(f"Turno de sábado inválido: {turno_sabado!r} (esperaba {_validos_s})")

    jornadas = [
        (campus["viernes"].isoformat(), turno_viernes),
        (campus["sabado"].isoformat(), turno_sabado),
        (campus["domingo"].isoformat(), HORA_DOMINGO),
    ]

    reservas: list[str] = []
    for nino_id in nino_ids:
        for fecha_iso, hora in jornadas:
            horario_id = await obtener_o_crear_horario(fecha_iso, hora)
            if not horario_id:
                logger.error(f"[DESAFIO] Sin HORARIO para {fecha_iso} {hora} — {nino_id} queda sin ese día")
                continue
            reserva_id = await crear_reserva(nino_id, horario_id)
            if reserva_id:
                reservas.append(reserva_id)
            else:
                logger.error(f"[DESAFIO] No pude reservar {nino_id} en {fecha_iso} {hora}")
    logger.info(f"[DESAFIO] Campus {campus['viernes'].isoformat()}: "
                f"{len(reservas)} reservas para {len(nino_ids)} niño(s)")
    return reservas


# ── Elección de turnos post-pago ─────────────────────────────────────────────
# El padre paga → completa el formulario → elige turno del VIERNES y del SÁBADO
# (el domingo es uno solo para todos). Con botones, no con texto libre: el flujo
# viejo pedía "escribime qué sábado te viene mejor" y había que adivinar la
# respuesta. El estado vive en flags de DB (Railway reinicia sin aviso).

_BTN_VIERNES = [{"id": "desafio_vie_1700", "title": "Viernes 17:00"},
                {"id": "desafio_vie_1930", "title": "Viernes 19:30"}]
_BTN_SABADO = [{"id": "desafio_sab_1100", "title": "Sábado 11:00"},
               {"id": "desafio_sab_1530", "title": "Sábado 15:30"}]
_TURNO_POR_BTN = {"desafio_vie_1700": "17:00", "desafio_vie_1930": "19:30",
                  "desafio_sab_1100": "11:00", "desafio_sab_1530": "15:30"}


async def _turnos_ofrecibles(fecha_iso: str, horas: tuple[str, ...]) -> tuple[list[str], bool]:
    """(horas que se pueden ofrecer, hay_alguna_llena).

    "cerrado" (20) se saca de la lista. "sold_out" (10-19) SÍ se sigue ofreciendo:
    el número que se comunica es 10, pero el techo real es 20 y la decisión de
    apretar un turno es de Iván, no del bot.
    """
    libres, llena = [], False
    for hora in horas:
        estado, _ = await estado_cupo(fecha_iso, hora)
        if estado == "cerrado":
            llena = True
            continue
        libres.append(hora)
    return libres, llena


async def ofrecer_turnos_viernes(telefono: str, proveedor, topic_id: int | None = None,
                                 tg_group: int = 0) -> bool:
    """Primer paso: los turnos del viernes. Deja el flag esperando la respuesta."""
    from agent.ab_test import actualizar_estado_flags
    from agent.memory import guardar_mensaje

    campus = proximo_campus()
    libres, _ = await _turnos_ofrecibles(campus["viernes"].isoformat(), turnos_viernes_de(campus))
    if not libres:
        await _avisar_sin_cupo(telefono, proveedor, campus, "viernes", topic_id, tg_group)
        return False

    texto = f"¡Listo! 🔥 Tu lugar en el DESAFÍO FENIX del {label_campus(campus)} está reservado.\n\n"
    texto += (f"Este *viernes*, como {MOTIVO_ESPECIAL}, hay un solo turno: {libres[0]} "
              "(día 1 — Descubrir). Confirmalo 👇"
              if len(libres) == 1 else
              "Ahora elegí el turno del *viernes* (día 1 — Descubrir) 👇")
    botones = [b for b in _BTN_VIERNES if _TURNO_POR_BTN[b["id"]] in libres]
    await proveedor.enviar_botones(telefono, texto, botones)
    await guardar_mensaje(telefono, "assistant", texto)
    await actualizar_estado_flags(telefono, desafio_espera_turno="viernes")
    await _espejar(topic_id, f"{texto}\n[botones: {' / '.join(libres)}]", telefono, tg_group)
    logger.info(f"[DESAFIO] {telefono}: ofrecidos turnos del viernes {libres}")
    return True


async def _espejar(topic_id: int | None, texto: str, telefono: str, tg_group: int) -> None:
    """Espejo a Telegram — best-effort, nunca rompe el flujo."""
    if not topic_id:
        return
    try:
        from agent.telegram_bridge import enviar_a_topic
        await enviar_a_topic(topic_id, f"👨‍🏫 IVAN: {texto}", telefono=telefono, group_override=tg_group)
    except Exception as e:
        logger.warning(f"[DESAFIO] No se pudo espejar en Telegram: {e}")


async def _avisar_sin_cupo(telefono: str, proveedor, campus: dict, dia: str,
                           topic_id: int | None, tg_group: int) -> None:
    """Los dos turnos del día llegaron al techo real (20). Se le dice al padre y
    se le avisa a Iván: la plata YA entró, así que esto no puede quedar en un log."""
    from agent.memory import guardar_mensaje
    import os
    texto = (f"Uff, los dos turnos del {dia} de este campus ya se llenaron 😅\n"
             "Dejame hablar con el profe a ver si te hacemos un lugarcito y te confirmo.")
    try:
        await proveedor.enviar_mensaje(telefono, texto)
        await guardar_mensaje(telefono, "assistant", texto)
    except Exception as e:
        logger.error(f"[DESAFIO] No pude avisarle del cupo a {telefono}: {e}")
    await _espejar(topic_id, texto, telefono, tg_group)
    admin = os.getenv("ADMIN_PHONE", "")
    if admin:
        try:
            await proveedor.enviar_mensaje(
                admin,
                f"⚠️ DESAFÍO SIN CUPO\n{telefono} PAGÓ y los dos turnos del {dia} "
                f"({label_campus(campus)}) están al tope de 20.\nHay que resolverlo a mano.",
            )
        except Exception as e:
            logger.error(f"[DESAFIO] No pude avisarle al admin del cupo lleno: {e}")


async def manejar_eleccion_turno(telefono: str, texto: str, btn_id: str | None,
                                 es_boton: bool, flags: dict, proveedor,
                                 topic_id: int | None = None, tg_group: int = 0) -> str | None:
    """Procesa la elección de turno. Devuelve None si no aplica (el flujo sigue).

    Igual que confirmacion_sabado.manejar_respuesta: se intercepta ANTES del menú
    y del brain para que la respuesta no caiga en el flujo conversacional.
    """
    from agent.ab_test import actualizar_estado_flags
    from agent.memory import guardar_mensaje

    espera = flags.get("desafio_espera_turno")
    if espera not in ("viernes", "sabado"):
        return None

    campus = proximo_campus()
    horas_validas = turnos_viernes_de(campus) if espera == "viernes" else turnos_sabado_de(campus)
    # Botón primero; si escribió, se acepta la hora textual ("17:00", "11") —
    # es un match contra valores conocidos, no un detector de intención nuevo.
    hora = _TURNO_POR_BTN.get(btn_id or "") if es_boton else None
    if hora not in horas_validas:
        hora = next((h for h in horas_validas
                     if h in (texto or "") or h.split(":")[0] in (texto or "").split()), None)
    if not hora:
        _todos = _BTN_VIERNES if espera == "viernes" else _BTN_SABADO
        botones = [b for b in _todos if _TURNO_POR_BTN[b["id"]] in horas_validas]
        recordatorio = "Tocá uno de los turnos 👇" if len(botones) > 1 else "Tocá el turno 👇"
        await proveedor.enviar_botones(telefono, recordatorio, botones)
        await guardar_mensaje(telefono, "assistant", recordatorio)
        return "[turno: recordatorio]"

    if espera == "viernes":
        await actualizar_estado_flags(telefono, desafio_turno_viernes=hora,
                                      desafio_espera_turno="sabado")
        libres, _ = await _turnos_ofrecibles(campus["sabado"].isoformat(), turnos_sabado_de(campus))
        if not libres:
            await _avisar_sin_cupo(telefono, proveedor, campus, "sábado", topic_id, tg_group)
            await actualizar_estado_flags(telefono, desafio_espera_turno=None)
            return "[turno sábado sin cupo]"
        pregunta = f"Genial, viernes {hora} ✅\n\n"
        pregunta += (f"Este *sábado*, como {MOTIVO_ESPECIAL}, hay un solo turno: {libres[0]} "
                     "(día 2 — Superar). Confirmalo 👇"
                     if len(libres) == 1 else
                     "Ahora el turno del *sábado* (día 2 — Superar) 👇")
        botones = [b for b in _BTN_SABADO if _TURNO_POR_BTN[b["id"]] in libres]
        await proveedor.enviar_botones(telefono, pregunta, botones)
        await guardar_mensaje(telefono, "assistant", pregunta)
        await _espejar(topic_id, f"{pregunta}\n[botones: {' / '.join(libres)}]", telefono, tg_group)
        logger.info(f"[DESAFIO] {telefono}: turno viernes {hora}")
        return "[turno viernes elegido]"

    # espera == "sabado" → ya están los dos turnos: se crean las 3 reservas
    turno_viernes = flags.get("desafio_turno_viernes") or TURNOS_VIERNES[0]
    from agent.airtable_client import obtener_grupo_familiar
    grupo = await obtener_grupo_familiar(telefono)
    nino_ids = [h["id"] for h in (grupo or {}).get("hijos", []) if h.get("id")]
    reservas = []
    if nino_ids:
        try:
            reservas = await crear_reservas_campus(nino_ids, turno_viernes, hora, campus)
        except Exception as e:
            logger.error(f"[DESAFIO] No pude crear las reservas de {telefono}: {e}")
    else:
        logger.error(f"[DESAFIO] {telefono} eligió turnos pero no tiene niños en el grupo")

    await actualizar_estado_flags(telefono, desafio_espera_turno=None,
                                  desafio_turno_sabado=hora, modo_agenda=False)

    v, s, d = campus["viernes"], campus["sabado"], campus["domingo"]
    confirmacion = (
        "¡Listo! Quedó reservado 🔥\n\n"
        f"📅 *Viernes {v.day}* — {turno_viernes} (Descubrir)\n"
        f"📅 *Sábado {s.day}* — {hora} (Superar)\n"
        f"📅 *Domingo {d.day}* — 12:00 Gran Desafío, 13:00 almuerzo en familia, "
        "15:00 cierre (Conquistar)\n\n"
        "📍 La Casona Lafuente — Maestras Paraguayas 2056\n"
        "https://maps.app.goo.gl/nZT5zGA7N8B76xmD6?g_st=iwb\n\n"
        "Traé ropa cómoda, zapatillas y agua 🌳"
    )
    await proveedor.enviar_mensaje(telefono, confirmacion)
    await guardar_mensaje(telefono, "assistant", confirmacion)
    await _espejar(topic_id, confirmacion, telefono, tg_group)
    logger.info(f"[DESAFIO] {telefono}: campus completo — vie {turno_viernes}, sáb {hora}, "
                f"{len(reservas)} reservas")
    return "[campus reservado]"
