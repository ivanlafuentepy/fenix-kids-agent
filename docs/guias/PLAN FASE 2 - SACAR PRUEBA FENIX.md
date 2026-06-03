up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# PLAN FASE 2 — Sacar PRUEBA FENIX del medio (eliminar identidad triplicada)

> Diseñado el 2026-06-02 (sesión 8). NO ejecutado aún.
> Refactor grande que toca el flujo de venta en producción → se ejecuta sub-fase por sub-fase,
> cada una con `/pre-cambio` + `/pre-deploy` + verificar que Dorita y Fénix Agent no se rompan.
> Regla de oro: expand → migrate → contract. Nunca borrar antes de validar.

---

## 1. Objetivo

Eliminar la **identidad triplicada** de Fénix: hoy el mismo niño/familia se escribe en `LEADS FENIX` (funnel), `PRUEBA FENIX` (copia al pagar) y `FAMILIAS+NIÑOS` (al inscribir). El objetivo es que la persona se cargue **una vez** y avance por estados sin re-copiarse, y que `PRUEBA FENIX` desaparezca como tabla de identidad.

**Nota de prioridad:** el re-tipeo hoy lo hace el agente automáticamente (Haiku extrae y crea), no Ivan a mano. El valor es prolijidad de datos + conectar al papá con Salsa. El riesgo es alto (toca el flujo que da plata). Por eso va lento y modular, y solo si el resto del negocio está estable.

---

## 2. Estado actual (cómo funciona hoy)

```
Lead escribe ──→ LEADS FENIX (Ivan atiende). CONVERSION: CONSULTA
   │  paga la prueba
   ▼
PRUEBA FENIX (1 registro por hijo)         ← NO se crea familia todavía
   identidad copiada (NOMBRE, NOMBRE HIJO) + evento (FECHA, HORA, QR, PRESENTE) + PAGO + CONVERSION=PAGO
   │  se inscribe
   ▼
inscripcion.py toma datos de PRUEBA FENIX ──→ crea FAMILIA + NIÑOS, marca INSCRIPTO
   (FAMILIA se crea recién acá)
```

**Router (clave):** `buscar_familia_por_telefono` → si el teléfono está en `FAMILIAS FENIX` ⇒ **Aurora**; si no ⇒ **Ivan**.

### Los 4 roles de PRUEBA FENIX (lo que hay que reubicar)
| Rol | Campos | A dónde migra |
|---|---|---|
| **Identidad** | NOMBRE, APELLIDO, NOMBRE HIJO, APELLIDO HIJO, EDAD, FECHA NAC | FAMILIA + NIÑO (vinculado, no copiado) |
| **Evento de prueba** | FECHA RESERVA, HORA, PRESENTE, AUSENTE, HORA_CHECKIN, QR RESERVA, QR ENVIADO | RESERVAS FENIX + ASISTENCIA FENIX (ya existen) |
| **Pago** | MONTO, CONCEPTO, PAGOS(link) | PAGOS (concepto PRUEBA) — ✅ ya está |
| **Estado** | CONVERSION, INSCRIPTO, INSCRIPCION | LEADS.CONVERSION + FAMILIA.ESTADO PLAN |

### Call-sites de PRUEBA FENIX (qué hay que tocar)
- **Escriben**: `flujo_pagos.py` (crear_prueba_fenix al pagar), `main.py` (~4033 crear_prueba_fenix, marcar_qr_enviado_prueba en 4 puntos), `airtable_client.crear_prueba_fenix/actualizar_prueba_fenix`.
- **Leen**: `main.py` (checkin_prueba ~555, checkin_asistencia_prueba ~590, _armar_lista_asistencia ~707, _listar_alumnos ~827, get_alumno_by_slug ~882), `resumenes.py` (resúmenes de prueba/asistencia).
- **Borra**: `airtable_client.eliminar_todo_de_telefono` (borra de las 5 tablas — actualizar).

---

## 3. El problema del ROUTER (efecto colateral crítico)

Si creamos la FAMILIA al **pagar la prueba**, el router actual la detectaría y mandaría a ese papá —que está en pleno flujo de prueba con **Ivan**— a **Aurora**. Rompería la venta.

**Solución:** el router debe decidir el agente por **ESTADO**, no por "existe familia":
- Lead en `CONSULTA`/`PAGO` (probó pero no inscripto) → **Ivan**, aunque ya exista una FAMILIA en estado `A PRUEBA`.
- `INSCRIPTO` / FAMILIA en `ACTIVO`/`PAUSADO` → **Aurora**.

Implementación: `buscar_familia_por_telefono` (o la función que activa Aurora) filtra FAMILIAS por `ESTADO PLAN ∈ {ACTIVO, PAUSADO}`. Las `A PRUEBA` no activan Aurora.

---

## 4. Las 4 sub-fases (orden incremental, cada una deployable)

### Sub-fase 2.A — Crear FAMILIA al pagar la prueba (sin romper el router)
**Prerequisito (Ivan, UI):** agregar opción **`A PRUEBA`** al select `ESTADO PLAN` de FAMILIAS FENIX.
**Cambios:**
1. **Router** (`airtable_client.buscar_familia_por_telefono` + activación Aurora en `main.py`): activar Aurora solo si `ESTADO PLAN ∈ {ACTIVO, PAUSADO}`. Familia `A PRUEBA` ⇒ sigue Ivan.
2. **`flujo_pagos.py`**: al pagar la prueba, además de crear PRUEBA FENIX (se mantiene por ahora — dual-write), crear/buscar FAMILIA `A PRUEBA` + NIÑO(s) vinculados (reusar `crear_familia`/`crear_nino`). Vincular al LEAD.
3. **`inscripcion.py`**: al inscribir, si la familia ya existe (de la prueba), **cambiar ESTADO a ACTIVO** en vez de crear otra.
**Riesgo:** MEDIO (router + flujo pago). Aditivo: PRUEBA FENIX sigue, nada que lee se rompe.
**Verificación:** lead nuevo paga prueba → sigue con Ivan (no salta a Aurora) → al inscribir, familia pasa a ACTIVO y ahí sí Aurora. Probar con número de test.

### Sub-fase 2.B — Migrar el evento de prueba a RESERVAS + ASISTENCIA
**Cambios:**
1. La reserva de la clase de prueba se crea en **RESERVAS FENIX** (igual que inscriptos), no en PRUEBA FENIX.
2. QR / check-in de prueba usa el mecanismo de familia ya existente (`generar_qr_familia`, `/checkin/familia/{id}`, `crear_asistencia`).
3. Reapuntar las **lecturas** (checkin_prueba, _armar_lista_asistencia, _listar_alumnos, resúmenes de prueba) a leer de RESERVAS/ASISTENCIA + FAMILIA/NIÑO.
**Riesgo:** MEDIO-ALTO (toca QR, asistencia, resúmenes). Varios deploys chicos, uno por lectura.
**Verificación:** sábado de prueba → QR funciona, asistencia se marca, resúmenes cuadran.

### Sub-fase 2.C — Dejar de escribir PRUEBA FENIX (el corte)
**Cambios:**
1. Sacar `crear_prueba_fenix` del flujo (flujo_pagos.py, main.py). Todo va por FAMILIA/NIÑO/RESERVAS/PAGOS.
2. Actualizar `eliminar_todo_de_telefono` (sacar PRUEBA FENIX, mantener el resto).
3. inscripcion.py ya no toma datos de PRUEBA (la familia ya existe de 2.A).
**Riesgo:** ALTO (es el corte). Solo cuando 2.A y 2.B estén estables y verificadas en producción varios días.

### Sub-fase 2.D — Migrar histórico + deprecar
**Cambios:**
1. Backup de PRUEBA FENIX (ya hay snapshot en `backups/2026-06-02/`).
2. Asegurar que los ~73 registros históricos tengan FAMILIA/NIÑO/RESERVA/ASISTENCIA equivalente (script de migración, como el de conceptos).
3. Renombrar `PRUEBA FENIX` → `PRUEBA FENIX (legacy)`, read-only. Borrar recién tras X días sin incidentes.
**Riesgo:** MEDIO (datos). Reversible con backup.

---

## 5. Salvaguardas (todas las sub-fases)
- ✅ `/pre-cambio` antes de editar · `/pre-deploy` antes de pushear.
- ✅ Un cambio lógico por commit, deploy incremental, verificar entre cada uno.
- ✅ La base es compartida con Salsa: **Dorita no toca tablas Fénix** (solo PAGOS) — verificado. Aun así, probar que ambos agentes siguen vivos tras cada deploy.
- ✅ No borrar PRUEBA FENIX hasta que 2.A–2.C estén estables y el histórico migrado.
- ✅ Backup antes de cualquier migración de datos.

## 6. Prerequisitos en Airtable (Ivan, UI — no se pueden por API)
- Agregar opción **`A PRUEBA`** al select `ESTADO PLAN` de FAMILIAS FENIX (para 2.A).

## 7. Estimación honesta
Refactor de **varias sesiones**. 2.A es el paso de mayor valor/menor alcance pero ya toca el router. No hacer 2.C (el corte) hasta tener 2.A+2.B rodando en producción sin incidentes. Si el negocio está en un momento sensible (campañas activas, mucho lead), posponer.
