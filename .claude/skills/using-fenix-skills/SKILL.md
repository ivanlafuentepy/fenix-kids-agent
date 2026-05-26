---
name: using-fenix-skills
description: Meta-skill que enseña al agente a reconocer intenciones y activar el skill correcto antes de actuar
---

# FENIX SKILLS — Router de Skills

Este skill se carga al inicio de cada sesión. Define CÓMO debe trabajar el agente
y CUÁNDO activar cada skill del sistema.

## Principio fundamental

**"Una respuesta segura no es una respuesta correcta."**

Antes de actuar en cualquier tarea no trivial, el agente DEBE verificar.
Verificar significa: leer el archivo, grep las dependencias, simular el impacto.
NUNCA asumir. NUNCA afirmar sin evidencia.

---

## Comportamientos obligatorios (no negociables)

1. **Verificar antes de afirmar** — si vas a decir "esto ya lo cubre el código", mostrá el grep + línea exacta. Sin evidencia = no afirmar.
2. **Leer antes de editar** — leé COMPLETO el archivo/función que vas a tocar. No asumir que sabés lo que hace.
3. **Un cambio por commit** — nunca mezclar prompt + código + DB en un push.
4. **Decir "no estoy seguro"** — si no estás seguro, decilo. Es preferible preguntar a romper producción.
5. **Buscar causa raíz** — nunca parchear el síntoma. Si algo falla, preguntá "¿por qué?" hasta llegar al origen.
6. **Respetar el scope** — no tocar archivos que no están relacionados con la tarea actual.

---

## Anti-patrones conocidos (errores que YA cometimos)

| Lo que hago mal | Lo que debería hacer |
|---|---|
| "Esto ya está cubierto por el código" (sin grep) | Grep + mostrar línea exacta, o decir "no lo encontré" |
| Pushear 5 cambios juntos | Un cambio por push, esperar deploy, verificar, siguiente |
| "Son cambios chicos, no pasa nada" | El crash del 11/5 fue por "cambios chicos" juntos |
| Agregar otro regex/interceptor | Proponer rediseño con estados/intents antes de parchear |
| Decir "listo" sin verificar | Probar que compila, que el endpoint responde, que los 5 escenarios pasan |
| Leer una memoria pero no aplicarla | Las memorias son reglas, no sugerencias — aplicarlas o justificar por qué no |
| Asumir fecha/hora sin calcular | SIEMPRE calcular con Python: `datetime.now(ZoneInfo("America/Asuncion"))` |

---

## Árbol de decisión — cuándo activar cada skill

Cuando detectes alguna de estas intenciones (del usuario o propia), SUGERÍ o INVOCÁ el skill correspondiente:

### Cambios en código crítico → `/pre-cambio`

**Triggers:**
- Editar `config/prompts.yaml` (system prompt — habla con leads reales)
- Editar `agent/main.py` (orquestación — si se rompe, todo se rompe)
- Editar `agent/tools/detectores.py` (interceptores regex)
- Editar `agent/afiches.py` o `agent/pagos.py` (dinero y precios)
- Cualquier cambio que afecte el flujo de conversación

**Acción:** Ejecutar `/pre-cambio` ANTES de escribir una sola línea.

### Deploy a producción → `/pre-deploy`

**Triggers:**
- `git push` a main
- Cualquier intención de deployar

**Acción:** Ejecutar `/pre-deploy` ANTES del push.

### Bug o error en producción → `/debug`

**Triggers:**
- Ivan reporta un error en una conversación
- Un lead recibió respuesta incorrecta
- El agente no respondió
- Algo se rompió después de un deploy

**Acción:** Ejecutar `/debug` — parar features, preservar evidencia, seguir el proceso.

### Análisis de conversación → `/endpoint`

**Triggers:**
- Ivan dice "endpoint [teléfono/nombre]"
- Necesidad de ver qué pasó con un lead

**Acción:** Ya existe y funciona. Invocar `/endpoint`.

### Decisión no trivial → `/verificar`

**Triggers:**
- Elegir entre múltiples enfoques
- Cambio que afecta arquitectura
- Algo con consecuencias irreversibles
- Incertidumbre sobre si un cambio va a romper algo

**Acción:** Ejecutar `/verificar` — proceso doubt-driven de 5 pasos.

### Cierre de sesión → `/cierre`

**Triggers:**
- Ivan dice "chau", "nos vemos", "hasta mañana", etc.
- Fin de la sesión de trabajo

**Acción:** Ya existe y funciona. Invocar `/cierre`.

### Follow-up post-sábado → `/fusabado`

**Triggers:**
- Ivan quiere generar follow-up de un sábado
- Después de una clase de prueba

**Acción:** Ya existe y funciona. Invocar `/fusabado`.

---

## Regla de oro

Si vas a tocar código y NO ejecutaste el skill correspondiente → PARÁ.
Preguntate: "¿ejecuté /pre-cambio?" Si la respuesta es no, ejecutalo.
No hay excusas. No hay "es un cambio chico". No hay "ya sé lo que hace".
