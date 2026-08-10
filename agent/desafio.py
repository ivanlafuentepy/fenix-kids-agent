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


def turnos_del_campus(campus: dict | None = None) -> list[tuple[str, str]]:
    """Los 5 slots (fecha_iso, hora) del campus, en orden cronológico."""
    campus = campus or proximo_campus()
    v, s, d = campus["viernes"].isoformat(), campus["sabado"].isoformat(), campus["domingo"].isoformat()
    return [(v, TURNOS_VIERNES[0]), (v, TURNOS_VIERNES[1]),
            (s, TURNOS_SABADO[0]), (s, TURNOS_SABADO[1]),
            (d, HORA_DOMINGO)]


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

    if turno_viernes not in TURNOS_VIERNES:
        raise ValueError(f"Turno de viernes inválido: {turno_viernes!r} (esperaba {TURNOS_VIERNES})")
    if turno_sabado not in TURNOS_SABADO:
        raise ValueError(f"Turno de sábado inválido: {turno_sabado!r} (esperaba {TURNOS_SABADO})")

    campus = campus or proximo_campus()
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
