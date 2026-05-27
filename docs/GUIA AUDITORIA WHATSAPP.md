---
up: "[[MOC FENIX KIDS]]"
created: 2026-05-26
tags: [fenix, auditoria, guia, whatsapp, airtable]
---

# Guia Profesional: Auditor de Conversaciones WhatsApp + Airtable

## Que problema resuelve

Cuando un lead recibe datos bancarios por WhatsApp, hay un flujo esperado:

```
datos bancarios → pago → agenda → formulario → QR
```

Cada paso genera datos en Airtable (PRUEBA FENIX). Si algun paso falla silenciosamente, el lead queda en limbo: pago sin QR, reserva sin formulario, o datos incompletos.

Este auditor recorre **cada lead que recibio datos bancarios**, verifica que el flujo se completo, y que los datos en Airtable estan correctos.

---

## Arquitectura

```
┌─────────────────────────────┐
│  scripts/auditoria_flujo.py │
└─────────────┬───────────────┘
              │
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
┌────────┐      ┌──────────────┐
│Railway │      │   Airtable   │
│  API   │      │   REST API   │
└───┬────┘      └──────┬───────┘
    │                  │
    ▼                  ▼
conversacion/     PRUEBA FENIX
{telefono}        (67 registros)
    │                  │
    └──────┬───────────┘
           │
    ┌──────┴──────┐
    │  5 checks   │    ← flujo conversacional
    │  de flujo   │
    ├─────────────┤
    │  12 checks  │    ← campos Airtable
    │  de datos   │
    ├─────────────┤
    │  acciones   │    ← que hacer con cada lead
    │  sugeridas  │
    └──────┬──────┘
           │
    ┌──────┴──────┐
    │  Terminal   │    ← output formateado
    │  + JSON     │    ← para post-proceso
    └─────────────┘
```

---

## Como funciona paso a paso

### 1. Carga de datos

```python
# Fetch TODOS los registros de PRUEBA FENIX (paginado)
pruebas = await fetch_all_prueba_fenix()

# Para cada uno, fetch conversacion de produccion
mensajes = await fetch_conversacion(client, telefono)
```

### 2. Filtro: solo leads con datos bancarios

```python
# Solo auditar si el assistant envio "1604338" (alias bancario)
if not check_datos_bancarios(mensajes):
    continue
```

### 3. Checks modulares de flujo

Cada check es una funcion independiente que retorna `True/False`:

| Check | Que verifica | Como detecta |
|-------|-------------|--------------|
| `check_datos_bancarios()` | Se enviaron datos del banco | "1604338" en mensajes del assistant |
| `check_pago_confirmado()` | El padre pago y se confirmo | [imagen] del user + "pago confirmado" del assistant |
| `check_agenda()` | Tiene fecha/hora reservada | FECHA RESERVA y HORA no vacios ni "(por definir)" |
| `check_formulario()` | Completo sus datos | NOMBRE + APELLIDO + NOMBRE HIJO llenos |
| `check_qr()` | Se envio el QR | QR ENVIADO = true en Airtable |

### 4. Checks modulares de Airtable

Funcion `check_campos_airtable()` verifica 12 campos:

- NOMBRE, APELLIDO (padre)
- NOMBRE HIJO, APELLIDO HIJO
- FECHA NACIMIENTO
- FECHA RESERVA, HORA
- MONTO > 0, METODO DE PAGO
- QR ENVIADO, QR RESERVA
- LEAD vinculado

### 5. Categorizacion de acciones

Por cada lead, el script sugiere que hacer:

| Situacion | Accion |
|-----------|--------|
| Sin QR | `/enviar-qr/{telefono}` |
| Sin formulario | Pedir datos al padre |
| Sin pago | Verificar comprobante manualmente |
| Campos faltantes | Completar en Airtable |
| Todo OK | Sin accion requerida |

### 6. Output

**Terminal:**
```
595985175667 — Victor Meza (Joaquin)
  Flujo: OK | datos✅ pago✅ agenda✅ formulario✅ qr✅
  Airtable: OK | completo
  Accion: Sin accion requerida
```

**JSON:** guardado en `scripts/output/auditoria_FECHA.json`

---

## Como ejecutar

```bash
cd Projects/fenix-kids-agent
python scripts/auditoria_flujo.py
```

Requisitos:
- `.env` con AIRTABLE_API_KEY y ADMIN_API_KEY
- Acceso a internet (Railway + Airtable)
- Python 3.11+

---

## Como extender (agregar checks nuevos)

### Agregar un check de flujo

1. Crear funcion en la seccion "Checks modulares: FLUJO CONVERSACIONAL":

```python
def check_mi_nuevo_check(mensajes: list[dict]) -> bool:
    """Descripcion de que verifica."""
    return any(
        "patron" in m.get("texto", "")
        for m in mensajes
        if m.get("rol") == "assistant"
    )
```

2. Agregarlo al dict de flujo en `main()`:

```python
flujo = {
    "datos": True,
    "pago": check_pago_confirmado(mensajes),
    "agenda": check_agenda(record),
    "formulario": check_formulario(record),
    "qr": check_qr(record),
    "mi_check": check_mi_nuevo_check(mensajes),  # nuevo
}
```

3. Agregar accion correspondiente en `categorizar_acciones()`.

### Agregar un campo de Airtable

Agregar tupla a la lista correspondiente:

```python
CAMPOS_REQUERIDOS = [
    ...
    ("MI CAMPO", "Mi campo"),  # nuevo
]
```

---

## Patrones de diseno utilizados

Basados en investigacion de mejores practicas CRM (BSWEN, Salesforce, KDnuggets):

### 1. Funciones modulares
Cada validacion es una funcion aislada. Si una falla, no afecta las demas. Facil de agregar nuevas sin tocar las existentes.

### 2. Read-only first
El script SOLO lee y reporta. No modifica datos, no envia mensajes, no patchea Airtable. Las acciones se ejecutan manualmente despues de revisar el reporte.

### 3. Dos buckets de resultados
Cada lead cae en "OK" o "accion requerida" con detalle de que hacer. No es un dump de datos — es un reporte accionable.

### 4. Output dual (terminal + JSON)
Terminal para revision rapida. JSON para post-procesamiento (ej: dashboard, alertas, integracion con otros sistemas).

### 5. Categorizacion de acciones
No solo dice "falta X" — dice "hace Y para arreglar X". El usuario no necesita pensar que hacer.

---

## Referencia de campos Airtable auditados

### PRUEBA FENIX

| Campo | Tipo | Requerido | Descripcion |
|-------|------|-----------|-------------|
| TELEFONO | text | si | Numero del padre |
| NOMBRE | text | si | Nombre del padre |
| APELLIDO | text | si | Apellido del padre |
| NOMBRE HIJO | text | si | Nombre del hijo |
| APELLIDO HIJO | text | si | Apellido del hijo |
| FECHA NACIMIENTO | date | si | Fecha nacimiento hijo |
| FECHA RESERVA | text | si | Fecha de la clase (no "(por definir)") |
| HORA | select | si | Horario (9:30, 11:00, 15:30) |
| MONTO | number | si | Monto pagado (> 0) |
| METODO DE PAGO | select | si | TRANSFER, EFECTIVO, etc. |
| CONVERSION | select | si | PAGO, GRATIS, INSCRIPTO |
| QR ENVIADO | checkbox | si | Se envio QR al padre |
| QR RESERVA | url | si | URL del checkin QR |
| LEAD | link | si | Vinculado a LEADS FENIX |

---

## Resultados de la primera ejecucion (2026-05-26)

- 64 leads auditados
- 1 con flujo completo (2%) — el unico al que le arreglamos los datos hoy
- 63 sin QR — campo nuevo, historicos no lo tienen
- 3 sin pago confirmado en la conversacion
- 1 sin agenda definida

Esto demuestra que el QR nunca se estaba rastreando y que hay datos faltantes en Airtable que se pueden completar con el historial de conversacion.
