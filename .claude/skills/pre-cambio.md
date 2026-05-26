---
name: pre-cambio
description: Verificación obligatoria antes de tocar código crítico — prompts, flujo, detectores, precios
---

# Pre-Cambio — Verificación antes de editar código crítico

## Overview

Este skill es OBLIGATORIO antes de editar cualquier archivo que afecte el comportamiento
del agente en producción. Si este código tiene un bug, leads REALES reciben basura.

## Triggers

Ejecutar este skill ANTES de editar:
- `config/prompts.yaml` — system prompt
- `agent/main.py` — orquestación del flujo
- `agent/tools/detectores.py` — interceptores regex
- `agent/afiches.py` — afiches y precios
- `agent/pagos.py` — flujo de pagos
- Cualquier archivo en `agent/tools/`

---

## Steps

### Paso 1 — Leer lo que voy a modificar

- Leer COMPLETO el archivo o función que voy a tocar
- Leer los parámetros, defaults y valores por defecto
- Entender qué hace cada parte que voy a cambiar o eliminar
- NO asumir que sé lo que hace — LEER

### Paso 2 — Verificar dependencias

- Para cada cosa que voy a SACAR o CAMBIAR: grep en todo el repo
- Mostrar los resultados del grep a Ivan
- Si algo depende de lo que voy a tocar → decirlo explícitamente
- Grep ALL call sites de cualquier función que modifique

### Paso 3 — Verificar cobertura

- Si digo "esto ya lo hace el código" → pegar el grep + línea exacta que lo demuestra
- Si NO hay código que reemplace lo que saco → decirlo explícitamente
- NUNCA afirmar cobertura sin evidencia

### Paso 4 — Simular impacto (5 escenarios)

Simular mentalmente qué pasa con mi cambio en estos 5 casos:
1. Un lead nuevo escribe "Hola"
2. Un lead pregunta precio/horario/ubicación
3. Un lead da nombre y edad del hijo
4. Un lead dice "sí quiero" / acepta
5. Un lead manda comprobante de pago

Si algún escenario queda sin cubrir → decirlo antes de implementar.

### Paso 5 — Presentar a Ivan

- Listar EXACTAMENTE qué voy a tocar (archivos, líneas, secciones)
- Listar las dependencias encontradas
- Listar los escenarios simulados y sus resultados
- Esperar el OK de Ivan antes de escribir código

### Paso 6 — Un cambio por commit

- No mezclar prompt + código + DB en un solo commit
- Si toco prompt + código → pushear código PRIMERO, esperar deploy, después prompt

### Paso 7 — Verificar que funciona

- Correr `python -c "from agent.main import ..."` — compila sin errores
- Si agregué funciones nuevas → probar con asserts básicos
- Si modifiqué detectores → probar con casos positivos Y negativos

---

## Anti-racionalizaciones

| Excusa | Respuesta |
|---|---|
| "Ya sé lo que hace este archivo" | No, leelo. El 12/5 afirmaste cobertura sin leer y un lead recibió basura |
| "Es un cambio de una línea" | El crash del 11/5 fue UN campo nuevo en PostgreSQL — una línea |
| "Esto ya está cubierto por otro interceptor" | Mostrá el grep. Sin grep = no está cubierto |
| "Son solo cambios en el prompt, no es código" | El prompt habla con leads REALES. Un error = dinero perdido |
| "Después verifico" | No. Verificar ANTES. "Después" no existe |
| "Voy a agregar un regex rápido" | NO. Proponer rediseño con estados/intents. No más parches regex |

---

## Red flags (si ves alguna, PARÁ)

- Más de 100 líneas sin testear
- Mezclar cambios no relacionados en un commit
- Afirmar sin mostrar evidencia (grep, read, output)
- Agregar un nuevo interceptor/detector regex
- Tocar archivos que no están relacionados con la tarea
- Decir "listo" sin haber probado

---

## Verificación final

Antes de decir "listo", confirmar:
- [ ] Leí completo lo que modifiqué
- [ ] Hice grep de dependencias y mostré resultados
- [ ] Los 5 escenarios pasan con mi cambio
- [ ] Ivan dio el OK
- [ ] Compila sin errores
- [ ] Un commit = un cambio lógico
