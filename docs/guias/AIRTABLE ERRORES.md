up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# AIRTABLE ERRORES — Registro de errores y lecciones

> Cada vez que algo falla con Airtable, se documenta acá.
> LEER ANTES de tocar cualquier fórmula, campo o integración con Airtable.

---

## 1. ARRAYJOIN no funciona con multipleRecordLinks

**Fecha:** 2026-05-25
**Qué pasó:** `FIND(record_id, ARRAYJOIN({FAMILIAS}))` devolvía 0 resultados aunque la reserva existía. Aurora decía "no tenés reservas" cuando el padre acababa de agendar.
**Por qué:** Los campos `multipleRecordLinks` (como NINO, FAMILIAS, HORARIO) contienen record IDs internos. `ARRAYJOIN` sobre estos campos NO produce texto buscable con `FIND`.
**Solución:** Usar campos `multipleLookupValues` (lookups de texto) en vez de los record links. Ejemplo: `FIND('FAMILIA Lafuente', ARRAYJOIN({FAMILIA}))` funciona porque `FAMILIA` es un lookup que devuelve texto.
**Regla:** NUNCA usar `FIND(record_id, ARRAYJOIN({campo_link}))`. Siempre buscar por un lookup de texto o por `RECORD_ID()='recXXX'`.

---

## 2. IS_AFTER no incluye el día exacto

**Fecha:** 2026-05-24
**Qué pasó:** Reservas del día actual no aparecían como futuras.
**Por qué:** `IS_AFTER({FECHA}, '2026-05-24')` es estricto — solo devuelve fechas DESPUÉS del 24, no el 24 mismo.
**Solución:** Usar el día anterior: `IS_AFTER({FECHA}, '2026-05-23')` para incluir hoy.
**Regla:** `IS_AFTER` = estrictamente después. Para incluir hoy, usar ayer como referencia.

---

## 3. Campos eliminados causan error 422 silencioso

**Fecha:** 2026-05-05
**Qué pasó:** Registros de PRUEBA FENIX no se creaban. Sin error visible en logs.
**Por qué:** Campo MONTO fue eliminado de la tabla pero el código seguía mandándolo en el POST. Airtable devuelve 422 pero el código no logueaba el body del error.
**Solución:** Verificar campos existentes con GET antes de POST/PATCH. Loguear siempre el body de errores 4xx.
**Regla:** Antes de POST/PATCH, verificar que TODOS los campos existen en la tabla.

---

## 4. Opciones de select no matchean (case sensitive)

**Fecha:** 2026-05-05
**Qué pasó:** Código mandaba "F. PRUEBA" (con espacio después del punto) pero Airtable tenía "F.PRUEBA" (sin espacio). Error 422 silencioso.
**Solución:** Copiar las opciones EXACTAS de Airtable, no escribirlas de memoria.
**Regla:** Opciones de singleSelect/multipleSelects son CASE SENSITIVE y SPACE SENSITIVE. Siempre verificar con GET.

---

## 5. Crear campos en la base equivocada

**Fecha:** 2026-04-26
**Qué pasó:** Campos APODO se crearon en la base Fenix vieja en vez de Salsa Soul (la base activa).
**Por qué:** No se verificó AIRTABLE_BASE_ID antes de crear.
**Solución:** Siempre GET /meta/bases/{base}/tables antes de crear campos.
**Regla:** VERIFICAR qué base está configurada antes de cualquier operación de metadata.

---

## 6. Suponer datos en vez de consultarlos

**Fecha:** 2026-05-09
**Qué pasó:** Ivan preguntó por qué un lead desapareció. En vez de consultar Airtable, empecé a teorizar.
**Solución:** Ante CUALQUIER pregunta sobre datos de Airtable: primero consultar, después opinar.
**Regla:** NUNCA teorizar sobre datos de Airtable. Consultarlo PRIMERO.

---

## Reglas generales

1. **SIEMPRE verificar antes de escribir** — GET antes de POST/PATCH/DELETE
2. **NUNCA usar ARRAYJOIN con record links** — usar lookups de texto
3. **IS_AFTER es estricto** — usar día anterior para incluir hoy
4. **Loguear body de errores 4xx** — Airtable da info útil en el body
5. **Opciones select son exactas** — copiar, no escribir de memoria
6. **Verificar AIRTABLE_BASE_ID** — antes de crear campos/tablas
7. **Consultar antes de opinar** — datos reales, no teorías
8. **Buscar en la web antes de probar** — Airtable tiene documentación
