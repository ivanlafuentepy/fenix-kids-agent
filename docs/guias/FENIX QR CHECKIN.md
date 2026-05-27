up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# FENIX QR CHECK-IN — Guia de implementacion

> Sistema de asistencia por codigo QR para FENIX KIDS ACADEMY.
> Cada reserva tiene un QR unico. Padre lo muestra, Ivan lo escanea, asistencia marcada.
> Ultima actualizacion: 2026-05-25

---

## 1. Vision general

```
VIERNES (automatico):
  Recordatorio WhatsApp a todos los inscriptos
  "Mañana hay clase! A que hora van? 11:00 o 15:30?"
      |
  Padre responde hora
      |
  Codigo crea/actualiza RESERVA en Airtable
      |
  Se genera QR unico (campo formula en Airtable)
      |
  Se envia QR al padre por WhatsApp + email (Gmail automation)

SABADO (en el parque):
  Padre llega → muestra QR en celular
      |
  Ivan escanea con su celular (camara o lector QR)
      |
  Se abre pagina web: fenixkidsacademy.com/checkin/{record_id}
      |
  Pagina marca PRESENTE en Airtable automaticamente
      |
  Muestra: "✅ [Nombre hijo] — Presente a las [hora]"

SI CANCELA/REAGENDA:
  Reserva vieja se borra → QR viejo queda invalido
  Reserva nueva se crea → QR nuevo se genera y envia
```

---

## 2. Que se necesita

| Componente | Tecnologia | Costo | Estado |
|---|---|---|---|
| Campo QR en RESERVAS FENIX | Formula Airtable | Gratis | Por crear |
| Pagina check-in | Cloudflare Pages (fenixkidsacademy.com/checkin) | Gratis | Por crear |
| Endpoint API check-in | Railway (agent/main.py) | Ya pagado | Por crear |
| Envio QR por WhatsApp | Provider Meta existente | Ya pagado | Por crear |
| Envio QR por email | Airtable automation + Gmail | Gratis | Por crear |
| Lector QR | Camara del celular de Ivan | Gratis | Ya existe |

**Costo total adicional: $0**

---

## 3. Airtable — Campo QR en RESERVAS FENIX

### Opcion A: Campo formula (mas simple, gratis)

Crear campo `QR_URL` tipo Formula en RESERVAS FENIX:

```
"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=https://fenixkidsacademy.com/checkin/" & RECORD_ID()
```

Esto genera una URL que devuelve la imagen PNG del QR. El QR contiene la URL de check-in con el record_id unico.

**Ventaja:** automatico, sin dependencias externas.
**Desventaja:** depende de api.qrserver.com (servicio publico gratuito).

### Opcion B: Make.com (mas robusto)

Automation en Make.com:
1. Trigger: "When record created in RESERVAS FENIX"
2. Action: Generate QR code (modulo nativo de Make)
3. Action: Upload attachment to Airtable (campo QR_IMAGE)

**Ventaja:** QR guardado como imagen en Airtable, no depende de servicio externo.
**Desventaja:** limite 1000 operaciones/mes gratis.

### Opcion C: Python desde el agente (control total)

```python
import qrcode
from io import BytesIO

def generar_qr(record_id: str) -> bytes:
    url = f"https://fenixkidsacademy.com/checkin/{record_id}"
    qr = qrcode.make(url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return buf.getvalue()
```

Agregar `qrcode` a requirements.txt.

**Ventaja:** control total, sin dependencias externas, se puede enviar directo por WhatsApp.
**Desventaja:** hay que agregar libreria.

### Recomendacion: Opcion C (Python)

Porque ya tenemos `enviar_imagen_bytes` en el provider Meta. Generamos el QR en Python y lo enviamos directo por WhatsApp. Sin dependencias externas, sin limites.

---

## 4. Endpoint de check-in en Railway

Agregar a `agent/main.py`:

```python
@app.get("/checkin/{record_id}")
async def checkin(record_id: str):
    """Marca PRESENTE en Airtable al escanear QR."""
    # Buscar reserva
    reserva = await _get_record(_RESERVAS, record_id)
    if not reserva:
        return HTMLResponse("<h1>❌ Reserva no encontrada</h1>")
    
    fields = reserva.get("fields", {})
    nombre = fields.get("NOMBRE COMPLETO", ["?"])[0]
    hora = fields.get("HORA", ["?"])[0]
    
    # Verificar si ya esta presente
    if fields.get("PRESENTE"):
        return HTMLResponse(f"<h1>⚠️ {nombre} ya esta marcado como presente</h1>")
    
    # Marcar presente
    await _patch(_RESERVAS, record_id, {"PRESENTE": True})
    
    return HTMLResponse(f"""
        <h1>✅ {nombre}</h1>
        <p>Presente a las {hora}h</p>
        <p>¡Bienvenido al Parque Fenix! 🌳</p>
    """)
```

**Sin autenticacion** — el record_id es suficiente como token (es un hash unico de Airtable, no adivinable).

**Respuesta HTML** — se muestra directo en el celular al escanear.

---

## 5. Pagina web en Cloudflare Pages

Opcion simple: el endpoint de Railway ya devuelve HTML. No se necesita pagina separada.

Si queremos algo mas lindo:

```
fenixkidsacademy.com/checkin/{record_id}
  → fetch a Railway API
  → muestra resultado con branding FENIX
```

Pero para empezar, el endpoint directo de Railway alcanza.

---

## 6. Flujo del viernes (recordatorio + QR)

### Paso 1: Recordatorio automatico (ya existe en reminders.py)

Modificar `_recordatorio_viernes` para que pregunte hora:

```
"Hola [nombre]! Mañana hay clase en el Parque Fenix 🌳
¿A que hora van [hijos]?
11:00h | 15:30h"
```

### Paso 2: Padre responde hora

Codigo detecta respuesta (11, 15:30, etc.) → crea RESERVA en Airtable.

### Paso 3: Generar y enviar QR

```python
# Generar QR con record_id de la reserva
qr_bytes = generar_qr(record_id)

# Enviar por WhatsApp
await proveedor.enviar_imagen_bytes(telefono, qr_bytes, "image/png")
await proveedor.enviar_mensaje(telefono, 
    f"Reserva confirmada ✅\n"
    f"{hijos} — Sabado a las {hora}h\n\n"
    f"Mostra este codigo QR cuando llegues 📱"
)
```

### Paso 4: Email automatico (Airtable automation)

En Airtable → Automations:
- Trigger: "When record matches conditions" (RESERVAS FENIX, campo QR_URL no vacio)
- Action: "Send email" via Gmail
  - To: email del padre (lookup desde FAMILIAS)
  - Subject: "Tu reserva FENIX KIDS — Sabado {fecha} {hora}h"
  - Body: imagen QR + datos de la reserva

---

## 7. Flujo del sabado (check-in)

1. Padre llega al Parque Fenix
2. Muestra QR en su celular (WhatsApp o email)
3. Ivan abre camara del celular → escanea QR
4. Se abre el navegador con: `fenixkidsacademy.com/checkin/recXXXXXX`
5. Pantalla muestra: "✅ Luciana — Presente a las 11:00h"
6. En Airtable: PRESENTE = true automaticamente

### Si el QR es invalido (reserva cancelada/reagendada)
- Pantalla muestra: "❌ Reserva no encontrada"
- Ivan sabe que algo cambio y puede verificar

### Si ya escaneo antes
- Pantalla muestra: "⚠️ Luciana ya esta marcada como presente"
- Evita duplicados

---

## 8. Cancelacion y reagendamiento

### Cancelar
1. Padre dice "no vamos" → cancelar_reserva borra el registro
2. QR viejo → al escanear dice "Reserva no encontrada"
3. No se genera nuevo QR

### Reagendar
1. Padre dice "cambiamos a las 15:30" → reagendar_reserva cancela + crea nueva
2. QR viejo → invalido
3. QR nuevo → se genera y envia automaticamente
4. El padre recibe el nuevo QR por WhatsApp

---

## 9. Datos necesarios en Airtable

### RESERVAS FENIX — campos nuevos
| Campo | Tipo | Uso |
|---|---|---|
| QR_URL | Formula | URL de la imagen QR (para email) |
| PRESENTE | Checkbox | Marcado al escanear (ya existe) |
| HORA_CHECKIN | DateTime | Cuando se escaneo (para analytics) |

### FAMILIAS FENIX — campo necesario
| Campo | Tipo | Uso |
|---|---|---|
| EMAIL PADRE | Email | Para enviar QR por Gmail (ya existe) |
| EMAIL MADRE | Email | Backup (ya existe) |

---

## 10. Implementacion paso a paso

### Fase 1 — Backend (1 sesion)
1. Agregar `qrcode` a requirements.txt
2. Crear funcion `generar_qr(record_id)` en un modulo nuevo `agent/qr.py`
3. Crear endpoint GET `/checkin/{record_id}` en main.py
4. Testear: crear reserva manual → generar QR → escanear → verificar PRESENTE en Airtable

### Fase 2 — Integracion WhatsApp (1 sesion)
1. Modificar `agendar_clase` para que despues de crear reserva, genere y envie QR
2. Modificar `reagendar_reserva` para que envie nuevo QR
3. Modificar recordatorio viernes para que incluya flujo de confirmacion + QR
4. Testear flujo completo: viernes → confirmar → QR → sabado → escanear

### Fase 3 — Email (opcional, Airtable)
1. Crear campo formula QR_URL en RESERVAS FENIX
2. Crear automation en Airtable: nueva reserva → email Gmail con QR
3. Verificar que emails llegan

### Fase 4 — Pagina bonita (opcional)
1. Pagina en Cloudflare Pages con branding FENIX
2. Fetch a Railway API para check-in
3. Animacion de confirmacion

---

## 11. Beneficios

| Antes | Despues |
|---|---|
| "asis 11" + "ok" + marcar manual | Escanear QR y listo |
| Ivan tocando celular durante clase | 2 segundos por padre |
| "Yo confirme" sin registro | QR invalido = no confirmo |
| Sin evidencia de asistencia | Registro con hora exacta de check-in |
| Parece academia informal | Parece operacion profesional |

---

## 12. Dependencias

- `qrcode` (pip) — libreria Python para generar QR
- `Pillow` (pip) — ya instalado (dependencia de qrcode)
- Endpoint publico en Railway (ya existe)
- Camara del celular de Ivan (ya existe)

---

## 13. Estimacion

| Fase | Esfuerzo | Prioridad |
|---|---|---|
| Backend (qr.py + endpoint) | 1 hora | Alta |
| Integracion WhatsApp | 1 hora | Alta |
| Email Airtable | 30 min | Media |
| Pagina bonita | 1 hora | Baja |

**Total minimo viable: 2 horas de desarrollo.**

---

*Documento de referencia. Implementar en proxima sesion.*
