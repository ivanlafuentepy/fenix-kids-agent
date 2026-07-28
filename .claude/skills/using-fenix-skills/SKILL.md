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

### Cambio de PRECIO → `/cambioprecio`

**Triggers:**
- "cambiamos el precio", "sube la matrícula", "el pack pasa a X", "ahora la prueba sale Y"
- Cualquier monto nuevo que un lead o una familia vaya a escuchar

**Acción:** Invocar `/cambioprecio` ANTES de tocar nada. El precio vive en **7 lugares + la web**,
los links de pago van **firmados por monto** (cambiar el monto sin refirmar los rompe) y el
afiche es lo primero que ve el lead. El skill incluye el grep de control obligatorio: la lista
de lugares es el punto de partida, no la garantía.

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

### Página de aviso masivo → `/pagina`

**Triggers:**
- Ivan quiere avisar algo a todas las familias/leads (cambio de horario, evento, broadcast)
- Necesidad de una página personalizada en fenixkidsacademy-web.pages.dev

**Acción:** Invocar `/pagina [slug]`. Si es follow-up post-prueba, usar `/fusabado` en su lugar.

### Plantilla Meta WhatsApp → `/plantilla`

**Triggers:**
- Ivan quiere crear o conectar una plantilla de WhatsApp (fuera de ventana 24h)
- Necesidad de mensaje proactivo aprobado por Meta

**Acción:** Invocar `/plantilla` — guía completa de creación, aprobación y conexión a Aurora.

### Envío masivo → `/masivo`

**Triggers:**
- Ivan quiere mandar un mensaje/video/afiche a MUCHOS números (FU, promo, aviso)
- Cualquier script de envío en loop

**Acción:** Invocar `/masivo` — pre-flight de token, test a 1 número, OK explícito, rate limit, bitácora. NUNCA correr un script de FU viejo sin este skill.

### Envío de WhatsApp real → memoria + permiso

**Triggers:**
- Cualquier intención de mandar un mensaje a un número real (lead, padre, admin)

**Acción:** SIEMPRE via `/test-envio/` de Railway (nunca curl directo a Meta) y SIEMPRE con OK explícito de Ivan antes de enviar a leads/padres.

---

## Regla de oro

Si vas a tocar código y NO ejecutaste el skill correspondiente → PARÁ.
Preguntate: "¿ejecuté /pre-cambio?" Si la respuesta es no, ejecutalo.
No hay excusas. No hay "es un cambio chico". No hay "ya sé lo que hace".
