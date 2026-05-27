up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

---
name: Próxima sesión FENIX KIDS
description: Pendientes tras sesión 2026-04-26 — engranaje redes sociales construido, falta validar + referidos
type: project
---
up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]


**Fecha del cierre:** 2026-04-26

## Lo que se hizo hoy

1. **Engranaje redes sociales completo**: tablas Airtable (CONTENIDO FENIX, REDES FENIX), módulo contenido_social.py (polling + calendario diario + recordatorio viernes), enviar_plantilla en provider Meta
2. **Documento de diseño**: [[ENGRANAJE_REDES_Y_REFERIDOS]].md con todo el proceso de decisión
3. **Integración [[POSTIZ]]**: diseñado el flujo [[EDITOR PRO MAX]] → Postiz → Airtable → Fenix → WhatsApp

## Pendientes para IVAN (manuales)

1. **Crear plantillas en Meta Business** — textos en PLANTILLAS_META.md (contenido_diario, contenido_hijo, recordatorio_clase)
2. **Actualizar links reales en REDES FENIX** de Airtable (ahora tienen placeholders)
3. **Borrar calendar_google.py** — ya no se importa
4. Completar APODOS, TALLA REMERA, CELL PADRE/MADRE en Airtable

## Pendientes de código

1. **Validar engranaje en producción** — push + probar con un registro de prueba en CONTENIDO FENIX
2. **Sistema de referidos** (REFERIDOS FENIX + detección números en chat + plantilla Meta)
3. **Menú Aurora** para padres inscriptos (10 opciones)
4. **Actualizar CLAUDE.md de Editor Pro Max** — instrucción de leer nombres archivos y generar tags #fenix_[apodo]

## P2

- Follow-up lunes post-clase
- Plan hermanos descuento automático
- Meta CAPI
- Flujo inscripción directa por WhatsApp

**Why:** Engranaje de redes sociales diseñado y construido. Falta crear [[PLANTILLAS_META|plantillas Meta]] y validar en producción.
**How to apply:** Primero Ivan crea plantillas en Meta, después push a prod y probar con registro de prueba.
