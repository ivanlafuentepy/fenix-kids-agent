Guia completa para crear y conectar una plantilla Meta WhatsApp al agente Aurora (FENIX Kids).

Usar este skill cuando Ivan diga:
- "armemos una plantilla nueva"
- "creemos plantilla para X"
- "como hago plantilla para WhatsApp"
- "agregar template Meta"

Cubre el flujo completo: diseno → creacion (API o Business Manager) → codigo Aurora → testeo.

---

## 0. LO DISTINTO DE FENIX (leer primero)

- **Fenix tiene su WABA PROPIO** (`WABA_ID = 896276490105251`), NO el compartido con
  Salsa Soul. La doc vieja que decia "WABA compartido 2112324596219739" era FALSA
  (error #131009 del 2026-07-11) — con Salsa/Dorita se comparte solo el Business
  Portfolio, no el WABA. Las plantillas de Fenix viven en SU WABA; las de Dorita NO
  estan disponibles para el numero de Fenix.
- **El token de Fenix (`META_ACCESS_TOKEN` de este repo) SI administra su WABA propio**
  → crea, edita y envia plantillas ahi. Verificado 2026-07-12 (se creo y aprobo
  `confirmacion_sabado_fenix` con ese token). NO hace falta el token de Dorita para
  plantillas de Fenix (el de Dorita solo se usa para leer el SCHEMA de Airtable).
  Listar/crear:
  `GET  https://graph.facebook.com/v21.0/896276490105251/message_templates` (Bearer token Fenix)
  `POST https://graph.facebook.com/v21.0/896276490105251/message_templates` (Bearer token Fenix)
- **La firma de `enviar_plantilla` en Fenix es DISTINTA a la de Dorita**:
  `enviar_plantilla(telefono, template_name, variables=None, componentes=None, language="es")`.
  El kwarg es **`language=`** (Dorita usa `idioma=`) y el **default es `"es"`** — si la
  plantilla esta aprobada en `es_AR` hay que pasar `language="es_AR"` EXPLICITO o Meta
  responde "template name does not exist in the translation".

---

## 1. CUANDO USAR UNA PLANTILLA META

Las plantillas (templates) son la unica forma de mandar WhatsApp **fuera de la ventana
de 24h** de conversacion activa. Si la familia no escribio en las ultimas 24h, los
mensajes libres son rechazados.

**Categorias Meta:**
| Categoria | Cuando | Aprobacion |
|---|---|---|
| `UTILITY` | Notificaciones post-accion (confirmacion, factura, recordatorio) | Rapida (~minutos) |
| `MARKETING` | Promos, anuncios, reactivacion | Mas estricta (~horas/dias) |

**Regla:** si la familia hizo algo (pago, agendo) y le respondes a esa accion, va
`UTILITY`. Si Aurora inicia para vender algo, va `MARKETING`.

---

## 2. CREAR LA PLANTILLA

### Opcion A: por API (con el token de FENIX, contra su WABA 896276490105251)

El token de Fenix (`META_ACCESS_TOKEN` del `.env` de este repo) alcanza para todo.
Ejemplo real: `confirmacion_sabado_fenix` (botones si/no, posicional), creada y
aprobada en minutos el 2026-07-12.

Body posicional con botones quick-reply (el molde mas simple):
```bash
TOK=$(grep -E "^META_ACCESS_TOKEN=" .env | cut -d= -f2-)
curl -s -X POST "https://graph.facebook.com/v21.0/896276490105251/message_templates" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{
    "name": "nombre_snake_case",
    "language": "es_AR",
    "category": "UTILITY",
    "components": [
      {"type": "BODY", "text": "Hola {{1}}! ... {{2}} ...",
       "example": {"body_text": [["Sofía", "Mateo"]]}},
      {"type": "BUTTONS", "buttons": [
        {"type": "QUICK_REPLY", "text": "Sí"},
        {"type": "QUICK_REPLY", "text": "No"}
      ]}
    ]
  }'
```
Con header DOCUMENT/IMAGE hay que subir la muestra primero (resumable upload →
`{"h": "<handle>"}`) y agregar `{"type":"HEADER","format":"DOCUMENT","example":{"header_handle":["<handle>"]}}`.
Para variables con nombre, usar `"parameter_format": "NAMED"` + `{{nombre}}` +
`"example":{"body_text_named_params":[{"param_name":"nombre","example":"Sofía"}]}`.

Queda `PENDING` → poll con
`GET https://graph.facebook.com/v21.0/896276490105251/message_templates?name=...&fields=name,status`
hasta `APPROVED` (UTILITY: minutos).

### Opcion B: manual en Business Manager

https://business.facebook.com → WhatsApp Manager → Plantillas → Crear plantilla.
- **Nombre**: lowercase con guiones bajos (ej: `factura_electronica_fenix`)
- **Idioma**: `Spanish (ARG)` = `es_AR`
- **Variables**: sintaxis NUEVA con nombre (`{{nombre}}`), NO `{{1}}`
- **Muestras**: nombres genericos (`Sofía`), nunca datos reales de clientes

---

## 3. CONECTAR EN EL CODIGO (Aurora)

Firma en `agent/providers/meta.py`:
```python
async def enviar_plantilla(telefono, template_name, variables=None, componentes=None, language="es") -> bool
```

**Variables posicionales `{{1}} {{2}}` (lo mas simple — arma el body solo):**
```python
await proveedor.enviar_plantilla(
    telefono, "confirmacion_sabado_fenix",
    variables=[nombre_padre, hijos_str],   # {{1}}, {{2}}
    language="es_AR",   # 👈 SIEMPRE explicito si la plantilla es es_AR
)
```

**Variables nombradas:**
```python
await proveedor.enviar_plantilla(
    telefono, "factura_electronica_fenix",
    componentes=[{
        "type": "body",
        "parameters": [{"type": "text", "parameter_name": "nombre", "text": nombre}],
    }],
    language="es_AR",   # 👈 SIEMPRE explicito si la plantilla es es_AR
)
```

Los botones quick-reply de una plantilla llegan de vuelta como `tipo=="button"`
(en `providers/meta.py`): solo trae el **texto** del boton (ej "Sí"/"No"), sin `btn_id`.
Para saber a que plantilla responde, guardar un flag de estado al enviarla
(patron de `agent/confirmacion_sabado.py`: `esperando_confirmacion_sabado`).

**Header documento (PDF) + body:**
```python
componentes=[
    {"type": "header", "parameters": [
        {"type": "document", "document": {"link": pdf_url, "filename": "factura.pdf"}}]},
    {"type": "body", "parameters": [
        {"type": "text", "parameter_name": "nombre", "text": nombre}]},
]
```

**Header imagen** (ej. Promo Madre, `main.py`): `{"type": "image", "image": {"id": media_id}}`.

Errores comunes: ver la guia hermana en `whatsapp-agentkit/.claude/commands/plantilla.md`
(seccion 6) — aplican igual.

---

## 4. TESTEAR

1. Enviar la plantilla a tu propio numero con un script/endpoint temporal.
2. Verificar que la variable se reemplaza (si sale literal `{{nombre}}` → el
   `parameter_name` no matchea o falta `parameter_format: NAMED` en la creacion).
3. Logs de Railway: buscar `Plantilla '<nombre>' enviada` o el error de Meta con detalle.

---

## 5. PLANTILLAS ACTIVAS EN FENIX (referencia)

Mantener actualizada esta seccion.

| Nombre | Categoria | Variables | Donde se usa | Codigo |
|---|---|---|---|---|
| `confirmacion_sabado_fenix` | UTILITY | `{{1}}` padre + `{{2}}` hijos + botones Sí/No | jueves 9AM: confirma asistencia del sábado a familias al día | `agent/loops.py` `_confirmacion_sabado_loop` + `agent/confirmacion_sabado.py` |
| `factura_electronica_fenix` | UTILITY | header DOCUMENT + `{{nombre}}` | envio de factura PDF fuera de ventana 24h | `agent/loops.py` `_envio_facturas_fenix_loop` |
| `contenido_hijo` | — | (ver codigo) | contenido social fuera de ventana | `agent/contenido_social.py:124` |
| `fenixpromomadre` | MARKETING | header IMAGE | envio masivo por endpoint | `agent/main.py` (~979) |

Todas viven en el WABA propio de Fenix (`896276490105251`). Listar el estado real:
`GET https://graph.facebook.com/v21.0/896276490105251/message_templates?fields=name,status,category,language`
con el token de Fenix. Las plantillas de Dorita NO estan disponibles para el numero de Fenix.
