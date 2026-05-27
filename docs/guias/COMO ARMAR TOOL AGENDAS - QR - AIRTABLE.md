up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# Como armar Tool de Agendas + QR Check-in + Airtable

> Guia maestra para implementar un sistema de reservas por WhatsApp con Claude Tool Use, QR check-in y Airtable como backend. Escrita para que cualquier Claude (o desarrollador) pueda leer esto e implementar sin errores.
>
> Basada en la implementacion real de FENIX KIDS ACADEMY (mayo 2026). Incluye el codigo que funciona y TODOS los errores cometidos en el camino.

---

## Indice

1. [[#Seccion 1 — La solucion completa que funciona]]
   - [[#1.1 — Principio fundamental: UNA tool unificada]]
   - [[#1.2 — Definicion de la tool]]
   - [[#1.3 — Forzar tool_choice]]
   - [[#1.3.1 — Dos estrategias para forzar tool_choice]]
   - [[#1.3.2 — Flujo deterministico post-pago (leads)]]
   - [[#1.4 — La funcion de la tool (agenda.py)]]
   - [[#1.5 — El executor (tool_executor.py)]]
   - [[#1.6 — Inyeccion de datos Airtable en el mensaje]]
   - [[#1.7 — Airtable: tablas y campos]]
   - [[#1.8 — QR Check-in]]
   - [[#1.8.1 — QR para leads: momento correcto]]
   - [[#1.8.2 — gestionar_prueba (tool unificada para leads)]]
   - [[#1.9 — Flujo completo de punta a punta]]
2. [[#Seccion 2 — Bitacora de errores: todo lo que salio mal]]

---

# Seccion 1 — La solucion completa que funciona

## 1.1 — Principio fundamental: UNA tool unificada

La decision mas importante de toda la implementacion: **una sola tool `gestionar_reserva`** en vez de 3 tools separadas (`agendar_clase`, `reagendar_reserva`, `cancelar_reserva`).

**Por que una sola tool:**

1. **Haiku no tiene que elegir entre 3 tools** — con `tool_choice: auto` y 3 tools similares, Haiku se confunde y responde conversacionalmente sin ejecutar ninguna.
2. **Un parametro `accion` con enum es trivial** — `"agendar"`, `"reagendar"`, `"cancelar"`. Haiku entiende perfecto.
3. **Para reagendar, la tool busca la reserva actual sola** — el modelo NO necesita pasar `fecha_actual` + `hora_actual` + `fecha_nueva` + `hora_nueva` (4 parametros). Solo pasa la fecha y hora NUEVA. La tool consulta Airtable y encuentra la reserva vigente.
4. **Un solo `tool_choice` para forzar** — cuando detectas keywords de reserva, forzas `{"type": "tool", "name": "gestionar_reserva"}` y listo.

> **Regla de oro:** Si dos o mas tools operan sobre la misma entidad (reservas, pedidos, tickets), unificalas en UNA tool con un parametro `accion`. El modelo trabaja mejor asi.

---

## 1.2 — Definicion de la tool

Archivo: `agent/tool_definitions.py`

```python
TOOLS_AURORA = [
    {
        "name": "gestionar_reserva",
        "description": (
            "Gestiona reservas de clases para familias inscriptas. "
            "Acciones: agendar (crear reserva nueva), reagendar (cambiar fecha/hora), cancelar. "
            "Para reagendar, la tool busca la reserva actual en Airtable automaticamente. "
            "SIEMPRE usar esta tool cuando el padre quiere agendar, reagendar o cancelar. "
            "NUNCA responder sobre reservas sin usar esta tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["agendar", "reagendar", "cancelar"],
                    "description": "Que hacer: agendar (nueva), reagendar (cambiar existente), cancelar.",
                },
                "fecha": {
                    "type": "string",
                    "description": (
                        "Fecha del sabado (ISO o texto: '31 de mayo', '31/5', '6/6'). "
                        "Para reagendar es la fecha NUEVA."
                    ),
                },
                "hora": {
                    "type": "string",
                    "enum": ["11:00", "15:30"],
                    "description": "Hora del turno. Para reagendar es la hora NUEVA.",
                },
            },
            "required": ["accion"],
        },
    },
    # ... otras tools (escalar_a_humano, etc.)
]
```

**Notas clave de la definicion:**

- `accion` es **required**, `fecha` y `hora` no — asi la tool puede manejar casos como "cancelar" sin hora (cancela todas las del dia)
- Las `description` dicen explicitamente "Para reagendar es la fecha NUEVA" — esto evita que Haiku pase la fecha vieja
- "SIEMPRE usar esta tool" y "NUNCA responder sin usar esta tool" son instrucciones directas al modelo
- `enum` en `hora` restringe a los turnos validos — Haiku no puede inventar "14:00"

---

## 1.3 — Forzar tool_choice

Archivo: `agent/main.py` (dentro del handler del webhook)

```python
# Forzar gestionar_reserva cuando Aurora esta en flujo de reservas
_tool_choice_override = None
if agent_actual == "aurora":
    _texto_lower = texto.lower().strip()
    _es_reserva = any(k in _texto_lower for k in (
        "agendar", "reagendar", "cancelar", "cambiar",
        "11:00", "15:30", "11h", "15h", "/5", "/6", "/7",
    )) or (
        # Fecha + hora: "sab 30 11h", "6/6 15:30", etc.
        re.search(r'\d{1,2}[/\s]', _texto_lower)
        and re.search(r'1[15]', _texto_lower)
    )
    if _es_reserva:
        _tool_choice_override = {"type": "tool", "name": "gestionar_reserva"}
        logger.info(f"[AURORA] Forzando gestionar_reserva para: {texto[:50]}")
```

Luego se pasa a `generar_respuesta()`:

```python
respuesta, _tool_acciones = await generar_respuesta(
    mensaje=texto,
    historial=historial,
    agent_actual=agent_actual,
    contexto_extra=contexto_extra,
    reservas_airtable=_reservas_airtable,
    tools=_tools_lista,
    tool_executor=lambda n, p: ejecutar_tool(n, p, telefono),
    context={"telefono": telefono, "agent_actual": agent_actual},
    tool_choice=_tool_choice_override,  # <-- fuerza la tool
)
```

**Por que forzar:** Sin `tool_choice`, Haiku con `auto` decide por si mismo si usar la tool o no. En la practica, prefiere responder conversacionalmente ("Listo, reagendado!") sin ejecutar nada. El padre recibe confirmacion pero Airtable queda igual.

**Cuando forzar:** Solo cuando las keywords indican que el padre quiere hacer algo con reservas. Para mensajes normales ("hola", "a que hora es?"), se deja `tool_choice=None` (auto).

**El `tool_choice` solo se aplica en el round 0** — en rounds subsiguientes del tool-use loop, se deja auto para que Haiku pueda responder con texto despues de ejecutar la tool.

### 1.3.1 — Dos estrategias para forzar tool_choice

**Aurora (inscriptos):** Deteccion por keywords + historial. Funciona porque el flujo es simple: menu → opcion 1 → el padre ya esta en contexto de reservas.

**Ivan (leads):** Flag `modo_agenda` post-pago. NO usar keywords — el flujo conversacional de Ivan tiene demasiadas variantes. El flag se activa SOLO despues del pago confirmado, donde hay certeza absoluta de que el siguiente paso es agendar.

```python
# Ivan: flag de estado (certeza)
if agent_actual == "ivan":
    flags = await obtener_estado_flags(telefono)
    if flags.get("modo_agenda"):
        tool_choice = {"type": "tool", "name": "gestionar_prueba"}

# Aurora: keywords + historial (heuristica)  
elif agent_actual == "aurora":
    if _keywords_reserva or _responde_horario:
        tool_choice = {"type": "tool", "name": "gestionar_reserva"}
```

**Regla:** Keywords funcionan cuando el flujo es corto y el contexto es claro. Para flujos conversacionales largos (ventas, leads), usar flags de estado que se activan en momentos de certeza.

### 1.3.2 — Flujo deterministico post-pago (leads)

El padre ya pago. Cero ambiguedad. El sistema toma control:

```
Pago confirmado
  → Mensaje fijo (sin Claude): "¡Pago recibido! ¿Que sabado te viene mejor?"
  → Lista de horarios disponibles de Airtable
  → modo_agenda = True
  → Padre elige fecha+hora
  → tool forzada → gestionar_prueba(confirmar)
  → Formulario de datos
  → PRUEBA FENIX creada
  → QR enviado
```

Codigo del mensaje post-pago:
```python
async def _armar_mensaje_agenda_post_pago() -> str:
    horarios = await obtener_horarios_disponibles(max_horarios=8)
    # agrupar por fecha, armar mensaje con sabados disponibles
    return f"¡Pago recibido ✅ Gracias!\n\nAhora agendamos tu clase de prueba 🌳\n\n📅 Sabados disponibles:\n{sabados_txt}\n\n¿Que dia y horario te viene mejor?"
```

**Importante:** El prompt de Ivan debe reflejar este flujo. Si el prompt dice "ofrecer horarios antes de cobrar", el agente va a ofrecer horarios antes de cobrar, sin importar que el codigo tenga modo_agenda. El prompt es la instruccion del agente.

---

## 1.4 — La funcion de la tool (agenda.py)

Archivo: `agent/tools/agenda.py`

```python
async def gestionar_reserva(
    telefono: str,
    accion: str,
    fecha: str | None = None,
    hora: str | None = None,
    familia_id: str | None = None,
) -> dict:
    """
    Tool unificada para agendar, reagendar y cancelar reservas.
    - agendar: crea reserva nueva para todos los hijos
    - reagendar: busca reserva actual en Airtable, cancela, crea nueva
    - cancelar: cancela reservas de la fecha/hora indicada
    """
    accion = accion.lower().strip()

    if accion not in ("agendar", "reagendar", "cancelar"):
        return {
            "error": True,
            "error_category": "validation",
            "is_retryable": False,
            "message": f"Accion '{accion}' no valida. Usar: agendar, reagendar, cancelar.",
        }

    # Resolver familia si no viene
    if not familia_id:
        fam = await buscar_familia_por_telefono(telefono)
        if fam:
            familia_id = fam["id"]
    if not familia_id:
        return {
            "error": True,
            "error_category": "business",
            "is_retryable": False,
            "message": "No encontre una familia registrada para este numero.",
        }

    if accion == "agendar":
        return await _agendar(telefono, fecha, hora, familia_id)
    elif accion == "reagendar":
        return await _reagendar(telefono, fecha, hora, familia_id)
    elif accion == "cancelar":
        return await _cancelar(telefono, fecha, hora, familia_id)
```

### _agendar() — Crear reserva para TODOS los hijos

```python
async def _agendar(telefono: str, fecha: str, hora: str, familia_id: str) -> dict:
    if not fecha or not hora:
        return {"error": True, "error_category": "validation",
                "is_retryable": True, "message": "Necesito fecha y hora para agendar."}

    # Obtener TODOS los hijos de la familia
    ninos = await obtener_ninos_de_familia(familia_id)
    if not ninos:
        return {"error": True, "error_category": "business",
                "is_retryable": False, "message": "La familia no tiene hijos registrados."}

    # Obtener o crear el HORARIO en Airtable
    horario_id = await obtener_o_crear_horario(fecha, hora)
    if not horario_id:
        return {"error": True, "error_category": "transient",
                "is_retryable": True, "message": f"No pude crear el horario {fecha} {hora}."}

    # Crear UNA reserva por cada hijo
    reservados = []
    reserva_ids = []
    for nino in ninos:
        rid = await crear_reserva(nino["id"], horario_id, familia_id)
        if rid:
            reservados.append(nino.get("nombre_completo") or nino.get("nombre") or "?")
            reserva_ids.append(rid)

    if not reservados:
        return {"error": True, "error_category": "transient",
                "is_retryable": True, "message": "No pude crear las reservas."}

    return {
        "texto": f"Reserva confirmada para {' y '.join(reservados)} el sabado {fecha} a las {hora}h.",
        "agendada": True,
        "fecha": fecha,
        "hora": hora,
        "hijos": " y ".join(reservados),
        "cantidad": len(reservados),
        "reserva_ids": reserva_ids,  # <-- para generar QRs
    }
```

**Puntos clave:**
- Siempre crea reserva para TODOS los hijos, no solo uno
- `reserva_ids` se retorna para que el caller genere QR por cada hijo
- `crear_reserva()` tiene deduplicacion interna — si ya existe una reserva para ese nino en ese horario, retorna el existente sin crear duplicado

### _reagendar() — Buscar reserva actual + cancelar + crear nueva

```python
async def _reagendar(telefono: str, fecha_nueva: str, hora_nueva: str, familia_id: str) -> dict:
    if not fecha_nueva or not hora_nueva:
        return {"error": True, "error_category": "validation",
                "is_retryable": True, "message": "Necesito la nueva fecha y hora para reagendar."}

    # 1. Buscar nombre de la familia (lookup texto, NO record link)
    fam_record = await _get_records(
        "FAMILIAS FENIX", formula=f"RECORD_ID()='{familia_id}'", max_records=1
    )
    nombre_familia = fam_record[0].get("fields", {}).get("FAMILIA", "")

    # 2. Buscar reservas por nombre de familia (ARRAYJOIN de lookup texto)
    reservas = await _get_records(
        _RESERVAS,
        formula=f"FIND('{nombre_familia}', ARRAYJOIN({{FAMILIA}}))",
        max_records=50,
    )

    # 3. Filtrar solo reservas futuras
    _hoy = datetime.now(ZoneInfo("America/Asuncion")).date()
    reservas_futuras = []
    for r in reservas:
        f = r.get("fields", {})
        _fecha = f.get("FECHA", "")
        if isinstance(_fecha, list):
            _fecha = _fecha[0] if _fecha else ""
        if _fecha >= _hoy.isoformat():
            _hora = f.get("HORA", "")
            if isinstance(_hora, list):
                _hora = _hora[0] if _hora else ""
            reservas_futuras.append({"id": r["id"], "fecha": _fecha, "hora": _hora})

    if not reservas_futuras:
        return {"error": True, "error_category": "business",
                "is_retryable": False,
                "message": "No hay reservas activas para reagendar. Usar agendar en su lugar."}

    # 4. Borrar todas las reservas actuales
    fecha_actual = reservas_futuras[0]["fecha"]
    hora_actual = reservas_futuras[0]["hora"]
    for r in reservas_futuras:
        await _delete(_RESERVAS, r["id"])

    # 5. Crear reserva nueva
    result = await _agendar(telefono, fecha_nueva, hora_nueva, familia_id)
    if result.get("error"):
        return result

    return {
        "texto": f"Reserva reagendada para {result['hijos']}: "
                 f"del {fecha_actual} {hora_actual}h al {fecha_nueva} {hora_nueva}h.",
        "reagendada": True,
        "agendada": True,
        "fecha": fecha_nueva,
        "hora": hora_nueva,
        "hijos": result.get("hijos", "?"),
        "reserva_ids": result.get("reserva_ids", []),  # <-- QRs nuevos
        "enviar_admin": True,
        "mensaje_admin": (
            f"REAGENDAMIENTO\n"
            f"{result['hijos']}: {fecha_actual} {hora_actual} -> {fecha_nueva} {hora_nueva}\n"
            f"tel: https://wa.me/{telefono}"
        ),
    }
```

**Lo critico de _reagendar():**
- La tool BUSCA la reserva actual sola — Haiku solo pasa la fecha/hora nueva
- Busca por NOMBRE DE FAMILIA (texto lookup), NO por record_id del link
- Filtra reservas futuras comparando con `_hoy.isoformat()`
- Borra las reservas viejas y crea nuevas — los QR viejos quedan invalidados automaticamente (record borrado = QR 404)

### _cancelar() — Eliminar reservas

```python
async def _cancelar(telefono: str, fecha: str, hora: str | None, familia_id: str) -> dict:
    if not fecha:
        return {"error": True, "error_category": "validation",
                "is_retryable": True, "message": "Necesito la fecha para cancelar."}

    borradas = await cancelar_reservas_familia_fecha(familia_id, fecha, hora or "")
    if borradas == 0:
        return {"texto": f"No encontre reservas para cancelar el {fecha}.", "cancelada": False}

    return {
        "texto": f"Cancele {borradas} reserva(s) del sabado {fecha}.",
        "cancelada": True,
        "cantidad_borradas": borradas,
    }
```

---

## 1.5 — El executor (tool_executor.py)

Archivo: `agent/tool_executor.py`

El executor es el puente entre Claude API (que retorna `tool_use` blocks) y las funciones Python reales.

```python
# Registro de tools
_TOOLS = {
    "gestionar_reserva": gestionar_reserva,
    "escalar_a_humano": escalar_a_humano,
    # ...
}

# Tools que necesitan familia_id auto-resuelto
_TOOLS_CON_FAMILIA = {"gestionar_reserva"}
```

**Resolucion automatica de `familia_id`:**

```python
async def ejecutar_tool(nombre: str, params: dict, telefono: str) -> dict:
    fn = _TOOLS.get(nombre)
    if not fn:
        return {"error": True, "message": f"Tool '{nombre}' no existe."}

    # Inyectar telefono
    params["telefono"] = telefono

    # Resolver familia_id automaticamente para tools que lo necesitan
    if nombre in _TOOLS_CON_FAMILIA and "familia_id" not in params:
        fam_id = await obtener_familia_id(telefono)
        if not fam_id:
            fam = await buscar_familia_por_telefono(telefono)
            if fam:
                fam_id = fam["id"]
        params["familia_id"] = fam_id  # puede ser None, la tool maneja el error

    resultado = await fn(**params)
    return resultado
```

**Por que el executor resuelve `familia_id`:**
- Haiku NO conoce el `familia_id` (es un record_id de Airtable)
- El executor lo busca por telefono antes de llamar a la tool
- La tool puede manejar `familia_id=None` y retornar error amigable

**Errores estructurados:**

Todas las tools retornan errores con este formato:
```python
{
    "error": True,
    "error_category": "transient" | "validation" | "business",
    "is_retryable": bool,
    "message": str,
}
```

Esto permite que el executor (y Claude en el tool-use loop) sepa si debe reintentar o informar al usuario.

---

## 1.6 — Inyeccion de datos Airtable en el mensaje

**Problema resuelto:** Haiku ignora datos del system prompt cuando el historial contradice esos datos. Si el historial tiene 20 mensajes mencionando "reserva el 30 de mayo a las 15:30", pero la reserva fue cancelada en Airtable, Haiku responde como si la reserva existiera.

**Solucion:** Inyectar los datos de Airtable EN EL MENSAJE DEL USUARIO (ultima posicion = maxima prioridad para el modelo).

En `brain.py`:

```python
# Reservas de Airtable van en el mensaje del usuario (maxima prioridad para Haiku)
if reservas_airtable:
    mensajes.append({
        "role": "user",
        "content": (
            f"[DATOS AIRTABLE EN TIEMPO REAL]\n"
            f"{reservas_airtable}\n\n"
            f"Mensaje del padre: {mensaje}"
        ),
    })
else:
    mensajes.append({"role": "user", "content": mensaje})
```

En `main.py`, la funcion `_build_contexto_aurora()` arma el texto de reservas:

```python
# Buscar reservas por nombre de familia (texto lookup)
_nombre_familia = campos.get("FAMILIA", "")
_formula = f"FIND('{_nombre_familia}', ARRAYJOIN({{FAMILIA}}))"
_reservas_raw = await _get_records(_RESERVAS, formula=_formula, max_records=50)

# Filtrar solo futuras
reservas_futuras = []
for _rr in _reservas_raw:
    _rf = _rr.get("fields", {})
    _fecha = _rf.get("FECHA", "")
    if isinstance(_fecha, list):
        _fecha = _fecha[0] if _fecha else ""
    if _fecha >= _hoy_str:
        reservas_futuras.append(...)

# Armar texto
if reservas_futuras:
    _reservas_texto = "RESERVAS ACTIVAS DE ESTA FAMILIA:\n"
    for r in sorted(reservas_futuras, key=lambda x: x.get("fecha", "")):
        _reservas_texto += f"  {nombre_nino}: Sabado {dia}/{mes} a las {hora}h\n"
else:
    _reservas_texto = "RESERVAS ACTIVAS: ninguna"
```

La funcion retorna DOS valores: `contexto_extra` (va al system prompt) y `_reservas_airtable` (va al user message).

---

## 1.7 — Airtable: tablas y campos

### Tabla: RESERVAS FENIX

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| NINO | Link a NINOS FENIX | El nino reservado (1 reserva = 1 nino) |
| HORARIO | Link a HORARIOS FENIX | Fecha + hora del turno |
| FAMILIAS | Link a FAMILIAS FENIX | La familia (para filtrar) |
| PRESENTE | Checkbox | Se marca al escanear QR |
| HORA_CHECKIN | DateTime | Hora exacta del check-in |
| NOMBRE COMPLETO | Lookup de NINOS | Texto del nombre (para display) |
| FECHA | Lookup de HORARIOS | Fecha del turno (texto) |
| HORA | Lookup de HORARIOS | Hora del turno (texto) |
| FAMILIA | Lookup de FAMILIAS | Nombre de la familia (texto) |

### Tabla: HORARIOS FENIX

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| FECHA | Date | Fecha del sabado |
| HORA | Single line text | "11:00" o "15:30" |
| RESERVAS FENIX | Link a RESERVAS FENIX | Reservas vinculadas (backlink) |

### Tabla: FAMILIAS FENIX

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| FAMILIA | Formula/Text | "FAMILIA Lafuente", autogenerado |
| CELL PADRE / CELL MADRE | Phone | Telefonos |
| NINOS FENIX | Link a NINOS FENIX | Hijos registrados |

### Reglas criticas de Airtable

**1. NUNCA usar ARRAYJOIN con multipleRecordLinks**
```
MAL:  FIND('recCDd7tDQavIdgOy', ARRAYJOIN({FAMILIAS}))     -- 0 resultados
MAL:  {FAMILIAS}='recCDd7tDQavIdgOy'                         -- 0 resultados
MAL:  FIND(record_id, ARRAYJOIN({NINO}, ','))                 -- 0 resultados

BIEN: FIND('FAMILIA Lafuente', ARRAYJOIN({FAMILIA}))          -- FAMILIA es lookup texto
```

`ARRAYJOIN` no funciona con campos de tipo `multipleRecordLinks`. Solo funciona con campos de tipo texto (lookup values, formula, single line text).

**2. IS_AFTER no incluye hoy**
```
MAL:  IS_AFTER({FECHA}, '2026-05-25')    -- NO incluye el 25 de mayo
BIEN: IS_AFTER({FECHA}, '2026-05-24')    -- Usar ayer para incluir hoy
```

`IS_AFTER` es estrictamente "despues de", no "en o despues de". Para incluir hoy, usar la fecha de AYER.

**3. Campos lookup retornan listas**

Los campos lookup de Airtable retornan `list` aunque haya un solo valor:
```python
fecha = fields.get("FECHA", "")
if isinstance(fecha, list):
    fecha = fecha[0] if fecha else ""
```

SIEMPRE verificar si es lista antes de usar.

**4. Deduplicacion en crear_reserva()**

```python
async def crear_reserva(nino_id, horario_id, familia_id):
    # Verificar si ya existe
    formula = f"AND(FIND('{nino_id}', ARRAYJOIN({{NINO}})), FIND('{horario_id}', ARRAYJOIN({{HORARIO}})))"
    existentes = await _get_records(_RESERVAS, formula=formula, max_records=1)
    if existentes:
        return existentes[0]["id"]  # retorna existente, no duplica
    # Crear nueva...
```

---

## 1.8 — QR Check-in

### Generacion del QR (agent/qr.py)

```python
import qrcode
from PIL import Image
from io import BytesIO

_LOGO_PATH = "marketing/logos/LOGO FENIX TRANSPARENTE OFICIAL.png"
_CHECKIN_BASE = os.getenv("CHECKIN_BASE_URL", "https://tu-app.up.railway.app")


def generar_qr(record_id: str) -> bytes:
    """Genera QR con logo en el centro. Apunta a /checkin/{record_id}."""
    url = f"{_CHECKIN_BASE}/checkin/{record_id}"

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # 30% de cobertura permitida
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    # Pegar logo en el centro
    if os.path.exists(_LOGO_PATH):
        logo = Image.open(_LOGO_PATH).convert("RGBA")
        logo_size = img.size[0] // 4  # 25% del QR
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

        pos_x = (img.size[0] - logo_size) // 2
        pos_y = (img.size[1] - logo_size) // 2

        # Fondo blanco detras del logo para mejor lectura
        bg = Image.new("RGBA", (logo_size + 10, logo_size + 10), "white")
        img.paste(bg, (pos_x - 5, pos_y - 5))
        img.paste(logo, (pos_x, pos_y), logo)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

**Notas:**
- `ERROR_CORRECT_H` permite que hasta el 30% del QR este cubierto (por el logo) y siga siendo escaneable
- El logo ocupa ~25% del area — dentro del margen seguro
- Retorna `bytes` PNG — se envia directo por WhatsApp sin guardar archivo

### Dependencias necesarias

```
qrcode[pil]>=7.4
Pillow>=10.0
```

### Envio del QR despues de confirmar reserva (main.py)

```python
# Despues de que la tool retorna, procesar acciones
for _ta in _tool_acciones:
    _ta_result = _ta["result"]

    # QR Check-in: enviar QR al padre cuando se confirma/reagenda
    _reserva_ids = _ta_result.get("reserva_ids", [])
    if _reserva_ids and (_ta_result.get("agendada") or _ta_result.get("reagendada")):
        from agent.qr import generar_qr
        for _rid in _reserva_ids:
            _qr_bytes = generar_qr(_rid)
            await proveedor.enviar_imagen_bytes(
                telefono, _qr_bytes, "image/png",
                caption="Mostra este QR cuando llegues a Fenix Kids Academy"
            )
```

**Un QR por cada hijo** — si la familia tiene 2 hijos, se envian 2 QRs (uno por reserva, cada uno con su `record_id`).

### Endpoint de check-in (main.py)

```python
@app.get("/checkin/{record_id}")
async def checkin(record_id: str):
    """Marca PRESENTE en Airtable al escanear QR."""

    # Buscar reserva
    formula = f"RECORD_ID()='{record_id}'"
    records = await _get_records(_RESERVAS, formula=formula, max_records=1)

    if not records:
        return HTMLResponse(
            "<h1>Reserva no encontrada</h1>"
            "<p>Este QR ya no es valido. La reserva fue cancelada o reagendada.</p>",
            status_code=404,
        )

    reserva = records[0]
    fields = reserva.get("fields", {})
    nombre = fields.get("NOMBRE COMPLETO", ["Alumno"])[0]

    # Si ya esta presente
    if fields.get("PRESENTE"):
        return HTMLResponse(f"<h1>{nombre}</h1><p>Ya esta marcado como presente</p>")

    # Marcar presente + hora
    ahora = datetime.now(ZoneInfo("America/Asuncion"))
    await _patch(_RESERVAS, record_id, {
        "PRESENTE": True,
        "HORA_CHECKIN": ahora.isoformat(),
    })

    return HTMLResponse(
        f"<h1>{nombre}</h1>"
        f"<p>Presente — Check-in: {ahora.strftime('%H:%M')}</p>"
        f"<p>Bienvenido a Fenix Kids Academy!</p>"
    )
```

**Seguridad implícita:**
- Si la reserva fue cancelada/reagendada, el `record_id` no existe mas → 404
- Si ya se escaneo, muestra "ya esta presente" → no se marca doble
- No requiere autenticacion porque el `record_id` de Airtable es suficientemente aleatorio y el peor caso es marcar presente a alguien que ya fue

### Logo en produccion

El logo DEBE estar en el repo para que Railway lo tenga:

```gitignore
# .gitignore
marketing/*
!marketing/logos/
!marketing/logos/LOGO FENIX TRANSPARENTE OFICIAL.png
```

Sin esta excepcion, el logo existe en local pero no en Railway. El QR se genera sin logo en produccion.

### 1.8.1 — QR para leads: momento correcto

Para leads, el QR NO se envia cuando la tool confirma la agenda (el registro PRUEBA FENIX aun no existe). Se envia DESPUES del formulario, cuando el registro ya se creo:

```python
# En el bloque post-formulario (despues de crear_prueba_fenix)
from agent.qr import generar_qr
pruebas = await _get_records(_PRUEBAS, formula=f"{{TELEFONO}}='{telefono}'", max_records=10)
for pq in pruebas:
    qr_bytes = generar_qr(pq["id"])
    await proveedor.enviar_imagen_bytes(telefono, qr_bytes, "image/png",
        caption="Mostra este QR cuando llegues a Fenix Kids Academy 📱")
```

**Diferencia clave Aurora vs Ivan:**
- **Aurora (inscriptos):** QR se envia inmediatamente despues de `gestionar_reserva` → el registro RESERVAS FENIX se crea en la tool → QR apunta al record_id de la reserva.
- **Ivan (leads):** QR se envia despues del formulario de datos → el registro PRUEBA FENIX se crea con los datos del formulario → QR apunta al record_id de la prueba.

**Por que:** La tool `gestionar_prueba` confirma la fecha/hora, pero el registro en PRUEBA FENIX se crea DESPUES cuando el padre manda los datos (nombre, fecha nacimiento). Si intentas enviar QR en el momento de la tool, el record_id no existe todavia → error.

---

## 1.8.2 — gestionar_prueba (tool unificada para leads)

Mismo patron que `gestionar_reserva` de Aurora, pero para leads:

```python
TOOLS_IVAN_AGENDA = [
    {
        "name": "gestionar_prueba",
        "description": "Gestiona reservas de clases de prueba para leads. Acciones: confirmar, reagendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "accion": {"type": "string", "enum": ["confirmar", "reagendar"]},
                "fecha": {"type": "string"},
                "hora": {"type": "string", "enum": ["11:00", "15:30"]},
            },
            "required": ["accion"],
        },
    },
]
```

**Diferencias con gestionar_reserva:**
- Solo 2 acciones: `confirmar` y `reagendar` (no `cancelar` — un lead que cancela simplemente no viene)
- No necesita `familia_id` — los leads no tienen familia registrada todavia
- Se fuerza SOLO con flag `modo_agenda`, nunca con keywords

---

## 1.9 — Flujo completo de punta a punta

```
1. Padre escribe: "Agendar sab 31 a las 11h"
          |
2. main.py detecta keywords de reserva ("agendar", "11h")
          |
3. _tool_choice_override = {"type": "tool", "name": "gestionar_reserva"}
          |
4. _build_contexto_aurora() consulta Airtable:
   - Busca la familia por telefono
   - Lista hijos: "Sofia" y "Mateo"
   - Lista reservas activas: "ninguna"
   - Retorna contexto_extra (system) + _reservas_airtable (user msg)
          |
5. generar_respuesta() llama a Claude API con:
   - system prompt + contexto_extra (datos de la familia)
   - historial de conversacion
   - user message: "[DATOS AIRTABLE] RESERVAS ACTIVAS: ninguna
                    Mensaje del padre: Agendar sab 31 a las 11h"
   - tools: [gestionar_reserva, escalar_a_humano]
   - tool_choice: {"type": "tool", "name": "gestionar_reserva"}
          |
6. Haiku responde con tool_use:
   gestionar_reserva(accion="agendar", fecha="31/5", hora="11:00")
          |
7. tool_executor resuelve familia_id por telefono
          |
8. gestionar_reserva() ejecuta _agendar():
   - obtener_ninos_de_familia() → [Sofia, Mateo]
   - obtener_o_crear_horario("2026-05-31", "11:00") → horario_id
   - crear_reserva(sofia_id, horario_id, familia_id) → reserva_id_1
   - crear_reserva(mateo_id, horario_id, familia_id) → reserva_id_2
   - Retorna {agendada: True, reserva_ids: [id1, id2], ...}
          |
9. brain.py recibe tool_result, le pasa a Haiku para respuesta final
          |
10. Haiku genera: "Listo! Sofia y Mateo estan agendados para
    el sabado 31 de mayo a las 11:00h. Te mando los QR!"
          |
11. main.py procesa tool_acciones:
    - Ve reserva_ids + agendada=True
    - generar_qr(reserva_id_1) → qr_bytes_1
    - generar_qr(reserva_id_2) → qr_bytes_2
    - enviar_imagen_bytes(telefono, qr_bytes_1)
    - enviar_imagen_bytes(telefono, qr_bytes_2)
          |
12. Padre recibe: mensaje de confirmacion + 2 QRs
          |
--- DIA DEL EVENTO ---
          |
13. Padre llega, muestra QR en su celular
14. Ivan escanea con la camara del celular
15. Se abre: https://tu-app.railway.app/checkin/recXXXXXXXXXX
16. Endpoint marca PRESENTE=true, HORA_CHECKIN=hora actual
17. Pantalla muestra: "Sofia - Presente - Check-in: 10:45"
```

---

# Seccion 2 — Bitacora de errores: todo lo que salio mal

> Esta seccion es un registro cronologico de TODOS los errores cometidos durante la implementacion. Para cada error: que se intento, por que se intento, por que fallo, cual fue la solucion correcta, y la leccion para futuras implementaciones.
>
> Leer esto ANTES de implementar. Cada error costo tiempo real.

---

## Error 1: Tres tools separadas en vez de una

**Que se intento:**
Se crearon 3 tools separadas: `agendar_clase`, `cancelar_reserva`, `reagendar_reserva`. Cada una con su propio schema, su propia funcion, sus propios parametros.

**Por que se intento:**
Parecia logico — cada accion es diferente, cada una tiene parametros distintos. La separacion de responsabilidades es buena practica en programacion.

**Por que fallo:**
- Con `tool_choice: auto` y 3 tools parecidas, Haiku decidia NO usar ninguna tool
- Respondia conversacionalmente: "Listo, reagendada!" sin ejecutar nada
- Los logs mostraban: `[TOOL-USE] 595982844548: 0 tools, interceptado=False`
- Cero escrituras en Airtable. El padre recibia confirmacion de algo que no paso
- `reagendar_reserva` requeria 4 parametros obligatorios: `fecha_actual`, `hora_actual`, `fecha_nueva`, `hora_nueva` — demasiado complejo para que Haiku los extraiga todos correctamente del texto del padre

**La solucion correcta:**
Una sola tool `gestionar_reserva` con parametro `accion` (enum: agendar, reagendar, cancelar). Para reagendar, solo pasar fecha/hora NUEVA — la tool busca la reserva actual sola en Airtable.

**Leccion:**
No separar acciones relacionadas en multiples tools. Una tool unificada con un parametro `accion` es mas simple para el modelo. Menos tools = menos decisiones = menos errores. El modelo es bueno extrayendo 2-3 parametros, no 4-5.

---

## Error 2: No forzar tool_choice

**Que se intento:**
Se dejaba `tool_choice` en su valor por defecto (`auto`), confiando en que Haiku elegiria la tool correcta basandose en la descripcion.

**Por que se intento:**
La documentacion de Anthropic dice que `auto` funciona bien en la mayoria de casos. Las descripciones de las tools eran claras y explicitas.

**Por que fallo:**
- Haiku, con `auto`, a menudo decidia que podia responder sin tool
- Decia "Reagendada!" o "Ya te agendamos para el sabado" pero en los logs: 0 tools ejecutados
- El padre recibia un mensaje de confirmacion bonito. Airtable seguia exactamente igual
- Esto es PELIGROSO — el usuario cree que la accion se ejecuto cuando no fue asi

**La solucion correcta:**
Detectar keywords de reserva en el mensaje del padre (agendar, reagendar, cancelar, patrones de fecha/hora) y forzar:
```python
tool_choice = {"type": "tool", "name": "gestionar_reserva"}
```

Solo forzar en el round 0 del tool-use loop — en rounds subsiguientes dejar `auto` para que Haiku pueda responder con texto despues de ejecutar.

**Leccion:**
Para acciones de negocio criticas (que modifican datos), NUNCA confiar en `tool_choice: auto`. Forzar la tool cuando el contexto indica que el usuario quiere ejecutar esa accion. El modelo no tiene incentivo para usar tools — su instinto es responder conversacionalmente.

---

## Error 3: Datos de reservas en system prompt ignorados por Haiku

**Que se intento:**
Los datos de Airtable (reservas activas de la familia) se inyectaban en el system prompt:
```
RESERVAS ACTIVAS: ninguna
```

**Por que se intento:**
El system prompt parece el lugar logico para poner contexto del negocio. Es donde van las reglas, la personalidad, la informacion de referencia.

**Por que fallo:**
- El historial de conversacion tenia 20+ mensajes mencionando "reserva para el sabado 30 a las 15:30"
- Haiku priorizaba el historial (que menciona la reserva existente) sobre el system prompt (que dice "ninguna")
- Cuando la reserva fue cancelada en Airtable, Haiku seguia diciendo "tu reserva es el sabado 30 a las 15:30"

**Intentos fallidos antes de la solucion:**
1. Agregar "REGLA CRITICA: la UNICA fuente de verdad para reservas son los datos de Airtable arriba" — no funciono, Haiku lo ignoro
2. Parsear strings en brain.py para separar reservas del contexto — fragil, feo, rompia con cualquier cambio
3. Pasar como parametro separado — direccion correcta pero implementacion compleja

**La solucion correcta:**
Inyectar los datos de Airtable en el MENSAJE DEL USUARIO (ultima posicion en la lista de mensajes):
```python
{
    "role": "user",
    "content": "[DATOS AIRTABLE EN TIEMPO REAL]\n"
               "RESERVAS ACTIVAS: ninguna\n\n"
               "Mensaje del padre: quiero reagendar"
}
```

El ultimo mensaje de la lista tiene la maxima prioridad para el modelo. Al estar ahi, los datos reales de Airtable superan al historial.

**Leccion:**
Para datos en tiempo real que pueden contradecir el historial de conversacion, ponerlos en el user message, no en el system prompt. El system prompt es para reglas inmutables. Los datos que cambian van en el mensaje mas reciente. Cambiar DONDE pones la data es mas efectivo que agregar mas instrucciones ("REGLA CRITICA", "FUENTE DE VERDAD", etc.).

---

## Error 4: ARRAYJOIN no funciona con multipleRecordLinks

**Que se intento:**
Buscar reservas por `familia_id` usando:
```
FIND('recCDd7tDQavIdgOy', ARRAYJOIN({FAMILIAS}))
```

**Por que se intento:**
`FAMILIAS` es un campo de tipo link en la tabla RESERVAS. ARRAYJOIN deberia concatenar los valores. FIND deberia encontrar el record_id dentro.

**Por que fallo:**
`ARRAYJOIN` con campos `multipleRecordLinks` retorna... nada util. No es un bug, es una limitacion de Airtable que no esta bien documentada. El campo contiene record_ids internos que ARRAYJOIN no sabe como serializar.

**Intentos fallidos (6+ formulas probadas a mano):**
1. `FIND('recCDd7tDQavIdgOy', ARRAYJOIN({FAMILIAS}))` → 0 resultados
2. `ARRAYJOIN({FAMILIAS}, ',')` → 0 resultados
3. `{FAMILIAS}='recCDd7tDQavIdgOy'` → 0 resultados
4. `FIND(record_id, ARRAYJOIN({NINO}, ','))` → 0 resultados
5. `SEARCH(record_id, {FAMILIAS})` → 0 resultados
6. Variaciones con comillas, sin comillas → 0 resultados

Cada intento requeria una llamada API a Airtable, esperar respuesta, ver 0 resultados, y probar la siguiente. Total: ~30 minutos perdidos.

**La solucion correcta:**
Usar campos de tipo lookup (texto, no record link):
```
FIND('FAMILIA Lafuente', ARRAYJOIN({FAMILIA}))
```

`FAMILIA` (sin S) es un campo de tipo `multipleLookupValues` que contiene el texto "FAMILIA Lafuente" — un string que ARRAYJOIN sabe manejar perfectamente.

**Leccion:**
1. NUNCA usar ARRAYJOIN con campos de tipo `multipleRecordLinks` — no funciona
2. Crear campos lookup de texto para los datos que necesitas filtrar
3. BUSCAR EN LA WEB antes de probar 10 formulas a mano — Airtable tiene documentacion y foros que explican esto
4. Si una formula no funciona al primer intento, no probar 5 variaciones — buscar la documentacion oficial

---

## Error 5: Logo del QR no aparece en produccion

**Que se intento:**
El QR se generaba con el logo de Fenix Kids en el centro. Funcionaba perfecto en local.

**Por que se intento:**
El logo en el centro del QR es un toque profesional que diferencia el QR de uno generico.

**Por que fallo:**
La carpeta `marketing/` estaba en `.gitignore` (para no subir afiches de 5MB a git). Pero el logo tambien estaba ahi. Git no lo subia → Railway no lo tenia → QR sin logo en produccion.

El codigo manejaba la ausencia del logo silenciosamente (`if os.path.exists(_LOGO_PATH)`), asi que no habia error — simplemente no habia logo.

**La solucion correcta:**
Agregar excepcion en `.gitignore`:
```gitignore
marketing/*
!marketing/logos/
!marketing/logos/LOGO FENIX TRANSPARENTE OFICIAL.png
```

**Leccion:**
Si el codigo referencia un archivo, verificar que ese archivo llega a produccion. Revisar `.gitignore` siempre que se usa un archivo estatico. Un `if os.path.exists()` que falla silenciosamente es peor que un crash — al menos el crash te avisa.

---

## Error 6: "Parque Fenix" en vez de "Fenix Kids Academy"

**Que se intento:**
El caption del QR decia "Mostra este QR cuando llegues al Parque Fenix". La pagina de check-in decia "Bienvenido al Parque Fenix".

**Por que se intento:**
Se usaron nombres informales sin verificar el nombre oficial del negocio.

**Por que fallo:**
El nombre correcto es "Fenix Kids Academy", no "Parque Fenix". Es un tema de branding — el nombre debe ser consistente en toda la comunicacion.

**La solucion correcta:**
Cambiar los textos a "Fenix Kids Academy" en el caption y en la pagina HTML.

**Leccion:**
Siempre usar el nombre oficial del negocio. No inventar variaciones informales. Si no estas seguro, preguntar.

---

## Error 7: Aurora inventa opciones de menu

**Que se intento:**
El prompt de Aurora decia algo como "MENSAJES SIGUIENTES: saludo calido + menu de opciones" sin especificar CUALES opciones.

**Por que se intento:**
Se confiaba en que Haiku armaria un menu logico basado en las capacidades del agente.

**Por que fallo:**
Haiku invento una opcion "2. Ver lista de ninos agendados" que no existia como funcionalidad. El padre la seleccionaba y el agente no sabia que hacer.

**La solucion correcta:**
Poner el menu EXACTO, textual, en el prompt:
```
Menu Aurora (mensajes siguientes):
1. Agendar clase
2. (Proximamente)
3. (Proximamente)
4. Redes sociales
```

**Leccion:**
Nunca dejar menus vagos para un LLM. Ser textual y explicito. Si el prompt dice "mostrar opciones", el modelo va a inventar opciones. Si el prompt dice "mostrar ESTAS opciones: 1, 2, 3", el modelo muestra exactamente eso.

---

## Error 8: IS_AFTER no incluye hoy

**Que se intento:**
Filtrar reservas futuras con:
```
IS_AFTER({FECHA}, '2026-05-25')
```
para ver las reservas de hoy (25 de mayo) en adelante.

**Por que se intento:**
IS_AFTER parece que deberia incluir la fecha exacta — "despues del 25" deberia incluir el 25, no?

**Por que fallo:**
No. `IS_AFTER` es estrictamente "despues de", excluyendo la fecha indicada. Las reservas del dia de hoy no aparecian.

**La solucion correcta:**
Usar la fecha de AYER:
```
IS_AFTER({FECHA}, '2026-05-24')
```
Asi se incluye el 25 de mayo.

Alternativamente, comparar strings directamente:
```python
if _fecha >= _hoy_str:  # >= incluye hoy
```

**Leccion:**
IS_AFTER en Airtable es estrictamente "after", no "on or after". Documentar este comportamiento porque es contraintuitivo.

---

## Error 9: Saltear el checklist multiples veces

**Que se intento:**
Se hicieron 3 deploys seguidos sin ejecutar el checklist de verificacion previo.

**Por que se intento:**
Prisa. "Es un cambio chico, no hace falta checklist."

**Por que fallo:**
Cada deploy rompio algo que el checklist habria detectado. Ivan tuvo que recordar multiples veces: "ejecuta el checklist".

**La solucion correcta:**
Ejecutar el checklist SIEMPRE, sin excepciones, antes de cada deploy. Es mas rapido ejecutar un checklist de 2 minutos que debuggear un bug en produccion por 20 minutos.

**Leccion:**
El checklist existe por una razon. Ejecutarlo CADA vez, no importa lo chico que sea el cambio. Si te parece que no hace falta, es exactamente cuando mas falta hace.

---

## Error 10: Parches de prompt en vez de arreglos de codigo

**Que se intento (cronologicamente):**
1. Agregar "REGLA CRITICA: la UNICA fuente de verdad para reservas son los datos de Airtable" al system prompt → no funciono
2. Parsear strings en brain.py para separar reservas del contexto → fragil, feo
3. Pasar reservas como parametro separado a la API → direccion correcta pero compleja
4. Finalmente: mover datos al user message + forzar tool → funciono en 10 minutos

**Por que se intento:**
El instinto es agregar mas texto al prompt cuando el modelo no hace lo que queres. "Si le explico mejor, va a entender."

**Por que fallo:**
Agregar mas instrucciones al prompt es como gritarle mas fuerte a alguien que no habla tu idioma. El problema no era la instruccion — era DONDE estaba la informacion.

3 horas entre intentos fallidos de prompt patches. La solucion (cambiar posicion de datos + forzar tool) tomo 10 minutos.

**Leccion:**
Arreglos de codigo > parches de prompt. Si el modelo ignora datos, no agregues mas instrucciones — cambia DONDE pones los datos. Si el modelo no usa una tool, no le pidas "por favor usa la tool" — forzala con `tool_choice`. El codigo es determinístico, el prompt no.

---

## Error 11: Reset que no limpio el historial

**Que se intento:**
Enviar el comando de reset ("holayosoyfenix") para limpiar el historial de una conversacion.

**Por que se intento:**
Para empezar limpio despues de un deploy con cambios grandes.

**Por que fallo:**
El deploy NO habia terminado cuando se envio el reset. El codigo viejo proceso el mensaje. Los mensajes nuevos se acumularon sobre los viejos. El historial paso de 74 a 82 mensajes en vez de resetearse.

**La solucion correcta:**
1. Esperar a que Railway muestre "Deploy successful" antes de testear
2. Verificar que el reset funciono consultando la DB/API
3. No asumir que "mande el comando" = "el comando se ejecuto"

**Leccion:**
Siempre verificar que un deploy termino antes de testear. Y siempre verificar que una accion destructiva (reset, delete) realmente se ejecuto. "Lo mande" no es lo mismo que "funciono".

---

## Error 12: Probar formulas de Airtable por fuerza bruta

**Que se intento:**
Cuando ARRAYJOIN con record links no funciono, se probaron 6+ formulas diferentes por trial and error.

**Por que se intento:**
"Alguna de estas tiene que funcionar." Iteracion rapida: cambiar formula, probar, ver resultado, repetir.

**Por que fallo:**
Ninguna funciono porque el problema era conceptual (ARRAYJOIN + multipleRecordLinks = no funciona), no de sintaxis. 30 minutos y 6+ llamadas API perdidas.

Ivan dijo: "En vez de probar como un loco diez mil cosas, por que no buscas en la web?"

**La solucion correcta:**
Buscar "airtable filter linked records formula" en Google. Los foros de Airtable y la documentacion explican claramente que ARRAYJOIN no funciona con record links y que la solucion es usar lookup fields de texto.

**Leccion:**
Google primero, probar despues. Especialmente con APIs de terceros (Airtable, Stripe, etc.) que tienen documentacion extensa y foros activos. Si algo no funciona al segundo intento, dejar de probar variaciones y buscar la documentacion oficial. La fuerza bruta es la opcion mas cara en tiempo.

---

## Error 13: gestionar_prueba retorna error porque PRUEBA FENIX no existe aun

**Que se intento:**
La tool `gestionar_prueba(accion="confirmar")` busca registros existentes en PRUEBA FENIX por telefono para confirmar la agenda.

**Por que se intento:**
Despues del pago, el sistema activa `modo_agenda` y fuerza la tool. El padre elige "30 mayo 11h" → tool se ejecuta.

**Por que fallo:**
PRUEBA FENIX no tiene registro todavia — se crea DESPUES con el formulario de datos (nombre, fecha nacimiento). La tool busca por telefono, no encuentra nada → `error=True` → sin QR. El registro termino creandose por el flujo viejo de regex post-formulario, que no tenia QR.

**La solucion correcta:**
El QR se envia DESPUES del formulario (cuando PRUEBA FENIX ya existe), no cuando la tool confirma la agenda. La tool confirma fecha+hora, el formulario crea el registro, el QR se genera con el record_id del registro creado.

**Leccion:**
El QR depende del registro existente. Enviar QR en el momento correcto del flujo (post-formulario), no post-agenda. Antes de generar un QR que apunta a un record_id, verificar que el record existe.

---

## Error 14: modo_agenda forzaba tool para TODOS los mensajes del lead

**Que se intento:**
Con `modo_agenda=True`, CUALQUIER mensaje del padre forzaba `gestionar_prueba`.

**Por que se intento:**
El flag se activaba post-pago para forzar la tool cuando el padre eligiera fecha+hora. La intencion era correcta.

**Por que fallo:**
El padre mando datos del formulario ("Ivan Lafuente, Ivan Lafuente, 09/09/2019") → el flag seguia activo → la tool se forzo con ese texto → intento "confirmar" de nuevo con datos incorrectos → error de nuevo. El flag persistio mas alla de su proposito.

**La solucion correcta:**
Limpiar `modo_agenda` despues de que el padre elige fecha+hora (no despues de confirmada la prueba). El flag debe vivir SOLO durante el momento exacto en que se espera la eleccion de horario.

**Leccion:**
Los flags de estado deben limpiarse en el momento correcto. Un flag que persiste mas de lo necesario causa efectos colaterales. Definir claramente: cuando se activa Y cuando se desactiva.

---

## Error 15: Deploy de Railway reinicia el servidor y se pierden mensajes

**Que se intento:**
El padre mando "precio" justo cuando Railway estaba reiniciando por un nuevo deploy.

**Por que se intento:**
No es un error del codigo — es timing desafortunado durante un deploy.

**Por que fallo:**
El servidor hizo shutdown (Shutting down → Finished server process) y el webhook no se proceso. Meta no reintenta webhooks que recibieron timeout. El mensaje se perdio.

**La solucion correcta:**
No es un bug del codigo. Esperar a que el deploy termine antes de testear. Considerar para el futuro: healthcheck mas robusto, o queue de mensajes para no perder webhooks durante restarts.

**Leccion:**
Railway reinicia en cada push a main. Los mensajes que llegan durante el reinicio (~5-10 seg) se pierden. Es un riesgo aceptable para el volumen actual, pero hay que saberlo. No testear durante deploys.

---

## Error 16: Prompt de Ivan seguia ofreciendo horarios antes del pago

**Que se intento:**
Implementamos flujo deterministico post-pago (`modo_agenda`), pero el prompt de Ivan decia "FASE 3: elige dia+horario → confirmar_reserva → pasar datos bancarios".

**Por que se intento:**
Se cambio el codigo (modo_agenda post-pago) sin actualizar el prompt de Ivan.

**Por que fallo:**
Ivan (el agente) ofrecia sabados ANTES de cobrar, porque el prompt le decia que lo hiciera. El modo_agenda era inutil porque el agente ya habia ofrecido horarios por su cuenta, siguiendo el prompt viejo.

**La solucion correcta:**
Invertir el prompt: FASE 3 = cobrar primero. "Te paso los datos para la transferencia. Una vez que reciba tu comprobante, agendamos el dia y te paso tu QR."

**Leccion:**
Cambiar el codigo sin cambiar el prompt es inutil. El prompt es la instruccion del agente — si contradice el codigo, el agente sigue el prompt. Codigo y prompt deben estar sincronizados SIEMPRE. Cuando cambias un flujo en el codigo, actualizar el prompt en el mismo commit.

---

## Error 17: Keywords insuficientes para detectar flujo de reservas en Ivan

**Que se intento:**
Deteccion por keywords: "agendar", "reagendar", "11:00", "15:30", "11h", "15h". Se expandio con regex y deteccion de "ultimo mensaje del agente ofrecio horarios".

**Por que se intento:**
Funcionaba para Aurora (flujo simple: menu → opcion 1 → fecha+hora). Se asumio que la misma estrategia serviria para Ivan.

**Por que fallo:**
- El padre dice "11" (sin "h") o "Si" → no matchea → tool no se fuerza
- Demasiadas variantes en el flujo conversacional de leads
- Expandir keywords lleva a falsos positivos ("11 de la manana" vs "tengo 11 alumnos")
- Intentar detectar "el ultimo mensaje ofrecio horarios" es fragil y rompe con cambios en el prompt

**La solucion correcta:**
- **Para Ivan:** No forzar tool_choice por keywords. Usar flag `modo_agenda` que se activa SOLO post-pago. Flag = certeza, keywords = adivinanza.
- **Para Aurora:** Keywords + deteccion de historial funciona porque el flujo es mas simple (menu → opcion 1 → fecha+hora).

**Leccion:**
Forzar tools por keywords es fragil. Preferir flags de estado (certeza) sobre heuristicas (keywords). Las keywords funcionan cuando el universo de respuestas posibles es acotado. En flujos conversacionales abiertos, los flags son la unica opcion confiable.

---

## Resumen ejecutivo de lecciones

| # | Leccion | Categoria |
|---|---------|-----------|
| 1 | Una tool unificada con `accion` > multiples tools separadas | Arquitectura |
| 2 | `tool_choice` forzado para acciones criticas, nunca `auto` | Tool Use |
| 3 | Datos en tiempo real van en user message, no en system prompt | Prompt Engineering |
| 4 | ARRAYJOIN no funciona con multipleRecordLinks en Airtable | Airtable |
| 5 | Verificar .gitignore cuando el codigo referencia archivos estaticos | Deploy |
| 6 | Usar siempre el nombre oficial del negocio | Branding |
| 7 | Menus del LLM deben ser textuales y explicitos, nunca vagos | Prompt Engineering |
| 8 | IS_AFTER en Airtable es estricto, no incluye la fecha dada | Airtable |
| 9 | Ejecutar el checklist SIEMPRE antes de deploy | Proceso |
| 10 | Arreglos de codigo > parches de prompt | Debugging |
| 11 | Verificar que el deploy termino antes de testear | Deploy |
| 12 | Google primero, probar despues (especialmente APIs de terceros) | Debugging |
| 13 | QR depende del registro existente — enviar post-formulario, no post-agenda | Flujo / Timing |
| 14 | Flags de estado deben limpiarse en el momento correcto | Estado |
| 15 | Railway pierde mensajes durante restart (~5-10 seg por deploy) | Deploy |
| 16 | Cambiar codigo sin cambiar prompt es inutil — sincronizar siempre | Prompt + Codigo |
| 17 | Flags de estado (certeza) > keywords (heuristica) para forzar tools | Tool Use |

---

> Documento creado: 2026-05-25
> Proyecto: FENIX KIDS ACADEMY — WhatsApp AI Agent
> Stack: Python 3.11 + FastAPI + Claude Haiku 4.5 + Airtable + WhatsApp (Meta Cloud API)
