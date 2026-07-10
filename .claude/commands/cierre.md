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

3. **Actualizar `docs/sesiones/CONVERSACIONES_FENIX.md`** (en este repo — Obsidian ya no se usa, decisión 2026-07-07; si el archivo no existe, crearlo):
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
   - Registrar la sesión en el índice `memory/sesiones.md` (la extensión VS Code NO deja renombrar el panel: cachea los nombres y no relee archivos; `/rename` de la CLI tampoco se sincroniza). En vez de pelear con eso, llevamos un índice propio. Obtené el código de la sesión activa (el `.jsonl` más reciente del proyecto) y agregá una fila:
     ```bash
     DIR=$(ls -dt ~/.claude/projects/*fenix-kids-agent*/ | head -1)
     SID=$(basename "$(ls -t "$DIR"*.jsonl | head -1)" .jsonl)
     echo "$SID"
     ```
     Agregá a `memory/sesiones.md` una fila con: `Nombre elegido | código (SID) | fecha | resumen de 1 línea`. Si el archivo no existe, crealo con el encabezado. NUNCA edites `~/.claude/sessions/` (no funciona). Para retomar después: `claude --resume <SID>`.

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

---

## REGLA FINAL — Aprendizajes que NO deben repetirse (obligatorio, ANTES del commit)

Contestate esta pregunta antes de commitear: **"¿Qué problema resolvimos hoy cuya solución
no debe re-descubrirse nunca?"** (criterio: costó >15 min, tocó producción, o Iván tuvo que
recordarnos algo ya resuelto). Si la respuesta es "ninguno", decilo explícito en el resumen
final. Si hubo, registralo en DOS lugares — los dos, no uno:

1. **`memory/errores-aprendidos.md`** del repo (si no existe, crealo; lo más reciente arriba):
   **qué falló · la causa raíz · cómo se resolvió · la regla para la próxima**.
2. **La memoria automática de ESTE proyecto** (`~/.claude/projects/<carpeta-de-este-proyecto>/memory/`):
   un archivo nuevo (o actualizar uno existente) con frontmatter `type: feedback`, el **Why**
   y el **How to apply**, + su línea en `MEMORY.md`. Esa memoria se carga SOLA en cada sesión:
   es la que evita repetir el error aunque nadie la busque.

> Por qué doble: el archivo del repo es la bitácora compartida (greppeable, versionada), pero
> solo sirve si alguien lo lee; `MEMORY.md` llega en cada arranque sin pedirlo. El bug del cert
> de Railway (2026-07-09) se re-diagnosticó desde cero teniendo la solución escrita en el repo.
> Y si el problema se resolvió a mitad de sesión, registralo EN ESE MOMENTO — este paso es la
> red por si se escapó, no el único lugar.
