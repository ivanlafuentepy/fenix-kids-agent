up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

---
name: Estado del proyecto FENIX KIDS
description: Snapshot al 2026-04-26 — engranaje redes sociales + follow-up diario construido
type: project
---
up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]


**Estado:** en producción (Railway, deploy automático)

## Arquitectura actual
- **Profe Ivan** maneja leads: FASE 1.5 en 2 pasos → diagnóstico diferido → afiche automático → pago → agenda
- **Aurora** atiende familias inscriptas: onboarding verificación datos → CONTROL DATOS check → agenda multi-hijo con apodos
- **Padres inscriptos sin modo nocturno**
- **Airtable** base [[SALSA SOUL]] (appWwCQxALdMMV4MA)
- **Google Calendar ELIMINADO**
- **RESERVAS FENIX**: 1 niño = 1 registro, campo NINO (sin Ñ), FAMILIAS vinculado

## Nuevo: Engranaje redes sociales
- **CONTENIDO FENIX** (Airtable): posteos vinculados a niños → WhatsApp automático
- **REDES FENIX** (Airtable): perfiles de redes sociales
- **contenido_social.py**: polling cada 5 min + calendario diario (lun=IG, mar=FB, mié=TT, jue=YT, vie=Threads) + recordatorio viernes 18:00
- **enviar_plantilla**: soporte template messages en provider Meta
- **Integración [[POSTIZ]]**: Claude de Postiz crea registro en CONTENIDO FENIX → Fenix envía WhatsApp

## Tablas Airtable
LEADS FENIX, PRUEBA FENIX, FAMILIAS FENIX, NIÑOS FENIX, HORARIOS FENIX, RESERVAS FENIX, DIAGNOSTICO FENIX, CONTENIDO FENIX, REDES FENIX

**Why:** Engranaje de redes sociales construido para mantener ventana 24h abierta con cada padre.
**How to apply:** Falta crear plantillas en Meta Business + push a prod + validar.
