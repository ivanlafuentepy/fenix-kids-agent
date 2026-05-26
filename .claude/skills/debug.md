---
name: debug
description: Workflow de debugging para errores en producción — stop the line, reproducir, localizar, fix root cause
---

# Debug — Debugging y recuperación de errores en producción

## Overview

Cuando algo falla en producción, PARAR todo lo demás. No seguir agregando features.
Preservar evidencia. Seguir el proceso paso a paso. Los errores se acumulan:
un bug no fixeado hace que todo lo que viene después sea incorrecto.

## Triggers

Ejecutar este skill cuando:
- Ivan reporta un error en una conversación
- Un lead recibió respuesta incorrecta o no recibió respuesta
- El agente no respondió a un mensaje
- Algo se rompió después de un deploy
- Un endpoint devuelve error

---

## Steps

### Paso 1 — Stop the line

- PARAR cualquier feature o cambio en progreso
- NO hacer más cambios hasta resolver el bug
- Preservar el estado actual (no hacer git stash ni reset)

### Paso 2 — Reproducir

Obtener evidencia real del problema:

```
/endpoint [teléfono del lead afectado]
```

Leer CADA mensaje de la conversación. Entender el flujo completo:
- ¿Qué dijo el usuario?
- ¿Qué respondió el agente?
- ¿En qué punto falló?
- ¿Cuál era la respuesta esperada?

Si no hay endpoint disponible, guardar debug en DB:
```python
await guardar_mensaje(telefono, "assistant", f"[DEBUG] {info_diagnostico}")
```
Esto es visible desde `/conversacion/{tel}` — usarlo como PRIMERA opción, no última.

### Paso 3 — Localizar

Identificar en qué capa falló:
- ¿Webhook? (no llegó el mensaje)
- ¿Detector/interceptor? (matcheó algo incorrecto)
- ¿Claude API? (respuesta alucinada)
- ¿Prompt? (instrucción incorrecta o faltante)
- ¿Tool use? (herramienta falló)
- ¿Airtable? (datos incorrectos)
- ¿Envío? (mensaje no se envió)

Para regresiones (algo que funcionaba y dejó de funcionar):
```bash
git log --oneline -20
```
Identificar qué commit pudo introducir el bug.

### Paso 4 — Reducir

Crear el caso mínimo que reproduce el problema:
- ¿Qué texto exacto del usuario dispara el bug?
- ¿En qué estado de la conversación?
- ¿Con qué datos en Airtable?

Eliminar variables: si el bug pasa con "Hola", no necesitás toda la conversación previa.

### Paso 5 — Fix root cause

Preguntar "¿POR QUÉ?" hasta llegar a la causa real:

| Síntoma | NO es el fix | SÍ es el fix |
|---|---|---|
| Detector matchea mal | Agregar más regex | Repensar los keywords del detector |
| Claude dice info incorrecta | Agregar más reglas al prompt | Corregir la info base en el prompt |
| Tool falla silenciosamente | Ignorar el error | Agregar logging + manejar el error |
| Mensaje no se envía | Reintentar | Verificar token y endpoint |

### Paso 6 — Guard (prevenir recurrencia)

- ¿Se puede detectar este tipo de error automáticamente?
- ¿Hay un escenario nuevo para agregar a la simulación de /pre-cambio?
- ¿Hay una regla nueva para el prompt?

### Paso 7 — Verificar end-to-end

- Compilar: `python -c "from agent.main import app"`
- Deploy incremental (un cambio por push)
- Esperar Railway (~2 min)
- Probar con /endpoint que el lead ahora recibe la respuesta correcta
- RECIÉN ahí decir "arreglado"

---

## Anti-racionalizaciones

| Excusa | Respuesta |
|---|---|
| "Ya sé cuál es el bug, no necesito reproducir" | El 3/5 "sabías" cuál era y fueron 4 intentos. Reproducí primero |
| "Es un edge case, no pasa seguido" | Si le pasó a un lead real, ya pasó. Fixealo |
| "Parcheo rápido y después lo hago bien" | Los parches rápidos son la razón por la que tenemos 30+ memorias de errores |
| "No tengo logs" | Guardá debug en DB. Es un endpoint. Funciona siempre |

---

## Red flags

- Adivinar el fix sin reproducir
- Fixear el síntoma en vez de la causa raíz
- Hacer cambios adicionales (features) mientras debuggeás
- No verificar que el fix realmente arregla el problema
- Decir "arreglado" sin probar en producción
