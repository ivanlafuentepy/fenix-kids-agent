Ritual de cierre de sesión de FENIX KIDS AGENT.

Ejecuta estos pasos EN ORDEN, sin saltarte ninguno:

1. **Revisar qué cambió en esta sesión:**
   - `git log` desde el último commit que tocó docs/FENIX_RESUMEN.md
   - `git status` para ver si quedan cambios sin commitear
   - Repasar mentalmente la conversación: qué se hizo, qué se decidió, qué quedó a medio

2. **Actualizar `docs/FENIX_RESUMEN.md`:**
   - **Sección 10 (Variables de entorno):** marcar como ✅ las que ya están listas, ⏳ solo las que de verdad faltan
   - **Sección 11 (Pendientes para deploy):** tachar lo hecho, agregar pendientes nuevos descubiertos
   - **Sección 12 (Historial de cambios):** agregar UNA fila nueva con fecha de hoy y un resumen claro de lo que se hizo en esta sesión
   - Si descubriste cosas estructurales nuevas (campos de Airtable, flows, archivos), actualizar la sección correspondiente
   - NO reescribas todo el documento — solo lo que cambió

3. **Actualizar `CONVERSACIONES_FENIX.md` en Obsidian** (`C:/Users/IVAN LAFUENTE/IVAN VAULT/FENIX KIDS/CONVERSACIONES_FENIX.md`):
   - Agregar una sección con la fecha de hoy (`## YYYY-MM-DD`)
   - Por cada intercambio relevante de la sesión, escribir:
     - **Ivan:** lo que pidió (textual o parafraseado, en sus palabras)
     - **Fenix:** resumen corto de lo que se hizo (qué archivo, qué fix, qué comando)
   - Al final de la sección, listar los commits de la sesión con hash + mensaje
   - NO borrar sesiones anteriores — solo agregar al final
   - Mantener el tono directo y conciso, no florear

4. **Actualizar memorias persistentes** en `C:/Users/IVAN LAFUENTE/.claude/projects/C--Users-IVAN-LAFUENTE-Projects-fenix-kids-agent/memory/`:
   - Actualizar `project_state.md` con el estado actual
   - Si surgió feedback nuevo del usuario, guardarlo
   - Si surgió un pendiente importante para la próxima sesión, anotarlo en `project_next_session.md`

5. **Commitear y pushear los cambios** del resumen y archivos relacionados:
   - Mensaje de commit en formato: `docs: cierre sesión YYYY-MM-DD — [resumen 5 palabras]`
   - NO incluir Co-Authored-By
   - Hacer `git push` automático después del commit — así docs/FENIX_RESUMEN.md siempre queda al día en el repo

6. **Nombrar la sesión:**
   - Preguntar: "¿Cómo le ponemos a esta sesión?"
   - Sugerir 3 nombres cortos basados en lo que se trabajó (ej: "monitor + guardian", "fix conversacional", "precios invierno")
   - Esperar que Ivan elija o proponga otro
   - Renombrar la sesión editando el JSON en ~/.claude/sessions/. Buscar el archivo que tiene el sessionId actual del proyecto, y agregar o actualizar el campo "name" con el nombre elegido. NUNCA pedirle al usuario que ejecute /rename manual.

7. **Avisar al usuario** con este formato exacto:
   ```
   ═══ Cierre de sesión ═══

   Resumen actualizado. Cambios:
   - [punto 1]
   - [punto 2]
   - [punto 3]

   Memorias actualizadas: [lista corta]

   Commit local hecho: [hash corto + mensaje]

   Pendiente para próxima sesión: [lo más importante a recordar]

   Listo. Hasta la próxima.
   ```

REGLAS:
- Si no hay nada que actualizar en el resumen (sesión sin cambios reales), avisarlo y no commitear vacío
- Push automático al cerrar — el usuario ya lo aprobó (2026-05-25)
- Si hay cambios sin commitear que NO son del resumen, avisar al usuario antes de tocar nada
