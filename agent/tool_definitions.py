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
            "Cambiar horario o fecha de una clase de prueba ya reservada. "
            "Usar cuando el padre quiere cambiar de hora, mover la clase, reagendar, "
            "o dice que no puede ir a la hora que eligió."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hora_nueva": {
                    "type": "string",
                    "enum": ["9:30", "11:00", "15:30"],
                    "description": "Nueva hora para la clase. Solo usar si el padre ya la especificó.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "confirmar_reserva",
        "description": (
            "Confirmar una reserva de clase de prueba con fecha y hora específicas. "
            "Usar cuando el padre acepta una fecha/hora y se le confirma la reserva."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha": {
                    "type": "string",
                    "description": "Fecha de la clase (ej: '23 de mayo', 'sábado 30')",
                },
                "hora": {
                    "type": "string",
                    "enum": ["9:30", "11:00", "15:30"],
                    "description": "Hora de la clase",
                },
            },
            "required": ["fecha", "hora"],
        },
    },
]
