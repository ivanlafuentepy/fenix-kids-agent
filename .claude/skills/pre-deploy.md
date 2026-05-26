---
name: pre-deploy
description: Verificación obligatoria antes de hacer git push — deploy incremental, nunca batch
---

# Pre-Deploy — Verificación antes de pushear a producción

## Overview

Cada `git push` a main dispara un deploy automático en Railway.
Si el push tiene un bug, el agente deja de responder a leads REALES.
asyncio.create_task traga excepciones — el webhook devuelve 200 OK pero el mensaje se pierde silenciosamente.

## Triggers

Ejecutar este skill ANTES de:
- `git push` a main
- Cualquier intención de deployar a producción

---

## Steps

### Paso 1 — ¿Es un cambio único o un batch?

- Si hay más de un cambio lógico → SPLITEAR
- Prompt y código van en pushes SEPARADOS
- Cambios de DB (columnas nuevas) van SOLOS con try/except

### Paso 2 — Verificar compilación

```bash
python -c "from agent.main import app; print('OK')"
```

Si falla → NO pushear. Arreglar primero.

### Paso 3 — ¿Ivan aprobó?

- ¿Ivan dio el OK explícito para este deploy?
- Si no → preguntar antes de pushear

### Paso 4 — Push

- `git push` a main
- Un solo push con un cambio lógico

### Paso 5 — Esperar y verificar

- Esperar ~2 minutos para que Railway termine el build
- Verificar con `/endpoint` de un lead existente que el agente responde
- Si es cambio de primer mensaje → probar con número nuevo o reset
- RECIÉN después de verificar, decir "listo"

---

## Anti-racionalizaciones

| Excusa | Respuesta |
|---|---|
| "Son cambios chicos, los pusheo juntos" | El crash del 11/5 fue exactamente esto: 5 cambios juntos, uno rompió todo |
| "Ya compiló, seguro funciona" | asyncio traga excepciones. Que compile no significa que funcione en prod |
| "Después verifico" | Si no verificás ahora y algo se rompe, un lead no recibe respuesta por horas |
| "Es solo un cambio de prompt" | El prompt habla con leads reales. Verificar que los 5 escenarios siguen pasando |

---

## Red flags

- Más de un cambio lógico en el push
- No haber corrido la verificación de compilación
- No esperar a que Railway termine el build
- Decir "listo" sin haber probado el endpoint
- Push de DB changes sin try/except

---

## Verificación final

- [ ] Es un solo cambio lógico
- [ ] Compila sin errores
- [ ] Ivan aprobó
- [ ] Railway terminó el build
- [ ] Probé con /endpoint que responde bien
