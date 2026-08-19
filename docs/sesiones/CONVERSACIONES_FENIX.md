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

---

## 2026-07-12 (tarde) — pendiente 263 + control de género + diseño Sábado v2

**Ivan:** "seguimos que tenemos pendiente" → "arreglamos el 3, Rosa Duarte ya arregle yo"
**Fenix:** Pendiente 263 (familias con tutor "Lead"). Verifiqué cada dato contra las conversaciones reales de prod (`/conversacion/{tel}`) antes de tocar Airtable. **Carmen Vergara** (595971318506): tutor renombrado (Mamá, CI 4616111-2) + creado **Santiago Guayuan** (HOMBRE, 2021-09-14). **Leticia Méndez** (595973652111): tutor renombrado (Mamá) + creada **Valentina Buey** (MUJER, 2022-10-27) + **Abigail Buey** completada (ya existía a medias — la memoria decía "falta Valentina" pero Airtable ya tenía Abigail; mirar antes de crear evitó duplicar). Los dos tutores estaban como "Papá" siendo mamás → corregido. Rosa la cargó Iván.

**Ivan:** "necesitamos el campo genero en niño... asi el saludo dice campeon o campeona... haceme un control de que todos los padres tengan el sexo correcto y los niños tb"
**Fenix:** El campo ya existe (SEXO, HOMBRE/MUJER). Control de los 105 niños + 110 tutores con `scratchpad/control_sexo.py` (API + heurístico de nombres). Corregidos: **Hannah Rojas**→MUJER, **Milagros López**→MUJER, **Nayila Duarte**→Mamá. Resto sano.

**Ivan:** (sobre el saludo campeón/campeona) → derivó en rediseñar la mecánica del sábado: 7 vueltas, caja mágica a las 10, cómo se vence al dragón, abrir/cerrar el entrenamiento, insignia con aprobación por WhatsApp.
**Fenix:** Verifiqué que el saludo son MP3 pregrabados por niño ("campeón" hardcodeado). Al reescribir los guiones con Iván quedaron NEUTROS (adiós campeón/héroe). Marqué el choque con la decisión del 05/07 (capas por disciplina, no por vueltas) → se resolvió: las vueltas DESBLOQUEAN el desafío, la insignia la da superar el desafío. Documenté todo en `PLAN-MAESTRO.md` §11 (Mecánica del Sábado v2). Decisiones: abrir/cerrar por comando WhatsApp; insignia genérica con SÍ post-cierre (Iván primero eligió automática y se retractó "error mío"). **Nada codeado — solo diseño.** Verifiqué que la base ya existe (`vuelta-face`/`juego_vueltas`, `/juego/dia`, `dragon-vencido`, patrón admin).

**Ivan:** "hay algo pendiente?" → luego "/cierre"
**Fenix:** Listé pendientes (formulario reserva end-to-end, confirmación sábado apagada, migración PRUEBA esperando el 18/07, implementar Sábado v2). Cierre.

**Sin commits de código** (solo datos Airtable + docs). Cambios versionados: `PLAN-MAESTRO.md` §11, `FENIX_RESUMEN.md`, este archivo.

---

## 2026-07-12/13 — Auditoría completa del proyecto + 21 fixes en producción

**Ivan:** "yo creo que esta tabla de familias al final fue al pedo y complicó todo... el niño fénix es el que paga la cuota... ¿vos qué pensás?"
**Fenix:** Coincidí con evidencia: FAMILIAS es una entidad artificial (el apellido no identifica — dos familias con el mismo apellido; las monoparentales rompen PADRE/MADRE) y el código ya camina hacia ahí (el "EJE B" de `airtable_client.py` ya busca por CELL de TUTORES y lee nombres del rollup). Pero el `familia_id` está en 285 lugares de 17 archivos: es una migración por fases, no un cambio de esquema de un día.

**Ivan:** "Estoy completando ahora en otra sesión la migración para eliminar la tabla prueba fénix... primero termino esa migración y después te hago hacer un análisis."
**Fenix:** Correcto — dos migraciones en paralelo sobre el mismo Airtable es justo lo que quema. Decisión registrada en memoria (`project_migracion_familias.md`), nada iniciado.

**Ivan:** "hacemos una auditoría completa de todo el proyecto, todos los bugs que encontrás... teniendo en mente que queremos hacer esa migración a solo niños Fénix"
**Fenix:** 6 agentes en paralelo (núcleo / datos / dinero / IA-conversación / background / Mundo Fenix) + verificación local (tests, import) + logs de Railway. **~70 hallazgos con archivo:línea**, consolidados en `docs/estado/AUDITORIA-2026-07-12.md`. Reconcilié contradicciones entre agentes (`registro.py` es código muerto; `_get_records` SÍ pagina — el bug es el tope `max_records`). Cinco críticos: PII de menores en endpoints públicos, dedup que descarta mensajes, `meta.py` ciego a errores de red, sin rate limit saliente, `max_records=100` truncando YA (105 niños).

**Ivan:** "si vamos con ctodo" → "si vamos con todo" → "seguimos"
**Fenix:** Ejecuté el plan F0→F4 con deploy incremental (un push por cambio, deploy verificado antes del siguiente). **21 pushes en fenix + 1 en pagos-bancard**, todos SUCCESS.
- **F0 seguridad:** auth en `/api/*` (verificado 401/200 en prod), token HMAC en el QR de `/checkin/prueba`, `/checkin/{id}` deja de mutar en GET, `/juego/dia` solo inicial del apellido, fix dedup (`IntegrityError`), `meta.py` con manejo de red + split >4096 (test de envío real OK), `max_records` 100→1000 (`/api/alumnos` pasó de 100 a **105 alumnos**).
- **F2 dinero:** guard anti-dup en inscripción, dedup de tarjeta fuera de la purga 24h, **firma del link cubre el teléfono** (cross-repo: `pagos-bancard` usa rama `master`; 5 combinaciones verificadas contra la pasarela real), montos viejos de `/agenda` retirados, **rescate del lead pagado que no completa el formulario** (aprobado por Iván: +2h re-Flow, +24h agenda por texto, recordatorios en Postgres con clamp nocturno), aviso de segundo comprobante.
- **F4 calidad:** **el prompt cache no funcionaba** — además de la hora invalidando el bloque, medí que el prefijo (~4350 tokens) queda **bajo el mínimo real de Haiku**: no escribía cache. Fix: system en 2 bloques + breakpoint en el mensaje del usuario. Verificado con la API (w6783 → r6783). **Tests revividos** (importaban Nixie eliminado; pytest ni recolectaba) → 30 pasan. **Telegram de raíz**: el grupo registrado del topic gana sobre el override → muere el rebote en ~8 call sites. Reagendar crea-antes-de-borrar. Año dinámico. CAPI `event_id`. Monitor (conf. sábado vigilada, radar 6h). 3 bugs medianos (`_hoy_cls`, "resumen asistencia", bloque duplicado).

**Pendiente consciente:** A10 (keywords que fuerzan `tool_choice`) y C4 (limiter saliente + promo masiva) NO se tocaron: el primero cambia comportamiento conversacional con leads (necesita `/pre-cambio` con simulación), el segundo es un diseño. A8/A15 mueren solos con la migración FAMILIAS.

**Commits (23):** `322f5e8` auth /api · `00a44e4` dedup · `dc9ec67` max_records · `6a1979c` montos /agenda · `0cf6db5` meta.py red+split · `0c56586` checkin token+POST · `968c336` /juego/dia · `2cf7836` guard inscripción · `a2b1f1a` dedup tarjeta · `406e4d0` 2º comprobante · `eaa9eb1` doc auditoría · `a3adffa` rescate post-pago · `eb58b43` firma teléfono (+ `4f5017f` en pagos-bancard) · `f038898` docs · `6e507ef` prompt cache · `f9f00ad` tests · `15e1f7b` telegram raíz · `5c87824` 3 bugs admin · `bba52d5` reagendar · `0ed7298` año dinámico · `51e38d5` CAPI event_id · `010a995` monitor · `1d352a0` docs.

---

## 2026-07-13 (madrugada) — cache en los 4 agentes + arranca la migración FAMILIAS→NIÑO

**Ivan:** "quiero que veas si dorita, neo y genesis el cache esta bien implementado"
**Fenix:** Los tres revisados **con llamadas reales a la API**, no leyendo código. **Dorita SANO** (escribe y lee ~7.084 tokens; prompt grande, bloque estable — no se tocó). **NEO tenía el cache MUERTO**: mismo bug doble que FENIX (la hora `%H:%M` dentro del bloque cacheado + prefijo de solo ~2.2k tokens, bajo el mínimo → la API ignora el `cache_control` **en silencio**). Arreglado igual que FENIX (system en 2 bloques + breakpoint en el mensaje); medido: **cachea a partir de ~30 mensajes de historial** y NEO manda hasta 50 → las conversaciones largas ahora cachean. **Genesis: diseño correcto** (2 bloques, fecha afuera) pero su system son ~540 tokens y no llega al mínimo: `r0/w0` es lo esperado, cachea solo si el prompt del cliente crece. A los **4** se les agregó el log `cache r/w`. Commits: NEO `42213b8` (**master**), Dorita `f6b26af`, Genesis `ea6f67f` — 3 deploys SUCCESS.

**Ivan:** "las familias me eran muy útiles sobre todo para la familia que vienen con más de un hijo porque de esa manera el pago va bajo familia... ¿hay forma de simplificar eso?"
**Fenix:** Miré los datos antes de opinar: **31% de las familias tienen 2-3 hijos** (24 de 77) y el precio **no es lineal** (240k/1 · 340k/2 · 440k/3 — el segundo hermano suma 100k, no 240k). O sea: el precio es **familiar por construcción**; partir un pago de 340k por niño obligaría a inventar un reparto artificial (170k+170k) que no existe. Propuesta: **el pago NO se parte** — se carga UNA vez y su campo de niños apunta a los 2-3 hermanos (los links de Airtable ya son multi-registro). El estado "al día" vive en el niño (rollup de sus pagos), y quién pagó va en un link a TUTORES (que es lo que la factura necesita). Casos que hoy son imposibles y se resuelven solos: 2 hijos pero solo uno entrena · hermanos con planes distintos · padres separados que pagan cada uno lo suyo.

**Ivan:** "perfecto, entonces simplemente en un pago se cargan dos o tres niños" → "¿ya me creaste los campos?" → "y obvio! sino para que sirve la migracion??"
**Fenix:** No los había creado (solo registrado la decisión). **M1+M2 ejecutados** (`16e2f46`), aditivos y sin tocar nada viejo:
- **Campos creados** (Metadata API con el token de Dorita): `PAGOS.NIÑOS FENIX` (link múltiple), `PAGOS.PAGA` (→TUTORES), `NIÑOS.PADRE`, `NIÑOS.MADRE`, `NIÑOS.VENCE EL` (rollup MAX), `NIÑOS.AL DÍA?` (fórmula); inversos en TUTORES renombrados a HIJOS (COMO PADRE)/(COMO MADRE).
- **Backfill** (`scripts/backfill_ninos_tutores_pagos.py`, dry-run primero): 102/105 niños con padre y/o madre · 62 pagos linkeados · **15 pagos cubren 2-3 hermanos con UN registro** (ej. un pago de 700k cubre a Mauro y Bruno Niz Paredes → los dos ✅ AL DÍA solos).
- **Verificado**: el `AL DÍA?` del niño coincide con el de su familia en los **103 comparables, 0 discrepancias**. FAMILIA / FAMILIA FENIX intactos, el agente en prod sigue igual.
- **Dato sucio**: hay pagos de familias de FENIX con `FUENTE='SALSA SOUL STUDIO'` (FAMILIA Molinas Silva) — el primer filtro los dejó afuera y esos 2 chicos quedaban sin VENCE EL. El criterio correcto es **tener FAMILIA FENIX**, NO la FUENTE.

**Falta solo el paso 3** (migrar el CÓDIGO a los campos nuevos) — espera al 18/07 porque toca los mismos archivos que la migración PRUEBA.

**Commits:** `16e2f46` M1+M2 migración · (otros repos: NEO `42213b8`, Dorita `f6b26af`, Genesis `ea6f67f`).

---

## 2026-07-13 (madrugada 3) — Migración FAMILIAS niño-eje entera + PRUEBA FENIX archivada

**Iván:** Vamos con la codificación de la migración.
**Fénix:** Leí las memorias, lancé 3 agentes exploradores (router/contexto, dinero, juego+docs) y armé el paso 3 en fases. Iván levantó la espera al 18/07: "quiero la migración completa ahora". Ejecuté el **núcleo (C0-C6)**: campo `NIÑOS.ESTADO` + backfill, pagos dual-write `NIÑOS FENIX`+`PAGA`, guards por unión, confirmación sábado por `NIÑOS.AL DÍA?`, reservas del contexto por links del niño (mató bug A8), router `es_cliente_activo_por_telefono`. 6 deploys verificados uno por uno.

**Iván:** ¿Ya se puede eliminar Familia y Prueba? (no lo voy a hacer, pero ¿ya se podría?)
**Fénix:** No todavía — le mostré exactamente qué las sigue enchufando: FAMILIAS aún se escribe (rompería el pago de leads), PRUEBA tiene histórico no copiado (40 PRESENTE, 11 caras). Le pedí decidir el orden.

**Iván:** Decime el paso a paso para llegar a eso.
**Fénix:** Le di el roadmap por tabla (PRUEBA: 2.C→2.D; FAMILIAS: F2→F7). Ejecuté **F2+F3**: `/api/*`, resúmenes, broadcasts, contexto Aurora y menú inscripto (`obtener_grupo_familiar`), nombre del topic — todo niño-eje. 5 deploys.

**Iván:** ¿Qué queda pendiente? / Vamos con todo, simulá el sábado 18 y arrancá.
**Fénix:** Simulé el sábado 18 en seco (4 flujos + /api de prod: todo cuadra), borré la reserva duplicada de Fiorella 11/07, y ejecuté **2.C completa** (C1→C6, cortar TODAS las escrituras a PRUEBA; "cargar familia" ahora matchea sobre FAMILIAS A PRUEBA+NIÑOS). Cacé un bug latente: `buscar_reservas_familia` con `FIND(record_id)` sobre link **nunca matcheaba** (verificado con 2 reservas). 6 deploys.

**Iván:** ¿Diferencia entre código por niño o tutor? → **por tutor.**
**Fénix:** Le expliqué las dos opciones (por tutor = UX intacta, links ya repartidos sobreviven). Eligió tutor. Ejecuté **F5**: juego con `TUTORES.CODIGO`, hijos por links del tutor. 0 códigos repartidos → sin backfill. Verificado con el tutor de Iván (código 43E8EW).

**Iván:** Lo del robot de facturas: no es externo, lo hiciste vos también, arreglalo.
**Fénix:** Cierto — es `Projects\facturador-set` (corre en la PC de Iván). Ejecuté **F6**: datos fiscales en `TUTORES.FACTURA`, factura linkea `TUTOR`, robot lee lookup `TUTOR RUC` (commit `ccb5089` en su repo, con fallback legacy). Backfill 3 datos + 1 factura. Loop de envío del PDF contacta por tutor.

**Iván:** No entiendo qué falta en Prueba y Familia. ¿Simplemente que yo elimine? → Solucioná todo eso, PRUEBA copiá todo, FAMILIA terminá el trabajo.
**Fénix:** Ejecuté **2.D**: backup JSON (75+8 → `backups/2026-07-13/`), rescaté el histórico (`scripts/migrar_historico_prueba.py`: 34 reservas con PRESENTE + 11 caras re-indexadas en Rekognition, idempotente), borré **−419 líneas** de código legacy, y **renombré la tabla a "PRUEBA FENIX LEGACY"** (canario ~30 días). "Resumen anuncios" migró a PAGOS. Después **F7.a**: PAGOS y FACTURAS ya no linkean FAMILIA FENIX. Le expliqué que F7.b (las altas todavía crean FAMILIAS) es un refactor de ~10 piezas que dejo mapeado para la próxima — tocarlo al final de 20 deploys es como se rompen producciones.

**Commits (23 en fenix, C0→F7.a):** `f943b71` C0 · `1ead97a` C1 · `711e796` C2 · `1322e51` C3 · `c90fcec` C4 · `0b9a3e2` C5 · `758fb8c` C6 · `c655a4c` docs · `64839e5` F2.a · `426d7f8` F2.b · `ec1a2e0` F2.c · `258fab0` F3 · `87cd6f1` F3.b · `203d180` 2.C-C1 · `7541d69` C5 · `5eddd05` C2 · `9ac7e50` C3 · `1388b0c` C4 · `82bf6c3` C6 · `0d2f5e5` F5 · `4838cda` F6 · `69c3589` 2.D backfill · `4c061b0` 2.D limpieza · `7ab5097` F7.a. **Robot facturador:** `ccb5089` (master). **Airtable:** tabla renombrada a PRUEBA FENIX LEGACY.

---

## 2026-07-14 — F7.b: el corte de altas de FAMILIAS + limpieza de datos

**Iván:** seguimos con esto (F7.b — el último tramo: las altas todavía crean FAMILIAS).
**Fénix:** Leí el worklist punto por punto de la memoria y corrí `/pre-cambio`. Ejecuté F7.b entero en **10 deploys niño-eje incrementales** (`c3b3741`→`506d30a`), cada uno SUCCESS + prod 200 + logs limpios antes del siguiente: (a) `crear_o_actualizar_tutor` idempotente por CELL LIMPIO+PARENTESCO; (b) `crear_nino` con links PADRE/MADRE+ESTADO; (c) agenda/formulario por grupo familiar + es_prueba por NIÑO.ESTADO; **(c3) el CORTE** — `crear_grupo_a_prueba` reemplaza `crear_familia_a_prueba`, lead por campo nuevo `LEADS.TUTOR FENIX`; (d) inscripción niño-eje; (e) candidatos desde NIÑOS A PRUEBA; (f) registro/cargar niño/modoalumno/reset por tutor; (g) borrados los endpoints de check-in por familia; (i) RESERVAS/ASISTENCIA sueltan FAMILIAS. De paso maté 3 bugs viejos (cancelar reservas y guard-dup por FIND-sobre-link, patch a FAMILIAS.PLAN inexistente).

**Iván (decisión):** el PLAN, ¿dónde queda al cortar FAMILIAS? → **Campo PLAN en NIÑOS**.
**Fénix:** Creé el campo `NIÑOS.PLAN` (select, 4 opciones) por Metadata API con el token de Dorita. La inscripción lo escribe por niño — soporta hermanos con planes distintos, que era justo lo que el modelo niño-eje quería resolver.

**Fénix (decisión propia):** la columna `tutor_id` en la DB **NO la creé** — al terminar el refactor tenía cero consumidores (el tutor se resuelve por CELL LIMPIO, el id se cachea en `estado_json`), y la regla del plan era "columna DB solo cuando algo la lea".

**Iván:** seguimos.
**Fénix:** Verifiqué que prod pasó la noche limpio y audité las fichas incompletas que bloqueaban F7.c. Hallazgos: **Martina Martinez** era una alumna real huérfana de links (la familia tenía su reserva) → la linkeé a Hector/Jessica; las **dos "FAMILIA Britez" NO eran duplicadas** (Johanna y Antonia Iliada, familias distintas — la "fuga" era el FIND por nombre ya muerto); quedaban 5 familias muertas (0 niños/pagos/reservas) + 9 tutores sin hijos.

**Iván (decisión):** borrar todo (las 5 familias muertas + los tutores).
**Fénix:** Backup local en `backups/2026-07-14/`, borré 9 tutores + 5 familias (conservé tu tutor con el CODIGO 43E8EW del juego). Estado final: 101 tutores, 1 solo sin hijos (vos, admin), 1 niño huérfano (ALAN TEST). Los datos ya no bloquean F7.c.

**Nota:** F7.b quedó sin probar en vivo (ningún lead pagó). Pendiente probar el alta niño-eje end-to-end con número de test + "cargar familia". F7.c código (sacar fallbacks → LEGACY → borrar) queda para después del sábado 18 — los fallbacks son la red de seguridad hasta que un sábado real valide todo.

**Commits (11 en fenix, F7.b-a→i):** `c3b3741` (a) · `87fc53d` (b) · `b022474` (c1) · `5314090` (c2) · `fc4a9db` (c3, el corte) · `38e0ef8` (e) · `cecb90e` (d) · `d5a2e6a` (f1) · `819883e` (f2) · `467cf3b` (g) · `506d30a` (i). **Airtable:** campos nuevos `LEADS.TUTOR FENIX` (`fldOaYMkJdtihJrj2`) y `NIÑOS.PLAN` (`fldNyWFtzD0NO48HC`); borradas 5 familias + 9 tutores muertos.

---

## 2026-07-24/25 — Primera estación NFC física armada + fix de plata + piloto de mañana

**Ivan:** cuántos días asistieron amira y eladio? (consulta rápida sobre 2 niños puntuales)
**Fenix:** Consulté Airtable — 1 día cada uno (la clase de prueba del 16/5), 0 asistencias registradas después. Estado "A PRUEBA — VENCIDO".

**Ivan:** [mandó fotos de un cable Mini-USB] este sirve?
**Fenix:** No — es Mini-USB (conector viejo), el ESP32 usa Micro-USB o USB-C. Cuando Ivan insistió que el ESP32 pedía Mini-USB, reconocí el error sin evidencia visual del puerto real y pedí confirmación en vez de sostener la afirmación sin verla.

**Ivan:** esta conectado el esp32! (pidió verificar)
**Fenix:** `arduino-cli` no estaba en el PATH ni el driver CP2102 instalado (Device Manager: error 28). Instalé el driver por `pnputil` elevado (con OK explícito de Ivan por el UAC), quedó en COM3, verificado con `board list`.

**Ivan:** tengo que soldar los 8 pines o solo los dos extremos / vos me estás jodiendo, no me consultaste nada
**Fenix:** El RC522 vino con agujeros pelados sin header (normal en estos kits, no fue un invento mío) — expliqué por qué hacen falta los 8 puntos de soldadura (cada uno es una señal SPI distinta) y guié paso a paso: cautín, estaño 63/37, header recto, técnica de soldado. Primera soldadura de Ivan, salió bien (verificado con `VersionReg = 0x92`).

**Ivan:** [cableado RC522↔ESP32, luego WiFi no conectaba] pero es mini usb lo que pide este esp32! / no es micro
**Fenix:** El WiFi fallaba con `NO_AP_FOUND` constante. Agregué `escanear_redes()` al sketch para ver los SSIDs reales — encontré la causa: la red se llama `LA CASONA LAFUENTE _EXT` **con un espacio** antes de "_EXT", invisible a simple vista. Usamos la red base sin extensor. Conectó.

**Ivan:** hacemos un niño de prueba y le cargamos este llavero
**Fenix:** Usé `/juego/nfc-vincular` (sin `nino_id`, a propósito — no ensucia Airtable con un niño falso). Probé el circuito completo: UID → POST → `estaciones_completadas`. Anduvo.

**Ivan:** quiero armar la vuelta con una sola estación — pase por quincho, vuelva al Fénix, complete la vuelta
**Fenix:** Cambié `JUEGO_ESTACIONES` en Railway a solo `quincho` (con OK explícito, + restart). Para el tótem, en vez de armar hardware nuevo con un segundo ESP32-U (sin antena, no conectaba a WiFi), propuse reusar el check-in facial que ya existe: lo extendí para que evalúe el circuito en cada escaneo y cierre la vuelta sola.

**Ivan:** y no se podría hacer que cuando llega al tótem al leer el rostro se vaya a mirar si completó y le otorgue la vuelta
**Fenix:** Exacto lo que hice — pero de paso encontré un bug real preexistente: el cierre de vuelta por NFC nunca acreditaba la plata real a la billetera (`_acreditar`), solo animaba la TV. Lo arreglé en los dos caminos (NFC y facial) y actualicé `totem.html` para avisar "vuelta completada" o "te falta pasar por X".

**Ivan:** [frustración repetida con jumpers/cables finos para el anillo LED, "una mierda", "no tiene sentido esta forma definitiva"]
**Fenix:** Reconocí que el jumper-hack para un cable tan fino no era forma definitiva de nada — la solución real es soldar el cable a un pin suelto (no al ESP32 en sí), y ofrecí parar ahí varias veces dado lo tarde que era. Ivan decidió seguir; terminamos soldando y el anillo WS2811 quedó andando — prende verde apenas lee el UID, ANTES de que conecte el WiFi (confirmado en el log).

**Ivan:** /cierre
**Fenix:** Cierre de sesión.

**Commits de la sesión:**
- `b51f9c7` — feat(firmware): estación NFC quincho — RC522+ESP32, WiFi + POST real
- `5732953` — fix(juego): acreditar plata real al cerrar vuelta + circuito en check-in facial
- `80765df` — feat(mundo-fenix): tótem avisa vuelta completada o estación faltante
- `1faf741` — feat(firmware): anillo WS2811 en quincho — feedback local instantáneo

**Cambios de infraestructura (no-código):** driver CP2102 instalado en esta PC · `JUEGO_ESTACIONES=quincho` en Railway (temporal, revertir cuando estén las otras estaciones) · niño de prueba "FENIX"/guardián mamba vinculado a UID `8BD8DF00` en Postgres (sin tocar Airtable).

---

## 2026-07-25 — Piloto en vivo: vincular pulseras reales + gestión de muñequeras

**Ivan:** ¿Cómo se vinculan las pulseras?
**Fenix:** Expliqué el flujo de `/profe.html`: Chrome Android + NFC prendido, elegir al niño, botón "Vincular pulsera NFC", apoyar la muñequera atrás del teléfono.

**Ivan:** [en un Huawei] me dice web nfc no disponible cargá el uid a mano / son los botones que compré por Aliexpress y no tengo otro celular
**Fenix:** Sospeché que el Huawei sin Google Play no tenía Chrome real y sugerí probar en la tablet del tótem (ya confirmada con Chrome genuino + NFC).

**Ivan:** pero creo que ya está funcionando, proba a mirar si está conectado un botón NFC a Alan
**Fenix:** Instalé `psycopg2` al vuelo y consulté la tabla `pulseras` de Postgres directo (vía `DATABASE_PUBLIC_URL` del servicio Postgres en Railway) — confirmé que el UID del botón SÍ había quedado vinculado a Alan, con timestamp de recién. El Web NFC del Huawei funcionaba después de todo; lo que pasaba era que el diálogo nativo de Android ("Wallet o Etiquetas") tapaba el cartel de confirmación antes de que Ivan lo viera.

**Ivan:** debería haber un check o ícono junto al nombre para saber que se vinculó
**Fenix:** Agregué el check ✅ junto al nombre en la lista de `/profe.html` (`9df6358`) — ya no depende de ver el toast a tiempo, queda visible en la lista.

**Ivan:** ¿y qué pasa cuando termina el entrenamiento, cómo se desvincula?
**Fenix:** No existía esa función — la agregué: `POST /juego/nfc-desvincular` + botón por niño (`f225e03`).

**Ivan:** debería haber un botón para desvincular a todos
**Fenix:** Agregado `POST /juego/nfc-desvincular-todas` + botón con confirmación, para resetear el pool completo de muñequeras de una sola vez al terminar (`c2ec37d`).

**Ivan:** /cierre
**Fenix:** Cierre de sesión.

**Commits de la sesión:**
- `9df6358` — feat(juego): check visible junto al nombre cuando ya tiene pulsera vinculada
- `f225e03` — feat(juego): endpoint y botón para desvincular una pulsera NFC
- `c2ec37d` — feat(juego): botón para desvincular TODAS las pulseras al terminar el entrenamiento

---

## 2026-07-25 — Firmware estación NFC: LED sigue la pulsera + fix de protocolo NFC

**Ivan:** ¿hasta cuántos colores tiene nuestra argolla conectada al ESP32?
**Fenix:** Es un anillo WS2812 COB direccionable (RGB) — millones de colores posibles, el ESP32 controla cada LED individualmente. No es una limitación de "N colores fijos".

**Ivan:** ahora cuando el niño pasa una vez muestra verde, ¿qué pasa si pone la pulsera varias veces en la estación?
**Fenix:** Expliqué el dedupe ya diseñado en `SPEC-NFC-CIRCUITO.md`: el LED prende siempre (feedback local, no depende de la red), pero el backend solo cuenta la PRIMERA pasada por estación dentro de la vuelta abierta.

**Ivan:** el LED se prende una vez y no se prende más — debería prender cada vez que paso
**Fenix:** Leí `firmware/estacion/estacion.ino`: el antirrebote de 2s y que el RC522 no vuelve a "ver" un tag en HALT sin WUPA. Confirmé con Iván que probaba tocando y soltando.

**Ivan:** debería quedarse prendido todo el tiempo que esté apoyado, ahora es muy corto
**Fenix:** Cambié el blink fijo de 400ms por un loop de presencia con `PICC_WakeupA` (a diferencia de REQA, sí despierta un tag en HALT sin sacarlo del campo) — el LED se apaga recién cuando deja de responder. Guie a Iván para compilar/flashear con `arduino-cli` (ya instalado, `C:\Program Files\Arduino CLI\arduino-cli.exe`, no en el PATH de la sesión) — COM3, libs MFRC522/FastLED/ArduinoJson ya instaladas.

**Ivan:** se quedó prendido 10 segundos solo
**Fenix:** El POST a Railway (`enviar_tap`) estaba ANTES del loop de presencia — el HTTPS bloqueante demoraba el apagado del LED aunque ya hubiera sacado la pulsera. Reordené: LED → esperar hasta que la saquen → recién ahí el POST (como ya decía el propio spec: el feedback local nunca debe depender de la red). Reflasheado y confirmado.

**Ivan:** con la caja de madera cerrada dejó de leer (antes leía apoyando sobre la tapa), solo lee si abro la caja y toco el RC522 directo
**Fenix:** Sospecha principal: el anillo LED quedó físicamente encima de la antena (bobina) del RC522, bloqueando el campo. Subí `PCD_SetAntennaGain(RxGain_max)` como mitigación por software (de fábrica arranca en ganancia media) — si no alcanza, hay que reubicar el anillo.

**Ivan:** la moneda (NTAG213) dejó de encender la luz, el llavero (Mifare Classic) sigue andando; si pongo la moneda después no me lee el llavero, y viceversa
**Fenix:** Encontré el bug real en el loop de presencia agregado antes: `HaltA` solo es válido en estado ACTIVE, pero el código lo mandaba justo después de un `WakeupA` exitoso — el tag queda en READY (no seleccionado), y mandarle Halt ahí es comportamiento NO definido por ISO14443. El NTAG213 se cuelga en ese estado y deja de responderle al lector, bloqueando la detección de CUALQUIER tag nuevo. Fix: completar el ciclo `WakeupA → PICC_Select → HaltA`. Compilado y flasheado.

**Ivan:** /cierre

**Commits de la sesión:**
- `86f8f87` — fix(firmware): estación NFC quincho — LED sigue presencia real y corrige bloqueo de lectura cruzada

**Pendiente:** Iván todavía no confirmó si el fix WUPA→Select→Halt resolvió la lectura cruzada moneda/llavero, ni si la ganancia máxima de antena alcanzó para leer con la caja cerrada (ver `docs/FENIX_RESUMEN.md` #286).

---

## 2026-07-25 (continuación) — buzzer instalado + el fix de la mañana se REVIERTE

**Ivan:** ah faltó instalar el módulo de altavoz para el sonido!
**Fenix:** Anotado como pendiente #287 (buzzer nunca instalado ni programado).

**Ivan:** hacemos ahora
**Fenix:** Agregué buzzer HW-508 pasivo en GPIO25 con barrido de frecuencias 1500-4500Hz (para pegarle a la resonancia). Guie el cableado paso a paso (foto del módulo → identifiqué pines S/+/- del HW-508), y cuando el 3.3V y el 5V del ESP32 quedaron ocupados (LED+RC522), guie armar una breadboard para repartir el 5V a los tres consumidores.

**Ivan:** listo, igual se escucha apenas
**Fenix:** Es limitación física del piezo chico del HW-508, no de firmware — aceptado así para el piloto (el LED sigue siendo la confirmación visual principal). Marcado #287 como hecho.

**Ivan:** de nuevo el mismo problema si yo pongo el botón después no quiere leer el llavero
**Fenix:** El fix de la mañana (WUPA→Select→Halt) NO alcanzó — se reprodujo el mismo bloqueo. Armé un script `pyserial` (el `arduino-cli monitor` de este harness no capturaba nada) para ver el log en vivo mientras Iván probaba.

**Ivan:** [varias pruebas guiadas, alternando "listo" con reportes de que seguía sin leer]
**Fenix:** La captura de serial confirmó: tras un tap exitoso, el log quedaba MUDO 50+ segundos — el RC522 dejaba de responder a CUALQUIER tag nuevo, sin ningún error visible. El mecanismo WUPA/Select/Halt (aunque protocolarmente correcto por ISO14443) resultó frágil con este hardware/librería — decidí abandonarlo por confiabilidad.

**Ivan:** si coloco uno después el otro no lee!!!!
**Fenix:** Revertí el LED a duración FIJA (1.5s) en vez de tratar de seguir el retiro real de la pulsera — sin el loop de Wakeup/Select que colgaba el lector. Compilado, flasheado y confirmado con Iván alternando moneda/llavero varias veces sin colgarse.

**Ivan:** perfecto /cierre

**Commits de la sesión:**
- `103ad53` — feat(firmware): agregar buzzer HW-508 a estacion quincho con barrido de frecuencias
- `315e7f4` — fix(firmware): revertir WakeupA/Select a duracion fija — colgaba el lector con tags nuevos

**Aprendizaje clave:** el mecanismo WUPA→Select→Halt en loop para "seguir la presencia real" de un tag NO es confiable en este hardware/librería (MFRC522 + ESP32) — se colgó 2 veces distintas (con NTAG213 Y con Mifare Classic), sin error visible. Registrado en `memory/errores-aprendidos.md` — NO reintentar ese enfoque sin resolver antes por qué se cuelga a bajo nivel.

---

## 2026-07-27 — el formulario de reserva perdía TODOS los datos del padre (bug real, fix completo)

**Ivan:** `/endpoint 555981941407` — "este número el sábado pagó, completó formulario, pero en la tabla pagos no aparece. y tampoco puedo ver los datos del formulario así que no sé quién es el niño"
**Fenix:** El teléfono tenía un typo (555 en vez de 595). Con el correcto: leí `/debug` y `/conversacion` de prod, después Airtable (LEADS/PAGOS/TUTORES/NIÑOS FENIX vía MCP) — el pago SÍ existía pero sin `NIÑOS FENIX`/`PAGA` linkeados (invisible en la vista filtrada); el niño sí se había creado pero, dije yo primero, "sin pasar por el formulario" — conclusión que resultó INCOMPLETA.

**Ivan:** "en telegram yo tengo 'formulario de reserva completado' — ¿por qué decís que no completó?"
**Fenix:** Corregido con evidencia: grepeé el código y confirmé que ESE mensaje sí implica que `procesar_formulario_reserva` corrió. Faltaba explicar por qué entonces no había datos.

**Ivan:** "¿y dónde están los datos del formulario? aparte se creó el niño y el padre — ¿por qué no están vinculados?"
**Fenix:** Fui a los logs de Railway (GraphQL directo a `backboard.railway.app`, filtrando por teléfono/`RESERVA-FORM`/`formulario`) y until encontré la secuencia exacta: el `[formulario]` SÍ llegó, pero `procesar_formulario_reserva` logueó `WARNING no encontré grupo a prueba — no completo datos` y descartó TODO el `flow_data` ahí mismo (nunca se guardó en DB, ni Airtable, ni ningún log con contenido). 5 minutos después, el detector legacy de texto recreó el niño con el nombre ADIVINADO del chat — por eso el niño "sí estaba" pero sin los datos reales del papá.

**Ivan:** "qué mierda de forma de trabajar es esta... la primera cosa que vamos a hacer ahora: cuando llegue 'formulario completado', mandame TODOS los datos a Telegram y WhatsApp"
**Fenix:** Corrí `/pre-cambio`, propuse el plan (espejo completo + persistencia en DB + procesar siempre sin depender del flag).

**Ivan:** "primero tenemos que arreglar la creación del niño, no tiene sentido ese agujero"
**Fenix:** Delegué un análisis profundo a un subagente (Fable, foreground) para no tirar un fix a ciegas sobre `main.py`/`pagos.py`. Devolvió la causa raíz completa (el sistema trata el dato adivinado como el eje y el dato real como decoración opcional) + un plan de 2 commits con riesgos identificados (interlock `prueba_creada` para desarmar el detector legacy, no pisar el CELL del tutor del WhatsApp, no duplicar niños con 2+ hermanos).

**Ivan:** "me estás pasando 10.000 cosas... lo único que tiene que hacer el sistema es crear al niño después del formulario. no sé por qué me haces tanto quilombo"
**Fenix:** Reduje al mínimo necesario y lo implementé directo: `procesar_formulario_reserva` ahora CREA el niño con los datos reales si no existe (reutilizando el tutor parcial sin duplicar), espeja TODO a Telegram+WhatsApp admin antes de tocar Airtable, guarda el `flow_data` crudo en DB siempre, y setea `prueba_creada=True` para desarmar el detector legacy. `import agent.main` OK + pytest 30/30 + prueba manual de `_resumen_formulario`. Commit `7541b7e`.

**Ivan:** "¿y cómo se cargan los datos del pago, si normalmente paga primero y completa el formulario después?"
**Fenix:** Agregué el back-fill: al procesar el formulario (que ya crea/completa al niño), se buscan los PAGOs `PRUEBA` del lead sin `NIÑOS FENIX` y se les cuelga el link — cierra el caso típico (paga → formulario después) sin tocar `registrar_pago_fenix`. Commit `1a8216d`.

**Ivan:** "PUSH" → luego "SI" (para el segundo commit)
**Fenix:** Pusheados uno por uno, cada uno verificado contra prod (`/debug/{tel}` responde normal) antes de seguir con el siguiente.

**Commits de la sesión:**
- `7541b7e` — fix(reserva): el formulario CREA al niño si no existe y sus datos se reportan siempre
- `1a8216d` — fix(reserva): back-fill del PAGO huérfano al completar el formulario

**Aprendizaje clave:** cuando un dato llega de una fuente verificada (formulario, comprobante) y el registro donde encaja todavía no existe, la respuesta es CREARLO, nunca descartar el dato. Todo webhook externo se persiste crudo en DB antes de cualquier lógica de negocio. Registrado en `memory/errores-aprendidos.md`.

**Pendiente:** los datos reales de Blas Páez (595981941407) — CI, fecha de nacimiento, mamá — se perdieron por el bug ANTES del fix y no son recuperables del sistema; pedírselos de nuevo por WhatsApp (#291). El detector legacy de texto sigue vivo como fallback si el papá nunca completa el formulario — evaluar si conviene desarmarlo del todo (#292).

## 2026-07-27 (sesión 28 — fotos web + caras por familia + R2 + botón)

**Ivan:** ¿de dónde se alimenta fenixkidsacademy.com/catalogo/?
**Fenix:** Detectado: `catalogo.json` estático en el repo web (216 videos, 19/05). De paso encontró la carpeta "perdida" de videos originales en `Downloads\FENIX KIDS ACADEMY\FENIX VIDEOS SAB 16-5-26` (9,2GB).

**Ivan:** quiero una sección de fotos de los entrenamientos en la web.
**Fenix:** Página `/fotos/` con grid por fecha + lightbox, `scripts/optimizar_fotos.py` (incremental por manifest, thumb+full, EXIF). Se publicaron 293 y luego 71 más (total tras limpiezas: 630). Se borraron 3 fotos ajenas (12/03) a pedido de Iván.

**Ivan:** quiero poder borrar fotos yo solo, y carpetas por fecha también en mi Escritorio.
**Fenix:** `fotos/admin.html` (tildar → genera comando de `borrar_fotos.py`) + `organizar_fotos_por_fecha.py` (fotos y videos por metadata, `--simular`, `--destino`, duplicados exactos auto-eliminados). Los 191 videos del Escritorio quedaron en carpetas por día.

**Ivan:** menú por fecha en la web + usar nuestro reconocimiento facial para filtrar por niño.
**Fenix:** Menú de fechas público (ok). Filtro por niño NO público (contradecía su propio commit de seguridad 1d7bb55): links privados por familia reusando el código mágico de TUTORES. Fix crítico de `_buscar_multiples_caras` (recorte real con Pillow — antes fotos grupales devolvían 1 niño), tablas + `GET /juego/fotos/{codigo}` + `familia.html` + batch `taggear_fotos_web.py`. Aplicado: 1062 tags/630 fotos/24 niños. Probado con su código (118 fotos de "Ivan TEST" linkeado como hijo de prueba).

**Ivan:** un comando /fotosfenix… o mejor un botón python en mi Desktop.
**Fenix:** `publicar_fotos.py` (pipeline entero: ordenar → publicar → taggear → WhatsApp) + acceso directo "FOTOS FENIX" con logo .ico + skill `/fotosfenix` que delega en el mismo script. Iván lo estrenó solo con 269 fotos y funcionó (menos el WhatsApp: faltaba `ADMIN_API_KEY` en `.env` local — arreglado y verificado).

**Ivan:** ¿cómo movemos a R2? (el repo engordó y un build de Pages se colgó)
**Fenix:** Bucket `fenix-fotos` + `cdn.fenixkidsacademy.com`, 1260 imágenes migradas por API REST (primer intento con wrangler fue a storage local por falta de `--remote`), páginas y endpoint apuntando al CDN, imágenes fuera de git, pipeline y borrado actualizados. Todo verificado en vivo.

**Ivan:** el rollout a familias cuando tengamos más rostros.
**Fenix:** Anotado: 70 niños sin FACE_ID. Antes del rollout: juntar FOTO en Airtable → `indexar_caras.py` → re-taggear (`--todas` no hace falta: basta borrar de `fotos_web_procesadas` o esperar fotos nuevas... correcto es re-correr tras indexar).

Commits agent: `54f0612` fix recorte caras · `80a30b2` tablas+endpoint fotos · `ed45cef`+`bc8745e` script batch · `6f5522e` guard+skill · `1a822f9` base_url CDN.
Commits web: `a04f16a` catálogo 293 · `99b43c7` quitar 3 · `33ebab9` admin · `9fdea27` +71 · `1ebff0d` videos · `8ea82f0` filtro fecha · `adf039a` familia.html · `11a2c3c` dups · `9540ad6` pipeline · `3e78a40` bat+ico · `b0c30a8` +269 (corrió Iván) · `ec31d91` CDN · `bda3216` fotos fuera de git.

## 2026-07-28 (sesión 29, continuación corta — fotos de WhatsApp sin fecha real)

**Ivan:** subí fotos que me pasaron por WhatsApp a la carpeta FOTOS — ¿van a tener fecha de hoy? No hay forma de recuperar la fecha real, son todas de días distintos.
**Fenix:** Confirmado con `extraer_fecha`: 17/28 sin EXIF, 11/28 con fecha de reenvío (no la real) — WhatsApp comprime y borra/reescribe el EXIF. Se agregó `fecha_foto()` en `optimizar_fotos.py`: la carpeta contenedora (`YYYY-MM-DD Día`) manda sobre el EXIF; recalculada en cada corrida, así que mover una foto ya publicada a la carpeta correcta la corrige sola después. Publicadas las 28 (658 total), taggeadas (76 tags nuevos), verificado en vivo. Sugerido a Iván: pedir que le manden las fotos "como Documento" para conservar el EXIF real.

Commit web: `17b896c` fecha_foto() + 28 fotos.

## 2026-07-28 (sesión 30, madrugada — el PACK de 5 clases: precio nuevo, saldo por niño y aviso al padre)

**Ivan:** cambiamos el precio: no va a ser 2.40 mensual, va a ser 3.50 y le vale por 5 sábados que NO vencen. Cambiar en la web, en el flujo de WhatsApp y el afiche. Y mandame ahora por WhatsApp los afiches que estamos usando (precios y horarios).
**Fenix:** Afiches enviados a su WhatsApp por `/test-envio` (como link: el endpoint solo manda texto). Mapeados los lugares vivos del precio: aparecieron **7**, no los 4 que decía la memoria — los 2 fallbacks de `main.py` y `reminders.py` salieron por grep. Memoria de precios corregida.

**Ivan:** el costo por hermano es 150mil + y le incluye 5 clases que no vencen, + 100 matrícula anual.
**Fenix:** Confirmado el esquema con 3 preguntas (prueba sigue igual · matrícula por cada niño · nombre "Pack 5 clases"). Tabla final: prueba 100/150/200 · pack 350/500/650 · matrícula 100k por niño.

**Ivan:** [manda un afiche nuevo hecho con ChatGPT] esta imagen para la web y WhatsApp.
**Fenix:** Verificado contra el esquema (dice 350.000, +150.000 por hijo extra, 5 SÁBADOS, ejemplos 350/500/650) → copiado a `static/afiche_fenix.png` y convertido a JPG para la web. Precio actualizado en los 7 lugares + la web, con los links de pago **refirmados** (la `sig` es HMAC del monto; sin refirmar quedaban rotos). Deploys separados: código primero, prompt después.

**Ivan:** tenemos que trabajar en el control: cada vez que el niño viene, el papá tiene que recibir un mensaje de que su hijo ingresó y cuántos sábados le quedan. Crear una plantilla para eso.
**Fenix:** Diseño con 3 decisiones suyas — **las familias del mensual viejo siguen aparte**, aviso en cada visita, al número de la conversación. Campos `CLASES DISPONIBLES` + `ULTIMO DESCUENTO` en NIÑOS FENIX; `descontar_clase()`/`recargar_pack()` como única puerta (patrón `_acreditar`); enganchado en los 3 check-ins con gate diario. Probado contra Airtable con 7 casos y el registro restaurado.

**Ivan:** cuando el papá paga el pack debería sumarle 5 automáticamente — si tiene 4 y compra otras 5, pasa a tener 9. ¿Cómo hacemos?
**Fenix:** `CONCEPTO=PAQUETE5` (la opción **ya existía** en el select) + `recargar_pack` acumulativo. Bonus: la fórmula `VENCIMIENTO_FORMULA` no contempla PAQUETE5 → el pago queda sin vencimiento, justo lo que necesita un pack que no vence. Parser probado con positivos y negativos.

**Ivan:** [dicta el texto de la plantilla] …y si es el mensual, decirle la fecha que vence. Y una pregunta final con botones: ¿te gustaría que te enviemos las fotos al terminar?
**Fenix:** Plantilla `checkin_fenix` creada en el WABA propio de FENIX → **APROBADA**. Botones "Sí, mandame fotos" / "No, gracias" — con texto distinto de los "Sí/No" de `confirmacion_sabado_fenix` a propósito: la respuesta llega sin id, solo con el texto, y se confundirían.

**Ivan:** cuando dice "sí, mandame las fotos" — ¿hacemos que el Python que sube las fotos también se encargue de enviarle?
**Fenix:** Sí, paso 7 de `publicar_fotos.py` → `POST /fotos/avisar-familias` y el server manda el link (todas las fotos del día, como pidió). Solo recibe quien lo pidió y el pedido se limpia al enviar. El botón del padre abre la ventana de 24h → el aviso sale como mensaje libre, sin plantilla ni costo. Todo **apagado** por `AVISO_CHECKIN_ACTIVO`.

**Ivan:** hacemos un comando /cambioprecio.
**Fenix:** `/cambioprecio` (skill + comando espejo en `.claude/commands/`, que es lo que lo hace invocable — `fotosfenix` no lo tiene y por eso no aparece). 8 pasos: cerrar la tabla de precios con Ivan → `/pre-cambio` (con el aviso de que un monto de otra cantidad de dígitos rompe la regex que lee comprobantes) → los 7 lugares → **el grep del valor viejo** → afiche verificado contra la tabla → web en rama master con los links refirmados → Airtable solo si el plan es nuevo → dos pushes + Done. Corregido también el CLAUDE.md, que decía "4 lugares vivos".

Commits agent: `23580fc` precio en código+afiche · `e7f42e5` precio en prompt · `854347c` saldo de clases · `004d745` +5 al pagar · `1916701` aviso al padre + fotos.
Commits web: `61217aa` precio + afiche + links refirmados · `23b82c3` paso 7 avisar familias.
Cierre: `0e0ca69` docs · `8d04b0e` skill /cambioprecio.

---

## 2026-08-07 — Tutores mudados a ALUMNOS

Aurora no le respondía a Ivan desde su propio número. El webhook crasheaba con
`can only concatenate str (not "list") to str`: el refactor del 03/08 seguía leyendo
`TUTORES FENIX`, pero los padres/madres se habían mudado a la tabla **ALUMNOS**
(`NEGOCIO = FENIX KIDS ACADEMY`) y los campos `HIJOS (COMO PADRE/MADRE)` que quedaron
en TUTORES son **texto**, no links — sumarlos como listas reventaba para los 101 tutores.
El crash ocurría antes de activar el modo padre, así que el silencio del modo secre
tapaba el error: los dos síntomas eran el mismo bug.

Fix en dos deploys incrementales: `95cb067` (identidad tutor → ALUMNOS) y `3fafa06`
(los callers). Verificado en prod: cero errores y `/api/alumnos` devolviendo 88 niños
con madre y 52 con padre, donde antes venía vacío.

Detalle completo → `.claude/handoffs/handoff_20260807_1253.md`

---

## 2026-08-07 (noche) — Basket armada y el RC522 mudo

Segunda estación del circuito NFC (`basket`) armada y verificada end-to-end: Iván soldó el
header del RC522, se cableó lector + buzzer HW-508 y se flasheó `estacion.ino` (mismo binario
que quincho, solo cambia `ESTACION_ID` en `config.h`). Se habilitó `basket` en la variable
`JUEGO_ESTACIONES` de Railway — antes solo tenía `quincho` y por eso todos los taps volvían
422. Verificado con hardware real: `UID 7B45DE00`/`3A90EF55` → `POST /juego/estacion → 200`.

⚠️ Consecuencia a tener presente: con las dos estaciones activas, **una vuelta ahora exige
tocar quincho Y basket**.

El grueso de la sesión se fue en tres trampas de hardware, la última de ~2 horas: **el RC522
se traba mudo** (responde `VersionReg` pero no detecta ningún tag) y **solo se destraba
cortándole la alimentación** — el botón `EN` reinicia el ESP32 pero no le corta la corriente
al lector. Sin cambios en los sketches: se probó una versión con POST asíncrono para acelerar
la fila, rompió la detección y se revirtió entera con `git checkout`.

Detalle completo → `.claude/handoffs/handoff_20260807_2318.md`

---

## 2026-08-08 — Aurora saluda por el número

Iván preguntó por qué el 17/07 Aurora saludó a Ilse Estigarribia con **"¡Hola Raul!"** (su
marido). La causa: cuando el teléfono no identificaba a nadie, el saludo se rellenaba con
"el primer tutor de la lista" — eliminado. Mirándolo apareció algo peor y vivo: tras la
migración a ALUMNOS del mediodía, el WhatsApp de Ilse **no resolvía** (su fila tenía cargado
un teléfono fijo) y Aurora, sin contexto, **le inventó una reserva del sábado 8 que no
existía**.

Control de identidad sobre los 24 números en modo Aurora contra el router real: **7 no
resolvían**, 2 eran familias activas (Ilse y Gaudi). Se corrigió el teléfono de Ilse, se creó
el campo fórmula `TELEFONO2 LIMPIO` y la identidad ahora busca en los dos números — Gaudi
comparte fila con Salsa e Impulso y no se le podía pisar el principal. Commits `3c0a3d7`,
`13ef71e`, `bd7d88a`.

Detalle completo → `.claude/handoffs/handoff_20260808_0040.md`

## 2026-08-09 — Adiós TUTORES FENIX

Auditoría completa post-migraciones con 5 agentes en paralelo (~50 hallazgos verificados
contra el schema real de Airtable): destapó que **el bot no registraba un solo pago desde el
25/07** — los links `PAGA`/`TUTOR FENIX` apuntaban a la tabla legacy y recibían ids de ALUMNOS,
así que Airtable rechazaba el POST entero; los pagos de agosto los había cargado Iván a mano
por la GUI. También que el texto de Aurora creaba y cancelaba reservas por regex. Se arreglaron
los 3 críticos y los 14 altos, y se ejecutó la **Etapa 2 completa** (TUTORES FENIX → ALUMNOS:
código del juego, datos fiscales, robot facturador, tabla renombrada LEGACY con canario de 30 días).

Dos de esos fixes rompieron producción: uno dejó al **agente mudo 8 minutos** por un `import`
dentro de una rama condicional, y lo descubrió Iván probando, no el sistema. De ahí salió una
segunda auditoría —los **caminos de silencio**— con sus 14 hallazgos arreglados: el `except` del
webhook ahora le responde al padre y alerta al admin, el envío se verifica y reintenta, y el
shutdown espera los mensajes en vuelo. Además `tests/test_webhook_no_muda.py`, validado
reintroduciendo el bug del día. 37 commits + 1 en facturador-set, todos deployados y verificados.

Detalle completo → `.claude/handoffs/handoff_20260809_2206.md`

## 2026-08-10 — Nace el Desafío FENIX

Cambio de producto completo en una noche: la clase de prueba de un sábado murió y la puerta de
entrada pasó a ser el **DESAFÍO FENIX**, un campus de viernes a domingo (350.000 reservando hasta
el jueves, 550.000 después, +150.000 por hermano). El primer campus es el 14, 15 y 16 de agosto.

Se tocó todo el circuito: `agent/desafio.py` nuevo (campus, precio por fecha, cupos, 3 reservas
por niño), los textos que pasaron de constantes a funciones porque el precio depende del día, el
prompt de ventas, la elección de turnos post-pago con botones, el `CONCEPTO=DESAFIO`, el afiche,
y la web entera —home reorientada, landing `/desafio` para anuncios y `campus.js` compartido—.
El pago con tarjeta terminó pidiéndose por WhatsApp: el cobro desde la web estaba roto desde el
12/07 por la validación de firma de la pasarela, y encima no inscribía a nadie.

Arrancó por otro lado: el pago de prueba de Iván aparecía sin nombre de alumno. Eran dos bugs
distintos —el PAGO no escribía el link `ALUMNO`, del que cuelgan la fórmula del nombre y el CI, y
el formulario del admin creaba tutor y niño duplicados— más un tercero que apareció solo: la
suite de tests se ponía roja después de las 23:00 por el modo noche.

22 commits (16 en el agente + 6 en la web), todos deployados y verificados en producción.

Detalle completo → `.claude/handoffs/handoff_20260810_0141.md`

## 2026-08-10 (madrugada) — El primer contacto del Desafío

Los 3 trabajos del plan `docs/PROXIMA-SESION-DESAFIO.md`, un push cada uno, los tres
deployados SUCCESS: el que llega del botón "pagar con tarjeta" de la web recibe el link
firmado en vez del saludo de venta (`4f36436`), el primer contacto pasó a contar el campus
con la foto de La Casona y botones `Info y precios · Reservar lugar · Agendar llamada`
(`2d314d3`), y "Info y precios" manda todo de una en mensajes separados (`055d99f`).

"Agendar llamada" quedó sin preguntar la hora, por decisión de Iván: pide el nombre y le
manda un `wa.me` prellenado para contactar al padre de un clic. Primer test de `lead_menu.py`
(79 → 99). De paso aparecieron dos cosas viejas: los dos afiches son el mismo PNG, y
`modo padre` se pierde en cada deploy — eso último hizo ver al agente como muerto un rato.

Detalle completo → `.claude/handoffs/handoff_20260810_0224.md`

## 2026-08-10 (tarde) — El reloj del Desafío

Sesión entera en el repo web (`fenixkidsacademy-web`, rama `master`); el agente no se tocó.
La web ahora muestra en vivo cuánto falta para que cierre la reserva anticipada: el plazo
escrito ("cierra el jueves a las 23:59") y abajo un reloj DÍAS·HORAS·MIN·SEG que corre al
segundo, en el hero y en dos bandas por página. Todo desde `assets/campus.js`, sin fechas
hardcodeadas. Commits `57b9dbe`, `bdf55b9`, `505649b`, `c2d3181`.

El error del día: el deploy estaba bien y la web se veía vieja igual, porque el `<script src>`
iba sin versión y el navegador servía el JS del cache — verificar con un navegador limpio daba
un falso OK. Se arregló con `?v=2`. Iván pidió además que el botón vaya debajo del reloj y que
la fecha del hero dejara de capitalizar el "y" y el "de".

Al cierre, además: el frontend de Mundo Fenix (páginas, los 2 SPECs nuevos, `_headers`,
`_serve.py`, el script de Roblox) entró al repo por primera vez (`f4f3e94`), y los 63 MB de
`mundo-fenix/assets/` —187 voces de George, guardianes, videos— quedaron respaldados en el
bucket R2 `mundo-fenix-assets`, verificados 215/215 por tamaño y md5. Los assets van al
`.gitignore`: se sirven desde Pages y git guardaría cada versión entera de cada binario.

Detalle completo → `.claude/handoffs/handoff_20260810_1329.md`

---

## 2026-08-11 (madrugada) — Gym armada y el RC522 mentiroso

El circuito pasó a **4 estaciones** (`arbol` → `gym`, sale `muelle` porque quedó dentro del
recorrido de gym) y la TV ahora muestra el progreso de la vuelta en curso: `/juego/dia` expone
qué estaciones encendió y cuáles le faltan a cada chico, y `lista.html` lo pinta con un ícono
grande por estación (`46bae62`, `34604c2`, `d4d6409`). Verificado con Chromium sobre 2, 6, 12
y 16 chicos, y en producción por contenido.

**Estación `gym` armada y verificada** — 5 lecturas, 4 tags distintos, uno de ellos un NTAG213
real de 7 bytes. Falta habilitarla en `JUEGO_ESTACIONES` (recién cuando esté montada: con `gym`
activa, una vuelta exige las tres).

El grueso de la sesión se fue en un **RC522 que vino fallado de fábrica**: no leía ni un tag
pero pasaba todos los tests de software. Y el sketch de diagnóstico que escribí para dirimirlo
dio un veredicto **falso** ("chip dañado") porque el autotest interno falla igual en los
módulos buenos — son clones. La regla que queda: el único criterio válido es **¿lee un tag que
ya sabés que funciona?**

También se decidió **no implementar** el doble check-in/check-out por estación que se evaluó
para medir tiempos: duplica los taps, crea estados huérfanos y el servidor ya sella la hora de
cada pasada.

Detalle completo → `.claude/handoffs/handoff_20260811_0129.md`

## 2026-08-12 — fix feriado

El 14 y 15 de agosto son feriado y el campus corre con un turno por día (viernes 17:00,
sábado 11:00; el domingo sin cambio). Entró en el agente y en la web como una tabla
`TURNOS_ESPECIALES` con las fechas explícitas: se apaga sola cuando pasa el finde, así que
no hay nada que revertir. Cubre los botones post-pago, los textos del lead, el aviso de
Aurora y la validación real — Aurora no puede agendar a las 15:30 ese sábado. Antes de
tocar nada se verificó en Airtable que los turnos caídos no tenían ninguna reserva, así
que no salió ningún mensaje: Aurora solo responde si le preguntan.

El hallazgo del día apareció probando las respuestas reales: el agente ofrecía las 19:30
igual, 2 de 2 veces, pese al aviso. Un dato escrito en el prompt le gana a cualquier
corrección del contexto, así que los horarios salieron de `prompts.yaml` y ahora los
inyecta el sistema siempre. Una revisión posterior con Fable cazó 3 bugs más (slots
fantasma de Airtable, el "es feriado" que también salía por cupo lleno, la lista vacía al
reagendar). De yapa, el saludo del primer contacto pasó al copy de la web.
Commits `807e81a`→`bec64a0` + `4c549b2` en la web.

Detalle completo → `.claude/handoffs/handoff_20260812_1330.md`

## 2026-08-12 — la web entra a Google

Iván preguntó cómo hacer para que `fenixkidsacademy.com` aparezca en Google. La respuesta
corta: no aparecía porque nunca se lo enviamos, y porque `robots.txt` y `sitemap.xml` no
existían — pero devolvían HTTP 200, que es la trampa de Cloudflare Pages (sirve el index como
fallback). Se sumaron los dos, más canonical, Open Graph absoluto y un JSON-LD con dirección,
teléfono, edades y los 4 turnos de 90 min. El logo bajó de 2.79 MB a 187 KB. Decisión de Iván:
la home sigue siendo la landing del Desafío — no se reescribe, solo cambia el title.

Search Console, la Redirect Rule de `www` y la ficha de Maps las hizo él con Claude Chrome,
con un prompt armado acá. Dos cosas salieron de eso: el `_redirects` de Pages **no matchea el
host** (la regla nunca se aplicó y el archivo quedaba aparentando funcionar, se borró), y la
ficha de Google publicaba **el número personal de Iván** y la dirección equivocada. De paso se
compactó `MEMORY.md` de 19.7 a 14.0 KB sin borrar ninguna memoria.
Commits `9a53cbf`→`eeb5f60`, todos en `fenixkidsacademy-web`.

Detalle completo → `.claude/handoffs/handoff_20260812_1601.md`

## 2026-08-12 (noche) — Sold out

El primer Desafío se llenó: el campus del 14-16 pasó a SOLD OUT y todo vende ya el del
21-23 a precio anticipado (350k hasta el jueves 20). Una sola palanca — `CAMPUS_AGOTADOS`
por fecha, que `proximo_campus()` saltea — movió sola precio, turnos, botones, textos,
links y el contador de la web; el cartel rojo y la línea de sold out se anuncian hasta el
domingo y mueren solos. Corrección de concepto de Iván sobre la marcha: el feriado NO
tiene entrenamiento regular para nadie (los turnos especiales son sesiones del campus) →
regla `hay_entrenamiento_regular()` en el aviso de Aurora, el pre-hook y las 3 fuentes de
horarios. Fiorella tiene reserva viva el sáb 15: le escribe Iván.
Commits `7cc5151`→`58f0e91` + `f18d456` (web).

Detalle completo → `.claude/handoffs/handoff_20260812_2330.md`

## 2026-08-13 (noche) — Identidad la decide el sistema

`/endpoint 595981683435`: Aurora llamó "Jorge" (el papá) a Jazmin (la mamá de Fio) toda la
conversación y mintió "ya anoté tu nombre ✅" con 0 tools en el log. El dato de Airtable
estaba bien — falló Haiku (el historial viejo pisó al contexto) y GENERO vacío dejaba a los
tutores sin etiqueta MADRE/PADRE. Fix en 4 frentes: saludo determinístico de inscriptos
(template + nombre de Airtable, sin LLM), `registrar_familia` acepta corrección del propio
nombre y completa GENERO, regla "el CONTEXTO manda" en `aurora_prompt`, y los topics de
Telegram se renombran. GENERO cargado en las filas de Jazmin y Jorge. Regla 14 en CLAUDE.md.
De paso quedó resuelto lo de Fiorella: la mamá reagendó el 15→29 (quedan 22 y 29, 11:00).
Commits `0698805`→`79887e3`.

Detalle completo → `.claude/handoffs/handoff_20260814_0116.md`

## 2026-08-14 — Caso Nayila

`/endpoint nayila duarte`: a una alumna regular le vendieron el Desafío con su SOLD OUT, le
dijeron "mañana horario normal" siendo feriado, y le confirmaron que sus 240.000 eran "el
paquete de 5 clases". Una sola causa raíz: el router leads/alumno solo corría dentro de
`if es_nuevo:`, así que la que se inscribió por fuera del bot quedó en modo lead para siempre
— y ese modo define qué prompt y qué contexto recibe Haiku. Fix: re-chequeo throttled de 24h
que promueve a Aurora sin cortar flujos de lead activos. Dos agravantes arreglados aparte: el
`aurora_prompt` tenía la semántica vieja de feriado contradiciendo al aviso del sistema, y
ningún prompt prohibía inventar a qué corresponde un pago. Auditoría en prod: 15 clientes más
congelados; los 16 promovidos, re-corrida en 0. Commits `3849372`→`43f46a1`.

Detalle completo → `.claude/handoffs/handoff_20260814_2057.md`

## 2026-08-17 — El campus pasa a 2 días

El viernes salió de la oferta (tres días eran demasiado para las familias): el Desafío queda
sábado (turno a elegir, 11:00 o 15:30) + domingo 15:30 con merienda en familia incluida para el
niño y los padres. Precios 300.000 anticipada (hasta el viernes 23:59) / 450.000 normal; la venta
cierra el sábado 11:00 y el entrenamiento regular queda solo sábados. `agent/desafio.py` y
`assets/campus.js` se re-anclaron al SÁBADO, la elección de turno post-pago pasó a un solo paso
y son 2 reservas por niño. Afiche nuevo de Iván publicado en las 3 rutas y link de ubicación
apuntando a la ficha propia de Fenix Kids Academy (antes abría la de La Casona, por eso el
preview mostraba una foto grupal). Commits `ea39a7c`→`b02d547` (agente) y `3adefca`→`5aeadee` (web).

Detalle completo → `.claude/handoffs/handoff_20260817_2224.md`

## 2026-08-18 — El menú era una jaula

`/endpoint 595982862766` destapó que el menú de botones se comía las preguntas: el lead tocó
*Info y precios*, leyó todo y preguntó "Hacen todos los meses.?" — le contestaron "Tocá una de
las opciones 👇" y su pregunta murió ahí, sin tope ni salida. El flujo de botones no tenía puerta
hacia el cerebro. Fix con el mismo flag `menu_estado` y un valor más (`menu_libre`): un solo
recordatorio y después `procesar_menu_lead` devuelve `None` para que responda Aurora en ese mismo
mensaje. 5 tests nuevos, validados reintroduciendo el bug. Commit `e3e3500`, deploy SUCCESS.

Antes de eso, Mundo Fenix: se evaluó poner una TV en cada estación del circuito con la foto del
niño. Software casi gratis (el evento `estacion` y el canal `/juego/eventos` ya existen), pero el
costo real es fierro a la intemperie y caras de niños en un endpoint sin auth → primero el test
con un celular viejo en la estación del gym.

Detalle completo → `.claude/handoffs/handoff_20260818_1134.md`

## 2026-08-19 — Cierre de la web

Ivan pidió cerrar fenixkidsacademy.com: solo el logo bien grande y nada más, sin
WhatsApp/IG/YouTube/teléfono. Un commit en `fenixkidsacademy-web` (`e296570`): la home quedó
logo-only sobre fondo crema (se fue también el JSON-LD con teléfono e Instagram), `/desafio`
redirige a `/` (los links de anuncios viejos no dan 404). `/fotos/` y `/catalogo/` intactos
(operativos, sin contactos); el bot no manda links de venta a la web → cero flujos rotos.
Pendiente si el cierre es total: la ficha de Google Business sigue publicando teléfono y horarios.

Detalle completo → `.claude/handoffs/handoff_20260819_1704.md`
