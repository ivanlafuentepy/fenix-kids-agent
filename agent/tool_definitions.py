# agent/tool_definitions.py — Schemas de tools para Claude API
# FENIX KIDS ACADEMY — migración a Tool Use
#
# SOLO tools para acciones que fallan con regex.
# FAQ simples (precios, horarios, ubicación, etc.) se quedan como
# interceptores regex — son gratis, instantáneos y confiables.

"""
Tools para Claude: solo acciones de negocio que requieren
datos estructurados (Airtable, notificaciones, estado).
"""

TOOLS_IVAN = [
    {
        "name": "reagendar_clase",
        "description": (
            "Cambia la hora de una clase de prueba ya reservada en Airtable. "
            "Si hora_nueva está vacío, retorna la reserva actual + horarios disponibles. "
            "Si hora_nueva tiene valor, actualiza la reserva y notifica al admin. "
            "Retorna: {reservas_actuales, horarios_disponibles, reagendado: bool}. "
            "Usar cuando el padre quiere cambiar de hora, mover la clase, reagendar, "
            "o dice que no puede ir a la hora que eligió. "
            "NO usar para crear una reserva nueva (usar confirmar_reserva). "
            "NO usar si el padre no tiene reserva previa."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hora_nueva": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Nueva hora para la clase. Omitir si el padre aún no eligió hora.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "confirmar_reserva",
        "description": (
            "Confirma una reserva de clase de prueba con fecha y hora en Airtable. "
            "Actualiza el registro PRUEBA FENIX y notifica al admin. "
            "Retorna: {confirmada: bool, fecha, hora, hijos}. "
            "Usar cuando el padre acepta un sábado + horario y se le confirma la reserva. "
            "NO usar si el padre no dijo fecha Y hora. "
            "NO usar para cambiar una reserva existente (usar reagendar_clase)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": (
                        "Fecha de la clase. Acepta formato ISO (2026-05-31) o texto "
                        "('31 de mayo', 'sábado 31'). Se valida que sea sábado."
                    ),
                },
                "hora": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora de la clase.",
                },
            },
            "required": ["fecha", "hora"],
        },
    },
    {
        "name": "escalar_a_humano",
        "description": (
            "Transfiere la conversación al Profe Ivan real (humano). "
            "El agente se silencia y el admin recibe alerta con resumen en WhatsApp y Telegram. "
            "Retorna: {escalado: bool, texto: mensaje para el padre}. "
            "Usar cuando: no sabés la respuesta, el padre pide hablar con una persona, "
            "el tema es sensible (diagnóstico, queja, reembolso), o la pregunta está "
            "fuera del ámbito de FENIX KIDS. "
            "NO usar para preguntas de precios, horarios, ubicación u otras FAQ "
            "(el sistema las responde automáticamente). "
            "Después de escalar, NO seguir respondiendo — esperar a que el humano retome."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": [
                        "no_se_la_respuesta",
                        "padre_pide_humano",
                        "tema_sensible",
                        "fuera_de_ambito",
                        "queja_o_problema",
                    ],
                    "description": "Categoría del motivo de escalación.",
                },
                "resumen": {
                    "type": "string",
                    "description": (
                        "Resumen breve para el admin: qué preguntó el padre, "
                        "qué intentaste responder, qué debería hacer el admin."
                    ),
                },
            },
            "required": ["motivo", "resumen"],
        },
    },
    {
        "name": "consultar_disponibilidad",
        "description": (
            "Consulta cuántos niños hay agendados para un sábado y horario. "
            "Si fecha+hora: conteo para ese slot. Si solo fecha: conteo para los 3 turnos. "
            "Si nada: próximos sábados disponibles con conteos. "
            "Retorna: {slots: [{fecha, hora, cantidad}], texto}. "
            "Usar cuando el padre pregunta si hay lugar, cuántos van, o cuál turno tiene menos gente. "
            "NO usar para ver nombres de niños (privacidad). "
            "NO usar para agendar — solo consulta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha del sábado (ISO o texto). Omitir para ver próximos sábados.",
                },
                "hora": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora del turno. Omitir para ver los 3 turnos del día.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "programar_llamada",
        "description": (
            "Programa un recordatorio para que el Profe Ivan llame al padre a una hora específica. "
            "Si la hora ya pasó, retorna aviso para llamar ahora. "
            "Retorna: {programada: bool, hora, texto}. "
            "Usar cuando le decís al padre 'te llamo a las X' o el padre pide que lo llamen. "
            "NO usar para agendar clases (usar confirmar_reserva)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hora_llamada": {
                    "type": "string",
                    "description": "Hora para llamar (ej: '15:00', '3pm', '3'). Si es < 8, se asume PM.",
                },
            },
            "required": ["hora_llamada"],
        },
    },
]


TOOLS_AURORA = [
    {
        "name": "agendar_clase",
        "description": (
            "Crea RESERVA para todos los hijos de la familia inscripta en un sábado y horario. "
            "Por defecto reserva a TODOS los hijos. Si el padre dice solo un nombre, mencionar "
            "que se reservó para todos y confirmar si quiere cambiar algo. "
            "Retorna: {agendada: bool, fecha, hora, hijos, cantidad}. "
            "Usar cuando el padre dice que quiere ir, quiere agendar, reservar o confirmar asistencia. "
            "NO usar para leads (solo familias inscriptas). "
            "NO usar sin fecha Y hora confirmadas por el padre."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": (
                        "Fecha del sábado (ISO o texto: '31 de mayo', 'sábado 31', '31/5'). "
                        "Se valida que sea sábado."
                    ),
                },
                "hora": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora del turno.",
                },
            },
            "required": ["fecha", "hora"],
        },
    },
    {
        "name": "cancelar_reserva",
        "description": (
            "Cancela las reservas de la familia para un sábado. "
            "Si se indica hora, cancela solo ese turno. Si no, cancela todos los turnos del día. "
            "Retorna: {cancelada: bool, cantidad_borradas: int}. "
            "Usar cuando el padre dice que no puede ir, quiere cancelar, o no va a asistir. "
            "NO usar para reagendar (usar reagendar_clase)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha del sábado a cancelar.",
                },
                "hora": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora del turno a cancelar. Omitir para cancelar todo el día.",
                },
            },
            "required": ["fecha"],
        },
    },
    {
        "name": "consultar_agendados",
        "description": (
            "Muestra la lista de niños agendados para un sábado y horario, con nombres. "
            "Retorna: {lista: str formateada, cantidad: int}. "
            "Usar cuando el padre pregunta quiénes van, cuántos hay, o quiere ver la lista. "
            "NO usar para consultar disponibilidad sin nombres (eso es consultar_disponibilidad de Ivan)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha del sábado.",
                },
                "hora": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora del turno.",
                },
            },
            "required": ["fecha", "hora"],
        },
    },
    {
        "name": "registrar_familia",
        "description": (
            "Registra o actualiza el nombre del padre o madre en FAMILIAS FENIX. "
            "Detecta automáticamente si es padre o madre por el nombre. "
            "Si la familia ya existe, actualiza. Si no, crea nueva. "
            "Retorna: {registrada: bool, familia_id, rol: PADRE|MADRE}. "
            "Usar cuando el padre dice su nombre completo por primera vez o cuando se corrige. "
            "NO usar si ya tenés el nombre registrado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre de pila del padre/madre.",
                },
                "apellido": {
                    "type": "string",
                    "description": "Apellido. Puede omitirse si no lo dijo.",
                },
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "registrar_hijo",
        "description": (
            "Registra un hijo vinculado a la familia. "
            "La familia debe existir previamente (usar registrar_familia primero si no existe). "
            "Retorna: {registrado: bool, nino_id, familia_id}. "
            "Usar cuando el padre da datos de un hijo (nombre, fecha de nacimiento, CI, talla). "
            "NO usar si el hijo ya está registrado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre del hijo.",
                },
                "apellido": {
                    "type": "string",
                    "description": "Apellido del hijo.",
                },
                "fecha_nacimiento": {
                    "type": "string",
                    "description": "Fecha de nacimiento (cualquier formato legible).",
                },
                "ci": {
                    "type": "string",
                    "description": "Cédula de identidad del hijo.",
                },
                "talla_remera": {
                    "type": "string",
                    "description": "Talla de remera (ej: '4', '6', '8', '10', '12').",
                },
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "escalar_a_humano",
        "description": (
            "Transfiere la conversación al Profe Ivan real (humano). "
            "El agente se silencia y el admin recibe alerta con resumen en WhatsApp y Telegram. "
            "Retorna: {escalado: bool, texto: mensaje para el padre}. "
            "Usar cuando: no sabés la respuesta, el padre pide hablar con una persona, "
            "el tema es sensible, o la pregunta está fuera del ámbito. "
            "NO usar para preguntas operativas que podés resolver con las otras herramientas. "
            "Después de escalar, NO seguir respondiendo — esperar a que el humano retome."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": [
                        "no_se_la_respuesta",
                        "padre_pide_humano",
                        "tema_sensible",
                        "fuera_de_ambito",
                        "queja_o_problema",
                    ],
                    "description": "Categoría del motivo de escalación.",
                },
                "resumen": {
                    "type": "string",
                    "description": (
                        "Resumen breve para el admin: qué preguntó el padre, "
                        "qué intentaste resolver, qué debería hacer el admin."
                    ),
                },
            },
            "required": ["motivo", "resumen"],
        },
    },
    {
        "name": "reagendar_reserva",
        "description": (
            "Reagenda una clase inscripta: cancela la reserva vieja y crea la nueva en una sola operación. "
            "Requiere los 4 datos: fecha/hora actual (la que se va a cancelar) y fecha/hora nueva. "
            "Retorna: {reagendada: bool, fecha_anterior, hora_anterior, fecha_nueva, hora_nueva, hijos}. "
            "Usar cuando el padre quiere CAMBIAR una reserva existente a otra fecha u horario. "
            "Aurora ya le mostró la reserva actual, así que tiene fecha_actual y hora_actual. "
            "NO usar para crear reserva nueva sin tener una existente (usar agendar_clase). "
            "NO usar para cancelar sin reagendar (usar cancelar_reserva)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_actual": {
                    "type": "string",
                    "description": "Fecha de la reserva que se cancela (ISO o texto).",
                },
                "hora_actual": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora de la reserva que se cancela.",
                },
                "fecha_nueva": {
                    "type": "string",
                    "description": "Fecha nueva para la clase (ISO o texto).",
                },
                "hora_nueva": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora nueva para la clase.",
                },
            },
            "required": ["fecha_actual", "hora_actual", "fecha_nueva", "hora_nueva"],
        },
    },
]
