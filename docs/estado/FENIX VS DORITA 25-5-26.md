up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# FENIX VS DORITA — Auditoría de Migración (25/05/2026)

> Comparación completa de la arquitectura de ambos agentes.
> FENIX completó la migración. DORITA tiene pendientes.

---

## 1. Estado general

| Aspecto | FENIX | DORITA |
|---------|-------|--------|
| main.py | 221 KB (4280 líneas) — monolito con extracciones recientes | ~65 KB — monolito masivo sin extracciones |
| Módulos extraídos del monolito | 8 | 0 |
| Tools/ directory | 8 tools especializadas | 2 tools (escalacion, info) |
| tool_definitions.py | 6 tools (Ivan 4 + Aurora 2) | 2 tools (enviar_datos_bancarios, escalar_a_humano) |
| Deploy | Railway (auto push main) | Railway (auto push main) |
| Modelo IA | Claude Haiku 4.5 | Claude Haiku 4.5 |
| Agentes | 2 (Ivan + Aurora) | 1 (Dorita) + modos (alumno, secretaria, uber) |

---

## 2. Módulos extraídos en FENIX (Dorita NO los tiene)

| Módulo Fenix | Tamaño | Función | Estado Dorita |
|---|---|---|---|
| `resumenes.py` | 67 KB | Generación de reportes y resúmenes admin | ❌ Inline en main |
| `inscripcion.py` | 22 KB | Flujo completo de inscripción post-pago | ❌ No extraído |
| `fotos.py` | 17 KB | Gestión de fotos de clases | ⚠️ Parcial |
| `afiches.py` | 10 KB | Generación y envío de pósters/precios | ❌ No tiene |
| `loops.py` | 31 KB | Tareas background (followups, recordatorios) | ✅ Tiene |
| `detectores_conv.py` | 15 KB | 10 detectores regex pre-Claude (FAQ, precios, ubicación) | ❌ Inline |
| `flujo_pagos.py` | 18 KB | Orquestación: comprobante → confirmación → registro | ❌ Todo junto |
| `concurrencia.py` | 2 KB | Locks por teléfono (evita race conditions) | ❌ No tiene |
| `night_mode.py` | 4 KB | Respuestas fuera de horario sin gastar tokens | ❌ Solo prompt |
| `seguridad.py` | 3 KB | Validación anti-injection centralizada | ❌ No tiene |
| `validar_nombre.py` | 6 KB | Base datos nombres hispanos para validar input | ❌ No tiene |
| `contenido_social.py` | 16 KB | Generación contenido redes sociales | ❌ No tiene |

---

## 3. Arquitectura de Tools

### FENIX (8 tools en agent/tools/)

```
agent/tools/
├── reservas.py       (11 KB) — gestionar_prueba: confirmar/reagendar pruebas
├── agenda.py         (8 KB)  — gestionar_reserva: agendar/reagendar/cancelar (Aurora)
├── disponibilidad.py (4 KB)  — consultar_disponibilidad + consultar_agendados
├── escalacion.py     (4 KB)  — escalar_a_humano (compartido Ivan/Aurora)
├── info.py           (3 KB)  — respuestas FAQ estáticas
├── llamada.py        (3 KB)  — programar_llamada
├── detectores.py     (5 KB)  — interceptores regex FAQ pre-Claude
├── registro.py       (5 KB)  — registrar inscripción nueva
└── __init__.py
```

### DORITA (2 tools en agent/tools/)

```
agent/tools/
├── escalacion.py     — escalar_a_humano
├── info.py           — info estática
└── __init__.py
```

**Faltantes en Dorita:**
- `tools/datos_bancarios.py` — envío de alias/QR para pago
- `tools/referidos.py` — flujo de referidos (clase gratis)
- `tools/agenda.py` — scheduling de clase de prueba
- `tools/formulario.py` — captura de datos personales
- `tools/disponibilidad.py` — consulta de horarios disponibles

---

## 4. Comparación de tool_definitions.py

### FENIX (6 tools declaradas para Claude)

| Tool | Agente | Propósito |
|------|--------|-----------|
| gestionar_prueba | Ivan | Confirmar/reagendar prueba de lead |
| escalar_a_humano | Ambos | Escalar a humano |
| consultar_disponibilidad | Ivan | Ver slots libres |
| programar_llamada | Ivan | Agendar llamada con padre |
| gestionar_reserva | Aurora | Agendar/reagendar/cancelar clase regular |
| consultar_agendados | Aurora | Ver quiénes van a una clase |

### DORITA (2 tools declaradas para Claude)

| Tool | Propósito |
|------|-----------|
| enviar_datos_bancarios | Enviar alias CI + banco para pago |
| escalar_a_humano | Escalar a Iván |

**Gap:** Dorita necesita al menos 3-4 tools más para que Claude pueda orquestar el flujo sin hardcodeo.

---

## 5. Features exclusivas de cada proyecto

### Solo en FENIX

| Feature | Módulo | Para qué |
|---|---|---|
| 2 agentes (Ivan + Aurora) | ab_test.py + brain.py | Separar ventas de operaciones |
| Face recognition | face_recognition.py | Identificar niños en fotos |
| QR check-in con endpoint web | qr.py + /checkin/ | Control de asistencia |
| Contenido social automático | contenido_social.py | Posts para redes |
| Afiches dinámicos | afiches.py | Envío de precios como imagen |
| Validación de nombres | validar_nombre.py | Confirmar nombres reales |
| Mode agenda post-pago | tool_choice forzada | Forzar reserva después de pagar |

### Solo en DORITA

| Feature | Módulo | Para qué |
|---|---|---|
| Google Calendar | calendar_google.py | Crear eventos de clase |
| Google Drive | google_drive.py | Documentos compartidos |
| Modo alumno (17 opciones) | alumno.py | Self-service para inscriptos |
| Secretaría pagos (voz Iván) | secretaria.py | Registrar pagos por audio |
| Secretaría viajes (Lujan) | uber_secretaria.py | Control gastos Uber/Bolt |
| Facturación | facturas.py | Generar facturas |
| Comics/banco comics | banco_comics.py | Entretenimiento |
| Categorizador mensajes | categorizer.py | Clasificar lead/alumno/admin |
| Comandos admin | commands_ivan.py | Atajos para Iván |
| Debug endpoints | debug_endpoints.py | Diagnóstico en prod |
| Notas personales | notas.py | Asistente personal |
| Reportes + endpoints | reporte.py | Informes periódicos |
| Form parser determinístico | form_parser.py | Regex puro para formularios |
| Shared state centralizado | shared_state.py | Constantes globales |
| 5 modos en un número | main.py | Lead/alumno/secre/uber/personal |

---

## 6. Integraciones compartidas

| Integración | FENIX | DORITA |
|---|---|---|
| Meta WhatsApp Cloud API | ✅ providers/meta.py | ✅ providers/meta.py |
| Anthropic Claude API | ✅ brain.py | ✅ brain.py |
| Airtable CRM | ✅ airtable_client.py | ✅ airtable_client.py |
| Telegram bridge | ✅ telegram_bridge.py | ✅ telegram_bridge.py |
| Groq Whisper (audio) | ✅ transcriber.py | ✅ transcriber.py |
| Meta CAPI (atribución) | ✅ meta_capi.py | ✅ meta_capi.py |
| QR codes | ✅ qr.py | ✅ qr_checkin.py |
| Reminders | ✅ reminders.py | ✅ reminders.py |
| A/B testing | ✅ ab_test.py | ✅ ab_test.py |
| PostgreSQL (prod) | ✅ | ✅ |
| Docker + Railway | ✅ | ✅ |

---

## 7. Pendientes prioritarios para DORITA

### P0 — Crítico (estabilidad en producción)

| # | Tarea | Por qué | Esfuerzo |
|---|---|---|---|
| 1 | Crear `concurrencia.py` — locks por teléfono | Race conditions: 2 msgs rápidos = respuestas duplicadas/corruptas | 30 min |
| 2 | Extraer `detectores_conv.py` — regex interceptores pre-Claude | Ahorra tokens + reduce latencia en FAQ comunes | 2 hrs |
| 3 | Separar `flujo_pagos.py` de la lógica de pagos | Orquestación del flujo completo es inmantenible inline | 2 hrs |

### P1 — Arquitectura (mantenibilidad)

| # | Tarea | Por qué | Esfuerzo |
|---|---|---|---|
| 4 | Expandir tools/ (datos_bancarios, referidos, agenda, formulario, disponibilidad) | Claude necesita más herramientas para decidir sin hardcodeo | 4 hrs |
| 5 | Actualizar tool_definitions.py (de 2 a 5-6 tools) | Dorita solo puede "escalar" y "enviar banco" — muy limitado | 2 hrs |
| 6 | Crear `seguridad.py` — validación centralizada | Anti-injection + rate limiting por teléfono | 1 hr |
| 7 | Crear `night_mode.py` — respuesta fuera de horario | Evita gastar tokens Claude cuando nadie atiende | 1 hr |

### P2 — Calidad

| # | Tarea | Por qué | Esfuerzo |
|---|---|---|---|
| 8 | Crear `validar_nombre.py` — nombres hispanos | Input inválido llega a Airtable | 1 hr |
| 9 | Extraer reportes/resúmenes si están inline | Reducir tamaño de main.py | 2 hrs |
| 10 | Estandarizar estructura agent/ al patrón Fenix | Consistencia entre proyectos | 3 hrs |

---

## 8. Resumen ejecutivo

```
FENIX = más modular, mejor arquitectura, migración completada
DORITA = más features, más modos, pero arquitectura legacy

Dorita funciona bien en producción pero es difícil de mantener.
La deuda técnica principal: main.py monolítico + solo 2 tools + sin concurrencia.

Orden de ataque recomendado:
1. concurrencia.py (30 min, impacto inmediato en estabilidad)
2. detectores_conv.py (2 hrs, ahorro de tokens)
3. expandir tools/ (4 hrs, mejor orquestación)
4. flujo_pagos.py (2 hrs, mantenibilidad)
5. night_mode + seguridad (2 hrs, hardening)
```

---

## 9. Métricas comparativas

| Métrica | FENIX | DORITA |
|---------|-------|--------|
| Archivos Python en agent/ | 31 | 39 |
| Tools especializadas en tools/ | 8 | 2 |
| Extracciones del monolito | 8 módulos | 0 módulos |
| Concurrencia | ✅ | ❌ |
| Detectores pre-Claude | ✅ Módulo separado | ❌ Inline |
| Night mode | ✅ | ❌ |
| Seguridad centralizada | ✅ | ❌ |
| Flujo pagos separado | ✅ | ❌ |
| Validación nombres | ✅ | ❌ |
| Modos operativos | 2 agentes | 5 modos |
| Líneas main.py | ~4,280 | ~65,000+ |
| Complejidad prompt | 210 líneas YAML | 205 líneas YAML |

---

*Generado: 25/05/2026 — Claude Code*
