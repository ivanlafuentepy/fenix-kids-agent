# firmware/leer_serial.py — captura el log serial de un ESP32 con timestamps.
#
# `arduino-cli monitor` no vuelca nada cuando se corre en background/redirigido en este
# entorno (queda con output vacío aunque el ESP32 esté imprimiendo) — este script con
# pyserial sí funciona para diagnosticar en vivo. Requiere pyserial (`py -3 -m pip install pyserial`,
# ya instalado en esta PC).
#
# Uso: py -3 firmware/leer_serial.py [puerto] [segundos]
#   py -3 firmware/leer_serial.py COM3 90

import serial
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 60

ser = serial.Serial(port, 115200, timeout=1)
end = time.time() + seconds
print(f"-- escuchando {port} por {seconds}s --", flush=True)
while time.time() < end:
    line = ser.readline()
    if line:
        try:
            text = line.decode("utf-8", errors="replace").rstrip()
        except Exception:
            text = repr(line)
        print(f"[{time.time():.2f}] {text}", flush=True)
ser.close()
print("-- fin --", flush=True)
