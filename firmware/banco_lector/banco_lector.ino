// firmware/banco_lector/banco_lector.ino — Fase N0 del circuito NFC (SPEC-NFC-CIRCUITO §8)
//
// Objetivo único: confirmar que el hardware LEE. Apoyás una pulsera/tarjeta sobre el RC522
// y el UID aparece por el monitor serial, ya normalizado igual que el backend
// (hex mayúsculas sin separadores — ver _norm_uid en agent/juego_endpoints.py).
//
// Todavía NO hay WiFi ni POST: eso es la fase N2. Acá aislamos el problema de hardware
// del problema de red, así si algo falla sabemos exactamente dónde.
//
// Cableado RC522 → ESP32-DevKitC (SPEC-NFC-CIRCUITO §3C):
//   SDA/SS → GPIO 5   ·  SCK → GPIO 18  ·  MOSI → GPIO 23
//   MISO   → GPIO 19  ·  RST → GPIO 22
//   3.3V   → 3.3V  ⚠️ NUNCA al pin de 5V: el RC522 se quema
//   GND    → GND

#include <SPI.h>
#include <MFRC522.h>

#define PIN_SS   5    // SDA del RC522
#define PIN_RST  22

MFRC522 lector(PIN_SS, PIN_RST);

// Antirrebote: la misma pulsera apoyada 3 segundos no imprime 40 veces.
String ultimo_uid = "";
unsigned long ultimo_ms = 0;
const unsigned long ESPERA_MISMO_UID_MS = 2000;

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) { }   // le damos un momento al monitor serial

  SPI.begin();          // usa los pines SPI por defecto del ESP32 (18/19/23)
  lector.PCD_Init();
  delay(50);            // el RC522 necesita un respiro antes de responder la versión

  Serial.println();
  Serial.println(F("== FENIX KIDS — lector de banco (fase N0) =="));
  diagnosticar_lector();
  Serial.println(F("Apoyá una tarjeta, llavero o pulsera sobre el lector..."));
  Serial.println();
}

void loop() {
  // PICC_IsNewCardPresent no bloquea: si no hay tag, sale enseguida
  if (!lector.PICC_IsNewCardPresent()) return;
  if (!lector.PICC_ReadCardSerial()) return;

  String uid = uid_normalizado();
  unsigned long ahora = millis();

  if (uid == ultimo_uid && (ahora - ultimo_ms) < ESPERA_MISMO_UID_MS) {
    cerrar_lectura();
    return;
  }
  ultimo_uid = uid;
  ultimo_ms = ahora;

  MFRC522::PICC_Type tipo = lector.PICC_GetType(lector.uid.sak);

  Serial.print(F("UID: "));
  Serial.print(uid);
  Serial.print(F("   ("));
  Serial.print(lector.uid.size);
  Serial.print(F(" bytes, "));
  Serial.print(lector.PICC_GetTypeName(tipo));
  Serial.println(F(")"));

  cerrar_lectura();
}

// UID en hex mayúsculas sin separadores (04A2B3C4D5) — el formato que espera el backend.
String uid_normalizado() {
  String s = "";
  for (byte i = 0; i < lector.uid.size; i++) {
    if (lector.uid.uidByte[i] < 0x10) s += "0";
    s += String(lector.uid.uidByte[i], HEX);
  }
  s.toUpperCase();
  return s;
}

void cerrar_lectura() {
  lector.PICC_HaltA();          // el tag deja de responder hasta que se retire y vuelva
  lector.PCD_StopCrypto1();
}

// La versión del firmware del RC522 es el test de cableado: 0x00 o 0xFF = mal conectado.
void diagnosticar_lector() {
  byte v = lector.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print(F("RC522 VersionReg = 0x"));
  Serial.println(v, HEX);

  if (v == 0x00 || v == 0xFF) {
    Serial.println(F("!! El lector NO responde. Revisá:"));
    Serial.println(F("   - 3.3V y GND bien puestos (NUNCA 5V)"));
    Serial.println(F("   - SDA=5 · SCK=18 · MOSI=23 · MISO=19 · RST=22"));
    Serial.println(F("   - jumpers flojos o mal soldado el header del RC522"));
  } else {
    Serial.println(F("Lector OK."));
  }
}
