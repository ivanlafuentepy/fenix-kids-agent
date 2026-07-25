// firmware/estacion/estacion.ino — Fase N2 del circuito NFC (SPEC-NFC-CIRCUITO §4C)
//
// Igual que banco_lector (fase N0: confirmar que el hardware lee) pero además manda
// cada tap por WiFi al backend: POST /juego/estacion. Mismo cableado RC522 → ESP32,
// ver firmware/README.md.
//
// Credenciales (WiFi, JUEGO_API_KEY, estacion_id) viven en config.h — NO en este archivo.
// Copiar config.h.example a config.h y completar antes de compilar.

#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <FastLED.h>
#include "config.h"

#define PIN_SS   5    // SDA del RC522
#define PIN_RST  22

// Anillo COB WS2811, 27mm — no sabemos el número exacto de LEDs físicos, así que
// pedimos de más (16). Los que no existen físicamente no reciben nada: no rompe nada,
// solo garantiza que TODOS los que sí hay se prendan.
#define PIN_LED   4
#define NUM_LEDS  16
CRGB leds[NUM_LEDS];

// Buzzer piezo PASIVO (necesita tone()/PWM, no un simple HIGH — a diferencia de uno activo).
#define PIN_BUZZER 25

MFRC522 lector(PIN_SS, PIN_RST);

// Antirrebote local: la misma pulsera apoyada 3 segundos no dispara 40 POSTs.
// El backend también dedupea por vuelta abierta — esto es nomás para no floodear la red.
String ultimo_uid = "";
unsigned long ultimo_ms = 0;
const unsigned long ESPERA_MISMO_UID_MS = 2000;

// DURACIÓN FIJA en vez de detectar el retiro real con WUPA/Select: se probó ese camino
// (WakeupA→Select→HaltA en loop) y dos veces distintas terminó dejando al RC522 sin
// responder a NINGÚN tag nuevo hasta reiniciar el ESP32 — probablemente un estado interno
// del chip/librería que no se limpia bien con esa secuencia en este hardware puntual.
// Se prefiere esto: menos preciso (el LED no seguía el retiro exacto), pero CONFIABLE
// (nunca cuelga la detección del próximo tag, que es un problema mucho peor con chicos
// tocando estaciones todo el rato).
const unsigned long DURACION_LED_MS = 1500;

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) { }

  SPI.begin();
  lector.PCD_Init();
  delay(50);            // el RC522 necesita un respiro antes de responder la versión
  lector.PCD_SetAntennaGain(MFRC522::RxGain_max);   // de fábrica arranca en ganancia media, no la máxima

  FastLED.addLeds<WS2811, PIN_LED, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(120);
  FastLED.clear();
  FastLED.show();

  pinMode(PIN_BUZZER, OUTPUT);

  Serial.println();
  Serial.println(F("== FENIX KIDS — estación NFC (fase N2) =="));
  Serial.print(F("Estación: "));
  Serial.println(ESTACION_ID);
  diagnosticar_lector();
  escanear_redes();
  WiFi.onEvent(onWifiEvent);
  conectar_wifi();
  Serial.println(F("Apoyá una pulsera sobre el lector..."));
  Serial.println();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectar_wifi();

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

  Serial.print(F("UID: "));
  Serial.println(uid);
  fill_solid(leds, NUM_LEDS, CRGB::Green);   // prendido fijo — ver nota en DURACION_LED_MS
  FastLED.show();
  beep();   // feedback inmediato, igual que el LED, no depende de la red
  delay(DURACION_LED_MS);

  FastLED.clear();
  FastLED.show();
  cerrar_lectura();
  enviar_tap(uid);   // recién ahora — el POST a Railway NUNCA debe demorar el LED (SPEC-NFC-CIRCUITO §4C)
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

// Barrido de frecuencias en vez de un tono fijo: un piezo pasivo suena bien más fuerte
// en su frecuencia de resonancia, y no sabemos cuál es la de este disco puntual.
void beep() {
  for (int f = 1500; f <= 4500; f += 300) {
    tone(PIN_BUZZER, f, 25);
    delay(25);
  }
  noTone(PIN_BUZZER);
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
    Serial.println(F("!! El lector NO responde. Revisá cableado y soldadura del header."));
  } else {
    Serial.println(F("Lector OK."));
  }
}

// Lista las redes 2.4GHz que el ESP32 ve DE VERDAD desde donde está — para no adivinar
// nombre exacto (mayúsculas/espacios) ni asumir que una red está en rango.
void escanear_redes() {
  Serial.println(F("Escaneando redes WiFi..."));
  int n = WiFi.scanNetworks();
  if (n <= 0) {
    Serial.println(F("  (no se vio ninguna red)"));
    return;
  }
  for (int i = 0; i < n; i++) {
    Serial.print(F("  \""));
    Serial.print(WiFi.SSID(i));
    Serial.print(F("\"  RSSI="));
    Serial.print(WiFi.RSSI(i));
    Serial.println(WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? F("  (abierta)") : F(""));
  }
  Serial.println();
}

unsigned long ultimo_intento_wifi = 0;
const unsigned long ESPERA_ENTRE_INTENTOS_MS = 8000;   // no reintentar antes de que termine el intento previo

// Motivo real del fallo — evita adivinar entre password mal, red 5GHz, AP no encontrado, etc.
// Códigos: https://github.com/espressif/esp-idf/blob/master/components/esp_wifi/include/esp_wifi_types_generic.h
void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    Serial.print(F("WiFi desconectado, razón = "));
    Serial.println(info.wifi_sta_disconnected.reason);
  }
}

void conectar_wifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - ultimo_intento_wifi < ESPERA_ENTRE_INTENTOS_MS) return;   // ya hay un intento en curso
  ultimo_intento_wifi = millis();

  Serial.print(F("Conectando a WiFi "));
  Serial.print(WIFI_SSID);
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < 15000) {
    delay(300);
    Serial.print(F("."));
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print(F("WiFi OK, IP: "));
    Serial.println(WiFi.localIP());
  } else {
    Serial.print(F("!! No se pudo conectar al WiFi. Status = "));
    Serial.println(WiFi.status());
  }
}

// POST /juego/estacion — ver agent/juego_endpoints.py. Responde
// {ok, valida, estaciones_completadas, faltan} o {ok:false, motivo:"pulsera_no_vinculada"}.
void enviar_tap(const String &uid) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(F("!! Sin WiFi, no se envió el tap."));
    return;
  }

  WiFiClientSecure cliente;
  cliente.setInsecure();   // sin validar certificado — dispositivo embebido simple (SPEC §4C)

  HTTPClient http;
  String url = String("https://") + SERVER_HOST + "/juego/estacion";
  http.begin(cliente, url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-JUEGO-KEY", JUEGO_API_KEY);

  JsonDocument doc;
  doc["uid"] = uid;
  doc["estacion_id"] = ESTACION_ID;
  String body;
  serializeJson(doc, body);

  int codigo = http.POST(body);
  String respuesta = (codigo > 0) ? http.getString() : http.errorToString(codigo);

  Serial.print(F("POST /juego/estacion -> "));
  Serial.print(codigo);
  Serial.print(F(" "));
  Serial.println(respuesta);

  http.end();
}
