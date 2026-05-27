up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# Guia: Claude Tool Use — Best Practices (Anthropic)

> Guia replicable para armar agentes WhatsApp con Claude + Tools.
> Basada en documentacion oficial de Anthropic + lecciones aprendidas en FENIX KIDS.
> Ultima actualizacion: 2026-05-24

---

## 1. Arquitectura de 3 capas

No todo necesita IA. Antes de llamar a Claude, filtrar:

| Capa | Cuando | Costo | Ejemplo |
|---|---|---|---|
| **Regex/interceptors** | Respuesta siempre igual | 0 tokens | "que horarios tienen?" -> afiche |
| **Tools** | Accion que modifica datos | Tokens extra por round | Crear reserva en Airtable |
| **Prompt** | Conversacion libre | Tokens normales | Personalizar respuesta por edad |

**Regla:** si la respuesta es siempre la misma -> regex. Si necesita datos del contexto o modifica estado -> tool. Si necesita razonamiento -> prompt.

---

## 2. Como escribir tool definitions

Fuente: [Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

**Nombres claros con namespace:**
```python
# MAL
{"name": "query_db", "description": "Execute query"}

# BIEN  
{"name": "confirmar_reserva", "description": "Confirma una reserva de clase de prueba con fecha y hora en Airtable..."}
```

**Descriptions son prompt engineering** — afectan directamente el comportamiento de Claude. Incluir:
- Que hace la tool
- Cuando usarla (casos positivos)
- Cuando NO usarla (casos negativos)
- Que retorna

```python
{
    "name": "reagendar_clase",
    "description": (
        "Cambia la hora de una clase de prueba ya reservada. "
        "Usar cuando el padre quiere cambiar de hora. "
        "NO usar para crear una reserva nueva (usar confirmar_reserva). "
        "NO usar si el padre no tiene reserva previa."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hora_nueva": {
                "type": "string",
                "enum": ["11:00", "15:30"],
                "description": "Nueva hora. Omitir si el padre aun no eligio.",
            },
        },
        "required": [],
    },
}
```

**Menos tools = mejor.** "More tools don't always lead to better outcomes." Solo acciones de alto impacto. No wrappear cada endpoint de API.

**Consolidar tools relacionadas.** En vez de `get_customer`, `list_transactions`, `list_notes` separadas -> una `get_customer_context` que compile todo.

---

## 3. Como integrar tools en el prompt

**MAL — bloque separado al final:**
```
HERRAMIENTAS DISPONIBLES:
- confirmar_reserva(fecha, hora): crear reserva
- reagendar_clase(hora_nueva): cambiar hora
- escalar_a_humano(motivo, resumen): transferir
REGLA: si aplica, usala.
```
Esto confunde a Haiku. Ve todas las tools juntas y se distrae del flujo conversacional. En nuestro caso, generaba respuestas truncadas porque intentaba armar algo estructurado en vez de conversar.

**BIEN — integradas en el flujo donde aplican:**
```
FASE 2B — CUANDO DICE SI:
Dar precio. Si pregunta disponibilidad -> usa la herramienta consultar_disponibilidad.

FASE 3 — CIERRE (elige dia+horario):
Usa la herramienta confirmar_reserva(fecha, hora) para registrar.

Si no sabes la respuesta -> usa la herramienta escalar_a_humano(motivo, resumen).
```
Cada tool aparece en el MOMENTO del flujo donde aplica. Claude no piensa en tools en las fases tempranas.

**Principio Anthropic:** "Tool descriptions are loaded into agent context, directly steering behavior. Even small refinements can yield dramatic improvements."

---

## 4. Tool Use Loop (como funciona en la API)

```
1. Enviar mensaje + system prompt + tools[] a Claude
2. Claude responde con texto y/o tool_use blocks
3. Si tool_use -> ejecutar la tool -> enviar resultado como tool_result
4. Claude procesa el resultado y responde (texto y/o mas tools)
5. Repetir hasta stop_reason=end_turn o max rounds
```

Configuracion recomendada:
```python
api_kwargs = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1024,
    "system": [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},  # cache del prompt
        }
    ],
    "messages": mensajes,
    "tools": tools_list,  # solo si hay tools
}
```

- **max rounds:** 3 (evitar loops infinitos)
- **timeout:** 25 segundos
- **reintentos:** 3 con backoff exponencial
- **errores de tool:** marcar `is_error: True` en tool_result para que Claude sepa que fallo

---

## 5. Tool Use Examples (accuracy 72% -> 90%)

Fuente: [Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)

Mostrar ejemplos concretos de uso mejora accuracy dramaticamente:
- Usar datos realistas (nombres reales, precios reales)
- Mostrar variedad: caso minimal, caso parcial, caso completo
- 1-5 ejemplos por tool
- Solo para tools donde el uso correcto no es obvio del schema

---

## 6. Hooks (validacion pre/post)

Antes y despues de ejecutar cada tool, correr validaciones:

**Pre-hooks (antes de ejecutar):**
- Validar parametros (fecha es sabado? hora es valida?)
- Anti-spam (max 1 escalacion por hora)
- Normalizar datos (fecha texto -> ISO)

**Post-hooks (despues de ejecutar):**
- Notificar a otros sistemas (Telegram, Meta CAPI)
- Actualizar estado

---

## 7. Principio de eficiencia del prompt

**Las tools REEMPLAZAN texto del prompt, no se suman.**

Antes (sin tools):
```
REGLA DE SILENCIO (CRITICO):
Si no sabes la respuesta, si no estas seguro...
-> responde EXACTAMENTE: "Te respondo en un minuto"
NADA MAS. No agregues nada. No inventes...
El sistema detecta esa frase y alerta al profe...
```
6 lineas.

Despues (con tool):
```
Si no sabes -> usa escalar_a_humano(motivo, resumen). NUNCA inventar.
```
1 linea. La logica pesada vive en la tool y el executor.

**Resultado real en FENIX:** prompt de Ivan paso de 8854 chars -> 5379 chars (-39%) y hace MAS cosas.

---

## 8. Resumen de decisiones clave

| Decision | Que hicimos | Por que |
|---|---|---|
| Modelo | Haiku 4.5 | 95% ahorro vs Sonnet, suficiente para flujo guiado |
| Cache | ephemeral en system prompt | Ahorra tokens en leads frecuentes |
| Tools en prompt | Integradas en fases, no en bloque | Haiku se confunde con bloque separado |
| FAQ | Regex interceptors | 0 costo, instantaneas, respuesta fija |
| Acciones | Tools | Datos estructurados, modifican Airtable |
| Validacion | Hooks pre/post | Fechas, horas, anti-spam automatico |
| Historial | 20 ultimos mensajes | Reducir tokens input |
| Fechas | Inyectadas por codigo | NUNCA dejar que el LLM calcule fechas |

---

## 9. Errores comunes (lo que aprendimos)

1. **Poner todas las tools en un bloque HERRAMIENTAS al final del prompt** -> Haiku se confunde, genera respuestas truncadas, intenta usar tools donde no debe.

2. **Dar tools sin mencionarlas en el prompt** -> Haiku las ignora completamente (0 tools en cada round). Necesita que el prompt le diga CUANDO usarlas.

3. **Wrappear todo como tool** -> Mas tools != mejor. FAQ con respuesta fija van mejor como regex (0 tokens, instantaneo).

4. **Dejar que el LLM calcule fechas** -> NUNCA. Inyectar "hoy es sabado 24 de mayo" en el system prompt. El LLM alucina fechas.

5. **Prompt largo con instrucciones manuales que la tool ya hace** -> Si la tool crea la reserva, el prompt no necesita explicar como crearla. Las tools REEMPLAZAN texto.

6. **Bloque HERRAMIENTAS al INICIO del prompt tampoco funciona** -> Probamos con Aurora: tenia un bloque "HERRAMIENTAS DISPONIBLES" con las 6 tools al inicio. Resultado: 0 tools en cada round, igual que Ivan. Haiku lee el bloque pero no lo conecta con el flujo. Solucion: eliminar el bloque y dejar las tools mencionadas SOLO en la seccion del flujo donde aplican.

7. **El problema es consistente entre agentes** -> Tanto Ivan como Aurora mostraron el mismo comportamiento: bloque separado = 0 tools. Integradas en flujo = las usa. No es un caso aislado, es como Haiku procesa la informacion.

8. **Reagendar = cancelar + crear (no modificar)** -> Si el prompt dice "reagendar: cancelar_reserva + agendar_clase" sin ser explicito, Haiku solo llama agendar_clase y deja la reserva vieja. Resultado: duplicados en Airtable. Solucion: instruccion CRITICA explicita "PRIMERO cancelar, DESPUES agendar. Si no cancelas primero quedan DOS reservas duplicadas."

9. **Las tools necesitan contexto de negocio, no solo schema** -> Claude recibe el schema de la tool (nombre, parametros, descripcion) via la API. Pero sin contexto en el prompt de CUANDO usarla, no la usa. El schema dice QUE hace, el prompt dice CUANDO hacerlo. Ambos son necesarios.

10. **Reduccion de prompt habilita mejor tool use** -> Prompt mas corto = menos ruido = Haiku entiende mejor cuando usar tools. Ivan paso de 8854 chars (sin tools funcionando) a 5379 chars (tools funcionando). Menos texto, mas accion.

---

## 10. Patron final validado

```
PROMPT (corto, solo flujo):
  FASE X: [instruccion conversacional]
  -> usa la herramienta [tool](params) para [accion].

TOOL DEFINITION (via API):
  name: tool_name
  description: que hace + cuando SI + cuando NO
  input_schema: parametros con enum/required

HOOKS (validacion automatica):
  PRE: validar params antes de ejecutar
  POST: notificar despues de ejecutar
```

Este patron funciona. Bloque separado no funciona. Probado con 2 agentes distintos (Ivan y Aurora) en produccion real.

---

## Sources

- [Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
- [Prompt Engineering Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [Context Engineering for Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
