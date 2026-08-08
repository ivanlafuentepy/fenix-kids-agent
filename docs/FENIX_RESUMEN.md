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
- **Activación:** por defecto en todo teléfono que NO es cliente activo (niño-eje: sin tutor en TUTORES FENIX con ≥1 hijo cuyo ESTADO ≠ A PRUEBA)
- **Frame:** PARQUE FENIX — experiencia al aire libre, naturaleza, superar miedos. NO hay menú de dolor ni evaluación.
- **Flujo:** nombre+edad → personalización por edad → propone prueba → precio → datos bancarios → comprobante → admin confirma → agenda automática post-pago → formulario → QR check-in
- **Cobrar PRIMERO, agendar DESPUÉS:** Ivan NUNCA ofrece horarios antes del pago. El agendamiento es automático post-confirmación del comprobante.
- **Tools (4):** gestionar_prueba (confirmar/reagendar), escalar_a_humano, consultar_disponibilidad, programar_llamada

### Aurora
- **Rol:** operaciones, consultas y reservas para familias inscriptas
- **Activación:** router niño-eje `es_cliente_activo_por_telefono` (airtable_client): TUTOR por CELL LIMPIO en TUTORES FENIX → cliente si ≥1 hijo con ESTADO ≠ A PRUEBA (vacío = cliente). Fallback legacy por FAMILIAS para fichas sin tutores/hijos linkeados.
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
1. Router detecta al tutor por teléfono (TUTORES FENIX) con un hijo activo → **Aurora** activa
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
| TUTOR FENIX | Link record | **(F7.b, `fldOaYMkJdtihJrj2`)** Tutor del lead — reemplaza el link FAMILIA en las altas niño-eje. Lo escriben `crear_grupo_a_prueba` (al pagar) y la inscripción |
| FAMILIA | Link record | **LEGACY** — vínculo a FAMILIAS FENIX. Ya NO se escribe en altas nuevas (F7.b); solo se lee en fallbacks legacy |
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

### Tabla FAMILIAS FENIX (⚠️ LEGACY — desde F7.b 14/07 las altas NO la crean; el eje es el NIÑO+TUTOR. Solo se lee en fallbacks; se archivará en F7.c)
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
| FAMILIA | Link record | Familia a la que pertenece (LEGACY — ya no se escribe en altas nuevas) |
| RESERVAS | Link records | Clases reservadas |
| LINK RESERVA | Formula | URL del formulario de reserva prefillado |
| **PADRE (ALUMNOS)** | Link → ALUMNOS | 🔄 07/08 — papá del niño. Antes era `PADRE` → TUTORES; los tutores se mudaron a ALUMNOS (ver nota abajo) |
| **MADRE (ALUMNOS)** | Link → ALUMNOS | 🔄 07/08 — mamá del niño |
| **ESTADO** | Select | 🆕 13/07 — ACTIVO/PAUSADO/BAJA/A PRUEBA (`fldayrwUxsXRwru8O`). Eje del router (es_cliente_activo) y de es_prueba. Vacío = cliente |
| **PLAN** | Select | 🆕 14/07 (F7.b, `fldNyWFtzD0NO48HC`) — SEMANAL/QUINCENAL × MENSUAL/TRIMESTRAL. El plan vigente vive en el niño (soporta hermanos con planes distintos). Lo escribe la inscripción |
| **PAGOS** | Link → PAGOS | 🆕 13/07 — inverso: los pagos que cubren a este niño |
| **VENCE EL** | Rollup | 🆕 13/07 — MAX del vencimiento de sus pagos |
| **AL DÍA?** | Formula | 🆕 13/07 — ✅ AL DÍA / ❌ VENCIDO (igual que en FAMILIAS, pero por niño) |

### ⚠️ Los TUTORES viven en ALUMNOS (desde 2026-08-07)

Los padres/madres **no** están en `TUTORES FENIX`: son filas de la tabla **ALUMNOS**
(compartida con Salsa Soul e Impulso IA) marcadas con `NEGOCIO = FENIX KIDS ACADEMY`.

| Tabla | Campo | Tipo |
|---|---|---|
| ALUMNOS | `HIJOS FENIX (PADRE)` / `(MADRE)` | Link → NIÑOS FENIX |
| ALUMNOS | `NEGOCIO` | multipleSelects — la opción `FENIX KIDS ACADEMY` marca al tutor |
| ALUMNOS | `TELEFONO LIMPIO` | Formula (595…) — reemplaza al viejo `CELL LIMPIO` |
| NIÑOS FENIX | `PADRE (ALUMNOS)` / `MADRE (ALUMNOS)` | Link → ALUMNOS |
| LEADS FENIX | `TUTOR (ALUMNOS)` | Link → ALUMNOS (creado 07/08; el viejo `TUTOR FENIX` quedó legacy) |
| PAGOS | `PAGA (ALUMNOS)` | Link → ALUMNOS (el viejo `PAGA` → TUTORES quedó legacy) |

Reglas duras que salen de esto:
- **La fila de ALUMNOS es COMPARTIDA** → un reset de Fenix **nunca la borra**: le quita la
  opción `FENIX KIDS ACADEMY` del NEGOCIO. Y al actualizar un tutor solo se completan campos
  vacíos: nunca se pisan datos de Salsa.
- **Nunca traer ALUMNOS entera** (es enorme): toda lectura masiva filtra por marca Fenix
  (`NEGOCIO` o `HIJOS FENIX (…)` no vacío).
- Un mismo teléfono puede tener **varias filas** en ALUMNOS → el match prioriza
  hijos-FENIX-linkeados > NEGOCIO=FENIX > ninguna (= no es tutor de Fenix).
- ALUMNOS **no tiene** `PARENTESCO` ni `ES QUIEN PAGA`: el parentesco se deriva de `GENERO`
  y el pagador cae al primer tutor con teléfono.

`TUTORES FENIX` quedó **LEGACY con dos usos vivos**: el `CODIGO` del link mágico del juego y
los datos de facturación (`FACTURA` + link `FACTURAS.TUTOR` que lee el robot facturador).
Sus campos `HIJOS (COMO PADRE)` / `(COMO MADRE)` son **texto** (no links) — leerlos como listas
fue el crash del 07/08.

### Tabla PAGOS (compartida con Salsa Soul — campos de FENIX)
| Campo | Tipo | Qué guarda |
|---|---|---|
| MONTO / CONCEPTO / METODO DE PAGO | — | El pago en sí |
| FUENTE | Select | ⚠️ NO es criterio confiable: hay pagos de FENIX con FUENTE='SALSA SOUL STUDIO'. El criterio real es tener FAMILIA FENIX |
| VENCIMIENTO PAGO | Formula | Vencimiento según el concepto |
| FAMILIA FENIX | Link → FAMILIAS | LEGACY — se va con la migración |
| LEAD FENIX | Link → LEADS | El lead que originó el pago |
| **NIÑOS FENIX** | Link múltiple → NIÑOS | 🆕 13/07 — **los hermanos que cubre UN pago**. Un pago familiar (340k por 2 hijos) se carga UNA vez y linkea a los dos: el monto NO se parte |
| **PAGA** | Link → TUTORES | 🆕 13/07 — el tutor que puso la plata (a quien se le factura) |

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

### Vigente desde el 2026-07-28 — el PACK reemplazó al mensual

**Clase de prueba (1 sábado):**
| Hijos | Precio |
|---|---|
| 1 hijo | 100.000 Gs |
| 2 hermanos | 150.000 Gs |
| 3 hermanos | 200.000 Gs |

Lógica: +50.000 por cada hijo extra. Solo transferencia bancaria. NO se descuenta de paquetes. NO hay devolución.

**Pack 5 clases — 5 sábados que NO vencen:** (sin matrícula)
| Hijos | Precio |
|---|---|
| 1 hijo | 350.000 Gs |
| 2 hermanos | 500.000 Gs |
| 3 hermanos | 650.000 Gs |

Lógica: +150.000 por cada hijo extra. Las clases **no vencen**: la familia las usa cuando quiere y se descuenta una por visita. Comprar otro pack **suma** sobre el saldo (le quedaban 4 + compra 5 = 9).

El saldo vive en `NIÑOS FENIX.CLASES DISPONIBLES`; se descuenta en el check-in y se recarga al pagar (`descontar_clase` / `recargar_pack` en `airtable_client.py`). **Campo vacío = familia del plan mensual viejo**, que sigue con su esquema aparte y no se le descuenta nada. El PAGO del pack usa `CONCEPTO=PAQUETE5`, que la fórmula `VENCIMIENTO_FORMULA` no contempla → queda sin vencimiento, como corresponde.

**Plan mensual (4 sábados, 240.000 Gs — HISTÓRICO):** ya no se vende. Las familias que lo tenían siguen con él (decisión de Ivan, 28/07).

**Matrícula anual: 100.000 Gs POR NIÑO** (cambio 2026-06-24: antes era "una vez por familia"). Se suma una sola vez al inscribirse → 1 hijo +100k, 2 hermanos +200k, 3 hermanos +300k.

**Edad: 4 a 12 años** (cambio 2026-06-24: antes 3). Menores de 4 (2-3) pueden venir a probar, pero NO se aceptan si necesitan asistencia personalizada 1-a-1; deben moverse de forma independiente en el grupo — depende de cada niño.

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
| `TELEGRAM_WEBHOOK_SECRET` | ✅ Configurada | Secret token del webhook de Telegram (auditoría 04/07): Telegram lo manda en cada update y `/telegram/webhook` rechaza 403 sin él. Si se rota: cargar en Railway + restart + `GET /telegram/setup?url=...` |
| `DATABASE_PUBLIC_URL` | ✅ En `.env` local (27/07) | URL pública del Postgres de Railway (`metro.proxy.rlwy.net`) para scripts locales contra prod (`taggear_fotos_web.py`). La interna `.railway.internal` no resuelve fuera de Railway. `ADMIN_API_KEY` también se copió al `.env` local ese día (la usa `publicar_fotos.py` del repo web para el WhatsApp del botón FOTOS FENIX). |
| `ELEVENLABS_API_KEY` | ✅ En `.env` local | Voz del Guardián (TTS George). La usa el script `scripts/generar_voces_alumnos.py` que pre-genera los MP3 de alumnos (23 generados 07/07, cuenta free 10k/mes agotada — resto el mes que viene o $5 Creator). NO la usa el agente en runtime. |
| `JUEGO_API_KEY` | ✅ Configurada en Railway (07/07) | Header `X-JUEGO-KEY` para los endpoints del juego que requieren auth (`/juego/evento`, `/juego/checkin-face`, `/juego/estacion`, `/juego/totem-nfc`, `/juego/nfc-vincular`, `/juego/alumnos`, `/juego/familia-codigo`, `/juego/elegir-robot`, `/juego/vuelta-face`). Los públicos (auth por código de familia o solo lectura) NO la piden: `/juego/eventos`, `/juego/familia/{codigo}`, `/juego/accion`, `/juego/reto-video`, `/juego/estaciones`, `/juego/dia` (resumen del día para la TV lista). |
| `JUEGO_ESTACIONES` | ⚠️ **`quincho,basket`** en Railway (07/08) — default del código `ninja,arbol,basket,quincho,muelle` | Estaciones del circuito NFC. Los `id` deben matchear el `estacion_id` de los ESP32 y del `mapa.html`. **Una vuelta exige tocar TODAS las de esta lista** → agregar una estación acá sin montarla físicamente bloquea el cierre de vueltas (#296). Faltan armar ninja/arbol/muelle (#299). |
| `JUEGO_TIEMPO_MIN_SEG` | Opcional (default `60`) | Segundos mínimos entre estaciones (anti tap-tap-tap). |
| `JUEGO_VUELTA_FACE_MIN_SEG` | Opcional (default `120`) | Segundos mínimos entre vueltas confirmadas por cara (anti doble-tap del "¿Completaste una vuelta?"). |
| `AVISO_CHECKIN_ACTIVO` | ⏳ APAGADA (setear `true` para activar) | Enciende el aviso al padre cuando el niño hace check-in por cara: plantilla `checkin_fenix` con las clases que le quedan (o el vencimiento del mensual) + botones de fotos. Sin ella, el check-in descuenta la clase igual pero no manda nada. Activar solo tras probar con el número de Ivan. **Cambiar la variable NO basta: hay que reiniciar el servicio.** |
| `CONFIRMACION_SABADO_ACTIVA` | ⏳ APAGADA (setear `true` para activar) | Enciende el loop del jueves 9AM que manda la plantilla `confirmacion_sabado_fenix` a las familias al día. Sin ella (o `false`), el loop corre pero NO envía. Activar solo tras probar el flujo Sí/No con 1 número. |

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
| 199 | FASE 2.C: dejar de escribir PRUEBA FENIX (el corte) — C1-C6 | ✅ Hecho (13/07, `203d180`→`82bf6c3`) |
| 200 | FASE 2.D: migrar histórico + deprecar PRUEBA FENIX → renombrada "PRUEBA FENIX LEGACY", canario ~30 días → Iván la borra | ✅ Hecho (13/07, backup+34 reservas+11 caras, `69c3589`/`4c061b0`) |
| 282 | **FAMILIAS FENIX — corte de ALTAS (F7.b)**: las altas ya NO crean FAMILIAS. 10 deploys niño-eje (`c3b3741`→`506d30a`, todos SUCCESS+prod 200+logs limpios): (a) `crear_o_actualizar_tutor` idempotente por CELL LIMPIO+PARENTESCO; (b) `crear_nino` con links PADRE/MADRE+ESTADO; (c) agenda/formulario por grupo familiar + es_prueba por NIÑO.ESTADO; **(c3) CORTE**: `crear_grupo_a_prueba` reemplaza `crear_familia_a_prueba` (borrada), lead se linkea por campo nuevo `LEADS.TUTOR FENIX`; (d) inscripción niño-eje con PLAN al niño (campo nuevo `NIÑOS.PLAN`); (e) candidatos desde NIÑOS A PRUEBA; (f) registro Aurora + cargar niño + modoalumno + reset por tutor; (g) BORRADOS /checkin/familia+/enviar-qr-familia+generar_qr_familia; (i) RESERVAS/ASISTENCIA sueltan FAMILIAS. 3 bugs viejos muertos de paso (cancelar/guard-dup por FIND-sobre-link, patch a FAMILIAS.PLAN inexistente). DECISIÓN: columna `tutor_id` en DB NO se creó (cero consumidores; se cachea en estado_json) | ✅ Hecho (14/07) |
| 283 | Iván (Airtable): vista PAGOS FENIX filtrar por `{NIÑOS FENIX}!=''` (no FAMILIA FENIX) + probar 1ª factura FENIX en vivo | ⏳ Pendiente (Iván) — el resto de la limpieza de datos se hizo en la fila 285 |
| 284 | **F7.c — cierre de FAMILIAS (pendiente)**: (1) ~~datos~~ ✅ hecho fila 285; (2) sacar fallbacks legacy de LECTURA (obtener_grupo_familiar/tutores/router, buscar_familia_por_*, confirmacion_sabado:103, facturas legacy, rama familia de _candidatos, /restaurar-aurora, imports muertos de main + tests/test_local.py importa crear_familia_completa) + flag factura_familia_id; (3) grep 0 lecturas → backup → rename "FAMILIAS FENIX LEGACY" → ~30 días → borrar. HACERLO DESPUÉS del sábado 18 (los fallbacks son la red de seguridad hasta que un sábado real valide) | ⏳ Pendiente (post-sábado) |
| 285 | **Limpieza de datos F7.c (14/07, OK de Iván)**: Martina Martinez linkeada a Hector/Jessica (alumna real huérfana de links); las 2 "FAMILIA Britez" resultaron familias DISTINTAS (tocayas, nada que fusionar); borradas 5 familias muertas (Samudio/Escobar Gimenez/Pineda Villacís/Carrera/Ojeda Memmel, 0 niños/pagos/reservas) + 9 tutores sin hijos. Backup local `backups/2026-07-14/`. Estado final: 101 tutores, 1 solo sin hijos (Iván admin, tiene CODIGO 43E8EW del juego), 1 niño huérfano (ALAN TEST) | ✅ Hecho (14/07) |
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
| 225 | BUG latente: `_get_records` (airtable_client:184) NO pagina, trunca a 100 registros (param `maxRecords` no sigue `offset`). Ya duplicó tutores al re-correr migración. También: `ARRAYJOIN({link})` devuelve el nombre, NO record_ids → no filtrar links con FIND(id) | ✅ Hecho (04/07: pagina por offset `57aacf4` + retry 429 `56b2755`, probado con 107 tutores) |
| 226 | EJE A / A3 (corte) y EJE B / B3 (contract) pendientes: sacar `crear_prueba_fenix` + borrar tabla PRUEBA; quitar escritura PADRE/MADRE + borrar campos. Solo cuando A1/B1/B2 estén estables varios días | ⏳ Pendiente |
| 235 | Web `fenixkidsacademy-web` rediseñada (repo aparte): fotos reales, edad 4-12, horarios 11:00/15:30, precios 240 + matrícula por niño, logos SVG de redes (WA/IG/TikTok/FB/YT). Deployada en Cloudflare Pages | ✅ Hecho (sesión 20) |
| 236 | Aurora sincronizada con la web (sesión 20): mensual 230→240 + matrícula por niño en prompts.yaml/afiches.py/lead_menu.py/pagos.py, afiche_fenix.png nuevo (240), edad 4 + política menores de 4, business.yaml. afiche_hermanos.png huérfano (obsoleto, no se usa) | ✅ Hecho (commits b3b64e9..ba74f07) |
| 237 | Borrar `static/afiche_hermanos.png` (quedó huérfano: el flujo de hermanos ahora manda el afiche de precios) — cosmético | ✅ Hecho (04/07, commit `5b0d43b`) |
| 238 | AUDITORÍA COMPLETA 04/07 — 33 commits deployados: 7 críticos (webhook Telegram con secret, botón pago legacy, rate-limit vs dedup, 429 Airtable, pre-hook pago para gestionar_prueba, prompt Aurora tools reales, Bancard atómico) + altos/medios (historial duplicado a Claude, ctwa_clid, precios 230, regex frágiles, modo nocturno, QR, recordatorios, facturas, timezone -4) + limpieza de muertos (−903 líneas). Detalle: Vault `estado/AUDITORIA COMPLETA 04-07-26.md` | ✅ Hecho |
| 239 | DECISIÓN Ivan — seguimientos +15min/+2h/+6h y recordatorios de formulario: HOY NO EXISTEN (código comentado). ¿Reactivar sobre tabla `recordatorios` de Postgres o borrar `reminders.py`? Regla: ningún FU automático sin aprobación | ⏳ Decisión |
| 240 | DECISIÓN Ivan — `/api/reservas`, `/api/alumnos`, `/api/alumno/{slug}` sin auth exponen nombres/edades de menores. ¿Intencional (web pública) o agregar key de solo-lectura? | ⏳ Decisión |
| 241 | Rediseño `detectar_tipo_pago` por ESTADO (no keywords) + reporte diario de inconsistencias (LEADS PAGO sin PAGOS → Telegram monitor) + borrar/archivar bloque PROMO MADRE (gated) + comportamiento de silencios (spam mudo para siempre / silencio manual expira 5 min) | ⏳ Pendiente |
| 242 | Verificación en vivo post-auditoría: (a) Ivan manda un mensaje desde Telegram en un topic (probar que el secret no rompió el flujo manual), (b) `/endpoint` de un lead real (por el fix del historial duplicado A1) | ⏳ Operacional |
| 243 | **JUEGO F7 — VAR de La Casona: pipeline verificado en vivo** (DVR `DS-7232HGHI-M2`, ISAPI+RTSP, search→download IMKH→FFmpeg→MP4, clip real cámara 31). Credenciales + mapa 32 cámaras por zona en `CLAUDE.local.md` | ✅ Hecho (sesión 26, commit 383aba7) |
| 244 | **JUEGO F7 — DVR: fijar IP (matar DHCP en `.32`) + crear usuario dedicado `fenix` (solo ver/descargar, no admin)**. Se puede por API sin teclado. Datos en `CLAUDE.local.md` | ⏳ Pendiente (esta noche en La Casona, Iván presente por si corta la red) |
| 245 | **JUEGO — Voz del Guardián (George/ElevenLabs) integrada al Modo TV** (`tvVoz()` en index.html) + 7 audios demo en `mundo-fenix/assets/voz/` | ✅ Hecho (sesión 26, no commiteado — repo propio F2) |
| 246 | **JUEGO — Espejo del Guardián** (`mundo-fenix/totem.html`): tótem de la tablet, toca→3-2-1→Rekognition→voz, reintento+fallback profe, modo demo. Tablet TCL Tab 11 comprada | ✅ Hecho (sesión 26, no commiteado — repo propio F2) |
| 247 | **JUEGO — ejecutar `mundo-fenix/SPEC-TOTEM-Y-PROFE.md` (con Opus):** backend eventos + `/juego/checkin-face` (reusa `face_recognition.py`) + TV polling + app del profe + script voces alumnos. 7 fases con verificación cada una | ⏳ Pendiente (Opus, guiado por la spec) |
| 248 | JUEGO — F2 backend del juego (repo propio + Cloudflare o endpoints en Railway del agente): decisión tomada en spec = Railway del agente para el piloto | ⏳ Pendiente |
| 249 | **JUEGO — Fenix cobra vida:** voz de George integrada (despertar + saludo + "¡Listo, Guardián! ¡A entrenar!"), fusión foto real→avatar, ave fénix de fuego (video de Dreamina/Seedance, fondo negro + `mix-blend-mode:screen`), escudo Fenix Kids como sello del espejo. "Hola Fenix" despierta por voz (Web Speech API) | ✅ Hecho (sesión 27, mundo-fenix/, no commiteado — repo propio F2) |
| 250 | **JUEGO — ARQUITECTURA aclarada por Iván:** la TABLET es SOLO el escáner de rostro; TODO el show (Fenix despierta, saluda por nombre, lluvia de monedas) va en la TV de 65". El Modo TV ahora hace ese show; el tótem se simplifica a reconocer | ✅ Decidido (sesión 27) |
| 251 | **JUEGO — Modo TV en la Smart TV (Google TV) verificado en vivo:** corre por túnel HTTPS (localtunnel, cloudflared falla porque el DNS del wifi de La Casona no resuelve trycloudflare); TV Bro como navegador; `?tv=demo` arranca directo el show; botón "MODO TV" grande navegable con el control | ✅ Probado (sesión 27) |
| 252 | JUEGO — deploy DEFINITIVO del juego a HTTPS estable (Cloudflare Pages) para la TV/tablet: mata los problemas de LAN (wifis aislados, DHCP que mueve la IP, caché terca de TV Bro, charset que localtunnel quita). Con URL propia, la TV apunta fijo y la cámara/mic del tótem andan | ⏳ Pendiente (antes del piloto) |
| 253 | JUEGO — decisión Seedance/Dreamina: para animar assets (ave, robots) conviene **pago por uso** (~$0.14/seg), NO la suscripción ($49/mes mensual o $24 atado al año en revendedor). Trial gratis de Dreamina en uso | ✅ Investigado (sesión 27) |
| 254 | JUEGO — **deploy DEFINITIVO a Cloudflare Pages** (`mundo-fenix.pages.dev`): repo propio `mundo-fenix-app` (privado). Cierra el ítem 252 y 248 | ✅ Hecho (sesión 28) |
| 255 | JUEGO — **backend de eventos + circuito NFC + checkin facial + app del profe** (`agent/juego_endpoints.py`, router `/juego/*` aislado). Cierra el ítem 247. Verificado en prod (vuelta completa real) | ✅ Hecho (sesión 28) |
| 256 | JUEGO — **F2/F3: app con datos REALES** — 3 tablas Airtable, link mágico `/?f=CODIGO`, economía en el servidor (`/juego/accion`), videos a R2 (`/api/video` + `/juego/reto-video`), multi-hijo, saludo "entrenaste N días". Arquitectura híbrida (Railway + CF videos) | ✅ Hecho (sesión 28) |
| 257 | JUEGO — 23 alumnos con voz de George generada; **quedan ~26 alumnos** (quota free agotada → 1° del mes que viene re-correr `scripts/generar_voces_alumnos.py`, o $5 Creator un mes) | ⏳ Pendiente (parcial) |
| 258 | JUEGO — **validación IA de videos del reto** (extraer frames + Haiku vision) — iteración 2, decidido. Hoy: checks automáticos + muestreo a Telegram | ⏳ Pendiente (iteración 2) |
| 259 | JUEGO — **hardware NFC** (pedido AliExpress/Amazon a Miami: ESP32×6 + RC522×6 + PN532 + botones NTAG213 lavables + jumpers/LED/buzzer + muñequeras). Fases N0-N7 del `SPEC-NFC-CIRCUITO.md` | ⏳ Pendiente (esperando hardware) |
| 260 | JUEGO — tablet TCL: `mundo-fenix.pages.dev/totem` + montaje + clave del juego | ✅ Hecho (11/07 — decisión: tablet con **Chrome** por el "Hola Fenix" y la cámara; TV con Fully Kiosk + Autoplay Audio ON) |
| 261 | JUEGO — F7 DVR: fijar IP + usuario dedicado (requiere estar en la red de La Casona) | ⏳ Pendiente (en La Casona) |
| 262 | JUEGO — prueba visual del Espejo end-to-end (tablet/PC → foto → Rekognition → TV saluda con voz) | ✅ Hecho (11/07 — validado con niños REALES: llegadas, selector de avatar, vueltas, presentación en TV) |
| 263 | CRM — cargar nombres reales de las 3 familias con tutor "Lead": Carmen Vergara (→ Santiago Guayuan), Leticia Méndez (→ Valentina Buey + Abigail completada), Rosa Marciana Duarte. Cada dato verificado contra las conversaciones de prod (`/conversacion/{tel}`); Airtable ya tenía a Abigail → mirar antes de crear evitó duplicar | ✅ Hecho (12/07 tarde; Rosa la cargó Iván a mano) |
| 264 | PAGOS — rediseño del extractor de nombres (`flujo_pagos.py:68` cae a "Lead" si no encuentra): falló con "Carmen Vergara mamá", "Mamá: Rosa...". Solución: Aurora PREGUNTA el nombre antes de crear la familia (o extracción Haiku) — NO más regex | ⏳ Pendiente (diseñar) |
| 265 | JUEGO — reactivar avatares del mapa (`#capa-kids` oculto por CSS en `mapa.html`) cuando los lectores NFC muevan de verdad a los niños por el circuito | ⏳ Pendiente (NFC en ~10-15 días desde el 11/07) |
| 266 | MIGRACIÓN PRUEBA FENIX — **FASE 0 + FASE 1 + FASE 2.B (reapuntar lecturas) COMPLETAS** (12/07). PRUEBA ya no es fuente de lectura de nada operativo | ✅ Hecho (deployado y verificado) |
| 267 | MIGRACIÓN — **prueba de fuego sábado 18/07**: resúmenes (reservas/flias/asis/telegram) y asistencia interactiva corren en vivo sobre RESERVAS. Comparar contra la clase real | ⏳ Pendiente (18/07) |
| 268 | MIGRACIÓN — **FASE 2.C: cortar escrituras a PRUEBA** (C1 tools reservas, C2 post-formulario + voltear guard, C3 /agenda, C4 promo madre + borrar one-off, C5 cargar familia, C6 fotos). Solo tras ≥1 sábado con 2.B estable | ⏳ Pendiente (tras 18/07) |
| 269 | MIGRACIÓN — **FASE 2.D: backfill histórico + backup + limpieza de código + rename tabla a LEGACY**. Solo tras 2 sábados con 2.C estable. Incluye: RESERVAS históricas con PRESENTE de los 40, links ASISTENCIA.PRUEBA→NIÑO/RESERVA, re-index 11 FACE_ID, borrar `_PRUEBAS`+~15 funciones/endpoints legacy | ⏳ Pendiente (tras 2 sábados) |
| 270 | DATO SUCIO — reserva duplicada de Fiorella González 11/07 11:00 en RESERVAS FENIX (borrar una a mano) | ⏳ Pendiente (Ivan) |
| 271 | CRM — control de sexo/parentesco de TODOS los niños (105) y tutores (110): corregidos Hannah Rojas→MUJER, Milagros López→MUJER (estaban HOMBRE), Nayila Duarte→Mamá (estaba Papá). Script `scratchpad/control_sexo.py` (baja por API + heurístico de nombres) | ✅ Hecho (12/07) |
| 273 | AUDITORÍA 12/07 — **`docs/estado/AUDITORIA-2026-07-12.md` es la fuente de verdad** (~70 hallazgos con archivo:línea). CRÍTICOS y F2 completos, F4 (lo confirmado) también | ✅ Hecho (21 pushes verificados) |
| 274 | AUDITORÍA — **A10: keywords que fuerzan `tool_choice`** (`"sab"` matchea "sabemos", `"cambiar"` genérico → Haiku obligado a llamar `gestionar_reserva` en mensajes que no son de reservas). Cambia comportamiento conversacional → requiere `/pre-cambio` + simulación de los 5 escenarios | ⏳ Pendiente (no tocar sin simulación) |
| 275 | AUDITORÍA — **C4: rate limiter de SALIDA** (solo existe para entrantes; la promo masiva manda ráfagas de 50 plantillas sin pausa y si falla deja el flag "activo" trabado). Es un diseño (cola/limiter central en el provider), no un parche | ⏳ Pendiente (diseñar) |
| 276 | AUDITORÍA — pendientes menores: A2 (guard de pagos más amplio — pensar junto con cuota-al-niño), A12 (el retry de brain re-fuerza la tool sobre historial mutado), night_mode responde con `agent_actual="ivan"` hardcodeado, escalación agarra "Hola" como nombre del padre, el gate del menú de leads bloquea a los detectores | ⏳ Pendiente |
| 277 | AUDITORÍA — migrar los bots de **salsa/curso** a firma-con-cliente para volver estricta la pasarela (`pagos-bancard`) para todos los negocios; hoy fenix es estricto y los otros toleran la firma legacy | ⏳ Pendiente |
| 278 | **MIGRACIÓN FAMILIAS FENIX** — **M1+M2 (Airtable+backfill) 13/07 ✅ y PASO 3 NÚCLEO (código) 13/07 ✅ EN PROD** (Iván levantó la espera al 18/07): pagos dual-write NIÑOS FENIX+PAGA, guards anti-dup por unión FAMILIAS∪NIÑOS.PAGOS, NIÑOS.ESTADO (espejo + promoción al inscribir), confirmación sábado por NIÑOS.AL DÍA?, reservas del contexto por link del niño (mató A8), router niño-eje `es_cliente_activo_por_telefono` con fallback legacy. Commits C0-C6 `f943b71`→`758fb8c`, ver §12. **Fases restantes:** juego `CODIGO FENIX` por niño, facturas/robot externo, `/api/*` + resúmenes + broadcasts (A15) + QR familia, `familia_id`→`tutor_id` en DB, corte de escrituras → FAMILIAS congelada → archivar | 🔄 núcleo ✅ / juego+facturas+corte ⏳ |
| 280 | DATO SUCIO — pagos de familias de **FENIX** cargados con `FUENTE='SALSA SOUL STUDIO'` (ej. FAMILIA Molinas Silva, concepto `F.SUSCRIPCION`). El criterio correcto para "pago de Fenix" es **tener FAMILIA FENIX**, no la FUENTE. Decidir si se re-etiquetan o se deja el criterio por link | ⏳ Pendiente (decisión Ivan) |
| 281 | NEO — su suite de tests tiene **26 tests fallando** (preexistente, no lo causó el fix del cache): `pytest-asyncio` sin configurar → "async def functions are not natively supported". Mismo patrón que el de FENIX del 13/07 | ⏳ Pendiente (al tocar NEO) |
| 279 | Probar el **formulario de reserva end-to-end en WhatsApp real** (Flow post-pago + rescate A7 de +2h/+24h): deployado pero nunca probado con un teléfono de verdad | ✅ Hecho (25/07, primera prueba real — encontró el bug del #289) |
| 282 | JUEGO/HARDWARE — vincular las pulseras REALES de los chicos vía `/profe` (Web NFC) pasando el `nino_id` real de Airtable — **en curso el 25/07 durante el piloto en vivo.** Web NFC confirmado funcionando (Chrome Android + NFC prendido, cualquier fabricante, no hace falta Google Play — se dudó de un Huawei sin GMS pero sí anduvo); pendiente terminar de vincular al resto de los chicos | 🔄 En curso (piloto 25/07) |
| 283 | JUEGO — completar `JUEGO_ESTACIONES` con las 5 (`ninja,arbol,basket,quincho,muelle`) a medida que se arman. **07/08: pasó de `quincho` a `quincho,basket`** (basket armada y verificada). Faltan ninja/arbol/muelle | 🔄 En progreso (2 de 5) |
| 284 | HARDWARE — armar las 2 estaciones restantes del piloto (`ninja`/`arbol`/`basket`/`muelle`, elegir 2): soldar header al RC522 (pack de 6 comprado, sin soldar), cablear, flashear `firmware/estacion/` con su `ESTACION_ID`, powerbank o fuente fija in situ. Carcasa/LED WS2811 quedan de mejora, no bloqueantes | ⏳ Pendiente |
| 286 | JUEGO/FIRMWARE — **CERRADO, con reversión** (ver #288): el fix WUPA→Select→Halt NO resolvió la lectura cruzada de fondo — se colgó dos veces más incluso siendo protocolarmente correcto. Se abandonó ese mecanismo por duración fija (commit `315e7f4`). Sigue pendiente verificar si `PCD_SetAntennaGain(RxGain_max)` alcanza para leer con la caja de `quincho` cerrada (antes solo leía tocando el RC522 directo — sospecha: el anillo LED tapa la antena) | 🔄 Ver #288 |
| 288 | JUEGO/FIRMWARE — **`firmware/estacion/estacion.ino`: el LED vuelve a duración FIJA (1.5s), no sigue el retiro real de la pulsera.** Se probó mantener el tag "despierto" con `WakeupA→PICC_Select→HaltA` en loop (protocolarmente correcto por ISO14443) para que el LED siguiera la presencia exacta — pero se colgó el lector 2 veces (con moneda NTAG213 Y con llavero Mifare Classic, no es cosa de un solo chip): tras un ciclo, el RC522 dejaba de detectar CUALQUIER tag nuevo hasta reiniciar el ESP32, sin ningún error en el log. Diagnosticado con captura de serial en vivo (`pyserial`, ver `scratchpad` de la sesión) — se vio literal silencio de 50+ segundos tras un tap exitoso. Revertido a duración fija por confiabilidad (commit `315e7f4`) — NO reintentar el enfoque WakeupA/Select en este hardware sin resolver antes por qué se cuelga a bajo nivel (ver `memory/errores-aprendidos.md`) | ✅ Hecho (25/07) |
| 287 | JUEGO/HARDWARE — buzzer HW-508 de `quincho` instalado (VCC a 5V vía breadboard — el ESP32 solo tiene un pin de 5V y un 3V3, ya ocupados por LED/RC522 — GND y señal a GPIO25) y programado en `firmware/estacion/estacion.ino` (barrido de frecuencias 1500-4500Hz en el tap, buscando la resonancia). Probado: suena pero MUY suave — limitación física del piezo chico del HW-508, no de firmware. Aceptado así para el piloto (el LED es la confirmación visual principal); si se necesita más volumen a futuro, cambiar a buzzer activo más grande o parlante amplificado | ✅ Hecho (25/07) |
| 285 | JUEGO — `/profe`: check ✅ visible junto al nombre del niño cuando ya tiene pulsera vinculada (no depende de ver el toast) + `POST /juego/nfc-desvincular` (un niño) y `/juego/nfc-desvincular-todas` (fin del entrenamiento, resetea el pool de muñequeras para reasignar, con confirm y sin borrar historial) | ✅ Hecho (25/07, en vivo durante el piloto) |
| 272 | JUEGO — implementar "Mecánica del Sábado v2" (diseño en `mundo-fenix/PLAN-MAESTRO.md` §11): 7 vueltas desbloquean el desafío / 10 = caja mágica; abrir/cerrar el entrenamiento por comando de WhatsApp; insignia (genérica) se otorga con el SÍ de Iván post-cierre (nada automático). Incrementos: (1) lista ✅7v+✅3misiones [empezar acá], (2) audio/evento 7ma vuelta + regenerar audios llegada/vuelta (neutros, TODOS los niños), (3) abrir/cerrar, (4) post-cierre WhatsApp. Abiertas: video de felicitación (genérico/por niño), texto audio Tesoro | ⏳ Pendiente (diseño listo, nada codeado) |
| 289 | **BUG CRÍTICO** — la primera prueba real del formulario de reserva (#279, caso 595981941407 "Blas Páez") perdió TODOS los datos que el papá cargó (nombre real, CI, fecha nacimiento, mamá): `procesar_formulario_reserva` solo sabía actualizar un niño existente, y sin niño previo tiraba el `flow_data` sin persistirlo en ningún lado (ni DB, ni Airtable, ni logs con contenido). El detector legacy de texto encima recreó al niño con el nombre ADIVINADO. Fix: el niño se CREA desde el formulario si no existe + los datos se espejan siempre (Telegram/WhatsApp admin/DB) + `prueba_creada=True` desarma el detector legacy. Detalle completo en `memory/errores-aprendidos.md` | ✅ Hecho (27/07, commit `7541b7e`) |
| 290 | **PAGO huérfano** — `registrar_pago_fenix` linkea `NIÑOS FENIX`/`PAGA` al momento del pago; si el niño nace después (vía formulario, ver #289) el pago queda sin esos links para siempre — invisible en las vistas de PAGOS filtradas por `FAMILIA FENIX`/`NIÑOS FENIX`. Fix: al procesar el formulario, back-fill automático de los PAGOs `PRUEBA` del lead que quedaron sin niños | ✅ Hecho (27/07, commit `1a8216d`) |
| 291 | DATO SUCIO — caso puntual de Blas Páez (595981941407): sus datos reales (CI, fecha nacimiento, datos de mamá) se perdieron por el bug #289 ANTES del fix — no son recuperables del sistema. Hay que pedírselos de nuevo por WhatsApp | ⏳ Pendiente (Iván) |
| 292 | El detector legacy de texto (`_es_formulario_completo` en `main.py`) que secuestró la reserva de Blas Páez el 25/07 sigue vivo en el código — ya no puede pisar datos reales gracias al interlock `prueba_creada` (#289), pero sigue siendo el fallback si el papá nunca completa el formulario. Evaluar si conviene un rediseño más de fondo | ⏳ Pendiente (evaluar) |
| 293 | **TUTORES FENIX legacy** — tras la migración a ALUMNOS (07/08) la tabla quedó con solo dos usos vivos: el `CODIGO` del link mágico del juego y los datos de facturación (`FACTURA` + link `FACTURAS.TUTOR`). Decidir si se mudan a ALUMNOS o si TUTORES queda como tabla de apoyo | ⏳ Pendiente |
| 294 | **Limpiar los campos texto** `HIJOS (COMO PADRE)` / `(COMO MADRE)` de TUTORES FENIX (traen datos viejos tipo 'ALAN TEST'). Ya no los lee nadie, pero conviene borrarlos para que no vuelvan a confundir a un refactor | ⏳ Pendiente (después de probar el alta end-to-end) |
| 295 | **Probar el alta de lead end-to-end** post-migración ALUMNOS: lead escribe → paga → formulario Meta → verificar en Airtable tutor en ALUMNOS con NEGOCIO=FENIX, niño con `PADRE/MADRE (ALUMNOS)`, PAGO con `PAGA (ALUMNOS)`. Es el único camino que el fix tocó y no se ejerció en vivo | ⏳ PRÓXIMA SESIÓN — arrancar por acá |
| 296 | ⚠️ **`basket` está activa en `JUEGO_ESTACIONES`** (`quincho,basket` desde 07/08) → **una vuelta exige tocar LAS DOS estaciones**. Si basket no está montada, alimentada y leyendo un sábado, NINGÚN niño puede cerrar vuelta. Para sacarla: `JUEGO_ESTACIONES=quincho` + `serviceInstanceRedeploy` (1 min) | ⏳ Verificar cada sábado |
| 297 | **Anillo LED de la estación `basket`** — no cableado. El firmware ya lo maneja (WS2811, GPIO 4). Necesita **breadboard** porque el `3V3` del ESP32 lo ocupa el RC522 (mismo caso que quincho). No es cosmético: el buzzer HW-508 casi no se oye, el LED es la confirmación real para el niño | ⏳ Pendiente |
| 298 | **Velocidad entre taps** — medidos 3,44 s entre lecturas en basket (1,5 s del `delay` del LED + ~2 s de handshake TLS). Iván reporta que quincho es casi instantáneo, con firmware idéntico → sin explicar. Antes de tocar código: **medir quincho por serial** igual que se midió basket. El experimento con POST asíncrono rompió la detección y se revirtió | ⏳ Pendiente (no urgente) |
| 299 | **Fase N3 — vincular pulseras** a niños reales: hoy los taps responden `pulsera_no_vinculada` y no cuentan. Estaciones que faltan armar: `ninja`, `arbol`, `muelle` | ⏳ Pendiente |

---

## 12. Historial de Cambios

| Fecha | Cambio realizado |
|---|---|
| 2026-08-07 (noche — estación NFC `basket` armada + el RC522 mudo que se destraba desenchufando) | **Segunda estación del circuito NFC terminada end-to-end.** Iván soldó el header del RC522, se cableó lector + buzzer HW-508 y se flasheó `estacion.ino` con `ESTACION_ID=basket` (mismo binario que quincho). Verificado con hardware real: `VersionReg 0x92`, WiFi OK, `UID 7B45DE00`/`3A90EF55` → `POST /juego/estacion → 200`. Se agregó `basket` a `JUEGO_ESTACIONES` en Railway (antes solo `quincho`) + redeploy → ⚠️ **una vuelta ahora exige tocar quincho Y basket**. Tres trampas de hardware: (1) el pin del **medio** del HW-508 es **GND**, no VCC — al revés da zumbido continuo; (2) boot loop `invalid header: 0xffffffff` por cableado → aislar alimentación primero, señales después; (3) **el RC522 se traba mudo** (`VersionReg` OK + cero detecciones) y **solo se destraba cortándole la alimentación** — el botón `EN` no se la corta (costó ~2h, probablemente el mismo modo de falla sin explicar del 25/07). Sin cambios en los sketches. Detalle completo → `.claude/handoffs/handoff_20260807_2318.md` |
| 2026-08-07 (Tutores mudados a ALUMNOS — Aurora muda por un TypeError) | **Aurora no le respondía a Ivan: el webhook crasheaba con `can only concatenate str (not "list") to str`.** Causa raíz: los padres/madres se mudaron a **ALUMNOS** (`NEGOCIO=FENIX KIDS ACADEMY`) pero el código del 03/08 seguía leyendo `TUTORES FENIX`, cuyos campos `HIJOS (COMO PADRE/MADRE)` quedaron como **texto** — sumarlos como listas reventaba para los 101 tutores. Fix en dos deploys: `95cb067` (identidad: `buscar_tutor_por_telefono` → ALUMNOS por `TELEFONO LIMPIO` con prioridad hijos-linkeados > NEGOCIO; links `PADRE/MADRE (ALUMNOS)`; el reset ya **no borra** la fila compartida, le quita la marca FENIX) y `3fafa06` (los callers: main/resumenes/inscripcion/formulario_reserva/confirmacion_sabado/facturas/registro). Verificado en prod: 0 errores, `/api/alumnos` devuelve 88 niños con madre y 52 con padre (antes: vacío). Detalle completo → `.claude/handoffs/handoff_20260807_1253.md` |
| 2026-07-28 (madrugada — precio nuevo: el PACK de 5 clases que no vencen + saldo por niño + aviso al padre en el check-in) | **Cambio de modelo comercial completo, de punta a punta, en una sesión: el mensual de 240k por 4 sábados murió y lo reemplazó un pack de 350k por 5 sábados que NO vencen (+150k por hermano; prueba y matrícula sin cambio).** **(1) Precio en los 7 lugares vivos** (`23580fc` código + `e7f42e5` prompt, deploys separados como manda la regla): `prompts.yaml`, `lead_menu.py` (TEXTO_PRECIOS/TEXTO_HERMANOS), `afiches.py` (msg_precios/msg_hermanos), **`main.py` × 2** (los fallbacks de texto de los interceptores cuando el afiche ya se envió — **no estaban en el mapa de la memoria, aparecieron por grep**), `reminders.py` (seguimiento A) y `pagos.py` (dict `PRECIOS` → `pack5*`; verificado: importado en main.py:78 pero **sin un solo consumidor**). Afiche nuevo (hecho por Ivan con ChatGPT) a `static/afiche_fenix.png` + convertido a JPG para la web. **(2) Web** (`61217aa`, repo `fenixkidsacademy-web`, **rama master**): card "Plan mensual" → "Pack 5 clases", tabla de hermanos 350/500/650 y **los 3 links de pago refirmados** — la `sig` es `HMAC(LINK_SECRET, "fenix:{monto}")[:16]`, así que cambiar el monto sin refirmar los deja rotos; `LINK_SECRET` se sacó de las variables de Railway por GraphQL y se validó recalculando la firma vieja de 240000 antes de generar las nuevas. **(3) Saldo de clases** (`854347c`): campos nuevos `NIÑOS FENIX.CLASES DISPONIBLES` (number) y `ULTIMO DESCUENTO` (date, gate de idempotencia). Una sola puerta —`descontar_clase()` / `recargar_pack()`— con la misma disciplina que `_acreditar` con el oro del juego. **Campo vacío = familia del mensual viejo: no se le descuenta nada** (decisión de Ivan: siguen aparte). Enganchado en los **tres** puntos que crean asistencia (cara, QR, HQ manual) — de ahí el gate diario: un niño puede pasar por más de uno el mismo sábado. Nunca baja de 0 ni bloquea la entrada del niño. Probado contra Airtable real con 7 casos (sin pack → None, +5, descuento, doble descuento mismo día, día siguiente, piso en 0) y el registro restaurado. **(4) Pagar el pack suma +5 acumulativo** (`004d745`): cargar la inscripción con "pack"/"paquete"/"5 clases"/"p5" registra el PAGO con **`CONCEPTO=PAQUETE5`** —opción que **ya existía** en el select— y suma 5 a cada niño del pago (4 que quedaban + 5 = 9). Bonus verificado: `VENCIMIENTO_FORMULA` no contempla PAQUETE5 → el pago queda **sin fecha de vencimiento**, justo lo que necesita un pack que no vence. Parser probado con positivos y negativos: mensual/trimestral/qm/sm/qt/st siguen resolviendo igual. **(5) Aviso al padre + fotos** (`1916701` + `23b82c3` en la web): plantilla **`checkin_fenix` creada y APROBADA** (WABA propio de FENIX, es_AR, UTILITY) — avisa que el hijo entró, cuántas clases le quedan (o cuándo vence su mensual) y pregunta por las fotos con botones. Los textos de botón son **"Sí, mandame fotos" / "No, gracias"**, distintos de los "Sí/No" de `confirmacion_sabado_fenix` a propósito: la respuesta llega **sin id, solo con el texto**, y se confundirían. `agent/checkin_aviso.py` nuevo maneja envío, respuesta y `avisar_fotos_listas()`; el **paso 7 de `publicar_fotos.py`** le pega a `POST /fotos/avisar-familias` cuando las fotos ya están arriba y el server le pasa el link a quien lo pidió (el pedido se limpia al enviar → no repite). El botón que toca el padre **abre la ventana de 24h**, así que el aviso de las fotos del mismo día sale como mensaje libre, sin plantilla ni costo. **APAGADO por defecto** (`AVISO_CHECKIN_ACTIVO`). **(6) Skill `/cambioprecio`** (`8d04b0e`) destilado de esta misma sesión: los 7 lugares + la web, el grep de control del valor VIEJO, las firmas HMAC, el afiche en los dos repos y los dos pushes separados, con tabla de anti-racionalizaciones. **De paso se corrigió el CLAUDE.md, que decía "4 lugares vivos"** — el mismo dato incompleto que casi deja el precio viejo en producción. Descubierto al registrarlo: un skill del proyecto solo es invocable con `/` si tiene su archivo espejo en `.claude/commands/` (`fotosfenix` no lo tiene). **Pendientes:** prender el flag y probar con el número de Ivan antes del sábado 01/08; el aviso está enganchado **solo en el check-in por cara** (QR y HQ descuentan pero no avisan); avisar a Ivan por Telegram cuando un niño llega a 0 clases. |
| 2026-07-27 (bug real del formulario de reserva: el niño se creó de más, el pago quedó huérfano — fix completo) | **`/endpoint 595981941407` (typo de Iván por 595, resuelto) destapó la primera prueba real en producción del formulario de reserva (#279), y encontró que perdió TODOS los datos del papá.** Investigación completa vía Airtable MCP (LEADS/PAGOS/TUTORES/NIÑOS FENIX) + logs de Railway (GraphQL directo a `backboard.railway.app`, filtrando por teléfono/`RESERVA-FORM`/`formulario`): el pago SÍ existía en PAGOS pero sin `NIÑOS FENIX`/`PAGA` (invisible en la vista filtrada); el niño SÍ se había creado pero por el **detector legacy de texto**, con el nombre ADIVINADO — no por el formulario. Los logs mostraron la secuencia exacta: `[formulario] llega → WARNING no encontré grupo a prueba → datos descartados → 5 min después el detector legacy crea el niño con el nombre del chat`. **Causa raíz:** `procesar_formulario_reserva` (`formulario_reserva.py`) solo sabía ACTUALIZAR un niño existente; sin grupo previo tiraba el `flow_data` completo sin persistirlo (ni DB, ni logs con contenido — solo un `warning` sin datos). Un subagente (Fable) analizó el código completo y devolvió un diagnóstico + plan de 2 commits con riesgos, que Iván simplificó a lo esencial: "que el formulario cree al niño". **Commit `7541b7e`:** `procesar_formulario_reserva` ahora CREA el niño con los datos reales si no existe (reutilizando el tutor parcial del pago sin duplicar); el contenido completo del formulario se guarda en DB y se espeja SIEMPRE a Telegram + WhatsApp del admin, ANTES de tocar Airtable; se sacó la dependencia del flag `esperando_formulario_reserva` para PROCESAR (antes, con el flag apagado, el mensaje cargaba al pipeline normal como texto `"[formulario]"` y se perdía); `prueba_creada=True` se setea al terminar — desarma el detector legacy que había pisado los datos reales en el caso real. **Commit `1a8216d`:** back-fill del PAGO huérfano — al crear/completar el niño, se buscan los PAGOs `PRUEBA` del lead sin niños linkeados y se les cuelga `NIÑOS FENIX`+`PAGA`. **Ambos pusheados y verificados en prod** (`/debug/{tel}` responde normal post-deploy en los dos). **Registrado en `memory/errores-aprendidos.md`** con la regla general: dato de fuente verificada + registro que no existe todavía → CREARLO, nunca descartar el dato; todo webhook externo se persiste crudo en DB antes de cualquier lógica. **Pendiente:** el caso puntual de Blas Páez quedó con datos reales (CI/fecha nac/mamá) irrecuperables — pedírselos de nuevo (#291); evaluar si el detector legacy de texto conviene desarmarlo del todo, no solo por interlock (#292). |
| 2026-07-25 (piloto en vivo: vinculación de pulseras reales + gestión de muñequeras en `/profe`) | **Continuación same-day de la sesión anterior — Iván ya en La Casona con chicos reales probando el circuito.** **(1) Diagnóstico Web NFC:** un Huawei sin Google Play generó dudas de compatibilidad (sospecha inicial: Chrome no genuino) pero **terminó confirmado que SÍ funciona** — Web NFC (`NDEFReader`) solo necesita Chrome real + NFC prendido en el dispositivo, sin depender de GMS. La confusión real fue de UX: el diálogo nativo de Android "Wallet vs Etiquetas" tapa el cartel de confirmación un instante, dando la falsa impresión de que no vinculó. Verificado directo en la tabla `pulseras` de Postgres (vía `DATABASE_PUBLIC_URL` del servicio Postgres de Railway, con `psycopg2` instalado al vuelo) que el UID sí había quedado vinculado. **(2) 3 mejoras a `/profe` shippeadas en caliente durante el piloto** (petición directa de Iván viendo el problema en tiempo real): **`9df6358`** — check ✅ visible junto al nombre en la lista de "Elegí al Guardián" cuando el niño ya tiene pulsera vinculada (antes solo había un toast fugaz); `GET /juego/alumnos` ahora cruza contra la tabla `pulseras` activa. **`f225e03`** — `POST /juego/nfc-desvincular` (un niño) + botón "🔓 Desvincular pulsera": libera la muñequera de un chico sin borrar su historial de pasadas/vueltas, para poder reasignarla a otro más adelante sin chocar con el 409 del vincular. **`c2ec37d`** — `POST /juego/nfc-desvincular-todas` + botón "🔓🔓 Desvincular TODAS las pulseras" (con `confirm()` antes de disparar): para el fin del entrenamiento, resetea el pool completo de muñequeras físicas de una sola vez en vez de una por una. **3 deploys, cada uno verificado con health 200 antes de decirle a Iván que siguiera.** **Pendiente:** terminar de vincular al resto de los chicos del piloto de hoy (#282 sigue en curso). |
| 2026-07-24/25 (circuito NFC físico: primera estación real armada + fix de plata + piloto de mañana) | **Primera vez que el circuito NFC de Mundo Fenix corre en hardware real, de punta a punta.** **(1) Puesta a punto de la PC:** faltaba el driver CP2102 (Silicon Labs) — el ESP32 se veía físicamente conectado pero sin puerto COM (Device Manager: "CP2102 USB to UART Bridge Controller", error 28); instalado por `pnputil` elevado, quedó en COM3. `arduino-cli` estaba instalado pero no en el PATH (`C:\Program Files\Arduino CLI\`). **(2) `firmware/` nuevo en el repo** (antes solo local, sin commitear): `banco_lector/` (fase N0, ya existía) + `estacion/estacion.ino` (fase N2) — WiFi + `POST /juego/estacion` real, credenciales en `config.h` gitignored (`config.h.example` como plantilla). Primer RC522 del pack de 6 vino **sin header soldado** (solo agujeros) — soldado a mano por primera vez (Iván, con guía paso a paso: cautín, estaño 63/37, header recto de 8 pines). **Bug de WiFi encontrado y resuelto:** el SSID real de La Casona tiene un **espacio antes de "_EXT"** (`LA CASONA LAFUENTE _EXT`, no pegado) — invisible a simple vista, causaba `NO_AP_FOUND` constante; se agregó `escanear_redes()` al sketch (lista SSIDs reales + RSSI al arrancar) para no volver a adivinar nombres de red. Se usó la red base `LA CASONA LAFUENTE` (sin extensor) para la prueba. **Estación `quincho` verificada end-to-end**: lee UID → WiFi conecta → POST 200 → niño de prueba "FENIX" (guardián mamba) vinculado por `/juego/nfc-vincular` (sin `nino_id`, adrede — no ensucia Airtable) → `estaciones_completadas` sube correcto. **(3) Bug real encontrado en el código de producción** (no de hoy, preexistente): el cierre de vuelta por NFC (`/juego/totem-nfc`) nunca pasaba por `_acreditar` — solo emitía el evento que anima la TV, la billetera (Airtable `PLATA`) **nunca se actualizaba de verdad**. Arreglado (`5732953`) + extraída la lógica común a `_evaluar_circuito()` (reusada por totem-nfc y por el check-in facial). **(4) Piloto simplificado para el 25/07** (pedido de Iván: solo 1 estación armada hoy, `quincho`): `JUEGO_ESTACIONES` en Railway cambiada de las 5 originales a solo `quincho` (+ restart) — pendiente revertir cuando estén las otras (#283). El check-in facial (`/juego/checkin-face`, ya existía para el saludo diario) ahora **también evalúa el circuito en cada escaneo** (no solo el primero del día) y cierra la vuelta sola si el niño ya tocó todas las estaciones activas — sin hardware nuevo en el tótem, reusa el reconocimiento facial que ya estaba andando. `mundo-fenix/totem.html` (**commiteado al repo por primera vez**, antes vivía solo untracked/en Cloudflare Pages) actualizado: si el circuito ya cerró la vuelta sola → festeja directo; si falta alguna estación → la nombra; si el niño no tiene pulsera vinculada → cae al conteo manual de siempre (sin romper nada). **(5) Anillo LED WS2811 (COB, 27mm) como feedback local**: agregado a `estacion.ino` con FastLED — prende verde apenas lee la pulsera, ANTES del POST (confirmado en el log: prendió incluso mientras el WiFi todavía estaba reintentando conectar). `NUM_LEDS` sobreestimado a 16 porque no se pudo confirmar el conteo físico real del anillo (los canales de más simplemente no reciben nada, sin riesgo). Cableado con jumpers hembra-hembra sobre las puntas peladas/estañadas del anillo (sin soldar al ESP32 — el ESP32 queda intacto y reusable). **3 commits de firmware+backend+frontend, todos deployados y verificados en prod** (`b51f9c7`, `5732953`, `80765df`, `1faf741`). **Comprado (aún sin llegar):** pack de 6 ESP32-DevKitC-32 (variante "D" con antena de PCB, no la "U" sin antena que trabó el arranque de la sesión) + pack de 6 RC522 sin soldar (~$14, más barato que uno pre-soldado — no se consiguió ninguno soldado en Amazon/AliExpress, no es estándar en esos marketplaces). **Pendientes para mañana:** vincular pulseras reales con `nino_id` (#282), armar las 2 estaciones restantes del piloto cuando lleguen los ESP32/RC522 nuevos (#284), decidir de dónde sale la corriente de `quincho` in situ (powerbank vs. fuente fija — sin resolver). |
| 2026-07-14 (F7.b — el CORTE de altas de FAMILIAS + limpieza de datos) | **Las ALTAS ya no crean FAMILIAS. Todo el ciclo de vida (alta lead → prueba → inscripción → reservas → registro → reset) corre por TUTOR+NIÑOS; FAMILIAS queda solo en fallbacks de lectura.** **10 deploys niño-eje incrementales (`c3b3741`→`506d30a`), cada uno SUCCESS + prod 200 + logs de arranque limpios antes del siguiente:** **(a) `c3b3741`** `crear_o_actualizar_tutor(persona, parentesco, familia_id="")` idempotente por **CELL LIMPIO + PARENTESCO** (ya no por familia; una persona = un registro aunque haya fichas duplicadas); familia_id opcional solo mantiene el link legacy. **(b) `87fc53d`** `crear_nino(datos, familia_id="", *, padre_id, madre_id, estado)` con links directos PADRE/MADRE + ESTADO explícito. **(c1) `b022474`** `gestionar_reserva` (agenda.py) y `formulario_reserva` resuelven por `obtener_grupo_familiar`; reagendar/cancelar por links `RESERVAS FENIX` del niño (el FIND viejo nunca matcheaba → cancelar estaba roto). **(c2) `5314090`** `es_prueba` de `obtener_ninos_por_horario` sale de **`NIÑO.ESTADO`** (lookup ESTADO PLAN de familia queda de respaldo). **(c3) `fc4a9db` — EL CORTE:** `crear_grupo_a_prueba` (tutor idempotente + niños ESTADO='A PRUEBA' linkeados, guard legacy familia-con-hijos) **reemplaza a `crear_familia_a_prueba` (borrada)** en los 5 call sites; el lead se linkea por el campo **nuevo `LEADS.TUTOR FENIX` (`fldOaYMkJdtihJrj2`)**; tutor_id se cachea en `estado_json`. **(e) `38e0ef8`** `_candidatos_a_prueba` (cargar familia) enumera NIÑOS ESTADO='A PRUEBA' agrupados por tutor (fallback por FAMILIA legacy). **(d) `cecb90e`** inscripción niño-eje: NIÑOS→ACTIVO + **PLAN al niño** (decisión de Iván: campo **nuevo `NIÑOS.PLAN` `fldNyWFtzD0NO48HC`**, 4 opciones; soporta hermanos con planes distintos), PAGOS con NIÑOS FENIX+PAGA=tutor, LEAD→INSCRIPTO+TUTOR FENIX. **Hallazgo:** `FAMILIAS.PLAN` **no existía en la tabla** → el patch viejo era un 422 silencioso hacía tiempo. **(f1) `d5a2e6a`** registro Aurora (tutor/hijo sin FAMILIAS, inline REGISTRO PADRE/HIJO delega en las tools, `/registro` por grupo sin crear FAMILIA vacía). **(f2) `819883e`** cargar niño (Flow) → TUTORES+NIÑO ACTIVO, `asegurar_grupo_prueba_admin` (modoalumno), `eliminar_todo_de_telefono` borra tutor→hijos→reservas por links (el reset viejo dejaba reservas huérfanas). **(g) `467cf3b`** BORRADOS `/checkin/familia/*`, `/enviar-qr-familia`, `generar_qr_familia`, `_render_checkin_lista_html` (−163 líneas). **(i) `506d30a`** `crear_reserva(nino, horario)` sin link FAMILIAS + guard anti-dup por links del niño; `crear_asistencia` sin FAMILIA/PRUEBA; confirmación/cancelación regex de main por grupo; `buscar_reservas_familia`/`cancelar_reservas_familia_fecha` **borradas** (las 2 funciones rotas de `reference_arrayjoin_link`). **DECISIÓN (h):** la columna `tutor_id` en ConversacionAB **NO se creó** — cero consumidores (el tutor se resuelve por CELL LIMPIO, el id se cachea en estado_json), y la regla del plan era "columna DB solo cuando algo la lea". **3 bugs viejos muertos de paso:** cancelar-reservas y guard-anti-dup de crear_reserva (ambos `FIND(id, ARRAYJOIN(link))` que compara ids contra nombres), + patch a `FAMILIAS.PLAN` inexistente. **LIMPIEZA DE DATOS F7.c (OK de Iván):** Martina Martinez linkeada a Hector/Jessica (alumna real huérfana de links — evidencia: la familia tenía su reserva y se crearon con 2 min de diferencia); las **2 "FAMILIA Britez" resultaron familias DISTINTAS** (Johanna con 2 hijos A PRUEBA / Antonia Iliada con Olivia — tocayas, nada que fusionar; la "fuga" era el FIND por nombre ya muerto); borradas **5 familias muertas** (Samudio/Escobar Gimenez/Pineda Villacís/Carrera/Ojeda Memmel, 0 niños/pagos/reservas) + **9 tutores sin hijos** (backup local `backups/2026-07-14/`; se conservó el tutor Iván `recKLA9bkRHHK8ET1` porque tiene el CODIGO 43E8EW del juego). **Estado final: 101 tutores, 1 solo sin hijos (Iván admin, intencional), 1 niño huérfano (ALAN TEST).** **PENDIENTE F7.c** (después del sábado 18 OK): sacar los fallbacks legacy de lectura → backup → rename "FAMILIAS FENIX LEGACY" → ~30 días → borrar. **Sin verificar en vivo aún** (ningún lead pagó): probar el alta niño-eje end-to-end con número de test + "cargar familia". |
| 2026-07-13 (madrugada 3 — PRUEBA FENIX = LEGACY 🎉 + FAMILIAS niño-eje casi entera) | **Sesión maratónica: 18 deploys en fenix (`64839e5`→`7ab5097`) + 1 en `facturador-set` (`ccb5089`), todos SUCCESS y verificados uno por uno. Objetivo declarado por Iván: "poder ELIMINAR las tablas".** **(A) FAMILIAS fuera del hot-path (F2+F3):** `/api/reservas`+`/api/alumnos` leen TUTORES+`NIÑOS.ESTADO` (105 niños comparados: 28 difs, todas mejoras); resúmenes con `_tutor_de_nino` (contacto desde el niño, CELL LIMPIO arregla wa.me rotos); broadcasts `obtener_familias_inscriptas` desde NIÑOS activos+TUTORES (dedupe: el viejo tenía 41 familias→40 tels = un doble envío; +arregla A15); **`obtener_grupo_familiar`** (tutor→hijos→tutores, fallback legacy) alimenta `_build_contexto_aurora` y `procesar_menu_inscripto`; nombre del topic Telegram por `buscar_tutor_por_telefono` (match exacto vs rollups por índice). **(B) PRUEBA FENIX → LEGACY (2.C+2.D COMPLETAS):** cortadas TODAS las escrituras (C1 tools reservas, C5 "cargar familia" sobre FAMILIAS A PRUEBA+NIÑOS, C2 post-formulario+señal por links del niño, C3 /agenda, C4 promo madre+borrado one-off, C6 fotos); rescate del histórico (`scripts/migrar_historico_prueba.py`): backup JSON 75+8 en `backups/2026-07-13/`, **34 reservas históricas con PRESENTE + 11 caras re-indexadas en Rekognition bajo el nino_id**, idempotente; **−419 líneas de código legacy** (funciones, endpoints /checkin/prueba + /enviar-qr-prueba, constante _PRUEBAS); "resumen anuncios" migró a PAGOS; **tabla RENOMBRADA a "PRUEBA FENIX LEGACY"** (canario ~30 días → la borra Iván). **(C) FAMILIAS F5+F6+F7.a:** juego link mágico por TUTOR (`TUTORES.CODIGO`, `_tutor_por_codigo`, hijos por links del tutor — 0 códigos repartidos, sin backfill); facturas por TUTOR (`TUTORES.FACTURA`+`FACTURAS.TUTOR`+lookup `TUTOR RUC`, backfill 3+1; **el "robot facturador" es NUESTRO —`Projects\facturador-set`, PC de Iván— no externo**; commit `ccb5089` con fallback legacy); F7.a: PAGOS y FACTURAS ya NO linkean FAMILIA FENIX (`registrar_pago_fenix` resuelve por grupo familiar). **BUG LATENTE cazado:** `buscar_reservas_familia`/`cancelar_reservas_familia_fecha` usan `FIND(record_id, ARRAYJOIN({link}))` que **NUNCA matchea** (verificado: 0 resultados con 2 reservas) — la señal B7 dependía de eso; migrada a links del niño (`agenda._cancelar` aún depende de la 2ª, anotado para F7.b). **OPERATIVO para Iván:** vencimientos ahora en NIÑOS (`VENCE EL`/`AL DÍA?`); si la vista PAGOS FENIX filtra por FAMILIA FENIX → cambiar a `{NIÑOS FENIX}!=''`. **Falta F7.b** (las ALTAS todavía crean FAMILIAS — worklist completo en memoria `migracion-familias-pendiente`) para poder archivar FAMILIAS. |
| 2026-07-13 (madrugada 2 — MIGRACIÓN FAMILIAS→NIÑO paso 3 NÚCLEO en producción) | **Iván levantó la espera al 18/07 ("quiero la migración completa ahora") → el código migró al modelo niño-eje en 6 deploys incrementales (C0-C6, `f943b71`→`758fb8c`), cada uno SUCCESS + verificado antes del siguiente.** **C0**: campo **`NIÑOS.ESTADO`** (`fldayrwUxsXRwru8O`, ACTIVO/PAUSADO/BAJA/A PRUEBA) + backfill 59/105 desde ESTADO PLAN (`scripts/backfill_estado_ninos.py`) — 105/105 coinciden con su familia; vacío = cliente (misma semántica que `familia_es_activa`). **C1**: `registrar_pago_fenix` **dual-write** — el PAGO linkea a los hermanos (`NIÑOS FENIX`) y al pagador (`PAGA`: cel del que manda el comprobante → ES QUIEN PAGA → único tutor) además de FAMILIA FENIX; el **guard anti-dup lee la UNIÓN `FAMILIAS.PAGOS ∪ NIÑOS.PAGOS`** (sobrevive al corte futuro); si la derivación falla el pago se crea igual (nunca se pierde). **C2**: ídem los 2 POSTs de "cargar familia" (matrícula+plan). **C3**: `crear_nino` espeja el ESTADO PLAN de la familia; la inscripción **promueve a ACTIVO** los niños reutilizados de la prueba. **C4**: la confirmación del sábado lee **`NIÑOS.AL DÍA?`** y agrupa por tutor pagador vía PADRE/MADRE (`obtener_ninos_al_dia` reemplaza a `obtener_familias_para_confirmacion`) — verificado: 10 teléfonos idénticos vs el modelo viejo. **C5**: las reservas del contexto Aurora salen de los **links `RESERVAS FENIX` del niño** (RECORD_ID), no de `FIND(nombre_familia,...)` — **mató el bug A8**: verificado que las 5 diferencias eran falsos positivos del método viejo, incluida una **fuga entre las DOS "FAMILIA Britez" duplicadas** (una veía la reserva de la otra). **C6**: **router niño-eje** `es_cliente_activo_por_telefono` (TUTOR por CELL LIMPIO → cliente si ≥1 hijo con ESTADO ≠ A PRUEBA) en los 2 call sites (lead nuevo + nocturno), con **fallback legacy a FAMILIAS** cuando el tutor no existe o no tiene hijos linkeados (10 fichas incompletas conservan su ruteo) — verificado con los 109 tutores: única corrección real = Rosa Duarte (hijo A PRUEBA con familia sin ESTADO PLAN → el viejo la mandaba MAL a Aurora). **Gap conocido**: cambios manuales de ESTADO PLAN en FAMILIAS (PAUSADO/BAJA) no se espejan al niño (hoy no altera el ruteo). **Quedan como fases propias**: juego (`CODIGO FENIX` por niño), facturas/robot externo, `/api/*`+resúmenes+broadcasts+QR familia, `familia_id`→`tutor_id`, corte de escrituras → congelar FAMILIAS. |
| 2026-07-13 (madrugada — cache en los 4 agentes + M1/M2 de la migración FAMILIAS→NIÑO) | **(1) Auditoría de prompt cache en los 4 agentes**, medida con llamadas reales a la API (no por lectura de código): **Dorita SANO** (escribe y **lee ~7.084 tokens**, prompt grande y bloque estable — no se tocó); **NEO tenía el cache MUERTO** con el mismo bug doble que FENIX (la hora `%H:%M` dentro del bloque cacheado **y** un prefijo de solo ~2.2k tokens, por debajo del mínimo → la API ignoraba el `cache_control` **en silencio**) → arreglado igual que FENIX: system en dos bloques + breakpoint en el mensaje del usuario; medido: **cachea a partir de ~30 mensajes de historial** (NEO manda hasta 50, así que las conversaciones largas —las caras— ahora cachean). **Genesis: diseño correcto** (ya tenía el system en 2 bloques con la fecha/hora afuera) pero su system son ~540 tokens y nunca llega al mínimo → `r0/w0` es lo esperado; empieza a cachear solo si el prompt del cliente crece. A los **4** se les agregó el log **`cache r/w` por llamada** para que esto no vuelva a ser invisible. Commits: NEO `42213b8` (rama **master**), Dorita `f6b26af` (main), Genesis `ea6f67f` (master) — los 3 deploys SUCCESS. **(2) Decisión de diseño de la migración FAMILIAS** (Iván): los pagos de familias con varios hijos **no se parten** — un pago se carga UNA vez y su campo de niños apunta a los 2-3 hermanos. Motivo verificado con datos: el **31% de las familias tienen 2-3 hijos** (24 de 77) y el precio de la cuota **no es lineal** (1 hijo 240k · 2 hijos 340k · 3 hijos 440k), así que partirlo obligaría a inventar un reparto artificial que no corresponde a ningún precio real. **(3) M1+M2 EJECUTADOS en Airtable** (commit `16e2f46`, script `scripts/backfill_ninos_tutores_pagos.py`) — **aditivo, nada viejo se tocó** (FAMILIA / FAMILIA FENIX intactos, el agente en prod sigue igual): campos nuevos **PAGOS.NIÑOS FENIX** (link múltiple) + **PAGOS.PAGA** (link a TUTORES), **NIÑOS.PADRE / NIÑOS.MADRE** (link a TUTORES), **NIÑOS.VENCE EL** (rollup MAX de los pagos del niño) y **NIÑOS.AL DÍA?** (misma fórmula que FAMILIAS, por niño); inversos en TUTORES renombrados a HIJOS (COMO PADRE)/(COMO MADRE). **Backfill**: 102/105 niños con padre y/o madre, 62 pagos linkeados a sus niños, y **15 pagos cubren 2-3 hermanos con UN solo registro** (ej.: un pago de 700k cubre a Mauro y Bruno Niz Paredes → los dos quedan ✅ AL DÍA solos). **Verificado contra los datos: el `AL DÍA?` del niño coincide con el de su familia en los 103 comparables — 0 discrepancias.** **Dato sucio encontrado:** hay pagos de familias de FENIX cargados con `FUENTE='SALSA SOUL STUDIO'` (FAMILIA Molinas Silva, concepto F.SUSCRIPCION) → el criterio correcto para "pago de Fenix" es **tener FAMILIA FENIX**, NO la FUENTE (filtrar por FUENTE deja niños sin VENCE EL). **Falta solo el paso 3: migrar el CÓDIGO** a los campos nuevos — espera al 18/07 porque toca los mismos archivos que la migración PRUEBA. |
| 2026-07-12/13 (auditoría completa del proyecto + 21 fixes en prod) | **Auditoría de TODO el proyecto con 6 agentes en paralelo** (núcleo, datos/Airtable, dinero, IA/conversación, background/integraciones, Mundo Fenix/endpoints) → ~70 hallazgos con archivo:línea, consolidados en **`docs/estado/AUDITORIA-2026-07-12.md`** (fuente de verdad: leerlo antes de atacar cualquier fix). Ejecutados **21 pushes en fenix + 1 en pagos-bancard**, uno por cambio, todos SUCCESS y verificados en prod. **CRÍTICOS cerrados:** (1) **PII de menores expuesta** — `/api/alumnos`, `/api/reservas`, `/api/alumno` devolvían nombre+foto+fecha de nacimiento+**celulares de los padres** sin auth y con CORS abierto → ahora exigen `X-ADMIN-KEY` (o `?k=`); `/checkin/prueba/{tel}` era **enumerable** probando números → token HMAC en el QR; `/checkin/{record_id}` marcaba PRESENTE en un **GET** (un prefetch marcaba asistencia) → ahora botón + POST; `/juego/dia` (TV pública) muestra solo la inicial del apellido. (2) **Dedup que perdía mensajes**: cualquier error de DB (timeout) se leía como "duplicado" y el mensaje del lead se descartaba sin log → solo `IntegrityError` cuenta. (3) **`providers/meta.py` ciego**: los envíos no manejaban errores de red (el monitor no veía "Meta inalcanzable") y los textos >4096 fallaban con 400 → helper único `_post_mensajes` + split. (4) **`max_records=100` truncando YA**: con 105 niños había alumnos invisibles en la web y broadcasts perdiendo familias → tope 1000 en 8 call sites (`/api/alumnos` pasó de 100 a 105). **DINERO:** guard anti-duplicado en los PAGOS de "cargar familia"; dedup de pago-tarjeta exenta de la purga de 24h (un replay duplicaba el PAGO); **firma del link de tarjeta cubre el teléfono** (cross-repo con `pagos-bancard`, rama `master` — antes se podía editar `?cliente=` y atribuir el pago a otra familia; verificadas 5 combinaciones contra prod); ayuda de `/agenda` con montos vigentes (decía 90/120mil → se cobraba de menos); **rescate del lead pagado que no completa el formulario** (+2h re-envía el Flow, +24h cae a agenda por texto; recordatorios en Postgres, clamp nocturno); aviso al admin ante un posible segundo comprobante. **PLATA/CALIDAD:** **el prompt cache no funcionaba** (la hora `%H:%M` invalidaba el bloque cada minuto **y** el prefijo ~4350 tokens quedaba bajo el mínimo real de Haiku) → system en 2 bloques + breakpoint en el mensaje del usuario; verificado con la API real (w6783 → r6783) y el log ahora muestra `cache r/w`. **`tests/test_local.py` estaba roto** (importaba funciones de Nixie eliminadas; pytest ni recolectaba) → **30 tests pasan**. **Telegram arreglado de raíz**: el grupo REGISTRADO del topic en la DB gana sobre cualquier default/override, y el recovery recrea en el grupo del agente → muere el "topic que rebota" en los ~8 call sites. **Reagendar** crea la reserva nueva ANTES de borrar las viejas (un fallo dejaba a la familia sin reserva). Año dinámico en la fecha del formulario (2026 hardcodeado). CAPI con `event_id` (Purchase duplicado inflaba Ads). Monitor: loop de confirmación del sábado vigilado, shutdown cancela todos los tasks, radar de leads sin respuesta a 6h. Fixes menores: `_hoy_cls` NameError (Aurora mostraba fechas ISO crudas), "resumen asistencia" lo capturaba el comando de pasar lista, bloque duplicado inalcanzable. **Decisión de arquitectura: eliminar FAMILIAS FENIX** (niño como eje de la cuota + tutores linkeados al niño) — aprobada, **en pausa** hasta cerrar PRUEBA; inventario de ~45 puntos de contacto y 5 huesos duros en el doc de auditoría. |
| 2026-07-12 (sesión tarde — pendiente 263 cerrado + control de género en Airtable + diseño Sábado v2 del juego; NO tocó código de producción) | **Sesión de datos + diseño. Cero deploys de código.** **(1) Pendiente 263 CERRADO** — cargadas las 2 familias con tutor "Lead" que faltaban, verificando cada dato contra las conversaciones reales de prod (`/conversacion/{tel}`): **Carmen Vergara** (595971318506) → tutor renombrado (Mamá, CI 4616111-2) + niño **Santiago Guayuan** creado (HOMBRE, nac 2021-09-14); **Leticia Méndez** (595973652111) → tutor renombrado (Mamá) + **Valentina Buey** creada (MUJER, 2022-10-27) + **Abigail Buey** completada (apellido/fecha/sexo — ya existía a medias). Los dos tutores estaban además como PARENTESCO "Papá" siendo mamás → corregido. Rosa Marciana Duarte la cargó Iván. La memoria decía "Leticia falta Valentina" pero Airtable ya tenía a Abigail → **mirar antes de crear evitó un duplicado**. **(2) Control de sexo/parentesco** (pedido de Iván, para el saludo campeón/campeona del juego): auditados **105 niños + 110 tutores** con `scratchpad/control_sexo.py` (baja por API con el token data-only + heurístico de nombres, paginado). Corregidos 3: **Hannah Rojas**→MUJER, **Milagros López**→MUJER (estaban HOMBRE), **Nayila Duarte**→Mamá (estaba Papá). Resto coherente. **(3) Diseño "Mecánica del Sábado v2"** documentado en `mundo-fenix/PLAN-MAESTRO.md` §11 (trackeado): vencer al dragón = 3 misiones en casa + 7 vueltas (que **desbloquean** el desafío, NO dan insignia) + superar el desafío → la insignia (**genérica**) se otorga con el **SÍ de Iván por WhatsApp** post-cierre (anti-abuso: nada automático); el entrenamiento lo **abre/cierra el profe por comando de WhatsApp**; 10 vueltas = caja mágica. **Los guiones de voz de George reescritos quedaron NEUTROS** (desaparecieron "campeón"/"héroe" → el sexo casi no se necesita en audios; solo el de Tesoro, pendiente, tendría género — el control de género del punto 2 valió igual como calidad de datos). Verificado en código que la base ya existe (`vuelta-face`/`juego_vueltas` cuentan vueltas por día, `/juego/dia`+`lista.html`, `PLATA_VUELTA=100`, `mision-casa`/`CASA_META=3`, `dragon-vencido`, patrón `_admin_espera_respuesta`). **NADA implementado — solo diseño.** Iván primero eligió "insignia automática en la 7ma vuelta" y se retractó ("error mío") → quedó con el SÍ manual. Abiertas: video de felicitación (genérico/por niño), texto del audio de Tesoro. |
| 2026-07-12 (sesión — MIGRACIÓN eliminar PRUEBA FENIX: FASE 0 + FASE 1 + FASE 2.B completas) | **Arranque de la migración final para ELIMINAR la tabla PRUEBA FENIX** (la "identidad triplicada": el lead vivía en LEADS + PRUEBA + FAMILIAS/NIÑOS). Plan por fases aprobado por Iván (research con 3 agentes exploradores + 1 de diseño; plan en `~/.claude/plans/concurrent-beaming-crown.md`). **Concepto clave:** "niño de prueba" pasa de `PRUEBA con NOT(INSCRIPTO)` a **RESERVA cuya FAMILIA tiene ESTADO PLAN="A PRUEBA"**; fecha/hora salen de HORARIOS (muere el doble formato texto/ISO); conversión→LEADS; monto→PAGOS (M1 ya hecho). **Decisiones de Iván:** histórico = backup + tabla renombrada a "PRUEBA FENIX LEGACY" congelada ~30 días (la borra él); comando `resumen prueba` **eliminado**, no se reconstruye. **FASE 0** (`e503147`): lookup `ESTADO PLAN` creado en RESERVAS FENIX por Metadata API (token Dorita) + `es_prueba` en `obtener_ninos_por_horario` (cambio aditivo, no-op) + backup preventivo en `backups/2026-07-12/` (75 PRUEBA + 10 ASISTENCIA, paginado). **FASE 1** — gaps de dual-write cerrados: reagendamiento de Ivan ahora crea la RESERVA real (`aae04e4`) + guard "ya existe PRUEBA" post-formulario asegura familia+reserva (dentro de `d2b3b33`). **FASE 2.B — reapuntar TODAS las lecturas** (B1-B7, `f0c2bd2`→`a85b786`): **B1** contexto Aurora solo desde RESERVAS — **corrigió un bug ACTIVO de doble conteo** (sumaba RESERVAS dual-write + registros PRUEBA de los mismos niños, Aurora inflaba los agendados a los leads); **B2** resúmenes reservas/flias/telegram (helper `_tutor_de_familia`, split por `es_prueba`); **B3** asistencia interactiva del sábado (lista, ok/números, PRESENTE nombre — todo patchea RESERVAS, 🔥=prueba, se fue el parámetro `solo_prueba`); **B4** resumen asis + **comando `resumen prueba` RETIRADO** (−243 líneas, menú secre sin ítem 5); **B5** web pública `/api/reservas` y `/api/alumnos` (split por es_prueba / ESTADO PLAN, TODO paginación >100); **B6** QR de check-in apunta a la RESERVA (`/checkin/{reserva_id}`, fallback legacy a PRUEBA hasta 2.D) + `/checkin` crea fila en ASISTENCIA; **B7** señal de reagendamiento OR (PRUEBA existente **o** familia A PRUEBA con reservas futuras — a prueba del corte de 2.C) + `obtener_nombre_nino` sin fallback PRUEBA. Cada push: compila + deploy Railway SUCCESS + verificado en seco contra datos reales del sábado 11/07 y prod. **Resultado: PRUEBA FENIX ya no es fuente de lectura de nada operativo — solo quedan las escrituras (dual-write).** **PENDIENTE:** sábado 18/07 = prueba de fuego de 2.B en vivo; después **2.C** cortar escrituras (C1-C6, el guard del formulario se voltea recién en C2 — comentado en el código); tras 2 sábados OK, **2.D** backfill histórico + backup + limpieza de código + rename tabla. Estado completo en memoria `project_migracion_pago`. Dato sucio conocido: reserva duplicada de Fiorella González 11/07 11:00. Coordinación: corrió en paralelo la sesión del Espejo/confirmación-sábado — commits intercalados, un hunk mío (Push 1.2) viajó dentro de un commit ajeno (lección en `errores-aprendidos.md`: stage+commit+push atómico con sesiones paralelas). |
| 2026-07-12 (sesión — bug topics Telegram + reserva por formulario Meta) | **(1) Bug de topics MÚLTIPLES en Telegram RESUELTO.** Un mismo número (sobre todo familias) abría varios temas: `obtener_o_crear_topic` crea un topic NUEVO cada vez que el grupo destino ≠ el guardado, y había DOS fuentes de verdad del grupo peleándose — el flujo usa `agent_actual` pero los 3 followups (`loops.py`) y el envío de QR (`main.py:1428`) forzaban el grupo de LEADS. Para familias: followup→LEADS, mensaje→FLIAS, cada salto = 1 topic. Evidencia dura en la DB: **15 de 25 familias** tenían su topic en el grupo equivocado. Fix `022b655` (followups) + `ea1cdab` (QR): todos usan `grupo_telegram_para(telefono)`. **Realineadas las 13 familias** desalineadas a FLIAS por script (crear topic en FLIAS + cerrar el viejo en LEADS + update DB). Nombres reales de los grupos: LEADS = **"FENIX KIDS RESERVAS"** (nombre confuso), FLIAS = **"☀️FLIAS FENIX"**, monitor = "THE GUARDIAN", notificaciones = "ALERTAS FENIX". **(2) Reserva por FORMULARIO Meta** (`6ced372` código + `f84b3f7` prompt): tras el pago, y ANTES de ofrecer las fechas, se manda el formulario nativo de Meta (reusa el Flow `fenix_cargar_nino` / `FLOW_CARGAR_NINO_ID`) para completar niño (nombre/apellido/CI/fecha nac) + padre y madre opcionales (nombre/apellido/CI/tel/email/fecha nac). Al completarlo, `agent/formulario_reserva.py` **ACTUALIZA** FAMILIA/NIÑO/TUTORES a prueba sin duplicar (resuelve el caso tel del form ≠ WhatsApp) y recién ahí ofrece la agenda. Reemplaza el pedido de datos por texto (frágil: no propagaba a FAMILIA/NIÑO, solo a PRUEBA). Fallback a agenda directa si el form no sale. Origen: análisis del endpoint 595981900294 (Mel Antonella) donde la mamá se confundió con el horario y los datos del padre nunca llegaron al niño. **PENDIENTE: probar end-to-end en WhatsApp real** (pago → formulario → agenda → reserva). |
| 2026-07-12 (sesión — confirmación proactiva del sábado + QR solo para leads) | **Feature nuevo: reservas de familias por confirmación proactiva. El flujo de leads no se tocó; corrió en paralelo con la sesión de migración de reservas (commits intercalados).** **(1) Plantilla `confirmacion_sabado_fenix`** (UTILITY, es_AR, botones Sí/No, APPROVED en minutos): creada por API con el **token de FENIX contra su WABA propio `896276490105251`** — se confirmó en la práctica que el token de Fenix SÍ administra su WABA (el skill `/plantilla` decía lo contrario, WABA compartido + token Dorita → **corregido**, commit `d2b3b33`). **(2) Feature** (`ca1ceb3`, `agent/confirmacion_sabado.py` nuevo + `loops.py` + `main.py` + `airtable_client.py`): los jueves 9AM PY Aurora manda la plantilla a las familias con pago al día (`AL DÍA?`=✅, al tutor que paga) preguntando si el hijo viene el sábado. Botón Sí → Aurora pregunta el turno (11:00/15:30) con botones interactivos → agenda a todos los hijos (fecha calculada en Python). Botón No → no reserva. Estado en flag DB `esperando_confirmacion_sabado`; la respuesta de plantilla llega como `tipo=="button"` sin id → se rutea por el flag. **(3) QR solo para leads**: las familias ya no usan QR (check-in facial) — se sacó el botón "QR familia" de `alumno_menu` y el QR post-reserva cuando `agent_actual=="aurora"` en main.py; leads intactos. **(4) La reserva por chat de familias SE MANTIENE** como fallback. **El loop está APAGADO por default** (`CONFIRMACION_SABADO_ACTIVA`) — verificado en prod: deploy SUCCESS + log `[CONF-SAB] Próximo envío jueves en 101.7h (2026-07-16 09:00 PY)`. Pendiente: probar Sí/No con 1 número → prender el env. Caso borde: familias A PRUEBA al día podrían caer en el flujo de leads. Aprendizaje: sesiones paralelas + git (nunca `git add -a`) en `errores-aprendidos.md` + memoria `feedback_dos_sesiones_git`. |

> Las filas anteriores a esta lista viven en [`FENIX_RESUMEN_archivo.md`](FENIX_RESUMEN_archivo.md).
