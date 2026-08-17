# agent/desafio.py — DESAFÍO FENIX: el campus de 2 días que reemplaza la clase de prueba
"""
Desde 2026-08-09 la puerta de entrada a FENIX no es una clase de prueba de un sábado:
es el DESAFÍO FENIX, un campus de fin de semana. Desde el 17/08 el viernes quedó
afuera (decisión de Iván: tres días eran demasiado para las familias):

    SÁBADO   11:00-12:30  o  15:30-17:00  (el padre elige turno)          — DESCUBRIR
    DOMINGO  15:30 entrenamiento + Gran Desafío · 17:00 merienda y cierre — CONQUISTAR

Un campus se identifica por la fecha de su SÁBADO; no hay tabla nueva. La inscripción
de un niño son DOS reservas sobre el modelo de siempre (NINO + HORARIO), así que el QR,
la asistencia y el check-in siguen funcionando sin migrar nada.

Precio: 300.000 con reserva anticipada (hasta el viernes 23:59 PY), 450.000 después;
+150.000 por cada hermano en los dos casos. La merienda del domingo está incluida
para el NIÑO y para los PADRES.

Cupos: se comunican 10 por turno, pero el límite real es 20. Entre 10 y 19 el agente dice
que está lleno y escala al admin ("vamos a ver si entra uno más"), NO bloquea.
"""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("agentkit")

_TZ = ZoneInfo("America/Asuncion")

# Turnos que el padre elige (solo el sábado). El domingo es uno solo para todos.
TURNOS_SABADO = ("11:00", "15:30")
HORA_DOMINGO = "15:30"

# Excepciones por fecha: días que corren con otros turnos que los de arriba.
# La clave es la fecha ISO del día (sábado o domingo), así que la excepción se
# apaga SOLA cuando ese campus pasa — nadie tiene que acordarse de revertir nada
# el lunes. Las constantes de arriba nunca se tocan: siguen siendo la regla general.
TURNOS_ESPECIALES: dict[str, tuple[str, ...]] = {
    # ⚠️ Estos turnos son SOLO las sesiones del campus: un feriado NO tiene
    # entrenamiento regular para nadie (regla de Iván 12/08, ver
    # hay_entrenamiento_regular). Las tools de familias rebotan estas fechas.
}
MOTIVO_ESPECIAL = "es feriado"

# Campus que ya NO se venden (SOLD OUT decidido por Iván). La clave es el SÁBADO
# ISO del campus. Mismo patrón que TURNOS_ESPECIALES: cuando ese fin de semana
# pasa, la entrada queda muerta sola — no hay nada que revertir. proximo_campus()
# saltea estos sábados, así que precio, turnos, botones, textos y web pasan solos
# al campus siguiente.
CAMPUS_AGOTADOS: set[str] = set()

# El rango horario que se le comunica al padre para cada turno.
RANGO_TURNO = {"11:00": "11:00 a 12:30", "15:30": "15:30 a 17:00"}

# El campus en curso se deja de vender cuando arranca el turno 1 del sábado.
_INICIO_SABADO = time(11, 0)

PRECIO_ANTICIPADA = 300_000
PRECIO_NORMAL = 450_000
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

    Devuelve {"sabado": date, "domingo": date}.

    Se puede reservar hasta el sábado a la mañana (decisión de Iván 17/08): mientras el
    turno 1 del sábado no arrancó, el campus de este fin de semana sigue en venta. Una
    vez que empezó, se ofrece el del fin de semana siguiente — un padre que escribe el
    sábado al mediodía ya no puede sumarse al campus en curso.
    """
    ahora = ahora or ahora_py()
    hoy = ahora.date()
    sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7)
    if sabado == hoy and ahora.time() >= _INICIO_SABADO:
        sabado += timedelta(days=7)
    # Un campus SOLD OUT no se vende: se pasa directo al siguiente.
    while sabado.isoformat() in CAMPUS_AGOTADOS:
        sabado += timedelta(days=7)
    return {
        "sabado": sabado,
        "domingo": sabado + timedelta(days=1),
    }


def es_anticipada(ahora: datetime | None = None, campus: dict | None = None) -> bool:
    """¿Todavía vale el precio de reserva anticipada?

    El corte es el VIERNES 23:59 PY previo al campus: desde el sábado 00:00 se cobra el
    precio normal, aunque el campus recién arranque a las 11:00.
    """
    ahora = ahora or ahora_py()
    campus = campus or proximo_campus(ahora)
    return ahora.date() < campus["sabado"]


def precio_desafio(hijos: int = 1, ahora: datetime | None = None,
                   campus: dict | None = None) -> tuple[int, bool]:
    """(monto, es_anticipada) para esa cantidad de hermanos.

    Anticipada: 300.000 · 450.000 · 600.000    Normal: 450.000 · 600.000 · 750.000
    """
    hijos = max(1, int(hijos or 1))
    anticipada = es_anticipada(ahora, campus)
    base = PRECIO_ANTICIPADA if anticipada else PRECIO_NORMAL
    return base + EXTRA_HERMANO * (hijos - 1), anticipada


def turnos_de(fecha_iso: str, normales: tuple[str, ...]) -> tuple[str, ...]:
    """Los turnos que corren ESE día: la excepción si la hay, si no los de siempre."""
    return TURNOS_ESPECIALES.get(fecha_iso, normales)


def turnos_sabado_de(campus: dict | None = None) -> tuple[str, ...]:
    """Turnos del sábado de ese campus (puede ser uno solo si es feriado)."""
    campus = campus or proximo_campus()
    return turnos_de(campus["sabado"].isoformat(), TURNOS_SABADO)


def turnos_del_campus(campus: dict | None = None) -> list[tuple[str, str]]:
    """Los slots (fecha_iso, hora) del campus, en orden cronológico.

    Normalmente son 3; un fin de semana con turno único tiene menos.
    """
    campus = campus or proximo_campus()
    s, d = campus["sabado"].isoformat(), campus["domingo"].isoformat()
    slots = [(s, h) for h in turnos_sabado_de(campus)]
    slots.append((d, HORA_DOMINGO))
    return slots


def label_campus(campus: dict | None = None) -> str:
    """"sábado 22 y domingo 23 de agosto" — para los mensajes al padre.

    Si el campus cruza de mes, cada día lleva el suyo ("sábado 31 de agosto y
    domingo 1 de septiembre" no se acorta mal).
    """
    campus = campus or proximo_campus()
    s, d = campus["sabado"], campus["domingo"]
    if s.month == d.month:
        return f"sábado {s.day} y domingo {d.day} de {_MESES[s.month - 1]}"
    return (f"sábado {s.day} de {_MESES[s.month - 1]} "
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


def hay_entrenamiento_regular(fecha_iso: str) -> bool:
    """¿Ese día hay entrenamiento regular para las familias?

    Los días de TURNOS_ESPECIALES son feriados: esos días corre ÚNICAMENTE el
    campus del Desafío (con sus turnos reducidos) y NO hay entrenamiento regular
    para nadie — regla de Iván del 12/08. Las tools de agendar/reagendar y las
    listas de horarios disponibles tienen que rebotar esas fechas.
    """
    return fecha_iso not in TURNOS_ESPECIALES


def aviso_horario_especial(hoy: date | None = None) -> str | None:
    """El bloque que se le inyecta a AURORA cuando hay un feriado cerca.

    Un feriado NO tiene entrenamiento regular: ese día corre solo el campus del
    Desafío (regla de Iván 12/08). Devuelve None si no hay ninguno cerca — así
    el aviso aparece y desaparece solo, sin tocar el prompt (que está cacheado).
    """
    dias = dias_especiales_proximos(hoy)
    if not dias:
        return None

    fechas = " ni el ".join(_label_dia(d) for d, _ in dias)
    agotado = campus_agotado_visible(hoy)
    campus_txt = (" — que además ya está COMPLETO (sold out)" if agotado else "")

    return (
        f"[SISTEMA — {MOTIVO_ESPECIAL.upper()}: NO HAY ENTRENAMIENTO REGULAR este fin de "
        f"semana. El {fechas} NO entrena nadie: esos días corre únicamente el DESAFÍO "
        f"FENIX (el campus){campus_txt}.\n"
        "Si un padre pregunta si hay entrenamiento esos días, la respuesta es NO — "
        f"explicá que {MOTIVO_ESPECIAL} y que ese fin de semana corre solo el campus.\n"
        "NO agendes, NO reagendes y NO confirmes asistencia para esas fechas. "
        "El entrenamiento vuelve el fin de semana siguiente, en los horarios de siempre "
        "(sábados 11:00 o 15:30): ofrecé reagendar para ahí.]"
    )


def campus_agotado_visible(hoy: date | None = None) -> dict | None:
    """El campus SOLD OUT que todavía vale la pena mencionar, o None.

    Se menciona mientras su domingo no pasó: el lunes siguiente el sold out
    deja de ser noticia y el aviso se apaga solo, como todo lo demás.
    """
    hoy = hoy or ahora_py().date()
    candidatos = []
    for sabado_iso in CAMPUS_AGOTADOS:
        try:
            s = date.fromisoformat(sabado_iso)
        except ValueError:
            logger.error(f"[DESAFIO] Fecha inválida en CAMPUS_AGOTADOS: {sabado_iso!r}")
            continue
        if hoy <= s + timedelta(days=1):
            candidatos.append(s)
    if not candidatos:
        return None
    s = min(candidatos)
    return {"sabado": s, "domingo": s + timedelta(days=1)}


def nota_sold_out(hoy: date | None = None) -> str | None:
    """La línea de SOLD OUT para los mensajes del lead, o None si no aplica."""
    agotado = campus_agotado_visible(hoy)
    if not agotado:
        return None
    return (f"🔥 El campus de este fin de semana ({label_campus(agotado)}) "
            "ya está *SOLD OUT* — no quedan lugares.")


def bloque_turnos_vigentes(campus: dict | None = None) -> str:
    """Los turnos REALES del campus que se está vendiendo, para inyectar SIEMPRE.

    El prompt no lleva la lista de horarios escrita, igual que no lleva las fechas:
    con la lista adentro, Haiku la usaba para ofrecer "otro turno más tarde" aunque
    el contexto dijera que ese día corre uno solo (probado el 12/08: fallaba 2 de 2).
    """
    campus = campus or proximo_campus()
    s, d = campus["sabado"], campus["domingo"]
    ts = turnos_sabado_de(campus)

    def _rangos(turnos: tuple[str, ...]) -> str:
        return " o ".join(RANGO_TURNO.get(h, h) for h in turnos)

    bloque = (
        f"[SISTEMA — TURNOS VIGENTES del campus del {label_campus(campus)}. Son los ÚNICOS "
        "que existen: NO ofrezcas ni menciones ningún otro horario, aunque lo recuerdes.\n"
        f"· {_label_dia(s)} (Descubrir): {_rangos(ts)}\n"
        f"· {_label_dia(d)} (Conquistar): 15:30 entrenamiento + Gran Desafío "
        "· 17:00 merienda en familia y cierre\n"
    )
    if len(ts) == 1:
        bloque += (f"Los días con un solo turno son así porque {MOTIVO_ESPECIAL}. Si al padre "
                   "no le sirve ese horario, NO hay otro ese día: ofrecele el fin de semana "
                   "siguiente, que corre normal.\n")
    agotado = campus_agotado_visible()
    if agotado:
        bloque += (f"⚠️ El campus del {label_campus(agotado)} está SOLD OUT: no queda NINGÚN "
                   "lugar ese fin de semana, aunque el padre insista o pida 'uno más'. Si "
                   "pregunta por ese finde, decíselo con orgullo (se llenó) y ofrecele el "
                   "campus de arriba, que está en precio de reserva anticipada.\n")
    return bloque + "]"


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


async def crear_reservas_campus(nino_ids: list[str], turno_sabado: str,
                                campus: dict | None = None) -> list[str]:
    """Inscribe a los niños en los DOS días del campus.

    Reusa obtener_o_crear_horario() y crear_reserva(), que ya son idempotentes: repetir
    la llamada no duplica reservas. Devuelve los record_id de las reservas creadas.

    Si un turno no es válido no se adivina: se levanta ValueError. Un turno inventado
    crearía un HORARIO fantasma y el niño quedaría anotado en un día que no existe.
    """
    from agent.airtable_client import obtener_o_crear_horario, crear_reserva

    campus = campus or proximo_campus()
    _validos_s = turnos_sabado_de(campus)
    if turno_sabado not in _validos_s:
        raise ValueError(f"Turno de sábado inválido: {turno_sabado!r} (esperaba {_validos_s})")

    jornadas = [
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
    logger.info(f"[DESAFIO] Campus {campus['sabado'].isoformat()}: "
                f"{len(reservas)} reservas para {len(nino_ids)} niño(s)")
    return reservas


# ── Elección de turno post-pago ──────────────────────────────────────────────
# El padre paga → completa el formulario → elige turno del SÁBADO (el domingo es
# uno solo para todos). Con botones, no con texto libre: el flujo viejo pedía
# "escribime qué sábado te viene mejor" y había que adivinar la respuesta.
# El estado vive en flags de DB (Railway reinicia sin aviso).

_BTN_SABADO = [{"id": "desafio_sab_1100", "title": "Sábado 11:00"},
               {"id": "desafio_sab_1530", "title": "Sábado 15:30"}]
_TURNO_POR_BTN = {"desafio_sab_1100": "11:00", "desafio_sab_1530": "15:30"}


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


async def ofrecer_turnos_campus(telefono: str, proveedor, topic_id: int | None = None,
                                tg_group: int = 0) -> bool:
    """Único paso: los turnos del sábado. Deja el flag esperando la respuesta."""
    from agent.ab_test import actualizar_estado_flags
    from agent.memory import guardar_mensaje

    campus = proximo_campus()
    libres, _ = await _turnos_ofrecibles(campus["sabado"].isoformat(), turnos_sabado_de(campus))
    if not libres:
        await _avisar_sin_cupo(telefono, proveedor, campus, "sábado", topic_id, tg_group)
        return False

    texto = f"¡Listo! 🔥 Tu lugar en el DESAFÍO FENIX del {label_campus(campus)} está reservado.\n\n"
    # "es feriado" solo si el día DE VERDAD tiene turno único: libres también
    # queda en 1 cuando el otro turno se cerró por cupo, y eso no es un feriado.
    if len(turnos_sabado_de(campus)) == 1:
        texto += (f"Este *sábado*, como {MOTIVO_ESPECIAL}, hay un solo turno: {libres[0]} "
                  "(día 1 — Descubrir). Confirmalo 👇")
    elif len(libres) == 1:
        texto += (f"Del *sábado* queda un solo turno con lugar: {libres[0]} "
                  "(día 1 — Descubrir). Confirmalo 👇")
    else:
        texto += "Ahora elegí el turno del *sábado* (día 1 — Descubrir) 👇"
    botones = [b for b in _BTN_SABADO if _TURNO_POR_BTN[b["id"]] in libres]
    await proveedor.enviar_botones(telefono, texto, botones)
    await guardar_mensaje(telefono, "assistant", texto)
    await actualizar_estado_flags(telefono, desafio_espera_turno="sabado")
    await _espejar(topic_id, f"{texto}\n[botones: {' / '.join(libres)}]", telefono, tg_group)
    logger.info(f"[DESAFIO] {telefono}: ofrecidos turnos del sábado {libres}")
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
    """Todos los turnos del día llegaron al techo real (20). Se le dice al padre y
    se le avisa a Iván: la plata YA entró, así que esto no puede quedar en un log.

    "los turnos", sin número: un feriado corre con un turno único y "los dos" mentiría.
    """
    from agent.memory import guardar_mensaje
    import os
    texto = (f"Uff, los turnos del {dia} de este campus ya se llenaron 😅\n"
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
                f"⚠️ DESAFÍO SIN CUPO\n{telefono} PAGÓ y los turnos del {dia} "
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
    # "viernes" es residuo del flujo de 3 días: un padre que quedó a mitad de la
    # elección vieja al momento del deploy entra igual al único paso del sábado.
    if espera not in ("viernes", "sabado"):
        return None

    campus = proximo_campus()
    horas_validas = turnos_sabado_de(campus)
    # Botón primero; si escribió, se acepta la hora textual ("15:30", "11") —
    # es un match contra valores conocidos, no un detector de intención nuevo.
    hora = _TURNO_POR_BTN.get(btn_id or "") if es_boton else None
    if hora not in horas_validas:
        hora = next((h for h in horas_validas
                     if h in (texto or "") or h.split(":")[0] in (texto or "").split()), None)
    if not hora:
        botones = [b for b in _BTN_SABADO if _TURNO_POR_BTN[b["id"]] in horas_validas]
        recordatorio = "Tocá uno de los turnos 👇" if len(botones) > 1 else "Tocá el turno 👇"
        await proveedor.enviar_botones(telefono, recordatorio, botones)
        await guardar_mensaje(telefono, "assistant", recordatorio)
        return "[turno: recordatorio]"

    # Turno del sábado elegido → se crean las 2 reservas
    from agent.airtable_client import obtener_grupo_familiar
    grupo = await obtener_grupo_familiar(telefono)
    nino_ids = [h["id"] for h in (grupo or {}).get("hijos", []) if h.get("id")]
    reservas = []
    if nino_ids:
        try:
            reservas = await crear_reservas_campus(nino_ids, hora, campus)
        except Exception as e:
            logger.error(f"[DESAFIO] No pude crear las reservas de {telefono}: {e}")
    else:
        logger.error(f"[DESAFIO] {telefono} eligió turno pero no tiene niños en el grupo")

    await actualizar_estado_flags(telefono, desafio_espera_turno=None,
                                  desafio_turno_sabado=hora, modo_agenda=False)

    s, d = campus["sabado"], campus["domingo"]
    confirmacion = (
        "¡Listo! Quedó reservado 🔥\n\n"
        f"📅 *Sábado {s.day}* — {hora} (Descubrir)\n"
        f"📅 *Domingo {d.day}* — 15:30 entrenamiento + Gran Desafío, "
        "17:00 merienda en familia y cierre (Conquistar)\n\n"
        "📍 La Casona Lafuente — Maestras Paraguayas 2056\n"
        "https://maps.app.goo.gl/Mpo3g9wqBvALMvNEA\n\n"
        "Traé ropa cómoda, zapatillas y agua 🌳"
    )
    await proveedor.enviar_mensaje(telefono, confirmacion)
    await guardar_mensaje(telefono, "assistant", confirmacion)
    await _espejar(topic_id, confirmacion, telefono, tg_group)
    logger.info(f"[DESAFIO] {telefono}: campus completo — sáb {hora}, "
                f"{len(reservas)} reservas")
    return "[campus reservado]"
