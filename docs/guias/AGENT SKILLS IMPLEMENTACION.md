up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# Agent Skills — Manual de Implementación

> Documento de referencia completo: cómo funciona el sistema de addyosmani/agent-skills,
> qué implementamos en FENIX KIDS AGENT, y cómo replicarlo en cualquier proyecto.
> Cualquier Claude debería poder usar este documento como manual.

---

## PARTE 1 — El modelo original de Addy Osmani

### 1.1 Qué es

**Repositorio:** github.com/addyosmani/agent-skills (45k+ stars, MIT license)

Es un meta-framework que programa el comportamiento de agentes de IA (Claude Code, Cursor,
Gemini CLI, etc.) para que sigan buenas prácticas de ingeniería de software. No es una
librería de código — es un sistema de archivos .md que se inyectan como instrucciones
al agente en el momento correcto.

Principio fundamental: **"Skills are workflows agents follow, not reference docs they read."**

Los skills no son documentos que el agente "debería leer" — son workflows que se cargan
activamente en el contexto del agente y le enseñan CÓMO ejecutar cada tarea.

### 1.2 Arquitectura de 3 capas

El sistema tiene 3 capas que trabajan juntas:

```
┌─────────────────────────────────────────────────────┐
│  CAPA 1: COMMANDS (.claude/commands/)               │
│  Entry points del usuario — 7 slash commands        │
│  /spec  /plan  /build  /test  /review  /ship  etc.  │
│  Cada command invoca uno o más skills                │
└──────────────────────┬──────────────────────────────┘
                       │ invoca
┌──────────────────────▼──────────────────────────────┐
│  CAPA 2: SKILLS (skills/<nombre>/SKILL.md)          │
│  Workflows paso a paso — 23 skills                  │
│  Cada skill tiene: triggers, steps, anti-excusas,   │
│  red flags, verificación                            │
└──────────────────────┬──────────────────────────────┘
                       │ pueden invocar
┌──────────────────────▼──────────────────────────────┐
│  CAPA 3: PERSONAS (agents/<nombre>.md)              │
│  Agentes especialistas para revisión paralela       │
│  code-reviewer, security-auditor, test-engineer     │
│  Se ejecutan como subagentes en paralelo            │
└─────────────────────────────────────────────────────┘
```

### 1.3 El mecanismo de auto-activación

Este es el corazón del sistema. Funciona así:

**Paso 1 — SessionStart hook**

En `hooks/hooks.json`:
```json
{
  "hooks": {
    "SessionStart": {
      "type": "command",
      "value": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"
    }
  }
}
```

Cuando se inicia cualquier sesión de Claude Code, el harness ejecuta `session-start.sh`.

**Paso 2 — El script inyecta el meta-skill**

`session-start.sh` hace `cat` del archivo `skills/using-agent-skills/SKILL.md` y lo
inyecta como mensaje del sistema. Esto carga el **router** en el contexto del agente.

**Paso 3 — El agente aprende a routear**

El meta-skill contiene un árbol de decisión que enseña al agente a reconocer intenciones
del usuario y mapearlas al skill correcto. Por ejemplo:

| Intención del usuario | Skill que se activa |
|---|---|
| "Implementá esta feature" | spec-driven-development → incremental-implementation |
| "Hay un bug" | debugging-and-error-recovery |
| "Revisá este código" | code-review-and-quality |
| "Deployá esto" | shipping-and-launch |

**Punto clave:** la activación NO es automática mediante hooks por archivo. El agente
APRENDE cuándo sugerir o invocar cada skill porque tiene el router cargado en contexto.
Es la diferencia entre "un archivo que debería leer" y "instrucciones que ya tiene".

### 1.4 Los 23 skills organizados por fase

Osmani organiza los skills en 7 fases del ciclo de desarrollo + 1 meta-skill:

**Meta (1):**
- `using-agent-skills` — Router. Se carga al inicio. Decide qué skill activar.

**Define (3):**
- `interview-me` — Hacer preguntas al usuario para entender requerimientos
- `idea-refine` — Refinar conceptos y generar variantes
- `spec-driven-development` — Generar especificación formal (SPEC.md)

**Plan (1):**
- `planning-and-task-breakdown` — Convertir spec en tareas accionables

**Build (7):**
- `incremental-implementation` — Rodajas verticales finas: implement → test → verify → commit
- `test-driven-development` — RED → GREEN → REFACTOR
- `context-engineering` — Gestionar contexto del agente eficientemente
- `source-driven-development` — Implementar basándose en docs/fuentes externas
- `doubt-driven-development` — Verificación adversarial antes de decisiones importantes
- `frontend-ui-engineering` — Workflows específicos para UI
- `api-and-interface-design` — Diseño de APIs e interfaces

**Verify (2):**
- `browser-testing-with-devtools` — Testing en browser con DevTools
- `debugging-and-error-recovery` — Debugging sistemático de errores

**Review (4):**
- `code-review-and-quality` — Revisión en 5 ejes (correctness, readability, architecture, security, performance)
- `code-simplification` — Simplificar código existente
- `security-and-hardening` — Auditoría de seguridad (OWASP Top 10)
- `performance-optimization` — Optimización de rendimiento

**Ship (5):**
- `git-workflow-and-versioning` — Workflow de git y versionado
- `ci-cd-and-automation` — Pipelines de CI/CD
- `deprecation-and-migration` — Deprecar y migrar código
- `documentation-and-adrs` — Documentación y ADRs
- `shipping-and-launch` — Deploy y lanzamiento

### 1.5 Anatomía de un skill

Cada skill sigue esta estructura estándar:

```markdown
---
name: nombre-del-skill
description: una línea describiendo el skill
---

# Nombre del Skill

## Overview
Qué hace y por qué importa.

## Triggers
Cuándo activar este skill (condiciones específicas).

## Steps
Proceso paso a paso. Cada paso es concreto y verificable.

## Anti-racionalizaciones
Tabla de excusas comunes que el agente da para saltear pasos,
con rebuttals que explican por qué cada excusa es incorrecta.

| Excusa | Respuesta |
|---|---|
| "Ya sé lo que hace" | No, leelo. El 12/5 afirmaste sin leer y falló |

## Red flags
Señales de que el skill se está aplicando mal.

## Verificación
Checklist final antes de declarar la tarea completa.
```

La sección de **anti-racionalizaciones** es la innovación más importante. No alcanza
con decirle al agente "verificá antes de actuar" — hay que anticipar las excusas
específicas que va a dar para NO verificar, y tener respuestas listas.

### 1.6 Los 7 slash commands

Los commands son orchestrators que invocan uno o más skills:

**`/spec`** — Lanza spec-driven-development. Hace preguntas, genera SPEC.md.

**`/plan`** — Invoca planning-and-task-breakdown. Lee SPEC.md, genera plan.md + todo.md.

**`/build`** — Invoca incremental-implementation + test-driven-development.
Ciclo: pick task → write failing test (RED) → implement (GREEN) → verify → commit → next.

**`/test`** — Invoca test-driven-development. Para features nuevas y para bugs (Prove-It pattern).

**`/review`** — Invoca code-review-and-quality. Análisis en 5 ejes.

**`/code-simplify`** — Lee CLAUDE.md, analiza código, identifica oportunidades de refactor.

**`/ship`** — El más sofisticado. Lanza 3 subagentes EN PARALELO:
```
/ship
  ├─→ [subagente: code-reviewer]     → 5 ejes de calidad
  ├─→ [subagente: security-auditor]  → OWASP, secrets, CVEs
  └─→ [subagente: test-engineer]     → cobertura, edge cases
```
Los 3 reportan, se fusionan hallazgos, y se da veredicto GO/NO-GO con plan de rollback.

### 1.7 Las 3 personas (agentes especialistas)

Las personas son roles que se invocan como subagentes (no son skills):

**code-reviewer.md** — Revisión en 5 ejes: correctness, readability, architecture, security, performance.

**test-engineer.md** — Diseño de tests, cobertura, Arrange-Act-Assert, concurrencia.

**security-auditor.md** — Input validation, auth, secrets, OWASP Top 10, threat modeling.

Regla crítica: **las personas NO se llaman entre sí.** Solo el orchestrator (/ship) las invoca.

### 1.8 Sistema de hooks

Además del SessionStart, Osmani usa hooks para:

**SDD-Cache** (PreToolUse + PostToolUse):
- Cachea recursos HTTP para source-driven-development
- Pre-fetch: HEAD con conditional headers; 304 = servir de cache
- Post-fetch: captura respuesta, graba ETag/Last-Modified

**Simplify-Ignore** (PreToolUse Read + PostToolUse Edit/Write + Stop):
- Protege bloques de código de /code-simplify
- Antes de leer: reemplaza bloques marcados con placeholder
- Después de editar: restaura el código original
- Al cerrar sesión: recuperación completa desde backup

### 1.9 Estructura de directorios completa

```
agent-skills/
├── .claude/
│   ├── commands/              ← 7 slash commands
│   │   ├── spec.md
│   │   ├── plan.md
│   │   ├── build.md
│   │   ├── test.md
│   │   ├── review.md
│   │   ├── code-simplify.md
│   │   └── ship.md
│   └── settings.json          ← (no encontrado — lo maneja el plugin)
├── .claude-plugin/
│   ├── plugin.json            ← Definición del plugin
│   └── marketplace.json       ← Metadata para el marketplace de Claude
├── agents/
│   ├── code-reviewer.md       ← Persona: revisión de código
│   ├── test-engineer.md       ← Persona: testing
│   └── security-auditor.md    ← Persona: seguridad
├── hooks/
│   ├── hooks.json             ← Configuración de hooks
│   ├── session-start.sh       ← Inyecta meta-skill al inicio
│   ├── sdd-cache-pre.sh       ← Cache pre-fetch
│   ├── sdd-cache-post.sh      ← Cache post-write
│   └── simplify-ignore.sh     ← Protección de bloques
├── skills/
│   ├── using-agent-skills/    ← META-SKILL (router)
│   │   └── SKILL.md
│   ├── spec-driven-development/
│   │   └── SKILL.md
│   ├── incremental-implementation/
│   │   └── SKILL.md
│   ├── doubt-driven-development/
│   │   └── SKILL.md
│   ├── debugging-and-error-recovery/
│   │   └── SKILL.md
│   └── ... (23 skills total)
├── references/                ← Checklists de referencia
│   ├── testing-checklist.md
│   ├── security-checklist.md
│   ├── performance-checklist.md
│   └── accessibility-checklist.md
├── docs/                      ← Guías de setup para otros IDEs
├── CLAUDE.md                  ← Instrucciones Claude-specific
├── AGENTS.md                  ← Modelo de ejecución de agentes
└── README.md                  ← Documentación principal (17KB)
```

### 1.10 Flujo completo de una feature (ejemplo)

```
1. Usuario dice: "Implementá autenticación con JWT"

2. SessionStart ya cargó el meta-skill (router) en contexto

3. El agente reconoce: "implementar feature" → sugiere /spec

4. /spec ejecuta spec-driven-development:
   - Hace preguntas de clarificación
   - Genera SPEC.md con requerimientos

5. Agente sugiere /plan
   - Lee SPEC.md
   - Genera tasks/plan.md + tasks/todo.md

6. Para cada tarea, agente sugiere /build:
   - Usa incremental-implementation + test-driven-development
   - RED: escribe test que falla
   - GREEN: implementa lo mínimo para que pase
   - REFACTOR: limpia si es necesario
   - Commit descriptivo
   - Siguiente tarea

7. Agente sugiere /review para code-review-and-quality

8. Agente sugiere /ship:
   - Lanza 3 subagentes en paralelo
   - Fusiona reportes
   - Veredicto GO/NO-GO
   - Si GO: deploy con plan de rollback
```

### 1.11 El concepto de anti-racionalizaciones

Esta es la innovación más importante del sistema. Osmani descubrió que decirle a un agente
"verificá antes de actuar" no funciona. El agente encuentra excusas para saltear la
verificación. La solución: anticipar las excusas y tener rebuttals listos.

Ejemplo del skill doubt-driven-development:

| El agente dice | El skill responde |
|---|---|
| "Ya lo pensé y está bien" | Pensar no es verificar. Mostrame el grep |
| "Es obvio que funciona" | Si es obvio, los 5 pasos toman 2 minutos. Hacelos |
| "El usuario tiene prisa" | Prefiere esperar 5 minutos a perder 3 horas arreglando |

Cada skill tiene su propia tabla de anti-racionalizaciones calibrada a las excusas
específicas que un agente da en ese contexto.

---

## PARTE 2 — Qué implementamos en FENIX y por qué

### 2.1 Diagnóstico del problema

FENIX KIDS AGENT tiene 30+ memorias de feedback en `memory/` y un `CHECKLIST.md` con
reglas obligatorias. El problema: son archivos pasivos. El agente DEBERÍA leerlos antes
de actuar, pero no lo hace. Resultado:

- 2026-05-03: 4 intentos para fixear un bug de 1 línea (no leyó la función completa)
- 2026-05-11: Crash en producción por pushear 5 cambios juntos
- 2026-05-12: Afirmó "esto ya lo cubre el código" sin grep — un lead recibió basura
- 2026-05-25: Borró todas las reservas futuras de Airtable sin verificar

El patrón es siempre el mismo: el agente actúa confiado, falla, se disculpa diciendo
"tenía la info en la memoria pero no la leí", y el usuario pierde horas.

### 2.2 Qué partes de Osmani usamos

| Componente de Osmani | Lo usamos | Por qué |
|---|---|---|
| Meta-skill (router) | ✅ Sí | Es el corazón — carga las reglas en contexto activo |
| SessionStart hook | ✅ Sí | Es el mecanismo de inyección automática |
| Estructura de skills (.md con triggers, steps, anti-excusas, red flags) | ✅ Sí | Formato probado que funciona |
| Commands como entry points | ✅ Sí | /pre-cambio, /pre-deploy, /debug, /verificar |
| doubt-driven-development | ✅ Sí | Adaptado como /verificar |
| incremental-implementation | ✅ Parcial | Ya lo teníamos como regla, ahora es parte del router |
| debugging-and-error-recovery | ✅ Sí | Adaptado como /debug |
| Personas (code-reviewer, etc.) | ❌ No | FENIX es un proyecto de 1 persona, no necesita revisión paralela |
| /spec, /plan, /build, /test | ❌ No | FENIX ya está en producción, no necesita ciclo completo de desarrollo |
| /ship con fan-out paralelo | ❌ No | Overkill para nuestro volumen de cambios |
| SDD-Cache hooks | ❌ No | No usamos source-driven-development |
| Simplify-Ignore hooks | ❌ No | No usamos /code-simplify |
| Plugin manifest (.claude-plugin/) | ❌ No | No es un plugin distribuible, es config del proyecto |

### 2.3 Qué skills creamos y por qué

**Meta-skill: `using-fenix-skills/SKILL.md`**
- **Qué es:** Router que se carga al inicio de cada sesión
- **Por qué:** Sin esto, las memorias y checklists son pasivos. Con esto, el agente tiene las reglas ACTIVAS en contexto
- **Contiene:** Comportamientos obligatorios, anti-patrones conocidos (con ejemplos reales de FENIX), árbol de decisión intención→skill

**Skill: `pre-cambio.md`**
- **Qué es:** Verificación obligatoria antes de editar código crítico
- **Por qué:** Consolida CHECKLIST.md + 3 memorias de feedback que el agente nunca leía
- **Consolida:** CHECKLIST.md, feedback_eficiencia, feedback_no_alucinar_cobertura, feedback_no_mas_parches_regex
- **Cuándo se activa:** Antes de editar prompts.yaml, main.py, detectores.py, afiches.py, pagos.py

**Skill: `pre-deploy.md`**
- **Qué es:** Verificación antes de git push
- **Por qué:** El crash del 11/5 fue por pushear 5 cambios juntos. asyncio traga excepciones
- **Consolida:** feedback_deploy_incremental, CHECKLIST pasos 6-8
- **Cuándo se activa:** Antes de cualquier git push a main

**Skill: `debug.md`**
- **Qué es:** Workflow de debugging para errores en producción
- **Por qué:** Adaptación del debugging-and-error-recovery de Osmani al contexto FENIX (Railway, Airtable, WhatsApp)
- **Consolida:** feedback_debug_db, proceso stop-the-line de Osmani
- **Cuándo se activa:** Cuando Ivan reporta un error o algo se rompe post-deploy

**Skill: `verificar.md`**
- **Qué es:** Doubt-driven verification — proceso de 5 pasos
- **Por qué:** Implementación directa del doubt-driven-development de Osmani. Contrarresta el patrón de "actuar confiado sin verificar"
- **Cuándo se activa:** Decisiones no triviales, cambios arquitectónicos, consecuencias irreversibles

### 2.4 Qué NO cambiamos de lo existente

- `endpoint.md`, `fusabado.md`, `pagina.md` — skills que ya funcionan bien
- `cierre.md` — ritual de cierre que ya funciona
- `CHECKLIST.md` — se mantiene como referencia, el skill pre-cambio lo absorbe
- Memorias en `memory/` — se mantienen como historial, los skills consolidan lo crítico
- `settings.local.json` — permisos del usuario, no se tocan

---

## PARTE 3 — Implementación técnica

### 3.1 Estructura de directorios implementada

```
.claude/
├── hooks/
│   └── session-start.sh              ← Script que inyecta briefing + meta-skill
├── skills/
│   ├── using-fenix-skills/
│   │   └── SKILL.md                  ← META-SKILL (router) — se carga automático
│   ├── pre-cambio.md                 ← Verificación pre-edición
│   ├── pre-deploy.md                 ← Verificación pre-deploy
│   ├── debug.md                      ← Workflow debugging producción
│   ├── verificar.md                  ← Doubt-driven verification
│   ├── endpoint.md                   ← (existente) Análisis de conversación
│   ├── fusabado.md                   ← (existente) Follow-up post-sábado
│   └── pagina.md                     ← (existente) Páginas de mensajes masivos
├── commands/
│   ├── pre-cambio.md                 ← /pre-cambio → skill pre-cambio
│   ├── pre-deploy.md                 ← /pre-deploy → skill pre-deploy
│   ├── debug.md                      ← /debug → skill debug
│   ├── verificar.md                  ← /verificar → skill verificar
│   ├── endpoint.md                   ← (existente) /endpoint
│   ├── fusabado.md                   ← (existente) /fusabado
│   ├── cierre.md                     ← (existente) /cierre
│   └── build-agent.md                ← (existente) /build-agent
├── settings.json                     ← Hooks: SessionStart → session-start.sh
└── settings.local.json               ← Permisos (no se tocó)
```

### 3.2 Flujo de activación

```
┌─────────────────────────────────────────────────────────┐
│  1. SESIÓN NUEVA                                        │
│     settings.json → SessionStart hook                   │
│     → bash .claude/hooks/session-start.sh               │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  2. session-start.sh                                    │
│     a) Muestra briefing (fecha, branch, commits)        │
│     b) cat skills/using-fenix-skills/SKILL.md           │
│     → meta-skill se inyecta en contexto del agente      │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  3. AGENTE TIENE EL ROUTER EN CONTEXTO                  │
│     Sabe cuándo sugerir cada skill:                     │
│     - Editar código crítico → /pre-cambio               │
│     - git push → /pre-deploy                            │
│     - Error en prod → /debug                            │
│     - Decisión compleja → /verificar                    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  4. USUARIO O AGENTE INVOCA EL SKILL                    │
│     /pre-cambio → lee pre-cambio.md → ejecuta steps     │
│     Cada step es concreto: leer, grep, simular, etc.    │
│     Anti-racionalizaciones bloquean excusas del agente   │
└─────────────────────────────────────────────────────────┘
```

### 3.3 El hook de session-start

Archivo: `.claude/hooks/session-start.sh`

```bash
#!/bin/bash
# Briefing operacional
echo '════════════════════════════════'
echo '  FENIX KIDS ACADEMY — Briefing'
echo '════════════════════════════════'
echo "  Fecha: $(date '+%A %d/%m/%Y %H:%M PY')"
echo "  Branch: $(git branch --show-current 2>/dev/null || echo 'sin git')"
echo ''
git status --short 2>/dev/null | head -10
echo ''
echo '  Ultimos 5 commits:'
git log -5 --oneline 2>/dev/null
echo '════════════════════════════════'
echo ''

# Inyectar meta-skill (router de skills)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_FILE="$SCRIPT_DIR/../skills/using-fenix-skills/SKILL.md"

if [ -f "$SKILL_FILE" ]; then
  echo '═══ FENIX SKILLS LOADED ═══'
  cat "$SKILL_FILE"
  echo '═══ END FENIX SKILLS ═══'
else
  echo '[WARN] Meta-skill no encontrado en: '"$SKILL_FILE"
fi
```

El script combina el briefing existente (que antes era un one-liner en settings.json)
con la inyección del meta-skill. Usa `$SCRIPT_DIR` para resolver la ruta relativa
al skill file, compatible con Windows Git Bash.

### 3.4 Configuración de settings.json

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/session-start.sh"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '  Sesion cerrada: '$(date '+%d/%m/%Y %H:%M')"
          }
        ]
      }
    ]
  }
}
```

### 3.5 Formato de los commands

Cada command es un archivo .md de una línea que apunta al skill:

```markdown
Leer y ejecutar las instrucciones de `.claude/skills/pre-cambio.md`
```

Claude Code detecta estos archivos en `.claude/commands/` y los registra como
slash commands invocables con `/nombre`. El sistema de skills de Claude Code
se encarga de leer el .md referenciado e inyectarlo en el contexto cuando se invoca.

---

## PARTE 4 — Cómo replicar en otro proyecto

### 4.1 Pasos mínimos

1. **Crear la estructura de directorios:**
```bash
mkdir -p .claude/hooks
mkdir -p .claude/skills/using-PROYECTO-skills
mkdir -p .claude/commands
```

2. **Escribir el meta-skill** (`.claude/skills/using-PROYECTO-skills/SKILL.md`):
   - Comportamientos obligatorios del agente en este proyecto
   - Anti-patrones conocidos (de errores pasados)
   - Árbol de decisión: intención → skill

3. **Escribir los skills** (`.claude/skills/nombre.md`):
   - Cada uno con: overview, triggers, steps, anti-racionalizaciones, red flags, verificación
   - Las anti-racionalizaciones son CRÍTICAS — sin ellas, el agente encuentra excusas

4. **Crear los commands** (`.claude/commands/nombre.md`):
   - Una línea: `Leer y ejecutar las instrucciones de .claude/skills/nombre.md`

5. **Crear el hook** (`.claude/hooks/session-start.sh`):
   - Script bash que hace `cat` del meta-skill
   - Se ejecuta al inicio de cada sesión

6. **Configurar settings.json** (`.claude/settings.json`):
   - SessionStart hook apuntando al script

### 4.2 Errores a evitar

- **No crear hooks por archivo** — la inteligencia va en el router (meta-skill), no en hooks granulares
- **No poner reglas genéricas** — las anti-racionalizaciones deben ser de errores REALES que pasaron
- **No olvidar los commands** — sin el command, el skill no es invocable con /nombre
- **No sobrecargar el meta-skill** — debe ser conciso. Los detalles van en cada skill individual
- **No inventar** — seguir la estructura de Osmani. Funciona porque está probada con 45k+ stars

### 4.3 Checklist de verificación

- [ ] `bash .claude/hooks/session-start.sh` muestra briefing + meta-skill
- [ ] El meta-skill aparece en el output del hook
- [ ] Los skills aparecen en la lista de skills disponibles al iniciar sesión
- [ ] `/nombre` invoca el skill correctamente
- [ ] Las anti-racionalizaciones incluyen errores reales del proyecto

---

## Apéndice A — Skills de Osmani que no implementamos (y por qué)

| Skill | Por qué no |
|---|---|
| spec-driven-development | FENIX ya está en producción, no hay features nuevas que especificar |
| planning-and-task-breakdown | Usamos Plan Mode de Claude Code directamente |
| test-driven-development | No tenemos suite de tests automatizados en FENIX |
| incremental-implementation | Ya lo teníamos como regla, está integrado en pre-cambio y pre-deploy |
| context-engineering | Relevante pero no prioritario ahora |
| source-driven-development | No implementamos desde docs externos |
| frontend-ui-engineering | FENIX es backend (WhatsApp), no tiene frontend |
| browser-testing-with-devtools | No aplica |
| code-review-and-quality | Somos 1 persona, no hay PRs ni revisiones |
| code-simplification | Podría ser útil pero no es prioridad |
| security-and-hardening | Pendiente — podría implementarse después |
| performance-optimization | No es problema actual |
| git-workflow-and-versioning | Ya tenemos nuestro propio workflow de git |
| ci-cd-and-automation | Deploy automático con Railway ya funciona |
| deprecation-and-migration | No aplica ahora |
| documentation-and-adrs | Podría ser útil después |
| shipping-and-launch | Overkill para nuestro flujo de deploy |

## Apéndice B — Referencia rápida de comandos

| Comando | Cuándo usarlo |
|---|---|
| `/pre-cambio` | Antes de editar prompts.yaml, main.py, detectores, afiches, pagos |
| `/pre-deploy` | Antes de git push a main |
| `/debug` | Cuando algo falla en producción |
| `/verificar` | Cuando hay una decisión no trivial que tomar |
| `/endpoint [tel]` | Para ver la conversación de un lead en producción |
| `/cierre` | Al terminar la sesión de trabajo |
| `/fusabado [fecha]` | Para generar follow-up post-sábado |
