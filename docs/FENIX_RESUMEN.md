up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# FENIX KIDS ACADEMY — Documentación Completa del Sistema

> Documento de referencia para entender el sistema sin necesidad de leer el código.
> Mantener actualizado: agregar una fila en la sección 10 cada vez que se haga un cambio importante.

---

## 1. ¿Qué es este sistema?

Agente virtual de WhatsApp para **FENIX KIDS ACADEMY**, centro de entrenamiento funcional y emocional para niños de 3 a 12 años en Asunción, Paraguay (PARQUE FENIX, LA CASONA LAFUENTE, Maestras Paraguayas 2056).

Opera con **dos agentes IA** en el mismo número de WhatsApp:

- **Profe Ivan Lafuente** — atención, ventas y cierre de pagos
- **Aurora** — operaciones, reservas y atención a familias inscriptas

**Objetivo:** que el padre confirme una clase de prueba (lead nuevo) o reserve una clase regular (padre inscripto), todo dentro del chat de WhatsApp.

---

## 2. Stack Tecnológico

### Lenguaje y framework
| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Servidor web | FastAPI + Uvicorn |
| Base de datos | PostgreSQL (Railway, producción) / SQLite (desarrollo) |
| ORM | SQLAlchemy async (asyncpg) |
| IA principal | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) — conversación Ivan/Aurora |
| IA auxiliar | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) — extracción de formularios |

### Servicios externos conectados
| Servicio | Uso |
|---|---|
| **Meta WhatsApp Cloud API** | Envío y recepción de mensajes de WhatsApp |
| **Anthropic API** | Generación de respuestas (Ivan/Aurora) y extracción de datos (Haiku) |
| **Airtable** | CRM en base [[SALSA SOUL]]: LEADS FENIX, PRUEBA FENIX, FAMILIAS FENIX, NIÑOS FENIX, HORARIOS FENIX, RESERVAS FENIX, DIAGNOSTICO FENIX, ANUNCIOS FENIX |
| ~~Google Calendar API~~ | **Eliminado** — ya no se usa |
| **Telegram Bot API** | Espejo de conversaciones en grupo de Telegram por topics |
| **Groq Whisper** | Transcripción de mensajes de audio de WhatsApp |

### Deployment
- **Plataforma:** Railway
- **Trigger de deploy:** automático en cada `git push` a `main` en GitHub
- **Repo:** github.com/ivanlafuentepy/fenix-kids-agent
- **Puerto:** 8000 (variable `PORT`)

### Monitor y Guardian (implementado 26/05/2026)

Sistema de vigilancia automática de producción con 3 capas de defensa:

| Capa | Qué es | Frecuencia |
|---|---|---|
| **1 — Monitor Interno** | `agent/monitor.py` — loops asyncio dentro del proceso Railway | Cada 1h |
| **2 — Guardian Remoto** | Claude Code trigger (`trig_01TkNS1SPNn6T7G9hhLyvkEK`) — audita código del repo | Cada 1h |
| **3 — Humano** | Ivan recibe alerta en Telegram → claude.ai/code → fix | On demand |

**Capa 1 — Monitor Interno** (`agent/monitor.py`):
- Loop conversaciones: detecta leads sin respuesta >10 min, errores webhook
- Loop salud: DB conectividad, 10 detectores OK, prompts.yaml válido, background tasks vivos
- Alertas al grupo Telegram dedicado (topic "Monitor FENIX")
- "Todo OK" solo a las 09, 15, 21h PY — problemas se alertan siempre

**Capa 2 — Guardian Remoto**:
- Sonnet 4.6, cada hora, clona el repo y ejecuta 6 checks
- Checks: detectores, prompts.yaml, migraciones DB, imports, endpoint prod, monitor.py
- Si encuentra bug obvio → push directo a main con `fix(guardian):` prefix
- Si no está seguro → solo reporta
- NO toca: prompts.yaml, .env, flujo de pagos, handlers de reset
- Admin: https://claude.ai/code/scheduled

**Telegram Monitor:** grupo dedicado `-5137950629` (`TELEGRAM_MONITOR_GROUP_ID`)

### Archivos principales
```
agent/
  main.py           — Servidor FastAPI, webhook WhatsApp, orquestación principal
  brain.py          — Llama a Claude API, carga ivan_prompt o aurora_prompt según estado
  memory.py         — Historial de conversaciones + estado + pagos persistentes + dedup
  monitor.py        — Monitor de producción: conversaciones sin respuesta + salud del sistema
  ab_test.py        — Estado por conversación: agente, modo, familia_id, Calendar
  pagos.py          — Flujo de pagos: comprobante, confirmación admin, precios (PostgreSQL persistente)
  airtable_client.py — Integración con Airtable base Salsa Soul (LEADS/PRUEBA/FAMILIAS/NIÑOS FENIX, etc.)
  telegram_bridge.py — Integración con Telegram
  reminders.py      — Recordatorios automáticos de seguimiento y formulario
  transcriber.py    — Transcripción de audios con Groq Whisper
  hooks.py          — PreToolUse/PostToolUse hooks (validación + notificaciones)
  tool_definitions.py — Schemas TOOLS_IVAN (4) + TOOLS_AURORA (2)
  tool_executor.py  — Dispatcher 6 tools + errores estructurados + resolver familia_id
  qr.py            — Generación QR check-in con logo FENIX + endpoint /checkin/{record_id}
  providers/        — Adaptador Meta WhatsApp Cloud API (botones interactivos, envío imagen)
  tools/
    reservas.py     — gestionar_prueba (confirmar/reagendar pruebas — Ivan)
    escalacion.py   — escalar_a_humano (compartido Ivan/Aurora)
    disponibilidad.py — consultar_disponibilidad + consultar_agendados
    llamada.py      — programar_llamada
    agenda.py       — gestionar_reserva (agendar/reagendar/cancelar — Aurora)
    detectores.py   — 10 detectores regex FAQ (interceptores pre-Claude)
    info.py         — Respuestas FAQ estáticas
config/
  prompts.yaml      — System prompts de Ivan (5379 chars) y Aurora (3100 chars)
  business.yaml     — Datos del negocio
```

---

## 3. Los Dos Agentes

### Profe Ivan Lafuente
- **Rol:** atención inicial, ventas y cierre de pagos para leads nuevos
- **Activación:** por defecto en todo mensaje de teléfono NO inscripto en FAMILIAS FENIX
- **Frame:** PARQUE FENIX — experiencia al aire libre, naturaleza, superar miedos. NO hay menú de dolor ni evaluación.
- **Flujo:** nombre+edad → personalización por edad → propone prueba → precio → datos bancarios → comprobante → admin confirma → agenda automática post-pago → formulario → QR check-in
- **Cobrar PRIMERO, agendar DESPUÉS:** Ivan NUNCA ofrece horarios antes del pago. El agendamiento es automático post-confirmación del comprobante.
- **Tools (4):** gestionar_prueba (confirmar/reagendar), escalar_a_humano, consultar_disponibilidad, programar_llamada

### Aurora
- **Rol:** operaciones, consultas y reservas para familias inscriptas
- **Activación:** solo cuando el teléfono del padre ya está en FAMILIAS FENIX (router automático, busca en CELL PADRE/MADRE y CELL LIMPIO)
- **Sin restricción nocturna:** padres inscriptos pueden escribir a cualquier hora
- **Onboarding (primera vez):** saluda por nombre/apodo, pregunta por hijos, verifica datos paso a paso. Campo CONTROL DATOS (checkbox) en FAMILIAS FENIX marca como verificado.
- **Atención normal (post-onboarding):** saluda y atiende directo. Menú 4 opciones: 1️⃣ Agendar/cancelar clase, 2️⃣ Fotos (próximamente), 3️⃣ Videos (próximamente), 4️⃣ Redes Sociales.
- **Reservas:** Airtable como fuente única de verdad, datos inyectados en el mensaje del usuario (no system prompt). Multi-hijo: asume todos los hijos van.
- **Tools (2):** gestionar_reserva (agendar/reagendar/cancelar), escalar_a_humano
- **Campos APODO:** APODO PADRE/MADRE en FAMILIAS, APODO en NIÑOS. Si existe, se usa para saludar y confirmar reservas.

---

## 4. Flujo Completo de Conversación

### Lead nuevo (primer mensaje)
1. Llega mensaje → se crea registro en LEADS (TELEFONO + CONVERSION=CONSULTA + AGENT_ACTUAL=IVAN)
2. Sistema envía mensaje de apertura (hardcodeado, FASE 1)
3. Ivan pide nombre padre + nombre hijo + edad (FASE 1.5)
4. Ivan personaliza por edad → propone prueba en PARQUE FENIX → "¿te gustaría regalarte un sábado?" (FASE 2)
5. Padre dice sí → Ivan da precio según hijos (FASE 2B): 100k/1, 150k/2, 200k/3
6. Ivan envía datos bancarios y pide foto del comprobante (FASE 3) — **NO ofrece horarios antes del pago**
7. Padre envía comprobante → admin confirma/rechaza con botones ✅❌
8. Pago confirmado → CONVERSION=PAGO → sistema envía mensaje fijo con sábados disponibles (determinístico, sin Claude)
9. `modo_agenda=True` → `tool_choice` forzada → **gestionar_prueba** confirma reserva automáticamente
10. Ivan pide formulario: nombre/apellido padre + hijo + fecha nacimiento (FASE 4)
11. Formulario completo → crea registro en **PRUEBA FENIX** (Haiku extrae datos)
12. **QR check-in** enviado al padre (post-formulario, no post-agenda)
13. Se notifica en Telegram (grupo FENIX KIDS)

### Padre ya inscripto escribe directo
1. Router detecta teléfono en FAMILIAS FENIX → **Aurora** activa
2. Aurora saluda por nombre/apodo + muestra menú 4 opciones
3. Si elige "Agendar/cancelar": Aurora muestra reservas activas de Airtable
4. Padre elige acción → **gestionar_reserva** (agendar/reagendar/cancelar) crea/modifica RESERVA en Airtable
5. Multi-hijo: asume todos los hijos. Confirmación con apodos.
6. Se notifica en Telegram

### Lead no responde
- +15 min, +2 h, +6 h: mensajes de seguimiento automático de Ivan
- +15 min, +2 h, +8 h, +23 h: recordatorios de completar formulario (después de agendar)
- Todos los timers se cancelan al primer mensaje del lead

---

## 5. Detección Clave en el Código

| Función | Archivo | Qué detecta / hace |
|---|---|---|
| `buscar_familia_por_telefono(tel)` | airtable_client.py | Router: ¿inscripto o lead? Busca en CELL PADRE/MADRE + CELL LIMPIO |
| `gestionar_prueba(tel, accion, fecha, hora)` | tools/reservas.py | Tool Ivan: confirmar o reagendar prueba en PRUEBA FENIX |
| `gestionar_reserva(tel, accion, fecha, hora)` | tools/agenda.py | Tool Aurora: agendar/reagendar/cancelar en RESERVAS FENIX |
| `extraer_datos_formulario(historial)` | brain.py | Haiku extrae datos de hijo/padre/madre del historial |
| `crear_familia_completa(telefono, datos)` | airtable_client.py | Crea FAMILIA + NIÑOS en Airtable y vincula al LEAD |
| `detectores.py` (10 funciones) | tools/detectores.py | Interceptan FAQ pre-Claude: precios, horarios, ubicación, hermanos, etc. |
| `hooks.py` (Pre/PostToolUse) | hooks.py | PreToolUse: validar fecha/hora/sábado, anti-spam escalación. PostToolUse: Telegram + CAPI |

---

## 6. Estructura de Airtable

**Base:** Salsa Soul Studio (`appWwCQxALdMMV4MA`) — compartida con Dorita, tablas separadas con sufijo FENIX.

### Tabla LEADS FENIX (leads en proceso)
| Campo | Tipo | Qué guarda |
|---|---|---|
| TELEFONO | Texto | Número WhatsApp del padre/madre |
| ROMPEHIELOS | Texto | Variante asignada |
| CONVERSION | Select | CONSULTA → AGENDA → PAGO → INSCRIPTO |
| AGENT_ACTUAL | Select | IVAN o AURORA |
| MODO_AURORA | Select | lead_nuevo o cliente_inscripto |
| FORMULARIO | Checkbox | True cuando todos los datos están completos |
| NOMBRE RESPONSABLE | Texto | Nombre del padre/madre que escribe |
| NOMBRE NIÑO | Texto | Nombre del hijo |
| EDAD | Texto | Edad del hijo |
| FECHA RESERVA | Texto | Fecha de la clase reservada |
| HORA RESERVA | Texto | Hora de la clase reservada |
| FECHA CREACION | DateTime | Cuándo se creó el lead |
| FECHA NACIMIENTO | Texto | Fecha nacimiento del hijo |
| DIAGNOSTICO | Link records | Condiciones elegidas del rompehielos (→ DIAGNOSTICO FENIX) |
| FAMILIA | Link record | Vínculo a FAMILIAS FENIX |
| ANUNCIO | Link record | Anuncio Meta que trajo al lead (→ ANUNCIOS FENIX, se vincula automáticamente via referral.source_id) |

### Tabla PRUEBA FENIX (leads que agendan/pagan — 1 registro por hijo)
| Campo | Tipo | Qué guarda |
|---|---|---|
| TELEFONO | Texto | Número WhatsApp |
| NOMBRE RESPONSABLE / APELLIDO RESPONSABLE | Texto | Padre/madre |
| NOMBRE HIJO / APELLIDO HIJO | Texto | Datos del niño |
| EDAD HIJO | Texto | Edad |
| FECHA NACIMIENTO | Texto | Fecha nac. del niño |
| FECHA RESERVA / HORA | Texto | Cuándo viene |
| CONVERSION | Select | AGENDA / PAGO / INSCRIPTO |
| ESTADO | Select | PRUEBA 90MIL / GRATIS / PLAN 250/MES / etc. / MATRICULA |
| MONTO | Número | Monto pagado (solo en primer hijo, resto 0) |
| INSCRIPCION | Checkbox | Check = crear en FAMILIAS |
| PRUEBA ID | Formula | "FENIX-" & RECORD_ID() |
| DIAGNOSTICO | Link records | Condiciones del rompehielos |
| LEAD | Link record | Vínculo a LEADS FENIX |
| FAMILIA | Link record | Vínculo a FAMILIAS FENIX |
| PAGOS | Link record | Vínculo a tabla PAGOS |
| FECHA CREACION | DateTime | Cuándo se creó |

### Tabla ANUNCIOS FENIX (tracking de anuncios Meta)
| Campo | Tipo | Qué guarda |
|---|---|---|
| NOMBRE | Texto | Nombre descriptivo del anuncio |
| META AD ID | Texto | ID del anuncio en Meta Ads |
| TIPO | Select | REEL CAPCUT / REEL IVAN / CARRUSEL |
| ESTADO | Select | ACTIVO / PAUSADO / TERMINADO |
| FECHA INICIO | Date | Cuándo arrancó el anuncio |
| MONTO DIARIO | Número | Presupuesto diario en PYG |
| GASTO TOTAL | Número | Gasto acumulado en PYG |
| CONVERSACIONES | Count | Cantidad de leads linkeados (automático) |
| CIERRES | Rollup | Leads con CONVERSION = PAGO o INSCRIPTO (automático) |
| NOTAS | Texto largo | Observaciones |
| LEADS FENIX | Link records | Link inverso automático desde LEADS FENIX.ANUNCIO |

### Tabla DIAGNOSTICO FENIX (15 condiciones del rompehielos)
| Campo | Tipo | Qué guarda |
|---|---|---|
| CONDICION | Texto | Descripción (ej: "Timidez / le cuesta animarse") |
| NUMERO | Número | 1-15 |
| CATEGORIA | Select | EMOCIONAL / FISICO / SOCIAL / CONDUCTUAL / CLINICO |

### Tabla FAMILIAS FENIX (ancla de cada familia — se crea al pagar la prueba en estado A PRUEBA; pasa a ACTIVO al inscribirse)
| Campo | Tipo | Qué guarda |
|---|---|---|
| FAMILIA | Formula | "FAMILIA [primer apellido padre] [primer apellido madre]" |
| NOMBRE PADRE / APELLIDO PADRE | Texto | Datos del padre |
| CI PADRE / EMAIL PADRE / CELL PADRE | Texto | Contacto del padre |
| FECHA NACIMIENTO PADRE | Fecha | Para calcular P/EDAD |
| APODO PADRE | Texto | Apodo del padre (Aurora usa para saludar si existe) |
| NOMBRE MADRE / APELLIDO MADRE | Texto | Datos de la madre |
| CI MADRE / EMAIL MADRE / CELL MADRE | Texto | Contacto de la madre |
| FECHA NACIMIENTO MADRE | Fecha | Para calcular M/EDAD |
| APODO MADRE | Texto | Apodo de la madre (Aurora usa para saludar si existe) |
| CONTROL DATOS | Checkbox | True = datos verificados por Aurora, no repetir onboarding |
| NIÑOS | Link records | Hijos vinculados a esta familia |

### Tabla NIÑOS (hijos inscriptos)
| Campo | Tipo | Qué guarda |
|---|---|---|
| NOMBRE COMPLETO | Formula | NOMBRE + APELLIDO |
| NOMBRE / APELLIDO | Texto | Datos del niño |
| CI | Texto | Cédula de identidad |
| FECHA NACIMIENTO | Fecha | Para calcular EDAD |
| EDAD | Formula | Calculada automáticamente |
| SEXO | Select | HOMBRE o MUJER |
| TALLA REMERA | Select | 2, 4, 6, 8, 10, 12, 14, 16, XS, S, M, L, XL |
| APODO | Texto | Apodo o nombre corto (ej: Mati, Ichi). Aurora usa para saludar |
| FAMILIA | Link record | Familia a la que pertenece |
| RESERVAS | Link records | Clases reservadas |
| LINK RESERVA | Formula | URL del formulario de reserva prefillado |

### Tabla HORARIOS (clases disponibles)
| Campo | Tipo | Qué guarda |
|---|---|---|
| HORARIO | Formula | "Sábado 12/4 9:30" |
| FECHA | Fecha | Fecha exacta de la clase |
| HORA | Select | 9:30, 11:00, 15:30 |
| DÍA | Formula | Nombre del día en español |
| RESERVAS | Link records | Reservas hechas para este horario |
| NIÑOS INSCRITOS | Count | Cuántos niños tiene ese horario |

### Tabla RESERVAS
| Campo | Tipo | Qué guarda |
|---|---|---|
| RESERVA | Formula | "NIÑO - HORARIO" |
| NIÑO | Link record | El niño que reservó |
| HORARIO | Link record | El horario reservado |
| FECHA / HORA | Lookup | Tomados de HORARIOS |
| PRESENTE | Checkbox | Asistencia el día de la clase |
| OBSERVACIONES | Texto | Notas del entrenador |

### Tabla CONTENIDO FENIX (posteos de redes sociales vinculados a niños)
| Campo | Tipo | Qué guarda |
|---|---|---|
| TITULO | Texto | Descripción del posteo |
| RED | Select | Instagram / Facebook / TikTok / YouTube / Threads |
| TIPO | Select | Reel / Posteo / Historia / Carrusel |
| LINK | URL | Link directo al posteo publicado |
| NIÑOS FENIX | Link records | Niños que aparecen en el posteo |
| NOTIFICADO | Checkbox | True = ya se enviaron los WhatsApps |
| FECHA | DateTime | Cuándo se creó el registro |

### Tabla SEGUIMIENTO FENIX (mensajes personalizados post-clase)
| Campo | Tipo | Qué guarda |
|---|---|---|
| FECHA | Date | Fecha de la clase |
| NINO | Link record | → NIÑOS FENIX (si es inscripto) |
| PRUEBA | Link record | → PRUEBA FENIX (si es prueba) |
| FAMILIA | Link record | → FAMILIAS FENIX |
| MENSAJE | Long text | Texto personalizado enviado |
| TELEFONO | Text | Número del padre |
| TURNO | Select | 9:30 / 11:00 / 15:30 |
| ENVIADO | Checkbox | True = mensaje enviado |
| RESPONDIO | Checkbox | True = padre respondió |
| DESCARTADO | Checkbox | True = decidió no enviar |

### Tabla REDES FENIX (perfiles de redes sociales)
| Campo | Tipo | Qué guarda |
|---|---|---|
| RED | Texto | Nombre de la red (Instagram, Facebook, etc.) |
| PERFIL | URL | Link al perfil de FENIX Kids |
| ICONO | Texto | Emoji identificador |

### Tabla ASISTENCIA FENIX (`tblFZmAcw6X54kdGW`) — check-in por QR (desde sesión 6, 2026-05-28)
Fuente única de asistencia. Una fila = un niño presente en un sábado. Separa "intención" (reserva) de "hecho" (vino). Reemplazará al campo PRESENTE de RESERVAS/PRUEBA (migración en Fase 3, todavía no apagado).
| Campo | Tipo | Qué guarda |
|---|---|---|
| REGISTRO | Texto | Identificador legible: "Nombre niño — DD/MM" |
| NIÑO | Link → NIÑOS FENIX | Si es inscripto |
| PRUEBA | Link → PRUEBA FENIX | Si es lead en clase de prueba |
| FAMILIA | Link → FAMILIAS FENIX | Familia inscripta |
| FECHA | Date | El sábado de la clase |
| HORA_CHECKIN | DateTime | Momento exacto del escaneo (TZ Asunción) |
| TURNO | Select | 9:30 / 11:00 / 15:30 |
| MÉTODO | Select | QR / MANUAL |
| RESERVA | Link → RESERVAS FENIX | Trazabilidad (opcional) |
| TELEFONO | Texto | Del padre/madre |

**Páginas de check-in:** `/checkin/familia/{familia_id}` (inscriptos, lista NIÑOS de la familia) y `/checkin/prueba/{telefono}` (leads, agrupa hermanos en PRUEBA FENIX). Cada hijo con botón presente/ausente (toggle: marcar crea fila, desmarcar la borra). QR fijo por grupo. Endpoints admin: `/enviar-qr-familia/{tel}` y `/enviar-qr-prueba/{tel}`. El `/checkin/{record_id}` viejo (1 niño) sigue vivo.

---

## 7. Estados del Lead

### En Airtable (campo CONVERSION en tabla LEADS)
| Estado | Significado | Cuándo |
|---|---|---|
| `CONSULTA` | Lead nuevo | Al primer mensaje |
| `AGENDA` | Confirmó una reserva | Cuando Ivan/Aurora confirma horario |
| `PAGO` | Pago de prueba confirmado | Al confirmar comprobante |
| `INSCRIPTO` | Inscripción confirmada | Al pagar plan mensual/trimestral |

### En PostgreSQL local (tabla ConversacionAB)
| Campo | Significado |
|---|---|
| `agent_actual` | "ivan" o "aurora" |
| `modo_nixie` | "lead_nuevo" o "cliente_inscripto" |
| `variante` | Rompehielos asignado: A (único por ahora) |
| `convertido` | True si inició recolección de datos |
| `evento_creado` | True si se envió evento Meta CAPI LeadSubmitted |
| `airtable_record_id` | ID del registro en LEADS |
| `familia_id` | ID del registro en FAMILIAS |
| `calendar_event_id` | (legacy, ya no se usa — Google Calendar eliminado) |
| `estado_json` | Flags dinámicos: modo_agenda, prueba_creada, registro_ya_iniciado, afiche_enviado, etc. |
| `ctwa_clid` | Meta Click-to-WhatsApp Click ID (atribución) |
| `ad_source_id` | ID del anuncio Meta que trajo al lead |

---

## 8. Precios y Planes

### Plan Invierno (vigente desde mayo 2026)

**Clase de prueba (1 sábado):**
| Hijos | Precio |
|---|---|
| 1 hijo | 100.000 Gs |
| 2 hermanos | 150.000 Gs |
| 3 hermanos | 200.000 Gs |

Lógica: +50.000 por cada hijo extra. Solo transferencia bancaria. NO se descuenta de paquetes. NO hay devolución.

**Plan mensual (4 sábados):**
| Hijos | Precio |
|---|---|
| 1 hijo | 300.000 Gs |
| 2 hermanos | 350.000 Gs |
| 3 hermanos | 400.000 Gs |

Adultos entran GRATIS.

Datos bancarios: **ALIAS 1604338** | Banco Itaú | Ivan Lafuente

**Horarios invierno:** Sábados 11:00h | 15:30h — 80 min aprox. (9:30 eliminado en invierno)

---

## 9. Sistema de Recordatorios

### Seguimiento de Ivan (lead no responde al rompehielos)
| # | Delay | Mensaje |
|---|---|---|
| 1 | +15 min | "¿Te quedó alguna duda sobre FENIX Kids?" |
| 2 | +2 h | Horarios de sábado disponibles |
| 3 | +6 h | Beneficios de la clase de prueba |

### Recordatorios de formulario (sistema esperando datos)
| # | Delay | Mensaje |
|---|---|---|
| 1 | +15 min | Recuerda completar el formulario |
| 2 | +2 h | Recuerda con el horario agendado |
| 3 | +8 h | Recuerda que la clase es próxima |
| 4 | +23 h | Último aviso antes del cierre 24hs |

**Restricciones horarias:** todos los envíos respetan 08:00–21:00 Paraguay (UTC-4).
**Cancelación:** al primer mensaje del lead (seguimiento) o al crear el evento Calendar (formulario).

---

## 10. Variables de Entorno Necesarias

| Variable | Estado | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Configurada | API de Claude |
| `AIRTABLE_API_KEY` | ✅ Configurada | Token de Airtable |
| `AIRTABLE_BASE_ID` | ✅ Configurada | `appWwCQxALdMMV4MA` (base Salsa Soul) |
| `META_ACCESS_TOKEN` | ✅ Configurada | Token permanente (System User Admin bajo Salsa Soul) |
| `META_PHONE_NUMBER_ID` | ✅ Configurada | `1005063086033214` (número nuevo bajo app Salsa Soul) |
| `META_VERIFY_TOKEN` | ✅ Configurada | `fenix-kids-2026` — sin default hardcodeado, guard fail-closed (commit c1f2c14) |
| `META_APP_SECRET` | ✅ Configurada | App Secret de Meta — valida la firma HMAC `X-Hub-Signature-256` del webhook (commit b1555ad) |
| `META_FIRMA_RECHAZAR` | ✅ Configurada `1` | Rechaza con 403 los webhooks con firma inválida (activado tras verificar en logs) |
| `TELEGRAM_BOT_TOKEN` | ✅ Configurada | Bot de Telegram de Fenix |
| `TELEGRAM_GROUP_ID` | ✅ Configurada | `-1003965489354` |
| ~~`GOOGLE_CALENDAR_ID`~~ | ❌ Eliminada | Ya no se usa Google Calendar |
| ~~`GOOGLE_CREDENTIALS_JSON`~~ | ❌ Eliminada | Ya no se usa Google Calendar |
| `GROQ_API_KEY` | ✅ Configurada | Para transcripción de audios |
| `AWS_ACCESS_KEY_ID` | ✅ Configurada | Rekognition (reconocimiento facial) |
| `AWS_SECRET_ACCESS_KEY` | ✅ Configurada | Rekognition |
| `AWS_REGION` | ✅ Configurada | `us-east-1` |
| `ADMIN_API_KEY` | ✅ Configurada | Header `X-ADMIN-KEY` para endpoints /stats, /debug, /telegram/setup |
| `ADMIN_PHONE` | ✅ Configurada en Railway | `595982790407` — sin default hardcodeado, fail-closed `""` (commit fb3fe4e) |
| `TELEGRAM_AGENDA_GROUP_ID` | ✅ Configurada | Grupo Telegram para notificaciones de agenda y alertas de llamada urgente |
| `TELEGRAM_IGNORE_PHONES` | ⏳ Agregar en Railway | Números que no se espejan a Telegram (ej: `595982790407`) |
| `TELEGRAM_MONITOR_GROUP_ID` | ✅ Configurada | `-5137950629` — grupo dedicado para Monitor + Guardian |

---

## 11. Pendientes para el Deploy

| # | Tarea | Estado |
|---|---|---|
| 1 | Crear app de Meta WhatsApp para Fenix Kids | ✅ Hecho |
| 2 | Crear bot de Telegram + grupo para Fenix | ✅ Hecho |
| 3 | Crear Service Account de Google Calendar | ✅ Hecho |
| 4 | Crear repo en GitHub (`ivanlafuentepy/fenix-kids-agent`) | ✅ Hecho |
| 5 | Crear proyecto en Railway + conectar repo | ✅ Hecho |
| 6 | Cargar todas las variables en Railway | ✅ Hecho |
| 7 | Registrar webhook de WhatsApp en Meta apuntando a Railway | ✅ Hecho |
| 8 | Registrar webhook de Telegram | ✅ Hecho |
| 9 | Probar con test local (`python tests/test_local.py`) | ✅ Hecho |
| 10 | Pegar `GOOGLE_CREDENTIALS_JSON` en Railway (versión one-line del archivo) | ✅ Hecho |
| 11 | Ajustar flujo conversacional de Ivan (FASE 2 conversacional, delay, cierre emocional) | ✅ Hecho |
| 12 | Nuevo flujo Nixie clase de prueba (sábados → datos mínimos) | ✅ Hecho |
| 13 | Fix transcripción de audios (tupla bytes/mime) | ✅ Hecho |
| 14 | Nixie se presenta automáticamente tras handoff de Ivan | ✅ Hecho |
| 15 | Agregar `TELEGRAM_IGNORE_PHONES` en Railway | ⏳ Pendiente |
| 16 | Flujo Nixie para inscripción directa | ❌ Obsoleto (router nuevo: Ivan maneja TODO el flujo de leads de anuncios; Nixie solo reagendamientos de inscriptos) |
| 17 | Cargar teléfonos de padres inscriptos en `CELL PADRE` / `CELL MADRE` de Airtable FAMILIAS (formato `595...` sin `+` ni espacios) | ⏳ Operacional |
| 18 | Verificar opciones del campo `HORA` en Airtable HORARIOS (`9:30`, `11:00`, `15:30` exactos — si hay `09:30` falla con 422) | ⏳ Operacional |
| 19 | Flujo de pagos: comprobante + botones admin confirmar/rechazar + pago obligatorio antes de agendar | ✅ Hecho |
| 20 | Validar en producción: P0 (RESERVA se alimenta, nombre real en Calendar), P1 (webhook <200ms), router Ivan/Nixie, alerta llamada urgente | ⏳ Operacional |
| 21 | Afiche de precios: envío automático cuando padre se presenta + follow-up con opción trimestral y prueba | ✅ Hecho |
| 22 | Precios actualizados al afiche: quincenal trim 450+140=590, semanal trim 690+140=830, matrícula trim 140k | ✅ Hecho |
| 23 | Validar flujo de pagos en producción: comprobante → botones admin → confirmación → agenda post-pago | ✅ Hecho (validado, monto multi-hijo funciona) |
| 24 | Migración Airtable a base Salsa Soul — tablas FENIX separadas | ✅ Hecho |
| 25 | Nixie → Aurora — renombre completo del agente asistente | ✅ Hecho |
| 26 | Hardening producción: lock por teléfono, dedup PostgreSQL, rate limit, pagos persistentes, Calendar null check | ✅ Hecho |
| 27 | Endpoint /conversacion/{telefono} para análisis de flujo | ✅ Hecho |
| 28 | Tabla DIAGNOSTICO FENIX (15 condiciones categorizadas) + tracking automático | ✅ Hecho |
| 29 | PRUEBA FENIX: registra leads que agendan con todos los datos (Haiku extrae del historial) | ✅ Hecho |
| 30 | Número nuevo de WhatsApp bajo app Salsa Soul (verificada) — phone_number_id 1005063086033214 | ✅ Hecho |
| 31 | Automatización Airtable: check INSCRIPCION en PRUEBA FENIX → crear FAMILIA + NIÑOS | ⏳ Pendiente (Ivan) |
| 32 | Monitor interno de producción (Capa 1): conversaciones sin respuesta + salud del sistema | ✅ Hecho |
| 33 | Guardian remoto (Capa 2): Claude Code trigger cada 1h auditando código del repo | ✅ Hecho |
| 32 | Validar que PRUEBA FENIX cargue correctamente nombre padre, hijos, fechas, diagnóstico | ⏳ Operacional |
| 33 | Flujo inscripción directa por WhatsApp (sin pasar por prueba) | ⏳ Pendiente |
| 34 | Filtro webhook por phone_number_id — ignorar mensajes de otros números (Dorita) | ✅ Hecho |
| 35 | Desuscribir app FENIX KIDS 2026 del WABA de Dorita | ✅ Hecho |
| 36 | FASE 1.5: pedir nombre padre + hijo antes del diagnóstico | ✅ Hecho |
| 37 | Follow-up afiche con opción de llamada telefónica | ✅ Hecho |
| 38 | Comando /agenda en Telegram — Ivan cierra agenda tras llamada | ✅ Hecho |
| 39 | Alerta llamada mejorada: nombre padre + hijo + edad + link wa.me personal | ✅ Hecho |
| 40 | Diagnóstico diferido: 3 min delay después de recibir edad (2+ números) | ✅ Hecho |
| 41 | Alerta y follow-up buscan datos en Airtable (no regex) | ✅ Hecho |
| 42 | Dos escenarios llamada: padre pide vs Ivan ofrece | ✅ Hecho |
| 43 | Clase prueba no repite datos que ya tiene de FASE 1.5 | ✅ Hecho |
| 44 | Afiche diferido: se envía después de que padre responda al diagnóstico | ✅ Hecho |
| 45 | Nuevo afiche de precios (diseño actualizado) | ✅ Hecho |
| 46 | Aurora onboarding: saludo personalizado + verificación de datos paso a paso | ✅ Hecho |
| 47 | Campos APODO en NIÑOS FENIX y APODO PADRE/MADRE en FAMILIAS FENIX | ✅ Hecho |
| 48 | Campo CONTROL DATOS (checkbox) en FAMILIAS FENIX | ✅ Hecho |
| 49 | Búsqueda fuzzy de familias (sin acentos, SequenceMatcher) | ✅ Hecho |
| 50 | Lista de niños agendados por horario al confirmar reserva | ✅ Hecho |
| 51 | Afiche automático cuando padre muestra interés post-diagnóstico (no depende de frase Ivan) | ✅ Hecho |
| 52 | Ivan prohibido inventar comandos falsos | ✅ Hecho |
| 53 | Ivan nunca dice "no te entendí" → "en qué te puedo ayudar?" | ✅ Hecho |
| 54 | Padres inscriptos sin restricción de horario nocturno | ✅ Hecho |
| 55 | Reset no-admin solo limpia conversación, NO borra Airtable | ✅ Hecho |
| 56 | buscar_familia_por_telefono busca también en CELL LIMPIO PADRE/MADRE | ✅ Hecho |
| 57 | obtener_ninos_de_familia lee IDs del registro familia (no fórmula) | ✅ Hecho |
| 58 | Topic Telegram muestra nombre del contacto de Airtable | ✅ Hecho |
| 59 | Aurora asume agenda para todos los hijos (multi-hijo) + confirmación con apodos | ✅ Hecho |
| 60 | Google Calendar eliminado — ya no se usa | ✅ Hecho |
| 61 | Horarios abril+mayo creados en HORARIOS FENIX (9 sábados x 3 turnos = 27) | ✅ Hecho |
| 62 | .env local actualizado a base Salsa Soul (appWwCQxALdMMV4MA) + token nuevo | ✅ Hecho |
| 63 | Plantillas WhatsApp para recordatorios (reemplazar Calendar) | ✅ Hecho (recordatorio viernes + plantillas Meta) |
| 64 | Borrar archivo calendar_google.py (ya no se importa) | ⏳ Pendiente |
| 65 | Tabla RESERVAS FENIX: 1 niño = 1 registro, NINO sin Ñ, FAMILIAS vinculado, lookups | ✅ Hecho |
| 66 | Detector múltiples confirmaciones en un mensaje (re.finditer) | ✅ Hecho |
| 67 | Parseo de fecha: "9 de mayo", "3/5", solo número | ✅ Hecho |
| 68 | Ivan nunca lista precios, solo "te paso un afiche" | ✅ Hecho |
| 69 | Llamada programada: padre dice hora → alerta admin a esa hora | ✅ Hecho |
| 70 | FASE 1.5 en 2 pasos: nombre padre → hijo + edad | ✅ Hecho |
| 71 | Extracción nombres: minúsculas, coma, "Ivan, se llama benja" | ✅ Hecho |
| 72 | TALLA REMERA campo select (6/8/10/12/14/P/M/G/XG) + Aurora pregunta si vacío | ✅ Hecho |
| 73 | Aurora acepta agendar para hoy si el padre lo pide | ✅ Hecho |
| 74 | Tabla CONTENIDO FENIX en Airtable (posteos vinculados a niños) | ✅ Hecho |
| 75 | Tabla REDES FENIX en Airtable (perfiles de redes sociales) | ✅ Hecho |
| 76 | Módulo contenido_social.py: polling + calendario diario + recordatorio viernes | ✅ Hecho |
| 77 | enviar_plantilla en provider Meta (template messages) | ✅ Hecho |
| 78 | Calendario diario: lun=IG, mar=FB, mié=TT, jue=YT, vie=Threads, sáb=fotos, dom=videos | ✅ Hecho |
| 79 | "Tu hijo aparece en este posteo" — WhatsApp automático cuando Claude de Postiz carga contenido | ✅ Hecho |
| 80 | Recordatorio viernes 18:00 PY — confirmación activa pre-clase sábado | ✅ Hecho |
| 81 | Crear plantillas en Meta Business Manager (contenido_diario, contenido_hijo, recordatorio_clase) | ⏳ Pendiente (Ivan) |
| 82 | Actualizar links reales en REDES FENIX de Airtable | ⏳ Pendiente (Ivan) |
| 83 | Sistema de referidos (REFERIDOS FENIX + detección números + plantilla) | ⏳ Pendiente |
| 84 | Menú Aurora para padres inscriptos (5 opciones + cancelar/reagendar) | ✅ Hecho |
| 85 | Auto-registro por WhatsApp: "Hola Aurora" para no registrados → FAMILIA + formulario | ✅ Hecho |
| 86 | /fenix en Telegram resetea conversación + /registro inicia Aurora | ✅ Hecho |
| 87 | Topic Telegram va directo al grupo correcto (FLIAS si familia, LEADS si lead) | ✅ Hecho |
| 88 | Topic viejo se cierra al migrar de grupo | ✅ Hecho |
| 89 | Aurora usa apodo o solo primer nombre, nunca nombre completo | ✅ Hecho |
| 90 | Deducir papá/mamá del nombre al registrar (deducir_genero) | ✅ Hecho |
| 91 | Fecha nacimiento se convierte a ISO antes de guardar en NIÑOS | ✅ Hecho |
| 92 | Aurora cancela reservas en Airtable + ofrece reagendar | ✅ Hecho |
| 93 | Aurora muestra reservas activas cuando padre elige opción 1 | ✅ Hecho |
| 94 | Aurora confirma reserva directo, NUNCA pide confirmación extra | ✅ Hecho |
| 95 | Kill switch AGENTE_PAUSADO env var para emergencias | ✅ Hecho |
| 96 | Seguimiento automático desactivado temporalmente | ⏳ Pendiente (reactivar con nuevo follow-up) |
| 97 | Armar follow-up de leads (reemplazar seguimiento desactivado) | ⏳ Pendiente |
| 98 | Timezone Paraguay (UTC-3) en resumen anuncios + FECHA CREACION | ✅ Hecho |
| 99 | Comando "resumen reservas" por WhatsApp (Aurora + Fenix por turno) | ✅ Hecho |
| 100 | Comando "resumen followup" por WhatsApp (mapa FU completo) | ✅ Hecho |
| 101 | Guard duplicados en crear_reserva (verifica antes de crear) | ✅ Hecho |
| 102 | HORARIOS FECHA es tipo Date — usar DATESTR() en formulas Airtable | ✅ Hecho |
| 103 | Resumen reservas muestra edad (EDAD HIJO) + promedio por turno | ✅ Hecho |
| 104 | Reconocimiento facial AWS Rekognition (fotos de clase → identificar niños) | ✅ Hecho |
| 105 | Campos FOTO + FACE_ID en NIÑOS FENIX y PRUEBA FENIX | ✅ Hecho |
| 106 | Comando "fotos [turno]" por WhatsApp — modo fotos + resumen + vincular CONTENIDO | ✅ Hecho |
| 107 | Comando "registrar cara [nombre]" — indexar cara nueva en Rekognition | ✅ Hecho |
| 108 | Script indexar_caras.py — carga inicial desde Airtable (NIÑOS + PRUEBA) | ✅ Hecho |
| 109 | descargar_media() en provider Meta — obtener bytes de imágenes WhatsApp | ✅ Hecho |
| 110 | Tabla SEGUIMIENTO FENIX en Airtable (mensajes personalizados post-clase) | ✅ Hecho |
| 111 | Botones ENVIADO/DESCARTADO en seguimiento — marca checkbox en Airtable | ✅ Hecho |
| 112 | Comando "resumen asis [fecha]" — presentes/ausentes por turno | ✅ Hecho |
| 113 | Comando "resumen prueba [fecha]" — dashboard pruebas (asis+pagos+inscripción+seguimiento) | ✅ Hecho |
| 114 | Comando "resumen seguimiento [fecha]" — estado mensajes personalizados | ✅ Hecho |
| 115 | cargar familia: búsqueda sin tildes (normalización unicodedata) | ✅ Hecho |
| 116 | btn_id en MensajeEntrante para distinguir acciones de botones | ✅ Hecho |
| 117 | Migración cara PRUEBA→NIÑOS al inscribir (cargar familia) | ✅ Hecho |
| 118 | Shift+Enter para nueva línea en Claude Code (keybindings.json) | ✅ Hecho |
| 119 | Refactor prompt Ivan: frame evaluativo + menú 10 opciones | ✅ Hecho |
| 120 | "prueba" → "evaluación" en todos los mensajes hardcodeados al padre | ✅ Hecho |
| 121 | Normalización menú viejo 15→10 para leads en curso | ✅ Hecho |
| 122 | Detección diagnóstico (TDAH/TEA/etc) → alerta Telegram con link topic | ✅ Hecho |
| 123 | Comandos /aprobado y /rechazado en Telegram para evaluación manual | ✅ Hecho |
| 124 | FASE 2B: primero diagnóstico, después pregunta evaluación con costo, fechas solo si dice sí | ✅ Hecho |
| 125 | Cupos eliminados del prompt — solo sábado más cercano con 3 turnos | ✅ Hecho |
| 126 | Campo RETORNANTE_AVISADO en LEADS FENIX (Airtable) | ✅ Hecho |
| 127 | Leads retornantes: implementado pero DESACTIVADO (causó crash, pendiente fix) | ⏳ Pendiente |
| 128 | Evaluación manual (en_evaluacion_manual en PostgreSQL): DESACTIVADO (mismo crash) | ⏳ Pendiente |
| 133 | Detección spam/scam → silenciar + alertar Telegram (no responder) | ✅ Hecho |
| 134 | Limpieza [SISTEMA:...] de respuestas Claude antes de enviar al padre | ✅ Hecho |
| 135 | REFRAME PARQUE FENIX: papá+hijo entrenan juntos, sin menú dolor, sin evaluación | ✅ Hecho |
| 136 | 90mil NO se descuenta — es un sábado en el parque, no prueba/evaluación | ✅ Hecho |
| 137 | Frase ancla "sábado inolvidable para vos y tu hijo" en todos los CTAs | ✅ Hecho |
| 138 | Limpieza basura flujo anterior en reminders.py y telegram_bridge.py | ✅ Hecho |
| 139 | FASE 2 más lenta: personalización por edad → gancho papá → cierre emocional → fechas solo si dice sí | ✅ Hecho |
| 140 | Eliminado código muerto: normalización 15→10, delay por números, _contar_numeros | ✅ Hecho |
| 141 | Export conversaciones: all_phones.txt actualizado (772→998), labels Agendó→Datos enviados | ✅ Hecho |
| 142 | Obsidian: todos los MDs de FENIX KIDS vinculados con up:: al MOC | ✅ Hecho |
| 143 | Foto/video del parque para enviar automáticamente después de FASE 1 | ⏳ Pendiente (Ivan prepara) |
| 144 | Tabla ANUNCIOS FENIX en Airtable + campo ANUNCIO en LEADS FENIX (linked record) | ✅ Hecho |
| 145 | Rastreo automático de anuncio por lead: referral.source_id → ad_source_id en DB → link en Airtable | ✅ Hecho |
| 146 | Doc CONEXION FENIX - SALSA SOUL - META en Obsidian (paso a paso vincular IG para ads) | ✅ Hecho |
| 129 | Bitácora sesiones renombrada a BITACORA SESIONES FENIX.md | ✅ Hecho |
| 130 | Conversaciones WhatsApp movidas al Vault (CONVERSACIONES FENIX/) | ✅ Hecho |
| 131 | Export conversaciones automático al iniciar sesión (día anterior) | ✅ Hecho |
| 132 | Archivos renombrados a FENIX YYYY-MM-DD.md | ✅ Hecho |
| 147 | Sábado corriente incluido en fechas disponibles (>= en vez de >) | ✅ Hecho |
| 148 | Comando PRESENTE nombre — marca asistencia individual (crea reserva si no existe) | ✅ Hecho |
| 149 | PRESENTE PRUEBA nombre — busca solo en PRUEBA FENIX | ✅ Hecho |
| 150 | Fix reagendamiento PRUEBA FENIX — solo actualiza, no crea registro nuevo + notifica admin | ✅ Hecho |
| 151 | Guard formulario: no crear PRUEBA FENIX duplicada post-redeploy | ✅ Hecho |
| 152 | Registrar cara busca en NIÑOS + PRUEBA FENIX | ✅ Hecho |
| 153 | Campo NINO FENIX (linked record) en PRUEBA FENIX — vincula al migrar | ✅ Hecho |
| 154 | Alerta reserva doble (mismo niño, mismo día, otro horario) | ✅ Hecho |
| 155 | Asistencia no muestra duplicados (inscripto > prueba) | ✅ Hecho |
| 156 | Asistencia acepta nombres extra post-lista (crea reserva + presente) | ✅ Hecho |
| 157 | Match por palabras (no substring) — "Enzo Echeverz" matchea "Enzo Manuel Echeverz Golin" | ✅ Hecho |
| 158 | Campo AUSENTE (checkbox) en RESERVAS FENIX y PRUEBA FENIX | ✅ Hecho |
| 159 | Asistencia muestra ✅/❌ si ya fue cargada | ✅ Hecho |
| 160 | Tool Use Ivan: 5 tools (reagendar, confirmar, escalar, disponibilidad, llamada) | ✅ Hecho |
| 161 | Tool Use Aurora: 6 tools (agendar, cancelar, agendados, familia, hijo, escalar) | ✅ Hecho |
| 162 | Hooks PreToolUse (fecha/hora/sábado + anti-spam escalación) | ✅ Hecho |
| 163 | Hooks PostToolUse (Telegram + CAPI) | ✅ Hecho |
| 164 | Guards regex: si tool manejó acción, regex no ejecuta (5 bloques) | ✅ Hecho |
| 165 | Monitorear tools Aurora en prod (agendar/cancelar/registrar via WhatsApp real) | ✅ Hecho |
| 166 | Paso 3: partir monolito main.py (solo moves de archivos, sin cambios de lógica) | ⏳ Pendiente |
| 167 | QR Check-in: qr.py + endpoint /checkin/{record_id} + logo FENIX + HORA_CHECKIN | ✅ Hecho |
| 168 | gestionar_reserva: tool unificada Aurora (agendar/reagendar/cancelar en 1) + tool_choice forzado | ✅ Hecho |
| 169 | gestionar_prueba: tool unificada Ivan (confirmar/reagendar en 1) | ✅ Hecho |
| 170 | Flujo determinístico post-pago: mensaje fijo + modo_agenda flag + tool forzada | ✅ Hecho |
| 171 | QR para leads: envío post-formulario (no post-agenda) | ✅ Hecho |
| 172 | Reservas Airtable inyectadas en mensaje del usuario (no system prompt) | ✅ Hecho |
| 173 | Fix ARRAYJOIN con record links → usar lookup texto FAMILIA | ✅ Hecho |
| 174 | Prompt Ivan: cobrar PRIMERO, agendar DESPUÉS (automático post-pago) | ✅ Hecho |
| 175 | Carpeta marketing/ con logos, afiches, anuncios, caricaturas, docs | ✅ Hecho |
| 176 | AIRTABLE ERRORES.md en Obsidian (6+5 errores documentados) | ✅ Hecho |
| 177 | COMO ARMAR TOOL AGENDAS - QR - AIRTABLE.md — guía maestra (17 errores + solución completa) | ✅ Hecho |
| 178 | QR Fase 3: email con QR via Airtable automation + Gmail | ⏳ Pendiente (Ivan) |
| 179 | QR Fase 4: página bonita con branding en Cloudflare Pages | ⏳ Pendiente |
| 180 | Ordenar raíz del proyecto: mover docs/datos/nombres/JSONs a carpetas | ✅ Hecho |
| 181 | Borrar archivos muertos del template (LICENSE, start.sh, Dockerfile, docker-compose.yml) | ✅ Hecho |
| 182 | Actualizar .env.example con las 21 variables reales | ✅ Hecho |
| 183 | Actualizar /cierre y memorias para apuntar a docs/ (no raíz) | ✅ Hecho |
| 184 | Marcar 65 PRUEBA FENIX históricos como QR ENVIADO en Airtable | ✅ Hecho |
| 185 | ARCHITECTURE.md + CHANGELOG.md + ADR (material para curso IA) | ⏳ Pendiente |
| 186 | Limpieza Airtable: borrar horarios 9:30 + reservas duplicadas testing | ⏳ Pendiente |
| 187 | QR familia/prueba: tabla ASISTENCIA FENIX + páginas check-in + toggle + logo | ✅ Hecho (sesión 6) |
| 188 | QR Fase 2: comando "QR" — papá escribe "QR" → recibe su QR (tool, NO regex) | ⏳ Pendiente |
| 189 | QR sub-fase: migrar envío automático (post-pago/reserva) a QR familia/prueba (1 solo, no por hijo) | ⏳ Pendiente |
| 190 | QR Fase 3: apagar campo PRESENTE viejo en RESERVAS/PRUEBA + migrar histórico a ASISTENCIA FENIX | ⏳ Pendiente |
| 191 | Deuda: endpoint /enviar-qr-familia devuelve enviado:true sin chequear envío real (el de prueba sí chequea) | ⏳ Pendiente |
| 192 | Bug `detectar_tipo_pago()`: clasifica mensualidad/paquete como "prueba" por keywords. Fix por ESTADO del lead (ya tiene PRUEBA con PAGO → siguiente pago = mensualidad). Va con el menú interactivo | ⏳ Pendiente (mañana) |
| 193 | Fecha nacimiento de Gastón Pedrozo (Johanna Britez, 595971580929) quedó vacía — el padre puso "10 agosto 2026" (imposible). Falta confirmar el año real | ⏳ Operacional |
| 194 | Edith, César, Johanna, Lee siguen modelados en PRUEBA FENIX con INSCRIPTO, no en FAMILIAS FENIX. Evaluar inscribirlos como familias reales | ⏳ Pendiente |
| 195 | FASE 2.A paso 1 (router): helper `familia_es_activa` — familias en estado A PRUEBA siguen con Ivan, no Aurora | ✅ Hecho (commit 7a00032) |
| 196 | FASE 2.A paso 2 (flujo pago): `/agenda` crea FAMILIA A PRUEBA + niños (dual-write) vía `crear_familia_a_prueba`; inscripción reutiliza la familia y pasa a ACTIVO; `obtener_familias_inscriptas` excluye A PRUEBA | ✅ Hecho (commits f22c3db + 8c60931) |
| 197 | FASE 2.A paso 2 — VERIFICACIÓN EN VIVO pendiente: ciclo `/agenda` → FAMILIA A PRUEBA creada → sigue Ivan → inscripción → ACTIVO → Aurora, con número de test | ⏳ Pendiente (próxima sesión) |
| 198 | FASE 2.B: migrar evento de prueba a RESERVAS + ASISTENCIA (reapuntar lecturas: checkin, lista asistencia, listar alumnos, resúmenes) | ⏳ Pendiente |
| 199 | FASE 2.C: dejar de escribir PRUEBA FENIX (el corte) — solo tras 2.A+2.B estables en prod varios días | ⏳ Pendiente |
| 200 | FASE 2.D: migrar histórico + deprecar PRUEBA FENIX (legacy read-only) | ⏳ Pendiente |
| 201 | Borrar opciones viejas del select CONCEPTO de PAGOS en la UI (F.PRUEBA*, F.MENSUAL*, etc.) — cosmético, lo hace Ivan, no por API | ⏳ Pendiente (Ivan) |
| 202 | Monitor detecta fallos de envío a Meta (401 = token muerto) y alerta por Telegram — antes decía "Todo OK" mientras los mensajes se caían | ✅ Hecho (commit c20f1c3) |
| 203 | Endpoint admin `POST /reset/{telefono}` — reset total remoto (conversación + Airtable cascada) con X-ADMIN-KEY, sin que la persona escriba holayosoyfenix | ✅ Hecho (commit fde871b) |
| 204 | Fix topics Telegram duplicados/rebotando: índice UNIQUE en topics_telegram + dedup + manejo race (commit 6050867); decisión de grupo única por `agent_actual` persistente vía `grupo_telegram_para` (commit d4c7dde) | ✅ Hecho (deployado y verificado) |
| 205 | Test en vivo fix topics: Ivan manda "Hola" desde 595982790407 (Aurora) → confirmar que topic migra UNA vez a FLIAS y 2do mensaje NO rebota. Opcional: endpoint `/debug/topics-dup` de solo lectura para inspeccionar la DB | ⏳ Pendiente (próxima sesión) |
| 206 | Limpieza manual en Telegram de los topics ya cerrados que quedaron de antes del fix (el fix frena nuevos, no borra los viejos) | ⏳ Operacional (Ivan, opcional) |
| 207 | Seguridad Fase 0 (replicada de Dorita): firma X-Hub-Signature-256 del webhook (commit b1555ad), META_VERIFY_TOKEN sin default + guard (c1f2c14), ADMIN_PHONE sin default (fb3fe4e). META_APP_SECRET + META_FIRMA_RECHAZAR=1 cargados → rechazo 403 ACTIVO, verificado en prod | ✅ Hecho (deployado y verificado en vivo) |
| 208 | Fix agendamiento "venir HOY": `obtener_horarios_disponibles` usaba `IS_AFTER({FECHA}, hoy)` que excluía los turnos del día → un lead que pedía venir el mismo sábado recibía "no hay cupo, próximo es el otro sábado". Cambio: `NOT(IS_BEFORE(...))` = fecha >= hoy + hora PY (no `date.today()` del server UTC). No filtra por hora: la persona decide 11:00 o 15:30 | ✅ Hecho (commit 1ab2f33, deployado + verificado vs Airtable) |
| 209 | Automatización horarios mensuales: `crear_horarios_mes(año, mes)` (sábados × [11:00, 15:30], idempotente) + loop `_horarios_mensuales_loop` (al arrancar asegura mes actual+siguiente; corre el ÚLTIMO día del mes 9AM PY y crea el mes siguiente; avisa al admin por WhatsApp SOLO si creó turnos nuevos). Registrado en lifespan + monitor. Próximo disparo real: 30/6 9AM → crea agosto | ✅ Hecho (commit 98b76e1, deployado + verificado, junio+julio cargados) |
| 210 | HUECO DE DISEÑO (causa raíz): el pago automático (`_procesar_comprobante` en flujo_pagos.py) marca `CONVERSION=PAGO` pero NO crea reserva/PRUEBA FENIX/FAMILIA. La materialización (FAMILIA A PRUEBA + PRUEBA FENIX) solo ocurre por el comando `/agenda` (cierre por llamada). Un lead que paga DIRECTO (manda comprobante sin pasar por /agenda) queda con el pago marcado pero sin reserva, sin familia, sin monto/método en Airtable (solo el monto crudo en PostgreSQL). Ej: Samuel 595983191291 | ⏳ Pendiente (decisión de diseño) |
| 211 | PLAN REDISEÑO pendiente: Ivan quiere que LEADS sea la tabla central (reciba pago/método, conecte directo con FAMILIA y PAGOS, migrar datos de PRUEBA FENIX). CATCH estructural: LEADS FENIX es 1 fila/teléfono; reservas y pagos son per-niño/recurrentes → no entra. Alternativa relacional (recomendada): que el pago automático haga lo de `/agenda` (FAMILIA A PRUEBA + RESERVA + PAGOS, tablas que YA existen con sus links). Decisión + plan detallado: próxima sesión | ⏳ Pendiente (próxima sesión) |
| 212 | Carga manual de pagos (operacional): Samuel 595983191291 (papá Ronny Paez, hijo Samuel) → PRUEBA FENIX 330k F.MENSUAL TRANSFER reserva 13 jun 15:30 + PAGOS 330k MENSUAL. Esteban 595995623883 (papá Esteban Echeverz, hijo Enzo) → 90k transfer (mayo) + 90k efectivo (hoy) = 180k, ambos reales en PAGOS, PRUEBA método [TRANSFER,EFECTIVO], reserva corregida a 13 jun | ✅ Hecho (manual, vía airtable_client) |
| 213 | DESCUBRIMIENTO estructural: PAGOS (tblYFtTzh2Y2zdwaX, compartida con Salsa) es el ledger real de pagos Fénix: `FUENTE='FENIX KIDS ACADEMY'`, `ESTADO DE PAGO='PAGADO'`, CONCEPTO (PRUEBA/MENSUAL/MATRICULA/TRIMESTRAL...), METODO (TRANSFER/EFECTIVO/DEBIT/CREDIT), links a PRUEBA FENIX y FAMILIA FENIX. Hay 3 tablas "leads": LEADS FENIX (la del agente), RESERVA LEADS (Salsa/Dorita, ya tiene monto+método+PAGOS), LEADS (staging). Patrón crear PAGOS en inscripcion.py:492 | ✅ Documentado |
| 214 | REGLA aprendida: antes de crear un pago en PAGOS, verificar si el registro ya tiene uno linkeado (Esteban ya tenía el de mayo → casi duplico). Y no cargar nombres a ciegas: confirmar a qué familia corresponde | ✅ Anotado (memoria) |
| 215 | EJE A / A1: crear la RESERVA FENIX real al confirmar/reagendar prueba (`tools/reservas.py`) y en el formulario post-pago (`main.py`), dual-write reusando `gestionar_reserva`. Aislado en try/except, idempotente | ✅ Hecho (commits 633b33b + f36bd2e, deployado) |
| 216 | A1 — VERIFICACIÓN EN VIVO pendiente: un lead real confirma/reagenda prueba → log `[A1] Reserva real OK` o RESERVA FENIX nueva en Airtable | ⏳ Pendiente (próxima sesión) |
| 217 | EJE A / A2 datos: medido con `scripts/migrar_reservas_historicas.py` (dry-run) → 0 reservas vivas que migrar (las candidatas eran basura del parser de fechas sin año). A1 ya cubre las futuras. Lecturas de asistencia/resumen NO se migran (Iván las va a rehacer con el lector facial) | ✅ Resuelto (script herramienta, commit 563ed97) |
| 218 | EJE B / B1: tabla **TUTORES FENIX** (`tblYlRqpGqtQGyUJA`) creada — NOMBRE/APELLIDO/APODO/CI/CELL/EMAIL/FECHA NACIMIENTO/PARENTESCO(Papá/Mamá/Tutor)/ES QUIEN PAGA/FAMILIA(link) + CELL LIMPIO y LINK CELL LIMPIO (fórmulas réplica exacta). Link inverso en FAMILIAS | ✅ Hecho (vía Airtable MCP) |
| 219 | EJE B / B1: migración `scripts/migrar_tutores.py` ejecutada — 104 tutores desde 80 familias, 47 quien-paga (CELL = TELEFONO de PRUEBA con pago), 0 duplicados, backup JSON. Corregido dato corrupto "V�ctor"→"Víctor" en FAMILIAS | ✅ Hecho (commit 042ba45) |
| 220 | EJE B / B1: escritura dual — helper `crear_o_actualizar_tutor` + llamado en `crear_familia` (cubre todos los flujos) y `registrar_familia`. Idempotente (CELL LIMPIO + PARENTESCO + check id FAMILIA en código), aislado en try/except | ✅ Hecho (commit 13544f5, deployado) |
| 221 | EJE B / B2 cimiento: helper de lectura `obtener_tutores_de_familia` con fallback a campos PADRE/MADRE viejos (no-op, nadie lo llama aún) | ✅ Hecho (commit 6af1dac, deployado) |
| 222 | EJE B / B2: primera lectura migrada — saludo del menú inscriptos (`alumno_menu.py` `_primer_nombre`) lee de TUTORES | ✅ Hecho (commit 8cfce2a, deployado) |
| 223 | EJE B / B2 — webhook "quién escribe" `_build_contexto_aurora` (main.py) migrado a `obtener_tutores_de_familia` (3 lecturas: quién escribe, bloque DATOS COMPLETOS, fallback apellido reservas). Verificado en vivo (Aurora saludó por nombre desde TUTORES) | ✅ Hecho (commit f67bb02, deployado) |
| 227 | PERF (descubierto en B2): bloque "TOTAL AGENDADOS POR HORARIO" de `_build_contexto_aurora` hacía 18 queries Airtable EN SERIE (6 horarios × 3) ≈19s — el grueso de la latencia de Aurora. Paralelizado con `asyncio.gather` + semáforo de 5 (rate limit Airtable; `_get_records` no maneja 429). Totales idénticos. Latencia Aurora medida en prod: **22s → 8s** | ✅ Hecho (commit f31cfae, deployado + verificado) |
| 228 | EJE B / B2 — displays migrados a TUTORES: saludo WhatsApp al activar Aurora (main.py) + fallback nombre de familia al crear reserva (agenda.py) | ✅ Hecho (commit 53960be, deployado) |
| 229 | EJE B / B2 — DECISIÓN: lo que corre en hot-path (nombre del topic Telegram; Grupo 2 = `buscar_familia_por_telefono`/`por_nombre`/`familia_es_activa`) se resolvió con **lookups/rollups en Airtable** (datos de tutores pre-cargados en el registro, 0 fetch). 7 campos creados + 4 consumidores migrados (sesión 19). NO migrar resumenes.py ni APIs web main.py:692/777 (código a rehacer) | ✅ Hecho (sesión 19) |
| 231 | EJE B / B2 — `obtener_familias_inscriptas` (broadcasts): NO se migró. Ivan decidió DESACTIVAR todos los broadcasts automáticos y rearmarlos desde cero en otra sesión. La función sigue leyendo PADRE/MADRE pero su código no se ejecuta (loops apagados). Migrar al rearmar broadcasts (campos `SALUDOS TUTORES`/`CELLS LIMPIOS TUTORES` ya listos) | ⏳ Pendiente (al rearmar broadcasts) |
| 232 | Rediseñar desde cero el sistema de comunicación automática a familias (saludo diario, aviso de posteo, recordatorio viernes) — los 3 loops de `contenido_social.py` quedaron DESACTIVADOS (commit `5707ad7`) | ⏳ Pendiente (otra sesión) |
| 233 | EJE B / B2 — verificación en vivo de `buscar_familia_por_telefono` migrado: cuando escriba un cliente real, confirmar que lo reconoce y rutea a Aurora (análisis exhaustivo lo respalda: 103/103 clientes reconocidos) | ⏳ Pendiente (evento real) |
| 234 | Borrar registro fantasma `recnXmWvMtZavs7wy` (FAMILIA "  ", cell `595985619453`, sin nombre/hijos/tutores) — único no reconocido por la búsqueda nueva, ya ruteaba como lead | ⏳ Operacional (opcional) |
| 230 | EJE B / B2 — verificación en vivo del saludo WhatsApp (deploy 2): se dispara al ACTIVARSE Aurora para un inscripto, no en cada mensaje. Test unitario pasó + boot limpio; falta gatillar la activación real | ⏳ Pendiente (opcional) |
| 224 | EJE B — VERIFICACIÓN EN VIVO escritura dual: un registro/pago real de familia nueva → confirmar que se creó su TUTOR en TUTORES FENIX | ⏳ Pendiente (próxima sesión) |
| 225 | BUG latente: `_get_records` (airtable_client:184) NO pagina, trunca a 100 registros (param `maxRecords` no sigue `offset`). Ya duplicó tutores al re-correr migración. Para tablas >100 (TUTORES ya tiene 104) paginar manual. También: `ARRAYJOIN({link})` devuelve el nombre, NO record_ids → no filtrar links con FIND(id) | ⏳ Pendiente (arreglar _get_records requiere /pre-cambio, lo usa todo el código) |
| 226 | EJE A / A3 (corte) y EJE B / B3 (contract) pendientes: sacar `crear_prueba_fenix` + borrar tabla PRUEBA; quitar escritura PADRE/MADRE + borrar campos. Solo cuando A1/B1/B2 estén estables varios días | ⏳ Pendiente |

---

## 12. Historial de Cambios

| Fecha | Cambio realizado |
|---|---|
| 2026-04-06 | Proyecto creado. Copiado desde Dorita y adaptado para FENIX KIDS ACADEMY. Dual agente: Profe Ivan + Nixie. Nueva estructura Airtable: LEADS, FAMILIAS, NIÑOS, HORARIOS, RESERVAS. Creados todos los archivos del agente. |
| 2026-04-06 | Airtable: creada tabla LEADS, campo TALLA REMERA en NIÑOS, opciones 16:00 y 17:30 en HORARIOS. |
| 2026-04-11 | Sistema de auto-organización: slash command `/cierre`, trigger `yosoyfenix` para briefing al inicio, memorias persistentes en `~/.claude/.../memory/` (project_state, feedback_session_close, feedback_yosoyfenix_trigger, reference_fenix_resumen, user_ivan). Verificación del `.env` real: META, TELEGRAM, GOOGLE_CALENDAR y GROQ ya estaban configuradas — el resumen estaba desactualizado desde el commit inicial. Sección 10 y 11 sincronizadas con la realidad. Pendiente confirmar con el usuario el estado del deploy en Railway. |
| 2026-04-11 (cierre 2) | Confirmado por el usuario: deploy en Railway funcionando, webhook de Meta apuntando a Railway, `GOOGLE_CREDENTIALS_JSON` cargado, leads/familias reales en Airtable. Sección 11: items 5–10 marcados ✅. Estado del proyecto = **en producción**. Único frente abierto: ajustar flujo conversacional de Ivan/Nixie en próxima sesión. |
| 2026-04-16 (RESUMEN SESIÓN) | **Sesión completa — 6 commits en producción.** (1) Análisis exhaustivo del proyecto con priorización P0/P1/P2/P3. (2) P0 ejecutado: horarios unificados, calendar_google limpio de Dorita, fix crash `int("30h")`, RESERVA se crea en Airtable, nombre real del niño en Calendar. (3) P1 ejecutado: webhook Meta async (<200ms), auth X-ADMIN-KEY en endpoints admin, removido falso positivo `" dan "` del prompt injection. (4) Estilo Ivan más humano: sin guiones `—`/`-`, con abreviaciones WhatsApp salpicadas (q, xke, x, tdv, tmb, tdo) y acentos omitidos ocasionales. (5) **Cambio de arquitectura**: Ivan maneja TODO el flujo de leads de anuncios (saludo, diagnóstico, agenda, datos, confirmación). Nixie solo atiende inscriptos. Router por teléfono consulta FAMILIAS en Airtable. Nueva pregunta intermedia: "Con quién tengo el gusto?" antes de ofrecer probar. Sábados SOLO del mes corriente (mes siguiente como fallback). (6) Alerta urgente doble (WhatsApp + Telegram) cuando lead pide llamada telefónica, con link wa.me pre-cargado. Pendientes principales: cargar teléfonos inscriptos en Airtable FAMILIAS, definir flujo de pagos, validar todo en producción. |
| 2026-04-16 (llamada) | **Alerta urgente cuando lead pide llamada.** Si el padre escribe pidiendo hablar por teléfono ("te puedo llamar?", "podemos hablar?", "me das tu número?", "llamarnos", etc.), el bot corta el flujo normal y responde: *"Ahora mismo no puedo atender llamadas, pero te llamo desde mi línea personal en breve 📞"*. En paralelo dispara alerta DOBLE al admin: (1) WhatsApp a `ADMIN_PHONE` con el texto "🚨 URGENTE, UN PADRE FENIX QUIERE HABLAR CONTIGO" + nombre + teléfono + link `wa.me/{padre}?text=Hola+[nombre]+soy+el+profe+Ivan+otra+vez+te+puedo+llamar+ahora`; (2) Telegram al `TELEGRAM_AGENDA_GROUP_ID` con el mismo contenido (respaldo por si WA falla por ventana 24h). Nombre del padre se extrae con regex del historial ("soy X", "me llamo X", filtrando casos como "la mamá de"). Detección con 17 patrones regex testeados con 12 casos (100% OK). |
| 2026-04-16 (router) | **Cambio de arquitectura: Ivan maneja todo el flujo de leads de anuncios, Nixie solo atiende inscriptos.** Router por teléfono: al llegar primer mensaje se consulta `buscar_familia_por_telefono` en Airtable FAMILIAS (CELL PADRE / CELL MADRE). Si matchea → Nixie modo cliente_inscripto. Si no → Ivan. Eliminados: handoff Ivan→Nixie, saludo automático de Nixie, activación directa por "nixi" (ya no se usa). Flujo Ivan ampliado: después de "con quién tengo el gusto?" y nombre del padre, ofrece sábados del MES CORRIENTE (solo los disponibles, si no le queda bien alguno entonces ofrece mes siguiente), pide datos uno por uno (nombre/apellido hijo, fecha nac, nombre padre si no se presentó), y confirma con "Reserva confirmada ✅ [niño] tiene su lugar el sábado [fecha] a las [hora]h". Nixie simplificada: solo modo cliente_inscripto para nuevas reservas/reagendamientos, sin pedir datos de registro. `_contexto_fechas()` en brain.py ahora inyecta primero sábados del mes corriente, luego del mes siguiente como backup. Detector de confirmación y extracción de formulario ahora corren para ambos agentes. Bonus: objeción de "débito automático" actualizada al esquema sin débito auto. |
| 2026-04-16 (cierre) | **Bitácora completa de la sesión del día.** Análisis exhaustivo del proyecto (bugs, deuda técnica, mejoras). Priorización en P0/P1/P2/P3. Ejecutados y pusheados P0 (commit `b181bd9`) y P1 (commit `e9ddfe7`). **P0 — 5 fixes críticos**: horarios unificados a 9:30/11:00/15:30 en todos los archivos; calendar_google.py limpio de Dorita/Salsa (default GOOGLE_CALENDAR_ID, _HORARIOS_ACADEMIA, summary "FENIX Kids — [Nombre]", description, link add-to-calendar); fix crash `int("30h")` en `_proxima_fecha`; nueva `obtener_o_crear_horario` + refactor `_procesar_confirmacion_reserva` que crea RESERVA en Airtable por cada niño (antes siempre vacía); evento Calendar con nombre real del niño. Bonus: fix kwarg inválido `notificar_agenda_telegram(nombre_lead=)` y texto wa.me "de Salsa Soul" → "de FENIX Kids". **P1 — 3 mejoras de seguridad/performance**: webhook Meta async (responde OK en <200ms, procesamiento en `asyncio.create_task`); auth `X-ADMIN-KEY` en /stats /debug /telegram/setup (var ADMIN_API_KEY configurada en Railway con `openssl rand -hex 32`); removido `" dan "` de blacklist prompt injection. Usuario informó que monitorea todo desde Airtable + Railway Logs, no usa los endpoints admin. P2 y P3 anotados en memory/project_next_session.md para retomar. |
| 2026-04-16 (p1) | **P1 del análisis: hardening.** (1) Removido `" dan "` de blacklist de prompt injection (falsos positivos reales: "¿Dan clases los sábados?" bloqueaba el mensaje). (2) Webhook Meta async: el handler `POST /webhook` ahora deduplica y retorna `{"status":"ok"}` en < 100ms, lanzando el procesamiento real (delays, Claude API, Airtable, Telegram) como `asyncio.create_task`. Antes, con delays de hasta 4min por números del rompehielos + Claude + Airtable, Meta podía timeoutear (20s) y reintentar → riesgo de duplicación. Extraída `_procesar_mensaje_webhook(msg)`. (3) Auth admin: endpoints `/stats`, `/debug/{telefono}` y `/telegram/setup` ahora requieren header `X-ADMIN-KEY` contra var de entorno `ADMIN_API_KEY` (antes cualquiera podía ver el historial de cualquier lead). `.env.example` actualizado con la nueva variable. |
| 2026-04-16 | **P0 del análisis completo: fixes críticos.** (1) Horarios unificados a `9:30 \| 11:00 \| 15:30` en todos los archivos (business.yaml, prompts.yaml nixie, reminders.py, FENIX_RESUMEN); antes nixie y reminders seguían diciendo 16:00/17:30. (2) calendar_google.py limpio de restos Dorita/Salsa: default GOOGLE_CALENDAR_ID vacío (no más "salsasoulon2@gmail.com"), _HORARIOS_ACADEMIA con horarios FENIX, summary eventos "FENIX Kids — [Nombre]", descripción "Niño/a: ... via Nixie (FENIX Kids WhatsApp)", link add-to-calendar "FENIX Kids Academy — Clase". (3) Fix bug `int("30h")` en `_proxima_fecha` — ahora normaliza "9:30h"/"9h30"/"9:30hs"/"09:30" al mismo formato. (4) Nueva función `obtener_o_crear_horario(fecha, hora)` en airtable_client + refactor `_procesar_confirmacion_reserva`: ahora crea RESERVA en Airtable por cada niño de la familia (antes la tabla RESERVAS siempre quedaba vacía). (5) El evento de Google Calendar usa el nombre real del niño (o "Mateo y Sofía" si hay varios) en lugar del teléfono. (6) Fix bug colateral: `notificar_agenda_telegram` recibía `nombre_lead=` (kwarg inválido) → ahora `nombre=` correcto. (7) Fix mensaje pre-cargado del link wa.me: decía "soy el profe Iván de Salsa Soul" → ahora "de FENIX Kids 🌳". |
| 2026-04-17 | **Sesión de fixes y mejoras de robustez (5 commits).** (1) Bypass modo nocturno para admin: `_PHONES_SIN_DELAY` (número admin) ya no se bloquea por horario nocturno, permite testear a cualquier hora. (2) Transcripción de audio movida ANTES de todos los detectores (llamada, prompt injection, nocturno): antes un audio "te puedo llamar" no se detectaba y Claude respondía cualquier cosa. (3) Comando `/fenix` en Telegram: reactiva el agente silenciado (igual que `/reactivar`), mensaje "Agente Fénix activado" solo visible en el topic. (4) Reset: eliminado `holayosoylasalsa` (era de Dorita), solo queda `holayosoyfenix`. (5) Alerta de llamada mejorada: mensaje al padre personalizado con nombre ("aguantame un ratito Carolina y te llamo 🤝"), alerta al admin simplificada con nombre padre + nombre hijo + teléfono + link wa.me (sin resumen Haiku, el contexto se lee desde Telegram). (6) Función `resumir_conversacion_para_alerta` agregada en brain.py (no se usa actualmente, disponible para futuro). |
| 2026-04-21 | **Flujo de pagos completo + afiche de precios (2 commits).** (1) Nuevo módulo `agent/pagos.py`: precios, datos bancarios Itaú, detección de comprobante (imagen/documento + CI 1604338 en historial), estado pagos pendientes en memoria (in-memory dicts). (2) Provider Meta ampliado: parseo de mensajes `interactive`/`button`, `enviar_botones` (botones interactivos WhatsApp), `enviar_imagen` (reenvío por media_id), `subir_media` + `enviar_imagen_bytes` (subir archivo y enviar). `es_boton` agregado a `MensajeEntrante`. (3) Flujo en main.py: detección de comprobante → respuesta automática al lead → reenvío imagen + botones ✅❌ al admin → admin confirma/rechaza → mensaje al lead + actualización LEADS a PAGO + notificación Telegram. Handler de botones del admin interceptado antes del flujo normal. (4) Prompt Ivan reescrito: FASE 3 = pago obligatorio con datos bancarios, FASE 4 = agendamiento solo post-pago, reglas anti-agenda-sin-pago. Clase prueba solo transferencia, inscripción todos los medios. (5) Precios actualizados al afiche: quincenal trim 450+140=590, semanal/full pass trim 690+140=830, matrícula trimestral 140k. (6) Afiche `static/afiche_fenix.png`: cuando Ivan dice "te paso un afiche", sistema envía imagen automáticamente + delay 3s + follow-up con opción trimestral y prueba 90k. (7) `notificar_pago_telegram` en telegram_bridge.py: comprobante_recibido/confirmado/rechazado al grupo de agenda. Plan hermanos en el afiche: 2do 30%, 3ro 70%, 4to FREE. |
| 2026-04-15 | **Sesión de ajuste de flujo conversacional completa.** Fix transcripción audios (bug tupla bytes/mime). TELEGRAM_IGNORE_PHONES para no espejar número admin. Ivan FASE 2: respuesta conversacional (no bloques numerados), delay por cantidad de números (1→30s, 2→60s, 3→120s, 4→180s, 5+→240s, sin delay para admin), cierre emocional con esencia FENIX (naturaleza, sol, árboles, desafíos reales) + pregunta de edad contextualizada, flujo paso a paso (no tirar toda la info junta), padre que se salta diagnóstico respetado. Nixie: se presenta automáticamente tras handoff, nuevo flujo clase de prueba (muestra sábados del mes → padre elige → datos mínimos uno por uno: nombre/apellido hijo, fecha nacimiento, nombre/apellido padre/madre). Precios actualizados: sin débito auto, trimestral 20% desc (quincenal 590k, semanal 890k). Horarios: 9:30, 11:00, 15:30. Pendiente: flujo Nixie inscripción directa, agregar TELEGRAM_IGNORE_PHONES en Railway. |
| 2026-04-22/23 | **Sesión masiva — 27 commits. Hardening + migración Airtable + nuevo número WhatsApp.** (1) **Análisis de flujo conversacional**: endpoint `/conversacion/{telefono}`, comando `endpoint` en Claude Code para análisis rápido. Fixes: anti-loop "Agendar", precios siempre por afiche, Alias CI en datos bancarios, no condicionar info a pago, follow-up afiche "¿Te gustaría ser parte de Fenix Kids Academy?". (2) **Hardening producción**: lock por teléfono (asyncio.Lock), dedup persistente PostgreSQL, rate limit 10 msgs/60s, pagos persistentes en PostgreSQL (tabla pagos_pendientes), Calendar null check, alerta Telegram si Claude API falla 3x, reset solo admin, historial 40 msgs. (3) **Nuevo número WhatsApp**: app Fenix Kids Academy creada bajo Business Manager de Salsa Soul Studio (verificado). Número +595 971 938655, phone_number_id 1005063086033214. Token permanente de System User Admin. (4) **Migración Airtable**: todas las tablas migradas de base Fenix a base Salsa Soul (appWwCQxALdMMV4MA). Tablas renombradas con sufijo FENIX: LEADS FENIX, PRUEBA FENIX, FAMILIAS FENIX, NIÑOS FENIX, HORARIOS FENIX, RESERVAS FENIX. Nueva tabla DIAGNOSTICO FENIX (15 condiciones categorizadas: EMOCIONAL/FISICO/SOCIAL/CONDUCTUAL/CLINICO). Datos migrados: 27 familias, 32 niños, 8 horarios, 22 reservas. Campo FAMILIA FENIX creado en tabla PAGOS. (5) **Nixie → Aurora**: renombre completo del agente asistente en código y prompts. (6) **PRUEBA FENIX**: nueva tabla para leads que agendan. 1 registro por hijo, monto solo en el primero. Haiku extrae datos del historial. Vinculada a LEADS, DIAGNOSTICO, FAMILIA, PAGOS. Precio multi-hijo: 90k/1, 120k/2, 150k/3. (7) **FAMILIAS solo en inscripción**: ya no se crea FAMILIA al agendar prueba. PRUEBA FENIX tiene campo INSCRIPCION (checkbox) para migrar a FAMILIAS manual o por automatización Airtable. (8) **Formulario multi-hijo**: pregunta hermanitos uno por uno, nombre + apellido + fecha nac, siempre pide nombre completo del responsable. |
| 2026-04-23 | **Fix crítico WABA + mejoras flujo conversacional (3 commits).** (1) **Bug WABA Dorita**: app FENIX KIDS 2026 estaba suscrita al WABA de Dorita (error de sesión anterior al usar token temporal para POST subscribed_apps). Mensajes de 9 clientes de Dorita llegaban al server de Fenix y se procesaban como leads nuevos. Fix en código: filtro por `phone_number_id` en `parsear_webhook` (meta.py). Fix raíz: desuscripción de FENIX KIDS 2026 del WABA Dorita vía API. Disculpa enviada a los 9 clientes desde número de Dorita. (2) **Follow-up afiche mejorado**: ahora ofrece dos opciones — "te puedo agendar una clase de prueba acá, o si preferís te puedo llamar". Si elige llamar → alerta urgente al admin. (3) **Comando /agenda en Telegram**: `/agenda 90mil|120mil|150mil nombre` — Ivan cierra agenda tras llamada telefónica. Crea PRUEBA FENIX con Haiku, envía formulario + datos bancarios al padre por WhatsApp, reactiva el agente. (4) **FASE 1.5 en prompt**: cuando padre responde números, ANTES del análisis pregunta nombre padre + hijo. Diagnóstico personalizado: usa nombre del padre al inicio, menciona nombre del hijo 2 veces. Prohibido "me alegra que me lo contés" (argentinismo). (5) **Alerta llamada mejorada**: "Urgente: Llamar a [nombre]" con hijo + edad + link wa.me "soy el profe Ivan desde mi personal". |
| 2026-04-23/24 | **Refinamiento del flujo conversacional completo (10 commits).** (1) **Diagnóstico diferido**: si padre eligió 2+ números, después de recibir edad Ivan dice "dame unos minutitos" y envía diagnóstico 3 min después (5s admin). Si padre dice "ok/dale/gracias" durante la espera, Fenix no responde. (2) **Afiche diferido**: ya no se envía junto al diagnóstico. Cierre del diagnóstico = "Qué te parece que [hijo] pruebe Fenix Kids?" → espera respuesta → recién ahí afiche. (3) **Follow-up afiche busca nombre hijo en Airtable** (antes regex agarraba nombre del padre). (4) **Dos escenarios de llamada**: padre pide → "aguantame un ratito"; Ivan ofreció y padre acepta → "Super, te llamo desde mi personal". Nuevos patrones: "puedo hablar", "llamame", "la segunda". (5) **Alerta llamada busca datos en Airtable** (nombre/hijo/edad) como fuente de verdad, regex solo fallback. (6) **Edad no se confunde con rompehielos**: regex solo extrae edad cuando Ivan preguntó "cuántos años". (7) **Clase prueba no repite datos**: si ya tiene nombre padre + hijo + edad de FASE 1.5, solo pide lo que falta. Formulario completo solo para inscripción. (8) **Nuevo afiche de precios** (diseño actualizado). (9) **FENIX_API_COSTO.md**: análisis de costos de API (~$0.15-0.20 por conversación completa). |
| 2026-04-25 (parte 1) | **Sesión Aurora + apodos + eliminación Calendar (27 commits).** (1) **Aurora onboarding completo**: saludo personalizado por nombre/apodo, pregunta por hijos por apodo, verificación de datos paso a paso (quien escribe → hijos con nombre completo + apodo → otro padre). Campo CONTROL DATOS (checkbox) en FAMILIAS FENIX marca como verificado para no repetir onboarding. (2) **Campos APODO**: APODO en NIÑOS FENIX, APODO PADRE/MADRE en FAMILIAS FENIX — creados por API. Si existe, Aurora y la lista de agendados usan apodo. (3) **Búsqueda fuzzy de familias**: `buscar_familia_por_nombre` con normalización de acentos (unicodedata), búsqueda AND/OR en Airtable, scoring con SequenceMatcher. (4) **Lista de niños agendados por horario**: al confirmar reserva se envía lista con emojis (nombre+apellido+edad, orden alfabético). Aurora puede compartir lista si el padre pregunta. (5) **Afiche automático**: ya no depende de que Ivan diga "te paso un afiche". Sistema detecta interés post-diagnóstico y envía automático. (6) **Ivan mejorado**: prohibido inventar comandos falsos, nunca dice "no te entendí" → "en qué te puedo ayudar?". (7) **Padres inscriptos sin modo nocturno**: Aurora atiende a cualquier hora. (8) **Reset seguro**: reset desde n��meros no-admin solo limpia conversación local, NO borra datos de Airtable. (9) **buscar_familia_por_telefono** busca en CELL PADRE/MADRE + CELL LIMPIO. (10) **obtener_ninos_de_familia** lee IDs del registro familia directamente (fórmulas Airtable no funcionaban con linked records). (11) **Topic Telegram con nombre**: muestra nombre del contacto de Airtable en vez del teléfono. (12) **Aurora multi-hijo**: asume agenda para todos los hijos, confirmación con apodos. (13) **Google Calendar eliminado**: toda la integración removida. (14) **Horarios abril+mayo**: 27 horarios creados (9 sábados x 3 turnos). (15) **.env local** actualizado a base Salsa Soul + token nuevo. |
| 2026-04-26 | **Engranaje redes sociales + follow-up diario.** (1) **Tablas Airtable nuevas**: CONTENIDO FENIX (posteos vinculados a niños, campos: TITULO, RED, TIPO, LINK, NIÑOS FENIX linked, NOTIFICADO, FECHA) + REDES FENIX (perfiles: Instagram, Facebook, TikTok, YouTube, Threads con links e iconos). (2) **Módulo `agent/contenido_social.py`**: polling cada 5 min a CONTENIDO FENIX, detecta registros con NOTIFICADO=false, envía WhatsApp personalizado a padres cuyos hijos aparecen ("tu hijo aparece en este posteo!") o genérico a todos. Calendario diario: lun=Instagram, mar=Facebook, mié=TikTok, jue=YouTube, vie=Threads. Envío automático a las 10:00 PY. Recordatorio viernes 18:00 PY: busca RESERVAS del sábado, envía "mañana [hijo] tiene clase, respondé CONFIRMO". (3) **`enviar_plantilla`** en provider Meta: soporte para template messages (contacto fuera de ventana 24h). (4) **Integración con Editor Pro Max + Postiz**: Claude de Postiz lee nombres de archivos (apodo_apellido.jpg), publica en redes, crea registro en CONTENIDO FENIX con link + niños vinculados. Fenix detecta y envía WhatsApp automático. Airtable como puente entre los dos proyectos. (5) **Estrategia de ventana abierta**: contacto diario mantiene ventana 24h abierta, mensajes gratis. Las fotos del sábado son el ancla (el padre siempre responde). (6) **Plantillas Meta preparadas**: contenido_diario, contenido_hijo, recordatorio_clase. Textos en PLANTILLAS_META.md para crear en Meta Business. (7) **Documento ENGRANAJE_REDES_Y_REFERIDOS.md**: proceso de diseño completo desde la idea inicial hasta la decisión final. |
| 2026-04-30/05-02 | **Sesión masiva — 20 commits. Auto-registro + Aurora completa + Telegram.** (1) **Auto-registro por WhatsApp**: padre no registrado escribe "Hola Aurora" → crea FAMILIA mínima (CELL en ambos campos) → Aurora pide nombre → `REGISTRO PADRE:` guarda en campo correcto (PADRE o MADRE según `deducir_genero`) → pide hijos → `REGISTRO HIJO:` crea NIÑOS con fecha ISO. Padre registrado → saludo normal + menú. (2) **Comandos Telegram**: `/fenix` resetea conversación (limpia estado, cancela timers), `/registro` envía WhatsApp al padre (registrado → saludo + menú, no registrado → formulario). Espejo muestra mensaje exacto de Aurora. (3) **Topic Telegram directo al grupo correcto**: usa `buscar_familia_por_telefono` ANTES de crear topic (familia → FLIAS, lead → LEADS). Topic viejo se cierra con `closeForumTopic` al migrar. (4) **Aurora nombres**: usa apodo si existe, sino solo primer nombre (nunca nombre completo). Match por CELL LIMPIO PADRE/MADRE en `_build_contexto_aurora`. (5) **Cancelar/reagendar reservas**: Aurora cancela directo, borra RESERVA de Airtable (`cancelar_reservas_familia_fecha`), ofrece reagendar. Menú opción 1 = "Agendar / cancelar clase". (6) **Reservas activas en contexto**: `_build_contexto_aurora` incluye reservas futuras de la familia. Si tiene reservas → muestra días agendados + pregunta agendar/reagendar/cancelar. (7) **Fecha nacimiento ISO**: `crear_nino` convierte dd/mm/yyyy a yyyy-mm-dd (Airtable rechazaba con 422). (8) **Kill switch**: `AGENTE_PAUSADO` env var para frenar todo en emergencias. (9) **Seguimiento desactivado** temporalmente, se rearma con nuevo follow-up. (10) **Confirmación directa**: Aurora confirma reserva sin pedir "¿estás seguro?". |
| 2026-04-25 (parte 2) | **Tabla RESERVAS + flujo Ivan refinado (11 commits).** (1) **RESERVAS FENIX arreglada**: campo NIÑO renombrado a NINO (encoding UTF-8 rompía la Ñ, reservas se creaban sin niño). 1 reserva = 1 niño + 1 horario. Campo FAMILIAS vinculado. Lookups FECHA, HORA, NOMBRE COMPLETO. (2) **Detector múltiples confirmaciones**: re.finditer en vez de re.search, soporta 2 reservas en un mensaje. (3) **Parseo de fecha robusto**: soporta "9 de mayo", "3/5" y solo número. Antes solo "d/m". (4) **Ivan nunca lista precios**: siempre "te paso un afiche para que veas todas las opciones". (5) **Follow-up afiche exacto**: "te puedo agendar o te gustaría que te llame?". (6) **Llamada programada**: padre dice hora → sistema programa alerta al admin a esa hora (WhatsApp + Telegram). Si ya pasó, alerta inmediata. (7) **FASE 1.5 en 2 pasos**: paso 1 "con quién tengo el gusto?", paso 2 "cómo se llama y cuántos años tiene tu hijo/a?". (8) **Extracción nombres mejorada**: regex hijo acepta minúsculas, detector padre parsea coma ("Ivan, se llama benja"). (9) **TALLA REMERA**: campo select (6/8/10/12/14/P/M/G/XG), Aurora pregunta si vacío. (10) **Link wa.me**: "te escribo desde mi personal, te puedo llamar ahora?". (11) **Aurora acepta agendar para hoy** si el padre lo pide. |
| 2026-05-07 | **Timezone PY + comandos admin WhatsApp + fix Airtable Date (8 commits).** (1) **Timezone Paraguay (UTC-3)**: `_parsear_filtro_fecha` usaba `date.today()` en UTC (Railway), mostraba jueves cuando en PY era miércoles 23h. Fix: `datetime.now(UTC-3).date()`. También FECHA CREACION en `crear_lead` y `crear_prueba_fenix` ahora guarda hora PY. `_fecha_py()` convierte timestamps UTC viejos a fecha PY al leer. (2) **Comando "resumen reservas"**: muestra sábado más cercano por turno (9:30/11:00/15:30), separado Aurora (inscriptos) y Fenix (pruebas), con nombre + edad + promedio por turno. FECHA RESERVA en PRUEBA FENIX se guarda como texto ("9 de mayo"), no ISO — búsqueda por ambos formatos. (3) **Comando "resumen followup"**: mapa completo de FU — en curso (con horas), respondieron, pagaron post-FU, descartados. (4) **Fix HORARIOS FECHA tipo Date**: `obtener_ninos_por_horario` y `obtener_o_crear_horario` usaban `{FECHA}='2026-05-09'` que no matchea campos Date en Airtable. Fix: `DATESTR({FECHA})='...'`. (5) **Guard duplicados reservas**: `crear_reserva` verifica si ya existe antes de crear. Borrados duplicados de Benjamin y Luciana Quiñonez. |
| 2026-05-09 | **Asistencia + Aurora reservas + fixes masivos — 15 commits.** (1) **Comando asistencia**: `asis 9.30` / `asis 11` / `asis 15.30` envía lista numerada por turno. Ivan responde `ok` (todos) o `5 7` (ausentes) → marca PRESENTE en Airtable (RESERVAS FENIX + PRUEBA FENIX). Envío automático sábados: 11:00→9:30, 12:30→11:00, 17:00→15:30. Campo PRESENTE checkbox creado en PRUEBA FENIX. (2) **Fix Aurora no crea reservas**: familias pre-existentes en Airtable no tenían familia_id en DB local → `obtener_familia_id` retornaba None → reservas no se creaban. Fix: fallback a `buscar_familia_por_telefono` (CELL LIMPIO). (3) **Comando resumen telegram**: reservas + link t.me por conversación + nombre padre. (4) **Endpoint /restaurar-aurora/{tel}**: restaura número a Aurora sin borrar historial. (5) **Fix imagen post-pago**: cualquier imagen después de "pago confirmado" ya no se interpreta como comprobante. (6) **Fix monto 150K**: nuevos patrones "Monto: **150.000 Gs**" y "Son 150.000 Gs". (7) **Prompt**: prohibido "qué onda", Aurora sin negritas en nombres, agendar hoy siempre posible (Ivan + Aurora). (8) **Reagendamiento sin fecha**: detecta "se pasa a las 15:30h hoy" → actualiza Airtable. (9) **Edad años,meses**: fórmula Airtable "3,5" = 3 años 5 meses en PRUEBA FENIX y NIÑOS FENIX. (10) **Debug endpoint**: incluye topic_telegram. (11) **Directorio contactos**: memoria con tel→padre→hijos para resolver "endpoint [nombre]" sin Airtable. |
| 2026-05-08 (sesión 2) | **Intercepción pre-Claude + fixes críticos + export conversaciones (5 commits).** (1) **Intercepción pre-Claude para horarios/precios/ubicación**: cuando el padre pregunta horarios, precios o ubicación, el código responde directo SIN llamar a Claude — ahorra tokens y evita respuestas duplicadas. Combinaciones funcionan ("precio y horario" → ambos afiches). Post-diagnóstico interés ("sí", "dale") también interceptado. Claude solo responde preguntas conversacionales/complejas. (2) **Fix detección formulario post-pago**: padre mandaba datos crudos sin keywords ("nombre", "mamá") y el detector no matcheaba. Ahora si pago+formulario confirmados, basta con texto largo + fechas. Respuesta post-formulario incluye nombres hijos + fecha/hora extraídos del "Reserva confirmada" previo. (3) **Fix monto 90K vs 120K**: regex tenía typo `ransferi` que no matcheaba `Transferencia` (Transfer-e-ncia). También agregado soporte para markdown (**A transferir**:) y patrón "120.000 Gs (prueba". (4) **Prompt lluvia corregido**: decía "NUNCA inventar infraestructura" → Claude inventó "entrenamos al aire libre lluvia o sol". Ahora dice explícitamente "bajo techo en La Casona, 3000m2". (5) **Reagendamiento PRUEBA FENIX**: cuando Ivan confirma nueva fecha y ya existe registro, actualiza FECHA RESERVA/HORA en Airtable (antes no tocaba nada). Nuevo patrón "está confirmado...sábado X". (6) **Export conversaciones**: script `export_conversaciones_v2.py` descarga todas las conversaciones de prod, genera MDs por día (solo leads Ivan, excluye Aurora) + CONVERSACIONES_RESERVAS.md cruzado con Airtable PRUEBA FENIX. (7) **PRUEBA FENIX manual**: creados Amira y Eladio Martinez Acosta (595981634024, sáb 16 mayo 15:30h, 120mil). Christopher Galeano reagendado de 9 a 16 mayo. |
| 2026-05-10 (sesión 2) | **Reconocimiento facial + seguimiento post-clase + comandos admin — 12 commits.** (1) **AWS Rekognition**: módulo `agent/face_recognition.py` (crear collection, registrar/identificar/actualizar/eliminar caras). Collection `fenix-kids` creada con 7 caras indexadas (Fiorella, Tito, Oli, Fio P, Anita, Lukis, Fabri). Campos FOTO + FACE_ID creados en NIÑOS FENIX y PRUEBA FENIX. Script `scripts/indexar_caras.py` para carga inicial. Cuenta AWS creada (IAM user `fenix-rekognition`, política AmazonRekognitionFullAccess). (2) **Comando "fotos [turno]"**: modo fotos por WhatsApp — admin envía fotos, sistema identifica niños con Rekognition, muestra resumen, confirma y vincula en CONTENIDO FENIX. (3) **Comando "registrar cara [nombre]"**: admin envía foto + nombre → busca niño en Airtable → indexa en Rekognition. (4) **`descargar_media()`** en provider Meta para obtener bytes de imágenes de WhatsApp. (5) **Tabla SEGUIMIENTO FENIX** en Airtable: FECHA, NINO (link), PRUEBA (link), FAMILIA (link), MENSAJE, TELEFONO, TURNO, ENVIADO, RESPONDIO, DESCARTADO. (6) **Mensajes personalizados sab 9/5**: 22 mensajes enviados al admin con link wa.me + botones ENVIADO/DESCARTADO. btn_id agregado a MensajeEntrante para distinguir acciones. Handler en main.py marca checkbox en Airtable. MD guardado en Obsidian. (7) **Comando "resumen asis [fecha]"**: presentes/ausentes por turno (inscriptos + pruebas). (8) **Comando "resumen prueba [fecha]"**: dashboard completo — agrupa por familia (padre + hijos), muestra asistencia, monto prueba (desde PAGOS linked), monto inscripción (desde FAMILIA FENIX en PAGOS), seguimiento (enviado/descartado/pendiente), total recaudado. Filtra PAGOS por FUENTE=FENIX (base compartida con Dorita). (9) **Comando "resumen seguimiento [fecha]"**: estado mensajes personalizados. (10) **cargar familia**: búsqueda sin tildes con unicodedata. (11) **Migración cara PRUEBA→NIÑOS**: al inscribir con cargar familia, re-indexa con nuevo record_id. (12) **Keybindings**: Shift+Enter para nueva línea en Claude Code. |
| 2026-05-11 | **Refactor evaluativo + reconocimiento facial + seguimiento — sesión maratónica (30+ commits).** (1) **AWS Rekognition**: módulo face_recognition.py, 7 caras indexadas, comandos "fotos [turno]" y "registrar cara [nombre]", descargar_media() en provider Meta, script indexar_caras.py. Campos FOTO+FACE_ID en NIÑOS y PRUEBA FENIX. Migración cara PRUEBA→NIÑOS al inscribir. (2) **SEGUIMIENTO FENIX**: nueva tabla Airtable (FECHA, NINO, PRUEBA, FAMILIA, MENSAJE, TELEFONO, TURNO, ENVIADO, DESCARTADO). 22 mensajes personalizados sab 9/5 enviados con botones. Handler btn_id en MensajeEntrante. (3) **Comandos admin nuevos**: resumen asis, resumen prueba (dashboard con pagos linked), resumen seguimiento. cargar familia sin tildes (unicodedata). (4) **Refactor prompt Ivan**: frame evaluativo ("prueba"→"evaluación"), menú 15→10, inscripción directa prohibida. Intentó con human-in-the-loop completo (en_evaluacion_manual en PostgreSQL) pero crasheó silenciosamente — revertido. Reimplementado paso a paso: solo prompt + texto + normalización 15→10 + alerta diagnóstico. (5) **Alerta diagnóstico**: detectar_diagnostico() con keywords TDAH/TEA/etc → alerta Telegram con link topic + comandos /aprobado /rechazado. (6) **FASE 2B corregida**: primero diagnóstico, después "¿querés agendar evaluación? 90mil", fechas solo cuando dice sí. Sin cupos. (7) **Organización Obsidian**: CONVERSACIONES_FENIX.md → BITACORA SESIONES FENIX.md. Carpeta CONVERSACIONES FENIX movida al Vault. Export automático al iniciar sesión. Archivos renombrados a FENIX YYYY-MM-DD.md. Reconstruidas sesiones 1-6 mayo. |
| 2026-05-12 | **CAMBIO DE PARADIGMA: PARQUE FENIX — 8 commits.** (1) **Detección spam/scam**: links .buzz/.xyz, mensajes de estafa → NO responde, silencia conversación, alerta Telegram. Prompt injection también silencia en vez de responder. (2) **Reframe completo PARQUE FENIX**: eliminado menú de dolor 1-10/1-15, eliminada "evaluación"/"clase de prueba"/"si es aceptado". Nuevo frame: "papá + hijo entrenan JUNTOS en el Parque FENIX". 90mil NO se descuenta, es un sábado en familia. (3) **FASE 2 más lenta**: personalización por edad (qué va a vivir el nene) → gancho papá ("a vos también te entrenamos!") → cierre emocional (90mil como experiencia) → "¿qué te parece la idea?" → fechas solo cuando dice sí. (4) **Frase ancla** "sábado inolvidable para vos y tu hijo" en TODOS los CTAs (prompt, afiche, reminders, followup). (5) **Limpieza total**: basura del flujo anterior en reminders.py ("evaluación/se descuenta"), telegram_bridge.py ("clase evaluativa/si es aceptado"), alerta diagnóstico (sin /aprobado /rechazado). (6) **Fix [SISTEMA:]**: Claude generaba `[SISTEMA: EVALUACION_MANUAL_REQUERIDA]` visible al padre → ahora se limpia antes de enviar. (7) **Export conversaciones**: all_phones.txt actualizado 772→998, labels corregidos (Agendó solo si pagó). (8) **Obsidian**: 25 MDs vinculados con up:: al MOC FENIX KIDS. Foto/video del parque pendiente (Ivan prepara). |
| 2026-05-12 (sesión 3) | **Tracking de anuncios Meta + doc conexión Salsa Soul.** (1) **Tabla ANUNCIOS FENIX en Airtable**: NOMBRE, META AD ID, TIPO (Reel CapCut/Reel Ivan/Carrusel), ESTADO, FECHA INICIO, MONTO DIARIO, GASTO TOTAL, CONVERSACIONES (count auto), CIERRES (rollup auto), NOTAS. 2 anuncios cargados (Carrusel niño/hombre + Giuli Equilibrio). (2) **Campo ANUNCIO en LEADS FENIX**: linked record a ANUNCIOS FENIX. (3) **Rastreo automático ad_source_id**: provider Meta captura `referral.source_id` (ID del anuncio), se guarda en DB (columna ad_source_id), al crear lead en Airtable se busca el anuncio y se linkea automáticamente. 5 archivos: base.py, meta.py, memory.py, main.py, airtable_client.py. (4) **Doc CONEXION FENIX - SALSA SOUL - META**: paso a paso para vincular IG Fenix con Salsa Soul para correr anuncios (desvincular FB → conectar desde Salsa Soul → correr ads → revincular). |
| 2026-05-16 | **Sábado de clases — asistencia + reagendamiento + reconocimiento facial (13 commits).** (1) **Fix sábado corriente**: `_contexto_fechas()` excluía hoy si era sábado (>), ahora incluye (>=). (2) **Comando PRESENTE nombre**: marca asistencia individual. Si no tiene reserva, busca en NIÑOS FENIX, crea reserva automática y marca presente. PRESENTE PRUEBA busca en PRUEBA FENIX. (3) **Fix reagendamiento PRUEBA FENIX**: antes creaba registro nuevo sin nombre + 150mil. Ahora solo PATCH fecha/hora en existentes + notifica admin por WhatsApp (quién, de cuándo a cuándo). Guard en formulario previene duplicados post-redeploy. (4) **Reconocimiento facial en PRUEBA FENIX**: `registrar cara` busca en NIÑOS + PRUEBA. Al migrar con `cargar familia`, vincula PRUEBA→NIÑO (campo NINO FENIX linked record creado). (5) **Alerta reserva doble**: si Aurora intenta reservar niño que ya tiene otro turno ese día, alerta admin. (6) **Asistencia mejorada**: no muestra duplicados (inscripto > prueba), acepta nombres extra post-lista (crea reserva + presente), modo se cierra después de una carga. Match por palabras (todas deben estar, no substring). (7) **Campo AUSENTE**: checkbox en RESERVAS y PRUEBA FENIX. Lista muestra ✅/❌ si ya fue cargada. (8) **Correcciones Airtable manuales**: borrado registro basura Sixinio, actualizado 3 hijos a 23/mayo, Enzo Echeverz a 23/mayo, borradas reservas dobles Galeano, vinculados NINO FENIX para inscriptos existentes (Paula, Horacio, Tomas). |
| 2026-05-24 (sesión 2) | **PASO 2 MIGRACIÓN TOTAL: 11 tools + hooks — 4 commits.** (1) **Deploy Paso 1**: push a Railway de fix 3 bugs críticos (confirmar_reserva executor, escalar_a_humano tool, errores estructurados). (2) **Wave 1 — Ivan 2 tools nuevas + hooks**: `consultar_disponibilidad` (conteo niños por slot, privacidad), `programar_llamada` (extraído de main.py). Sistema hooks.py: PreToolUse (validar_fecha_hora valida sábado+futuro+hora, anti_escalacion_spam max 1/hora) + PostToolUse (notificar_telegram, enviar_capi_event). brain.py integra hooks en agentic loop (+context param). TOOLS_IVAN 3→5. (3) **Wave 2 — Aurora 6 tools (fin de regex)**: `agendar_clase` (crea RESERVA multi-hijo, detecta doble reserva), `cancelar_reserva` (por fecha+hora), `consultar_agendados` (lista con nombres), `registrar_familia` (crea/actualiza FAMILIA, deduce padre/madre), `registrar_hijo` (crea NIÑO vinculado), `escalar_a_humano` (compartido). TOOLS_AURORA creado (6 schemas). tool_executor 3→10 + resolver familia_id automático. main.py: Aurora recibe tools, 5 guards en bloques regex (si tool manejó la acción, regex no se ejecuta). prompts.yaml: sección HERRAMIENTAS en Aurora, regla "NUNCA escribas REGISTRO PADRE/HIJO". Regex queda como fallback con USE_TOOL_USE=false. |
| 2026-05-18 (sesión 2) | **Afiche hermanos (1 commit).** Nuevo detector `_padre_pregunta_hermanos()` (keywords: hermano/combo/plan familiar/2 hijos/3 hijos). Nueva función `_enviar_afiche_hermanos_y_followup()` envía `afiche_hermanos.png` + texto con descuentos exactos (Paq 5: 2do 30% OFF, 3ro 50% OFF; Paq 12: 2do 40% OFF, 3ro GRATIS 3x2). Hermanos tiene prioridad sobre afiche general en la intercepción. Si ya se envió, repite descuentos en texto sin reenviar imagen. Bug original: `_AFICHE_HERMANOS_PATH` estaba definido pero nunca se usaba, y Haiku confundía "2" (hijos) con "2 años" (edad). |
| 2026-05-24/25 | **PLAN INVIERNO + refactor prompts + tools — 20+ commits.** (1) **Refactor prompt Ivan -39%**: de 8854→5379 chars. Tools integradas en cada fase del flujo (no en bloque separado). Eliminado concepto "papá entrena". Basado en best practices Anthropic (tool descriptions = prompt engineering, integrar en contexto no en lista). (2) **Plan Invierno**: precios nuevos (prueba 100k, mensual 300k, +50k por hermano), eliminados paquetes 5/12 clases y promo 2 sábados. Horarios invierno: solo 11:00 y 15:30 (9:30 eliminado). Mensaje apertura nuevo (texto emocional largo). Afiches nuevos. 13 archivos actualizados. (3) **Aurora de 7 tools a 4**: eliminadas consultar_agendados (ya en contexto), registrar_familia y registrar_hijo (admin/onboarding). Quedan: agendar_clase, cancelar_reserva, reagendar_reserva, escalar_a_humano. (4) **reagendar_reserva**: tool única que cancela vieja + crea nueva en una llamada (Haiku no hacía 2 pasos secuenciales). (5) **Eliminado bloque HERRAMIENTAS** de ambos prompts (confundía a Haiku, generaba respuestas truncadas). (6) **Fix reservas pasadas**: filtro IS_AFTER en Airtable + doble check Python + timezone America/Asuncion (no date.today()). Caso Victor Quiñonez: mostraba reservas del 9 mayo como activas. (7) **Fix Airtable 422**: mapeo aurora→NIXIE en AGENT_ACTUAL de LEADS. (8) **tool_choice investigado**: auto (Haiku ignora), any (forzado pero rigid), regex detection (frágil). Pendiente: decidir approach definitivo. (9) **Datos bancarios simplificados**: ALIAS 1604338 / Banco Itaú / Ivan Lafuente. (10) **CTA actualizado**: "¿inscribirte de una o agendar prueba?" en vez de "sábado inolvidable". (11) **Follow-up horarios**: después del afiche "¿Te gustaría agendar un sábado?". (12) **Guías en Obsidian**: AGENTE FENIX ESTRUCTURA.md (arquitectura completa), GUIA TOOL USE ANTHROPIC.md (best practices + errores aprendidos). (13) **Menú Aurora**: 4 opciones (sin ver agendados), submenú agendar/reagendar/cancelar. Pendiente: Aurora determinística en código vs Claude con tools. |
| 2026-05-25 (sesión 2) | **QR CHECK-IN + TOOLS UNIFICADAS + FLUJO POST-PAGO — 14 commits.** (1) **QR Check-in**: `agent/qr.py` genera QR con logo FENIX en el centro (ERROR_CORRECT_H). Endpoint `GET /checkin/{record_id}` marca PRESENTE + HORA_CHECKIN en Airtable (busca en RESERVAS y PRUEBA FENIX). Campo HORA_CHECKIN creado en ambas tablas. (2) **gestionar_reserva (Aurora)**: 3 tools → 1 con param `accion` (agendar/reagendar/cancelar). Reagendar busca reserva actual en Airtable sola. `tool_choice` forzado por keywords + detección historial. (3) **gestionar_prueba (Ivan)**: 2 tools → 1 con param `accion` (confirmar/reagendar). `tool_choice` forzado por flag `modo_agenda` post-pago. (4) **Flujo determinístico post-pago**: después del pago, mensaje fijo con sábados de Airtable (sin Claude). `modo_agenda=True` fuerza tool. Se limpia al confirmar. (5) **Prompt Ivan invertido**: cobrar PRIMERO, agendar DESPUÉS. FASE 3 = datos bancarios, no horarios. (6) **Reservas Airtable en mensaje del usuario**: datos de reservas inyectados en el user message (no system prompt) para que Haiku los priorice sobre historial. (7) **Fix ARRAYJOIN con record links**: no funciona con multipleRecordLinks, cambiado a lookup texto FAMILIA. (8) **QR para leads post-formulario**: QR se envía después de crear PRUEBA FENIX (cuando registro existe), no post-agenda. (9) **Carpeta marketing/**: logos, afiches, anuncios, caricaturas, docs. Logo excluido de .gitignore para Railway. (10) **Notificaciones**: solo Telegram (no WhatsApp admin), con iconos ✅/🔄/❌ por acción. (11) **Guía maestra**: COMO ARMAR TOOL AGENDAS - QR - AIRTABLE.md en Obsidian (17 errores + solución completa). (12) **AIRTABLE ERRORES.md**: 6 errores documentados (ARRAYJOIN, IS_AFTER, 422 silencioso, select case-sensitive, base equivocada, suponer datos). |
| 2026-05-06 (sesión 2) | **Notificaciones WhatsApp + orden afiche + monto correcto (5 commits).** (1) **Link Telegram en notificaciones WhatsApp**: todas las notificaciones al admin (pago, reserva, agenda) ahora incluyen `💬 t.me/c/{gid}/{topic_id}` para ir directo a la conversación en Telegram. Antes solo llegaba wa.me. (2) **Afiche primero**: cuando FENIX envía precios, el orden era texto de Claude → afiche → msg_precios (duplicado). Ahora: afiche → msg_precios (hardcoded). La respuesta de Claude se omite porque el afiche ya cubre todo. (3) **RESERVA COMPLETA con datos reales**: la notificación mostraba "Lead" y "hijo/a" vacíos porque usaba regex simple. Ahora usa `extraer_datos_formulario` (Haiku) que ya corrió — llega con nombre padre + nombre(s) hijo(s). (4) **Notificación agenda corregida**: el link wa.me decía "me contó Aurora" para leads de FENIX. Ahora usa "te saluda el profe Ivan" cuando `agente=ivan`. Fallback "alumno" eliminado. (5) **`monto_prueba_por_hijos` reescrito**: antes adivinaba contando líneas con "X años" en el historial (bug: "desde los 3 años" + "tiene 2 años" = 2 hijos = 120K). Ahora lee el monto que FENIX confirmó en la conversación ("Transferencia: 90.000 Gs", "Prueba 2 hijos: 120.000", "90mil Gs"). Fallback 90K. |
| 2026-05-25 (sesión 3) | **Auditoría completa post-migración + comparación Dorita + MIGRACIÓN VERIFICADA (0 commits código).** Sesión de documentación pura. Ivan confirmó que el flujo completo end-to-end fue testeado y funciona correctamente — migración oficialmente completada. (1) **FENIX VS DORITA 25-5-26.md**: auditoría comparativa de ambos proyectos — Fenix completó migración (31 módulos + 8 tools + hooks + concurrencia + night mode), Dorita sigue monolítica (main.py ~65K, solo 2 tools, sin concurrencia ni detectores separados). Pendientes prioritarios de Dorita documentados (P0/P1/P2). (2) **AUDITORIA FENIX POST MIGRACION 25-5-26.md**: documento completo del estado actual — arquitectura antes/después, flujos detallados (webhook 13 pasos, pago 8 pasos, Aurora), comparativas de costo (95% ahorro), latencia, confiabilidad, cronología de 12 commits de migración en 5 fases, 10 lecciones aprendidas + 8 errores documentados, diagrama de dependencias, métricas del sistema. |
| 2026-05-26 (sesión 2) | **MONITOR + GUARDIAN + AGENT BLUE — 1 commit código + 1 commit cursos-ia.** (1) **Monitor interno (Capa 1)**: nuevo `agent/monitor.py` con 2 loops asyncio (conversaciones sin respuesta >10 min + salud: DB, 10 detectores, prompts.yaml, background tasks, errores webhook). Integrado en main.py (lifespan + error tracking). Alerta por Telegram, "Todo OK" 3x/día. (2) **Guardian remoto (Capa 2)**: RemoteTrigger `trig_01TkNS1SPNn6T7G9hhLyvkEK` cada 1h, Sonnet 4.6, 6 checks (detectores, prompts.yaml, migraciones, imports, endpoint prod, monitor.py). Reporta a Telegram. (3) **Guardian Dorita actualizado**: ahora reporta a Telegram (antes solo en claude.ai/code). (4) **Grupo Telegram dedicado**: `-5137950629` para ambos monitores y guardians. Env var `TELEGRAM_MONITOR_GROUP_ID`. (5) **Prompt fundacional Agent Blue**: 427 líneas en cursos-ia, enseña a Agent Blue a implementar agent-skills + monitor/guardian + generar contenido de curso. (6) **Cierre mejorado**: paso "nombrar sesión" con 3 sugerencias agregado al /cierre. |
| 2026-05-26 (sesión 3) | **Fix detectores afirmativos + cierre FASE 3 + supergrupo Guardian — 2 commits.** (1) **Fix _padre_muestra_interes**: 31 de 34 variaciones afirmativas no matcheaban (anchors `^sí$` exigían texto exacto). Lead 595981101080 dijo "si si a que hora seria" y ningún detector capturó → Claude agendó sin cobrar. Reescrito con set de exactos (limpian puntuación) + patrones flexibles (si si, sii, dale!, sip, yes, claro!, si porfa, etc). (2) **padre_pregunta_horarios**: agregado "a que hora", "a qué hora", "que hora" (variaciones reales que no matcheaban). (3) **Prompt FASE 3**: cierre con "Quedo atento." en vez de "¿Dale?" (imperativo). Prohibición explícita de "¿Dale?", "¿Va?", etc. (4) **THE GUARDIAN supergrupo**: grupo convertido a supergrupo con topics, nuevo ID -1003834000116 (antes -5137950629 era grupo normal, topics no funcionaban). Topic "Monitor FENIX" creado (thread_id=7). Env var TELEGRAM_MONITOR_GROUP_ID actualizada localmente. Pendiente: actualizar en Railway. |
| 2026-05-26 (sesión 4) | **Fix PRUEBA FENIX + QR tracking + auditoría + migración docs — 5 commits.** (1) **Fix datos faltantes PRUEBA FENIX post-formulario**: cuando lead pagaba antes de llenar formulario, PRUEBA FENIX se creaba sin nombre padre/apellido hijo/fecha nac. El guard "ya existe" abortaba sin actualizar. Ahora extrae datos con Haiku y patchea campos vacíos. QR también se envía en este flujo (antes se perdía). (2) **Campos QR en Airtable**: `QR RESERVA` (url) + `QR ENVIADO` (checkbox) creados por API en PRUEBA FENIX y RESERVAS FENIX. Al enviar QR se marca automáticamente. (3) **Endpoint `/enviar-qr/{telefono}`**: genera y envía QR como imagen PNG. Param `?destino=` para preview sin marcar. Espejo Telegram "QR Reserva enviado" en los 3 puntos de envío. (4) **Script auditoría `scripts/auditoria_flujo.py`**: audita todos los leads con datos bancarios — checks modulares de flujo (datos→pago→agenda→formulario→QR) + completitud Airtable (12 campos). Output terminal + JSON. Primera ejecución: 64 leads, solo 1 completo (Víctor Meza). (5) **Migración docs Obsidian → repo git**: 28 docs movidos de IVAN VAULT a `docs/`. Se deja de usar Obsidian para este proyecto. Conversaciones (datos leads) a Google Drive. (6) **Guía profesional**: GUIA AUDITORIA WHATSAPP.md con arquitectura, patrones, referencia campos. |
| 2026-05-28 | **Limpieza y organización del proyecto — 5 commits.** (1) **QR masivo**: 65 PRUEBA FENIX históricos marcados como QR ENVIADO en Airtable (script `scripts/marcar_qr_masivo.py`). (2) **Ordenar raíz**: docs sueltos movidos a `docs/` (CHECKLIST, MIGRACION TOTAL, SISTEMA_SEGUIMIENTOS, conversaciones_fenix). Datos a `data/` (phones, contactos) y `data/nombres/` (5 archivos). 9 JSONs de followup a `data/followup/`. 6 duplicados borrados (ya estaban en docs/). (3) **Archivos muertos del template borrados**: LICENSE (no era de Ivan), start.sh, Dockerfile, docker-compose.yml (deploy es Railway, no Docker). (4) **Referencias actualizadas**: /cierre apunta a `docs/FENIX_RESUMEN.md`, memorias checklist y yosoyfenix apuntan a `docs/`. (5) **.env.example actualizado**: de 14 a 21 variables, refleja el estado real (Telegram, AWS, Groq, etc.), borradas secciones Whapi/Twilio sin uso. (6) **Prompt START para curso IA**: creado `prompt-start-curso-ia.md` en cursos-ia/ — instalador de herramientas (Git, Python, Node, VS Code, Claude Code, LICENSE) que el alumno corre ANTES del prompt maestro. Raíz del proyecto queda solo con: CLAUDE.md, CLAUDE.local.md, README.md, requirements.txt, .env. |
| 2026-05-25 (sesión 4) | **Sesión operacional — Airtable + export + organización Vault (0 commits código).** (1) **Correcciones Airtable manuales**: Maria Natalia Fernández (595983957781) reagendada 23→30 mayo. Max Lee (595992247697) segundo pago 90mil creado en PRUEBA FENIX + PAGOS para 23/5. Sixinio Acuna 3 hijos reagendados de 23→30 mayo 11:00h. Marcelo Saucedo (595994468797) hora cambiada de 11:00→15:30 para 23/5. (2) **Export conversaciones masivo**: descargadas 1165 conversaciones de Railway, generados 13 archivos .md (13-25 mayo) en CONVERSACIONES FENIX/. all_phones.txt actualizado a 1167 teléfonos. (3) **Organización Vault Obsidian**: 25 .md sueltos organizados en 5 carpetas (guias/, operaciones/, marketing/, estado/, sesiones/). MOC actualizado con links a nuevas rutas. (4) **Análisis de conversaciones 22-23 mayo**: identificados reagendamientos de Jacqueline (sin pago, pendiente) y Marcelo (actualizado). |
| 2026-05-30 (sesión 7 — fix lluvia + carga pagos) | **Fix prompt lluvia + sesión operacional Airtable (1 commit código `5d1a572`).** **(1) Fix prompt lluvia**: el prompt decía "bajo techo en La Casona, 3000m2" — falso, los 3000m2 son el parque al aire libre, lo cubierto es la mansión (~300m2). Una clienta (Leticia) recibió esa info equivocada y se confundió con lugar/horario. Corregido a "si llueve, entrenan dentro de la mansión" ([config/prompts.yaml:36](../config/prompts.yaml#L36)). **(2) Bug detectado (NO arreglado, va con menú interactivo)**: `detectar_tipo_pago()` ([agent/pagos.py:202](../agent/pagos.py#L202)) clasifica el tipo de pago por **keywords del mensaje** (`_KEYWORDS_INSCRIPCION`), no por estado del lead. Una mensualidad ("abonar la mensualidad") cae al default `"prueba"` → carga monto de prueba (100mil) y dice "agendamos tu clase de prueba". Fix correcto: detectar por estado (si ya tiene PRUEBA con PAGO → siguiente pago es mensualidad). **(3) Carga operacional Airtable** (5 endpoints analizados, pagos del día que no se procesaron bien): Edith Guerrero (mensualidad 230mil → registro F.MENSUAL INSCRIPTO en PRUEBA FENIX + PAGOS); César Méndez (PAQUETE5 350mil → PRUEBA FENIX + PAGOS); Johanna Britez (prueba 120mil 2 hijos Gastón+Danna, reserva+pago+formulario, nunca se proceso → 2 registros PRUEBA FENIX + PAGOS); Lee Jun Yob/Max (3era prueba 90mil → PRUEBA FENIX + PAGOS). **(4) Devolución Leticia Paredes**: le devolvieron 150mil → asiento **−150.000** con concepto DEVOLUCION en PAGOS (dejando el +150.000 original como rastro, neto 0) + las 2 pruebas marcadas CONVERSION=CANCELADO. **(5) Opciones Airtable nuevas**: `F.MENSUAL` (concepto en PRUEBA FENIX), `DEVOLUCION` (concepto en PAGOS). **(6) Patrón de carga aprendido**: cada pago va a PRUEBA FENIX (reserva/concepto) **y** a PAGOS (asiento, vinculado al registro de PRUEBA FENIX vía campo PRUEBA FENIX), método TRANSFER, estado PAGADO, fuente FENIX KIDS ACADEMY. |
| 2026-05-28 (sesión 6 — QR familia) | **QR fijo por familia + check-in de asistencia individual — 3 commits (`77ad368`, `ef0adc0`, `269096d`).** Rediseño del check-in: en vez de un QR por hijo (con hermanos llegaban 2-3 QR), ahora **un QR por grupo** que abre una página con todos los hijos y un botón presente/ausente por cada uno (toggle: marcar crea fila, desmarcar la borra — para corregir errores). **(0)** Nueva tabla **ASISTENCIA FENIX** (`tblFZmAcw6X54kdGW`): fuente única de asistencia, separa "intención" (reserva) de "hecho" (vino). Campos: REGISTRO, NIÑO→NIÑOS, PRUEBA→PRUEBA FENIX, FAMILIA, FECHA, HORA_CHECKIN, TURNO, MÉTODO (QR/MANUAL), RESERVA, TELEFONO. Una fila = un niño presente en un sábado. **(1)** Fase 1 inscriptos: `GET /checkin/familia/{familia_id}` + `POST .../toggle/{nino_id}`, `generar_qr_familia()`, `crear_asistencia`/`borrar_asistencia`/`obtener_asistencias_ninos_fecha` en airtable_client, endpoint admin `/enviar-qr-familia/{telefono}`. Validado en prod (1 y 2 hijos). **(2)** Logo FENIX en la página (servido desde `/static/logo-fenix.png`, optimizado a 52KB). **(3)** Cobertura leads en prueba: render generalizado (`_render_checkin_lista_html`), `GET /checkin/prueba/{telefono}` agrupa hermanos en PRUEBA FENIX, `obtener_asistencias_pruebas_fecha`, `generar_qr_prueba`, admin `/enviar-qr-prueba/{telefono}`. Validado en prod (2 hermanos). Todo aditivo: el `/checkin/{record_id}` viejo y el envío automático de QR siguen intactos. **Aprendizaje**: el envío a un número fuera de la ventana de 24h de Meta da `enviado:true` (status 200) pero no entrega — se confirmó abriendo la ventana. Pendiente Fase 2 (comando "QR"), sub-fase (migrar envío automático a QR nuevos), Fase 3 (apagar lo viejo + migrar histórico de PRESENTE). |
| 2026-06-21 | **Colapso de identidad triplicada: PRUEBA FENIX → FAMILIAS (Fases 0-1-3).** Sesión de rediseño de datos. Diagnóstico: el desorden real NO era padre/madre dentro de FAMILIAS, sino la misma familia viviendo 3 veces (LEADS + PRUEBA FENIX + FAMILIAS) — la "identidad triplicada" del council 2026-06-02. **Fase 0 (medición)**: 75 PRUEBA, 42 FAMILIAS (solo 2 con ESTADO PLAN seteado), 61 PAGOS FENIX de los cuales **59 colgaban de PRUEBA FENIX**. PAGOS es tabla COMPARTIDA con Salsa (campos DORITA/ACCESO SSS, links ALUMNOS/RESERVA LEADS) → todo repunte filtra `FUENTE=FENIX`. **Fase 1 (deploy, commit `32d762f`)**: completado el dual-write de FAMILIA(A PRUEBA)+NIÑO en formulario post-pago y promo madre de main.py (antes solo lo hacía `/agenda` en flujo_pagos.py). Al pagar la prueba ahora se crea/reusa la familia con `crear_familia_a_prueba`, aislado en try/except (nunca rompe el pago). Deploy verificado (arranque limpio). **Fase 3 (migración histórica, script `scripts/migrar_prueba_a_familia.py`)**: migrados los 62 PRUEBA sueltos → 38 familias nuevas (A PRUEBA, madre/padre por `deducir_genero` + 7 overrides manuales: Luis Peralta=padre; Milagros/Ruth/Nancy/Solange/Edith/Dirse=madre), 51 niños (duplicados consolidados: Lee Jun 4→1), 60 PRUEBA linkeadas, 45 pagos repuntados a FAMILIA FENIX (**0 pagos de Salsa tocados**). Cancelados (3) y reservas históricas excluidos por decisión. Backup JSON en `backups/`. Idempotente y verificado: **FAMILIAS 42→80**, dry post-migración da 0 candidatos. **PRUEBA FENIX sigue intacta** (no se borró). **Aclaración clave**: Aurora es UN agente que atiende SIEMPRE en modos (leads/familia), como Dorita — no hay dos agentes que se pasan la conversación; el estado define el MODO, no quién atiende. **Pendiente (Fase 2/4)**: rediseñar el check-in/QR de cero directo sobre FAMILIAS+RESERVAS (Ivan confirmó que el QR actual no se usa y se rehará), y recién ahí eliminar PRUEBA FENIX + repuntar el resto. |
| 2026-06-21 (sesión 2) | **Arranque de la migración estructural completa: plan aprobado + Fase A1.** Iván pidió terminarla: FAMILIAS como única ancla, **tabla TUTORES** nueva (padres salen de adentro de FAMILIAS), **PRUEBA FENIX eliminada**, todo conectado. Check-in nuevo (lector facial + push del viernes) queda aparte/después. Plan aprobado (en `~/.claude/plans/parallel-strolling-rivest.md`): 2 ejes, cada uno expand→migrate→contract, nunca big-bang. **EJE A** elimina PRUEBA mudando las reservas a RESERVAS FENIX (decisión de Iván vs congelar); **EJE B** crea TUTORES y toca el webhook "quién escribe" (corre en cada mensaje = máximo riesgo → va segundo y aislado). **Fase A1 implementada (commiteada, SIN pushear aún)**: `confirmar_reserva_prueba`/`reagendar_clase` ([tools/reservas.py](../agent/tools/reservas.py), commit `633b33b`) y el formulario post-pago ([main.py](../agent/main.py), commit `f36bd2e`) ahora, además de escribir PRUEBA, **crean la RESERVA FENIX real** reusando `gestionar_reserva` de agenda.py (dual-write, aislado en try/except, idempotente). Pendiente: deployar A1 + verificar; luego A2 (mover lecturas asistencia/resumen/inscripción a RESERVAS+FAMILIAS), A3 (migrar histórico + sacar `crear_prueba_fenix` + borrar PRUEBA), y EJE B (TUTORES). |
| 2026-06-02 (sesión 8 — limpieza conceptos pago) | **Análisis de arquitectura del holding + limpieza del Frankenstein de conceptos de pago Fénix (1 commit código `957a250`).** **(1) Council + diseño**: sesión larga de análisis del "universo Iván Lafuente" (9 negocios: Salsa, Fénix, Curso IA, ventas PC, Alma Latina, Mamba Basket, Uber, casona, facturación Líder). Se corrió un LLM Council (5 advisors + peer review + chairman) sobre el rediseño de datos → veredicto: modelo Personas+Ventas+Pagos correcto pero NO rediseñar el holding ahora; quedarse en Airtable (no migrar a Postgres); foco quirúrgico solo Fénix. Artefactos en `COUNCIL/` (transcript + HTML). **(2) Diseño Fénix**: validado modelo de 2 tablas (LEADS=funnel efímero 1170 regs + FAMILIAS=clientes con niños/pagos), estado de embudo en LEADS y de cobranza en FAMILIAS, pago por FAMILIA (no por niño: el plan ya depende de #hijos+frecuencia). **(3) Backup**: snapshot de 5 tablas (2.164 registros) en `backups/` (gitignored). **(4) Limpieza CONCEPTO de pagos (solo Fénix)**: el campo CONCEPTO en PAGOS era un Frankenstein de 40 opciones que mezclaba negocio+monto+tipo (F.PRUEBA 90MIL, F.MENSUAL250, F.TRI 690, PAQUETE5/12, PRUEBA NHIJOS). Re-cableados 5 archivos (`inscripcion.py`, `flujo_pagos.py`, `main.py`, `airtable_client.py`, `resumenes.py`) para escribir genéricos: **PRUEBA / CLASE / MENSUAL / TRIMESTRAL / MATRICULA**. El negocio queda en FUENTE, el monto en MONTO. Eliminado el parche `_MONTOS_CONCEPTO` de resumenes.py (el campo MONTO ya trae el valor real). FENIXMAMA se mantiene (tiene lecturas en `resumenes.py:1535` y `main.py`). **(5) Migración de datos**: 49 pagos históricos Fénix migrados a genéricos (46→PRUEBA, 2→TRIMESTRAL, 1→CLASE), verificado 0 conceptos viejos restantes en FUENTE=FENIX. **(6) Opción nueva**: `CLASE` agregada al select CONCEPTO (Ivan, UI). **Aprendizaje**: `_post`/`_patch` NO usan typecast → Airtable rechaza valores de select inexistentes; verificar SIEMPRE que la opción destino exista antes de escribir/migrar. **(7) Fase 2 arrancada** (commits `4771bd6` + `7a00032`): plan completo del refactor "sacar PRUEBA FENIX" en `docs/guias/PLAN FASE 2 - SACAR PRUEBA FENIX.md` (4 sub-fases incrementales). Ejecutado **2.A paso 1 (router)**: helper `familia_es_activa()` en airtable_client.py — Aurora se activa solo si la familia NO está en estado `A PRUEBA` (ACTIVO/PAUSADO/BAJA/vacío → Aurora sin cambio; A PRUEBA → sigue Ivan). Aplicado en router principal (main.py:3204), modo nocturno (3139) y grupo Telegram (2800). Opción `A PRUEBA` agregada al select ESTADO PLAN. Deployado, comportamiento actual idéntico (no hay familias A PRUEBA aún). Hallazgo clave: crear familia al pagar la prueba dispara el router → por eso 2.A arregla el router ANTES de tocar el flujo de pago. Pendiente 2.A paso 2: crear familia A PRUEBA al pagar la prueba (flujo_pagos.py + inscripcion.py). |
| 2026-06-02 (sesión 9 — Fase 2.A paso 2: familia A PRUEBA al pagar) | **Ejecutado 2.A paso 2 del refactor "sacar PRUEBA FENIX" — 2 commits incrementales.** Objetivo: que el lead que paga/agenda la prueba se materialice como **FAMILIA en estado A PRUEBA + NIÑOS** (dual-write: PRUEBA FENIX se sigue creando por ahora), sin romper el router (que ya quedó listo en paso 1). **Deploy 1 (`f22c3db`) — `inscripcion.py`**: `_ejecutar_inscripcion` ahora hace `buscar_familia_por_telefono` ANTES de crear; si la familia ya existe (de la prueba) la reutiliza y la promueve a ACTIVO en vez de crear una duplicada, con dedupe de NIÑOS por nombre (linkea PRUEBA→NIÑO y migra cara al niño existente). No-op al momento del deploy (todavía no hay familia en la prueba) → comportamiento idéntico, prepara el terreno. **Deploy 2 (`8c60931`) — `airtable_client.py` + `flujo_pagos.py`**: nuevo helper `crear_familia_a_prueba(telefono, padre, ninos)` (busca/reutiliza, si no crea FAMILIA con ESTADO PLAN=A PRUEBA + niños + vínculo al lead, no duplica); se llama en `_cerrar_agenda_desde_telegram` tras crear PRUEBA FENIX, en try/except (nunca rompe el flujo de pago), aplica al caso pagado y al `gratis`. Además `obtener_familias_inscriptas` ahora excluye A PRUEBA (guarda contra broadcasts de contenido_social — la función dice "inscriptas" y A PRUEBA no lo es). Verificado en Airtable que la opción `A PRUEBA` existe exacta en el select ESTADO PLAN (sin typecast falla silencioso). Ambos deploys: health check prod 200, app arranca OK. **Pendiente próxima sesión: verificación funcional en vivo** del ciclo completo con número de test (/agenda → FAMILIA A PRUEBA → sigue Ivan → inscripción → ACTIVO → Aurora). Sigue Fase 2.B (migrar evento de prueba a RESERVAS+ASISTENCIA). |
| 2026-06-05 (sesión 10 — token Meta + monitor 401 + endpoint reset) | **Incidente "Aurora no responde" diagnosticado + 2 fixes — 2 commits.** **(1) Diagnóstico del incidente (ops, sin commit)**: Aurora dejó de responder a los papás (`401 code 190 OAuthException` en todos los envíos a Meta). Causa raíz: NO era el token — Ivan ya lo había renovado bien (System User, nunca expira, app FENIX KIDS 2026 correcta, verificado con `debug_token`). El problema: **cambiar `META_ACCESS_TOKEN` en Railway no reinició el proceso** de Fénix, que siguió usando el token viejo en memoria (`os.getenv` se lee una sola vez al arrancar). Dorita sí se reinició sola, Fénix no → por eso Dorita anduvo y Fénix no. Resuelto con restart manual del servicio; verificado con envío directo a Meta (200) y `/test-envio` del proceso vivo (`enviado:true`). **(2) Fix monitor 401 (`c20f1c3`)**: el monitor reportaba "Todo OK" aunque `enviar_mensaje` devolviera False con 401 — el fallo solo se logueaba, no se registraba donde el monitor lo viera. Agregado `meta_send_errors` + `registrar_error_meta()` + `_contar_errores_meta()` en `monitor.py`; el loop de salud detecta los 401 y alerta "🔴 TOKEN META MUERTO — renovar en Railway y reiniciar". Helper `_registrar_fallo()` (import perezoso, sin circular) en los 6 métodos de envío de `providers/meta.py`. Probado end-to-end con token inválido. Limitación: chequeo cada 1h (techo de aviso ~1h). **(3) Endpoint `/reset/{telefono}` (`fde871b`)**: nuevo endpoint admin `POST` que ejecuta reset total remoto (`eliminar_todo_de_telefono` + `limpiar_estado_completo`) con `X-ADMIN-KEY`, sin que la persona escriba `holayosoyfenix`. Ejecutado para `595982844548` (número de prueba de Ivan): 50 mensajes + lead borrados, número desde cero. El `familia_id` que mostraba `/debug` era un vínculo local huérfano (apuntaba a `recCDd7tDQavIdgOy`, familia ya inexistente en Airtable) — limpiado; búsqueda confirmó 0 familias asociadas. **Aprendizaje clave**: al renovar el token de Meta en Railway, SIEMPRE reiniciar el servicio (la variable sola no basta). |
| 2026-06-06 (sesión 11 — menú de botones leads + inscriptos) | **Sistema de botones interactivos estilo Dorita para leads y familias inscriptas — 11 commits incrementales (`971ce4a`→`c29bd3a`), todo verificado e idéntico para quien no usa botones.** **(1) Infra Meta (`971ce4a`)**: `enviar_lista()` + parseo de `list_reply` en `providers/meta.py` (antes solo `button_reply`). **(2) Menú de LEADS — módulo nuevo `agent/lead_menu.py`** (`f199f59`,`8e651b2`,`4515664`): el primer contacto del lead nuevo (agent_actual="ivan") reemplaza la FASE1 larga por **saludo cortado de Aurora + botones [📋 Info sobre clases][🎯 Agendar prueba][💬 Hablar con Aurora]**. "Info" → lista (Precios/Horarios/Ubicación/Agendar/Hablar). Navegación **100% por botones** hasta que toque "Agendar"/"Hablar con Aurora" (recién ahí entra el cerebro de ventas actual, branded Aurora — NO se renombró `ivan` internamente, solo lo visible). Precios/Horarios/Ubicación reusan los afiches/textos existentes y terminan con botones [Agendar][Hablar][Ver más info]. Texto libre antes de "Hablar" → insiste con botones. Enganche en `main.py` (~3252) con `return` temprano (sin duplicar envíos). **(3) Combo hermanos (`cd3ecb8`,`1f46b70`)**: botón tras Precios que muestra la tabla de precios por #hijos (se sacó la línea confusa "+50mil/+100mil por hermano" de Precios); sin afiche (estaba desactualizado), solo texto. **(4) `modo alumno` auto-familia (`b680c47`)**: `asegurar_familia_prueba_admin()` en airtable_client — si no existe familia para el admin, la recrea (Iván + hijo Mateo Lafuente, nac 2019-03-15) para que Aurora reconozca al inscripto y no pregunte "¿con quién tengo el gusto?". No toca el reset ni el router: `modo padre` sigue borrando todo (simula lead → menú), `modo alumno` garantiza familia (simula inscripto → Aurora). Familia de prueba creada también a mano en Airtable (`rec5vMDcySZwtXaZO` familia, `recnPfg02JLCxWh2M` niño Mateo, número admin 595982790407, ESTADO PLAN vacío = activa). **(5) Menú de INSCRIPTOS — módulo nuevo `agent/alumno_menu.py`** (`ddd4c4b`,`1f7a41f`,`0e4e171`,`c29bd3a`): familias inscriptas (Aurora cliente_inscripto) reciben botones en vez del menú numerado 1-4. **QR familia** → envía el QR fijo de la familia (`generar_qr_familia`) con caption de check-in (mismo QR siempre, para escanear al llegar y marcar presente). **Contenido Fenix** → nuevo `obtener_contenido_de_ninos()` (CONTENIDO FENIX donde aparecen los hijos, ordenado por FECHA, filtra por record_id en Python) + redes (`obtener_redes`). Se quitó "Agendar clase" (la dinámica cambia: Fénix va a empujar la confirmación de asistencia los viernes). El menú NO repite el botón recién usado: tras QR → [Contenido][Hablar con Aurora], tras Contenido → [QR][Hablar con Aurora]. Texto libre de inscripto → Aurora conversacional (pueden consultar). Enganche en `main.py` (~3285) tras resolver la familia. **(6) Diagnósticos (ops, sin commit)**: "Aurora no responde" al admin = estaba en **modo secre** (mensajes ignorados a propósito, main.py:2766); para probar como lead usar `modo padre`, como inscripto `modo alumno`. Confirmado por logs que el deploy levantó sano cada vez. **Aprendizaje**: los modos del admin (`_admin_modo_padre`) viven en memoria → cada deploy/reinicio los borra; probar después de terminar de deployar. **Pendiente**: feature "Fénix confirma asistencia los viernes" (hay scheduler de viernes para enganchar); verificación funcional en vivo del menú con números reales. |
| 2026-06-07 (sesión 12 — fix topics duplicados/rebotando en Telegram) | **Diagnóstico de por qué un mismo número abría varios topics en Telegram + 2 commits incrementales (`6050867`, `d4c7dde`), ambos deployados y verificados (health 200 + endpoint).** **Síntoma reportado por Ivan**: familias (Patricia Amarilla, Fernando Salla) y leads acumulaban 2-4 topics cada uno, con muchos mensajes "Fenix cerró el tema" del mismo número. **Causa raíz (verificada con grep + lectura, no asumida)**: (a) **Rebote entre grupos** — el grupo del topic se decidía con señales **volátiles** que cambiaban entre mensajes: `main.py:2832` usaba `"aurora" in texto OR familia_es_activa(_fam_tg)` (Airtable vivo). Mensaje sin "aurora", o Airtable lento/None, → grupo leads → `obtener_o_crear_topic` ve grupo distinto al guardado → cierra el topic viejo (`closeForumTopic` = "Fenix cerró el tema") y crea uno nuevo. Siguiente mensaje → vuelve a Aurora → migra de nuevo. Cada salto = topic nuevo visible + "cerró el tema". Además varios call sites (reset 2403, modo alumno 2726, hooks, night_mode) llamaban sin `group_override` → caían al default leads, botando familias fuera del grupo Aurora. (b) **Duplicados en mismo grupo** — `TopicTelegram.telefono` era `index=True` pero **no único**; webhooks duplicados de Meta + creación sin lock → dos filas/dos topics. **Commit 1 (`6050867`) — seguridad DB**: en `_migrar_columnas_nuevas` (memory.py) dedup de filas existentes por teléfono (queda la de id más alto, SQL distinto Postgres/SQLite) + `CREATE UNIQUE INDEX` en telefono (best-effort, no tumba arranque). En telegram_bridge.py los dos inserts (creación + recreación) capturan `IntegrityError`, re-consultan y usan el topic que ganó la carrera. **Commit 2 (`d4c7dde`) — decisión de grupo única**: nueva `grupo_telegram_para(telefono)` que lee el `agent_actual` **persistente de la DB** (el mismo valor que decide prompt/tools/menú, vía `obtener_agent_actual` de ab_test) → aurora=FLIAS, ivan/default=LEADS. `obtener_o_crear_topic` la usa como default cuando no recibe `group_override` (arregla reset/alumno/hooks/night_mode de un saque). En main.py se reemplazó el cálculo volátil de 2832 por `await grupo_telegram_para(telefono)`. Así el grupo no depende del texto ni de Airtable vivo → no rebota; queda alineado con cómo se atiende al número. La migración leads→Aurora ahora ocurre **una sola vez** (transición real lead→familia), no en bucle. **Verificación**: asserts del mapeo (aurora→FLIAS, ivan/default→LEADS, fallback sin FLIAS→leads), `from agent.main import app` OK en ambos commits, health prod 200 estable post-deploy, `/debug` protegido responde. El `/debug` del admin confirmó el diagnóstico en vivo: `agent_actual: aurora` pero `topic.group_id: 0` (leads) — exactamente la inconsistencia que el fix corrige en el próximo mensaje. **NO se pudo verificar visualmente la DB** (no hay endpoint SQL) ni observar una migración en vivo (requiere mensaje entrante real). **Limitación honesta**: los topics ya cerrados que quedaron en Telegram NO se borran (limpieza manual en la app si Ivan quiere); el fix solo frena que se sigan creando. **Pendiente**: test en vivo — Ivan manda "Hola" desde su cel (595982790407, que es Aurora) → confirmar que el topic migra una vez a FLIAS y que un 2do mensaje NO rebota. |
| 2026-06-13 (sesión 14 — fix agendar HOY + automatización horarios + carga pagos + diagnóstico flujo pago) | **2 commits de código deployados + diagnóstico de raíz del flujo de pago + cargas manuales. Disparado por `/endpoint 595983191291` (Samuel): el agente rechazaba agendar el mismo sábado.** **(1) Fix agendamiento "venir HOY" (`1ab2f33`)**: causa raíz en `airtable_client.obtener_horarios_disponibles` — la fórmula `IS_AFTER({FECHA}, hoy)` excluía SIEMPRE los turnos del día actual, así que un lead que pedía venir el mismo sábado (con el turno todavía por delante) recibía "no hay cupo, próximo es el otro sábado", y el bot improvisaba horas/cupos inventados. El reloj andaba bien (el prompt inyecta hora PY correcta) — el bug era la tool dándole datos que contradecían al prompt. Fix: `NOT(IS_BEFORE({FECHA}, hoy))` = fecha >= hoy + hora PY real (no `date.today()` del server UTC). No filtra por hora: la persona elige 11:00 o 15:30. Verificado vs Airtable real. **(2) Automatización horarios mensuales (`98b76e1`)**: nace de que el 15:30 nunca se había cargado para varias fechas → se cargaban a mano y se olvidaban. `crear_horarios_mes(año, mes)` (sábados × [11:00,15:30], idempotente, no duplica) + loop `_horarios_mensuales_loop` (al arrancar asegura mes actual+siguiente tapando huecos al instante; corre el ÚLTIMO día del mes 9AM PY — robusto vs "día 30" que rompe en febrero — y crea el mes siguiente; avisa al admin por WhatsApp SOLO si creó turnos nuevos, anti-spam en reinicios). Registrado en lifespan + monitor. Verificado: al bootear logueó "junio 0 creados/8 existían, julio 0/8, próxima 30/6". Junio 27 + julio se cargaron en la prueba local. **(3) Diagnóstico de raíz "no cargó reserva ni pago" (sin commit, doctrina)**: `_procesar_comprobante` (pago automático) marca `CONVERSION=PAGO` pero NO crea reserva/PRUEBA FENIX/FAMILIA — eso solo lo hace el comando `/agenda`. Un lead que paga directo (manda comprobante sin pasar por /agenda) queda con el pago marcado pero huérfano. Confirmado con Samuel (PRUEBA=0, FAMILIA=0, solo LEADS.CONVERSION=PAGO). Además: la migración "SACAR PRUEBA FENIX" solo tiene hecha la sub-fase 2.A, y solo cableada en /agenda. **(4) Mapeo de tablas (read-only, MCP)**: PAGOS (compartida con Salsa) es el ledger real Fénix (`FUENTE='FENIX KIDS ACADEMY'`, ESTADO PAGADO, concepto PRUEBA/MENSUAL, links a PRUEBA FENIX/FAMILIA). Hay 3 tablas "leads" (LEADS FENIX del agente, RESERVA LEADS de Salsa con monto+método+PAGOS ya armados, LEADS staging). LEADS FENIX es 1 fila/teléfono → no puede absorber reservas/pagos per-niño/recurrentes. **(5) Carga manual de pagos (ops)**: Samuel 595983191291 (papá **Ronny Paez**, hijo Samuel) → PRUEBA FENIX 330k F.MENSUAL TRANSFER reserva 13 jun 15:30 + PAGOS 330k MENSUAL. Esteban 595995623883 (papá Esteban Echeverz, hijo Enzo) → 90k transfer (mayo, ya existía) + 90k efectivo (hoy) = 180k reales en PAGOS, PRUEBA método [TRANSFER,EFECTIVO] monto 180k, reserva corregida 23 may→13 jun. **Errores propios corregidos en vivo**: casi duplico el pago de Esteban (ya tenía el de mayo linkeado) y sobrescribí su método; verifiqué y reconcilié. **Pendiente grande próxima sesión**: PLAN de rediseño del flujo de pago — opción LEADS-como-centro (lo que pidió Ivan, choca con multi-hijo) vs relacional (que el pago automático haga lo de /agenda: FAMILIA A PRUEBA + RESERVA + PAGOS, tablas que ya existen). **Reglas aprendidas (memoria)**: antes de crear un pago verificar si ya hay uno linkeado; no cargar nombres a ciegas. |
| 2026-06-10 (sesión 13 — seguridad Fase 0: firma webhook + hardening) | **Replicada la "Fase 0" de seguridad ya probada en Dorita — 3 commits, deployados incrementalmente y verificados en vivo en prod. Cierra los 3 hallazgos de la auditoría sin tocar rate limit ni auth de debug (que Fenix ya tenía).** Antes de codear, leí la implementación de referencia en Dorita (`whatsapp-agentkit`): `verificar_firma()` en providers/meta.py y el check log-only en main.py. **(1) CRÍTICO — firma del webhook (`b1555ad`)**: el `POST /webhook` no validaba la firma HMAC `X-Hub-Signature-256` de Meta → cualquiera con la URL podía inyectar payloads falsos. Agregado `verificar_firma(body_bytes, firma_header)` en meta.py (HMAC-SHA256 con `META_APP_SECRET` + `hmac.compare_digest`; sin secret → warning y True, fail-open para no dejar mudo al agente). Llamado en el webhook leyendo `await request.body()` ANTES de parsear (Starlette cachea el body → el `request.json()` interno sigue andando). **Modo log-only**: loguea `[FIRMA-INVALIDA]` y procesa igual; rechaza 403 solo si `META_FIRMA_RECHAZAR=1`. Verificado con 6 asserts (fail-open, valida correcta, rechaza inválida/malformada/body-alterado). **(2) META_VERIFY_TOKEN (`c1f2c14`)**: sacado el default adivinable `"agentkit-verify"` → `""` + guard `if self.verify_token and ...` en `validar_webhook` (sin token configurado, la verificación GET se rechaza — fail-closed). **(3) ADMIN_PHONE (`fb3fe4e`)**: el número admin (con superpoderes) estaba baked-in como default de `os.getenv` en 22 sitios de 8 archivos → reemplazado por `os.getenv("ADMIN_PHONE", "")` (fail-closed, sin número en el código). **Infra (yo, vía Railway CLI)**: linkeé el proyecto FENIX (servicio fenix-kids-agent), confirmé que `ADMIN_PHONE` NO estaba cargada (el código usaba el default) → la cargué; cargué `META_APP_SECRET` (Ivan me pasó el valor) y borré una variable basura `META_APP_SECRETGracias.` (paste viejo con "Gracias." pegado en nombre y valor); activé `META_FIRMA_RECHAZAR=1`. **Verificación en vivo**: Ivan mandó "Hola" reales → procesaron con `200 OK`, **0 `[FIRMA-INVALIDA]`** y **0 `403`** con el rechazo ACTIVO → las firmas legítimas de Meta pasan, los forjados se rechazan. Webhook blindado. **Secuencia segura usada**: deploy en log-only → cargar secret (sigue log-only, valida de verdad) → verificar 0 fallos en logs → recién activar el rechazo. **Aprendizajes guardados en memoria**: tengo Railway CLI + Airtable MCP + GitHub conectados → miro la infra yo, no le hago recordar/preguntar a Ivan (`[[conexiones-y-herramientas-fenix]]`, `[[no-pedir-lo-que-puedo-mirar]]`). **Pendiente operacional**: si alguna vez se quiere volver a log-only, sacar `META_FIRMA_RECHAZAR`. |
| 2026-06-21 (sesión 17 — A1 deploy + EJE B/B1 completo TUTORES + B2 cimiento) | **8 commits, todo deployado y verificado (health 200). Migración estructural en marcha (plan parallel-strolling-rivest, expand→migrate→contract).** **(1) EJE A / A1 deployado (`633b33b`+`f36bd2e`, pusheados hoy)**: `confirmar_reserva_prueba`/`reagendar_clase` (tools/reservas.py) y el formulario post-pago (main.py) ahora crean la RESERVA FENIX real (dual-write reusando `gestionar_reserva`, aislado, idempotente). Falta verificación en vivo (log `[A1] Reserva real OK`). **(2) A2 datos = 0 trabajo**: `scripts/migrar_reservas_historicas.py` (dry-run) reveló 0 reservas vivas que migrar — las candidatas eran basura del parser de fechas sin año (empuja fechas pasadas a 2027). A1 ya cubre las futuras. Lecturas de asistencia/resumen NO se migran (Iván las va a rehacer con el lector facial). Script commiteado como herramienta (`563ed97`). **(3) EJE B / B1 (expand) COMPLETO** — colapsa los campos PADRE/MADRE embebidos a una tabla propia: tabla **TUTORES FENIX** (`tblYlRqpGqtQGyUJA`) creada vía MCP (NOMBRE/APELLIDO/APODO/CI/CELL/EMAIL/FECHA NACIMIENTO/PARENTESCO[Papá/Mamá/Tutor]/ES QUIEN PAGA/FAMILIA[link] + CELL LIMPIO y LINK CELL LIMPIO como fórmulas réplica EXACTA de FAMILIAS); migración `scripts/migrar_tutores.py` (`042ba45`) ejecutada → 104 tutores desde 80 familias, 47 quien-paga (CELL = TELEFONO de PRUEBA con pago), 0 duplicados, backup JSON, corregido dato corrupto "Víctor"; escritura dual (`13544f5`) — helper `crear_o_actualizar_tutor` llamado en `crear_familia` (cubre todos los flujos) y `registrar_familia`, idempotente (CELL LIMPIO+PARENTESCO+check id FAMILIA en código), aislado en try/except. **(4) EJE B / B2 arrancado**: helper de lectura `obtener_tutores_de_familia` con fallback a campos viejos (`6af1dac`, no-op probado camino normal+fallback); primera lectura migrada — saludo del menú inscriptos (`alumno_menu.py`) lee de TUTORES (`8cfce2a`). **(5) BUGS descubiertos**: `_get_records` NO pagina (trunca a 100) → duplicó tutores al re-correr la migración (limpiados); `ARRAYJOIN({link})` devuelve el nombre (primary), NO record_ids → no se puede filtrar links con FIND(id). Ambos en memoria. **Pendiente próxima sesión**: verificación en vivo A1 + escritura dual; seguir B2 con las lecturas CORE (buscar_familia_por_telefono, webhook quién-escribe, familia_es_activa) en deploys aislados + verificación en vivo; después A3/B3 (cortes). |
| 2026-06-23 (sesión 19 — B2 lookups/rollups Airtable + 4 consumidores core migrados + broadcasts desactivados) | **5 commits deployados, todos health 200 + arranque limpio.** Continuación EJE B (migrate). **(1) Infra Airtable — 7 campos nuevos, 0-fetch:** en TUTORES FENIX `NOMBRE COMPLETO` y `SALUDO` (formula apodo→nombre pila); en FAMILIAS FENIX los rollups `NOMBRES TUTORES`, `CELLS LIMPIOS TUTORES`, `SALUDOS TUTORES` (array, para lectura) + los campos formula plano `BUSCAR CELLS TUTORES` y `BUSCAR NOMBRES TUTORES` (para filterByFormula). Los rollups van en el registro de familia ya cargado → 0 GETs extra. **APRENDIZAJE TÉCNICO clave:** los rollups de Airtable devuelven array → `FIND`/`SEARCH` directos sobre el rollup en filterByFormula son INCONSISTENTES (matchean solo a veces, dan #ERROR en LEN/FIND). Hay que buscar sobre un campo FORMULA que coerce el rollup a texto plano (`{rollup} & ""`). Verificado con tests reales. La aggregation `ARRAYJOIN(values,...)` que pide la UI no se aplica como esperado (queda array igual) — por eso los campos BUSCAR. **(2) #1 topic Telegram (`e3c16cd`):** el nombre del topic deriva del tutor que escribió vía rollups (match por índice cells↔nombres con guarda de longitud, fallback primer tutor→FAMILIA). 0 fetch. **(3) Broadcasts desactivados (`5707ad7`):** Ivan decidió APAGAR los 3 loops de `contenido_social.py` (saludo diario 10am, aviso de posteo, recordatorio viernes) — se rearman desde cero en otra sesión. Comentadas las 3 `create_task` en `iniciar_contenido_social` (código intacto). Por eso #2 `obtener_familias_inscriptas` NO se migró (su código ya no corre). **(4) #3 `familia_es_activa` (`70b7cfd`):** ruteo cliente-vs-lead lee `NOMBRES TUTORES` en vez de NOMBRE PADRE/MADRE. Verificado: 0 diferencias de clasificación sobre las 80 familias. **(5) #4 `buscar_familia_por_telefono` (`f16b9f7`):** la búsqueda central (>20 call sites) usa `FIND` sobre BUSCAR CELLS TUTORES + guarda contra teléfono vacío. Análisis exhaustivo: 103/103 clientes reales reconocidos; único no encontrado = registro fantasma sin tutores (ya ruteaba como lead → impacto nulo); 0 cambiadas/espurias. **(6) #5 `buscar_familia_por_nombre` (`bdc2878`):** búsqueda fuzzy sobre BUSCAR NOMBRES TUTORES + scoring sobre rollup NOMBRES TUTORES; eliminada constante `_NORM_PADRE`; función no se invoca en prod (solo test_local). **Estado:** lecturas CORE de PADRE/MADRE migradas; quedan 42 refs = escrituras (B3) + #2 diferido + código a rehacer (asistencia/resúmenes/web). **Pendiente:** verificación en vivo #4; migrar #2 al rearmar broadcasts; B3 (quitar escrituras + borrar campos). |
| 2026-06-22 (sesión 18 — B2 lecturas a TUTORES + fix performance Aurora) | **3 commits, todo deployado y verificado en vivo (health 200 + /endpoint).** Continuación del EJE B (migrate: mover lecturas de PADRE/MADRE a TUTORES FENIX). **(1) Deploy 1 (`f67bb02`):** `_build_contexto_aurora` (main.py, contexto que arma Aurora en cada mensaje de inscripto) migrado a `obtener_tutores_de_familia` — quién escribe, bloque DATOS COMPLETOS y fallback de apellido para reservas. Verificado en vivo: Aurora saludó por nombre leyendo de TUTORES. **(2) Perf (`f31cfae`):** descubierto que el bloque "TOTAL AGENDADOS POR HORARIO" hacía 18 queries a Airtable EN SERIE (6 horarios × 3) ≈19s — el grueso de la latencia. Paralelizado con `asyncio.gather` + semáforo de 5 (rate limit Airtable; `_get_records` no maneja 429). Totales idénticos verificados. **Latencia de respuesta de Aurora medida en prod: 22s → 8s.** **(3) Deploy 2 (`53960be`):** saludo de WhatsApp (activación Aurora) + fallback de nombre de familia en agenda.py migrados a TUTORES. **Decisión clave:** los displays/búsquedas que corren en hot-path (topic Telegram, Grupo 2 = `buscar_familia_por_telefono`/`por_nombre`/`familia_es_activa`/`obtener_familias_inscriptas`) se dejan FUERA del helper para no sumar latencia — se resolverán con lookups/rollups en Airtable (datos de tutores pre-cargados en el registro de familia). Pendiente: diseñar los lookups → Telegram + Grupo 2 → luego B3 (quitar escrituras viejas + borrar campos). |
