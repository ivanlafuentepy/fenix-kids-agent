// firmware/diagnostico_rc522/diagnostico_rc522.ino — ¿el RC522 está sano por dentro?
//
// Cuando un lector responde VersionReg pero NO detecta ningún tag, el cableado de datos
// está bien (si no, daría 0x00) y el problema está más adentro. Este sketch interroga los
// registros internos para separar tres casos que desde afuera se ven idénticos:
//
//   A) chip dañado            → el autotest de fábrica falla
//   B) sección de RADIO muerta → el autotest pasa, pero los drivers de antena no encienden
//   C) todo sano              → pasa todo y el problema es el tag o la distancia
//
// El caso B es el típico de una placa sobrecalentada al soldar: el cristal de 27,12 MHz y
// los capacitores del filtro de antena están al lado del header. El SPI no usa ese cristal
// (el reloj lo pone el ESP32 por SCK), por eso el chip sigue contestando aunque no pueda
// generar el campo de 13,56 MHz que despierta a la pulsera.
//
// Mismo cableado que banco_lector (ver firmware/README.md). No usa WiFi.

#include <SPI.h>
#include <MFRC522.h>

#define PIN_SS   5
#define PIN_RST  22

MFRC522 lector(PIN_SS, PIN_RST);

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 3000) { }

  SPI.begin();
  lector.PCD_Init();
  delay(50);

  Serial.println();
  Serial.println(F("== FENIX KIDS — diagnóstico del RC522 =="));
  Serial.println();

  bool ok_version = prueba_version();
  bool ok_bus     = prueba_bus();
  bool ok_antena  = prueba_antena();
  bool ok_self    = prueba_autotest();

  Serial.println();
  Serial.println(F("---------------- VEREDICTO ----------------"));
  if (!ok_version || !ok_bus) {
    Serial.println(F("CABLEADO: el chip no contesta de forma confiable."));
    Serial.println(F("  -> revisar 3.3V, GND y los pines SPI antes de culpar al modulo."));
  } else if (!ok_antena) {
    Serial.println(F("RADIO MUERTA: el chip responde pero la antena no enciende."));
    Serial.println(F("  -> el modulo no sirve para leer tags, cambiarlo."));
  } else {
    Serial.println(F("BUS Y ANTENA OK. Esto NO garantiza que lea."));
    Serial.println(F("  -> el unico criterio valido es probar un TAG QUE SEPAS QUE FUNCIONA"));
    Serial.println(F("     con firmware/banco_lector. Un RC522 puede pasar todo esto y"));
    Serial.println(F("     no leer nada (verificado 2026-08-11 en la estacion gym)."));
  }
  if (!ok_self) {
    Serial.println();
    Serial.println(F("(autotest en FALLA: NO concluyente — ver nota en la prueba [4])"));
  }
  Serial.println(F("-------------------------------------------"));
}

void loop() { }

// 1) Versión del firmware del chip. 0x91/0x92 = v1.0/v2.0; 0x00 o 0xFF = no contesta.
bool prueba_version() {
  byte v = lector.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print(F("[1] VersionReg      = 0x"));
  Serial.print(v, HEX);
  bool ok = (v == 0x91 || v == 0x92);
  Serial.println(ok ? F("   OK") : F("   !! no responde o version rara"));
  return ok;
}

// 2) El bus de verdad: escribir valores y leerlos de vuelta. VersionReg es de solo lectura
//    y siempre da lo mismo — podría contestar por alimentación parásita. Esto prueba que
//    el chip ESCUCHA lo que le mandamos, no solo que devuelve una constante.
bool prueba_bus() {
  const byte patrones[] = {0xA5, 0x5A, 0x00, 0xFF};
  bool ok = true;
  Serial.print(F("[2] escritura/lectura:"));
  for (byte p : patrones) {
    lector.PCD_WriteRegister(MFRC522::FIFODataReg, p);
    byte leido = lector.PCD_ReadRegister(MFRC522::FIFODataReg);
    Serial.print(F(" 0x"));
    Serial.print(p, HEX);
    Serial.print(leido == p ? F("=OK") : F("=MAL"));
    if (leido != p) ok = false;
    lector.PCD_WriteRegister(MFRC522::FIFOLevelReg, 0x80);   // limpiar el FIFO
  }
  Serial.println(ok ? F("   -> bus OK") : F("   -> BUS INESTABLE"));
  return ok;
}

// 3) Lo que de verdad importa acá: ¿encienden los drivers de la antena?
//    TxControlReg bits 0 y 1 (Tx1RFEn/Tx2RFEn) = las dos patas que excitan la bobina.
//    Si tras pedir PCD_AntennaOn() esos bits NO quedan en 1, el chip no puede generar
//    el campo -> ningún tag va a despertarse jamás, por más cerca que lo apoyes.
bool prueba_antena() {
  lector.PCD_AntennaOff();
  delay(20);
  byte apagada = lector.PCD_ReadRegister(MFRC522::TxControlReg);

  lector.PCD_AntennaOn();
  delay(50);
  byte encendida = lector.PCD_ReadRegister(MFRC522::TxControlReg);

  Serial.print(F("[3] TxControlReg    = 0x"));
  Serial.print(apagada, HEX);
  Serial.print(F(" (apagada) -> 0x"));
  Serial.print(encendida, HEX);
  Serial.print(F(" (encendida)"));

  bool ok = (encendida & 0x03) == 0x03;
  Serial.println(ok ? F("   OK") : F("   !! LA ANTENA NO ENCIENDE"));

  byte gan = (lector.PCD_ReadRegister(MFRC522::RFCfgReg) >> 4) & 0x07;
  Serial.print(F("    ganancia de antena = "));
  Serial.print(gan);
  Serial.println(F(" (0-7; el sketch de estacion la sube al maximo)"));
  return ok;
}

// 4) Autotest de fábrica: el chip corre un CRC sobre su ROM y compara con la firma del
//    MFRC522 original.
//    ⚠️ EN NUESTRO HARDWARE ESTE TEST NO SIRVE COMO VEREDICTO. Verificado el 2026-08-11:
//    falla IGUAL en un módulo que no lee nada y en uno que lee perfecto — porque los packs
//    baratos traen clones (FM17522 y similares) cuya firma no coincide con la del original.
//    Se deja porque es información, no porque decida nada. NO cambiar un módulo por esto.
bool prueba_autotest() {
  bool ok = lector.PCD_PerformSelfTest();
  Serial.print(F("[4] autotest interno = "));
  Serial.println(ok ? F("PASA   OK") : F("FALLA   !! chip dañado"));
  lector.PCD_Init();          // el autotest deja el chip en un estado raro: reiniciarlo
  delay(50);
  return ok;
}
