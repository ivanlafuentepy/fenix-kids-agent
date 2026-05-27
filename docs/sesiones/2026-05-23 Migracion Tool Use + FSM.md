---
up:: "[[FENIX KIDS MOC]]"
tags: fenix, arquitectura, migracion, tool-use, fsm
fecha: 2026-05-23
---

# Migración FENIX: De Frankenstein a Tool Use + FSM

> Sesión 2026-05-23 — Análisis completo del estado actual + plan de migración

---

## 1. El problema que detonó todo

**Caso Marcelo Saucedo (595994468797):**
- Lead con PRUEBA FENIX pagada, reservado para sábados 23 y 30 de mayo a las 11:00h
- HOY pidió cambiar a las 15:30h
- FENIX le confirmó: "Te cambio a las 15:30h para el sábado 23 y sábado 30"
- **Airtable NO se actualizó** — sigue en 11:00h

**¿Por qué falló?**
1. El detector `_detectar_confirmacion_aurora()` parsea la RESPUESTA de Claude con regex
2. Los patrones esperan "sábado X a las Y" (fecha ANTES de hora)
3. Claude escribió "a las 15:30h para el sábado 23" (hora ANTES de fecha) → no matcheó
4. Cayó al patrón sin fecha → `{"fecha": "hoy", "hora": "15:30"}`
5. Pero el guard de pago busca "pago confirmado" en últimos 10 mensajes
6. "Pago confirmado!" era el mensaje #26 → fuera de la ventana de 10
7. Resultado: `confirmaciones = []` → se ignoró silenciosamente

**Conclusión de Ivan:** "No podemos depender de cómo Claude responde. Decenas de veces hicimos estos parches y siempre pasa lo mismo."

---

## 2. El Frankenstein: Estado actual del agente

### Números del horror

| Métrica | Valor | Problema |
|---------|-------|----------|
| Líneas en main.py | **8000+** | Debería ser ~200 |
| Interceptores regex pre-Claude | **15** | Una palabra diferente = no detecta |
| Detectores regex post-Claude | **6** | Dependemos de cómo Claude redacta |
| Variables in-memory | **17** | Se pierden en cada deploy |
| Tools de Claude API | **0** | No usamos la capacidad más potente |
| Archivos en agent/ | 18 | Solo main.py tiene el 60% del código |

### Interceptores PRE-Claude (regex sobre texto del usuario)

| Función | Detecta | Acción |
|---------|---------|--------|
| `_padre_pregunta_precios()` | Preguntas sobre precios/costos | Enviar afiche precios |
| `_padre_pregunta_hermanos()` | Preguntas sobre 2+ hijos | Enviar afiche hermanos |
| `_padre_pregunta_horarios()` | Preguntas sobre horarios/días | Enviar afiche horarios |
| `_padre_pregunta_ubicacion()` | Dónde queda | Respuesta fija + mapa |
| `_padre_pregunta_duracion()` | Cuánto dura la clase | "80 minutos" |
| `_padre_pregunta_que_llevar()` | Qué llevar | "Ropa cómoda, zapatillas, agua" |
| `_padre_pregunta_devolucion()` | Devolución/garantía | "No hay compromiso" |
| `_padre_pregunta_efectivo()` | Medios de pago | "Solo transferencia" |
| `_padre_dice_ya_transfiri()` | "Ya pagué" sin comprobante | "Mandame foto" |
| `_padre_pregunta_alias()` | Alias bancario | "CI: 1604338" |
| `_detectar_pedido_llamada()` | "Llamame", "una llamada" | Alerta admin |
| `_es_spam_o_scam()` | Links sospechosos | Silenciar + alerta |
| `_es_mensaje_sospechoso()` | Prompt injection | Silenciar + alerta |
| `_diagnostico_ya_enviado()` | Ivan ya envió diagnóstico | Flag para pitch |
| `_padre_muestra_interes()` | Respuestas afirmativas post-diagnóstico | Enviar afiche |

### Detectores POST-Claude (regex sobre respuesta del LLM)

| Detector | Busca en respuesta | Acción |
|----------|-------------------|--------|
| `_detectar_confirmacion_aurora()` | "reserva confirmada/sábado X a las Y" (12+ patrones) | Crear PRUEBA FENIX en Airtable |
| `REGISTRO PADRE:` regex | "REGISTRO PADRE: nombre apellido" | Actualizar FAMILIA |
| `REGISTRO HIJO:` regex | "REGISTRO HIJO: nombre, nac, CI, talla" | Crear NIÑO |
| `cancelé la reserva` regex | "cancelé la reserva sábado D a las H" | Cancelar RESERVAS |
| `[SISTEMA:]` limpiador | Bloques internos | Eliminar (no enviar al padre) |
| `te llamo a las X` regex | Llamada programada | Programar recordatorio |

### Variables de estado in-memory (se pierden en cada deploy)

| Variable | Tipo | Estado que trackea |
|----------|------|--------------------|
| `_prueba_creada` | set | PRUEBA FENIX ya creada |
| `_afiche_enviado` | set | Afiche precios ya enviado |
| `_afiche_hermanos_enviado` | set | Afiche hermanos ya enviado |
| `_afiche_horarios_enviado` | set | Afiche horarios ya enviado |
| `_registro_ya_iniciado` | set | Ya pasó por flujo Aurora |
| `_diagnostico_pendiente` | dict | Task asyncio de diagnóstico |
| `_admin_modo_padre` | set | Admin en modo normal vs secre |
| `_asistencia_pendiente` | dict | Admin esperando respuesta asis |
| `_inscripcion_pendiente` | dict | Flujo inscripción activo |
| `_fotos_sesion` | dict | Sesión fotos en progreso |
| `_cara_pendiente` | dict | Esperando foto para cara |
| `_cara_candidatos` | dict | Múltiples candidatos cara |
| `_cara_record_preseleccionado` | dict | Record preseleccionado |
| `_cara_media_pendiente` | dict | Media ID para cara |
| `_esperando_pago_promo_madre` | set | Esperan comprobante promo |
| `_leads_promo_madre_enviada` | set | Ya recibieron plantilla |
| `_esperando_formulario_promo` | set | Esperan datos post-pago |

### Flujo actual de `_procesar_mensaje_interno()` (~1500 líneas)

```
FASE 0: Setup (líneas 2319-2925)
  1. Capturar ad_source de anuncios Meta
  2. Transcribir audio
  3. 20+ comandos admin (resumen, asis, fotos, modo padre, etc.)
  4. Diagnóstico pendiente (si padre dice "ok" → ignorar)

FASE 1: Preparación (líneas 2872-2934)
  5. Espejo Telegram del mensaje del padre
  6. Guardar mensaje en DB (early save)
  7. Alerta diagnóstico (TDAH/TEA)

FASE 2: Seguridad (líneas 2968-3233)
  8. Verificar si Ivan responde manualmente
  9. PROMO MADRE (3 sub-flujos)
  10. Detectar comprobante pago
  11. Pedido de llamada
  12. Spam/scam
  13. Prompt injection

FASE 3: Business logic (líneas 3235-3370)
  14. Modo nocturno
  15. Obtener historial + variante
  16. Router Ivan/Aurora
  17. Inyectar contexto

FASE 4: Interceptación pre-Claude (líneas 3372-3473)
  18. Mensaje apertura fijo (FASE 1 del funnel)
  19. 10 interceptores FAQ (precios, horarios, ubicación, etc.)

FASE 5: Claude (línea 3476)
  20. generar_respuesta() — SIN tools

FASE 6: Post-procesamiento (líneas 3484-3900)
  21. Limpiar [SISTEMA:]
  22. Anti-repetición
  23. Actualizar lead en Airtable
  24. Detectar registro padre/hijo (Aurora)
  25. Detectar cancelación reserva
  26. Detectar confirmación reserva ← DONDE FALLÓ MARCELO
  27. Detectar llamada programada

FASE 7: Envío (líneas 3870+)
  28. Guardar respuesta
  29. Delay humano
  30. Enviar a WhatsApp
  31. Espejo Telegram
  32. Ejecutar acciones (afiches)
```

---

## 3. Investigación: 7 arquitecturas de agentes

Se investigaron 7 modelos de arquitectura para agentes de atención al cliente:

### 1. Tool Use (Anthropic)
Claude recibe lista de tools con schema JSON. DECIDE cuál llamar y con qué parámetros. Respuesta estructurada, cero regex.
- **Pro:** Zero regex, nativo en Claude API, schema validado
- **Contra:** Tool descriptions agregan tokens

### 2. Router + Workers (Anthropic)
Un Haiku clasifica la intención → despacha a handler especializado.
- **Pro:** Cada handler tiene prompt optimizado
- **Contra:** 2 llamadas API por mensaje

### 3. LangGraph
Grafo dirigido: nodos = funciones, edges = transiciones. Estado tipado.
- **Pro:** Visual, estado explícito, checkpointer
- **Contra:** Dependencia pesada (LangChain), curva alta

### 4. ReAct Loop (Think → Act → Observe)
El LLM razona, llama tool, observa resultado, decide si necesita más.
- **Pro:** Maneja múltiples intenciones
- **Contra:** 2-5x costo y latencia

### 5. Rasa CALM
LLM entiende → flows determinísticos ejecutan (YAML).
- **Pro:** Ejecución 100% determinística
- **Contra:** Framework enterprise pesado

### 6. FSM + LLM
Máquina de estados finitos. Estado en DB, transiciones predecibles.
- **Pro:** Extremadamente predecible, liviano
- **Contra:** Rígido para conversaciones abiertas

### 7. Multi-Agent (Supervisor)
Supervisor despacha a agentes especializados (pagos, horarios, ventas).
- **Pro:** Cada agente es pequeño y enfocado
- **Contra:** 2-3x costo API

### Comparación

| Patrón | Complejidad | Costo API | Regex | Ideal para |
|--------|------------|-----------|-------|------------|
| Tool Use | **Baja** | Igual | **0** | 10-30 acciones |
| Router+Workers | Media | 2x | 0 | Handlers especializados |
| LangGraph | Alta | Variable | 0 | Flujos complejos |
| ReAct Loop | Media | 2-5x | 0 | Multi-intención |
| Rasa CALM | Muy Alta | N/A | 0 | Enterprise |
| FSM + LLM | **Baja** | Igual | **0** | Flujos lineales |
| Multi-Agent | Alta | 2-3x | 0 | Muchos dominios |

### Decisión: Tool Use + FSM híbrido

**Tool Use** → Claude decide la acción. Elimina TODOS los regex.
**FSM** → Estado persistente en DB. No se pierde en deploy.

---

## 4. Plan de migración

### Arquitectura nueva

```
WhatsApp → main.py (~200 líneas, solo webhook + dispatch)
    ↓
1. ¿Comando admin? → admin/comandos.py (determinístico)
2. ¿Comprobante? → tools/pagos.py (determinístico)
3. Obtener estado FSM de DB
4. brain.py → Claude Haiku 4.5 CON TOOLS
    ↓
Claude DECIDE: ¿texto o tool_use?
    ↓
tool_use → tool_executor.py → función Python → resultado a Claude → responde
texto → enviar al padre + espejo Telegram
```

### Estructura de archivos

```
agent/
  main.py              ← SOLO webhook + dispatch (~200 líneas)
  brain.py             ← Claude API CON tool_use loop
  router.py            ← FSM: estado + transiciones
  tool_definitions.py  ← Schemas JSON de tools
  tool_executor.py     ← Dispatcher: tool_name → función
  tools/
    info.py            ← precios, horarios, ubicación
    reservas.py        ← agendar, cancelar, reagendar
    pagos_tools.py     ← comprobante, registrar pago
    escalacion.py      ← escalar a humano
    familia.py         ← registrar padre/hijo (Aurora)
  admin/
    comandos.py        ← resumen, asis, fotos, etc.
```

### Fases incrementales

| Fase | Qué | Duración | Riesgo |
|------|-----|----------|--------|
| **0** | Persistir estado in-memory en DB | 1-2 días | Bajo |
| **1** | Extraer tools como funciones puras | 2-3 días | Bajo (refactor) |
| **2** | Implementar Tool Use en brain.py | 2-3 días | **Alto** (cambio core) |
| **3** | Conectar al flujo con feature flag | 2-3 días | Medio |
| **4** | FSM persistente (opcional, después) | 3-5 días | Bajo |

### FASE 0 — Persistir estado (1-2 días)
- Columna `estado_json` en ConversacionAB
- Migrar 6 sets (`_afiche_enviado`, etc.) de in-memory a DB
- Los estados admin transitorios quedan in-memory (son cortos)

### FASE 1 — Extraer funciones (2-3 días)
- Crear `agent/tools/` con archivos separados
- Mover lógica de `_padre_pregunta_*` → `tools/info.py`
- Mover `_procesar_confirmacion_reserva` → `tools/reservas.py`
- main.py importa en vez de tener inline

### FASE 2 — Tool Use en brain.py (2-3 días)
- Definir tool schemas en `tool_definitions.py`
- Modificar `generar_respuesta()` para aceptar tools + loop
- Loop: Claude llama tool → ejecutar → resultado vuelve → Claude responde
- Max 3 rounds por mensaje

### FASE 3 — Feature flag (2-3 días)
- `USE_TOOL_USE=false` en Railway
- Flujo viejo y nuevo coexisten
- Migrar un interceptor a la vez (precios → horarios → reagendar → comprobante)
- Cuando todo migrado → `USE_TOOL_USE=true` → eliminar código viejo

### FASE 4 — FSM (3-5 días, posterior)
- Columna `estado` en ConversacionAB
- Estados: inicio → diagnostico → pitch → negociacion → esperando_pago → esperando_comprobante → formulario → confirmado → inscripto
- Tools filtrados por estado
- Router con transiciones definidas

### Ejemplo: Caso Marcelo con la nueva arquitectura

```
Marcelo: "quisiera cambiar el horario"

1. main.py recibe → no es admin, no es comprobante
2. brain.py con TOOLS_IVAN
3. Claude ve tool "reagendar_clase" → lo llama (sin hora, Marcelo no la dijo)
4. Tool: busca PRUEBA FENIX → retorna reservas actuales + horarios disponibles
5. Claude: "Tenés a Mauricio para 23 y 30 mayo a las 11:00h.
   Disponible: 9:30 | 15:30. ¿A cuál te cambio?"
6. Marcelo: "a las 15:30"
7. Claude: tool_use("reagendar_clase", {"hora_nueva": "15:30"})
8. Tool: patchea AMBOS registros en Airtable + notifica admin
9. Claude: "Listo! Te cambié a las 15:30h ✅"

CERO regex. Airtable actualizado. Admin notificado.
```

---

## 5. Fuentes

- [Building Effective Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [Advanced Tool Use — Anthropic](https://www.anthropic.com/engineering/advanced-tool-use)
- [LangGraph Review 2025](https://sider.ai/blog/ai-tools/langgraph-review-is-the-agentic-state-machine-worth-your-stack-in-2025)
- [Tool-Calling Architecture Patterns](https://medium.com/@vasanthancomrads/tool-calling-architecture-patterns-for-ai-agents-91c82333d662)
- [Rasa CALM](https://rasa.com/calm)
- [Haptik FSM](https://www.haptik.ai/tech/finite-state-machines-to-the-rescue/)
- [Redis AI Agent Architecture Patterns](https://redis.io/blog/ai-agent-architecture-patterns/)
