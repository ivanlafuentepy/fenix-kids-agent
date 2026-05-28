# MIGRACION TOTAL — FENIX KIDS AGENT

## 1. QUE ES FENIX KIDS AGENT

FENIX KIDS AGENT es un agente de WhatsApp en produccion (Railway + PostgreSQL) que atiende leads y familias inscriptas de FENIX KIDS ACADEMY, una academia de entrenamiento infantil al aire libre en Asuncion, Paraguay.

**Stack**: Python 3.11+ async, FastAPI + Uvicorn, SQLAlchemy 2.0 async, PostgreSQL (prod) / SQLite (dev)
**Deploy**: Railway (container unico), URL: https://fenix-kids-agent-production.up.railway.app/
**IA**: Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) para respuestas y extraccion de datos
**Integraciones**: Meta WhatsApp Cloud API, Airtable CRM (6 tablas), Telegram (admin bidireccional), Google Calendar, Meta Conversion API (CAPI)

**Dos agentes con personalidades distintas**:
- **Ivan** (ventas/leads): Es el Profe Ivan Lafuente, director. Tono empatico, entusiasmado, estilo WhatsApp real. Vende la experiencia del PARQUE FENIX donde papa+hijo entrenan juntos al aire libre.
- **Aurora** (operaciones/familias): Asistente IA calida y eficiente. Agenda clases, lleva asistencia, gestiona datos de familias inscriptas.

---

## 2. ESTADO ACTUAL DETALLADO — COMO FUNCIONA CADA PIEZA

### 2.1 Estructura de archivos actual

```
fenix-kids-agent/
  agent/
    main.py                 # 8,010 lineas — EL MONOLITO (todo esta aca)
    brain.py                # 437 lineas — Conexion Claude API + agentic loop
    memory.py               # 471 lineas — SQLAlchemy ORM, 6 modelos, historial
    ab_test.py              # 309 lineas — Estado conversacion, flags, variantes A/B
    tool_definitions.py     # 56 lineas — 2 schemas de tools para Claude
    tool_executor.py        # 47 lineas — Dispatcher de tools
    pagos.py                # 225 lineas — Deteccion y flujo de pagos
    night_mode.py           # 126 lineas — Modo nocturno 23:00-07:00
    reminders.py            # 342 lineas — Recordatorios asincrónicos
    airtable_client.py      # 1,168 lineas — Cliente Airtable completo
    telegram_bridge.py      # 658 lineas — Telegram bidireccional
    meta_capi.py            # 81 lineas — Meta Conversion API
    validar_nombre.py       # 153 lineas — Validacion de nombres hispanos
    transcriber.py          # ~100 lineas — Transcripcion audio
    face_recognition.py     # ~250 lineas — Reconocimiento facial
    calendar_google.py      # Google Calendar
    contenido_social.py     # Distribucion contenido redes
    email_notifier.py       # Alertas email
    providers/
      base.py               # ABC ProveedorWhatsApp + MensajeEntrante
      meta.py               # Meta Cloud API adapter (~150 lineas)
      __init__.py            # Factory: obtener_proveedor()
    tools/
      detectores.py          # 123 lineas — 10 detectores regex de intencion
      reservas.py            # 99 lineas — Reagendamiento en Airtable
      info.py                # 103 lineas — Respuestas FAQ estaticas
  config/
    prompts.yaml             # 222 lineas — System prompts Ivan + Aurora
    business.yaml            # 69 lineas — Datos del negocio
```

**Total: 14,393 lineas de Python en ~26 archivos.**

### 2.2 El monolito: main.py (8,010 lineas)

Este archivo contiene TODO el flujo del agente. Detalle completo de lo que hay adentro:

#### Variables globales y estado en memoria (lineas 164-240)

```python
_locks_telefono: dict[str, asyncio.Lock]    # Lock por telefono (max 200, LRU cleanup)
_rate_limit: dict[str, list[float]]          # Timestamps para rate limit (10 msgs/60s)
_admin_modo_padre: set[str]                  # Admin phones en modo "padre" vs "secre"
_asistencia_pendiente: dict[str, list]       # Esperando respuesta de asistencia
_inscripcion_pendiente: dict[str, dict]      # Wizard inscripcion en progreso
_fotos_sesion: dict[str, dict]               # Sesion de fotos activa
_cara_pendiente: dict[str, str]              # Registro facial en espera
_cara_candidatos: dict[str, list]            # Multiples candidatos faciales
_cara_record_preseleccionado: dict           # Candidato seleccionado
_cara_media_pendiente: dict[str, str]        # Media pendiente para cara
_PROMO_MADRE_ACTIVA = False                  # Promo expirada (codigo muerto)
_esperando_pago_promo_madre: set[str]        # Codigo muerto
_leads_promo_madre_enviada: set[str]         # Codigo muerto
_USE_TOOL_USE = os.getenv("USE_TOOL_USE")    # Feature flag Tool Use
```

**PROBLEMA**: Todos estos dicts se pierden cuando Railway reinicia el container. `_asistencia_pendiente` e `_inscripcion_pendiente` son los mas criticos — si Railway reinicia mientras el admin esta marcando asistencia, pierde todo el progreso.

#### Funciones de seguridad (lineas 118-197)

- `_es_mensaje_sospechoso(texto)` — Detecta prompt injection (keywords como "ignora tus instrucciones", "jailbreak", etc.)
- `_es_spam_o_scam(texto)` — Regex para URLs sospechosas (.buzz, .xyz, fake money)
- `detectar_diagnostico(texto)` — Detecta menciones de TDAH/TEA/autismo para alertar admin
- `_obtener_lock(telefono)` — Lock asyncio por telefono para evitar race conditions
- `_check_rate_limit(telefono)` — Max 10 mensajes por 60 segundos por telefono

#### Background loops (lineas 365-500)

| Loop | Frecuencia | Que hace |
|------|-----------|----------|
| `_recordatorios_loop()` | Cada 60s | Poll PostgreSQL por recordatorios pendientes, envia los que toca |
| `_resumen_diario_loop()` | 08:00 AM PY | Envia resumen de anuncios + reservas al admin |
| `_noche_wakeup_loop()` | 07:00 AM PY | Procesa leads que escribieron entre 23:00-07:00 |
| `_asistencia_auto_loop()` | Sabados 11:00/12:30/17:00 | Envia lista de asistencia automatica al final de cada turno |
| `_followup_loop()` | 09:00 AM PY (DESACTIVADO) | Follow-up diario a leads sin respuesta |
| `contenido_social` | Cada 5 min | Polling Airtable por contenido nuevo para redes |

#### Endpoints (25 rutas)

| Ruta | Metodo | Proposito |
|------|--------|-----------|
| `/` | GET | Health check |
| `/webhook` | GET | Verificacion Meta |
| `/webhook` | POST | **Webhook principal — recibe mensajes WhatsApp** |
| `/api/reservas` | GET | Reservas por turno |
| `/stats` | GET | Estadisticas conversion (admin) |
| `/api/alumnos` | GET | Lista familias |
| `/api/alumno/{slug}` | GET | Perfil familia |
| `/test-envio/{phone}` | GET | Enviar mensaje test (admin) |
| `/debug/{phone}` | GET | Inspeccionar conversacion (admin) |
| `/restaurar-aurora/{phone}` | POST | Forzar Aurora en telefono (admin) |
| `/conversacion/{phone}` | GET | Historial completo (admin) |
| `/telegram/webhook` | POST | Webhook Telegram |
| `/telegram/setup` | GET | Registrar webhook Telegram |
| +12 endpoints debug/promo | GET | Varios debug y promo (admin) |

#### EL FLUJO PRINCIPAL: que pasa cuando llega un mensaje de WhatsApp

**POST /webhook → `_procesar_mensaje_interno()` (lineas 2325-4133)**

Este es el corazon del sistema. 1,800 lineas de logica secuencial:

```
PASO 1: Capturar metadata (ctwa_clid para Meta CAPI)
PASO 2: Si es audio → descargar de WhatsApp, transcribir con Whisper
PASO 3: Si es admin → despachar comando (comandos, promo madre, reset, presente, asistencia, fotos, registrar cara, cargar familia, resumenes)
PASO 4: Si admin en modo "secre" y no es comando → ignorar
PASO 5: Cancelar timers de follow-up pendientes
PASO 6: Si diagnostico pendiente + ACK → guardar sin responder
PASO 7: Deteccion spam/scam → silenciar agente, alertar admin
PASO 8: Deteccion prompt injection → silenciar, alertar
PASO 9: Night mode (23:00-07:00) → respuesta automatica, marcar pendiente
PASO 10: Obtener historial (20 msgs) + asignar variante A/B + get agent actual
PASO 11: Deteccion respuesta post-followup → marcar RESPONDIO_FU
PASO 12: Deteccion "Hola Aurora" → forzar Aurora, crear FAMILIA si no existe
PASO 13: Routing Ivan vs Aurora:
         - Buscar FAMILIA por telefono
         - Si existe → Aurora (cliente inscripto)
         - Si no existe → Ivan (lead nuevo)
         - Crear registro LEAD en Airtable si es nuevo
PASO 14: Si Aurora → inyectar contexto familia (padres, hijos, reservas activas, redes)
PASO 15: Si Ivan + padre ya pidio precios + tiene nombre+edad → inyectar "[SISTEMA: Hace el PITCH]"
PASO 16: Si lead nuevo + primer mensaje → respuesta fija hardcodeada (no Claude)
PASO 17: INTERCEPTORES FAQ (si Ivan):
         - padre_pregunta_precios() → afiche precios
         - padre_pregunta_hermanos() → afiche hermanos
         - padre_pregunta_horarios() → afiche horarios
         - padre_pregunta_ubicacion() → respuesta fija
         - padre_pregunta_duracion() → respuesta fija
         - padre_pregunta_que_llevar() → respuesta fija
         - padre_pregunta_devolucion() → respuesta fija
         - padre_pregunta_efectivo() → respuesta fija
         - padre_dice_ya_transfiri() → "Genial! Mandame comprobante"
         - padre_pregunta_alias() → "El alias es CI: 1604338"
         Si alguno matchea → respuesta inmediata, se salta Claude
PASO 18: Si NO fue interceptado → LLAMAR A CLAUDE:
         - Si USE_TOOL_USE + Ivan → generar_respuesta() con TOOLS_IVAN
         - Si no → generar_respuesta() sin tools
PASO 19: Limpiar [SISTEMA:...] de la respuesta
PASO 20: Anti-repeticion: quitar preguntas ya hechas (nombre, hijo, edad)
PASO 21: Extraer datos del lead (nombre padre, nombre hijo, edad) → actualizar Airtable
PASO 22: Si Aurora + "REGISTRO PADRE:" en respuesta → crear FAMILIA en Airtable
PASO 23: Si Aurora + "REGISTRO HIJO:" → crear NINO vinculado a FAMILIA
PASO 24: Si Aurora + "cancele la reserva" → parsear fecha/hora, borrar de RESERVAS
PASO 25: Si "tiene su lugar el sabado X a las Yh" → crear RESERVA o actualizar PRUEBA FENIX
PASO 26: Si "te llamo a las X" → programar alerta de llamada
PASO 27: Guardar respuesta en DB
PASO 28: Si datos bancarios en respuesta → marcar CONTACTADO, resetear seguimiento
PASO 29: Si formulario completo (pago + datos + fechas) → crear PRUEBA FENIX
PASO 30: Si afiche no enviado + Claude menciono precios → trigger afiche
PASO 31: Si "te respondo en un minuto" → escalada a humano via regex
PASO 32: Enviar respuesta WhatsApp con delay humano
PASO 33: Espejo a Telegram
PASO 34: Crear PRUEBA FENIX post-formulario (si corresponde)
```

#### Inyecciones [SISTEMA:] (mensajes invisibles para Claude)

| Contexto | Inyeccion | Proposito |
|----------|-----------|-----------|
| Ivan + precio + nombre+edad | "[SISTEMA: Hace el PITCH CORTO...]" | Guiar al pitch personalizado |
| Follow-up 1 | "[SISTEMA: El padre recibio datos bancarios hace 24h...]" | Guiar recordatorio |
| Follow-up 2 | "[SISTEMA: Segundo seguimiento...]" | Segundo recordatorio |
| Follow-up 3 | "[SISTEMA: Tercer y ultimo seguimiento...]" | Ultimo intento |
| Pago confirmado | "[SISTEMA: pago confirmado...]" | Trigger confirmacion reserva |
| Evaluacion aprobada | "[SISTEMA: EVALUACION_APROBADA]" | Continuar flujo post-evaluacion |

Todas se stripean antes de enviar al usuario.

### 2.3 brain.py — El agentic loop actual (437 lineas)

```python
async def generar_respuesta(mensaje, historial, agent_actual, contexto_extra, tools, tool_executor):
```

**Flujo**:
1. Carga system prompt de YAML + contexto de fechas (calculado con Python, NUNCA por Claude)
2. Construye mensajes: historial + mensaje actual
3. Loop de reintentos (3 intentos, backoff exponencial 2^n segundos)
4. Loop de tools (max 3 rounds):
   - Llama Claude con `cache_control: ephemeral` en system prompt
   - Si `stop_reason == "end_turn"` → extraer texto, retornar
   - Si `stop_reason == "tool_use"` → ejecutar cada tool, inyectar resultados, continuar
5. Si agotan rounds → retorna `obtener_mensaje_error()` (generico)

**Problemas del loop actual**:
- Linea 218: `if response.stop_reason == "end_turn" or not _usa_tools` — si tools desactivado, cualquier stop_reason se trata como end_turn
- Retorna `str` sin tools o `tuple[str, list[dict]]` con tools — dualidad confusa
- Error generico al agotar rounds — tools pueden haber ejecutado parcialmente
- Timeout 25s por request × 3 rounds = 75s potenciales de espera para el usuario

**Dual client**: Dos instancias `AsyncAnthropic` separadas para Ivan y Aurora (permiten keys distintas).

**Funciones auxiliares en brain.py**:
- `extraer_datos_formulario(historial)` — Haiku extrae nombre padre, hijos, DOB del chat
- `resumir_conversacion_para_alerta(historial)` — Haiku resume para admin
- `_alertar_fallo_api(error)` — Envia alerta a Telegram si Claude API falla

### 2.4 tool_definitions.py — 2 tools (56 lineas)

```python
TOOLS_IVAN = [
    {
        "name": "reagendar_clase",
        "description": "Cambiar horario o fecha de una clase de prueba ya reservada...",
        "input_schema": {
            "properties": {
                "hora_nueva": {"type": "string", "enum": ["9:30", "11:00", "15:30"]}
            },
            "required": []
        }
    },
    {
        "name": "confirmar_reserva",
        "description": "Confirmar una reserva de clase de prueba con fecha y hora...",
        "input_schema": {
            "properties": {
                "fecha": {"type": "string"},  # string libre — Claude puede inventar formatos
                "hora": {"type": "string", "enum": ["9:30", "11:00", "15:30"]}
            },
            "required": ["fecha", "hora"]
        }
    }
]
```

**Problemas**:
- Descripciones cortas, no dicen que RETORNA cada tool
- No dicen cuando NO usar (Anthropic: "la descripcion es el mecanismo de seleccion")
- `confirmar_reserva` requiere `fecha` como string libre — el modelo puede inventar formatos
- Solo 2 tools y Aurora no tiene ninguna

### 2.5 tool_executor.py — Dispatcher (47 lineas)

```python
_TOOLS = {
    "reagendar_clase": reagendar_clase,
    # confirmar_reserva NO ESTA ACA — BOMBA
}

async def ejecutar_tool(nombre, params, telefono):
    fn = _TOOLS.get(nombre)
    if not fn:
        return {"texto": f"Tool {nombre} no disponible.", "error": True}
    # ...
    except Exception as e:
        return {"texto": "Hubo un error procesando tu solicitud.", "error": True}
```

**BOMBA**: `confirmar_reserva` esta en `TOOLS_IVAN` (Claude puede llamarlo) pero NO esta en `_TOOLS` del executor. Resultado: Claude llama la tool → executor retorna error generico → usuario recibe "hubo un error".

**Error handling**: Catch generico, sin categorizar (transient vs validation vs business). Claude no sabe si reintentar o reformular.

### 2.6 memory.py — Base de datos (471 lineas)

**6 modelos SQLAlchemy**:

| Modelo | Campos clave | Proposito |
|--------|-------------|-----------|
| `ConversacionAB` | telefono, variante, conversion, agent_actual, modo, airtable_record_id, familia_record_id, calendar_id, estado_json, noche_pendiente, ctwa_clid | Estado maestro por conversacion |
| `Mensaje` | telefono, role, content, timestamp | Historial de chat |
| `Recordatorio` | telefono, hora_envio_utc, payload_json, enviado, cancelado | Recordatorios persistentes |
| `TopicTelegram` | telefono, topic_id, group_id, agente_silenciado, ultimo_mensaje_ivan | Mapping WhatsApp ↔ Telegram |
| `PagoPendiente` | telefono, tipo, plan, monto, media_id, estado | Comprobantes esperando confirmacion |
| `MensajeProcesado` | mensaje_id, procesado_en | Dedup webhooks (cleanup 24h) |

**`estado_json`**: Campo JSON flexible en ConversacionAB para flags arbitrarios (afiche_enviado, prueba_creada, formulario_completo, etc.). Es el "catch-all" de estado persistente.

### 2.7 prompts.yaml — System prompts (222 lineas)

**ivan_prompt** (~168 lineas):
- Identidad: "Sos el Profe Ivan Lafuente, director de FENIX KIDS ACADEMY"
- Frame: PARQUE FENIX, papa+hijo entrenan juntos, naturaleza, rio, arboles
- Frase ancla: "¿Te gustaria agendar un sabado inolvidable para vos y [nombre]?"
- Prohibiciones: "evaluacion", menu 1-15, "se descuenta", remera, devolucion, inventar precios
- Estilo: WhatsApp real, emojis moderados, abreviaciones (q, xke, x)
- Precios: tabla completa prueba (1/2/3 hijos) + promo + paquetes + descuentos familiares
- Datos bancarios: Itau, CI 1604338, cta 1074574
- Flujo 5 fases: apertura → personalizacion → pitch → cierre → post-pago → formulario
- Regla de silencio: si no sabe → "Te respondo en un minuto 😊" (NADA MAS)
- Anti-loop: no repetir preguntas, no presionar

**aurora_prompt** (~52 lineas):
- Identidad: "Sos Aurora, asistente IA de FENIX KIDS ACADEMY para familias inscriptas"
- Menu: 5 opciones (agendar, ver ninos, fotos, videos, redes)
- Multi-hijo: asumir TODOS van salvo que el padre diga lo contrario
- Confirmacion directa: incluir "Reserva confirmada" (el sistema lo detecta con regex)
- Cancelar: incluir "cancele la reserva" (el sistema lo detecta)
- Disponibilidad: solo conteo total, NUNCA nombres de otros ninos

**Problema del prompt**: mezcla identidad, reglas de negocio, flujo conversacional, datos bancarios, precios, prohibiciones — todo monolitico. Contradiccion: "NO presionar" vs "SIEMPRE cerrar con pregunta que empuje al siguiente paso".

### 2.8 Airtable — CRM (1,168 lineas, 6+ tablas)

| Tabla | Campos clave | Uso |
|-------|-------------|-----|
| LEADS FENIX | telefono, nombre, conversion (CONSULTA→CONTACTADO→PAGO→INSCRIPTO→DESCARTADO), agent_actual, diagnostico, fecha_reserva, hora_reserva, formulario | Tracking del funnel |
| FAMILIAS FENIX | padre/madre nombre+apellido+CI+telefono, cell_limpio | Datos de familias inscriptas |
| NINOS FENIX | nombre, apellido, fecha_nacimiento, CI, genero, talla_remera, familia (linked) | Datos de cada hijo |
| HORARIOS FENIX | fecha, hora, tipo | Slots disponibles |
| RESERVAS FENIX | nino (linked), horario (linked), familia (linked), presente | Reservas de clases |
| PRUEBA FENIX | telefono, nombre_resp, nombre_hijo, edad, fecha_reserva, hora, conversion, monto, metodo_pago | Clases de prueba |

### 2.9 Telegram bridge (658 lineas)

- **Topics por telefono**: Cada lead/familia tiene un topic en Telegram. Se crea automaticamente.
- **Espejo bidireccional**: Mensajes WhatsApp → Telegram topic, y admin responde desde Telegram → WhatsApp
- **Silencio**: Cuando admin responde, el agente se silencia 5 min (`silenciar_dorita`)
- **Notificaciones**: Reservas, pagos, llamadas urgentes → grupos separados de Telegram
- **Dos grupos**: Ivan (leads) y Aurora (familias inscriptas)

### 2.10 Pagos (225 lineas)

**Flujo completo**:
1. Ivan envia datos bancarios (CI: 1604338)
2. Padre envia comprobante ([imagen] o [documento])
3. `es_posible_comprobante()` detecta: debe ser imagen/doc + datos bancarios en historial + no confirmado ya
4. Sistema registra `PagoPendiente` en DB
5. Admin recibe alerta en Telegram con botones CONFIRMAR/RECHAZAR
6. Admin confirma → `confirmar_pago()` → actualiza LEADS (CONVERSION=PAGO) → Meta CAPI → notifica
7. Sistema inyecta "[SISTEMA: pago confirmado]" → Ivan confirma reserva

**Precios**:
- Prueba 1 hijo: 90,000 Gs | Promo: 100,000 (2 sabados)
- Prueba 2 hijos: 120,000 | Promo: 150,000
- Prueba 3 hijos: 150,000 | Promo: 180,000
- Paquete 5 clases: 350,000 | Paquete 12: 750,000

### 2.11 Night mode (126 lineas)

- 23:00-07:00 Paraguay → respuesta automatica "Gracias por contactarnos, mañana a las 06:00 seras el primero..."
- Marca `noche_pendiente=True` en DB
- A las 07:00 → loop procesa todos los pendientes: obtiene historial, genera respuesta con Claude, envia

### 2.12 Reminders (342 lineas)

**3 tipos**:
1. **Formulario** (4 msgs despues de reservar): +15min, +2h, +8h, +23h. Se cancelan si FORMULARIO=True.
2. **Seguimiento inicial** (3 msgs si lead no responde): +15min, +2h, +6h. Se cancelan con cualquier respuesta.
3. **Recordatorio clase** (persistente en DB): 07:00 AM del dia de la clase.

Todos respetan ventana 08:00-21:00 y limite 23.5h de WhatsApp.

---

## 3. DIAGNOSTICO — POR QUE RECONSTRUIR

### 3.1 Problemas criticos

**C1 — `confirmar_reserva` sin executor = BOMBA ACTIVA**
El tool esta en TOOLS_IVAN, Claude puede llamarlo, pero el executor no lo tiene registrado. Cuando un lead confirma una reserva, el agente responde con error generico. Esto pasa en produccion AHORA.

**C2 — main.py de 8,010 lineas = inmantenible**
Un archivo con webhook handler, 15 admin endpoints, 6 background loops, pagos, inscripciones, asistencia, fotos, follow-ups, resumenes, detectores, interceptores. Cada parche agrega lineas porque nadie puede refactorear sin romper algo. Es la causa raiz de la fragilidad.

**C3 — Errores genericos en tools = Claude ciego**
`return {"texto": "Hubo un error procesando tu solicitud.", "error": True}`. Claude no puede distinguir "Airtable caido" (reintentar en 2s) de "hora invalida" (pedir otra hora) de "lead sin reserva" (no hay nada que reagendar). Segun la guia Anthropic, los errores deben ser estructurados: `{error_category, is_retryable, message, attempted_query}`.

### 3.2 Problemas altos

**A1 — Sin hooks deterministicos para reglas de negocio**
Los precios, horarios validos y datos bancarios se "protegen" solo via prompt. Si Haiku alucina un precio (dice "80.000" en vez de "90.000"), no hay nada que lo detenga. La guia Anthropic dice: "consecuencias financieras → hooks, no prompts".

**A2 — Escalada fragil (frase magica)**
La escalada a humano depende de que Claude genere la frase EXACTA "Te respondo en un minuto 😊" y que main.py la detecte con regex. Es probabilistico. La guia Anthropic dice: "escalada = tool deterministica con handoff estructurado".

**A3 — Estado en memoria se pierde en redeploy**
`_asistencia_pendiente`, `_inscripcion_pendiente`, `_fotos_sesion` son dicts en memoria. Railway reinicia sin aviso → estados intermedios se pierden. El admin puede estar en medio de marcar asistencia y todo desaparece.

**A4 — Aurora sin tools = regex fragil**
Aurora maneja reservas, cancelaciones, registros — todo dependiendo de que el LLM genere frases especificas ("Reserva confirmada", "cancele la reserva", "REGISTRO PADRE:") que main.py detecta con regex. Si Aurora cambia una palabra → se rompe silenciosamente.

### 3.3 Antipatrones segun guia Anthropic (Certified Architect)

| Antipatron | Que dice la guia | Que hace FENIX |
|-----------|-----------------|----------------|
| Descripciones vagas | "La descripcion es el mecanismo de seleccion" — decir que retorna, cuando usar, cuando NO | Descripciones cortas sin retorno ni exclusiones |
| Errores no categorizados | Categorizar: transient/validation/business + is_retryable | Catch generico → "Hubo un error" |
| Escalada probabilistica | Tool deterministica con handoff estructurado | Frase magica detectada por regex |
| Reglas criticas en prompts | Financieras/legales → hooks deterministicos | Todo en el prompt, nada determinista |
| Sin PostToolUse | Normalizar datos, notificar, enriquecer resultado | No existe el concepto |
| stop_reason ignorado | Chequear end_turn/tool_use/max_tokens | `or not _usa_tools` cortocircuita el check |

---

## 4. PLAN DE RECONSTRUCCION

### 4.1 Estructura nueva (~50 archivos)

```
app/
  __init__.py
  main.py                         # FastAPI app, lifespan, monta routers (~100 lineas)
  config.py                       # Settings via pydantic BaseSettings (~80 lineas)
  
  db/
    engine.py                     # SQLAlchemy engine + async_session
    models.py                     # Mismos 6 modelos + tabla escalaciones
    repository.py                 # Repos tipados: ConversacionRepo, MensajeRepo, etc.
  
  pipeline/
    router.py                     # Orquestador: guards → interceptors → brain → postprocess → deliver
    interceptors.py               # Los 10 FAQ regex actuales, organizados como lista de (detector, builder)
    guards.py                     # Spam, inyeccion, rate-limit, dedup, night-mode
    postprocessors.py             # Limpieza [SISTEMA:], anti-repeticion, deteccion afiche
  
  agents/
    brain.py                      # Agentic loop con tool_use + hooks + errores estructurados
    prompts.py                    # Carga prompts .md + inyeccion contexto fechas
    tool_registry.py              # TOOLS_IVAN (5), TOOLS_AURORA (6) — schemas completos
    tool_executor.py              # Dispatcher con errores categorizados
    hooks.py                      # PreToolUse (validacion) + PostToolUse (normalizacion)
    errors.py                     # StructuredToolError dataclass
  
  tools/ivan/
    reagendar_clase.py            # Cambiar hora/fecha de prueba
    consultar_disponibilidad.py   # Cupos por turno
    escalar_a_humano.py           # Escalada deterministica + handoff Telegram
    programar_llamada.py          # Alerta para que Ivan llame
  tools/aurora/
    agendar_clase.py              # Crear RESERVA para inscripto
    cancelar_reserva.py           # Cancelar reserva
    consultar_agendados.py        # Listar ninos por turno
    registrar_familia.py          # Crear/actualizar FAMILIA
    registrar_hijo.py             # Crear NINO vinculado a FAMILIA
    escalar_a_humano.py           # Escalada deterministica
  
  services/
    airtable.py                   # Cliente Airtable limpio
    whatsapp/provider.py + meta.py
    telegram.py                   # Bridge + notificaciones
    payments.py                   # Flujo completo de pagos
    transcriber.py
    face_recognition.py
    meta_capi.py
    data_extractor.py             # Haiku extrae datos formulario
  
  webhooks/
    whatsapp.py                   # GET/POST /webhook
    telegram.py                   # POST /telegram/webhook
  
  admin/
    commands.py                   # Dispatcher comandos admin
    attendance.py                 # Asistencia
    inscription.py                # Wizard inscripcion
    reports.py                    # Resumenes
    photos.py                     # Fotos + reconocimiento
  
  background/
    scheduler.py                  # fire_and_forget
    reminders.py                  # Loop recordatorios
    night_mode.py                 # 23:00-07:00
    followup.py                   # Follow-up leads
    attendance_auto.py            # Auto-asistencia sabados
    daily_summary.py              # Resumen diario 08:00
  
  api/
    routes.py                     # Endpoints publicos
    debug.py                      # Endpoints debug

config/prompts/
  ivan.md                         # System prompt Ivan reestructurado
  aurora.md                       # System prompt Aurora reestructurado
config/business.yaml              # Sin cambios
```

### 4.2 Tools completas (11 total, schemas segun buenas practicas)

Cada tool tiene descripcion que dice: que hace, que RETORNA, cuando usar, cuando NO usar.

**Ivan (5 tools)**: consultar_disponibilidad, reagendar_clase, escalar_a_humano, programar_llamada
**Aurora (6 tools)**: agendar_clase, cancelar_reserva, consultar_agendados, registrar_familia, registrar_hijo, escalar_a_humano

### 4.3 Agentic loop rediseñado

- SIEMPRE retorna `tuple[str, list[dict]]` (elimina dualidad str|tuple)
- Check deterministico de stop_reason (end_turn, tool_use, max_tokens)
- PreToolUse hooks BLOQUEAN antes de ejecutar (validar horario, fecha, sabado)
- PostToolUse hooks TRANSFORMAN despues (normalizar fechas, notificar Telegram, CAPI)
- Errores estructurados: {error_category, is_retryable, message, attempted_query}
- Si agotan 5 rounds → escalar automaticamente (no error generico)
- Retry exponencial para errores transitorios

### 4.4 Escalada como tool (no frase magica)

**Actual**: Claude dice "Te respondo en un minuto" → regex detecta → alerta admin
**Nuevo**: Claude llama `escalar_a_humano(motivo, resumen)` → executor genera handoff estructurado → Telegram recibe: motivo, resumen conversacion, acciones previas, recomendacion → agente se silencia → retorna mensaje para el padre

### 4.5 System prompts reestructurados

De YAML monolitico con prohibiciones dispersas a archivos .md separados con secciones claras:
IDENTIDAD → HERRAMIENTAS DISPONIBLES → CONTEXTO → PRECIOS → FLUJO → ESCALADA → RESTRICCIONES

### 4.6 Migracion incremental (5 fases con feature flags)

**Fase 0** — Crear `app/` al lado de `agent/`, mover DB, deploy sin cambios
**Fase 1** — Extraer servicios (airtable, telegram, pagos) con shims backward-compat
**Fase 2** — Extraer admin + background loops
**Fase 3** — Nuevo agentic loop + 11 tools, feature flag `USE_NEW_BRAIN`
**Fase 4** — Nuevo pipeline, feature flag `USE_NEW_PIPELINE`
**Fase 5** — Cutover despues de 48h monitoreo, borrar viejo

### 4.7 Las 19 features que DEBEN preservarse

1. WhatsApp webhook (Meta Cloud API, dedup, rate-limit)
2. Dual agent (Ivan ventas, Aurora operaciones, routing automatico)
3. FAQ interception (regex gratis, sin Claude)
4. Tool Use (Claude llama tools para acciones)
5. Payment flow (comprobante → pendiente → admin confirma)
6. Airtable CRM (6 tablas)
7. Telegram bridge bidireccional
8. Telegram notifications (reservas, pagos, llamadas)
9. Night mode (23:00-07:00)
10. Reminders (formulario, follow-up, clase)
11. Attendance (lista + marcar + auto sabados)
12. Admin commands (desde Telegram)
13. Data extraction (Haiku extrae datos del chat)
14. Meta CAPI (LeadSubmitted, Purchase)
15. Audio transcription
16. Photo/face recognition
17. Follow-up system
18. Security (injection, spam)
19. Inscription wizard

---

---

## 6. COUNCIL DE 5 ADVISORS (metodologia Karpathy)

Se sometio el plan completo a un council de 5 advisors IA independientes, con peer review anonimo y sintesis final. Cada advisor leyo el documento MIGRACION TOTAL.md completo antes de opinar.

### 6.1 Los 5 advisors

**The Contrarian** (busca fallas fatales):
> Tres bombas: (1) Shadow mode no funciona con sistemas conversacionales con estado — ambos pipelines no pueden compartir DB sin divergencia. Si el nuevo pipeline escribe algo en DB mientras el viejo lee, el historial se duplica. Si solo el viejo escribe, el nuevo nunca tiene datos reales para validar. (2) Fase 3 es demasiado grande — nuevo loop + 11 tools detras de un solo flag es un cambio masivo. Deberia poder activar cada tool individualmente. (3) Estado en memoria se pierde en cutover — conversaciones activas al momento del switch pierden `_asistencia_pendiente`, `_inscripcion_pendiente`. No es edge case, es el caso mas probable en horario pico.
>
> Alternativa: 3 pasos quirurgicos — persistir estado a PostgreSQL primero (1 semana), implementar 11 tools con hooks en brain.py actual (2 semanas), DESPUES partir monolito.
>
> **"No esta mal diseñado. Esta mal secuenciado."**

**The First Principles Thinker** (reformula el problema):
> "Estan preguntando lo equivocado." El problema no es el codigo, es que logica de negocio y ejecucion no estan separadas. Tres bugs de produccion AHORA: (1) confirmar_reserva sin executor = conversiones perdidas, (2) escalacion por regex = falsos positivos silenciosos, (3) Aurora sin tools = dependiente de parsing fragil.
>
> Esos tres solos justifican actuar. Pero rebuilding completo de 50 archivos con 5 fases en produccion viva es donde la logica dice NO.
>
> Fix quirurgico primero (2-3 dias): executor para confirmar_reserva, escalacion como tool, errores estructurados. Eso resuelve el 80% del dolor. Luego fases 0-2 de extraccion. Decidis rebuild vs continuar con datos reales de comportamiento post-fix, no teoria.
>
> **"50 archivos para 14k lineas es apropiado. Pero llegas ahi con tres semanas de incrementos verificables, no un plan de 5 fases bajo presion."**

**The Expansionist** (busca upside oculto):
> "Estan pensando chico." Esto es realmente un framework para academias. Fenix Kids no es un cliente — es el primer caso de uso. Salsa Soul Studio es el segundo. ¿Cuantas academias de danza, fitness kids, artes marciales, natacion existen en Asuncion? Todas tienen el mismo problema: WhatsApp caotico, reservas por Excel, seguimiento manual.
>
> La arquitectura domain-separated (pipeline/, agents/, tools/, services/) es exactamente lo que se necesita para multi-tenant. Si se agrega tenant_id desde el principio, el salto de 1 a 100 academias es configuracion, no codigo.
>
> Los 11 tools son universales para cualquier negocio de reservas. La diferencia entre negocios vive en prompts y reglas de Airtable, no en la logica del agente.
>
> **"El AgentKit ya existe en CLAUDE.md. Esta es su implementacion de produccion."**

**The Outsider** (sin contexto previo, ojos frescos):
> Las 8,010 lineas no son el problema real. Tres bugs separados tienen tres fixes puntuales. El rebuild es un rewrite disfrazado de migracion.
>
> Cada fase crea nuevas superficies de integracion entre codigo viejo y nuevo. Shadow mode es peligroso para un developer solo — mantener dos codebases simultaneamente, comparar outputs, debuggear discrepancias. Eso es trabajo de equipo.
>
> Mayor riesgo: la migracion nunca termina. Se terminan Fases 0-2, surge un issue de cliente, se parchea el sistema viejo porque es mas rapido, y ahora viejo y nuevo divergieron. Fase 3 arranca sobre una base que ya se movio. Meses despues hay tres sistemas: el viejo, el medio-migrado, y los parches.
>
> **"Arregla 3 bugs, shippea. DESPUES pregunta si el refactor vale la pena. La propuesta resuelve los problemas correctos con la herramienta equivocada."**

**The Executor** (solo le importa la ejecucion):
> Se puede hacer? Si. Es realista? Mayormente. Fase 3 es donde los proyectos mueren — eso no es refactor, es rewrite.
>
> Lunes a la mañana: `git checkout -b migration/phase-0`, mkdir, mover modelos DB, agregar shim, deploy. 2-3 horas. Zero cambio de comportamiento.
>
> Timeline realista por fase: Fase 0 (1 sesion), Fase 1 (3-4 sesiones), Fase 2 (2-3 sesiones), Fase 3 (4-6 sesiones minimo), Fase 4 (2-3 sesiones), Fase 5 (1 sesion + 48h). Total: 13-20 sesiones = 6-10 semanas a 2 sesiones/semana.
>
> Regla clave: NUNCA mezclar moves de archivos con cambios de logica en el mismo commit. Fases 1-2 son moves puros. Fases 3-4 son logica nueva. Congelar deploys viernes antes de clases sabado.

### 6.2 Peer review (anonimo)

Los advisors evaluaron las respuestas de los demas sin saber quien dijo que:

**Respuesta mas fuerte: The Contrarian** — Identifica failure modes especificos y testeables, no opiniones. La alternativa (secuenciar: persistir → tools → split) es accionable y ataca la causa raiz. El reframe "mal secuenciado, no mal diseñado" es correcto.

**Mayor punto ciego: The Expansionist** — Contesta otra pregunta ("¿debemos hacer multi-tenant?") sin evaluar si el plan actual funciona. Inyectar tenant_id en Fase 1 agrega scope durante una operacion fragil. Nunca habla de los 3 bugs de produccion ni del riesgo de developer solo. Es el consejo que podria activamente empeorar las cosas expandiendo scope mid-migracion.

**Lo que TODOS ignoraron**: Nadie pregunto ¿cual es el costo REAL del monolito hoy? ¿Cuantas horas por semana debugging? ¿Con que frecuencia deploys rompen prod? Sin ese baseline, "fix 3 bugs" y "rebuild ahora" son ambas apuestas disfrazadas de analisis.

### 6.3 Veredicto del Chairman

#### Donde el Council coincide (alta confianza)

- **Los 3 bugs de produccion hay que resolverlos ANTES de cualquier cosa.** 4 de 5 advisors convergieron independientemente: el codigo roto tiene prioridad sobre el codigo feo.
- **Fase 3 tal como esta es demasiado grande.** Nuevo loop + 11 tools + feature flag = un rewrite disfrazado de fase. Consenso claro: ese paso es donde el proyecto muere.
- **El destino (50 archivos) es correcto. La secuencia no.** Nadie dijo "50 archivos es equivocado." Lo que dijeron es que el camino maximiza la probabilidad de que la migracion nunca termine.

#### Donde el Council choca (desacuerdo genuino)

- **Fix puntual vs fix + refactor** — depende de cuantas horas por semana consume el monolito. Si son 2h/semana, el fix puntual gana. Si son 10h, el refactor se justifica. El council no tenia ese dato.
- **Multi-tenant desde Fase 1** — El Expansionist dice que agregar tenant_id es gratis y habilita Salsa Soul. El Contrarian dice que es scope creep que mata migraciones fragiles.

#### Puntos ciegos detectados

1. **Nadie midio el costo real del monolito** — sin ese numero, ambas opciones son apuestas
2. **Shadow mode con estado compartido no funciona** — dos pipelines sobre la misma DB de conversaciones = divergencia inevitable
3. **Desarrollador unico + migracion de 6-10 semanas** = riesgo alto de abandono a mitad, no por capacidad sino por fragmentacion de atencion

#### Recomendacion original del Chairman

> "No reconstruyas todavia. Arregla los bugs, medi el costo real, y ejecuta solo Fases 0-2."

---

## 7. DECISION FINAL — INPUT DE IVAN (OWNER)

El council dejo abierta una pregunta clave: ¿cual es el costo real del monolito hoy?

**Respuesta de Ivan:**

> "Cada conversacion tiene potencial de error y tengo que estar haciendo el fix en el momento, respondiendo personalmente a los clientes para arreglar, y es una constante diaria."

Este dato cambia la ecuacion. El costo del monolito NO son 2 horas semanales de debugging — es **intervencion manual diaria en conversaciones con clientes reales**. El fix quirurgico de 3 bugs no alcanza porque el problema no son 3 bugs puntuales: es que todo el sistema es fragil y cualquier conversacion puede requerir intervencion personal.

### 7.1 Secuencia final aprobada

Con el dato de Ivan, la recomendacion se ajusta siguiendo la logica del Contrarian (el advisor mas fuerte segun el peer review): **la direccion es correcta, la secuencia se corrige**.

**PASO 1 — Fix los 3 bugs activos (2-3 dias)**
Para que deje de romperse MIENTRAS se reconstruye:
- Implementar executor de `confirmar_reserva`
- `escalar_a_humano` como tool deterministica (reemplazar frase magica)
- Errores estructurados en `tool_executor.py`

**PASO 2 — Implementar los 11 tools con hooks en brain.py ACTUAL (2 semanas)**
Esto es lo que mas impacto tiene en reducir errores diarios, sin tocar main.py:
- 5 tools Ivan + 6 tools Aurora con schemas completos
- PreToolUse hooks (validar horario, fecha, sabado)
- PostToolUse hooks (normalizar, notificar, CAPI)
- Errores estructurados con categorias
- Aurora deja de depender de regex para reservas/cancelaciones/registros

**PASO 3 — Partir el monolito (Fases 0-2 del plan original, 2-3 semanas)**
Ya con un agente que responde bien, reorganizar archivos:
- Crear estructura `app/` al lado de `agent/`
- Extraer servicios, admin, background
- Solo moves de archivos, sin cambios de logica

La diferencia clave con el plan original: no se mezcla "arreglar lo roto" con "reorganizar archivos" en el mismo movimiento. Primero el agente responde bien (tools + hooks + errores), despues el codigo queda limpio (modularizacion).

### 7.2 Lo que NO se hace (por ahora)

- Shadow mode (Phase 4 original) — el council demostro que no funciona con estado compartido
- Multi-tenant / tenant_id — scope creep, se evalua cuando el agente este estable
- Reescribir system prompts — se hace DESPUES de que los tools esten funcionando, no antes
- Follow-up system — sigue desactivado hasta que el agente base sea confiable

### 7.3 Metricas de exito

El exito se mide por UNA cosa: **cuantas veces por dia Ivan tiene que intervenir manualmente en conversaciones**.
- Hoy: varias veces por dia (linea base)
- Post Paso 1: deberia bajar ~50% (los errores mas groseros desaparecen)
- Post Paso 2: deberia bajar ~80% (Aurora con tools reales, escalada deterministica)
- Post Paso 3: no cambia la metrica (es reorganizacion interna)

---

## 8. REGISTRO DE IMPLEMENTACION

### 8.1 PASO 1 — Fix los 3 bugs activos (2026-05-24)

**Objetivo**: Arreglar los 3 bugs criticos que causan intervencion manual diaria sin tocar main.py.

#### Cambio 1: Implementar executor de `confirmar_reserva`

**Archivo modificado**: `agent/tools/reservas.py`
- Agregada funcion `_parsear_fecha(fecha_texto)` — convierte texto libre de fecha a ISO (YYYY-MM-DD). Acepta: ISO directo, "31 de mayo", "sabado 31", "31/5", "31/05/2026". Si la fecha ya paso, asume año siguiente.
- Agregada funcion `confirmar_reserva_prueba(telefono, fecha, hora)` que:
  - Valida hora contra `_HORARIOS_VALIDOS` (9:30, 11:00, 15:30)
  - Parsea fecha con `_parsear_fecha()`, valida que sea sabado
  - Busca registros PRUEBA FENIX por telefono en Airtable
  - Si no encuentra → error estructurado (business, no retryable)
  - Si encuentra → actualiza FECHA RESERVA y HORA en todos los registros
  - Notifica admin via WhatsApp con formato: RESERVA CONFIRMADA + padre + hijos + fecha + link WA
  - Retorna {confirmada, fecha, hora, hijos, enviar_admin, mensaje_admin}
- Todos los errores de validacion retornan errores estructurados con `error_category` y `is_retryable`

**BOMBA DESACTIVADA**: `confirmar_reserva` ahora tiene executor. Claude puede llamarlo sin provocar error generico.

#### Cambio 2: `escalar_a_humano` como tool deterministica

**Archivo creado**: `agent/tools/escalacion.py`
- Funcion `escalar_a_humano(telefono, motivo, resumen)` que:
  - Obtiene ultimos 10 mensajes del historial
  - Extrae nombre del padre (best effort del historial)
  - Construye handoff estructurado: motivo, padre, ultimo mensaje, resumen, link WA, link Telegram topic
  - Canal 1: envia alerta WhatsApp al admin (ADMIN_PHONE)
  - Canal 2: envia alerta Telegram via `notificar_llamada_urgente()`
  - Silencia agente via `silenciar_dorita(telefono)` (5 min)
  - Retorna {texto: "Te respondo en un minuto", escalado: true, motivo, nombre_padre}
- 5 motivos categorizados: no_se_la_respuesta, padre_pide_humano, tema_sensible, fuera_de_ambito, queja_o_problema

**ESCALADA DETERMINISTICA**: Claude ahora LLAMA el tool en vez de generar una frase magica. La escalada es una ACCION, no texto detectado por regex. El admin recibe handoff estructurado con contexto.

#### Cambio 3: Errores estructurados en tool_executor

**Archivo reescrito**: `agent/tool_executor.py`
- Registra 3 tools: reagendar_clase, confirmar_reserva, escalar_a_humano
- Las 3 estan en `_TOOLS_CON_TELEFONO` (reciben telefono automaticamente)
- Errores categorizados en 4 niveles:
  - Tool no encontrada → validation, no retryable
  - TimeoutError/ConnectionError/OSError → transient, retryable
  - ValueError/TypeError/KeyError → validation, no retryable
  - Deteccion por contenido (timeout, 429, 503 en el mensaje) → transient, retryable
  - Cualquier otro → internal, no retryable
- Cada error incluye: error_category, is_retryable, message, attempted_query
- Claude recibe `is_error: True` en el tool_result y puede decidir: reintentar, reformular, o escalar

#### Cambio 4: Descripciones mejoradas de tools

**Archivo reescrito**: `agent/tool_definitions.py`
- 3 tools en TOOLS_IVAN (antes 2):
  - `reagendar_clase` — descripcion ampliada: dice que RETORNA, cuando NO usar (no para crear reserva nueva, no sin reserva previa)
  - `confirmar_reserva` — descripcion ampliada: dice que RETORNA, cuando NO usar (no sin fecha+hora, no para cambiar reserva existente), fecha acepta multiples formatos
  - `escalar_a_humano` (NUEVA) — descripcion completa: 5 motivos enum, resumen requerido, dice cuando usar y cuando NO (no para FAQ), dice que despues de escalar NO seguir respondiendo

#### Cambio 5: brain.py — is_error en tool_results

**Archivo modificado**: `agent/brain.py` (linea 240)
- Cuando un tool retorna `error: True`, el tool_result enviado a Claude incluye `is_error: True`
- Esto sigue la best practice de Anthropic: Claude sabe que la tool fallo y puede actuar en consecuencia (reintentar si retryable, reformular si validation, escalar si business)

#### Verificacion

- `python -c "from agent.tool_definitions import TOOLS_IVAN; print(len(TOOLS_IVAN), 'tools')"` → 3 tools
- `python -c "from agent.tool_executor import _TOOLS; print(len(_TOOLS), 'executors')"` → 3 executors
- `_parsear_fecha()` probada con 5 formatos: ISO, "31 de mayo", "sabado 31", "31/5", "sabado 7 de junio" → todos correctos
- Imports verificados sin errores

#### Archivos tocados

| Archivo | Accion | Lineas |
|---------|--------|--------|
| `agent/tools/reservas.py` | Modificado | 99 → ~230 |
| `agent/tools/escalacion.py` | CREADO | ~95 |
| `agent/tool_definitions.py` | Reescrito | 56 → ~100 |
| `agent/tool_executor.py` | Reescrito | 47 → ~95 |
| `agent/brain.py` | Modificado (1 bloque) | +6 lineas |
| `agent/main.py` | **NO TOCADO** | 8,010 |
| `config/prompts.yaml` | **NO TOCADO** | 222 |
