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
| `JUEGO_ESTACIONES` | ⚠️ **`quincho,basket`** en Railway (07/08) — default del código `ninja,gym,basket,quincho` (4 estaciones desde el 11/08) | Estaciones del circuito NFC. Los `id` deben matchear el `estacion_id` de los ESP32 y del `mapa.html`. **Una vuelta exige tocar TODAS las de esta lista** → agregar una estación acá sin montarla físicamente bloquea el cierre de vueltas (#296). Faltan: habilitar `gym` (armada, #300) y armar `ninja` (#301). |
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
| 283 | JUEGO — completar `JUEGO_ESTACIONES` con las **4** (`ninja,gym,basket,quincho`) a medida que se arman. 07/08: `quincho`→`quincho,basket`. 11/08: el circuito pasó de 5 a 4 estaciones (`arbol`→`gym`, sale `muelle`) y `gym` quedó armada pero **sin habilitar** | 🔄 En progreso (2 de 4 activas · 3 de 4 armadas) |
| 284 | HARDWARE — armar las estaciones del circuito: soldar header al RC522, cablear, flashear `firmware/estacion/` con su `ESTACION_ID`, powerbank o fuente fija in situ. **`quincho` (25/07), `basket` (07/08) y `gym` (11/08) armadas y verificadas**; falta `ninja` (#301). Carcasa/LED WS2811 quedan de mejora, no bloqueantes | 🔄 3 de 4 |
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
| 299 | **Fase N3 — vincular pulseras** a niños reales: hoy los taps responden `pulsera_no_vinculada` y no cuentan | ⏳ Pendiente |
| 300 | ⚠️ **Habilitar `gym` en `JUEGO_ESTACIONES`** — el hardware está armado y verificado (11/08) pero la variable sigue en `quincho,basket`. Hacerlo **solo cuando la caja esté montada y enchufada**: con `gym` activa, una vuelta exige las TRES. Es variable + `serviceInstanceRedeploy`, 1 minuto | ⏳ Pendiente |
| 301 | **Armar la estación `ninja`** — la última de las 4. ⚠️ **Probar el RC522 con `banco_lector` ANTES de soldarle el header**: el 11/08 uno vino fallado de fábrica y costó ~1h (pasa `VersionReg`, bus y antena, y no lee) | ⏳ Pendiente |
| 302 | **Alinear `mundo-fenix/mapa.html`** — su array `STATIONS` todavía tiene `arbol` y `muelle`. No urgente (los niños ya no se muestran en el mapa desde el 11/07, quedó de reposo). Al hacerlo, decidir dónde va el ícono de `gym`: es interior y el tótem ya ocupa el centro de la casona (`x:50,y:36`) | ⏳ Pendiente |
| 303 | **En `lista.html` el nombre del niño queda en 0px con 16+ chicos** (3 columnas) — bug **preexistente**, medido el 11/08 sobre la versión original. Se arregla igual que el resto: sacando otro chip de la fila. No tocado por estar fuera del scope | ⏳ Pendiente |
| 300 | **Probar en vivo el saludo por número**: pedirle a Gaudi (595991921375) o Ilse (595981102495) que escriban "hola" y confirmar que Aurora las saluda con **su propio** nombre. Es el único paso del fix del 08/08 que no se verificó con un mensaje real | ⏳ Pendiente |
| 301 | ⚠️ **Aurora alucina datos cuando se queda sin contexto** — el 07/08 le afirmó a Ilse una reserva del sábado 8 que **no existía**. Se corrigió la causa de ese caso (identidad), pero un `obtener_grupo_familiar → None` se sigue tratando como caso normal. Evaluar tratarlo como error explícito o prohibir en el prompt afirmar reservas sin contexto | ⏳ Pendiente |
| 302 | `crear_o_actualizar_tutor` (`airtable_client.py:611`) busca idempotencia solo por `{TELEFONO LIMPIO}` exacto → si alguien se inscribe con un número que vive en el `TELEFONO2` de otra fila, crea **duplicado**. Hoy solo Gaudi tiene TELEFONO2 (riesgo bajo) | ✅ Hecho 09/08 (`df29ae7`: busca por los dos números) |
| 303 | **Probar el ciclo completo en vivo** (lead → alias + link de tarjeta → comprobante → PAGO con `PAGA (ALUMNOS)` → formulario → reserva) — los 2 intentos del 09/08 cayeron en bugs ya arreglados | ⏳ Pendiente |
| 304 | **Borrar `TUTORES FENIX LEGACY`** (~08/09). ANTES: sacar `{TUTOR RUC}` viejo del `NEG1_FILTRO` del robot, de la cadena de `facturador-set/airtable.py` y el fallback de `obtener_contacto_tutor` — un lookup muerto en el filtro = 422 y NEG1 entero deja de facturar | ⏳ Pendiente |
| 305 | Cruzar comprobantes del topic de Telegram vs filas de PAGOS **desde el 25/07** — saber si se perdió algún pago real por el bug del link `PAGA` | ⏳ Pendiente |
| 306 | Medios del doc de auditoría sin tocar: aviso de saldo en QR/HQ (hoy solo facial), saldo negativo repite "era la última clase", hora en el prefijo cacheado, links de tarjeta sin expiración, CAPI Purchase sin `value` | ⏳ Pendiente |
| 307 | ~~**Primer contacto del Desafío**~~ — los 3 trabajos hechos y en prod (`4f36436`, `2d314d3`, `055d99f`): camino propio para el que viene de la web a pagar con tarjeta, saludo que cuenta el campus + foto de La Casona, y "agendar llamada" con aviso al admin. **Falta probarlo desde un WhatsApp real** | ✅ Hecho 10/08 (sin verificar en vivo) |
| 308 | **Probar el Desafío end-to-end en vivo**: pago → formulario → turnos, verificando en Airtable `CONCEPTO=DESAFIO` y las **3 reservas**. Nunca se pudo ejercer sin un mensaje entrante real | ⏳ Pendiente |
| 309 | ~~Definir las 3 opciones de horario de "agendar llamada"~~ — **ya no aplica**: Iván decidió (10/08) que NO se pregunta la hora. Se pide el nombre y le llega un WhatsApp con link `wa.me` prellenado para contactar de un clic | ✅ Resuelto por decisión |
| 313 | **`_admin_modo_padre` vive en memoria del proceso** (`main.py:157`) → cada deploy devuelve al admin a modo secre, donde el agente **no responde nada** y se ve idéntico a estar muerto (perdió 20 min el 10/08). Mover a flags de DB, igual que `_fotos_sesion`, `_asistencia_pendiente` e `_inscripcion_pendiente` (ya estaba en `AUDITORIA-2026-07-12.md:144`) | ⏳ Pendiente |
| 314 | **`static/afiche_horarios.png` es una copia exacta de `afiche_fenix.png`** (md5 `93b52709…` los dos): quien pide horarios recibe el afiche de precios. Por eso el paquete de info manda el afiche una sola vez. Diseñar el afiche real de horarios o dejarlo en texto | ⏳ Pendiente |
| 310 | El afiche tiene un "GRAN DESAFÍO **FÉNIX**" con tilde (domingo 12:00, letra chica) — Iván decidió dejarlo así por ahora | ⏳ Decidido dejarlo |
| 311 | `pagos-bancard` rechaza para fenix cualquier link cuya firma no cubra el teléfono (`main.py:341-343`). Hoy no molesta porque los links salen del agente, pero **cualquier cobro futuro desde una web va a fallar igual** (pasó con los links de pack y matrícula, rotos desde el 12/07) | ⏳ Pendiente |
| 312 | Los `.md` internos de Mundo Fenix son accesibles públicamente (`mundo-fenix.pages.dev/COMPRAS-Y-PENDIENTES.md`, los `SPEC-*`) — viene de deploys viejos, el direct upload sube el directorio entero | ⏳ Pendiente |
| 315 | **Controlar si Google indexó la web** (pedido el 12/08 desde Search Console): Inspección de URLs → `https://fenixkidsacademy.com/` debe decir "La URL está en Google". Si a los 10 días sigue afuera, revisar cobertura y backlinks | ⏳ Pendiente |
| 316 | Cargar en la ficha de Google Business los 4 turnos de 90 min (vie 17:00-18:30 y 19:30-21:00 · sáb 11:00-12:30 y 15:30-17:00) — la web ya los publica en su JSON-LD | ⏳ Operacional |
| 317 | `desafio.html` tiene **"350.000 Gs" escrito a mano en la meta description** — queda viejo al pasar a 550k. Sumar ese lugar al skill `/cambioprecio` | ⏳ Pendiente |
| 318 | **Ver el re-chequeo del router disparándose solo** (`3849372`): buscar en logs de Railway `[ROUTER] ... ahora es inscripto → promovido a Aurora`. Los 16 del 14/08 se promovieron a mano — el camino automático nunca corrió con un mensaje real | ⏳ Pendiente |
| 319 | **Decisión de negocio:** el criterio del router es `ESTADO2 ≠ 'A PRUEBA'` → incluye **BAJA** y sin-estado. Los 5 congelados con hijo BAJA quedaron en Aurora. Si una familia dada de baja debe volver al flujo de venta, hay que cambiar el criterio | ⏳ Decisión de Iván |
| 320 | **`programar_llamada` no verifica que la llamada ocurra**: Nayila pidió el retorno 5 veces (03/07→10/07) y el bot prometió "te llama en unos minutos" cada vez, sin seguimiento. Evaluar que el Monitor alerte cuando una llamada prometida no se registró | ⏳ Pendiente |
| 321 | Mover el script de auditoría de congelados (Postgres × Airtable, quedó en el scratchpad del 14/08) a `scripts/` si se va a correr seguido — hoy da 0 y tiene que seguir dando 0 | ⏳ Pendiente |

---

## 12. Historial de Cambios

| Fecha | Cambio realizado |
|---|---|
| 2026-08-14 (noche — Caso Nayila) | **4 commits (`3849372`→`43f46a1`), todos SUCCESS.** `/endpoint nayila duarte`: a una **alumna regular** le vendieron el Desafío con su SOLD OUT, le dijeron "mañana horario normal" siendo **feriado**, y le confirmaron que sus 240.000 eran "el paquete de 5 clases". **Una sola causa raíz:** el router leads/alumno corría únicamente dentro de `if es_nuevo:` → la que se inscribió por fuera del bot quedó en modo lead **para siempre**, y con ese modo el sistema le inyecta a Haiku el contexto de venta del campus en vez del aviso de feriado. Fix: **re-chequeo throttled de 24h** (`router_recheck_ts`) que promueve a Aurora, sin cortar flujos de lead activos. Dos agravantes arreglados aparte: el `aurora_prompt` tenía la semántica VIEJA de feriado peleando contra el aviso del sistema, y ningún prompt prohibía inventar a qué corresponde un pago. Auditoría en prod: **15 clientes más congelados** en modo lead → los 16 promovidos, re-corrida en **0**. Regla 14 completada (el sistema decide **y re-decide**). **Detalle en `.claude/handoffs/handoff_20260814_2057.md`.** |
| 2026-08-13 (noche — Identidad la decide el sistema) | **5 commits (`0698805`→`79887e3`), todos SUCCESS.** `/endpoint 595981683435`: Aurora llamó "Jorge" (el papá) a Jazmin (la mamá) toda la conversación — el contexto decía JAZMIN pero el historial viejo pesó más, `GENERO` vacío en ALUMNOS dejaba a los tutores sin etiqueta MADRE/PADRE, y el "ya anoté tu nombre ✅" fue mentira (0 tools en el log). Fix en 4 frentes: **saludo determinístico** de inscriptos (template + nombre de Airtable, sin Haiku, `alumno_menu.py`), `registrar_familia` acepta la corrección del propio nombre y completa GENERO, regla de identidad en `aurora_prompt` (el CONTEXTO manda sobre el historial), y los **topics de Telegram se renombran** cuando el nombre resuelto cambió. GENERO cargado a mano en las filas de Jazmin y Jorge. Regla 14 nueva en CLAUDE.md. **Detalle en `.claude/handoffs/handoff_20260814_0116.md`.** |
| 2026-08-12 (noche — Sold out) | **4 commits en el agente (`7cc5151`→`58f0e91`) + 1 en la web (`f18d456`), todos SUCCESS.** El primer Desafío se llenó: **SOLD OUT del campus 14-16** vía `CAMPUS_AGOTADOS` (por fecha, se apaga solo) — `proximo_campus()` lo saltea y precio (350k hasta el jueves 20), turnos completos, botones, textos, links firmados, contador y web pasaron **solos** al 21-23. Cartel rojo SOLD OUT en hero y bandas + la línea en saludo/precios/horarios + el bloque del LLM (no cede ni al "metele un lugarcito"). **Corrección de Iván:** el feriado NO tiene entrenamiento regular para nadie (los turnos especiales son sesiones del campus) → `hay_entrenamiento_regular()` consumida por el aviso a Aurora ("la respuesta es NO"), el pre-hook y las 3 fuentes de horarios. Queda en manos de Iván avisarle a Fiorella (reserva viva el sáb 15). **Detalle en `.claude/handoffs/handoff_20260812_2330.md`.** |
| 2026-08-12 (la web entra a Google) | **5 commits en `fenixkidsacademy-web` (`9a53cbf`→`eeb5f60`), todos deployados y verificados por contenido; el repo del agente no se tocó.** El sitio **no estaba indexado**: nunca se lo envió a Google y no existían `robots.txt` ni `sitemap.xml` (Pages devolvía el index con 200 en esas rutas). Se sumaron los dos, más `canonical`, Open Graph absoluto y JSON-LD `SportsActivityLocation` con dirección, teléfono, edades y los 4 turnos de 90 min; el logo pasó de 2.79 MB a 187 KB. Search Console verificado por DNS + sitemap enviado + indexación pedida, y Redirect Rule `www`→apex en Cloudflare. **Dos hallazgos:** el `_redirects` de Pages **no matchea el host** (la regla nunca se aplicó), y la ficha de Google Business publicaba el **número personal de Iván** y la dirección equivocada. **Detalle en `.claude/handoffs/handoff_20260812_1601.md`.** |
| 2026-08-12 (fix feriado) | **11 commits en el agente (`807e81a`→`bec64a0`) + 1 en la web (`4c549b2`), todos SUCCESS.** El finde del 14 y 15 (feriado) corre con **un turno por día** (vie 17:00, sáb 11:00; el domingo no cambia), vía una tabla `TURNOS_ESPECIALES` **por fecha** en `agent/desafio.py` espejada en `campus.js`: se apaga sola, no hay nada que revertir el lunes. Cubre botones post-pago (un botón), textos del lead, aviso a Aurora y **validación real** (el pre-hook resuelve la fecha antes que la hora). Verificado en Airtable que los turnos caídos no tenían ninguna reserva → cero mensajes salientes (Aurora solo responde si preguntan). **El hallazgo del día:** el aviso que corrige al prompt **pierde contra el prompt** — los horarios salieron de `prompts.yaml` y ahora los inyecta el sistema siempre (`bloque_turnos_vigentes`). Una revisión posterior cazó 3 bugs más: slots fantasma de Airtable que se seguían ofreciendo, el "es feriado" que también salía cuando el turno único era por cupo, y la lista vacía al reagendar. De paso, el saludo del primer contacto pasó al copy de la web. **Detalle en `.claude/handoffs/handoff_20260812_1330.md`.** |
| 2026-08-11 (madrugada — estación `gym` armada + los fuegos de la vuelta en la TV) | **El circuito pasó a 4 estaciones** (`46bae62`: `arbol`→`gym`, sale `muelle` porque quedó dentro del recorrido de gym) y **la TV muestra el progreso de la vuelta en curso**: `/juego/dia` expone `vuelta_actual`/`estaciones_vuelta`/`faltan_vuelta` (`34604c2`, aditivo) y `lista.html` pinta un ícono grande por estación, encendido el que completó (`d4d6409`, deployado a Pages y verificado por contenido). **Estación `gym` armada y verificada** (5 lecturas, 4 tags, uno NTAG213 real) — falta habilitarla en `JUEGO_ESTACIONES`. ⚠️ Aprendizaje caro: **un RC522 puede venir FALLADO y pasar todos los tests de software** (`VersionReg`, bus, `TxControlReg` encendiendo la antena) sin leer un solo tag; y el **autotest interno NO sirve como veredicto** (falla igual en módulos buenos y malos, son clones FM17522) — el único criterio es *¿lee un tag ya probado?*. Se sumó `firmware/diagnostico_rc522/`. Detalle completo → `.claude/handoffs/handoff_20260811_0129.md` |
| 2026-08-10 (tarde — El reloj del Desafío) | **4 commits en `fenixkidsacademy-web` (`57b9dbe`, `bdf55b9`, `505649b`, `c2d3181`), los 4 deployados y verificados en `fenixkidsacademy.com`. El repo del agente no se tocó.** La web muestra en vivo cuánto falta para que cierre la reserva anticipada: plazo escrito ("cierra el jueves a las 23:59") + reloj DÍAS·HORAS·MIN·SEG repintado cada segundo, en el hero y en 2 bandas por página (después de *El diferencial* y entre Precios y FAQ). Cuenta al **jueves 23:59** hasta el viernes, y a las **17:00** el viernes mismo — un contador que apunte solo al jueves queda vencido el día de más tráfico. Todo sale de `assets/campus.js` (pinta por clase, ya no por id). **El error del día:** el deploy estaba OK y la web se veía vieja igual — el `<script src>` sin versión lo servía el cache del navegador, y verificar con navegador limpio daba un **falso OK**; se arregló con `?v=2`. **Detalle en `.claude/handoffs/handoff_20260810_1329.md`.** |
| 2026-08-10 (madrugada — El primer contacto del Desafío) | **3 commits (`4f36436`, `2d314d3`, `055d99f`), un push cada uno, los 3 deployados SUCCESS.** El primer contacto pasó a ser el campus: el que llega del botón de la web a pagar con tarjeta recibe el link firmado en vez del saludo de venta (el bug tenía **dos** puertas cerradas, no una: el menú responde antes del brain **y** el hook de `main.py:4135` no manda link con monto adivinado); el saludo cuenta el Desafío con la foto de La Casona y botones `Info y precios · Reservar lugar · Agendar llamada`; "Info y precios" manda todo de una en mensajes separados. "Agendar llamada" no pregunta la hora (decisión de Iván): pide el nombre y le manda a Iván un `wa.me` prellenado. Primer test de `lead_menu.py`: **79 → 99 tests**. De paso: los dos afiches son el mismo PNG (#314) y `modo padre` se pierde en cada deploy (#313). **Detalle en `.claude/handoffs/handoff_20260810_0224.md`.** |
| 2026-08-10 (Nace el Desafío FENIX — el campus de 3 días reemplaza a la clase de prueba) | **22 commits (16 en el agente `5caaf03`→`243087e` + 6 en la web), todos deployados SUCCESS.** Murió la clase de prueba de un sábado: la puerta de entrada es el **DESAFÍO FENIX**, campus de viernes a domingo (350.000 hasta el jueves / 550.000 desde el viernes, +150.000 por hermano). `agent/desafio.py` nuevo calcula campus, precio y cupos; los textos pasaron de constantes a funciones porque el precio depende del día. Post-pago se eligen los turnos del viernes y del sábado con botones y se crean **3 reservas**; el pago va con `CONCEPTO=DESAFIO`. En Airtable: opciones `17:00/19:30/12:00` y los 20 slots de los 4 campus. Web rehecha (home + landing `/desafio` + `campus.js` compartido) y el pago con tarjeta pasó a pedirse por WhatsApp — el cobro desde la web estaba **roto desde el 12/07** y además no inscribía a nadie. De arranque, dos bugs del pago de Iván (el PAGO sin nombre por el link `ALUMNO`, y el formulario del admin creando duplicados). **Detalle en `.claude/handoffs/handoff_20260810_0141.md`.** |
| 2026-08-09 (Adiós TUTORES FENIX — auditoría, migración completa y los caminos de silencio) | **37 commits + 1 en facturador-set, todos deployados SUCCESS.** Auditoría con 5 agentes (~50 hallazgos, `docs/estado/AUDITORIA-2026-08-09.md`) destapó que **el bot no registraba pagos desde el 25/07** (los links `PAGA`/`TUTOR FENIX` apuntaban a TUTORES legacy y recibían ids de ALUMNOS → 422 del POST entero) y que **el texto de Aurora creaba/cancelaba reservas** por regex. Se ejecutó la **Etapa 2 completa**: `CODIGO FENIX`/`FACTURA FENIX` en ALUMNOS, `FACTURAS.TUTOR (ALUMNOS)` + lookup, backfill, juego y facturas migrados, robot facturador actualizado, tabla renombrada **TUTORES FENIX LEGACY** (canario ~30 días). Dos fixes propios rompieron prod (el agente quedó **mudo** 8 min por un `import` dentro de una rama) → de ahí salió la **auditoría de caminos de silencio**: los 14 arreglados (el `except` del webhook ahora responde y alerta al admin, envío con reintento, shutdown que espera los mensajes en vuelo) + **`tests/test_webhook_no_muda.py`**, validado reintroduciendo el bug. **Detalle en `.claude/handoffs/handoff_20260809_2206.md`.** |
| 2026-08-08 (madrugada — Aurora saluda por el número: control de identidad + 2do teléfono) | El "Hola Raul" a Ilse (17/07) era un fallback que rellenaba el nombre con **el primer tutor de la lista** cuando el teléfono no identificaba a nadie — eliminado. Mirándolo apareció el problema vivo: tras la migración a ALUMNOS el WhatsApp de Ilse no resolvía (su fila tenía un **teléfono fijo**) y Aurora, sin contexto, **le inventó una reserva inexistente**. Control sobre los 24 números en modo Aurora contra el router real: **7 no resolvían**, 2 eran familias activas (Ilse y Gaudi). Campo fórmula nuevo **`TELEFONO2 LIMPIO`** en ALUMNOS + `buscar_tutor_por_telefono` busca en los dos números (Gaudi comparte fila con Salsa/Impulso: no se le pisa el principal) + helper único `tutor_tiene_telefono()` para los 4 call sites que comparaban a mano. Commits `3c0a3d7`, `13ef71e`, `bd7d88a`. **Detalle en `.claude/handoffs/handoff_20260808_0040.md`.** |
| 2026-08-07 (noche — estación NFC `basket` armada + el RC522 mudo que se destraba desenchufando) | **Segunda estación del circuito NFC terminada end-to-end.** Iván soldó el header del RC522, se cableó lector + buzzer HW-508 y se flasheó `estacion.ino` con `ESTACION_ID=basket` (mismo binario que quincho). Verificado con hardware real: `VersionReg 0x92`, WiFi OK, `UID 7B45DE00`/`3A90EF55` → `POST /juego/estacion → 200`. Se agregó `basket` a `JUEGO_ESTACIONES` en Railway (antes solo `quincho`) + redeploy → ⚠️ **una vuelta ahora exige tocar quincho Y basket**. Tres trampas de hardware: (1) el pin del **medio** del HW-508 es **GND**, no VCC — al revés da zumbido continuo; (2) boot loop `invalid header: 0xffffffff` por cableado → aislar alimentación primero, señales después; (3) **el RC522 se traba mudo** (`VersionReg` OK + cero detecciones) y **solo se destraba cortándole la alimentación** — el botón `EN` no se la corta (costó ~2h, probablemente el mismo modo de falla sin explicar del 25/07). Sin cambios en los sketches. Detalle completo → `.claude/handoffs/handoff_20260807_2318.md` |
| 2026-08-07 (Tutores mudados a ALUMNOS — Aurora muda por un TypeError) | **Aurora no le respondía a Ivan: el webhook crasheaba con `can only concatenate str (not "list") to str`.** Causa raíz: los padres/madres se mudaron a **ALUMNOS** (`NEGOCIO=FENIX KIDS ACADEMY`) pero el código del 03/08 seguía leyendo `TUTORES FENIX`, cuyos campos `HIJOS (COMO PADRE/MADRE)` quedaron como **texto** — sumarlos como listas reventaba para los 101 tutores. Fix en dos deploys: `95cb067` (identidad: `buscar_tutor_por_telefono` → ALUMNOS por `TELEFONO LIMPIO` con prioridad hijos-linkeados > NEGOCIO; links `PADRE/MADRE (ALUMNOS)`; el reset ya **no borra** la fila compartida, le quita la marca FENIX) y `3fafa06` (los callers: main/resumenes/inscripcion/formulario_reserva/confirmacion_sabado/facturas/registro). Verificado en prod: 0 errores, `/api/alumnos` devuelve 88 niños con madre y 52 con padre (antes: vacío). Detalle completo → `.claude/handoffs/handoff_20260807_1253.md` |
| 2026-07-28 (madrugada — precio nuevo: el PACK de 5 clases que no vencen + saldo por niño + aviso al padre en el check-in) | **Cambio de modelo comercial completo, de punta a punta, en una sesión: el mensual de 240k por 4 sábados murió y lo reemplazó un pack de 350k por 5 sábados que NO vencen (+150k por hermano; prueba y matrícula sin cambio).** **(1) Precio en los 7 lugares vivos** (`23580fc` código + `e7f42e5` prompt, deploys separados como manda la regla): `prompts.yaml`, `lead_menu.py` (TEXTO_PRECIOS/TEXTO_HERMANOS), `afiches.py` (msg_precios/msg_hermanos), **`main.py` × 2** (los fallbacks de texto de los interceptores cuando el afiche ya se envió — **no estaban en el mapa de la memoria, aparecieron por grep**), `reminders.py` (seguimiento A) y `pagos.py` (dict `PRECIOS` → `pack5*`; verificado: importado en main.py:78 pero **sin un solo consumidor**). Afiche nuevo (hecho por Ivan con ChatGPT) a `static/afiche_fenix.png` + convertido a JPG para la web. **(2) Web** (`61217aa`, repo `fenixkidsacademy-web`, **rama master**): card "Plan mensual" → "Pack 5 clases", tabla de hermanos 350/500/650 y **los 3 links de pago refirmados** — la `sig` es `HMAC(LINK_SECRET, "fenix:{monto}")[:16]`, así que cambiar el monto sin refirmar los deja rotos; `LINK_SECRET` se sacó de las variables de Railway por GraphQL y se validó recalculando la firma vieja de 240000 antes de generar las nuevas. **(3) Saldo de clases** (`854347c`): campos nuevos `NIÑOS FENIX.CLASES DISPONIBLES` (number) y `ULTIMO DESCUENTO` (date, gate de idempotencia). Una sola puerta —`descontar_clase()` / `recargar_pack()`— con la misma disciplina que `_acreditar` con el oro del juego. **Campo vacío = familia del mensual viejo: no se le descuenta nada** (decisión de Ivan: siguen aparte). Enganchado en los **tres** puntos que crean asistencia (cara, QR, HQ manual) — de ahí el gate diario: un niño puede pasar por más de uno el mismo sábado. Nunca baja de 0 ni bloquea la entrada del niño. Probado contra Airtable real con 7 casos (sin pack → None, +5, descuento, doble descuento mismo día, día siguiente, piso en 0) y el registro restaurado. **(4) Pagar el pack suma +5 acumulativo** (`004d745`): cargar la inscripción con "pack"/"paquete"/"5 clases"/"p5" registra el PAGO con **`CONCEPTO=PAQUETE5`** —opción que **ya existía** en el select— y suma 5 a cada niño del pago (4 que quedaban + 5 = 9). Bonus verificado: `VENCIMIENTO_FORMULA` no contempla PAQUETE5 → el pago queda **sin fecha de vencimiento**, justo lo que necesita un pack que no vence. Parser probado con positivos y negativos: mensual/trimestral/qm/sm/qt/st siguen resolviendo igual. **(5) Aviso al padre + fotos** (`1916701` + `23b82c3` en la web): plantilla **`checkin_fenix` creada y APROBADA** (WABA propio de FENIX, es_AR, UTILITY) — avisa que el hijo entró, cuántas clases le quedan (o cuándo vence su mensual) y pregunta por las fotos con botones. Los textos de botón son **"Sí, mandame fotos" / "No, gracias"**, distintos de los "Sí/No" de `confirmacion_sabado_fenix` a propósito: la respuesta llega **sin id, solo con el texto**, y se confundirían. `agent/checkin_aviso.py` nuevo maneja envío, respuesta y `avisar_fotos_listas()`; el **paso 7 de `publicar_fotos.py`** le pega a `POST /fotos/avisar-familias` cuando las fotos ya están arriba y el server le pasa el link a quien lo pidió (el pedido se limpia al enviar → no repite). El botón que toca el padre **abre la ventana de 24h**, así que el aviso de las fotos del mismo día sale como mensaje libre, sin plantilla ni costo. **APAGADO por defecto** (`AVISO_CHECKIN_ACTIVO`). **(6) Skill `/cambioprecio`** (`8d04b0e`) destilado de esta misma sesión: los 7 lugares + la web, el grep de control del valor VIEJO, las firmas HMAC, el afiche en los dos repos y los dos pushes separados, con tabla de anti-racionalizaciones. **De paso se corrigió el CLAUDE.md, que decía "4 lugares vivos"** — el mismo dato incompleto que casi deja el precio viejo en producción. Descubierto al registrarlo: un skill del proyecto solo es invocable con `/` si tiene su archivo espejo en `.claude/commands/` (`fotosfenix` no lo tiene). **Pendientes:** prender el flag y probar con el número de Ivan antes del sábado 01/08; el aviso está enganchado **solo en el check-in por cara** (QR y HQ descuentan pero no avisan); avisar a Ivan por Telegram cuando un niño llega a 0 clases. |
| 2026-07-27 (bug real del formulario de reserva: el niño se creó de más, el pago quedó huérfano — fix completo) | **`/endpoint 595981941407` (typo de Iván por 595, resuelto) destapó la primera prueba real en producción del formulario de reserva (#279), y encontró que perdió TODOS los datos del papá.** Investigación completa vía Airtable MCP (LEADS/PAGOS/TUTORES/NIÑOS FENIX) + logs de Railway (GraphQL directo a `backboard.railway.app`, filtrando por teléfono/`RESERVA-FORM`/`formulario`): el pago SÍ existía en PAGOS pero sin `NIÑOS FENIX`/`PAGA` (invisible en la vista filtrada); el niño SÍ se había creado pero por el **detector legacy de texto**, con el nombre ADIVINADO — no por el formulario. Los logs mostraron la secuencia exacta: `[formulario] llega → WARNING no encontré grupo a prueba → datos descartados → 5 min después el detector legacy crea el niño con el nombre del chat`. **Causa raíz:** `procesar_formulario_reserva` (`formulario_reserva.py`) solo sabía ACTUALIZAR un niño existente; sin grupo previo tiraba el `flow_data` completo sin persistirlo (ni DB, ni logs con contenido — solo un `warning` sin datos). Un subagente (Fable) analizó el código completo y devolvió un diagnóstico + plan de 2 commits con riesgos, que Iván simplificó a lo esencial: "que el formulario cree al niño". **Commit `7541b7e`:** `procesar_formulario_reserva` ahora CREA el niño con los datos reales si no existe (reutilizando el tutor parcial del pago sin duplicar); el contenido completo del formulario se guarda en DB y se espeja SIEMPRE a Telegram + WhatsApp del admin, ANTES de tocar Airtable; se sacó la dependencia del flag `esperando_formulario_reserva` para PROCESAR (antes, con el flag apagado, el mensaje cargaba al pipeline normal como texto `"[formulario]"` y se perdía); `prueba_creada=True` se setea al terminar — desarma el detector legacy que había pisado los datos reales en el caso real. **Commit `1a8216d`:** back-fill del PAGO huérfano — al crear/completar el niño, se buscan los PAGOs `PRUEBA` del lead sin niños linkeados y se les cuelga `NIÑOS FENIX`+`PAGA`. **Ambos pusheados y verificados en prod** (`/debug/{tel}` responde normal post-deploy en los dos). **Registrado en `memory/errores-aprendidos.md`** con la regla general: dato de fuente verificada + registro que no existe todavía → CREARLO, nunca descartar el dato; todo webhook externo se persiste crudo en DB antes de cualquier lógica. **Pendiente:** el caso puntual de Blas Páez quedó con datos reales (CI/fecha nac/mamá) irrecuperables — pedírselos de nuevo (#291); evaluar si el detector legacy de texto conviene desarmarlo del todo, no solo por interlock (#292). |

> Las filas anteriores a esta lista viven en [`FENIX_RESUMEN_archivo.md`](FENIX_RESUMEN_archivo.md).
