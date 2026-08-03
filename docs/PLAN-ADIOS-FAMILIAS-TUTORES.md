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
- [ ] ¿Quedan fichas "solo-FAMILIAS"? — tutores sin `HIJOS (COMO PADRE/MADRE)`, niños sin
      `PADRE`/`MADRE`, y teléfonos en `CELLS LIMPIOS TUTORES` de FAMILIAS que no existan
      en `TUTORES.CELL LIMPIO` (el comentario del código habla de ~10 fichas viejas).
      Migrarlas a mano ANTES de borrar fallbacks, o esos números caen a "lead".
- [ ] ¿Quién lee los lookups `RESERVAS FENIX.FAMILIA` / `.ESTADO PLAN`? (código no los usa —
      verificar vistas/interfaces de Airtable con Iván).

### 1.1 Aurora — un push (código)
- [ ] Borrar código muerto verificado: `crear_familia_completa`, `crear_familia`,
      `vincular_familia_a_lead`, `buscar_familia_por_nombre`, `marcar_control_datos`,
      `_asegurar_datos_fiscales` (facturas.py:97) + imports muertos en `main.py:83-90`
      y `resumenes.py:11`.
- [ ] Dejar de ESCRIBIR legacy: merge de `TUTORES.FAMILIA` en `crear_o_actualizar_tutor`
      (769-775), `NIÑOS.FAMILIA` en `crear_nino` (905-909).
- [ ] ⚠️ `crear_nino` 919-923 lee `FAMILIAS.ESTADO PLAN` para espejar `NIÑOS.ESTADO` —
      si falla en silencio el niño queda "cliente" y un lead se rutea a Aurora. Reemplazar:
      el ESTADO viene del flujo (A PRUEBA en alta, ACTIVO en inscripción), nunca de FAMILIAS.
- [ ] Borrar fallbacks legacy: `buscar_familia_por_telefono`, `familia_es_activa`,
      `obtener_ninos_de_familia`, rama fallback de `obtener_tutores_de_familia` (702-721),
      `obtener_contacto_familia` + su uso en `loops.py:1057`, fallback de
      `obtener_grupo_familiar` (1022-1033), compat de `juego_familia_codigo` (213-221),
      fallback de `confirmacion_sabado` (103-113), fallback de `_candidatos_a_prueba`
      (171-183), pista de `flujo_pagos` (133-149), `tool_executor` (63-72), camino
      FAMILIAS de `eliminar_todo_de_telefono` (455-460), `manejar_respuesta_factura:190`,
      `_asegurar_datos_fiscales:117-119`, `restaurar_aurora` (main:1191).
- [ ] SQLite: dejar de usar `familia_id` de `ab_test` (155-172) como pista.
- [ ] Fórmulas en código que referencian el link: `listar_facturas_fenix_para_enviar:1983`
      (`OR({TUTOR}!='',{FAMILIA FENIX}!='')` → `{TUTOR}!=''`) y `resumenes.py:934`
      (`OR({NIÑOS FENIX}!='',{FAMILIA FENIX}!='')` → `OR({NIÑOS FENIX}!='',{PAGA}!='')`).
      **Fórmulas primero en el código, campo después en Airtable** — al revés rompe el loop.
- [ ] Bonus: fix `NameError` latente `inscripcion.py:603` y `:620` (`familia_id` no definido).
- [ ] `scripts/generar_voces_alumnos.py` usa FAMILIAS — reescribir o marcar obsoleto.

### 1.2 facturador-set (la otra máquina) — ANTES de tocar Airtable
- [ ] `.env` (a mano, está gitignored) + `.env.example:30`: sacar `{FLIA FENIX RUC}` del
      `NEG1_FILTRO`. Si el lookup muere antes que el filtro → **422 y NEG1 entero deja de
      facturar, Salsa incluida** (raise_for_status sin try/except).
- [ ] `airtable.py:133-135`: borrar `fenix_txt` / `FLIA FENIX RUC` de la cadena de RUC.
- [ ] `airtable.py:149`: flag `fenix` pasa a `FUENTE == "FENIX KIDS ACADEMY"` (los links
      no crashean al desaparecer — `f.get()` da None — pero el flag quedaría siempre False).

### 1.3 Airtable — automation + campos (después de 1.1 y 1.2 deployados)
- [ ] Automation `CREAR FACTURA` (wflC685NYFZiNkXH5): hoy lee `PAGOS.FAMILIA FENIX` y si
      no hay ALUMNO linkea la factura a la familia. Cambiar a: sin ALUMNO → usar `PAGA`→
      link TUTOR de la factura (o tirar error claro). Editar el script en la UI (la API
      no edita customScript).
- [ ] Borrar campos link a FAMILIAS (los lookups dependientes mueren con ellos):
      `PAGOS.FAMILIA FENIX` (+`FAMILIA NOMBRE`), `FACTURAS.FAMILIA FENIX` (+`FLIA FENIX RUC`),
      `NIÑOS.FAMILIA`, `TUTORES.FAMILIA`, `RESERVAS FENIX.FAMILIAS` (+2 lookups),
      `LEADS FENIX.FAMILIA`, `SEGUIMIENTO FENIX.FAMILIA`, `ASISTENCIA FENIX.FAMILIA`,
      `PRUEBA FENIX LEGACY.FAMILIA`.
      Nota: los 64 pagos históricos de Fenix no pierden su marca — ya tienen `NEGOCIO`.
- [ ] Backup JSON completo de FAMILIAS FENIX a `knowledge/` → borrar la tabla.

### 1.4 Verificación end-to-end
- [ ] Mensaje real de un padre → Aurora lo reconoce (identidad va por TUTORES, intacta).
- [ ] Alta de prueba completa (lead → pago → grupo creado sin FAMILIA).
- [ ] Factura de Fenix emitida y enviada (robot + loop de Aurora).
- [ ] `resumen anuncios` y confirmación del sábado corren sin error.

---

## ETAPA 2 — TUTORES FENIX desaparece (proyecto aparte — DECIDIR después de la Etapa 1)

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
