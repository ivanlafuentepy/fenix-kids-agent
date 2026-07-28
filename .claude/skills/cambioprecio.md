# /cambioprecio — Cambiar un precio en TODOS los lugares donde vive

Recibís como argumento: $ARGUMENTS (el precio nuevo, ej: "el pack pasa a 400mil", "la prueba sube a 120mil", "matrícula 150").

> Este skill salió del cambio del 2026-07-28 (mensual 240k → pack de 350k). La memoria decía
> "4 archivos" y en realidad eran **7 + la web**: los 3 que faltaban (los 2 fallbacks de
> `main.py` y el follow-up de `reminders.py`) los encontró un grep de control, no la lista.
> Un precio viejo suelto = un lead recibe un número equivocado y se cobra de menos.

---

## Paso 0 — Cerrar el esquema con Ivan ANTES de tocar nada

Un precio nunca viene solo. Preguntar (UNA pregunta por vez) hasta poder llenar esta tabla:

| | 1 hijo | 2 hermanos | 3 hermanos |
|---|---|---|---|
| Clase de prueba | | | |
| Plan/pack vigente | | | |
| Matrícula anual | | | |

Y las 3 dudas que siempre aparecen:
1. ¿Los que ya están pagando el plan viejo **siguen con el viejo** o migran? (28/07: siguen aparte)
2. ¿La matrícula es por niño o por familia? (hoy: **por niño**)
3. Si es un plan nuevo, ¿cómo se llama y **vence**? (el pack de 5 NO vence)

Mostrarle la tabla llena y esperar el OK antes del Paso 1.

---

## Paso 1 — `/pre-cambio` (obligatorio)

Toca `prompts.yaml`, `main.py`, `afiches.py` y `pagos.py` → el skill `/pre-cambio` no es opcional.
Simular los 5 escenarios, con atención especial al **5**: `monto_prueba_por_hijos_detallado`
(`pagos.py`) parsea el monto del historial con regex `(\d{2,3})[.\s]?(\d{3})`. Si el precio nuevo
tiene otra cantidad de dígitos (ej. 1.200.000), **esa regex deja de matchear** y el pago se
registra con el fallback de 100k en silencio. Verificarlo explícitamente.

---

## Paso 2 — Los 7 lugares del agente

Editar TODOS. Ninguno es opcional:

| # | Archivo | Qué tiene |
|---|---|---|
| 1 | `config/prompts.yaml` | sección PRECIOS + la línea de FASE 2B (inscripción) |
| 2 | `agent/lead_menu.py` | `TEXTO_PRECIOS` y `TEXTO_HERMANOS` (menú de botones) |
| 3 | `agent/afiches.py` | `msg_precios` y `msg_hermanos` (acompañan al afiche) |
| 4-5 | `agent/main.py` (**× 2**) | los fallbacks de texto de los interceptores, cuando el afiche YA se envió (buscar `_pide_hermanos` / `_pide_precios`) |
| 6 | `agent/reminders.py` | `_MENSAJES_SEGUIMIENTO["A"]` — el follow-up automático repite precios |
| 7 | `agent/pagos.py` | dict `PRECIOS` (sin consumidores hoy, pero es la tabla de referencia) |

---

## Paso 3 — El grep de control (NO saltear)

Después de editar, buscar el valor **VIEJO** en todas sus formas:

```bash
grep -rn "240\.000\|240_000\|240mil\|4 sábados" agent/ config/ --include=*.py --include=*.yaml
```

**No decir "listo" hasta que vuelva vacío.** La tabla de arriba es el punto de partida, no la
garantía: si aparece un lugar nuevo, agregarlo a la tabla de este skill y a la memoria
`reference_donde_viven_precios_aurora`.

---

## Paso 4 — Afiche

Ivan suele mandar el PNG nuevo. **Leerlo con Read y verificar que los números coincidan con la
tabla del Paso 0** antes de publicarlo (un afiche con otro precio es peor que no cambiarlo).

```bash
cp "<png nuevo>" static/afiche_fenix.png     # el que manda WhatsApp
py -3 -c "from PIL import Image; Image.open(r'<png>').convert('RGB').save(r'C:\Users\IVAN LAFUENTE\Projects\fenixkidsacademy-web\assets\afiche-precios.jpg','JPEG',quality=88,optimize=True)"
```

El de horarios (`afiche_horarios.png`) solo cambia si cambian los horarios.

---

## Paso 5 — La web (repo aparte, **rama master**)

`Projects/fenixkidsacademy-web/index.html`, sección `<!-- PRECIOS -->`: cards + tabla de hermanos.

⚠️ **Los links de pago van firmados**: `sig = HMAC(LINK_SECRET, "fenix:{monto}")[:16]`
(`agent/pagos_tarjeta.py`). Cambiar el monto sin refirmar deja el link **roto para el cliente**
sin que nada falle de este lado. `LINK_SECRET` NO está en el `.env` local — sale de las variables
de Railway (GraphQL, ver CLAUDE.md global). **Validar el algoritmo recalculando una firma vieja
que esté publicada**: si no la reproduce, las nuevas también van a estar mal.

```bash
cd ../fenixkidsacademy-web && git push origin master   # OJO: master, no main
```

---

## Paso 6 — Airtable (solo si el plan es nuevo, no si solo cambia el monto)

- El `CONCEPTO` de PAGOS es un singleSelect: **mirar las opciones existentes antes de inventar
  una** (`PAQUETE5` ya existía y se reusó). Skill `airtable-seguro`.
- `VENCIMIENTO_FORMULA` calcula el vencimiento por concepto con un SWITCH: un concepto que no
  esté ahí queda **sin vencimiento**. Eso es correcto para un pack que no vence y un bug para
  un plan que sí vence — decidirlo a propósito, no por omisión.
- Si el plan nuevo lleva saldo de clases, va por `recargar_pack()` (ver [[project_pack_clases]]).

---

## Paso 7 — Deploy (dos pushes, nunca uno)

Regla 8 del CLAUDE.md: si toco prompt + código, **código primero**.

1. Commit 1: los 6 archivos de código + el afiche → push → esperar deploy → verificar.
2. Commit 2: `config/prompts.yaml` → push.
3. La web es un repo aparte: su propio commit y push a `master`.

Verificar el deploy con algo real, no con el reloj:
```bash
curl -s -o /dev/null -w "%{size_download}\n" -L https://fenix-kids-agent-production.up.railway.app/static/afiche_fenix.png   # debe pesar lo del afiche nuevo
curl -s https://fenixkidsacademy.com/ | grep -o "<nombre del plan nuevo>" | head -1
```

---

## Paso 8 — Definition of Done

- [ ] `py -3 -c "import agent.main"` sin errores
- [ ] `py -3 -m pytest tests/ -q` (30 tests)
- [ ] El grep del Paso 3 vuelve **vacío**
- [ ] Afiche nuevo servido en prod (tamaño distinto al viejo)
- [ ] La web muestra el precio nuevo en producción
- [ ] Links de pago: firma nueva verificada contra el algoritmo
- [ ] **Prueba real**: escribir "precios" desde un número que NO sea el de Ivan → debe llegar el
      afiche nuevo + el texto nuevo. Esto necesita un mensaje entrante de verdad; si no se puede,
      **decirlo explícitamente** en vez de darlo por hecho.
- [ ] Actualizar `docs/FENIX_RESUMEN.md` §8 (Precios y Planes) y la memoria
      `reference_donde_viven_precios_aurora` si cambió el mapa

---

## Anti-racionalizaciones

| Excusa | Respuesta |
|---|---|
| "Ya cambié los 4 archivos de la memoria" | Eran 7 el 28/07. Corré el grep igual |
| "Es solo el monto, la web puede esperar" | La web cobra con links firmados: monto viejo o firma vieja = plata que no entra |
| "El afiche lo cambio después" | El afiche es lo PRIMERO que ve el lead. Precio nuevo en texto + afiche viejo = desconfianza |
| "Total el dict PRECIOS no lo usa nadie" | Cierto hoy, pero es la tabla de referencia. Dejarlo desactualizado es sembrar el próximo bug |
| "Pusheo todo junto que es un solo cambio" | Código y prompt van separados: si el prompt rompe, querés saber cuál fue |
