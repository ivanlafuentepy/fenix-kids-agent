# FENIX KIDS AGENT — Instrucciones para Claude Code

> Este archivo es el manual operativo del proyecto. Se carga en cada sesión.
> Describe el sistema REAL en producción — no es una plantilla.
> El detalle profundo vive en `docs/FENIX_RESUMEN.md` (~785 líneas): leelo cuando
> necesites entender un flujo a fondo. Este archivo te dice QUÉ es el sistema,
> CÓMO trabajar en él sin romperlo, y DÓNDE está cada cosa.

---

## 1. Qué es este proyecto

Agente de WhatsApp **en producción** para **FENIX KIDS ACADEMY**, centro de
entrenamiento funcional y emocional para niños de 3 a 12 años en Asunción,
Paraguay (PARQUE FENIX / LA CASONA LAFUENTE, Maestras Paraguayas 2056).

Un solo número de WhatsApp, **dos agentes IA** según el estado de la conversación:

| Agente | Modo | Qué hace |
|---|---|---|
| **Profe Ivan Lafuente** | leads | Atención, ventas, agendar clase de prueba, cierre de pagos |
| **Aurora** | familia | Operaciones, reservas de clases regulares, atención a inscriptos |

El estado por teléfono (en DB, `agent/ab_test.py`) define el MODO, no quién atiende.
Objetivo del sistema: que el padre confirme una clase de prueba (lead) o reserve
una clase regular (familia inscripta), todo dentro del chat.

**En conversación conmigo, al agente "ivan" llamalo FENIX** (en código sigue siendo `ivan`).
La marca se escribe **FENIX / Fenix, SIN tilde** — nunca "Fénix".

---

## 2. ⚠️ Regla cero: esto habla con clientes reales

Cada línea de `main.py`, `prompts.yaml` y los detectores afecta conversaciones
con padres reales AHORA. Un push roto = leads perdidos y plata perdida.
Por eso existen los skills obligatorios (sección 6) y el `docs/CHECKLIST.md`.
No existe "cambio chico". El crash del 11/05 fue por "cambios chicos" juntos.

---

## 3. Stack real

| Componente | Tecnología |
|---|---|
| Runtime | Python 3.11+ async-first |
| Servidor | FastAPI + Uvicorn |
| IA (conversación + extracción) | `claude-haiku-4-5-20251001` (3 call sites en `brain.py`) |
| WhatsApp | **Meta Cloud API únicamente** (`agent/providers/meta.py`) |
| DB | PostgreSQL (Railway prod) / SQLite (dev) — SQLAlchemy 2.0 async + asyncpg |
| CRM | Airtable, base SALSA SOUL: LEADS / PRUEBA / FAMILIAS / NIÑOS / HORARIOS / RESERVAS / DIAGNOSTICO / ANUNCIOS FENIX |
| Espejo admin | Telegram Bot API (grupo con topics por conversación + grupo Monitor dedicado) |
| Audio | Groq Whisper (`agent/transcriber.py`) |
| Caras | AWS Rekognition (`agent/face_recognition.py`, check-in facial del Espejo) |
| Atribución ads | Meta CAPI (`agent/meta_capi.py` — LeadSubmitted/Purchase para CTWA) |
| Deploy | Railway, deploy automático en cada `git push` a `main` |

Dependencias en `requirements.txt`. No agregar librerías sin avisar.
Google Calendar fue **eliminado** — no reintroducirlo.

### Flujo de un mensaje (real)

```
WhatsApp → Meta Cloud API → POST /webhook (main.py)
  → dedup (mensaje_ya_procesado) → early save en DB (el mensaje nunca se pierde)
  → detectores regex PRIMERO (agent/tools/detectores.py — precio, horario, ubicación…)
  → si ningún detector matchea → brain.py → Claude Haiku con ivan_prompt o aurora_prompt
  → tools si aplica (tool_definitions.py + tool_executor.py, flag USE_TOOL_USE)
  → respuesta via providers/meta.py → espejo al topic de Telegram
```

Regla de arquitectura: **parser determinístico primero, IA como fallback** — evita
alucinaciones en precios/horarios. Pero OJO: **NO agregar detectores/regex nuevos** —
si un caso no está cubierto, proponer rediseño con estados/intents, no otro parche
(regla dura, ya nos quemamos con la pila de interceptores).

---

## 4. Mapa del repo

```
agent/
  main.py            ← 5000+ líneas. Orquestador: webhook, dedup, detectores, estados,
                        pagos, endpoints admin. EL archivo más crítico. Leer antes de tocar.
  brain.py           ← Claude API. Elige ivan_prompt/aurora_prompt según estado.
                        Historial limitado a 20 mensajes (costo).
  memory.py          ← Historial + dedup + recordatorios. Postgres/SQLite.
  ab_test.py         ← Estado por conversación: agente, modo, familia_id, flags.
  pagos.py           ← Flujo de pagos: comprobantes, confirmación admin, PRECIOS.
  airtable_client.py ← CRM. ⚠️ `_get_records` NO pagina (trunca a 100) — paginar a mano
                        en tablas grandes; ya duplicó tutores una vez.
  telegram_bridge.py ← Espejo Telegram, topics, silenciar/reactivar agente.
  monitor.py         ← Monitor interno: leads sin respuesta, salud, token Meta muerto.
  meta_capi.py       ← Eventos de conversión a Meta.
  tool_definitions.py / tool_executor.py ← Tool use (TOOLS_IVAN + TOOLS_AURORA).
  tools/             ← detectores.py (regex), reservas, agenda, disponibilidad,
                        escalacion, llamada, registro.
  providers/         ← base.py + meta.py (solo Meta; acá NO existen whapi/twilio).
  hq_endpoints.py    ← router HQ, protegido con HQ_API_KEY.
  juego_endpoints.py ← router /juego: Mundo Fenix (pulseras NFC, check-in facial, ledger).
  + inscripcion, facturas, flujo_pagos, pagos_tarjeta, afiches, lead_menu,
    alumno_menu, fotos, qr, reminders, night_mode, seguridad, concurrencia,
    face_recognition, resumenes, contenido_social, loops, hooks…
config/
  prompts.yaml       ← ivan_prompt + aurora_prompt + fallback/error (~165 líneas).
                        HABLA CON LEADS REALES. Nunca tocar sin /pre-cambio.
mundo-fenix/         ← Frontend del juego físico (tótem, mapa, index) + SPECs
                        (PLAN-MAESTRO, SPEC-TOTEM-Y-PROFE, SPEC-NFC, SPEC-BLE).
docs/
  FENIX_RESUMEN.md   ← Documentación completa del sistema. Fuente de verdad técnica.
  CHECKLIST.md       ← Control OBLIGATORIO antes de cambios en prompt/flujo/deploy.
scripts/             ← One-offs: exports, migraciones, follow-ups masivos, voces ElevenLabs.
tests/               ← test_local.py (chat simulado) + test_extractor_nombres.py.
static/              ← Afiches PNG, profe.html, assets servidos.
```

### Dónde viven las cosas (para no buscar mal)

- **Precios**: 4 lugares vivos → `config/prompts.yaml`, `agent/afiches.py`,
  `agent/lead_menu.py`, `agent/pagos.py` (+ afiches PNG en `static/`). Si cambia un
  precio, cambian LOS CUATRO. `business.yaml` y el `tools.py` del template original
  son **código muerto** — no los uses de referencia.
- **Estado del proyecto / pendientes / decisiones**: `docs/` del repo (sección 9)
  + la memoria persistente de Claude Code.
- **Endpoints admin** (`/reset/{tel}`, `/conversacion/{tel}`, `/test-envio/{tel}`…):
  protegidos con header `X-ADMIN-KEY` (env `ADMIN_API_KEY`). URL de prod y key en
  la memoria persistente de Claude Code.

---

## 5. Reglas duras (no negociables)

1. **Español SIEMPRE** — chat, comentarios, commits, docs.
2. **NUNCA hardcodear API keys ni teléfonos** — env vars via python-dotenv.
   Nunca imprimir tokens completos en el chat.
3. **NUNCA enviar mensajes a leads/familias sin aprobación explícita de Ivan.**
   Tampoco activar follow-ups automáticos nuevos sin aprobación.
4. **Enviar WhatsApp de prueba solo via Railway** (`/test-envio/{telefono}`),
   NUNCA curl directo a la API de Meta.
5. **Fechas y horas: calcular SIEMPRE con Python** —
   `datetime.now(ZoneInfo("America/Asuncion"))`. Nunca asumir ni "recordar" la fecha.
   El LLM del agente tampoco calcula fechas: se le inyecta el contexto exacto.
6. **Airtable: mirar antes de crear/afirmar** — verificar que tabla/campo/opción de
   select existan EXACTO antes de POST/PATCH. Consultar datos reales antes de
   teorizar. Antes de crear un registro en PAGOS, verificar que no exista uno linkeado.
7. **Nunca decir "el código ya cubre X" sin grep + línea exacta.** Sin evidencia, no afirmar.
8. **Un cambio lógico por commit.** Nunca prompt + código + DB juntos.
   Si toco prompt + código → código primero, deploy, verificar, después el prompt.
9. **Deploy incremental** — nunca pushear un refactor grande de una vez.
10. **No parches regex nuevos** — rediseñar con estados/intents.
11. **Nunca `--no-verify`.** Nunca tocar archivos fuera del scope de la tarea.
12. **Debug en producción**: si algo falla silencioso, guardar el debug como mensaje
    en la DB (primera opción, no última).
13. **Token de Meta renovado = reiniciar el servicio en Railway** — el proceso lee
    el token solo al arrancar; cambiar la variable no basta.

---

## 6. Flujo de trabajo obligatorio (skills)

Antes de actuar, identificá la intención y ejecutá el skill que corresponde.
No hay excusas ni "es un cambio chico".

| Situación | Skill | Cuándo |
|---|---|---|
| Tocar `prompts.yaml`, `main.py`, detectores, `pagos.py`, `afiches.py` o el flujo | `/pre-cambio` | ANTES de escribir una línea |
| `git push` a main | `/pre-deploy` | ANTES del push |
| Bug o error en producción | `/debug` | Parar features, preservar evidencia |
| Decisión no trivial / arquitectura | `/verificar` | Proceso doubt-driven de 5 pasos |
| "endpoint [tel/nombre]" | `/endpoint` | Trae conversación de prod + análisis de flujo |
| Ivan se despide (chau/bs/ns) | `/cierre` | Ofrecer ritual de cierre de sesión |
| Follow-up post-sábado | `/fusabado` | Después de clase de prueba |
| Plantilla Meta nueva | `/plantilla` | Guía de creación + conexión al agente |

Además: `docs/CHECKLIST.md` se ejecuta COMPLETO antes de cualquier cambio en
prompts/flujo/deploy, mostrando los resultados a Ivan ANTES de implementar.

---

## 7. Definition of Done

Un cambio está "listo" SOLO cuando pasó todo esto. Antes de eso, no decir "listo".

```bash
# 1. Importa sin errores
py -3 -c "import agent.main"

# 2. Tests que toquen lo cambiado
py -3 -m pytest tests/ -q        # o py -3 tests/test_local.py para probar conversación

# 3. Si tocaste detectores → probar casos positivos Y negativos a mano
# 4. Push → esperar build de Railway (~2 min) → verificar que el deploy quedó OK
# 5. Probar en prod: /conversacion o /test-envio con un número de prueba.
#    Si es cambio de primer mensaje → probar con número nuevo o /reset.
# 6. Reportar: "✅ Verificado: [qué revisé y qué respondió prod]"
```

Simulación mínima obligatoria para cambios de flujo (sale del CHECKLIST):
lead nuevo dice "Hola" · pregunta precio/horario/ubicación · da nombre y edad
del hijo · dice "sí quiero" · manda comprobante. Si un escenario queda sin
cubrir con el cambio, decirlo explícitamente.

---

## 8. Convenciones de código

- Código y comentarios **en español**; nombres descriptivos en snake_case
  (`guardar_mensaje`, `padre_pregunta_precios`); `_prefijo` = función privada del módulo.
- Densidad de comentarios como la existente: cabecera por archivo
  (`# agent/x.py — qué hace`), docstring por función pública. No borrar comentarios sin razón.
- Nada de "nuevo/mejorado/enhanced/v2" en nombres — el código es evergreen.
- Commits: `feat:` / `fix:` / `docs:` / `config:` / `refactor:` con scope cuando aplica
  (`feat(juego): …`, `fix(capi): …`) — mirá `git log` y seguí el patrón.
- Estado SIEMPRE en DB, nunca en memoria del proceso (Railway reinicia sin aviso).
- Dedup de webhooks obligatoria (Meta manda duplicados) — ya está en `memory.py`, no romperla.
- Rate limiting existente: respetarlo (Meta silencia números por spam).
- Historial a Claude: 20 mensajes máx. Modelo Haiku fijo — no subir de modelo sin
  aprobación de Ivan (decisión de costo del 2026-05-04, ~95% de ahorro vs Sonnet).
- Prompt cache (`cache_control: ephemeral`) en el system prompt — no romperlo.

---

## 9. Documentación — fuente de verdad

**Obsidian ya NO se usa** (decisión 2026-07-07). Toda la documentación viva del
proyecto está en `docs/` de este repo:

- `docs/FENIX_RESUMEN.md` — documentación técnica completa del sistema.
- `docs/CHECKLIST.md` — control obligatorio pre-cambio/pre-deploy.
- `docs/sesiones/` — cierres de sesión. `docs/estado/`, `docs/marca/`,
  `docs/operaciones/`, `docs/marketing/` — lo demás.
- La memoria persistente de Claude Code guarda lo operativo entre sesiones.
- Si un skill, memoria o doc viejo dice "actualizá en Obsidian" → actualizá en
  `docs/` del repo en su lugar.

---

## 10. Monitor y Guardian (ya implementados — no duplicar)

- **Capa 1**: `agent/monitor.py` — loops asyncio dentro del proceso Railway. Detecta
  leads sin respuesta >10 min, errores de webhook, token Meta muerto (401), salud de
  DB/detectores/prompts. Alerta al grupo Telegram Monitor. "Todo OK" solo 09/15/21h PY.
- **Capa 2**: Guardian remoto (Claude Code scheduled, cada 1h) — audita el repo y
  pushea fixes obvios con prefix `fix(guardian):`. NO toca prompts.yaml, .env,
  flujo de pagos ni handlers de reset.
- **Capa 3**: Ivan recibe la alerta por Telegram y decide.

Antes de proponer "un monitor para X", verificar si estas capas ya lo cubren.

---

## 11. Comandos de referencia

```bash
# Python en esta máquina: py -3 (o python). En Git Bash: date SIN TZ= (invierte la hora).
py -3 -m uvicorn agent.main:app --reload --port 8000   # servidor local
py -3 tests/test_local.py                               # chat simulado sin WhatsApp
py -3 -m pytest tests/ -q                               # tests
```

Producción: Railway, proyecto FENIX, servicio `fenix-kids-agent`,
repo `github.com/ivanlafuentepy/fenix-kids-agent`. Railway (API GraphQL con token
del env), Airtable MCP y `gh` los uso yo directo — no pedirle a Ivan datos de
infra que puedo consultar solo.

---

## 12. Reglas de eficiencia de tokens

1. Pensar antes de actuar. Leer los archivos existentes antes de escribir código.
2. Conciso en el output, exhaustivo en el razonamiento.
3. Editar antes que reescribir archivos enteros.
4. No re-leer archivos ya leídos salvo que hayan cambiado.
5. Probar el código antes de declarar terminado.
6. Sin aperturas aduladoras ni cierres de relleno.
7. Soluciones simples y directas.
8. Las instrucciones del usuario SIEMPRE pisan este archivo.
