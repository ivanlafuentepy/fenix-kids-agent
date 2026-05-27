up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# AGENTE FENIX — Documento de Proyecto Completo

> Sistema de agente WhatsApp dual (Profe Ivan + Aurora) para [[Fenix Kids Academy]].
> Construido con FastAPI + Claude Haiku + PostgreSQL + Airtable + Telegram + Google Calendar.
> En produccion desde abril 2026.

---

## 1. Que es FENIX KIDS AGENT

Un agente de WhatsApp con IA que atiende leads y familias de **FENIX KIDS ACADEMY**, una academia de entrenamiento funcional y emocional para ninos de 3 a 12 anos en Asuncion, Paraguay.

El sistema tiene **dos agentes**:
- **Profe Ivan** — agente de ventas. Recibe al lead, hace rompehielos, diagnostica, ofrece precios y horarios, cierra la venta.
- **Aurora** — asistente operativa. Recolecta datos de la familia, agenda clases, gestiona reservas y cancelaciones.

El handoff de Ivan a Aurora es automatico cuando Ivan dice "te contacta Aurora".

---

## 2. Stack tecnico

| Componente | Tecnologia |
|-----------|-----------|
| Runtime | Python 3.11+ |
| Servidor | FastAPI + Uvicorn |
| IA conversacional | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| IA extraccion datos | Claude Haiku 4.5 (formularios) |
| WhatsApp | Meta Cloud API (v21.0) |
| Base de datos | PostgreSQL (prod via Railway) / SQLite (dev) |
| ORM | SQLAlchemy async + asyncpg |
| CRM | Airtable (7 tablas) |
| Calendario | Google Calendar API |
| Espejo admin | Telegram Bot API (topics por lead) |
| Transcripcion audios | Groq Whisper Large v3 |
| Atribucion anuncios | Meta Conversions API (server-side) |
| Deploy | Railway (Docker) |

---

## 3. Arquitectura de archivos

```
fenix-kids-agent/
├── agent/
│   ├── main.py              # Servidor FastAPI + webhook + logica de flujo
│   ├── brain.py              # Claude API + system prompts + retry
│   ├── memory.py             # ORM PostgreSQL (mensajes, pagos, dedup, topics)
│   ├── tools.py              # Datos del negocio (legacy, no se usa en flujo)
│   ├── ab_test.py            # Estado persistente de cada conversacion
│   ├── airtable_client.py    # CRUD completo de Airtable (7 tablas)
│   ├── telegram_bridge.py    # Espejo bidireccional WhatsApp-Telegram
│   ├── meta_capi.py          # Eventos server-side a Meta (LeadSubmitted, Purchase)
│   ├── pagos.py              # Deteccion comprobantes + flujo confirmar/rechazar
│   ├── reminders.py          # Recordatorios automaticos (formulario, seguimiento)
│   ├── night_mode.py         # Respuesta automatica 23:00-07:00 PY
│   ├── calendar_google.py    # Google Calendar (crear/cancelar eventos)
│   ├── transcriber.py        # Groq Whisper (audio WhatsApp a texto)
│   ├── contenido_social.py   # Envio diario de contenido a familias
│   ├── validar_nombre.py     # Validacion de nombres
│   └── providers/
│       ├── base.py           # Interfaz abstracta ProveedorWhatsApp
│       ├── meta.py           # Implementacion Meta Cloud API
│       └── __init__.py       # Factory de proveedores
├── config/
│   ├── prompts.yaml          # System prompts de Ivan y Aurora
│   ├── business.yaml         # Datos del negocio (precios, horarios, banco)
│   └── google_credentials_fenix.json
├── scripts/
│   ├── fu_grupo_a.py         # Follow-up masivo grupo A
│   ├── fu_grupo_b_lujan.py   # Follow-up masivo grupo B
│   ├── migrate_prueba_to_reservas.py
│   └── test_meta.py
├── static/
│   ├── afiche_horarios.png   # Imagen de horarios
│   ├── afiche_fenix.png      # Imagen de precios
│   ├── followup_caricatura.png
│   ├── followup_foto.jpeg
│   └── followup_video.mp4
├── tests/
│   └── test_local.py         # Simulador de chat en terminal
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env                      # Variables de entorno (no versionado)
```

---

## 4. Flujo de un mensaje (webhook)

```
WhatsApp (padre escribe)
    |
Meta Cloud API (webhook POST /webhook)
    |
providers/meta.py -- parsea y normaliza a MensajeEntrante
    |
main.py -- responde 200 OK inmediato, lanza task en background
    |
    +-- Deduplicacion (mensaje_id en DB)
    +-- Rate limit (10 msgs / 60s)
    +-- Transcripcion audio (si es audio, via Groq Whisper)
    +-- Proteccion prompt injection
    +-- Espejo a Telegram (topic del lead)
    +-- Modo nocturno (23:00-07:00 responde fijo, marca pendiente)
    |
    +-- Detectores de intent:
    |     reset ("holayosoyfenix")
    |     comandos admin (resumen anuncios, resumen reservas, etc.)
    |     pago (comprobante de transferencia)
    |     pedido de llamada
    |     handoff Ivan->Aurora
    |     activacion Aurora ("Hola Aurora")
    |     confirmacion de reserva
    |
    +-- brain.py -- genera respuesta con Claude Haiku
    |     system prompt (Ivan o Aurora segun agent_actual)
    |     historial (ultimos 20 mensajes)
    |     contexto extra (sabados disponibles)
    |
    +-- memory.py -- guarda mensaje usuario + respuesta en DB
    |
    +-- providers/meta.py -- envia respuesta por WhatsApp
    |
    +-- Espejo respuesta a Telegram
```

---

## 5. Los dos agentes

### 5.1 Profe Ivan (agente de ventas)

**Prompt:** `config/prompts.yaml` → `ivan_prompt`

**Fases de la conversacion:**

| Fase | Que hace | Trigger |
|------|---------|---------|
| FASE 1 | Rompehielos: 15 opciones numeradas (timidez, pantallas, constancia...) | Primer mensaje del lead |
| FASE 2 | Autoridad + promesas: responde diagnostico, pide nombre + edad del hijo | Lead responde numeros |
| FASE 2B | Personalizacion por edad: cierre calido, ofrece info | Lead da nombre y edad |
| FASE 3 | Pago y horarios: muestra sabados, datos bancarios, espera comprobante | Lead muestra interes |
| FASE 4 | Post-pago: confirma reserva, pasa a Aurora para formulario | Lead envia comprobante |

**Reglas criticas:**
- NUNCA dice "Reserva confirmada" ANTES de recibir comprobante
- Speech exacto para datos bancarios: "Te paso los datos para la transferencia..."
- Anti-loop: no repite preguntas que ya hizo
- Maneja objeciones: efectivo, faltas, edad fuera de rango, otros dias

### 5.2 Aurora (asistente operativa)

**Prompt:** `config/prompts.yaml` → `aurora_prompt`

**Dos modos:**
1. **lead_nuevo** — recolecta formulario (nombre padre/madre, nombre/apellido/fecha nac/CI/talla hijo)
2. **cliente_inscripto** — menu de 5 opciones

**Menu Aurora:**
1. Agendar clase (muestra sabados disponibles)
2. Ver lista de ninos agendados por horario
3. Proximamente (contenido)
4. Proximamente (tienda)
5. Redes sociales

---

## 6. Modulos detallados

### 6.1 main.py — Servidor FastAPI

**Endpoints:**

| Metodo | Ruta | Funcion |
|--------|------|---------|
| GET | `/` | Health check |
| GET | `/stats` | Estadisticas de conversion (admin) |
| GET/POST | `/webhook` | Webhook de WhatsApp (Meta) |
| GET | `/debug/{telefono}` | Inspeccionar estado de lead (admin) |
| GET | `/diagnostico-audio` | Diagnostico config audios |
| GET | `/test-audio/{media_id}` | Prueba transcripcion |
| GET | `/resumen-followup` | Analisis post follow-up masivo |
| GET | `/conversacion/{telefono}` | Historial completo con timestamps |
| GET | `/telegram/setup` | Registrar webhook Telegram |
| POST | `/telegram/webhook` | Mensajes desde Telegram |

**Tasks en background (lifespan):**
- `_recordatorios_loop()` — cada 60s, chequea recordatorios pendientes
- `_noche_wakeup_loop()` — a las 07:00 PY procesa leads nocturnos
- `_keepalive_admin_loop()` — 9:00 y 22:00 PY mantiene ventana 24h

**Comandos admin por WhatsApp:**
- `holayosoyfenix` — reset completo (conversacion + Airtable)
- `modo alumno` — reset conversacion sin tocar Airtable
- `resumen anuncios` / `resumen anuncios hoy` / `resumen anuncios ayer` / `resumen anuncios [mes]`
- `resumen reservas` — sabado proximo por turno, edad + promedio
- `resumen followup` / `resumen fu` — mapa completo de FU

**Detectores (regex):**
- Registro Aurora, activacion Aurora, handoff Ivan→Aurora
- Respuesta de edad, diagnostico enviado, interes del padre
- Pedido de llamada (16 patrones), confirmacion de reserva Aurora
- Numeros del rompehielos (1-15)

**Protecciones:**
- Rate limit: 10 msgs/60s por telefono
- Deduplicacion persistente en PostgreSQL
- Lock asyncio por telefono (evita race conditions)
- Prompt injection: lista de palabras peligrosas
- Kill switch: `AGENTE_PAUSADO=true` en env

### 6.2 brain.py — Claude API

**Funciones:**
- `cargar_prompt_agente(agent_actual)` — carga system prompt + inyecta sabados disponibles del mes
- `generar_respuesta(mensaje, historial, agent_actual, contexto_extra)` — llamada a Claude Haiku
  - max_tokens: 1024, timeout: 25s
  - 3 reintentos con backoff exponencial (2, 4, 8 segundos)
  - Alerta a Telegram si fallan todos
  - Prompt caching con ephemeral control
- `extraer_datos_formulario(historial)` — extrae datos estructurados del chat:
  - `{ninos: [{nombre, apellido, ci, fecha_nacimiento, sexo, talla_remera}], padre: {...}, madre: {...}, completo: bool}`
- `resumir_conversacion_para_alerta(historial)` — resumen corto para alerta de llamada

**Modelo:** `claude-haiku-4-5-20251001` (cambio de Sonnet el 2026-05-04, ~95% ahorro)

### 6.3 memory.py — Base de datos

**Modelos SQLAlchemy:**

| Tabla | Campos principales | Uso |
|-------|-------------------|-----|
| `ConversacionAB` | telefono, variante, agent_actual, modo_nixie, airtable_record_id, familia_id, ctwa_clid, noche_pendiente | Estado de cada conversacion |
| `Mensaje` | telefono, role, content, timestamp | Historial de chat |
| `Recordatorio` | telefono, tipo, programado_para, enviado, payload | Tasks programadas |
| `PagoPendiente` | telefono, tipo, plan, monto, media_id, estado | Pagos esperando confirmacion |
| `TopicTelegram` | telefono, topic_id, nombre, group_id, agente_silenciado | Mapeo WhatsApp↔Telegram |
| `MensajeProcesado` | mensaje_id, procesado_en | Deduplicacion |

**Funciones principales:**
- `guardar_mensaje()`, `obtener_historial(limite=20)`
- `crear_recordatorio()`, `obtener_recordatorios_pendientes()`, `marcar_recordatorio_enviado()`
- `registrar_pago_pendiente_db()`, `confirmar_pago()`, `rechazar_pago()`
- `mensaje_ya_procesado()`, `registrar_mensaje_procesado()`
- `limpiar_estado_completo(telefono)` — reset total
- `guardar_ctwa_clid()`, `obtener_ctwa_clid()` — atribucion Meta

### 6.4 airtable_client.py — CRM

**7 tablas en Airtable:**

| Tabla | Campos clave |
|-------|-------------|
| LEADS FENIX | TELEFONO, NOMBRE RESPONSABLE, NOMBRE NINO, EDAD, CONVERSION, AGENT_ACTUAL, FORMULARIO, SEGUIMIENTOS, RESPONDIO FU1/FU2 |
| FAMILIAS FENIX | NOMBRE PADRE/MADRE, CI, CELL, EMAIL, FECHA NACIMIENTO |
| NINOS FENIX | NOMBRE, APELLIDO, CI, FECHA NACIMIENTO, SEXO, TALLA REMERA, FAMILIA (link) |
| HORARIOS FENIX | FECHA (date), HORA (string), CUPO (number) |
| RESERVAS FENIX | FAMILIA, NINO, FECHA, HORA, ESTADO (RESERVADA/CANCELADA/ASISTIO/FALTO) |
| PRUEBA FENIX | FAMILIA, NINO, FECHA, HORA, ESTADO, ASISTIO |
| CONTENIDO FENIX | TIPO, DESCRIPCION, URL_MEDIA, DIA_ENVIO, HORA_ENVIO, ENVIADO |

**Funciones principales:**
- `crear_lead()`, `obtener_lead_record_id()`, `actualizar_conversion_lead()`, `eliminar_lead()`
- `crear_familia()`, `crear_familia_completa(datos)`, `buscar_familia_por_telefono()`
- `crear_nino()`, `obtener_ninos_de_familia()`
- `obtener_o_crear_horario()`, `obtener_horarios_disponibles()`
- `crear_reserva()`, `crear_prueba_fenix()`, `cancelar_reservas_familia_fecha()`
- `obtener_ninos_por_horario()` — para "ver lista" de Aurora
- `eliminar_todo_de_telefono()` — reset cascada (leads + familias + ninos)

### 6.5 telegram_bridge.py — Espejo admin

Cada lead tiene un **topic** (hilo) en un grupo de Telegram con Topics activados.

**Flujo:**
- Mensaje entrante: `"👤 [texto del padre]"` → topic del lead
- Respuesta del agente: `"👨‍🏫 IVAN: [respuesta]"` o `"🌟 AURORA: [respuesta]"`
- Si admin escribe en el topic → se envia por WhatsApp al lead, agente se silencia 5 min
- Comprobantes de pago se envian como foto al topic (no solo texto)

**Alertas especiales:**
- Pago recibido: telefono + monto + tipo + link wa.me + link t.me/c/
- Reserva completa: datos del lead + link wa.me + link t.me/c/
- Pedido de llamada urgente: nombre + contexto + link wa.me

**Dos grupos:**
- `TELEGRAM_GROUP_ID` — leads (Ivan)
- `TELEGRAM_GROUP_ID_FLIAS` — familias inscriptas (Aurora)

### 6.6 pagos.py — Flujo de pagos

```
Padre envia comprobante (foto)
    |
es_posible_comprobante() -- verifica:
    1. Es [imagen] o [documento]
    2. CI bancario (1604338) aparece en historial reciente
    |
registrar_pago_pendiente() -- guarda en DB (estado=pendiente)
    |
Alerta a Telegram con botones: CONFIRMAR / RECHAZAR
    |
Admin presiona boton
    |
Si CONFIRMAR:                    Si RECHAZAR:
  confirmar_pago()                 rechazar_pago()
  "Pago confirmado!"              "No pudimos verificar..."
  Crear RESERVA en Airtable       Ofrece reintentar
  Crear evento Google Calendar
  Evento Meta CAPI
```

**Precios:**
- Prueba 1 hijo: 90.000 Gs
- Prueba 2 hijos: 120.000 Gs
- Prueba 3 hijos: 150.000 Gs
- Semanal mensual: 350.000 + matricula 200.000
- Semanal trimestral: 690.000 + matricula 140.000 = 830.000 (40% OFF)
- Quincenal mensual: 250.000 + matricula 200.000
- Quincenal trimestral: 450.000 + matricula 140.000 = 590.000 (40% OFF)

### 6.7 meta_capi.py — Atribucion de anuncios

Envia eventos server-side a Meta para optimizar anuncios Click-to-WhatsApp (CTWA).

- `enviar_evento_agenda(telefono)` → evento "LeadSubmitted" (cuando agenda + paga prueba)
- `enviar_evento_pago(telefono)` → evento "Purchase" (pago de inscripcion)

Usa `ctwa_clid` capturado del referral del anuncio para atribuir la conversion.

### 6.8 night_mode.py — Modo nocturno

- 23:00 a 07:00 PY: responde mensaje fijo una sola vez
- Marca `noche_pendiente=True` en DB
- A las 07:00: procesa todos los pendientes con Claude (respuesta real)

### 6.9 transcriber.py — Audios

- Descarga audio de Meta Graph API (`GET /{media_id}`)
- Transcribe con Groq Whisper Large v3 (modelo `whisper-large-v3`, idioma `es`)
- Timeout: 30s descarga, 60s transcripcion

### 6.10 reminders.py — Recordatorios

Programa 4 recordatorios despues de que Aurora agenda sin recibir formulario:
- T1: 15 min despues
- T2: 2h despues
- T3: 8h despues
- T4: 23h despues (antes del cierre de ventana 24h)

Todos respetan horario 08:00-21:00 PY.

### 6.11 providers/meta.py — WhatsApp

Implementa la interfaz `ProveedorWhatsApp` para Meta Cloud API v21.0:
- `parsear_webhook()` — soporta: text, image, document, audio, interactive, button
- `enviar_mensaje()` — texto simple
- `enviar_botones()` — interactive message con botones
- `enviar_imagen()` / `enviar_imagen_bytes()` — imagenes por media_id o bytes
- `enviar_video_bytes()` — videos
- `enviar_plantilla()` — templates HSM (fuera de ventana 24h)
- `subir_media()` — upload a Meta Graph API
- Filtra por phone_number_id (ignora mensajes de otros numeros)
- Captura ctwa_clid del referral

---

## 7. Flujo completo: Lead nuevo hasta familia inscripta

```
1. Padre ve anuncio CTWA en Instagram/Facebook
2. Click → abre WhatsApp → envia primer mensaje
3. Meta envia webhook POST /webhook
4. Sistema captura ctwa_clid del referral
5. Crea registro en LEADS FENIX (CONVERSION=CONSULTA, AGENT=IVAN)
6. Crea topic en Telegram para este lead

--- IVAN (ventas) ---

7. Ivan envia rompehielos (15 numeros)
8. Padre responde numeros (ej: "3, 7, 11")
9. Ivan hace diagnostico personalizado
10. Pregunta nombre y edad del hijo
11. Padre responde: "Mateo, 6 anos"
12. Ivan personaliza por edad, ofrece info
13. Padre muestra interes → Ivan envia afiche precios
14. Padre pide agendar → Ivan muestra sabados + datos bancarios
15. Padre envia comprobante de transferencia
16. Admin confirma pago en Telegram
17. Ivan: "Pago confirmado! Te contacta Aurora para los datos"

--- HANDOFF automatico ---

18. Sistema detecta "te contacta Aurora"
19. Cambia AGENT_ACTUAL=aurora, MODO_NIXIE=lead_nuevo
20. CONVERSION cambia a DATOS en Airtable

--- AURORA (operativa) ---

21. Aurora: "Hola! Soy Aurora. Cuantos hijos tenes?"
22. Recolecta: nombre padre/madre, nombre/apellido/CI/fecha nac/talla hijo(s)
23. Extrae datos con Claude Haiku (extraer_datos_formulario)
24. Crea FAMILIA + NINO(S) en Airtable
25. Aurora: "Reserva confirmada! [NOMBRE] sabado [FECHA] a las [HORA]h"
26. Crea RESERVA en Airtable + evento Google Calendar
27. Envia evento "LeadSubmitted" a Meta CAPI

--- POST-RESERVA ---

28. Dia anterior 07:00: recordatorio automatico
29. Dia de clase: padre lleva al hijo
30. Post-clase (+2h): "Como le fue a [hijo]?"
31. Padre inscripto escribe "Hola Aurora" → menu 5 opciones
```

---

## 8. Como se construyo (cronologia)

### Semana 1 — Base (abril 2026)
- Estructura AgentKit: FastAPI + webhook + Claude Sonnet + SQLite
- Provider Meta Cloud API
- Test local en terminal
- Deploy inicial en Railway

### Semana 2 — Agente Ivan
- System prompt con rompehielos (15 opciones)
- Flujo de 4 fases (rompehielos → diagnostico → precios → pago)
- Airtable: tabla LEADS
- Afiche de precios y horarios (imagenes estaticas)

### Semana 3 — Agente Aurora + Dual
- Segundo agente con prompt separado
- Handoff automatico Ivan→Aurora
- Formulario de datos familiares (extraccion con Claude)
- Airtable: tablas FAMILIAS, NINOS, HORARIOS, RESERVAS
- Google Calendar integration

### Semana 4 — Telegram + Pagos
- Espejo bidireccional WhatsApp↔Telegram con topics
- Flujo de pagos: deteccion comprobante → confirmar/rechazar
- Alertas de pago, reserva, llamada urgente
- Silenciamiento automatico cuando admin escribe

### Semana 5 — Produccion + Optimizacion
- Migracion SQLite→PostgreSQL (Railway)
- Deduplicacion persistente de mensajes
- Rate limiting
- Modo nocturno (23:00-07:00)
- Transcripcion de audios (Groq Whisper)
- Meta CAPI (atribucion de anuncios)
- Cambio Sonnet→Haiku (~95% ahorro costos)
- Prompt compactado de 783→210 lineas
- Recordatorios automaticos (formulario pendiente)

### Semana 6 — Follow-up + Escala
- Seguimiento automatico post-datos bancarios (FU1, FU2, FU3)
- Follow-up masivo (scripts para 139+ leads)
- Resumen reservas por turno con edad y promedio
- Resumen followup por WhatsApp
- Guard duplicados en reservas
- Timezone UTC-3 (Paraguay) en todo

---

## 9. Variables de entorno

```bash
# WhatsApp (Meta Cloud API)
META_ACCESS_TOKEN=eabc...
META_PHONE_NUMBER_ID=1234567890
META_VERIFY_TOKEN=agentkit-verify

# Claude API
ANTHROPIC_API_KEY=sk-ant-...          # Ivan
ANTHROPIC_API_KEY_AURORA=sk-ant-...   # Aurora (fallback a Ivan)

# Base de datos
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/fenix-kids

# Airtable
AIRTABLE_API_KEY=patXXXX...
AIRTABLE_BASE_ID=apph96UwbdbHoEdYr

# Google Calendar
GOOGLE_CREDENTIALS_FILE=config/google_credentials_fenix.json
GOOGLE_CALENDAR_ID=...@group.calendar.google.com

# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_GROUP_ID=...          # Grupo leads (Ivan)
TELEGRAM_GROUP_ID_FLIAS=...    # Grupo familias (Aurora)
TELEGRAM_IGNORE_PHONES=...     # Numeros que no se espejan

# Admin
ADMIN_PHONE=595982790407
ADMIN_API_KEY=...

# Meta CAPI
META_CAPI_PIXEL_ID=...
META_CAPI_ACCESS_TOKEN=...

# Groq (audios)
GROQ_API_KEY=gsk_...

# Servidor
PORT=8000
ENVIRONMENT=production
AGENTE_PAUSADO=false
```

---

## 10. Comandos utiles

```bash
# Dev local
python tests/test_local.py                    # Chat simulado
uvicorn agent.main:app --reload --port 8000   # Servidor local

# Produccion
docker compose up --build                     # Docker local
docker compose logs -f agent                  # Ver logs

# Admin endpoints (Railway)
curl https://[URL]/stats?key=[ADMIN_KEY]
curl https://[URL]/debug/595XXXXXXXXX?key=[ADMIN_KEY]
curl https://[URL]/conversacion/595XXXXXXXXX?key=[ADMIN_KEY]
```

---

## 11. Numeros clave

- **608+ leads** procesados (no-PAGO)
- **20 mensajes** de historial por conversacion
- **1024 tokens** max por respuesta Claude
- **25s** timeout por llamada a Claude
- **3 reintentos** con backoff exponencial
- **10 msgs/60s** rate limit por telefono
- **5 min** silenciamiento auto cuando admin escribe en Telegram
- **24h** ventana de WhatsApp (Meta policy)
- **7 tablas** en Airtable
- **15 opciones** de rompehielos
- **16 patrones** regex para detectar pedido de llamada
