# Circuito NFC — Compras y Pendientes de instalar
> Checklist de hardware del juego (SPEC-NFC-CIRCUITO.md). Última actualización: 2026-07-07.
> Regla de compatibilidad: TODO debe ser **NTAG213 / ISO14443A / 13.56 MHz**. NO sirve
> ICODE SLIX (ISO15693) ni UHF (900 MHz) — el RC522 no los lee.

---

## 1. 🛒 Comprado / en el carrito (AliExpress → Miami)

| Ítem | Modelo / detalle | Cant. | Precio | Para qué |
|---|---|---|---|---|
| **ESP32-DevKitC** | ESP-32D, CP2102, USB-C, 38 pin (pack 6) | 6 | ~$30-40 | El cerebro + WiFi de cada estación |
| **RC522** | Mifare RC522 kit (trae tarjetas S50 + llaveros de prueba) (pack 6) | 6 | ~$12-18 | Lector NFC de cada estación |
| **PN532** | HiLetgo PN532 NFC V3 (I2C/SPI/HSU) | 1 | ~$10 | Lector del TÓTEM (lee mejor/más lejos) |
| **Botones NFC** | ZONi **PPS25-14443A / NTAG213** ⚠️ (Ø25.5mm, 2 agujeros, IP67, 200°C) | 50 | $34.07 | Identidad del niño (cosido en muñequera/capa) |
| **Cables Dupont** | 20cm, 3 tipos (H-H + M-M + M-H), 120 piezas | 1 pack | $4.47 | Conectar lector ↔ ESP32 (7 cables/lector) |
| **Anillo LED** | WS2812 COB **5V** 48mm (RGB direccionable) | según estaciones | $4.68 c/u | El "🔥 fuego" que se enciende al apoyar la pulsera |

**⚠️ AL COMPRAR LOS BOTONES:** confirmar que la variante diga **`14443A` / `NTAG213`**, NUNCA
`15693` ni `15093` (ese vendedor vende ICODE SLIX bajo el mismo anuncio — ese chip NO lo lee el RC522).
**⚠️ EL LED:** que sea **5V**, no 12V (el ESP32 lo alimenta por USB).

---

## 2. ⏳ Falta comprar

| Ítem | Buscar en AliExpress | Cant. | Precio aprox. | Nota |
|---|---|---|---|---|
| **Zumbador piezo** | `passive buzzer module 3.3V arduino` | 6 | ~$3 pack | El "beep" del check en la estación |
| **Muñequeras de tela** | `muñequera deportiva velcro niños` / `elastic wristband blank` | 10-15 | variable | Donde se cose el botón NFC (identidad diaria) |
| **Alimentación** | `cargador USB 5V 2A` + cable USB-C (o `power bank 5000mAh` si no hay enchufe) | 1/estación | ~$5-12 | Alimenta el ESP32 |
| **Cajas** (opcional) | `caja proyecto ABS 100x60mm` (o tupper / impresión 3D) | 6 | ~$2 c/u | Proteger la plaquita; temática por estación |

---

## 3. 🔧 Pendiente de armar / instalar (cuando llegue el hardware)

Orden = fases del `SPEC-NFC-CIRCUITO.md`. Cada una se verifica antes de la siguiente.

- [ ] **N0 — Banco:** armar 1 ESP32 + 1 RC522 con jumpers, flashear el sketch, apoyar una tarjeta S50 → que el UID aparezca por serial. (Confirma que el hardware lee.)
- [ ] **N2 — Estación real:** el ESP32 hace el POST HTTPS real a Railway al leer un tag + LED/buzzer de feedback + cola offline.
- [ ] **N3 — Identidad:** coser botones NFC en muñequeras + vincular con el celu del profe (Web NFC en `/static/profe.html`).
- [ ] **N4 — Circuito de 3:** 3 estaciones con id propio (ninja/arbol/basket/quincho/muelle) + tiempo mínimo + dedupe.
- [ ] **N5 — Tótem NFC:** PN532 en el tótem → cierra la vuelta y la TV celebra.
- [ ] **N7 — Sábado piloto:** circuito + tótem + muñequeras con 5 niños reales.
- [ ] **Tablet TCL** (ya comprada): Fully Kiosk → `mundo-fenix.pages.dev/totem` + montaje ~1.10m + tipear la clave del juego una vez.
- [ ] **DVR (F7):** fijar IP + usuario dedicado (requiere estar en la red de La Casona).

**Firmware/software del ESP32:** libs `MFRC522`/`Adafruit_PN532` + `WiFi` + `WiFiClientSecure`
+ `HTTPClient` + `ArduinoJson`. Pinout RC522↔ESP32 y lógica en `SPEC-NFC-CIRCUITO.md §3C-4C`.
Cada estación lleva su `estacion_id` + su key. HTTPS con `setInsecure()` para el piloto.

---

## 4. ✅ Ya LISTO (el software, hecho el 07/07 — no espera al hardware)

- Backend de eventos + circuito NFC + checkin facial + app del profe → **en producción** (Railway `/juego/*`).
- App del juego con datos reales (link mágico, economía en el servidor, videos a R2, multi-hijo) → **en producción** (`mundo-fenix.pages.dev`).
- Mapa Vivo + Modo TV + tótem conectados al backend real. 23 alumnos con voz de George.
- **El circuito NFC ya funciona de punta a punta** (vuelta completa verificada por curl). Solo falta
  reemplazar el "curl" por los ESP32 físicos → por eso el hardware es lo único que falta para el piloto.

---

## Presupuesto total del prototipo
Hardware núcleo ~$90-120 (Iván mencionó que lo de Fénix en el pedido actual es **~$15** — arranque
mínimo: 1-2 de cada cosa para la fase N0). El pedido grande (6 estaciones + volumen de botones con
logo Fénix a Alibaba) se hace DESPUÉS de que el piloto valide la experiencia con niños reales.
