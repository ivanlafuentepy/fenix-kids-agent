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
                    "enum": ["9:30", "11:00", "15:30"],
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
                    "enum": ["9:30", "11:00", "15:30"],
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
]
