# FENIX KIDS ACADEMY — Documentación Completa del Sistema

> Documento de referencia para entender el sistema sin necesidad de leer el código.
> Mantener actualizado: agregar una fila en la sección 10 cada vez que se haga un cambio importante.

---

## 1. ¿Qué es este sistema?

Agente virtual de WhatsApp para **FENIX KIDS ACADEMY**, centro de entrenamiento funcional y emocional para niños de 3 a 12 años en Asunción, Paraguay (PARQUE FENIX, LA CASONA LAFUENTE, Maestras Paraguayas 2056).

Opera con **dos agentes IA** en el mismo número de WhatsApp:

- **Profe Ivan Lafuente** — atención, ventas y diagnóstico emocional
- **Nixie** — operaciones, recolección de formularios y reservas

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
| IA principal | Claude Sonnet 4.6 (`claude-sonnet-4-6`) |
| IA auxiliar | Claude Haiku (`claude-haiku-4-5-20251001`) — extracción de formularios |

### Servicios externos conectados
| Servicio | Uso |
|---|---|
| **Meta WhatsApp Cloud API** | Envío y recepción de mensajes de WhatsApp |
| **Anthropic API** | Generación de respuestas (Ivan/Nixie) y extracción de datos (Haiku) |
| **Airtable** | CRM en base Salsa Soul: LEADS FENIX, PRUEBA FENIX, FAMILIAS FENIX, NIÑOS FENIX, HORARIOS FENIX, RESERVAS FENIX, DIAGNOSTICO FENIX |
| ~~Google Calendar API~~ | **Eliminado** — ya no se usa |
| **Telegram Bot API** | Espejo de conversaciones en grupo de Telegram por topics |
| **Groq Whisper** | Transcripción de mensajes de audio de WhatsApp |

### Deployment
- **Plataforma:** Railway
- **Trigger de deploy:** automático en cada `git push` a `main` en GitHub
- **Repo:** por crear (pendiente)
- **Puerto:** 8000 (variable `PORT`)

### Archivos principales
```
agent/
  main.py           — Servidor FastAPI, webhook WhatsApp, orquestación principal
  brain.py          — Llama a Claude API, carga ivan_prompt o aurora_prompt según estado
  memory.py         — Historial de conversaciones + estado + pagos persistentes + dedup
  ab_test.py        — Estado por conversación: agente, modo, familia_id, Calendar
  pagos.py          — Flujo de pagos: comprobante, confirmación admin, precios (PostgreSQL persistente)
  airtable_client.py — Integración con Airtable base Salsa Soul (LEADS/PRUEBA/FAMILIAS/NIÑOS FENIX, etc.)
  calendar_google.py — (ELIMINADO, ya no se importa)
  telegram_bridge.py — Integración con Telegram
  reminders.py      — Recordatorios automáticos de seguimiento y formulario
  transcriber.py    — Transcripción de audios con Groq Whisper
  providers/        — Adaptador Meta WhatsApp Cloud API (botones interactivos, envío imagen)
config/
  prompts.yaml      — System prompts de Ivan y Aurora
  business.yaml     — Datos del negocio
```

---

## 3. Los Dos Agentes

### Profe Ivan Lafuente
- **Rol:** atención inicial, diagnóstico emocional, ventas
- **Activación:** por defecto en todo mensaje nuevo
- **Flujo:** rompehielos diagnóstico (15 opciones) → análisis conversacional (con delay según cantidad de números) → cierre emocional (por qué FENIX + edad) → pregunta si quiere probar → horarios/precios solo cuando corresponde
- **Transferencia a Nixie:** cuando dice exactamente *"Perfecto 🙌 En breve te contacta NIXIE, ella se va a encargar de pedirte los datos y hacerte la reserva."*

### Aurora (antes Nixie)
- **Rol:** operaciones, consultas y reservas para familias inscriptas
- **Activación:** solo cuando el teléfono del padre ya está en FAMILIAS FENIX (router automático, busca en CELL PADRE/MADRE y CELL LIMPIO)
- **Sin restricción nocturna:** padres inscriptos pueden escribir a cualquier hora
- **Onboarding (primera vez):** saluda por nombre/apodo, pregunta por hijos, verifica datos paso a paso (quien escribe → hijos → otro padre). Campo CONTROL DATOS (checkbox) en FAMILIAS FENIX marca como verificado.
- **Atención normal (post-onboarding):** saluda y atiende directo. Asume agenda para todos los hijos (multi-hijo). Confirmación con apodos.
- **Campos APODO:** APODO PADRE/MADRE en FAMILIAS, APODO en NIÑOS. Si existe, se usa para saludar y confirmar reservas.

---

## 4. Flujo Completo de Conversación

### Lead nuevo (primer mensaje)
1. Llega mensaje → se crea registro en LEADS (TELEFONO + CONVERSION=CONSULTA + AGENT_ACTUAL=IVAN)
2. Ivan responde con el rompehielos diagnóstico (15 opciones)
3. Padre elige números → Ivan valida emocionalmente → explica → propone
4. Padre acepta agendar → Ivan dice frase de transferencia → **NIXIE entra en modo `lead_nuevo`**
5. Nixie pide formulario hijo/a (uno por hijo)
6. Nixie pide formulario papá
7. Nixie pide formulario mamá
8. Haiku extrae datos del historial → si completo → crea FAMILIA + NIÑOS en Airtable
9. Nixie ofrece horarios → padre elige → **Nixie confirma reserva**
10. Sistema detecta confirmación → crea RESERVA en Airtable + evento en Google Calendar
11. Se envía link del evento al padre por WhatsApp
12. Se notifica en Telegram (grupo FENIX KIDS)

### Padre ya inscripto escribe directo
1. Padre escribe "hola nixie" (o similar) → Nixie entra en modo `cliente_inscripto`
2. Nixie pide nombre y apellido
3. Sistema busca en FAMILIAS por nombre
4. Nixie muestra hijos registrados
5. Padre elige hijos y horario → **Nixie confirma reserva**
6. Se crea RESERVA + evento en Google Calendar

### Lead no responde
- +15 min, +2 h, +6 h: mensajes de seguimiento automático de Ivan
- +15 min, +2 h, +8 h, +23 h: recordatorios de completar formulario (después de agendar)
- Todos los timers se cancelan al primer mensaje del lead

---

## 5. Detección Clave en el Código

| Función | Archivo | Qué detecta |
|---|---|---|
| `_detectar_activacion_nixie(texto)` | main.py | Si el padre escribió "nixi", "hola nixie", etc. |
| `_detectar_handoff_ivan_nixie(respuesta)` | main.py | Si Ivan dijo "En breve te contacta NIXIE" |
| `_detectar_confirmacion_nixie(respuesta)` | main.py | Si Nixie dijo "Reserva confirmada ✅ [niño] el sábado [fecha] a las [hora]" |
| `extraer_datos_formulario(historial)` | brain.py | Haiku extrae datos de hijo/padre/madre del historial |
| `crear_familia_completa(telefono, datos)` | airtable_client.py | Crea FAMILIA + NIÑOS en Airtable y vincula al LEAD |

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

### Tabla DIAGNOSTICO FENIX (15 condiciones del rompehielos)
| Campo | Tipo | Qué guarda |
|---|---|---|
| CONDICION | Texto | Descripción (ej: "Timidez / le cuesta animarse") |
| NUMERO | Número | 1-15 |
| CATEGORIA | Select | EMOCIONAL / FISICO / SOCIAL / CONDUCTUAL / CLINICO |

### Tabla FAMILIAS FENIX (familias inscriptas — solo se crea al inscribirse, no en prueba)
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
| `agent_actual` | "ivan" o "nixie" |
| `modo_nixie` | "lead_nuevo" o "cliente_inscripto" |
| `variante` | Rompehielos asignado: A (único por ahora) |
| `convertido` | True si Nixie inició recolección de datos |
| `evento_creado` | True si se creó el evento en Google Calendar |
| `airtable_record_id` | ID del registro en LEADS |
| `familia_id` | ID del registro en FAMILIAS |
| `calendar_event_id` | ID del evento en Google Calendar (para reagendamientos) |

---

## 8. Precios y Planes

**Clase de prueba:** 90.000 Gs (descontable de la primera cuota si se inscriben). Solo transferencia bancaria.
**Matrícula anual:** 200.000 Gs con plan mensual / 140.000 Gs con plan trimestral (incluye camisilla Fenix Kids)

| Plan | Mensual + matrícula | Trimestral + matrícula |
|---|---|---|
| QUINCENAL (2 sábados/mes) | 250.000 + 200.000 = **450.000** | 450.000 + 140.000 = **590.000** |
| FULL PASS / SEMANAL (todos los sábados) | 350.000 + 200.000 = **550.000** | 690.000 + 140.000 = **830.000** |

Plan hermanos: 2do hijo 30% desc, 3er hijo 70% desc, 4to hijo FREE.

Inscripción: todos los medios de pago. Clase de prueba: solo transferencia.
Datos bancarios: Ivan Lafuente, Itaú, Cta cte 1074574, CI 1604338.

**Horarios:** Sábados 9:30h | 11:00h | 15:30h — 80 min aprox.

---

## 9. Sistema de Recordatorios

### Seguimiento de Ivan (lead no responde al rompehielos)
| # | Delay | Mensaje |
|---|---|---|
| 1 | +15 min | "¿Te quedó alguna duda sobre FENIX Kids?" |
| 2 | +2 h | Horarios de sábado disponibles |
| 3 | +6 h | Beneficios de la clase de prueba |

### Recordatorios de formulario (Nixie esperando datos)
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
| `META_VERIFY_TOKEN` | ✅ Configurada | `fenix-kids-2026` |
| `TELEGRAM_BOT_TOKEN` | ✅ Configurada | Bot de Telegram de Fenix |
| `TELEGRAM_GROUP_ID` | ✅ Configurada | `-1003965489354` |
| ~~`GOOGLE_CALENDAR_ID`~~ | ❌ Eliminada | Ya no se usa Google Calendar |
| ~~`GOOGLE_CREDENTIALS_JSON`~~ | ❌ Eliminada | Ya no se usa Google Calendar |
| `GROQ_API_KEY` | ✅ Configurada | Para transcripción de audios |
| `ADMIN_API_KEY` | ✅ Configurada | Header `X-ADMIN-KEY` para endpoints /stats, /debug, /telegram/setup |
| `ADMIN_PHONE` | ✅ Default `595982790407` | Número del admin para alertas WhatsApp (también se usa para excluir delays) |
| `TELEGRAM_AGENDA_GROUP_ID` | ✅ Configurada | Grupo Telegram para notificaciones de agenda y alertas de llamada urgente |
| `TELEGRAM_IGNORE_PHONES` | ⏳ Agregar en Railway | Números que no se espejan a Telegram (ej: `595982790407`) |

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
| 63 | Plantillas WhatsApp para recordatorios (reemplazar Calendar) | ⏳ Pendiente |
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
| 2026-04-25 (parte 2) | **Tabla RESERVAS + flujo Ivan refinado (11 commits).** (1) **RESERVAS FENIX arreglada**: campo NIÑO renombrado a NINO (encoding UTF-8 rompía la Ñ, reservas se creaban sin niño). 1 reserva = 1 niño + 1 horario. Campo FAMILIAS vinculado. Lookups FECHA, HORA, NOMBRE COMPLETO. (2) **Detector múltiples confirmaciones**: re.finditer en vez de re.search, soporta 2 reservas en un mensaje. (3) **Parseo de fecha robusto**: soporta "9 de mayo", "3/5" y solo número. Antes solo "d/m". (4) **Ivan nunca lista precios**: siempre "te paso un afiche para que veas todas las opciones". (5) **Follow-up afiche exacto**: "te puedo agendar o te gustaría que te llame?". (6) **Llamada programada**: padre dice hora → sistema programa alerta al admin a esa hora (WhatsApp + Telegram). Si ya pasó, alerta inmediata. (7) **FASE 1.5 en 2 pasos**: paso 1 "con quién tengo el gusto?", paso 2 "cómo se llama y cuántos años tiene tu hijo/a?". (8) **Extracción nombres mejorada**: regex hijo acepta minúsculas, detector padre parsea coma ("Ivan, se llama benja"). (9) **TALLA REMERA**: campo select (6/8/10/12/14/P/M/G/XG), Aurora pregunta si vacío. (10) **Link wa.me**: "te escribo desde mi personal, te puedo llamar ahora?". (11) **Aurora acepta agendar para hoy** si el padre lo pide. |
