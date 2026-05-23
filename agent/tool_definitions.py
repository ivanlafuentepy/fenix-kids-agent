# agent/tool_definitions.py — Schemas de tools para Claude API
# FENIX KIDS ACADEMY — migración a Tool Use

"""
Define los tools disponibles para cada agente.
Claude recibe estos schemas y DECIDE cuál llamar según el mensaje del usuario.
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
        "name": "consultar_precios",
        "description": (
            "Mostrar precios de clases de prueba y paquetes FENIX. "
            "Usar cuando el padre pregunta cuánto sale, precio, costo, tarifa, promo, paquete, plan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["prueba", "paquetes", "hermanos"],
                    "description": "prueba=clase suelta, paquetes=5/12 clases, hermanos=descuento 2+ hijos",
                },
            },
            "required": ["tipo"],
        },
    },
    {
        "name": "consultar_horarios",
        "description": (
            "Mostrar horarios y días de clase. "
            "Usar cuando el padre pregunta qué días, qué horarios, cuántas veces por semana, frecuencia."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "consultar_ubicacion",
        "description": (
            "Mostrar dirección y mapa de FENIX Kids Academy. "
            "Usar cuando el padre pregunta dónde queda, ubicación, dirección, cómo llegar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "consultar_duracion",
        "description": (
            "Informar cuánto dura la clase. "
            "Usar cuando el padre pregunta cuánto dura, cuánto tiempo, cuántas horas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "consultar_que_llevar",
        "description": (
            "Informar qué necesitan llevar a la clase. "
            "Usar cuando el padre pregunta qué llevar, qué necesitan, qué traer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "consultar_devolucion",
        "description": (
            "Informar política de devolución. "
            "Usar cuando el padre pregunta si devuelven, reembolso, garantía, si no le gusta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "consultar_medios_pago",
        "description": (
            "Informar medios de pago aceptados. "
            "Usar cuando el padre pregunta si aceptan efectivo, tarjeta, cómo pagar, formas de pago."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "enviar_datos_bancarios",
        "description": (
            "Enviar alias y datos bancarios para transferencia. "
            "Usar cuando el padre pregunta el alias, datos para transferir, o dice que ya transfirió sin mandar comprobante."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "enviar_afiche",
        "description": (
            "Enviar imagen/afiche con información visual al padre. "
            "Usar cuando corresponde mostrar precios, horarios o plan hermanos con imagen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["precios", "hermanos", "horarios"],
                    "description": "Tipo de afiche a enviar",
                },
            },
            "required": ["tipo"],
        },
    },
]
