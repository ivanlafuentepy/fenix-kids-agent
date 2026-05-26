# /endpoint — Analizar conversación de producción

Recibís como argumento: $ARGUMENTS (puede ser un teléfono o un nombre de padre/hijo).

## Paso 1 — Resolver teléfono

Si $ARGUMENTS parece un número de teléfono (empieza con 595, o tiene 10+ dígitos):
- Usar ese número directamente.

Si $ARGUMENTS es un nombre:
- Buscar en el archivo de memoria `C:\Users\IVAN LAFUENTE\.claude\projects\C--Users-IVAN-LAFUENTE-Projects-fenix-kids-agent\memory\contactos_fenix.md`.
- Buscar coincidencia parcial (nombre del padre O nombre de hijo).
- Si hay match, usar el teléfono correspondiente.
- Si no hay match, buscar en Airtable con curl:
  ```
  curl -s -H "Authorization: Bearer $AIRTABLE_API_KEY" "https://api.airtable.com/v0/$AIRTABLE_BASE_ID/LEADS%20FENIX?filterByFormula=SEARCH(LOWER(\"$NOMBRE\"),LOWER({NOMBRE PADRE}))"
  ```
  (leer AIRTABLE_API_KEY y AIRTABLE_BASE_ID de `.env` del proyecto).
- Si no encontrás nada, reportar "No encontré teléfono para ese nombre" y terminar.

## Paso 2 — Fetch de datos de producción

Leer ADMIN_API_KEY de la memoria `reference_railway_prod.md`.

Ejecutar DOS curls en paralelo con Bash (NUNCA usar WebFetch):

```bash
curl -s -H "X-ADMIN-KEY: $ADMIN_API_KEY" "https://fenix-kids-agent-production.up.railway.app/debug/$TELEFONO"
```

```bash
curl -s -H "X-ADMIN-KEY: $ADMIN_API_KEY" "https://fenix-kids-agent-production.up.railway.app/conversacion/$TELEFONO"
```

**IMPORTANTE:**
- PATH PARAM: /debug/{telefono} y /conversacion/{telefono}, NUNCA query param
- NUNCA usar WebFetch — siempre curl con Bash
- NUNCA inventar URLs que no sean estas dos

## Paso 3 — Leer CADA mensaje

Del response de `/conversacion/{telefono}`, leer el array `conversacion` que tiene objetos `{rol, texto, timestamp}`.

**LEER CADA MENSAJE CRUDO.** No resumir. Entender el flujo completo: qué dijo el usuario, qué respondió el agente, en qué orden, si hubo problemas.

Del response de `/debug/{telefono}`, extraer:
- `agent_actual` — qué agente está activo (ivan/aurora)
- `modo_nixie` — en qué modo está (null, formulario, reserva, etc.)
- `familia_id` — si ya es familia inscripta
- `esta_convertido` — si convirtió
- `mensajes_totales` — total de mensajes

## Paso 4 — Buscar nombre del contacto

Con el teléfono, buscar en `contactos_fenix.md` el nombre del padre/madre.
Si no está ahí, usar el nombre que aparezca en la conversación o "Desconocido".

## Paso 5 — Reportar

Formato EXACTO:

```
═══ Endpoint TELEFONO — NOMBRE ═══

📊 Estado: [lead/familia] | Agent: [agent_actual] | Modo: [modo_nixie o "normal"] | Mensajes: [total]

📋 Resumen del flujo:
[3-5 líneas describiendo qué pasó en la conversación: dónde está el lead, qué se habló, en qué punto del funnel está]

⚠️ Problemas detectados:
[Listar problemas concretos: respuestas fuera de contexto, loops, errores, flujo roto, etc. Si no hay, poner "Ninguno"]

💡 Sugerencia:
[Qué acción tomar: seguir esperando, intervenir manualmente, corregir algo en el código, etc. Si todo bien, poner "Flujo normal, sin acción requerida"]
```

## REGLAS CRÍTICAS

- **SOLO LECTURA** — NUNCA enviar mensajes ni modificar datos sin permiso explícito de Ivan
- **NUNCA** inventar datos que no vengan del response
- **NUNCA** usar WebFetch — solo curl via Bash
- Si el endpoint devuelve error o 0 mensajes, reportar eso claramente
