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

MFRC522 lector(PIN_SS, PIN_RST);

// Antirrebote local: la misma pulsera apoyada 3 segundos no dispara 40 POSTs.
// El backend también dedupea por vuelta abierta — esto es nomás para no floodear la red.
String ultimo_uid = "";
unsigned long ultimo_ms = 0;
const unsigned long ESPERA_MISMO_UID_MS = 2000;

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) { }

  SPI.begin();
  lector.PCD_Init();
  delay(50);            // el RC522 necesita un respiro antes de responder la versión

  FastLED.addLeds<WS2811, PIN_LED, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(120);
  FastLED.clear();
  FastLED.show();

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
  prender_led(CRGB::Green, 400);   // feedback local instantáneo — no depende del WiFi/POST
  enviar_tap(uid);

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

// Prende el anillo entero de un color por ms milisegundos, después lo apaga.
void prender_led(CRGB color, int ms) {
  fill_solid(leds, NUM_LEDS, color);
  FastLED.show();
  delay(ms);
  FastLED.clear();
  FastLED.show();
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
