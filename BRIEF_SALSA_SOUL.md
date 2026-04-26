# BRIEF PARA CLAUDE — Implementar Engranaje Redes Sociales en SALSA SOUL

> Este documento explica un sistema que ya funciona en el proyecto FENIX KIDS AGENT.
> Tu trabajo es implementar lo mismo adaptado para SALSA SOUL (academia de baile).
> Lee todo antes de empezar.

---

## Qué es y por qué existe

Es un sistema automático que:
1. **Envía contenido de redes sociales a los alumnos/padres por WhatsApp todos los días** — una red diferente por día
2. **Detecta cuando un alumno aparece en un posteo** y le avisa personalizado: "Mirá, aparecés en este posteo de Instagram!"
3. **Envía recordatorio pre-clase** con confirmación activa
4. **Mantiene la ventana de 24h de WhatsApp siempre abierta** — si le escribís todos los días con contenido de valor, los mensajes son gratis (no necesitás plantillas Meta pagas)

La estrategia viene de Hormozi ($100M Leads): follow-up agresivo, nunca el mismo mensaje, cada toque agrega valor. WhatsApp tiene 98% de apertura vs 20% del email.

---

## Calendario semanal

| Día | Red social | Mensaje |
|---|---|---|
| Lunes | Instagram | "Hola [nombre]! Mirá nuestro nuevo posteo en Instagram [link]" |
| Martes | Facebook | "Hola [nombre]! Nueva publicación en Facebook [link]" |
| Miércoles | TikTok | "Hola [nombre]! Nuevo video en TikTok [link]" |
| Jueves | YouTube | "Hola [nombre]! Nuevo contenido en YouTube [link]" |
| Viernes | Threads | "Hola [nombre]! Mirá esto en Threads [link]" |
| Sábado | Fotos del día | Fotos de la clase (directo en el chat) |
| Domingo | Videos | Videos de la clase editados |

Si el alumno aparece en el posteo del día, recibe un mensaje diferenciado:
```
"Hola [nombre]! Aparecés en nuestro nuevo posteo de [red]! Miralo acá 👇 [link]"
```

---

## Arquitectura: cómo funciona

### Flujo completo

```
IVAN: nombra fotos con nombre_apellido.jpg
        |
CLAUDE (Editor Pro Max): lee nombres de archivos, arma carrusel/reel
        |
CLAUDE (Postiz): publica en redes sociales + obtiene link del posteo
        |
CLAUDE (Postiz): crea registro en tabla CONTENIDO [PROYECTO] de Airtable
    → link, red social, tipo, vincula ALUMNOS por nombre
        |
BOT (polling cada 5 min): detecta registros con NOTIFICADO = false
        |
BOT determina tipo de mensaje:
    - Si el alumno está vinculado al posteo → mensaje personalizado
    - Si no está vinculado → mensaje genérico del día
        |
BOT envía WhatsApp → marca NOTIFICADO = true
```

### Airtable como puente

Airtable es el puente entre Postiz (que publica) y el bot de WhatsApp (que notifica). Claude de Postiz crea el registro, el bot lo detecta y actúa. No hay comunicación directa entre los dos sistemas.

---

## Qué se necesita en Airtable

### Tabla CONTENIDO [PROYECTO] (ej: CONTENIDO SALSA)

| Campo | Tipo | Descripción |
|---|---|---|
| TITULO | Texto | Descripción del posteo (ej: "Clase bachata martes 29/4") |
| RED | Single Select | Instagram / Facebook / TikTok / YouTube / Threads |
| TIPO | Single Select | Reel / Posteo / Historia / Carrusel |
| LINK | URL | Link directo al posteo publicado |
| ALUMNOS | Link records (→ tabla de alumnos) | Alumnos que aparecen en el posteo |
| NOTIFICADO | Checkbox | El bot marca true al enviar los WhatsApps |
| FECHA | DateTime | Auto al crear |

### Tabla REDES [PROYECTO] (ej: REDES SALSA)

| Campo | Tipo | Descripción |
|---|---|---|
| RED | Texto | Instagram, Facebook, TikTok, YouTube, Threads |
| PERFIL | URL | Link al perfil (ej: https://instagram.com/salsasoulstudio) |
| ICONO | Texto | Emoji (📸, 📘, 🎵, 🎬, 🧵) |

---

## Qué se necesita en el código del bot

### 1. Funciones en airtable_client.py (o equivalente)

```python
# Constantes
_CONTENIDO = "CONTENIDO SALSA"  # o como se llame la tabla
_REDES = "REDES SALSA"

# Funciones nuevas:
async def obtener_contenido_no_notificado() -> list[dict]:
    """Retorna registros con NOTIFICADO=false. Cada item: id, titulo, red, tipo, link, alumno_ids"""

async def marcar_contenido_notificado(record_id: str) -> bool:
    """Marca NOTIFICADO=True"""

async def obtener_ultimo_contenido_por_red(red: str) -> dict | None:
    """Busca el contenido más reciente de una red específica con NOTIFICADO=false"""

async def obtener_redes() -> list[dict]:
    """Retorna todos los perfiles de redes sociales"""

async def obtener_alumnos_con_telefono() -> list[dict]:
    """Retorna todos los alumnos/contactos con teléfono cargado.
    Cada item: id, telefono, nombre, apodo, alumno_ids (si aplica)"""

async def obtener_nombre_alumno(alumno_id: str) -> dict | None:
    """Retorna nombre y apodo de un alumno por record_id"""
```

### 2. Función enviar_plantilla en provider de WhatsApp

```python
async def enviar_plantilla(
    self,
    telefono: str,
    template_name: str,
    variables: list[str] | None = None,
    language: str = "es",
) -> bool:
    """
    Envía un mensaje de plantilla aprobada por Meta.
    Necesario para contactos fuera de ventana 24h.
    """
    url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
    template = {
        "name": template_name,
        "language": {"code": language},
    }
    if variables:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": v} for v in variables],
            }
        ]
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono,
        "type": "template",
        "template": template,
    }
    # ... enviar con httpx
```

### 3. Módulo contenido_social.py — el motor principal

Tiene 3 loops que corren en background:

#### Loop 1: Polling CONTENIDO (cada 5 min)
```
- Busca registros con NOTIFICADO=false
- Por cada registro:
  - Obtiene la lista de alumnos vinculados al posteo
  - Obtiene la lista de todos los contactos con teléfono
  - Por cada contacto:
    - Si algún alumno vinculado al contacto aparece en el posteo:
      → mensaje personalizado: "[nombre] aparece en este posteo de [red]! [link]"
    - Si no aparece:
      → no envía nada (el calendario diario se encarga del genérico)
  - Marca NOTIFICADO=true
```

#### Loop 2: Calendario diario (una vez al día, 10:00 hora local)
```
- Determina qué red social toca hoy (lun=IG, mar=FB, etc.)
- Busca el último contenido de esa red en CONTENIDO con NOTIFICADO=false
- Si hay contenido nuevo:
  - Envía a cada contacto:
    - Personalizado si su alumno aparece
    - Genérico si no
  - Marca como notificado
- Si NO hay contenido nuevo:
  - Envía link al perfil genérico de la red ("Seguinos en Instagram")
```

#### Loop 3: Recordatorio pre-clase (ej: viernes 18:00 para clases del sábado)
```
- Busca reservas/inscripciones para el día siguiente
- Por cada alumno con reserva:
  - Busca teléfono del contacto
  - Envía: "Mañana [nombre] tiene clase a las [hora]. Respondé CONFIRMO"
```

### 4. Integración en main.py (lifespan del servidor)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... inicialización existente ...

    # Contenido social: polling + calendario + recordatorio
    from agent.contenido_social import iniciar_contenido_social
    iniciar_contenido_social(proveedor)

    yield
```

La función `iniciar_contenido_social(proveedor)` crea los 3 asyncio.Tasks.

---

## Plantillas Meta necesarias

Crear en Meta Business Manager (business.facebook.com → WhatsApp Manager → Message Templates):

### `contenido_diario` (Marketing)
```
Hola {{1}}! Mirá nuestro nuevo posteo en {{2}} 👇
{{3}}
```
Variables: nombre, red_social, link

### `contenido_alumno` (Marketing)
```
Hola {{1}}! {{2}} aparece en nuestro nuevo posteo de {{3}}! Miralo acá 👇
{{4}}
```
Variables: nombre_contacto, nombre_alumno, red_social, link

### `recordatorio_clase` (Utility — más barato)
```
Hola {{1}}! Mañana {{2}} tiene clase a las {{3}}h. Te esperamos!
```
Variables: nombre_contacto, nombre_alumno, hora

---

## Lógica de ventana 24h (ahorro de costos)

- Si el contacto respondió en las últimas 24h → usar `enviar_mensaje` (GRATIS)
- Si la ventana está cerrada → usar `enviar_plantilla` (~$0.04 USD)
- **Truco**: las fotos del sábado/domingo son el ancla. Cuando mandás una foto del alumno, SIEMPRE responde. Eso reabre la ventana para toda la semana.
- **Intento primero mensaje normal, si falla intento plantilla** (el código de FENIX lo hace así)

---

## Conexión con Editor Pro Max / Postiz

Para que el flujo sea automático end-to-end, en el CLAUDE.md de Editor Pro Max hay que agregar:

> Cuando armes carruseles o posteos para [PROYECTO], lee los nombres de los archivos de fotos.
> Los archivos están nombrados como `nombre_apellido_01.jpg`.
> Después de publicar en Postiz, creá un registro en la tabla CONTENIDO [PROYECTO] de Airtable
> con el LINK del posteo, la RED social, el TIPO, y vinculá los ALUMNOS que aparecen
> (matcheando nombre_apellido del archivo con NOMBRE + APELLIDO en la tabla de alumnos).

---

## Adaptaciones necesarias para Salsa Soul

| FENIX KIDS | SALSA SOUL |
|---|---|
| Tabla NIÑOS FENIX | Tabla ALUMNOS (ya existe) |
| Tabla FAMILIAS FENIX (padres) | Contacto directo del alumno |
| Campo CELL PADRE / CELL MADRE | Campo de teléfono del alumno |
| Campo APODO en NIÑOS | Campo APODO en ALUMNOS (si existe) |
| Recordatorio viernes 18:00 | Recordatorio según día de clases de Salsa Soul |
| HORARIOS FENIX (sábados) | HORARIOS de Salsa Soul (según días de clase) |
| RESERVAS FENIX | Tabla de inscripciones/reservas de Salsa Soul |

---

## Archivos de referencia en FENIX KIDS AGENT

Si necesitás ver el código real que funciona:

- `agent/contenido_social.py` — módulo completo (polling + calendario + recordatorio)
- `agent/airtable_client.py` — funciones de Airtable (buscar las que empiezan con `obtener_contenido`, `obtener_redes`, `obtener_familias_inscriptas`)
- `agent/providers/meta.py` — función `enviar_plantilla`
- `ENGRANAJE_REDES_Y_REFERIDOS.md` — documento de diseño completo
- `PLANTILLAS_META.md` — textos exactos de las plantillas
