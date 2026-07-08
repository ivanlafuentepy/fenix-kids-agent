# Bitácora de Sesiones — FENIX KIDS AGENT

> Registro conversacional por sesión (qué pidió Iván, qué se hizo). Se agrega al final en cada `/cierre`.
> Fuente de estado estructurado: `docs/FENIX_RESUMEN.md`. Esto es el relato.

---

## 2026-07-07 — Sesión 28: Mundo Fénix, de mock a producción real

**Iván:** ¿Dónde consigo las pulseras para rastrear a los niños? La idea: que en cada estación hagan un ejercicio, hagan check con la pulsera, y al llegar al Fénix (la TV) les lea el recorrido automático y les cargue la vuelta con sus monedas.
**Fénix:** Investigué precios reales. Recomendé pulseras NFC pasivas NTAG213 (~$0.30-1.50) + ESP32+RC522 como lectores de estación + PN532 para el tótem. Aclaré que la etiqueta es pasiva (el lector es el que tiene energía), así que el niño lleva la pulsera y los lugares llevan los lectores.

**Iván:** No me cierra que manden video por WhatsApp, es incómodo. Y no puedo recibir 100 videos por día. ¿Se sube en la app y se controla después, o con IA?
**Fénix:** Cambié el diseño en PLAN-MAESTRO: video se sube EN la app → R2, acreditación inmediata, control asíncrono en 3 capas (checks automáticos + IA async + revisión humana solo de excepciones). La IA quedó para iteración 2.

**Iván:** Pero es la app web donde hacen el reto de 5 días. ¿Dónde eligen avatar, ven progreso y monedas?
**Fénix:** Mapeé qué vive dónde: la app (avatar, reto, progreso, banco), WhatsApp (canal + notificaciones), La Casona (pulseras, tótem, cámaras). Actualicé el plan con la decisión de videos en la app.

**Iván:** Armame todo el diseño y el plan de implementación de las pulseras.
**Fénix:** Escribí `SPEC-NFC-CIRCUITO.md` completo (hardware, firmware, endpoints, anti-trampa, fases N0-N7, presupuesto). Lo revisé críticamente con Fable y corregí 5 cosas: la vuelta se cierra en el tótem (no en la última estación), vinculación por Web NFC desde el celu del profe, timestamps del servidor, key por estación, dedupe explícito.

**Iván:** ¿Se puede tener otra TV con un mapa interactivo donde se ve dónde están y cómo se mueven los niños, cada uno con su avatar?
**Fénix:** Sí. Construí el nivel 1 gratis (`mapa.html`, avatares que se mueven por saltos con los taps NFC) y dejé `SPEC-BLE-TRACKING.md` para el nivel 2 (movimiento continuo con pulseras BLE, para después del piloto).

**Iván:** ¿Me sacás una foto con las cámaras para pasarle a ChatGPT y me arme un mapa?
**Fénix:** Bajé 19 snapshots de las cámaras del DVR por ISAPI a `Escritorio/FOTOS MAPA CASONA`. (De paso me corregí: eran las 13:50, no la madrugada — el reloj del DVR estaba bien, yo asumí la hora.)

**Iván:** [pasó el mapa de ChatGPT + video del Fénix saludando] Las monedas deberían salir de cada estación e ir a la casa donde está el niño.
**Fénix:** Integré el arte real como fondo del mapa, reposicioné las 5 estaciones (ninja/árbol/básquet/quincho/muelle) sobre las zonas reales, y reprogramé la animación de vuelta: las monedas vuelan de cada estación a la casa.

**Iván:** Manos a la obra con todo.
**Fénix:** Ejecuté las fases del backend con `/pre-cambio` + `/pre-deploy` + deploy incremental: A (eventos), N1 (circuito NFC), E (profe), B (checkin facial), F (voces). Conecté TV/mapa/tótem al backend real. Avisos de progreso por WhatsApp al 595982790407 como pidió.

**Iván:** Ya te pasé la API key de ElevenLabs, ya la usamos para George.
**Fénix:** La recuperé de la transcripción de anoche, la verifiqué y generé 23 alumnos con voz (la quota free cortó ahí). Corregí un bug de tildes en `tvVoz()`.

**Iván:** Listo, vamos con el deploy del juego.
**Fénix:** Repo propio `mundo-fenix-app` + Cloudflare Pages → `mundo-fenix.pages.dev`. Saqué la key hardcodeada del tótem. Mata todos los líos de LAN de las sesiones 26-27.

**Iván:** Vamos con el 8/9/10 (F2 + F3 + saludo personalizado).
**Fénix:** Plan mode → aprobado. Decisión: arquitectura híbrida (Railway lógica/datos + CF solo videos→R2). Ejecuté P1-P8: 3 tablas Airtable, link mágico, economía en el servidor, R2 + Functions de video, reto-video + muestreo Telegram, frontend modo real (multi-hijo + pantalla familia), saludo "entrenaste N días". Todo verificado en prod, health 200.

**Commits de la sesión (agente):**
- `cf73321` — router `/juego` con ledger de eventos (Fase A)
- `f49f000` — circuito NFC: pulseras, pasadas, cierre de vuelta en el tótem (N1)
- `7e64b9e` — app del profe: `/juego/alumnos` + `/static/profe.html` (Fase E)
- `35a0f14` — checkin facial del Espejo: `/juego/checkin-face` (Fase B)
- `9d1eca7` — script de voces por alumno con ElevenLabs (Fase F)
- `3f9505c` — link mágico de familia (F2-P2)
- `2bb5ae2` — `/juego/accion`: economía en el servidor (F2-P3)
- `ab573b8` — `/juego/reto-video`: video con acreditación inmediata + Telegram (F3-P5)
- `e710cc2` — saludo "entrenaste N días en casa" en las llegadas (F2-P7)

**Repo del juego (`mundo-fenix-app`):** varios commits + 4 deploys a Cloudflare Pages (juego, Function de videos, modo real).

**Nota:** en paralelo corrió otra sesión que commiteó CLAUDE.md/skills/export (`210e488`, `06d36fa`, `b7c3b1e`, `c4c337f`, `5baa19b`) — no es trabajo de esta sesión.
