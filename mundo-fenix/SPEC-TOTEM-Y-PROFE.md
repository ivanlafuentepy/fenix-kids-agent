# SPEC — Espejo del Guardián (tótem) + App del Profe + TV conectada
> Escrito el 2026-07-06 (sesión Fable) para ser EJECUTADO POR OPUS en sesiones siguientes.
> Todas las decisiones ya están tomadas — acá no se re-decide, se ejecuta.
> Regla de oro: leer `feedback_checklist_obligatorio` y ejecutar `/pre-cambio` antes de tocar
> código del agente. Deploy incremental SIEMPRE (un cambio → deploy → verificar → siguiente).

---

## 1. Objetivo

El niño llega a La Casona → toca la tablet de la entrada ("Espejo del Guardián") → la cámara
lo reconoce (AWS Rekognition, infra YA existente) → se registra su asistencia (+10 oro) →
la Smart TV lo recibe con su nombre gigante, su robot Guardián, lluvia de monedas y la
**voz de George** (ElevenLabs, ya integrada al prototipo). El profe, desde su celular,
dispara los demás eventos del juego (vuelta, dragón, tesoro) hacia la misma TV.

## 2. Decisiones tomadas (NO re-decidir)

| Decisión | Valor | Motivo |
|---|---|---|
| Backend de eventos | **Railway del agente FKA** (mismo servicio) | face_recognition.py, AWS creds, Airtable client y deploy ya viven ahí |
| Disparo de foto | **El niño TOCA la pantalla** → countdown 3-2-1 → foto | Robustez: foto en el momento justo, cero falsos disparos, el toque es parte del ritual |
| Si no reconoce | **1 reintento → fallback "Pedile al Guardián Mayor"** (profe marca manual en 2 taps) | El niño SIEMPRE recibe su saludo; nunca se va sin magia |
| Hardware tótem | **TCL Tab 11 (9466X) — COMPRADA 06/07** (11" 2000×1200, frontal 8MP, Android 13) | Montar a ~1.10m apenas inclinada hacia abajo + cargador permanente + Fully Kiosk Browser |
| Transporte de eventos | **Polling HTTP cada 2s** (NO WebSocket) | Simplicidad; Railway lo aguanta de sobra para 1 TV + 1 tablet + 2 profes |
| Red | Tablet y TV hablan con el **backend público HTTPS** | La Casona tiene varios wifis que no se ven entre sí (verificado 06/07) — no depender de LAN |
| Privacidad | **Biometría solo con opt-in del padre** | Niño sin opt-in NUNCA pasa por Rekognition → flujo manual del profe. Mismo patrón que opt-in fotos redes |
| Voz | Audios **pre-generados** por alumno con ElevenLabs (George) | Costo ~cero: se genera 1 vez por alumno, la TV solo reproduce MP3s |

## 3. Arquitectura

```
TABLET (Espejo)          CELU PROFE              SMART TV (Android TV)
  /totem                   /profe                  /tv (modo TV de la PWA)
    │ toca→foto              │ botones evento         │ polling GET cada 2s
    ▼                        ▼                        ▼
┌────────────────────── RAILWAY (agente FKA) ─────────────────────────┐
│  POST /juego/checkin-face   POST /juego/evento   GET /juego/eventos │
│         │                                                           │
│         ▼                                                           │
│  face_recognition.py (Rekognition, collection fenix-kids)           │
│  → match niño → asistencia +10 oro (Airtable) → evento "llegada"    │
│  Eventos en DB (tabla juego_eventos) — estado persistente SIEMPRE   │
└──────────────────────────────────────────────────────────────────────┘
```

## 4. Componentes a construir

### 4A. Backend — endpoints nuevos en Railway (agente FKA)

Archivo nuevo: `agent/juego_endpoints.py` (router aparte, NO tocar main.py más que para
incluir el router). Env var nueva: `JUEGO_API_KEY` (header `X-JUEGO-KEY` en todos los POST).

| Endpoint | Qué hace |
|---|---|
| `POST /juego/checkin-face` | Body: `{foto_base64}`. → Rekognition `identificar_ninos()` → si match: registra asistencia (+10 oro), crea evento `llegada`, responde `{ok, nino: {nombre, guardian, rango}}`. Si no match: `{ok: false, motivo: "no_reconocido"}`. **Cooldown 5 min por niño** (no duplicar llegadas si toca 5 veces). |
| `POST /juego/evento` | Body: `{tipo: vuelta\|dragon\|tesoro, nino_id, extra}`. Solo profe (misma key). Crea evento. |
| `GET /juego/eventos?since={id}` | Devuelve eventos con id > since (para polling de TV). Sin auth (solo lectura de nombres/eventos, sin datos sensibles). |
| `GET /juego/alumnos` | Lista `{id, nombre}` para el selector manual del profe. Requiere key. |

- **Tabla nueva** `juego_eventos` (SQLAlchemy, mismo patrón de memory.py): id autoincrement,
  tipo, nino_nombre, guardian, payload JSON, timestamp. Estado en DB, no en memoria (regla del proyecto).
- Reusar `face_recognition.identificar_ninos()` — NO reescribir.
- Rate limit el checkin (ej. 10/min por IP) — patrón ya existente en el proyecto.
- **VERIFICAR ANTES (con grep/Airtable, no asumir):** cómo se llama el campo de opt-in de fotos
  en NIÑOS FENIX; cómo se registra asistencia hoy (QR checkin ya existe — `docs/guias/FENIX QR CHECKIN.md`);
  si FACE_ID está poblado (correr `scripts/indexar_caras.py` si hace falta).

### 4B. Tablet — "Espejo del Guardián" (`/totem`)

Página nueva servida por HTTPS (Railway static o ruta del agente — getUserMedia EXIGE HTTPS).
- Idle: cámara frontal en vivo (espejo) + "👆 TOCÁ EL ESPEJO PARA QUE TE RECONOZCA" + branding Fénix.
- Toque → countdown 3-2-1 (grande, con sonido) → captura frame (canvas → JPEG ~0.8, máx 720p) → POST.
- Esperando: "🔥 El Guardián te está mirando…" (spinner). Latencia esperada 1-3s.
- Éxito: "¡HOLA {NOMBRE}!" + robot + verde → (la TV en paralelo hace su escena con voz).
- Fallo 1: "¡Casi! Acomodate y probá de nuevo" → botón reintentar (1 vez).
- Fallo 2: "Pedile al Guardián Mayor que te anote 🧙" → vuelve a idle en 8s.
- Kiosk: **Fully Kiosk Browser** (gratis) apuntando a la URL, pantalla siempre encendida.

### 4C. TV — de localStorage a polling

En `mundo-fenix/index.html` (modo TV ya construido, con voz):
- Agregar polling: `GET /juego/eventos?since={ultimoId}` cada 2s cuando `tvMode` — cada evento
  nuevo → `tvPlay(ev)` (ya existe, ya habla).
- MANTENER el canal localStorage + botón Demo (sirve para demo sin backend).
- **Autoplay**: Android TV bloquea audio sin gesto → al entrar al modo TV ya hay un toque
  (botón TV), verificar que alcance; si no, pantalla "tocá para iniciar" una sola vez.
- Los audios por alumno: `assets/voz/llegada_{nombre}.mp3` etc. — convención YA implementada
  en `tvVoz()`. Generar audios de alumnos reales (ver 4E).

### 4D. Celu del profe (`/profe`)

- PIN simple (env var) → lista de alumnos (GET /juego/alumnos) → tap en alumno → botones:
  ✅ Llegó (manual, para los no-reconocidos) · 🏃 Vuelta · ⚔️ Dragón · 🏴‍☠️ Tesoro.
- Cada tap → POST /juego/evento → la TV lo celebra. Confirmación visual mínima (toast).
- Es una página más de la PWA — misma estética del juego.

### 4E. Voz — audios por alumno (script, no runtime)

- Script `scripts/generar_voces_alumnos.py`: lee alumnos de Airtable → por cada uno genera
  4 MP3 (llegada/vuelta/dragon/tesoro) con ElevenLabs (voz **George**, `JBFqnCBsd6RMkjVDRZzb`,
  model `eleven_multilingual_v2`, settings stability 0.45 / similarity 0.8 / style 0.4).
- Key de ElevenLabs: env var `ELEVENLABS_API_KEY` (plan free: 10k chars/mes — 30 alumnos ×
  4 frases ≈ 18k chars → generar en 2 tandas de 2 meses O pagar $6 un mes y listo).
- Guion por escena (nombre se interpola):
  - llegada: "¡{N} llegó a La Casona! El Guardián Fénix te da la bienvenida, campeón/campeona. Ganaste diez monedas de oro… ¡que comience la aventura!"
  - vuelta: "¡Increíble, {N}! Vuelta completada… el cofre del tesoro está cada vez más cerca. ¡Seguí así, Guardián!"
  - dragon: "¡{N} venció al dragón! La Casona respira tranquila gracias a vos. Ganaste una nueva insignia… ¡sos una leyenda!"
  - tesoro: "¡{N} encontró el cofre del Capitán! Trescientas monedas de plata para el héroe del día. ¡La Casona entera te aplaude!"
- Fallback runtime: si no existe el MP3 del nombre, `tvVoz()` falla silencioso (solo visual). Ya implementado.

## 5. Riesgos ya resueltos (no descubrirlos de nuevo)

1. **getUserMedia exige HTTPS** → el tótem se sirve desde Railway (HTTPS), no file:// ni http://.
2. **Autoplay de audio en Android TV** → requiere un gesto; el botón de entrar a modo TV cuenta como gesto. Verificar en la TV real; plan B: overlay "tocá para iniciar".
3. **Varias redes wifi en La Casona que no se ven entre sí** (verificado 06/07) → TODO pasa por el backend público. Nada LAN-a-LAN.
4. **Rekognition latencia 1-3s** → UX de espera diseñada ("El Guardián te está mirando…").
5. **Niño toca 20 veces** → cooldown 5 min por niño en el backend.
6. **Niño sin opt-in** → no está en la collection → cae a flujo manual. NUNCA indexar sin opt-in.
7. **Costo Rekognition** → $0.001/búsqueda ≈ $0.15/sábado con 30 niños y reintentos. Irrelevante.
8. **El formato de asistencia ya existe** (QR checkin) → el checkin facial REUSA esa lógica, no crea una paralela. Grep primero.

## 6. Orden de ejecución para Opus (cada fase = commit + deploy + verificar)

| Fase | Qué | Verificación antes de seguir |
|---|---|---|
| A | Tabla `juego_eventos` + `GET /juego/eventos` + `POST /juego/evento` | curl local: crear evento → leerlo. Deploy → curl prod. |
| B | `POST /juego/checkin-face` conectado a Rekognition | curl con foto real de un niño indexado → match correcto. Foto de desconocido → no_reconocido. |
| C | TV polling en index.html (manteniendo Demo) | Evento por curl → la TV (en Chrome PC) lo muestra y habla en <3s. |
| D | Página /totem | Probar en PC (localhost cuenta como secure context) → luego en un celu Android via HTTPS prod. |
| E | Página /profe | Marcar llegada manual desde el celu → TV celebra. |
| F | Script voces alumnos + subir MP3s | Reproducir 3 al azar. Verificar nombres con acentos (ñ, tildes → normalizar filename: minúsculas sin tildes). |
| G | Compra tablet + Fully Kiosk + montaje + prueba sábado | Piloto real con 5 niños antes de anunciarlo. |

**Reglas duras:** un cambio por commit · `/pre-cambio` antes de tocar agent/ · `/pre-deploy`
antes de cada push · NO tocar el flujo de Aurora/WhatsApp existente · si algo falla, `/debug`
y buscar causa raíz, no parche.

## 7. Estado al momento de escribir esta spec (2026-07-06)

- ✅ Modo TV visual completo + voz de George integrada (`tvVoz()` en index.html) + 5 audios demo en `mundo-fenix/assets/voz/`
- ✅ ElevenLabs cuenta free activa (key en manos de Iván; va a env var `ELEVENLABS_API_KEY`)
- ✅ face_recognition.py + indexar_caras.py existentes (collection `fenix-kids`)
- ✅ DVR/cámaras F7: pipeline VAR verificado (ver PLAN-MAESTRO 5.3c) — F7 se integra DESPUÉS con este mismo canal de eventos
- ✅ **`mundo-fenix/totem.html` CONSTRUIDO Y PROBADO** (06/07, Chrome PC + cámara real, modo
  demo). Flujo completo: toque → 3-2-1 → captura → reconocimiento simulado → éxito con voz /
  reintento / Guardián Mayor. Para conectarlo al backend real: solo setear `CONFIG.API_URL`
  y `CONFIG.JUEGO_KEY` (primeras líneas del script). La fase D del tótem queda REDUCIDA a eso.
- ✅ Tablet TCL Tab 11 comprada (en camino)
- ⏳ Falta backend de eventos + checkin-face, TV-polling, app del profe (fases A-C, E)
- ⏳ DVR pendiente esta noche: IP fija + usuario dedicado (datos en CLAUDE.local.md)
