# SPEC — Tracking BLE por zonas (Mapa Vivo nivel 2) — PARA DESPUÉS
> Escrito 2026-07-07 (sesión Fable). NO se implementa ahora — este doc existe para que,
> cuando el Mapa Vivo nivel 1 (saltos NFC, `mapa.html`) quede corto, la mejora esté
> pensada y se pueda ejecutar sin re-investigar.
> Prerequisito: circuito NFC funcionando (SPEC-NFC-CIRCUITO.md) + backend de eventos.

---

## 0. Qué agrega sobre el nivel 1 (y qué no)

| | Nivel 1 — NFC (ya diseñado) | Nivel 2 — BLE (este doc) |
|---|---|---|
| El avatar se mueve | por SALTOS (cuando toca una estación) | SOLO, en continuo (zona actual real) |
| Entre estaciones | no se sabe dónde está | se sabe la ZONA (pileta/cancha/quincho…) |
| Hardware niño | botón NFC pasivo (sin batería, $0.5) | pulsera BLE activa (CON batería, $5-15) |
| Mantenimiento | cero | cargar/cambiar pilas + gestionar flota |
| Precisión | exacta en el punto del tap | nivel ZONA (~radio 5-15 m), nunca GPS |
| Seguridad | no aplica | alerta "niño en zona no habilitada" (muelle/río) |

**El NFC no se reemplaza**: la identidad del circuito (taps, vueltas, tótem) sigue siendo
NFC. El BLE se SUMA solo para presencia continua en el mapa + alertas de zona.

---

## 1. Hardware

### 1A. La pulsera del niño (beacon BLE)
- **Qué es:** un emisor Bluetooth Low Energy que grita "acá estoy" (advertising) cada ~1s.
  No se conecta a nada — solo emite su ID. Igual que las pulseras de parque acuático.
- **Opciones (de más simple a más pro):**
  1. **Beacon llavero/pulsera iBeacon genérico** (AliExpress "ibeacon waterproof bracelet",
     $5-10): batería de botón CR2032, dura 6-18 meses, se cambia la pila. RECOMENDADO para
     el piloto.
  2. **Pulsera BLE recargable de silicona** ($10-15): USB, hay que cargarla cada 1-4 semanas
     → más lindas pero más gestión. Solo si el piloto valida.
  3. **NO usar**: tags Apple AirTag / Samsung SmartTag (ecosistema cerrado, no se puede
     leer el ID libremente) ni UWB (precisión de 30cm pero $$$ — overkill total).
- **Identidad:** cada beacon emite un `MAC`/UUID fijo → tabla `PULSERAS FENIX` gana una
  columna `ble_mac` al lado del `uid` NFC. Un niño = 1 botón NFC + 1 beacon BLE
  (idealmente EN la misma muñequera de tela: el botón cosido + el beacon en un bolsillito).

### 1B. Los receptores por zona (¡ya los tenemos!)
- **Los mismos ESP32 de las estaciones escanean BLE de fábrica** — doble trabajo: leen NFC
  y escuchan beacons. Cero hardware nuevo en las zonas que ya tienen estación.
- Para zonas SIN estación (pileta, muelle, casa del árbol): **1 ESP32 pelado por zona**
  (~$5, sin lector NFC) enchufado a un cargador USB. Solo escucha y reporta.
- Cobertura realista: un ESP32 escucha beacons a ~10-30 m al aire libre. Una zona = un
  ESP32 en el centro. La Casona entera con ~8-10 receptores.

---

## 2. Cómo se calcula "en qué zona está" (RSSI, el único truco)

Cada receptor escucha a cada beacon con una **intensidad de señal (RSSI)**. El que lo
escucha MÁS FUERTE gana → esa es la zona del niño. Reglas para que no "rebote":

1. **Ventana + promedio:** promediar el RSSI de los últimos ~10s por (beacon, receptor) —
   el RSSI crudo salta muchísimo.
2. **Histéresis:** cambiar de zona SOLO si la nueva zona le gana a la actual por >6 dB
   sostenidos. Sin esto el avatar parpadea entre dos zonas vecinas.
3. **Timeout:** si ningún receptor lo escucha por >60s → estado "sin señal" (el mapa lo
   atenúa, NO lo teletransporta).
4. La calibración fina (umbral por zona, potencia de emisión del beacon) se hace EN
   La Casona con niños de verdad — no vale la pena simularla antes.

**El ESP32 NO manda cada lectura al backend** (sería spam): agrega localmente y reporta
cada ~10s un batch: `{receptor_id, lecturas:[{mac, rssi_prom}]}`.

---

## 3. Arquitectura (se enchufa a lo que ya existe)

```
 pulseras BLE (beacon, ~1s advertising)
      ▼  (escucha pasiva)
 ESP32 por zona (estación NFC o receptor pelado)
      ▼  POST /juego/presencia  cada ~10s (batch, key por dispositivo)
 RAILWAY backend
   → resolver mac→niño → RSSI: ventana+histéresis → zona actual por niño
   → tabla presencia EN MEMORIA CALIENTE + evento `zona` SOLO al cambiar
      ▼  GET /juego/eventos (mismo polling de siempre)
 mapa.html → el avatar CAMINA a la zona nueva (ya soporta eventos, tipo nuevo "zona")
 + regla de alerta: zona ∈ {muelle} y sin profe → aviso al celu del profe
```

- **Endpoint nuevo:** `POST /juego/presencia` (batch RSSI). Todo lo demás REUSA el canal
  de eventos existente. `mapa.html` solo aprende el tipo de evento `zona` (~15 líneas).
- **Nada de esto guarda historial**: la presencia vive en memoria con TTL corto. A la DB solo van
  los eventos del JUEGO (taps, vueltas) — ver privacidad.

## 4. Privacidad (NO NEGOCIABLE — hereda PLAN-MAESTRO 5.3c)

1. **Nivel zona, nunca trayectoria fina.** El sistema no sabe (ni quiere saber) el punto
   exacto — solo "está en la pileta".
2. **Sin historial:** la posición NO se archiva por niño. El mapa es "ahora". Los batches
   RSSI se descartan al procesarse. Lo único persistente = eventos del juego (como hoy).
3. **Opt-in por familia** (mismo patrón que fotos/biometría). Niño sin opt-in = beacon no
   asignado; su experiencia de juego NFC es idéntica.
4. **El mapa muestra avatares y nombres de Guardián**, jamás fotos/video.
5. **Narrativa pública:** "cada rincón donde juega tu hijo, cubierto — nunca fuera de
   vista" + el mapa es PARTE DEL JUEGO. Nunca la palabra "tracking".
6. La alerta de zona (muelle/río) se comunica como SEGURIDAD — es el argumento más
   vendible del sistema y es defendible ante cualquier padre.

## 5. Fases (cuando se decida hacerlo)

| Fase | Qué | Verificación |
|---|---|---|
| B0 | Comprar 2 beacons de prueba + sketch de escaneo BLE en un ESP32 de estación (dual NFC+BLE) | El serial muestra MAC + RSSI de los 2 beacons; el NFC de la estación sigue andando |
| B1 | `POST /juego/presencia` + resolución zona (ventana+histéresis) + evento `zona` | Caminar con un beacon entre 2 zonas → el evento sale una vez por cambio, sin rebote |
| B2 | `mapa.html` consume evento `zona` (avatar camina solo) | El avatar sigue a la persona por el mapa en <15s de retraso |
| B3 | Receptores en zonas sin estación (pileta, muelle, árbol) + calibración in situ | Mapa de cobertura: ningún punto ciego en zonas de juego |
| B4 | Alerta de zona no habilitada al celu del profe | Beacon al muelle → notificación en <30s |
| B5 | Flota real: beacons en las muñequeras, alta en PULSERAS FENIX (`ble_mac`), rutina de pilas | Sábado piloto con 5-10 niños con opt-in |

## 6. Presupuesto estimado (piloto BLE)

| Ítem | Cant. | Costo |
|---|---|---|
| Beacons iBeacon CR2032 (prueba + piloto) | 10-12 | ~$60-100 |
| ESP32 extra para zonas sin estación | 3-4 | ~$20 (o sobran del pack de 6) |
| Cargadores USB | 3-4 | ya se tienen |
| **Total** | | **~$80-120** |

## 7. Gate de decisión (cuándo hacer esto)

Hacer el nivel 2 SOLO si, después del piloto NFC:
- el Mapa Vivo por saltos queda visiblemente "muerto" entre taps (los niños/padres lo notan), **o**
- Iván quiere la alerta de seguridad de zona (muelle/río) como feature vendible, **o**
- los profes piden saber dónde están los niños entre estaciones.

Si ninguna de las tres pasa → el nivel 1 alcanza y esto queda archivado sin costo.
