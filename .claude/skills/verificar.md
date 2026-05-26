---
name: verificar
description: Doubt-driven verification — 5 pasos para verificar una decisión antes de implementarla
---

# Verificar — Doubt-Driven Development

## Overview

"Una respuesta segura no es una respuesta correcta."

Este skill implementa un proceso de verificación adversarial para decisiones no triviales.
Asumí que estás equivocado. Buscá evidencia de que tu plan tiene problemas.
Solo avanzá cuando los hallazgos sean triviales.

## Triggers

Ejecutar cuando:
- Elegir entre múltiples enfoques de implementación
- Cambio que afecta arquitectura del agente
- Consecuencias irreversibles (borrar datos, cambiar flujo de pagos)
- Incertidumbre sobre si un cambio va a romper algo
- Antes de una decisión que Ivan no pueda revertir fácilmente

---

## Steps

### Paso 1 — CLAIM (Qué y por qué)

Nombrar la decisión en 2-3 líneas:
- ¿Qué voy a cambiar?
- ¿Por qué importa? (¿qué se rompe si lo hago mal?)

### Paso 2 — EXTRACT (Aislar el artefacto)

Aislar el artefacto concreto que voy a modificar:
- El archivo y la función exacta
- El contrato: ¿qué DEBE hacer este código? ¿qué inputs recibe? ¿qué outputs produce?
- Separar el artefacto del razonamiento — solo el código + su contrato

### Paso 3 — DOUBT (Revisar con ojos frescos)

Revisión adversarial — asumí sobreconfianza y buscá problemas:

1. ¿Hay algún caso donde mi cambio produce un resultado incorrecto?
2. ¿Hay dependencias que no consideré? (grep call sites)
3. ¿Mi cambio rompe alguno de los 5 escenarios? (Hola, precio, nombre+edad, "sí quiero", comprobante)
4. ¿Estoy asumiendo algo que no verifiqué?
5. ¿El cambio introduce un nuevo anti-patrón? (regex patch, batch deploy, afirmar sin grep)

**IMPORTANTE:** No buscar confirmación de que mi plan es bueno.
Buscar evidencia de que tiene problemas.

### Paso 4 — RECONCILE (Clasificar hallazgos)

Clasificar cada hallazgo por severidad:

1. **Contrato roto** → el cambio no cumple su función → PARAR, rediseñar
2. **Accionable** → problema real que se puede arreglar → arreglar antes de implementar
3. **Trade-off** → compromiso aceptable → documentar para Ivan
4. **Ruido** → no es un problema real → ignorar

### Paso 5 — STOP

Condiciones de salida:
- Los hallazgos restantes son triviales → avanzar
- Después de 3 ciclos de DOUBT sin resolver → el artefacto no está listo, escalar a Ivan
- Ivan dice que avance → avanzar

Presentar a Ivan:
- Qué voy a hacer
- Qué problemas encontré y cómo los resolví
- Qué trade-offs acepto
- Pedir OK

---

## Anti-racionalizaciones

| Excusa | Respuesta |
|---|---|
| "Ya lo pensé y está bien" | Pensar no es verificar. Mostrame el grep |
| "Es obvio que funciona" | Si es obvio, los 5 pasos toman 2 minutos. Hacelos |
| "Ivan tiene prisa" | Ivan prefiere esperar 5 minutos a perder 3 horas arreglando |
| "Solo cambio una línea" | Una línea causó el crash del 11/5 y la muda de 24h de Dorita |

---

## Red flags

- Doubt theater: ejecutar los pasos pero no clasificar nada como accionable
- Buscar confirmación en vez de problemas
- Saltar el paso DOUBT porque "ya sé que está bien"
- Más de 3 ciclos sin resolver → escalar, no seguir girando
