# SPEC — Circuito NFC: identidad física, estaciones y vueltas automáticas
> Escrito 2026-07-07 (sesión Fable). Diseño completo para EJECUTAR en sesiones siguientes.
> Se enchufa al canal de eventos YA diseñado en `SPEC-TOTEM-Y-PROFE.md` (mismo backend,
> mismos endpoints). NO crea un sistema paralelo: la pulsera NFC es una FUENTE de eventos más.
> Economía y reglas del juego: `PLAN-MAESTRO.md`. Acá se define el HARDWARE + FIRMWARE +
> los endpoints nuevos que faltan.

---

## 0. Qué resuelve (el problema en una frase)

Hoy las vueltas del circuito **las carga el profe a mano** (PLAN-MAESTRO 3.6). Con NFC, el
niño toca cada estación con su muñequera y **la vuelta se registra sola** — infalsificable
(la dispara el hardware, no el niño) y sin trabajo del profe. Además la muñequera se vuelve
la **identidad física** del niño: la llave que conecta su cuerpo con su Guardián digital.

**Encaja con el principio del proyecto:** "toda la economía la disparan adultos o hardware,
nunca el niño" (PLAN-MAESTRO 3.6 y 6). El NFC ES hardware → la plata por vuelta queda blindada.

---

## 1. Decisiones — tomadas vs abiertas

**TOMADAS (heredadas, no re-decidir):**

| Decisión | Valor | Fuente |
|---|---|---|
| Backend de eventos | Railway del agente FKA (mismo servicio) | SPEC-TOTEM 2 |
| Red | Todo contra backend público HTTPS (los wifis de La Casona no se ven entre sí) | SPEC-TOTEM 2 |
| Auth de eventos | Header `X-JUEGO-KEY` (env `JUEGO_API_KEY`) | SPEC-TOTEM 4A |
| Estado | En DB, nunca en memoria | regla del proyecto |
| Economía por vuelta | 1 vuelta = 100 plata · 5 = +200 · 10 = +500 + caja 🎁 | PLAN-MAESTRO 6 |
| Chip | NTAG213 / ISO14443A / 13.56 MHz | compatibilidad RC522 + PN532 |
| Lector del tótem | PN532 (mejor lectura/distancia) | esta spec |
| Lector de estación | RC522 (barato, alcanza) | esta spec |
| **Cierre de vuelta** | **EN EL TÓTEM** — el niño reclama ante Fénix, no se cierra en la última estación | pedido original de Iván 07/07 ("Fénix corrobora el recorrido") + la celebración ocurre frente a la TV con el niño presente |
| Timestamps | Los pone el SERVIDOR al recibir; la hora del dispositivo solo para cola offline (pasadas rezagadas, ver 4C) | el ESP32 no tiene reloj confiable |
| Auth de estaciones | Una key POR estación (revocable individual) además de `X-JUEGO-KEY` | si roban una cajita no comprometen el sistema |

**ABIERTAS (Iván decide antes de comprar/ejecutar):**

1. **Identidad física: ¿muñequera de tela o botón en la capa?**
   - Recomendación de la spec: **muñequera de tela con botón NFC cosido**. Motivo: la capa
     no la tienen los nuevos ni los del Reto (son los que más querés medir), se olvida en
     casa y se presta entre hermanos. La muñequera la tiene TODO niño desde el día 1, va al
     agua y no se saca. El botón en la capa queda como detalle CEREMONIAL (opcional, fase 2).
2. **Llegada: ¿facial (ya construido) o NFC?**
   - Recomendación: **conviven**. El facial (SPEC-TOTEM) sigue para la llegada con opt-in.
     El NFC se suma como identidad SIEMPRE presente y es lo único nuevo obligatorio para el
     CIRCUITO (vueltas). Si el piloto muestra que la muñequera funciona mejor que la cámara,
     se puede migrar la llegada a NFC después (más barato, sin Rekognition, sin opt-in
     biométrico). No se re-decide ahora: NFC entra por el circuito, no toca el facial.
3. **¿Orden de estaciones fijo o libre?** Recomendación: **libre** (tocá las N que quieras)
   + tiempo mínimo por estación. Una vuelta = tocar TODAS las estaciones del circuito de la
   temporada **y volver al tótem a reclamarla**. Simple de explicar a un niño de 4 años:
   "encendé todos los fuegos y volvé al Fénix".
4. **Cuántas estaciones en el piloto.** Recomendación: **1 estación + tótem** para el
   prototipo de banco, luego **3 estaciones** para el primer sábado real. El pack de 6
   lectores da margen a escalar sin comprar de nuevo.

---

## 2. Identidad física — la muñequera (botón NFC)

- **Botón:** NFC PPS laundry tag, **24 mm, 2 agujeros** (se cose como botón), **NTAG213**,
  IP68, aguanta lavado/secado/plancha (-20°C a 180°C). ~$0.30–0.60/u por volumen.
  - ⚠️ Al comprar confirmar chip **NTAG213** (NO ICODE SLIX2 — mismo 13.56 MHz pero otro
    protocolo que el RC522 no lee).
- **Muñequera:** tela resistente + velcro o cordón ajustable, botón cosido en el interior.
  Barata, lavable, sumergible, se lleva siempre. Puede llevar el color de la patrulla.
- **Cada botón trae un UID único de fábrica (solo lectura).** Es la única data que usamos:
  no escribimos nada en el chip → cero configuración, el botón sale de la bolsa y funciona.
- **Vínculo UID → niño:** se hace UNA vez en el onboarding (ver endpoint `/juego/nfc-vincular`).

---

## 3. Arquitectura hardware

```
  ESTACIÓN (×N)                        TÓTEM (entrada)
 ┌──────────────┐                    ┌──────────────────┐
 │ ESP32-DevKitC│                    │ ESP32 + PN532    │  (o la tablet TCL con
 │  + RC522     │                    │  (mejor lector)  │   lector USB — decisión 4)
 │  + LED + buzz│                    └────────┬─────────┘
 └──────┬───────┘                             │
        │ tap muñequera → lee UID             │ tap muñequera → lee UID
        │ HTTPS POST (solo acumula)           │ HTTPS POST (llegada + CIERRA vuelta)
        ▼                                     ▼
 ┌──────────────────── RAILWAY (agente FKA) — HTTPS público ───────────────────┐
 │  POST /juego/estacion    POST /juego/totem-nfc    POST /juego/nfc-vincular  │
 │        │                        │                   (Web NFC celu profe)    │
 │        ▼                        ▼                                          │
 │  registrar pasada ──────► evaluar circuito → cerrar vuelta → plata         │
 │  (timestamp del servidor)  (Airtable) → evento → la TV celebra con voz     │
 └────────────────────────────────────────────────────────────────────────────┘
        ▲ GET /juego/eventos?since= cada 2s
 ┌──────┴───────┐
 │  SMART TV    │  (modo TV de la PWA — ya construido, ya habla)
 └──────────────┘
```

### 3A. Estación (checkpoint) — bill of materials por unidad
- 1× **ESP32-DevKitC** (del pack de 6, USB-C, CP2102). El cerebro + WiFi.
- 1× **RC522** (del pack de 6). El lector.
- 1× **LED** (idealmente RGB o WS2812) + 1× **buzzer piezo**. Feedback inmediato local
  ("🔥 fuego encendido") — NO depende de la red, prende al instante de leer el UID.
- 7× **cables jumper** hembra-hembra (RC522↔ESP32, pinout estándar SPI).
- Alimentación: **powerbank USB** (autonomía ~un sábado) o fuente USB fija si hay enchufe.
- Caja: cualquier cajita (impresa 3D, tupper, madera temática de la estación).

### 3B. Tótem
- **PN532** (viene solo, es el mejor lector). Dos caminos, decisión 2:
  - (a) PN532 + su propio ESP32 → POST igual que una estación pero a `/juego/totem-nfc`.
  - (b) PN532 por USB/I2C a la **tablet TCL** que ya se compró para el Espejo → la tablet
    lee el UID y hace el POST. Integra NFC + facial en un solo aparato.
  - Recomendación: **(a) para el prototipo** (independiente, no toca la tablet); evaluar (b)
    cuando el tótem esté armado.

### 3C. Pinout RC522 ↔ ESP32 (referencia de armado)
| RC522 | ESP32 |
|---|---|
| SDA/SS | GPIO 5 |
| SCK | GPIO 18 |
| MOSI | GPIO 23 |
| MISO | GPIO 19 |
| RST | GPIO 22 |
| 3.3V | 3.3V (⚠️ NUNCA 5V — el RC522 es 3.3V) |
| GND | GND |
(PN532 en modo SPI o I2C — pinout según jumpers de la placa HiLetgo; definir en armado.)

---

## 4. Arquitectura software

### 4A. Endpoints nuevos (Railway, `agent/juego_endpoints.py` — el router YA existe por SPEC-TOTEM)

| Endpoint | Auth | Qué hace |
|---|---|---|
| `POST /juego/estacion` | `X-JUEGO-KEY` + key de estación | Body `{estacion_id, uid, rezagada?}`. Resuelve UID→niño y registra la PASADA (timestamp lo pone el SERVIDOR). **NO cierra vueltas** — solo acumula progreso. Dedupe: la misma estación cuenta 1 sola vez por vuelta abierta. Responde `{ok, estaciones_completadas, faltan}`. |
| `POST /juego/totem-nfc` | `X-JUEGO-KEY` | Body `{uid}`. EL tap del tótem, hace dos cosas: **(1)** si es el primer tap del día → asistencia +10 oro + evento `llegada` (saludo con nombre + tramo "entrenaste N días en casa", ver §7). Cooldown 5 min (idéntico al facial). **(2)** SIEMPRE evalúa el circuito: si desde la última vuelta cerrada pasó por TODAS las estaciones activas respetando el tiempo mínimo → **cierra la VUELTA acá**, acredita plata (100/+200/+500), crea evento `vuelta` → la TV celebra CON el niño adelante. Si le faltan estaciones → evento `progreso` opcional: Fénix le dice cuáles le faltan ("te falta encender el fuego del arco 🏹"). |
| `POST /juego/nfc-vincular` | `X-JUEGO-KEY` | Body `{uid, nino_id}`. Onboarding: asocia un botón a un niño. Falla si el UID ya está vinculado a otro (evita robos de identidad). **El lector es el CELULAR del profe**: la página `/profe` usa Web NFC (Chrome Android) — elige al niño, apoya la muñequera contra el celu, y la página manda uid+nino_id juntos. Sin hardware extra y sin estados "pendientes" (que tenían condición de carrera si otro niño tocaba el tótem en ese momento). |
| `GET /juego/estaciones` | key | Config del circuito activo (qué estaciones cuentan, tiempo mínimo, temporada). Editable en Airtable sin deploy. |

- **Reusar** el evento `vuelta` que el tótem YA celebra (SPEC-TOTEM 4C). El NFC solo cambia
  QUIÉN lo dispara: antes el profe, ahora el propio sistema. La TV y la voz no se tocan.
- **La vuelta se cierra en el tótem, nunca en una estación** (decisión, §1): el ritual es
  "encendé todos los fuegos y volvé al Fénix a reclamar". La celebración ocurre donde está
  la TV y el niño presente — la estación del fondo celebraría sola.
- **Pasadas `rezagada: true`** (enviadas desde la cola offline del ESP32) se registran pero
  NO cierran vueltas automáticamente → quedan flaggeadas para que el profe las valide desde
  `/profe`. Motivo: una cola offline con hora del dispositivo sería la forma más fácil de
  fabricar vueltas falsas.
- **UID normalizado** a hex mayúsculas sin separadores (ej. `04A2B3C4D5`) en todo el sistema.

### 4B. Tablas nuevas
**⚠️ v1 IMPLEMENTADA EN POSTGRES (07/07/2026):** `pulseras` / `juego_pasadas` / `juego_vueltas`
viven en el Postgres del agente (mismo patrón que `juego_eventos`), NO en Airtable — porque
las tablas Airtable del juego (MOVIMIENTOS BRASAS, GUARDIANES) recién se crean en F2. La
acreditación de plata se emite como EVENTO por ahora; cuando exista F2 se migra el ledger a
Airtable sin tocar el hardware (los endpoints no cambian). Diseño Airtable objetivo:

(Airtable, base Salsa Soul, sufijo FENIX — patrón PLAN-MAESTRO 5.1)

| Tabla | Campos clave | Nota |
|---|---|---|
| **PULSERAS FENIX** | `uid` (texto, único), link GUARDIAN, activa (bool), fecha_alta | el mapa físico→digital |
| **PASADAS FENIX** | `uid`, estacion_id, timestamp, link VUELTA | ledger crudo de cada tap (auditoría + VAR) |
| **VUELTAS FENIX** | link GUARDIAN, inicio, fin, estaciones_ok (n), válida (bool), plata_acreditada | una fila por vuelta cerrada |
- Acreditación de plata reusa **MOVIMIENTOS BRASAS** (PLAN-MAESTRO 5.1) — no crear ledger nuevo.
- Reglas Airtable conocidas: rollups=array, paginar >100, typecast (reference_airtable_errores).

### 4C. Firmware ESP32 (mismo sketch para estación y tótem, cambia config)
Librerías: `MFRC522` (o `Adafruit_PN532`), `WiFi.h`, `WiFiClientSecure`, `HTTPClient`, `ArduinoJson`.

Lógica (pseudocódigo):
```
setup(): conectar WiFi (SSID de La Casona con salida a internet) · init lector · LED azul "listo"
loop():
  uid = leer_tag()                      # bloqueante hasta que se apoya una muñequera
  if uid:
     LED verde + buzz corto             # feedback INMEDIATO, no espera a la red (dopamina)
     ok = POST_https(endpoint, {estacion_id, uid})       # WiFiClientSecure.setInsecure()
     if ok: LED "fuego" 🔥 (animación)   # confirmación de servidor
     else:  guardar_en_cola(uid, millis)  # si el wifi falla, cola local → reintenta después
     delay(anti-doble-lectura ~2s)
```
- **Timestamps: los pone el SERVIDOR al recibir el POST.** El ESP32 no manda hora (no tiene
  reloj confiable). La única excepción es la cola offline: esas se reenvían con
  `rezagada: true` y el backend las trata distinto (no cierran vueltas solas — ver 4A).
- **Cola offline:** si el POST falla (wifi caído), guardar en un buffer (SPIFFS/NVS) y
  reintentar. El niño ve el fuego local igual; el crédito llega cuando vuelve la red
  (validado por el profe si cerraba una vuelta).
- **HTTPS:** `WiFiClientSecure.setInsecure()` para el piloto (cifra sin validar cert —
  MITM en LAN es riesgo bajo). Endurecer con fingerprint del cert de Railway en producción.
- **estacion_id + key PROPIA de la estación** viven en NVS (config al flashear). Un sketch
  único; cada estación con su id y su key. Si roban una cajita → se revoca SU key en la
  config de Airtable y las demás siguen funcionando.

---

## 5. El flujo completo del niño (paso a paso)

1. **Onboarding (una vez):** el profe abre `/profe` en su celu Android, elige al niño y
   apoya la muñequera nueva contra el celular (Web NFC) → UID vinculado. Listo para siempre.
2. **Llega el sábado:** apoya la muñequera en el tótem (o cámara facial) → +10 oro → la TV
   grita su nombre con la voz de George + lluvia de oro + "veo que entrenaste en casa N
   días esta semana…". (SPEC-TOTEM ya construido; el tramo de entrenamiento es §7.)
3. **Hace el circuito:** en cada estación hace la actividad (arco, pelotas, fuerza…) y apoya
   la muñequera → 🔥 la estación se enciende (LED+buzz) y el fuego queda "prendido".
4. **Reclama la vuelta ante Fénix:** con todos los fuegos encendidos, corre al tótem y apoya
   la muñequera — "¡completé una vuelta, Fénix!". El backend corrobora el recorrido → +100
   plata → la TV celebra CON el niño adelante y todos mirando. Si le falta una estación,
   Fénix se lo dice: "te falta encender el fuego del arco 🏹" (evento `progreso`).
5. **Sigue dando vueltas:** a las 5 → +200 bonus; a las 10 → +500 + caja sorpresa 🎁.
6. **El VAR de fondo:** cada tap tiene timestamp de servidor + estación → si algo es raro
   (dos taps imposibles, tiempos mínimos violados, pasadas rezagadas) queda flaggeado; las
   cámaras F7 son el replay/árbitro.

---

## 6. Anti-trampa (VAR por diseño)

- **Dedupe por vuelta:** tocar la misma estación 3 veces cuenta 1 (lo PRIMERO que un niño
  va a probar). Solo suma la primera pasada por estación dentro de la vuelta abierta.
- **Tiempo mínimo por estación:** si pasa de una estación a otra en < X segundos, la pasada
  no cuenta (config en Airtable). Impide "tap-tap-tap corriendo sin hacer la actividad".
- **La vuelta la corrobora Fénix en el tótem** (no se cierra sola en el campo): el momento
  de acreditación es público, frente a la TV y al profe — la trampa tendría testigos.
- **Pasadas rezagadas (cola offline) nunca cierran vueltas solas** → validación del profe.
- **1 UID no puede estar en 2 estaciones al mismo tiempo:** si el backend ve el mismo UID en
  dos lectores dentro de una ventana imposible → flag (muñequera prestada o clonada).
- **Pulsera maestra del profe (opcional, estaciones supervisadas como arco):** la pasada del
  niño solo cuenta si el profe valida con SU tag después. Mismo lector, cero hardware extra.
- **Tope económico:** la plata por día ya está acotada (PLAN-MAESTRO 6) → no hay "farmeo".
- **Cámaras F7 (VAR):** el replay de la vuelta es a la vez premio (el niño ve su vuelta) y
  árbitro (nadie inventa vueltas). Ver PLAN-MAESTRO 5.3c.

---

## 6b. Mapa Vivo — la segunda TV (construido 07/07, `mapa.html`)

Pantalla extra que consume el MISMO canal de eventos: **mapa ilustrado de La Casona** donde
cada niño es su robot Guardián parado en el último fuego que encendió, y camina por el
sendero cuando toca la siguiente estación. Vuelta cerrada en el tótem → lluvia de monedas
en el mapa. Es render puro de datos que ya existen — cero backend adicional.
- `mundo-fenix/mapa.html`: eventos por localStorage (`mf_tv_event`/`mf_mapa_event`, formato
  del prototipo `{t,n,g,e}`) Y por polling (`CONFIG.API_URL` → `GET /juego/eventos`, formato
  backend `{tipo, nino_nombre, guardian, payload.estacion_id}`). `?demo` = simulación en loop.
- Evento nuevo que el backend debe emitir para alimentarlo: **`estacion`** (cada pasada
  registrada) además de los ya definidos (`llegada`/`vuelta`/`progreso`).
- Muda a propósito (la voz vive en la TV principal). Estaciones/coords editables en el
  array `STATIONS` del archivo.
- **Nivel 2 (movimiento continuo por zonas con pulseras BLE): NO ahora** — diseño completo
  listo para cuando se decida, en `SPEC-BLE-TRACKING.md` (gate de decisión incluido).

## 7. Integración con el reto en casa (el saludo personalizado)

Pedido de Iván: al llegar, Fénix dice *"veo que esta semana entrenaste en casa 3 días e
hiciste tal cosa…"*. Cómo se arma con lo que ya existe:

- Los entrenamientos en casa se registran en la app (video → R2 → acreditación inmediata,
  decisión 07/07, PLAN-MAESTRO 3.3). Cada uno es una fila con niño + fecha + actividades.
- Cuando el niño apoya la muñequera en el tótem (`/juego/totem-nfc`), el backend, además
  del "+10 oro", **consulta los entrenamientos de los últimos 7 días** de ese niño y arma
  una frase → la manda como parte del evento `llegada`.
- La voz: el guion de `llegada` (SPEC-TOTEM 4E) se extiende con un tramo dinámico. Como los
  MP3 son pre-generados por alumno, el tramo "entrenaste N días" se puede:
  - (a) generar en runtime con ElevenLabs (costo bajo, pero latencia), o
  - (b) pre-generar variantes por número de días (0-5) y concatenar — más simple y barato.
  - Decisión en la fase de ejecución; (b) es lo recomendado.
- **El impacto:** el esfuerzo invisible de la casa se vuelve reconocimiento público en la
  academia. Es la marca pura (entrenar lejos de la pantalla para que el Guardián te reconozca).

---

## 8. Fases de implementación

Cada fase = armar + verificar antes de seguir. Regla del proyecto: `/pre-cambio` antes de
tocar `agent/`, deploy incremental, `/pre-deploy` antes de cada push.

| Fase | Qué | Verificación para cerrarla |
|---|---|---|
| **N0 — Banco** | 1 ESP32 + 1 RC522 armado en la mesa. Sketch que lee un tag y lo imprime por serial. | Apoyar un S50/llavero → el UID aparece en el monitor serial. Confirma que el hardware lee. |
| **N1 — Endpoint + evento** | `POST /juego/estacion` + `POST /juego/totem-nfc` + tablas PASADAS/VUELTAS + cierre de vuelta en el tótem + acreditación de plata (mock de 1 niño). Reusa el evento `vuelta` del tótem. **⚡ NO necesita el hardware — se construye YA, mientras el pedido viaja de Miami** (estaciones y tótem simulados con curl). | curl local: N pasadas + tap de tótem → se cierra la vuelta → evento → la TV (Chrome PC) lo celebra con voz. Tap de tótem con estación faltante → evento `progreso`. Deploy → curl prod. |
| **N2 — Estación real** | El ESP32 del banco hace el POST HTTPS real a Railway al leer un tag. Cola offline básica (`rezagada: true`). | Apoyar tag en el ESP32 → la pasada aparece en Airtable en <3s. Cortar wifi → el tag se encola → vuelve wifi → llega como rezagada y queda flaggeada (no cierra vuelta). |
| **N3 — Vínculo + identidad** | `POST /juego/nfc-vincular` con Web NFC en `/profe` (celu Android del profe como lector) + tabla PULSERAS + muñequeras con botón cosido (5-10 para el piloto). | Vincular un botón desde el celu → apoyar en el ESP32 → la pasada se registra a ESE niño. |
| **N4 — Circuito de 3** | 3 estaciones con id y key propios + config de circuito en Airtable + tiempo mínimo + dedupe. El cierre se prueba con tótem simulado (curl o botón en /profe). | Un adulto corre las 3 estaciones y "toca el tótem" → se cierra 1 vuelta (+100). Correrlas en 5s → no cuenta (tiempo mínimo). Tocar 2 veces la misma → cuenta 1. |
| **N5 — Tótem NFC** | PN532 en el tótem → `/juego/totem-nfc` real (+10 oro primera vez + cierre de vueltas). | Apoyar muñequera en el tótem → +10 oro + saludo por nombre; con los 3 fuegos encendidos → cierra la vuelta y la TV celebra. |
| **N6 — Saludo entrenamiento** | El saludo suma "entrenaste N días esta semana" leyendo los entrenamientos de la app. | Cargar 3 entrenamientos de prueba → llegar → la voz menciona los 3 días. |
| **N7 — Sábado piloto** | Circuito de 3 + tótem + muñequeras, con 5 niños reales elegidos a mano. | Los niños completan vueltas sin intervención del profe; las cámaras F7 respaldan. Medir enganche. |

**Gate:** N7 recién cuando N0-N6 estén verificados. El circuito NUNCA rompe el flujo de
Aurora/pagos (regla dura del proyecto).

---

## 9. Presupuesto (prototipo, hardware ya elegido por Iván 07/07)

| Ítem | Cantidad | Costo estimado |
|---|---|---|
| Pack 6× ESP32-DevKitC (USB-C, CP2102) | 1 pack | ~$30–40 |
| Pack 6× RC522 (+ tarjetas S50 + llaveros de prueba) | 1 pack | ~$12–18 |
| PN532 HiLetgo V3 (tótem) | 1 | ~$10 |
| Botones NFC lavables NTAG213 24mm 2 agujeros | 50 | ~$20–30 |
| Muñequeras de tela (o material para coser) | 10–50 | variable / local |
| Cables jumper dupont (pack 40) | 1–2 | ~$6–10 |
| LEDs + buzzers piezo | 6 c/u | ~$5 |
| Powerbanks USB (o fuentes) | 3–6 | ya se tienen / variable |
| **Total hardware núcleo** | | **~$90–120** |

El software (endpoints, firmware, tablas, integración con tótem/voz/cámaras) lo construimos
nosotros — mismo stack que ya corre. Costo de nube: R2 (videos) centavos, Railway ya está.

---

## 10. Riesgos (identificados, con mitigación)

1. **WiFi fragmentado de La Casona** (verificado 06/07: varios wifis 192.168.100.x que no se
   ven entre sí). Las estaciones DEBEN estar en el wifi con salida a internet para llegar a
   Railway. → Pendiente: mapear qué wifi cubre las zonas de las estaciones. Plan B: un router/
   repetidor dedicado para el circuito.
2. **Alimentación de estaciones:** powerbank se agota. → Medir autonomía en N2; preferir
   enchufe fijo donde haya; powerbank de respaldo etiquetado.
3. **Niño arranca/pierde la muñequera:** → botón barato, stock de repuesto, re-vincular en
   30s. La muñequera es reemplazable, el UID se re-asigna.
4. **Clonación de UID:** posible con hardware especial, irreal para un niño de 3-12. El VAR
   (cámaras) y el check "1 UID en 2 lugares" cubren el caso raro.
5. **Chip equivocado en la compra** (ICODE SLIX2 en vez de NTAG213): → confirmar con el
   vendedor ANTES de comprar 50. Los kits RC522 traen S50 que también sirven para probar ya.
6. **RC522 y NTAG:** el RC522 lee el UID de NTAG213 sin problema (solo leemos UID, no NDEF).
   Verificado como diseño; se confirma en la fase N0.
7. **HTTPS en ESP32:** `setInsecure()` para el piloto; endurecer con fingerprint después.
8. **Web NFC (vinculación) solo funciona en Chrome sobre ANDROID** — no existe en iPhone ni
   en desktop. El celu del profe que vincule debe ser Android (y `/profe` ya se sirve por
   HTTPS, requisito de Web NFC). Fallback si no hay Android a mano: apoyar la muñequera en
   una estación en "modo vincular" o tipear el UID a mano (aparece en el serial/log).

---

## 11. Checklist de compra (para pedir todo junto a Miami)

- [x] Pack 6× ESP32-DevKitC (elegido)
- [x] Pack 6× RC522 (elegido)
- [x] PN532 HiLetgo V3 (elegido)
- [ ] Botones NFC lavables **NTAG213** 24mm 2 agujeros ×50 — *confirmar chip NTAG213 con vendedor*
- [ ] Cables jumper dupont hembra-hembra (pack 40) ×2
- [ ] LEDs (RGB o WS2812) + buzzers piezo ×6
- [ ] Muñequeras de tela (comprar o mandar a coser localmente)
- [ ] Powerbanks USB (si no hay enchufe en las zonas)

**Primer paso apenas llegue el hardware:** Fase N0 (banco) — leer un UID por serial. Todo lo
demás se construye sobre esa confirmación.
