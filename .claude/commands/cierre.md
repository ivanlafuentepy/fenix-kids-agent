Ritual de cierre de sesión de FENIX KIDS AGENT.

**PRINCIPIO RECTOR: el handoff es la ÚNICA redacción larga de la sesión. Todo lo demás
(FENIX_RESUMEN.md, CONVERSACIONES_FENIX.md, memoria) son filas cortas o punteros hacia él.
NUNCA volver a contar la historia completa en más de un lugar.**

Ejecuta estos pasos EN ORDEN, sin saltarte ninguno:

0. **Pedir nombre de sesion (SIEMPRE con 3 opciones marcables):**
   - ANTES de hacer cualquier otra cosa, ofrecer el nombre con la herramienta **AskUserQuestion** — NUNCA preguntar abierto pidiendo que Iván escriba.
   - Generar **3 propuestas de nombre** basadas en lo que se hizo en la sesión (descriptivas, no genéricas). Iván solo marca una (o usa "Other" si ninguna le cierra).
   - Reglas: una sola pregunta, header "Nombre sesión", 3 opciones, la más representativa primera.
   - Esperar la selección. Usar ese nombre en el handoff, resumen y commit.

1. **Revisar qué cambió en esta sesión:**
   - `git log` desde el último commit que tocó docs/FENIX_RESUMEN.md
   - `git status` para ver si quedan cambios sin commitear
   - Repasar mentalmente la conversación: qué se hizo, qué se decidió, qué quedó a medio

2. **Actualizar `docs/FENIX_RESUMEN.md`:**
   - **Sección 10 (Variables de entorno):** marcar como ✅ las que ya están listas, ⏳ solo las que de verdad faltan
   - **Sección 11 (Pendientes para deploy):** tachar lo hecho, agregar pendientes nuevos descubiertos
   - **Sección 12 (Historial de cambios):** agregar UNA fila **corta**: fecha, commits con hash, una frase de qué se hizo, y el puntero al handoff archivado (`.claude/handoffs/handoff_XXXX.md`) — **PROHIBIDO el párrafo largo**, el detalle ya vive en el handoff
   - El historial mantiene **máximo ~15 filas**: si al agregar la nueva quedan más, mover las más viejas a `docs/FENIX_RESUMEN_archivo.md`
   - Si descubriste cosas estructurales nuevas (campos de Airtable, flows, archivos), actualizar la sección correspondiente
   - NO reescribas todo el documento — solo lo que cambió

2b. **Generar handoff** en `.claude/handoff.md` — LA redacción canónica y completa de la
    sesión (la única larga). Crear/sobreescribir con esta estructura exacta:

    ```
    # HANDOFF — [fecha Paraguay DD/MM/YYYY] — [nombre sesion]

    ## Completado en esta sesion
    [lista especifica de todo lo que hicimos, con commits]

    ## En progreso (quedo a medias)
    [que quedo incompleto y en que punto exacto]

    ## Proxima sesion — arrancar por aca
    [PRIMER paso exacto, sin ambiguedad]
    [resto en orden de prioridad]

    ## Errores encontrados hoy
    [errores con causa y solucion — o "Ninguno"]

    ## Decisiones tomadas
    [decisiones importantes y por que]

    ## Archivos modificados
    [lista de archivos tocados hoy]
    ```

2c. **Archivar el handoff con timestamp** (NO depender de ningún hook):
    - Ejecutar: `mkdir -p .claude/handoffs && cp .claude/handoff.md ".claude/handoffs/handoff_$(date +%Y%m%d_%H%M).md"`
    - Guardar el nombre del archivo generado: es el **puntero** que usan los pasos siguientes.

3. **Actualizar `docs/sesiones/CONVERSACIONES_FENIX.md`** (en este repo — Obsidian ya no se usa, decisión 2026-07-07; si el archivo no existe, crearlo):
   - Agregar **una entrada corta** con la fecha de hoy: `## YYYY-MM-DD — [nombre sesion]` +
     2-3 líneas (qué se hizo y por qué, commits referenciados) + el puntero al handoff archivado
   - **PROHIBIDO volver a redactar el intercambio turno por turno (Ivan:/Fenix:)** — esa
     redacción completa ya vive en el handoff; acá va solo el resumen corto + puntero
   - NO borrar sesiones anteriores — solo agregar al final
   - Mantener el tono directo y conciso, no florear

4. **Actualizar memorias persistentes** en `C:/Users/IVAN LAFUENTE/.claude/projects/C--Users-IVAN-LAFUENTE-Projects-fenix-kids-agent/memory/`:
   - `project_state.md` es un **SNAPSHOT, no un historial**: agregar la nota de esta sesión
     (unas líneas + puntero al handoff) y **mantener SOLO las últimas 5 notas** — al agregar la
     nueva, borrar la más vieja (su contenido ya vive en FENIX_RESUMEN/CONVERSACIONES/handoffs del repo)
   - Si surgió feedback nuevo del usuario, guardarlo
   - Si surgió un pendiente importante para la próxima sesión, anotarlo en `project_next_session.md`

5. **Commitear y pushear los cambios** del resumen y archivos relacionados:
   - Mensaje de commit en formato: `docs: cierre sesión YYYY-MM-DD — [resumen 5 palabras]`
   - NO incluir Co-Authored-By
   - Hacer `git push` automático después del commit — así docs/FENIX_RESUMEN.md siempre queda al día en el repo

6. **Índice de sesiones** — registrar esta sesión en `memory/sesiones.md` (la extensión VS Code NO deja renombrar el panel: cachea los nombres y no relee archivos; `/rename` de la CLI tampoco se sincroniza). En vez de pelear con eso, llevamos un índice propio. Usá el nombre elegido en el paso 0. Obtené el código de la sesión activa (el `.jsonl` más reciente del proyecto):
   ```bash
   DIR=$(ls -dt ~/.claude/projects/*fenix-kids-agent*/ | head -1)
   SID=$(basename "$(ls -t "$DIR"*.jsonl | head -1)" .jsonl)
   echo "$SID"
   ```
   Agregá a `memory/sesiones.md` una fila con: `Nombre elegido | código (SID) | fecha | resumen de 1 línea`. Si el archivo no existe, crealo con el encabezado. NUNCA edites `~/.claude/sessions/` (no funciona). Para retomar después: `claude --resume <SID>`.

7. **Avisar al usuario** con este formato exacto:
   ```
   ═══ Cierre de sesión ═══

   Handoff generado: .claude/handoff.md
   Resumen actualizado: docs/FENIX_RESUMEN.md
   Conversaciones actualizadas: docs/sesiones/CONVERSACIONES_FENIX.md

   Cambios:
   - [punto 1]
   - [punto 2]
   - [punto 3]

   Memorias actualizadas: [lista corta]

   Commit local hecho: [hash corto + mensaje]

   Pendiente para próxima sesión: [lo más importante a recordar]

   Handoff archivado en: .claude/handoffs/handoff_YYYYMMDD_HHMM.md
   Listo. Hasta la próxima.
   ```

REGLAS:
- Si no hay nada que actualizar en el resumen (sesión sin cambios reales), avisarlo y no commitear vacío
- Push automático al cerrar — el usuario ya lo aprobó (2026-05-25)
- Si hay cambios sin commitear que NO son del resumen, avisar al usuario antes de tocar nada
- **Una sola redacción larga por cierre (el handoff). Si estás escribiendo el mismo párrafo
  por segunda vez en otro archivo, estás haciendo el cierre viejo — pará y poné el puntero.**

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
