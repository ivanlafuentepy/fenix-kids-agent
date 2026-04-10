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
| **Airtable** | CRM: LEADS, FAMILIAS, NIÑOS, HORARIOS, RESERVAS |
| **Google Calendar API** | Creación automática de eventos al confirmar clase de prueba o reserva |
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
  brain.py          — Llama a Claude API, carga ivan_prompt o nixie_prompt según estado
  memory.py         — Historial de conversaciones + estado (agent_actual, modo_nixie)
  ab_test.py        — Estado por conversación: agente, modo, familia_id, Calendar
  airtable_client.py — Toda la integración con Airtable (LEADS, FAMILIAS, NIÑOS, etc.)
  calendar_google.py — Integración con Google Calendar
  telegram_bridge.py — Integración con Telegram
  reminders.py      — Recordatorios automáticos de seguimiento y formulario
  transcriber.py    — Transcripción de audios con Groq Whisper
  providers/        — Adaptador Meta WhatsApp Cloud API
config/
  prompts.yaml      — System prompts de Ivan y Nixie
  business.yaml     — Datos del negocio
```

---

## 3. Los Dos Agentes

### Profe Ivan Lafuente
- **Rol:** atención inicial, diagnóstico emocional, ventas
- **Activación:** por defecto en todo mensaje nuevo
- **Flujo:** rompehielos diagnóstico (15 opciones numeradas) → validación empática → propuesta (metodología + precios) → cierre
- **Transferencia a Nixie:** cuando dice exactamente *"Perfecto 🙌 En breve te contacta NIXIE, ella se va a encargar de pedirte los datos y hacerte la reserva."*

### Nixie
- **Rol:** operaciones, formularios, reservas
- **Activación directa:** si el padre escribe "nixi", "hola nixie", "quiero reservar con nixie", etc.
- **Activación por handoff:** cuando Ivan detecta intención de agendar y transfiere

**Nixie tiene dos modos:**

| Modo | Cuándo | Qué hace |
|---|---|---|
| `lead_nuevo` | Viene derivada por Ivan (primer agendamiento) | Pide formulario hijo + padre + madre, coordina horario, confirma reserva |
| `cliente_inscripto` | Padre ya inscripto escribe directo | Pide solo nombre y apellido, busca en Airtable FAMILIAS, muestra hijos, agenda |

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

### Tabla LEADS (leads en proceso)
| Campo | Tipo | Qué guarda |
|---|---|---|
| TELEFONO | Texto | Número WhatsApp del padre/madre |
| ROMPEHIELOS | Select | Variante asignada: A, B o C |
| CONVERSION | Select | Estado: CONSULTA → AGENDA → INSCRIPTO |
| AGENT_ACTUAL | Select | IVAN o NIXIE |
| MODO_NIXIE | Select | lead_nuevo o cliente_inscripto |
| FORMULARIO | Checkbox | True cuando todos los datos están completos |
| FECHA PRIMER CONTACTO | Fecha | Cuándo escribió por primera vez |
| FAMILIA | Link record | ID del registro en FAMILIAS (una vez creado) |

### Tabla FAMILIAS (familias inscriptas)
| Campo | Tipo | Qué guarda |
|---|---|---|
| FAMILIA | Formula | "FAMILIA [primer apellido padre] [primer apellido madre]" |
| NOMBRE PADRE / APELLIDO PADRE | Texto | Datos del padre |
| CI PADRE / EMAIL PADRE / CELL PADRE | Texto | Contacto del padre |
| FECHA NACIMIENTO PADRE | Fecha | Para calcular P/EDAD |
| NOMBRE MADRE / APELLIDO MADRE | Texto | Datos de la madre |
| CI MADRE / EMAIL MADRE / CELL MADRE | Texto | Contacto de la madre |
| FECHA NACIMIENTO MADRE | Fecha | Para calcular M/EDAD |
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
| FAMILIA | Link record | Familia a la que pertenece |
| RESERVAS | Link records | Clases reservadas |
| LINK RESERVA | Formula | URL del formulario de reserva prefillado |

### Tabla HORARIOS (clases disponibles)
| Campo | Tipo | Qué guarda |
|---|---|---|
| HORARIO | Formula | "Sábado 12/4 9:30" |
| FECHA | Fecha | Fecha exacta de la clase |
| HORA | Select | 9:30, 11:00, 16:00, 17:30 |
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
| `AGENDA` | Confirmó una reserva | Cuando Nixie confirma horario |
| `INSCRIPTO` | Pago confirmado | Al detectar comprobante de pago |

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

**Clase de prueba:** 90.000 Gs (descontable de la primera cuota si se inscriben)
**Matrícula anual:** 200.000 Gs (incluye camisilla Fenix Kids)

| Plan | Mensual | Promo débito auto (Bancard) | Trimestral |
|---|---|---|---|
| QUINCENAL (2 sábados/mes) | 250.000 Gs | 190.000 Gs | 540.000 Gs |
| SEMANAL (todos los sábados) | 350.000 Gs | 290.000 Gs | 840.000 Gs |

**Horarios:** Sábados 9:30h | 11:00h | 16:00h | 17:30h — 80 min aprox.

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
| `AIRTABLE_BASE_ID` | ✅ Configurada | `apph96UwbdbHoEdYr` |
| `META_ACCESS_TOKEN` | ⏳ Pendiente | Token de Meta WhatsApp para Fenix |
| `META_PHONE_NUMBER_ID` | ⏳ Pendiente | ID del número de Fenix en Meta |
| `META_VERIFY_TOKEN` | ✅ Listo | `fenix-kids-2026` |
| `TELEGRAM_BOT_TOKEN` | ⏳ Pendiente | Token del bot de Telegram de Fenix |
| `TELEGRAM_GROUP_ID` | ⏳ Pendiente | ID del grupo de Telegram de Fenix |
| `GOOGLE_CALENDAR_ID` | ⏳ Pendiente | Email del calendario de Fenix |
| `GOOGLE_CREDENTIALS_JSON` | ⏳ Pendiente | JSON de la Service Account de Fenix |
| `GROQ_API_KEY` | ⏳ Pendiente | Para transcripción de audios |

---

## 11. Pendientes para el Deploy

| # | Tarea | Estado |
|---|---|---|
| 1 | Crear app de Meta WhatsApp para Fenix Kids | ⏳ Pendiente |
| 2 | Crear bot de Telegram + grupo para Fenix | ⏳ Pendiente |
| 3 | Crear Service Account de Google Calendar | ⏳ Pendiente |
| 4 | Crear repo en GitHub | ⏳ Pendiente |
| 5 | Crear proyecto en Railway + conectar repo | ⏳ Pendiente |
| 6 | Cargar todas las variables en Railway | ⏳ Pendiente |
| 7 | Registrar webhook de WhatsApp | ⏳ Pendiente |
| 8 | Registrar webhook de Telegram | ⏳ Pendiente |
| 9 | Probar con test local (`python tests/test_local.py`) | ⏳ Pendiente |

---

## 12. Historial de Cambios

| Fecha | Cambio realizado |
|---|---|
| 2026-04-06 | Proyecto creado. Copiado desde Dorita y adaptado para FENIX KIDS ACADEMY. Dual agente: Profe Ivan + Nixie. Nueva estructura Airtable: LEADS, FAMILIAS, NIÑOS, HORARIOS, RESERVAS. Creados todos los archivos del agente. |
| 2026-04-06 | Airtable: creada tabla LEADS, campo TALLA REMERA en NIÑOS, opciones 16:00 y 17:30 en HORARIOS. |
