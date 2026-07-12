# Bitácora de Sesiones — FENIX KIDS AGENT

> Registro conversacional por sesión (qué pidió Iván, qué se hizo). Se agrega al final en cada `/cierre`.
> Fuente de estado estructurado: `docs/FENIX_RESUMEN.md`. Esto es el relato.

---

## 2026-07-08 — Sesión 32: Llegó la tablet — puesta en marcha del Espejo del Guardián

**Iván:** Llegó la tablet, vamos con eso.
**Fénix:** Verifiqué que el tótem está deployado en `mundo-fenix.pages.dev/totem`, conectado al backend real y pidiendo la clave del juego una sola vez. Le pasé la `JUEGO_API_KEY` para tipear y la guía de Fully Kiosk (WiFi, permisos, montaje).

**Iván:** Conectado Fully. No escucha audio, la cámara está habilitada. Cuando toco responde con audio, pero cuando hablo no escucha. Yo quiero que el niño hable con Fénix.
**Fénix:** Le expliqué que el "escuchar" (Web Speech API) no anda en el WebView de Fully Kiosk. Después de idas y vueltas quedó claro lo que quería: **comandos de voz** ("Hola Fénix"), no conversación libre.

**Iván:** No, no quiero micrófono, el niño toca la pantalla y listo. Sacame las frases y el emoji hablando. Poné el espejo más alto que la cámara está arriba.
**Fénix:** Limpié el tótem: saqué frases/emoji/micrófono, tocar toda la pantalla despierta, subí el espejo pegado arriba (mejor encuadre para la cámara). Deployado.

**Iván:** No me reconoce esta mierda, se queda 2 segundos y nada. Ayer cargamos una foto mía con nombre ALAN.
**Fénix:** Miré los logs de Railway: **el backend SÍ te reconocía como ALAN** (200 OK, evento "llegada" creado) pero el tótem mostraba "Pedile al Guardián Mayor". Causa raíz: **`checkin-face` no devolvía CORS** → el navegador bloqueaba la respuesta. Fix en `juego_endpoints.py` (commit `def7359`), deployado y verificado. ALAN reconocido.

**Iván:** Toca y saca la foto de una, jamás espera el "Hola Fénix". Si no lo dice debería apagarse, no sacar la foto. Así estaba programado. ¿Por qué no se puede?
**Fénix:** Le aclaré la verdad: el "Hola Fénix" **SÍ se puede — en Chrome (donde estaba probando), NO en Fully Kiosk**. Yo lo había sacado pensando en Fully Kiosk. Lo **restauré** con su lógica: toca → escucha → si dice "Fénix" lee la cara; si no en 6s se apaga sin foto.

**Iván:** Sacá el cartel "Decí Hola Fénix", el niño ya sabe. El audio debería salir en la TV, no acá.
**Fénix:** Saqué el cartel (la escucha corre en silencio). Confirmé la arquitectura: el espejo lee rápido, el circo (voz "¿Quién despertó al ave Fénix?") va en la TV conectada al mismo backend.

**Iván:** ¿Por qué no usamos Chrome? Explicá la diferencia con Fully Kiosk.
**Fénix:** Comparé los dos: Fully Kiosk = kiosco completo pero sin motor de voz ni cámara fácil; Chrome = "Hola Fénix" + cámara OK pero no es kiosco. Recomendé **Chrome + anclaje de pantalla de Android**.

**Iván:** Perfecto, vamos con Chrome y el anclaje. Mañana seguimos, buen trabajo. /cierre
**Fénix:** Cierre de sesión.

**Commits de la sesión:**
- `def7359` — fix(juego): checkin-face devuelve CORS en todas las respuestas
- (frontend `totem.html` deployado a Cloudflare Pages por wrangler, `mundo-fenix/` sigue untracked en git)

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

## 2026-07-07 — Sesión 29: CLAUDE.md upgrade en los 4 agentes

- **Ivan:** "Sos mi senior engineering lead. Auditá y mejorá el CLAUDE.md para que un modelo más barato (Opus/Sonnet) rinda casi como Fable 5 cuando deje de usarlo. Aplicalo para agent kit, fenix, cowork, agente neo."
- **Fenix:** Auditoría real de los 4 proyectos (3 agentes Explore en paralelo + auditoría directa de FENIX). Gap principal: los CLAUDE.md describían templates/planes viejos, no los sistemas en producción. Reescritos los 4: FENIX (manual operativo real, 13 reglas duras, DoD), Dorita (stack completo, mapa de tamaños, DoD honesto sin CI), NEO (realidad: 1 curso, Bancard, 10 tablas Airtable), Genesis (doble identidad kit + instancia viva).
- **Ivan:** "300k y 350k son viejos, eliminalo. yosoyfenix no es de Dorita. Corregimos el path de NEO. Obsidian ya no usamos."
- **Fenix:** Precios viejos eliminados de `business.yaml` + `obtener_precios()` muerta eliminada (0 callers, verificado). `yosoyfenix` quitado del CLAUDE.md de Dorita (no existe en su código). `CLAUDE.local.md` de NEO corregido. Obsidian eliminado de CLAUDE.md de FENIX y NEO, `/cierre` reescrito para `docs/sesiones/`, 5 memorias de Obsidian borradas.
- **Ivan:** "Renombrar" (cowork) → eligió **genesis-agentkit**.
- **Fenix:** Renombrado completo: repo GitHub, carpeta local, remote, historial de Claude Code migrado, proyecto.yaml (alias Genesis, estado produccion), CLAUDE.md, README.
- **Ivan:** "Sí, hay otras 2 sesiones andando" (commitear).
- **Fenix:** Commits por path explícito en los 4 repos, sin tocar el trabajo de las otras sesiones. Deploys verificados por GraphQL de Railway: todos SUCCESS.
- **Ivan:** "Vamos a alinearlo" (repo de NEO).
- **Fenix:** Repo `curso-ia-agent` → `agente-neo`. Railway siguió el rename solo. El SERVICIO Railway queda como `curso-ia-agent` a propósito (renombrarlo regeneraría el dominio del webhook de Meta).
- **Hallazgo de seguridad reportado:** PATs de GitHub/Airtable en texto plano en `.claude/settings.local.json` de Dorita — Ivan debe rotar/purgar.

**Commits de esta sesión (en este repo):**
- `210e488` — docs: reescribir CLAUDE.md como manual operativo real del sistema en produccion
- `06d36fa` — config(cierre): la bitacora de sesion se escribe en docs/sesiones, no en Obsidian

**En otros repos:** Dorita `d5dd4d5` + `5f60049` · NEO `1917967` + `e08c0cf` · Genesis `149e3dd` + `918a457`.

---

## 2026-07-07 — Sesión 30: auditoría de skills + skills globales nuevos

- **Ivan:** "Sos mi analista de sistemas de IA. Estudiá cómo uso Claude, auditá cada skill y workflow (keep/fix/merge/delete), reescribí mis workflows repetidos como skills reutilizables, capturá mis estándares para un modelo más barato. Preguntame antes de borrar. Para agent kit, fenix, cowork y agente neo."
- **Fenix:** 5 auditores Explore en paralelo (4 proyectos + skills globales + 168 sesiones de historial). Hallazgos: dualidad skills/commands con wrappers triviales, `/pagina` huérfano, cifras viejas en Dorita, `banner-design`/`slides` redundantes con `design`, `ui-ux-pro-max` roto (scripts de 0 bytes). El mayor dolor sin skill del historial: renovar token Meta (~53 sesiones), "seguimos/pendientes" (~110), operaciones Airtable (~81).
- **Fenix:** Creados 4 skills globales (agente-ops, renovar-token-meta, airtable-seguro, pendientes) + `estandares-trabajo.md` enganchado al CLAUDE.md global con `@`. `/masivo` en FENIX. Fixes en los 4 repos.
- **Ivan:** Aprobó los 3 borrados (build-agent x2, banner-design+slides, recortar ui-ux-pro-max).
- **Fenix:** Borrados ejecutados. `ui-ux-pro-max` recortado 659→379 líneas conservando los 99 lineamientos UX.
- **Ivan:** "Vamos con todo" (los pendientes recomendados).
- **Fenix:** agente-ops unificado con punteros en NEO/Genesis, `/pendientes`, export automático en el hook SessionStart de FENIX. Descubierto y corregido: el refactor `94f6865` movió `all_phones.txt` a `data/` pero el script apuntaba a la raíz → export estaba roto. Regenerado desde Airtable (1178) y probado end-to-end.
- **Ivan:** "commit, hay otras sesiones corriendo."
- **Fenix:** Commits por path explícito en los 4 repos, sin tocar `mundo-fenix/` ni `juego_endpoints.py` de las otras sesiones. Sin push (la sesión paralela ya los subió).

**Commits de esta sesión (en este repo):**
- `b7c3b1e` — feat(skills): /masivo con pre-flight + /pagina invocable + router actualizado
- `c4c337f` — feat(export): export diario automatico de conversaciones al iniciar sesion
- `5baa19b` — docs: skills nuevos en la tabla de flujo de trabajo del CLAUDE.md

**En otros repos:** Dorita `7680342` · NEO `ab3521a` · Genesis `b71fa58`.

**Skills globales creados (fuera de git, en `~/.claude/`):** agente-ops, renovar-token-meta, airtable-seguro, pendientes, docs/estandares-trabajo.md.

## 2026-07-08

Sesión de auditoría de Mundo Fenix + mejoras a la TV de recibimiento. El agente de leads/pagos no se tocó (solo el router `/juego/*` aislado y el frontend en el repo propio `mundo-fenix-app`).

- **Ivan:** "hacemos una auditoría completa del proyecto mundo fenix, decime todo lo que podemos hacer para mejorar y dejame bien detallado los pendientes."
- **Fenix:** Auditoría completa (PLAN-MAESTRO, 3 SPECs, `juego_endpoints.py`, frontend, Functions R2). 11 hallazgos priorizados. Críticos: **H1** el oro por llegada nunca se acreditaba (kepi/remera imposibles de ganar), **H2** la plata de vueltas NFC no llega al ledger Airtable. + huecos de anti-abuso (H3-H5) y deuda menor. Pendientes ordenados en software (A1-A11) / bloqueos de Ivan / hardware / fases grandes.

- **Ivan:** "dale vamos con eso" (arrancar por A1).
- **Fenix:** `/pre-cambio` → `_acreditar_oro_llegada` (+10 oro, gate diario 1×/día en `ESTADO JSON` compartido facial↔NFC, best-effort) en `checkin-face` y `totem-nfc`. `/pre-deploy` → commit `62775f4`, deploy Railway SUCCESS, endpoints verificados en prod (401/422/200 correctos).

- **Ivan:** "vamos a armar un check in de prueba, me cargo mi foto y hacemos todo el proceso." (después: "poneme como nombre alan!")
- **Fenix:** `/airtable-seguro` → creado registro NIÑOS FENIX `recLwzdHkFbHSysge` (IVAN TEST, después renombrado ALAN). Foto de Ivan subida a Airtable + indexada en Rekognition (FACE_ID `8a9ca8c9`, collection pasó de 36 a 37 caras).

- **Ivan (varias):** reportes sobre la TV — "no tiene audio", "siguen esos botones", "que navegador uso en la TV", "porque piratas del fenix", "quiero el LOGO flotando", "no carga nada", "toco OK y no pasa nada".
- **Fenix:** Cadena de fixes a `index.html`/`totem.html` (repo `mundo-fenix-app`): idle = logo Fenix flotando (fuera "Piratas del Fenix" y el párrafo largo); botones Demo/Salir borrados del HTML; `_headers` no-cache (adiós pelea con caché de Fully); pantalla de arranque "Tocá para despertar" que desbloquea audio y acepta el OK del control (keydown); fix `ReferenceError` (resize() antes de definir `cv` dejaba la TV en blanco — diagnosticado con Edge headless screenshot); video del saludo conectado y optimizado (4.4MB→590KB, 30fps).

- **Ivan:** check-in disparado con su foto → reconoció ALAN 100%, ORO=10 en Airtable. Después: "no hubo sonido!" → falta el gesto de desbloqueo.
- **Fenix:** Verificado en Airtable: GUARDIAN ALAN ORO=10 + fila MOVIMIENTOS "Asistencia — llegada a La Casona" + gate diario marcado (2ª llegada = oro 0, no duplica). A1 cerrado end-to-end.

- **Ivan:** "la moneda tiene que tener el logo de fenix... son 10 monedas, se ven de a una, van al celular del padre (la billetera), con sonido de monedas."
- **Fenix:** Explicado: las animaciones se programan (CSS/JS), no se generan aparte — más liviano y fluido que un video. Prototipo aparte mostrado a Ivan → aprobado. Integrado a la escena de llegada: primero el Fenix saluda, después las 10 monedas (logo escudo) vuelan de a una a la "Billetera de {niño}", saldo 0→10, cling por moneda + cha-ching final (WebAudio). Video optimizado. Deployado.

- **Ivan:** "bien aprobado."

**Commits de esta sesión:**
- Repo agente: `62775f4` — feat(juego): +10 oro por llegada — facial y NFC, gate diario cross-canal
- Repo `mundo-fenix-app` (frontend, deployado a Cloudflare Pages): `3e7907c`, `1f72605`, `efa8850`, `4fff5c4`, `60680af`, `a19bcc7`, `8d363ff`, `5b546e6`

**Pendiente inmediato:** A2 — conectar la plata de las vueltas NFC al ledger Airtable (hueco H2). Registro de prueba ALAN quedó en NIÑOS FENIX con la cara de Ivan indexada (decidir si borrar).

---

## 2026-07-11 — TV "Guardianes de Hoy" + 3 fixes de producción del juego

**Ivan:** "cargar selfie no funciona, pongo selfie de un niño, me encuentra dos y cuando selecciono 1 o 2 me pasa la lista de reservas."
**Fenix:** Bug reproducido. El atajo numérico del menú secre (`"1"`→"resumen reservas") corría ANTES del handler de selección de candidatos. Fix en `main.py`: `_admin_espera_respuesta` — el atajo se salta cuando hay `_cara_candidatos`/`_asistencia_pendiente`/`_inscripcion_pendiente`. Quedó mezclado en el commit `82d196c` de una sesión paralela.

**Ivan:** "misma cosa!!" (seguía fallando tras el fix)
**Fenix:** Diagnóstico con logs de Railway: el reintento cayó en medio de una tormenta de deploys (mi push + los de la sesión paralela reiniciaron el proceso). La lista de candidatos vive en memoria del proceso → el restart la borró. No era el fix; era timing. Se pidió reintentar sin deploys en curso.

**Ivan:** "quiero en otra TV la lista de los niños del día: cuántas vueltas, cuántas monedas ganaron hoy y cuántas tienen en total, con logo Fenix, nombre y avatar."
**Fenix:** Nuevo `GET /juego/dia` (público, CORS) que cruza GUARDIANES + MOVIMIENTOS BRASAS + `juego_vueltas`. Frontend `mundo-fenix/lista.html` (`/lista`) con estética de brasas, avatar del guardián, auto-reload kiosk. Deploy a Pages.

**Ivan:** "que la lista sea con el apellido" + "se ven solo 6, se tienen que ver todos."
**Fenix:** Apellido cruzado desde NIÑOS FENIX por NINO ID (GUARDIANES no lo guarda). Layout rehecho: grid que reparte el alto + columnas automáticas (1/2/3/4 según cantidad) → entran todos sin scroll. Las dos Fiorella ahora se distinguen (Perinetto / González Aguero).

**Ivan:** "cuando subo un selfie con dos nombres y dos apellidos no lo agarra."
**Fenix:** Causa raíz: no era "dos nombres/apellidos" sino acentos. La búsqueda multi-palabra usaba las palabras crudas contra `FIND` (sensible a acentos) → apellido con tilde no matchea sin tilde. Fix en `fotos.py`: cada palabra matchea por OR de sus variantes de acento. Probado contra Airtable real.

**Ivan:** "de nuevo no carga el video en la TV, tarda, dura un segundo, carga el mp4 desde cero."
**Fenix:** El archivo estaba perfecto (5s, faststart OK). Causa: Pages sirve todo con `Cache-Control: max-age=0, must-revalidate` → la TV re-baja el video en cada reproducción. Fix: `mundo-fenix/_headers` cachea `/assets/*` 30 días (HTML sin cache para no romper el auto-reload). Verificado el header en prod.

**Commits de esta sesión (repo agente):**
- `82d196c` — fix: menú secre pisaba selecciones pendientes (mezclado con log WABA de sesión paralela)
- `e7502b9` — feat(juego): GET /juego/dia — resumen del día para la TV lista
- `e59f2c0` — feat(juego): /juego/dia incluye apellido (cruzado desde NIÑOS FENIX)
- `556f15e` — fix(fotos): selfie tolera acentos en nombres de varias palabras
- Memorias: `78818cc`, `9e03975`, `69754be`
- Frontend (Pages, `mundo-fenix/` untracked): `lista.html` nuevo + `_headers` nuevo

**Pendiente inmediato:** posible duplicado en NIÑOS FENIX ("Thiago Gomez" aparece dos veces) — revisar si es real y limpiar.

## 2026-07-11/12 — El sábado del Espejo: avatar + vueltas por cara + presentación en TV (probado con niños reales)

**Ivan:** Los chicos llegan hoy y ninguno tiene avatar. Cuando el Espejo los reconozca y no tengan avatar, que la tablet les ofrezca elegirlo, y al elegir que las monedas queden en su billetera.
**Fenix:** Backend: `checkin-face` devuelve el guardián (robot+billetera) + nuevo `POST /juego/elegir-robot` (commit `3667dfb`). Tótem: selector de 10 Guardianes. De paso cayó un bug: el backend nunca mandaba el robot y TODOS se fusionaban con Mamba.

**Ivan:** Los NFC llegan en 10-15 días. Mientras tanto: si ya se escaneó hoy, que la tablet pregunte "¿completaste una vuelta?" con SÍ/NO (yo superviso) y cada SÍ pague monedas.
**Fenix:** `POST /juego/vuelta-face` (+100 🥈, bonus 5ª/10ª, anti doble-tap 120s) + panel SÍ/NO en el tótem (commit `8082615`). Probado en prod con Mateo y revertido.

**Ivan:** Cuando el niño llega que marque la asistencia. Y quiero el comando "selfie Nombre Apellido" como en Dorita para registrar caras.
**Fenix:** La asistencia ya estaba implementada… pero descubrimos después que NUNCA funcionó (ver abajo). El flujo de registro de caras ya existía completo (`registrar cara`); solo se agregó el alias `selfie` (commit `1ace6ab`).

**Ivan:** La tablet con Chrome; ¿la TV con Fully Kiosk o Chrome?
**Fenix:** TV con Fully Kiosk (Autoplay Audio ON — la voz de George suena sin gesto); tablet con Chrome (Web Speech para el "Hola Fenix").

**Ivan:** Quiero que el reposo de la TV sea el mapa a pantalla completa, y cuando hay evento aparezca el Fenix.
**Fenix:** `mapa.html` como iframe-capa-idle dentro de la TV (singleton + fade). Después pidió el mapa PELADO: sin header, ticker, tótem, etiquetas de estaciones ni avatares flotantes (todo oculto por CSS, reversible).

**Ivan:** Probé como AlanTest y no me ofreció el avatar.
**Fenix:** No era el código: la tablet corría el totem VIEJO (cero POSTs a los endpoints nuevos en logs). Fix de raíz: auto-reload kiosk — tablet y TV hashean su HTML cada 10 min (Pages no manda ETag) y recargan solo en reposo; la TV salta la portada tras auto-reload y vigila index+mapa.

**Ivan:** Elegí el avatar y me cargó el dinero en la tablet — eso tiene que pasar EN LA TV: elijo, me vuelvo a espejar, y ahí aparece en la TV.
**Fenix:** `presentar_avatar` en ESTADO JSON al elegir; el próximo escaneo lo consume → evento llegada para la TV (celebra con monedas) + la tablet solo fusiona y manda a la pantalla grande (commit `c9d4163`).

**Ivan:** Reseteá mi test para probar de cero. (3 veces)
**Fenix:** `scripts/reset_alan_test.py` (commit `8f31122`). Al resetear cayó otro bug: **la asistencia FACE nunca se creó** — el select MÉTODO solo tenía "QR" → 422 silencioso desde el 08/07. Opción FACE creada via typecast; confirmado con asistencias reales después.

**Ivan:** ¿Por qué a Fiorella no le dio las monedas? Dice 0.
**Fenix:** **Dos Fiorellas**: el "¿ya llegó hoy?" comparaba por nombre de PILA en eventos → González quedó como repetida de Perinetto. Fix `d673c70`: repetido = gate `ult_oro_llegada` del guardián del NIÑO. Datos reparados (+10, movimiento, asistencia).

**Ivan:** ¿Qué pasa con las reservas? En tutores marca "Lead", sin nombre. ¿Es porque no se registraron los datos del papá?
**Fenix:** Confirmado con datos: 3 tutores "Lead" (`flujo_pagos.py:68` cae a "Lead" si el extractor no encuentra el nombre — y falló con "Carmen Vergara mamá", "Mamá: Rosa..."). Los nombres SÍ están en los chats: Carmen Vergara (familia sin niños ni reservas), Leticia Méndez (falta Valentina Buey), Rosa Marciana Duarte. Quedó esperando OK para cargar (pendiente 263) + rediseño del extractor (264: preguntar el nombre, no más regex).

**Commits de la sesión:** `3667dfb` avatar desde el tótem · `8082615` vueltas por cara · `1ace6ab` alias selfie · `c9d4163` presentación TV · `d673c70` fix dos Fiorellas · `8f31122` script reset · `92cdaf6`/`dc2dfb2`/`7e9cd5e` docs errores-aprendidos. Frontend: ~8 deploys a `mundo-fenix.pages.dev` (no-git).

## 2026-07-12 — Confirmación proactiva del sábado + QR solo para leads

**Ivan:** Eliminemos toda la reserva de familias por QR. El QR queda solo para leads. Y para las familias, los jueves 9am Aurora les escribe con plantilla preguntando si el hijo viene el sábado — botón Sí, botón No.
**Fenix:** Mapeé el flujo real primero: el "QR de familia" no era una reserva, era check-in de asistencia; la reserva de familias se hacía por chat con `gestionar_reserva`. Aclaramos: la reserva por chat SE MANTIENE (fallback), lo que se saca es el QR del lado familia (ahora check-in facial). Diseño en 3 fases + la plantilla.

**Ivan:** El copy: "Hola nombre! Te escribo para saber si este sábado viene nombre a entrenar. ¿Confirmás asistencia?" Turno lo preguntamos después. Solo familias con pago al día. La plantilla de utility se aprueba en minutos.
**Fenix:** Creé `confirmacion_sabado_fenix` (UTILITY, es_AR, botones Sí/No). Ojo: el skill `/plantilla` decía WABA compartido + token Dorita — falso. Verifiqué que el token de FENIX administra su WABA propio `896276490105251` y creé la plantilla ahí. APPROVED en minutos. Corregí el skill (`d2b3b33`).

**Fenix (Fase 1):** Saqué el botón "QR familia" de `alumno_menu` y el QR post-reserva cuando el agente es Aurora (main.py); leads intactos.
**Fenix (Fase 2):** `agent/confirmacion_sabado.py` — handler del Sí/No (estado en flag DB `esperando_confirmacion_sabado`): Sí → pregunta turno con botones 11:00/15:30 → agenda; No → no reserva. Fecha del sábado calculada en Python.
**Fenix (Fase 3):** loop jueves 9AM en `loops.py` + `obtener_familias_para_confirmacion` (filtra AL DÍA=✅ en Python). Probado en lectura real: 10 familias al día, arma bien nombre+hijos. **Loop APAGADO por default** (`CONFIRMACION_SABADO_ACTIVA`).

**Ivan:** Vamos, ojo que hay otra sesión corriendo.
**Fenix:** Diagnostiqué git antes de tocar: la otra sesión ya había arrastrado mi función `obtener_familias_para_confirmacion` a su commit `e503147` (working tree compartido). Commiteé por nombre explícito (nunca `-a`), verifiqué integridad (compila, sin duplicados) y pushié mis 2 commits limpios. Deploy SUCCESS, log `[CONF-SAB] Próximo envío jueves en 101.7h (2026-07-16 09:00 PY)`.

**Ivan:** Actualizá el skill / guardá la memoria.
**Fenix:** Skill `/plantilla` corregido (WABA propio + token FENIX + molde posicional con botones). Memorias: `feedback_dos_sesiones_git` y `project_confirmacion_sabado`.

**Commits de la sesión:** `d2b3b33` fix skill plantilla (WABA propio) · `ca1ceb3` feat confirmación sábado + QR solo leads. (La parte Airtable `obtener_familias_para_confirmacion` quedó en `e503147`, commit de la sesión paralela.)

---

## 2026-07-12 — Bug de topics en Telegram + reserva por formulario Meta (sesión "TV Guardianes", continuación)

**Ivan:** "se está abriendo un tema en Telegram por cada familia que escribe, analizá qué se espeja por grupo."
**Fenix:** Mapeé los 4 grupos (LEADS="FENIX KIDS RESERVAS", FLIAS="☀️FLIAS FENIX", "THE GUARDIAN" monitor, "ALERTAS FENIX" notificaciones). Primero afirmé "un topic por teléfono" leyendo el comentario del código — Ivan me corrigió con datos reales (un número abría 5 temas).

**Ivan:** "mentira, el número 595982778542 abrió 5 temas, no puedo creer que no lo veas."
**Fenix:** Fui a los DATOS (asyncpg contra la DB de prod). Causa raíz: `obtener_o_crear_topic` crea un topic nuevo cada vez que el grupo destino ≠ el guardado; había dos fuentes de verdad del grupo (flujo usa `agent_actual`, pero followups de `loops.py` + QR de `main.py` forzaban LEADS). 15 de 25 familias desalineadas. Fix `022b655` + `ea1cdab` (todos usan `grupo_telegram_para`). Realineé las 13 familias a FLIAS por script.

**Ivan:** "analizá el flujo de reserva de 595981900294."
**Fenix:** `/endpoint` — Mel Antonella. La reserva se materializó (pago 100k + RESERVA + QR + niño con cara), PERO la mamá preguntó 2 veces por el horario y el bot no aclaró; y los datos del padre (CI/email/tel) nunca llegaron a FAMILIA/NIÑO, solo a PRUEBA.

**Ivan:** "ahora la reserva se pide con formulario de Meta: niño (nombre/apellido/fecha) + padre y madre (nombre/apellido/fecha/CI/email/tel), padre y madre opcionales. Reusar el que ya existe, teléfono en el form, después del pago antes de las fechas."
**Fenix:** Plan aprobado (plan mode). Implementado: `agent/formulario_reserva.py` nuevo (envía el Flow `fenix_cargar_nino` y ACTUALIZA FAMILIA/NIÑO/TUTORES a prueba sin duplicar), `flujo_pagos.py` (post-pago manda el form + flag `esperando_formulario_reserva`, fallback a agenda), `main.py` (rama nfm_reply para leads), `prompts.yaml` FASE 4/5 (ya no pide datos por texto). Deploys `6ced372` (código) + `f84b3f7` (prompt), ambos SUCCESS. Falta probar end-to-end en WhatsApp real.

**Commits de esta tanda:** `022b655` fix followups grupo real · `ea1cdab` fix QR grupo real · `1320dcb` memoria rebote topics · `6ced372` feat formulario reserva · `f84b3f7` config prompt FASE 4/5.

---

## 2026-07-12 — Migración final: eliminar PRUEBA FENIX (FASE 0 + 1 + 2.B)

**Ivan:** "la tabla pruebas fenix ya se puede eliminar vd? ya hicimos toda la migración, no afecta en nada?"
**Fenix:** NO — con evidencia dura: la tabla se leyó en prod ayer mismo (logs Railway), está referenciada en 9 archivos (>80 usos) y se sigue CREANDO en el flujo vivo (`crear_prueba_fenix` en formulario/agenda/promo). Lo que migramos (M1) fue solo el pago. El corte de la tabla nunca se hizo.

**Ivan:** "en todo el proyecto ya no debería haber nada haciendo referencia a esa tabla."
**Fenix:** Tampoco es así, lo probé: leída en prod el 11/07 18:12, se sigue escribiendo en cada agenda de prueba. Es la columna vertebral del flujo de leads. Es un proyecto de migración en sí, no un borrado.

**Ivan:** "armemos el plan para terminar ya esa migración y eliminar esta tabla."
**Fenix:** Plan mode. Lancé 3 agentes Explore (docs+modelo nuevo / escrituras / lecturas) + 1 Plan. Perfilé los datos reales (75 regs, 0 pruebas futuras, campos de RESERVAS/HORARIOS/ASISTENCIA). Descubrí un **bug activo de doble conteo** (RESERVAS dual-write + PRUEBA sumados). Plan por fases 0→2.D aprobado. Decisiones de Ivan: histórico con backup + tabla LEGACY 30 días; comando `resumen prueba` eliminado (no reconstruir).

**Ivan:** "seguimos" (x varias) + "hace b5, b6 y b7 sin pedirme permiso de nada."
**Fenix:** Ejecuté domingo (sin clases, riesgo bajo) 11 pushes incrementales, cada uno compilando + deploy SUCCESS + verificado en seco contra datos reales:
- FASE 0 (`e503147`): lookup ESTADO PLAN en RESERVAS (Metadata API) + `es_prueba` + backup.
- FASE 1 (`aae04e4` + dentro de `d2b3b33`): cerré los 2 gaps de dual-write.
- FASE 2.B (`f0c2bd2`→`a85b786`): B1 contexto Aurora (fix doble conteo) · B2 resúmenes reservas/flias/telegram · B3 asistencia interactiva · B4 resumen asis + retiro de "resumen prueba" (−243 líneas) · B5 web pública · B6 QR por reserva + asistencia en /checkin · B7 señal reagendamiento OR familia+reservas.
Resultado: PRUEBA ya no es fuente de lectura de nada. Decisión técnica propia: el guard del formulario NO se voltea hasta C2 (voltearlo hoy cortaría PRUEBA antes de migrar "cargar familia") — documentado en código y memoria.

**Commits de la sesión (migración):** `e503147` Push 0 · `aae04e4` Push 1.1 · `7ec5810` memoria stage-atómico · `f0c2bd2` B1 · `bc09c3b` B2 · `36d2742` B3 · `3052039` B4 · `fbbc7d0` B5 · `88186aa` B6 · `a85b786` B7. (Push 1.2 viajó dentro de `d2b3b33` de la sesión paralela.)
