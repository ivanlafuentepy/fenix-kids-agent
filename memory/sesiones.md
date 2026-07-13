# 🗂️ Índice de Sesiones — FENIX KIDS AGENT

> **Por qué existe:** la extensión de Claude Code para VS Code no deja renombrar las sesiones del panel (cachea los nombres y no relee archivos; `/rename` de la CLI no se sincroniza). Solución: llevamos nuestro propio índice. Claude ve el código de la sesión; vos le ponés el nombre; lo vinculamos acá.
>
> **Para retomar una sesión:** copiá su código y en la terminal:
> ```
> claude --resume <código>
> ```
> El `/cierre` actualiza esta tabla solo.

---

| Nombre | Código (sessionId) | Fecha | Qué se hizo |
|--------|--------------------|-------|-------------|
| auditoría de skills | c26595b6-67d6-4cbf-b0d6-a08c4746d93b | 2026-07-07 | Auditoría de ~50 skills/commands de los 4 agentes + 10 globales + 168 sesiones. Skills globales nuevos (agente-ops, renovar-token-meta, airtable-seguro, pendientes) + estandares-trabajo.md. FENIX: /masivo + export diario automatizado. |
| TV Guardianes + fixes | ab21583d-274b-40b9-943e-496dc7bb0d42 | 2026-07-11 | TV "Guardianes de Hoy" (/juego/dia + /lista) + fixes menú secre, acentos del selfie y cache del video del tótem |
| el sábado del Espejo | b364cbf5-7b9c-4633-8402-a0dac765dde3 | 2026-07-11/12 | Primera jornada del juego con niños reales: avatar en tablet + vueltas por cara + presentación en TV + mapa como reposo + auto-reload kiosk + fixes dos Fiorellas/asistencia FACE + diagnóstico tutores "Lead" |
| reservas por plantilla | ef69079f-2beb-4a30-aec4-1e3773bb6f31 | 2026-07-12 | Confirmación proactiva del sábado: plantilla `confirmacion_sabado_fenix` (WABA propio FENIX) los jueves 9AM a familias al día → Sí pregunta turno y agenda, No no reserva. QR solo para leads (familias = check-in facial). Loop APAGADO por env. Skill /plantilla corregido. |
| la auditoría de los 21 fixes | 69573ea6-6451-467a-9ee7-7b410fbb2681 | 2026-07-12/13 | Auditoría completa con 6 agentes (~70 hallazgos, docs/estado/AUDITORIA-2026-07-12.md) + 21 pushes verificados: PII de menores fuera de los endpoints públicos, dedup que perdía mensajes, meta.py ciego a red, max_records truncando, dinero (firma con teléfono, guards, rescate post-pago), prompt cache que nunca cacheó, tests muertos revividos, Telegram de raíz. Decisión: eliminar FAMILIAS (niño-eje), en pausa hasta cerrar PRUEBA |
| arrancó la migración del niño | 69573ea6-6451-467a-9ee7-7b410fbb2681 | 2026-07-13 | Cache auditado en los 4 agentes (Dorita sano, NEO muerto→arreglado, Genesis prompt chico) + ARRANCA la migración FAMILIAS→NIÑO: M1 campos en Airtable (PAGOS.NIÑOS FENIX múltiple + PAGA, NIÑOS.PADRE/MADRE/VENCE EL/AL DÍA?) y M2 backfill — 15 pagos cubren 2-3 hermanos con UN registro, 0 discrepancias contra FAMILIAS. Decisión: el pago NO se parte. Falta el código (espera al 18/07) |
