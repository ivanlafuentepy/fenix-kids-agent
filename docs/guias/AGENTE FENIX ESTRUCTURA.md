up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# AGENTE FENIX ESTRUCTURA
> Guia completa, replicable y escalable del agente WhatsApp de FENIX KIDS ACADEMY.
> Actualizar cada vez que se modifique arquitectura, prompts o tools.
> Ultima actualizacion: 2026-05-24

---

## 1. Que es este agente

Un agente de WhatsApp con IA que atiende leads y familias inscriptas de FENIX KIDS ACADEMY, un centro de entrenamiento funcional para chicos de 3 a 12 anios en Asuncion, Paraguay.

**Objetivo:** convertir consultas en reservas de clase de prueba (leads) y gestionar reservas de familias inscriptas (operaciones). Todo dentro del chat de WhatsApp, sin intervencion humana salvo excepciones.

**Resultado medible:** cuantas veces por dia Ivan (el humano) interviene manualmente.

---

## 2. Arquitectura general

```
WhatsApp (padre escribe)
    |
Meta Cloud API (webhook POST /webhook)
    |
FastAPI (agent/main.py) -- servidor principal
    |
    +-- Dedup (PostgreSQL, 24h)
    +-- Rate Limit (10 msg / 60s por telefono)
    +-- Lock por telefono (asyncio.Lock, max 200)
    |
Router: es familia inscripta? (busca en FAMILIAS FENIX)
    |
    +-- SI --> Aurora (operaciones)
    +-- NO --> Ivan (ventas)
    |
Regex Interceptors (FAQ rapidas, 0 costo, instantaneas)
    |
    +-- Interceptado? --> respuesta directa (sin Claude)
    +-- No interceptado? --> Claude API
    |
Claude Haiku 4.5 (con o sin tools segun USE_TOOL_USE)
    |
    +-- Tool Use? --> tool_executor.py --> Airtable/Telegram/etc
    +-- Solo texto? --> respuesta directa
    |
Proveedor Meta (enviar respuesta)
    |
WhatsApp (padre recibe)
```

---

## 3. Stack tecnologico

| Componente | Tecnologia | Por que |
|---|---|---|
| Lenguaje | Python 3.11+ async | Performance + ecosystem IA |
| Servidor | FastAPI + Uvicorn | Async nativo, webhooks rapidos |
| Base de datos | PostgreSQL (prod) / SQLite (dev) | Railway da PostgreSQL gratis, SQLAlchemy async |
| ORM | SQLAlchemy 2.0 async (asyncpg) | Pool: size=5, max_overflow=10, recycle=300s |
| IA conversacional | Claude Haiku 4.5 | 95% ahorro vs Sonnet, suficiente para el flujo |
| IA extraccion datos | Claude Haiku 4.5 | Formularios estructurados (max_tokens=300) |
| WhatsApp | Meta Cloud API v21.0 | API oficial, gratis por conversacion |
| CRM | Airtable (9 tablas) | Ivan ya lo usaba, facil de operar |
| Notificaciones | Telegram Bot API | Espejo de conversaciones por topics |
| Audio | Groq Whisper | Transcripcion de audios de WhatsApp |
| Deploy | Railway | Auto-deploy en cada push a main |
| Tracking | Meta CAPI | Atribucion de conversiones de anuncios |

---

## 4. Por que Claude Haiku 4.5

**Modelo:** `claude-haiku-4-5-20251001`
**Max tokens:** 1024
**Timeout:** 25 segundos
**Reintentos:** 3 con backoff exponencial (2^n segundos)

**Razon:** Haiku cuesta ~95% menos que Sonnet y es suficiente para:
- Conversacion de ventas (flujo guiado por prompt)
- Extraccion de datos de formularios
- Tool use (5 tools Ivan, 6 tools Aurora)

**Cuando NO usar Haiku:** Si necesitas razonamiento complejo o multi-step. Para FENIX, el prompt guia el flujo paso a paso, asi que Haiku sobra.

**Cache de prompt:** `cache_control: {"type": "ephemeral"}` en el system prompt. Ahorra tokens cuando un lead frecuente escribe multiples mensajes (el system prompt no se re-procesa).

---

## 5. Los dos agentes

### Profe Ivan Lafuente (ventas)
- **Activacion:** por defecto para todo numero no inscripto
- **Flujo:** apertura -> nombre+edad -> personalizacion -> precio+promo -> cierre -> pago -> datos -> confirmacion
- **Prompt:** ~5400 chars, 97 lineas (refactoreado 2026-05-24)
- **Tools:** 5 (confirmar_reserva, reagendar_clase, consultar_disponibilidad, programar_llamada, escalar_a_humano)

### Aurora (operaciones)
- **Activacion:** cuando el telefono esta en FAMILIAS FENIX (campo CELL PADRE/MADRE o CELL LIMPIO)
- **Sin restriccion nocturna:** padres inscriptos pueden escribir a cualquier hora
- **Prompt:** ~3260 chars con seccion HERRAMIENTAS explicita
- **Tools:** 6 (agendar_clase, cancelar_reserva, consultar_agendados, registrar_familia, registrar_hijo, escalar_a_humano)

### Router (como decide)
```
1. Buscar telefono en FAMILIAS FENIX (Airtable)
2. Si encontrado --> Aurora (modo cliente_inscripto)
3. Si NO encontrado --> Ivan (modo lead)
4. Handoff Ivan->Aurora: cuando Ivan dice "te contacta Aurora/Nixie"
```

---

## 6. Sistema de 3 capas: Regex + Tools + Prompt

Esta es la arquitectura clave del agente. Tres capas que se complementan:

### Capa 1: Regex Interceptors (gratis, instantaneos)
**Donde:** `agent/main.py` + `agent/tools/detectores.py`
**Cuando:** ANTES de llamar a Claude
**Costo:** 0 tokens

Interceptan FAQ simples donde la respuesta es fija:
- **Precios** --> envia afiche + texto con precios
- **Horarios** --> envia afiche de horarios
- **Ubicacion** --> envia link Google Maps + texto
- **Duracion** --> "80 minutos aprox"
- **Que llevar** --> "ropa comoda, zapatillas y agua"
- **Devolucion** --> "no hacemos devolucion"
- **Efectivo** --> "solo transferencia bancaria"
- **Ya transfiri** --> activa flujo de pago
- **Alias bancario** --> envia datos bancarios
- **Llamada** --> alerta WhatsApp + Telegram al admin

**Por que regex y no tools:** Son gratis (0 API calls), instantaneos (<100ms), y las respuestas son siempre iguales. No hay razon para gastar tokens en algo que un regex resuelve mejor.

**Anti-duplicacion (guards):** Cada bloque regex tiene un guard que verifica si una tool ya ejecuto la misma accion. Si la tool ya lo hizo, el regex no duplica.

### Capa 2: Tools (acciones que modifican datos)
**Donde:** `agent/tool_definitions.py` + `agent/tool_executor.py` + `agent/tools/`
**Cuando:** Claude decide llamarlas durante la conversacion
**Costo:** tokens adicionales por round de tool use

Tools son para ACCIONES que requieren datos estructurados:
- Crear/modificar registros en Airtable
- Enviar notificaciones al admin
- Consultar datos en tiempo real

**Regla de oro:** Si la respuesta es siempre la misma --> regex. Si necesita datos del contexto o modifica estado --> tool.

#### Tools de Ivan (5)
| Tool | Cuando | Que hace |
|---|---|---|
| `confirmar_reserva(fecha, hora)` | Padre elige dia+hora | Crea PRUEBA FENIX en Airtable, notifica admin |
| `reagendar_clase(hora_nueva)` | Padre quiere cambiar hora | Actualiza PRUEBA FENIX, notifica admin |
| `consultar_disponibilidad(fecha, hora)` | Pregunta si hay lugar | Cuenta reservas por slot |
| `programar_llamada(hora_llamada)` | Pide que lo llamen | Crea recordatorio en DB |
| `escalar_a_humano(motivo, resumen)` | No sabe, tema sensible | Alerta WhatsApp+Telegram, silencia agente |

#### Tools de Aurora (6)
| Tool | Cuando | Que hace |
|---|---|---|
| `agendar_clase(fecha, hora)` | Padre inscripto quiere ir | Crea RESERVAS FENIX para todos los hijos |
| `cancelar_reserva(fecha, hora)` | Padre cancela | Borra RESERVAS FENIX |
| `consultar_agendados(fecha, hora)` | Pregunta quienes van | Lista nombres de ninos agendados |
| `registrar_familia(nombre, apellido)` | Da su nombre por primera vez | Crea/actualiza FAMILIAS FENIX |
| `registrar_hijo(nombre, ...)` | Da datos del hijo | Crea NINOS FENIX vinculado a familia |
| `escalar_a_humano(motivo, resumen)` | Igual que Ivan | Compartida con Ivan |

#### Tool Use Loop (brain.py)
```
1. Claude recibe mensaje + historial + system prompt + tools
2. Claude responde con texto y/o tool_use
3. Si tool_use --> ejecutar tool --> enviar resultado a Claude
4. Claude responde con texto y/o otra tool_use
5. Maximo 3 rounds (_MAX_TOOL_ROUNDS = 3)
6. Si solo texto (stop_reason=end_turn) --> retornar
```

#### Hooks (validacion pre/post tool)
**Pre-hooks (antes de ejecutar):**
- `validar_fecha_hora`: hora valida (9:30|11:00|15:30), fecha es sabado futuro
- `anti_escalacion_spam`: max 1 escalacion por telefono por hora

**Post-hooks (despues de ejecutar):**
- `notificar_telegram`: notifica reservas/cancelaciones al grupo
- `enviar_capi_event`: envia LeadSubmitted a Meta CAPI

### Capa 3: Prompt (comportamiento conversacional)
**Donde:** `config/prompts.yaml`
**Cuando:** Siempre que Claude responde
**Costo:** tokens de input (cacheados con ephemeral)

El prompt define:
- Identidad y tono (quien es, como habla)
- Frame de ventas (que vender, como venderlo)
- Flujo conversacional (fases 1-5)
- Restricciones (que nunca decir)
- Donde usar cada tool (integrado en las fases)

---

## 7. Estructura del prompt de Ivan

Refactoreado 2026-05-24. Principio: **las tools REEMPLAZAN texto del prompt, no se suman.**

```
ivan_prompt (5379 chars, 97 lineas):
|
+-- Identidad y tono (4 lineas)
|   Quien es, emojis, estilo WhatsApp
|
+-- Frame Global (4 lineas)
|   Papa + hijo JUNTOS, experiencia del sabado, naturaleza
|
+-- Prohibido (11 lineas)
|   Palabras y comportamientos prohibidos
|
+-- Estilo Conversacional (5 lineas)
|   Conversacion, no pitch. Abreviaciones WhatsApp.
|
+-- Datos del Negocio (15 lineas)
|   Ubicacion, horarios, precios, bancarios, paquetes
|   REGLA: precio TOTAL por familia, NUNCA desglosar
|
+-- Flujo de Conversacion (45 lineas)
|   FASE 1: apertura (sistema, no Claude)
|   FASE 2: nombre+edad -> personalizacion por edad
|   FASE 2B: dice si -> precio+promo
|       --> consultar_disponibilidad si pregunta lugar
|   FASE 3: elige dia+hora -> confirmar_reserva(fecha, hora)
|   FASE 4: post-pago -> pedir datos hijo
|   FASE 5: datos recibidos -> confirmacion final
|
+-- Objeciones (4 lineas)
|   Multi-hijo, planes, 3-4 anios, diagnostico
|
+-- Tools integradas en contexto (3 lineas)
|   reagendar_clase -> cambiar hora existente
|   programar_llamada -> agendar llamada
|   escalar_a_humano -> no sabe, sensible, pide humano
|
+-- Anti-loop y principio (2 lineas)
```

### Como integramos tools en el prompt (segun guia Anthropic)

**MAL (lo que hicimos primero y fallo):**
```
HERRAMIENTAS DISPONIBLES:
- reagendar_clase(hora_nueva): cambiar hora
- confirmar_reserva(fecha, hora): crear reserva
- ...
REGLA: si aplica, usala.
```
Esto confundio a Haiku. Veia `confirmar_reserva` y en vez de seguir el flujo conversacional, intentaba armar algo estructurado y generaba respuestas truncadas.

**BIEN (lo que funciona):**
```
FASE 2B -- CUANDO DICE SI:
Dar precio+promo...
Si pregunta disponibilidad -> usa la herramienta consultar_disponibilidad.

FASE 3 -- CIERRE (elige dia+horario):
Usa la herramienta confirmar_reserva(fecha, hora) para registrar.
```
Las tools aparecen en el MOMENTO del flujo donde aplican. Haiku no piensa en tools en las fases tempranas.

**Principio Anthropic:** "Tool descriptions are loaded into agent context, directly steering behavior. Even small refinements to tool descriptions can yield dramatic improvements."

---

## 8. Base de datos

### Tablas SQLAlchemy (PostgreSQL prod / SQLite dev)

| Tabla | Campos clave | Uso |
|---|---|---|
| ConversacionAB | telefono, agent_actual, modo_nixie, convertido, familia_id, estado_json | Estado por conversacion |
| Mensaje | telefono, role, content, timestamp | Historial de chat (limite: 20 ultimos) |
| Recordatorio | telefono, tipo, programado_para, enviado, payload | Recordatorios y seguimientos |
| PagoPendiente | telefono, tipo, monto, estado, media_id | Flujo de pagos |
| MensajeProcesado | mensaje_id, procesado_en | Dedup (24h) |
| TopicTelegram | telefono, topic_id, group_id, agente_silenciado | Espejo Telegram |

### Airtable (CRM, base SALSA SOUL)

| Tabla | Uso |
|---|---|
| LEADS FENIX | Leads nuevos (telefono, nombre, conversion, seguimiento) |
| PRUEBA FENIX | Reservas de clase de prueba |
| FAMILIAS FENIX | Familias inscriptas (padre, madre, telefonos) |
| NINOS FENIX | Hijos vinculados a familias |
| HORARIOS FENIX | Slots de horarios por sabado |
| RESERVAS FENIX | Reservas de familias inscriptas |
| CONTENIDO FENIX | Posts para redes sociales |
| ANUNCIOS FENIX | Seguimiento de anuncios Meta |

---

## 9. Flujo de pago (critico)

```
1. Ivan pasa datos bancarios (CI: 1604338 en el mensaje)
2. Padre envia foto de comprobante ([imagen])
3. Sistema detecta: es media + datos bancarios en historial + no ya pago
4. Registra PagoPendiente (tipo=prueba, monto=segun historial)
5. AUTO-CONFIRMA el pago (no hay validacion manual)
6. Inyecta "[SISTEMA: pago confirmado]" en el historial
7. Ivan (Claude) ve ese mensaje y pide datos del formulario
8. Notifica admin por WhatsApp + Telegram
9. Meta CAPI: envia evento Purchase
```

---

## 10. Background tasks

| Tarea | Frecuencia | Que hace |
|---|---|---|
| Recordatorios formulario | 15min, 2h, 8h, 23h | Pide datos si no los dio |
| Seguimiento inicial | 15min, 2h, 6h | Followup si no respondio al rompehielos |
| Modo noche | 07:00 AM PY | Procesa leads que escribieron de noche |
| Resumen diario | 08:00 AM PY | Anuncios + reservas del dia |
| Contenido social | cada 5 min | Polling de CONTENIDO FENIX (Airtable) |
| Calendario semanal | Lunes 10:00 AM | Envia horarios de la semana |
| Recordatorio viernes | Viernes | Recordatorio a padres inscriptos |
| Asistencia auto | 11:00, 12:30, 17:00 | Lista de asistencia post-turno |

---

## 11. Seguridad y proteccion

| Mecanismo | Implementacion |
|---|---|
| Rate limiting | 10 msg/60s por telefono (ventana deslizante) |
| Dedup | PostgreSQL persistente, 24h |
| Lock por telefono | asyncio.Lock (max 200 concurrentes) |
| Prompt injection | 5 frases peligrosas bloqueadas por regex |
| Spam/scam | 7 patrones regex (dominios sospechosos, premios) |
| Admin auth | Header X-ADMIN-KEY en endpoints protegidos |
| Kill switch | Variable AGENTE_PAUSADO pausa TODAS las respuestas |
| Anti-escalacion spam | Max 1 escalacion por telefono por hora |

---

## 12. Modos admin

| Comando | Efecto |
|---|---|
| (default) | Modo secreto: mensajes ignorados, solo comandos |
| "Modo padre" | Reset completo + flujo como lead nuevo |
| "Comandos" | Lista de comandos disponibles |
| AGENTE_PAUSADO | Kill switch global |

---

## 13. Integraciones externas

### Meta WhatsApp Cloud API
- Version: v21.0
- Webhook: POST /webhook
- Verify token: agentkit-verify
- Tipos soportados: texto, imagen, documento, audio, botones interactivos

### Telegram Bot API
- Espejo de conversaciones por topics (1 topic = 1 telefono)
- Notificaciones: pagos, reservas, llamadas, escalaciones
- IGNORE_PHONES: numeros sin espejo (ej: admin)

### Meta CAPI (Conversion API)
- Eventos: LeadSubmitted (al confirmar reserva), Purchase (al pagar)
- Dataset ID configurado en .env

### Groq Whisper
- Transcripcion de audios de WhatsApp
- El audio llega como [audio], se descarga, se transcribe, y se pasa como texto a Claude

---

## 14. Deploy y operacion

### Railway
- Auto-deploy en cada push a main
- Variables de entorno criticas: ANTHROPIC_API_KEY, META_ACCESS_TOKEN, AIRTABLE_API_KEY, DATABASE_URL
- Puerto: 8000
- Health check: GET / --> {"status": "ok"}

### Monitoreo
- Logs Railway con prefijos: [WA], [IVAN], [AURORA], [TOOL-USE], [HOOK-PRE], [HOOK-POST], [PAGOS], [AIRTABLE]
- Endpoints admin: /stats, /debug/{tel}, /conversacion/{tel}

---

## 15. Principios de diseno (lecciones aprendidas)

1. **Regex primero, IA como fallback** -- FAQ gratis e instantaneas. IA solo para lo que necesita razonamiento.

2. **Tools reemplazan texto del prompt** -- Si una tool ejecuta la accion, el prompt no necesita explicar como hacerla manualmente. El prompt se achica.

3. **Tools integradas en el flujo, no en bloque separado** -- Haiku se confunde si le das una lista de tools sin contexto. Poner cada tool en la fase donde aplica.

4. **Estado persistente en DB** -- Railway reinicia containers sin aviso. Todo lo que importa esta en PostgreSQL.

5. **Dedup obligatoria** -- Meta envia webhooks duplicados. Sin dedup, el agente responde 2 veces.

6. **NUNCA dejar que el LLM calcule fechas** -- Inyectar contexto exacto (hoy, manana, sabados del mes) en el system prompt.

7. **Deploy incremental** -- NUNCA pushear refactor grande de una vez. Paso a paso, verificando cada cambio.

8. **Haiku es suficiente** -- 95% ahorro vs Sonnet. El prompt guia el flujo, Haiku ejecuta.

9. **Early save** -- Guardar mensaje del usuario en DB ANTES de procesar. Si crashea, no se pierde.

10. **No mas parches regex** -- Si un regex se vuelve complejo, redisenar con tools/intents. Los regex son para respuestas fijas.

---

## 16. Estructura de archivos

```
agent/
  main.py              -- Servidor FastAPI, webhook, orquestacion (3500+ lineas)
  brain.py             -- Claude API, tool use loop, cache, extraccion datos
  memory.py            -- SQLAlchemy, historial, estado, pagos, dedup
  ab_test.py           -- Estado por conversacion (variante, agent, modo)
  pagos.py             -- Flujo de pagos: deteccion, confirmacion, precios
  airtable_client.py   -- CRM: 9 tablas, CRUD completo
  telegram_bridge.py   -- Espejo Telegram, notificaciones, topics
  reminders.py         -- Recordatorios, seguimientos, guardado parcial
  transcriber.py       -- Groq Whisper, transcripcion de audios
  hooks.py             -- Pre/Post tool hooks (validacion + notificaciones)
  tool_definitions.py  -- Schemas: TOOLS_IVAN (5) + TOOLS_AURORA (6)
  tool_executor.py     -- Dispatcher: 10 tools + errores estructurados
  meta_capi.py         -- Meta Conversion API (LeadSubmitted, Purchase)
  providers/
    base.py            -- Clase abstracta ProveedorWhatsApp
    meta.py            -- Adaptador Meta Cloud API v21.0
  tools/
    reservas.py        -- reagendar_clase + confirmar_reserva_prueba
    escalacion.py      -- escalar_a_humano (compartida Ivan/Aurora)
    disponibilidad.py  -- consultar_disponibilidad + consultar_agendados
    llamada.py         -- programar_llamada
    agenda.py          -- agendar_clase + cancelar_reserva (Aurora)
    registro.py        -- registrar_familia + registrar_hijo (Aurora)
    detectores.py      -- 10 detectores regex FAQ
    info.py            -- Respuestas FAQ estaticas
config/
  prompts.yaml         -- System prompts Ivan (5400 chars) + Aurora (3260 chars)
  business.yaml        -- Datos del negocio
```

---

## 17. Metricas clave

| Metrica | Valor actual | Fuente |
|---|---|---|
| ivan_prompt | 5379 chars / 97 lineas | prompts.yaml |
| aurora_prompt | 3262 chars | prompts.yaml |
| Tools Ivan | 5 | tool_definitions.py |
| Tools Aurora | 6 | tool_definitions.py |
| Regex interceptors | 10+ patrones | detectores.py + main.py |
| Hooks | 3 pre + 2 post | hooks.py |
| Tablas Airtable | 9 | airtable_client.py |
| Background tasks | 8 | main.py lifespan |
| Max tokens | 1024 | brain.py |
| Historial | 20 ultimos mensajes | memory.py |
| Rate limit | 10 msg/60s | main.py |
| Tool rounds max | 3 | brain.py |

---

*Documento vivo. Actualizar en cada cambio de arquitectura.*
