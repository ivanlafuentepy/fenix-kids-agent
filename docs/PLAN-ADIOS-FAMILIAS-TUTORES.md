# Plan — Desaparición de FAMILIAS FENIX y TUTORES FENIX

> Auditoría 03/08/2026 (censo completo de código + Airtable). Objetivo de Iván: que las
> tablas TUTORES FENIX y FAMILIAS FENIX desaparezcan y ALUMNOS sea la tabla única de
> personas. Contexto previo: migración personas unificadas del 28/07 (padres ya son filas
> de ALUMNOS con NEGOCIO, niños vinculados por `PADRE/MADRE (ALUMNOS)`).

## El hallazgo que ordena todo

Las dos tablas NO están en la misma situación:

- **FAMILIAS FENIX ya está medio muerta**: ~47 refs y la mayoría son fallback legacy
  comentado como "muere con la tabla" + 6 funciones código muerto. El alta actual
  (`crear_grupo_a_prueba`, niño-eje) NO crea familias. **Eliminarla es viable ya.**
- **TUTORES FENIX es la columna vertebral viva de Aurora**: ~88 refs. `CELL LIMPIO` es
  la clave primaria de facto — el router Aurora/Ivan, el contexto del LLM, las tools,
  los pagos (`PAGA`), las facturas (`TUTOR` → lookup `TUTOR RUC`), el juego (`CODIGO`),
  los broadcasts y el loop de facturas cuelgan de ahí. **Eliminarla es rediseñar la
  identidad del agente — proyecto aparte, decisión aparte.**

Por eso el plan tiene DOS etapas independientes. La 1 se hace; la 2 se decide después.

---

## ETAPA 1 — FAMILIAS FENIX desaparece (~2 sesiones, riesgo medio-bajo)

### 1.0 Pre-check de datos (solo lectura, antes de tocar código)
- [x] ✅ 03/08: cero fichas "solo-FAMILIAS" — la única familia sin link a TUTORES tiene a su
      padre (Rosa Duarte) ya en TUTORES; cero teléfonos solo-en-FAMILIAS; cero niños sin
      PADRE/MADRE; cero tutores sin hijos. Los 2 pagos FAMILIA-sin-PAGA tienen NIÑOS+NEGOCIO.
- [ ] ¿Quién lee los lookups `RESERVAS FENIX.FAMILIA` / `.ESTADO PLAN`? (código no los usa —
      verificar vistas/interfaces de Airtable con Iván).

### 1.1 Aurora — un push (código) — ✅ HECHO 03/08 (commit 6ebaf1f, deploy SUCCESS, prod HTTP 200, loop de facturas corriendo con la fórmula nueva)
- [x] Borrar código muerto verificado: `crear_familia_completa`, `crear_familia`,
      `vincular_familia_a_lead`, `buscar_familia_por_nombre`, `marcar_control_datos`,
      `_asegurar_datos_fiscales` (facturas.py:97) + imports muertos en `main.py:83-90`
      y `resumenes.py:11`.
- [x] Dejar de ESCRIBIR legacy: merge de `TUTORES.FAMILIA` en `crear_o_actualizar_tutor`
      (769-775), `NIÑOS.FAMILIA` en `crear_nino` (905-909).
- [x] ⚠️ `crear_nino` 919-923 lee `FAMILIAS.ESTADO PLAN` para espejar `NIÑOS.ESTADO` —
      si falla en silencio el niño queda "cliente" y un lead se rutea a Aurora. Reemplazar:
      el ESTADO viene del flujo (A PRUEBA en alta, ACTIVO en inscripción), nunca de FAMILIAS.
- [x] Borrar fallbacks legacy: `buscar_familia_por_telefono`, `familia_es_activa`,
      `obtener_ninos_de_familia`, rama fallback de `obtener_tutores_de_familia` (702-721),
      `obtener_contacto_familia` + su uso en `loops.py:1057`, fallback de
      `obtener_grupo_familiar` (1022-1033), compat de `juego_familia_codigo` (213-221),
      fallback de `confirmacion_sabado` (103-113), fallback de `_candidatos_a_prueba`
      (171-183), pista de `flujo_pagos` (133-149), `tool_executor` (63-72), camino
      FAMILIAS de `eliminar_todo_de_telefono` (455-460), `manejar_respuesta_factura:190`,
      `_asegurar_datos_fiscales:117-119`, `restaurar_aurora` (main:1191).
- [x] SQLite: dejar de usar `familia_id` de `ab_test` (155-172) como pista.
- [x] Fórmulas en código que referencian el link: `listar_facturas_fenix_para_enviar:1983`
      (`OR({TUTOR}!='',{FAMILIA FENIX}!='')` → `{TUTOR}!=''`) y `resumenes.py:934`
      (`OR({NIÑOS FENIX}!='',{FAMILIA FENIX}!='')` → `OR({NIÑOS FENIX}!='',{PAGA}!='')`).
      **Fórmulas primero en el código, campo después en Airtable** — al revés rompe el loop.
- [x] Bonus: fix `NameError` latente `inscripcion.py:603` y `:620` (`familia_id` no definido).
- [x] `scripts/generar_voces_alumnos.py` usa FAMILIAS — reescribir o marcar obsoleto.

### 1.2 facturador-set — ✅ código y .env de ESTA máquina hechos 03/08 (commit f64f90b). ⚠️ Si el robot corre en OTRA máquina: git pull + editar su .env (sacar {FLIA FENIX RUC} del NEG1_FILTRO) ANTES de la 1.3
- [x] `.env` (a mano, está gitignored) + `.env.example:30`: sacar `{FLIA FENIX RUC}` del
      `NEG1_FILTRO`. Si el lookup muere antes que el filtro → **422 y NEG1 entero deja de
      facturar, Salsa incluida** (raise_for_status sin try/except).
- [x] `airtable.py:133-135`: borrar `fenix_txt` / `FLIA FENIX RUC` de la cadena de RUC.
- [x] `airtable.py:149`: flag `fenix` pasa a `FUENTE == "FENIX KIDS ACADEMY"` (los links
      no crashean al desaparecer — `f.get()` da None — pero el flag quedaría siempre False).

### 1.3 Airtable — ✅ HECHO 03/08
- [x] Automation `CREAR FACTURA` con script nuevo (Iván lo pegó y publicó; verificado por
      API: draft = deployed, valida ALUMNO o PAGA y linkea TUTOR para pagos Fenix).
- [x] Tabla FAMILIAS FENIX **ELIMINADA** (actionId revert: actVlFKI0ZkLwvYi8). Backup previo:
      `whatsapp-agentkit/knowledge/backup_familias_fenix_2026-08-03.json` (79 registros +
      schema de 48 campos). Airtable convirtió los 9 links entrantes en **singleLineText**
      (conservan los nombres como rastro) y dejó 3 lookups rotos inertes.
- [ ] Limpieza cosmética (a mano en la UI, sin apuro): borrar los campos huérfanos
      `PAGOS.FAMILIA FENIX`+`FAMILIA NOMBRE`, `FACTURAS.FAMILIA FENIX`+`FLIA FENIX RUC`,
      `NIÑOS/TUTORES/LEADS/SEGUIMIENTO/ASISTENCIA/PRUEBA LEGACY.FAMILIA`,
      `RESERVAS FENIX.FAMILIAS`+`FAMILIA` (la API no borra campos).

### 1.4 Verificación end-to-end
- [x] Robot: `pendientes()` con el filtro nuevo contra la base real → OK sin 422, resolvió
      una factura Fenix por TUTOR RUC (RUC 1953350, ₲740k, fenix=True). 03/08.
- [x] Aurora post-borrado: HTTP 200, loop de facturas polleando sin errores en logs.
- [ ] Mensaje real de un padre → Aurora lo reconoce (identidad va por TUTORES, intacta).
- [ ] Alta de prueba completa (lead → pago → grupo creado sin FAMILIA).
- [ ] `resumen anuncios` y confirmación del sábado (jueves 06/08) corren sin error.

⚠️ Hallazgo lateral 03/08 (NO causado por la migración): 3 facturas en "EMITIENDO 13:40-13:43"
de una corrida del robot que murió — revisar en Marangatú y marcar FACTURADO o limpiar:
rec2UDvotloW13tqa, recAOnmj3dVuF1pW0, recyguE0SoC4NlmSm.

---

## ETAPA 2 — ✅ EJECUTADA 09/08/2026 (sesión auditoría+migración; tabla renombrada "TUTORES FENIX LEGACY")

**Lo que se hizo (todo verificado en prod):**
- Campos nuevos: `ALUMNOS.CODIGO FENIX` (fldt1UHfR22wFiTTn), `ALUMNOS.FACTURA FENIX`
  (fldYFJWslw2ljiYiu), `FACTURAS.TUTOR (ALUMNOS)` (fldw4H3XP0jtWc5Or) +
  lookup `TUTOR RUC (ALUMNOS)` (fldzn86XIkuX8faBD).
- Backfill (`scripts/backfill_tutores_a_alumnos.py`): 5 filas CODIGO/FACTURA
  (43E8EW en la fila personal de Iván) + 2 facturas espejadas. 0 sin match.
- Juego a ALUMNOS (`juego_endpoints.py`): código, hijos, fotos, validación —
  verificado `/juego/familia/43E8EW` en prod. Murieron los stubs.
- Facturas a ALUMNOS (`facturas.py`): datos fiscales en `FACTURA FENIX`,
  factura linkea `TUTOR (ALUMNOS)`; selector de envío acepta ambos links.
- `PAGA (ALUMNOS)` / `TUTOR (ALUMNOS)` en pagos/inscripción/lead (eran los
  CRÍTICOS de la auditoría: el link legacy tumbaba el POST del pago entero).
- facturador-set (`b0ec54d` master): cadena RUC con lookup nuevo + legacy;
  `NEG1_FILTRO` actualizado en `.env` y `.env.example`. `pendientes()` OK.
- Limpieza: `buscar_tutor_legacy_por_telefono` y `ES QUIEN PAGA` muertos;
  `test_local` modo padre por ALUMNOS; `_TUTORES` pasó a table ID.
- **Tabla renombrada "TUTORES FENIX LEGACY"** (canario ~30 días). Backup:
  `backups/2026-08-09/tutores-fenix-backup.json` (101 registros).

**Queda para el borrado definitivo (~30 días, lo hace Iván):**
1. ~~Pegar el script nuevo de la automation CREAR FACTURA en la UI~~ ✅ **HECHO
   09/08** (Iván lo pegó y publicó; verificado por API: deployed + valid, el
   draft no difiere de lo desplegado, y linkea `TUTOR (ALUMNOS)` cuando el
   pago es de FENIX). Copia del script en
   `docs/operaciones/automation-crear-factura-2026-08-09.js`.
2. Antes de BORRAR la tabla: sacar `{TUTOR RUC}` del `NEG1_FILTRO` del robot
   y de la cadena (`airtable.py`), y el fallback de `obtener_contacto_tutor`.
   Un lookup muerto en el filtro = 422 y NEG1 entero deja de facturar.
3. Borrar la tabla + campos huérfanos (`FACTURAS.TUTOR`, `TUTOR RUC`,
   `PAGOS.PAGA`, `LEADS.TUTOR FENIX`).

## (histórico) ETAPA 2 — dimensionamiento original

Qué implicaría (para dimensionar, no para ejecutar ya):
1. **ALUMNOS gana los campos que le faltan**: `PARENTESCO`, `ES QUIEN PAGA`,
   `CODIGO` (juego), `FACTURA` (texto fiscal Fenix — o unificar con `FACTURA OPCION`/`RUC`
   que ALUMNOS ya tiene). `APODO` y `TELEFONO LIMPIO` ya existen.
2. **Identidad**: `buscar_tutor_por_telefono` pasa a buscar en ALUMNOS
   (`TELEFONO LIMPIO`, NEGOCIO contiene FENIX) con fallback transitorio a TUTORES.
3. **Links nuevos** (Airtable no permite re-apuntar): `PAGOS.PAGA (ALUMNOS)`,
   `FACTURAS.RECEPTOR (ALUMNOS)` + lookup de RUC, `LEADS FENIX.TUTOR (ALUMNOS)`;
   los `NIÑOS.PADRE/MADRE (ALUMNOS)` **ya existen y están backfilleados** (28/07).
4. **El reparto de facturas Dorita vs Aurora deja de depender del link** y pasa a
   `FUENTE`/`NEGOCIO` (ya existe en FACTURAS y la automation lo copia). Esto resuelve
   de raíz la pregunta original "¿y si la factura es de Fenix?".
5. facturador-set: `NEG1_FILTRO` y cadena de RUC al lookup nuevo (patrón tolerante:
   leer nuevo con fallback a viejo, verificar corrida limpia, recién sacar el viejo).
6. ~88 refs en Aurora a reescribir por subsistema (identidad → altas → pagos →
   facturas → juego → broadcasts), un push por subsistema.

**Recomendación:** ejecutar recién cuando la Etapa 1 esté estable. Mientras tanto,
mitigar el drift de datos duplicados (tutor cambia de teléfono → actualizar ambos):
al editar teléfono/nombre de un tutor, espejar al ALUMNO linkeado por el mapeo.

---

## Código muerto adicional encontrado (independiente del plan)
- `facturador-set/scripts/probar_apertura.py:31` — `KeyError` garantizado (`factura_opcion`
  no existe en la salida de `pendientes()`), ya estaba roto.
- `facturador-set/airtable.py:150` — `alumno_ids` no se usa downstream.
- `fenix-kids-agent/tests/test_local.py` importa 3 funciones que la Etapa 1 borra — actualizar.
