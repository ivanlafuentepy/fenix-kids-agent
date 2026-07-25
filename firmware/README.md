# Firmware del circuito NFC — Mundo Fenix

Firmware de las estaciones y el tótem del circuito NFC. El diseño completo (por qué cada
decisión) vive en [`mundo-fenix/SPEC-NFC-CIRCUITO.md`](../mundo-fenix/SPEC-NFC-CIRCUITO.md);
acá está lo operativo: cómo se cablea, cómo se compila y cómo se flashea.

El backend ya está en producción (`agent/juego_endpoints.py`) — el firmware solo reemplaza
los `curl` con los que se verificó el circuito por hardware real.

---

## Sketches

| Carpeta | Fase | Qué hace |
|---|---|---|
| `banco_lector/` | **N0** | Lee el UID de una pulsera y lo imprime por serial. Sin WiFi. Confirma que el hardware lee. |

---

## Cableado RC522 → ESP32-DevKitC

Los 7 jumpers hembra-hembra del pack Dupont. **El RC522 va a 3.3V — el pin de 5V lo quema.**

| RC522 | ESP32 | Color sugerido |
|---|---|---|
| SDA (SS) | GPIO 5 | amarillo |
| SCK | GPIO 18 | naranja |
| MOSI | GPIO 23 | azul |
| MISO | GPIO 19 | verde |
| IRQ | *(no se conecta)* | — |
| GND | GND | negro |
| RST | GPIO 22 | blanco |
| 3.3V | **3.3V** ⚠️ | rojo |

En el ESP32-DevKitC de 38 pines, el pin `3V3` está en la esquina superior de un costado y
hay varios `GND` repartidos — sirve cualquiera.

---

## Compilar y flashear (arduino-cli)

Requisitos ya instalados en esta PC: `arduino-cli` 1.5.1, core `esp32:esp32`, librería
`MFRC522`. Desde la raíz del repo:

```bash
# 1. ver en qué puerto quedó la placa (con el ESP32 enchufado por USB)
arduino-cli board list

# 2. compilar
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/banco_lector

# 3. flashear (cambiar COMx por el puerto del paso 1)
arduino-cli upload -p COMx --fqbn esp32:esp32:esp32 firmware/banco_lector

# 4. ver la salida
arduino-cli monitor -p COMx -c baudrate=115200
```

### Si el upload falla con "Failed to connect / no serial data received"

1. Mantené apretado el botón **BOOT** de la placa, tocá **EN/RST** una vez, soltá BOOT.
2. Si el puerto no aparece en `board list`: falta el driver **CP2102** de Silicon Labs.
3. Probá otro cable USB — muchos cables baratos son solo de carga, sin líneas de datos.

### Si `arduino-cli monitor` no muestra nada

En algunos entornos `arduino-cli monitor` corrido en background/redirigido no vuelca el log
(queda vacío aunque el ESP32 esté imprimiendo). Alternativa que sí funciona, con `pyserial`
(`py -3 -m pip install pyserial` si no está):

```bash
py -3 firmware/leer_serial.py COM3 90   # escucha el puerto 90 segundos, con timestamp por línea
```

---

## Diagnóstico del lector

El sketch de banco imprime `RC522 VersionReg` al arrancar:

| Valor | Significa |
|---|---|
| `0x91` / `0x92` | Lector OK (v1.0 / v2.0) |
| `0x00` o `0xFF` | No responde → cableado, alimentación o header sin soldar |

---

## Formato del UID

El UID se normaliza a **hex mayúsculas sin separadores** (`04A2B3C4D5`) — idéntico a
`_norm_uid()` en `agent/juego_endpoints.py`. Los NTAG213 dan 7 bytes (14 caracteres); las
tarjetas S50 del kit RC522, 4 bytes (8 caracteres). Ambos sirven para probar.
