Guia completa para crear y conectar una plantilla Meta WhatsApp al agente Aurora (FENIX Kids).

Usar este skill cuando Ivan diga:
- "armemos una plantilla nueva"
- "creemos plantilla para X"
- "como hago plantilla para WhatsApp"
- "agregar template Meta"

Cubre el flujo completo: diseno → creacion (API o Business Manager) → codigo Aurora → testeo.

---

## 0. LO DISTINTO DE FENIX (leer primero)

- **Fenix vive en el WABA COMPARTIDO con Salsa Soul** (`WABA_ID = 2112324596219739`).
  Las plantillas son del WABA, no del numero: **cualquier plantilla aprobada de Dorita
  tambien la puede mandar el numero de Fenix** (y viceversa). Antes de crear una nueva,
  revisar si ya existe una que sirva.
- **El token de Fenix (`META_ACCESS_TOKEN` de este repo) NO tiene rol de management
  sobre el WABA** → NO puede crear plantillas. Para crear/editar hay que usar el token
  de management de Dorita (`whatsapp-agentkit/.env` → `META_ACCESS_TOKEN`), igual que
  con los Flows (ver `scripts/crear_flow_fenix.py`). Para ENVIAR plantillas aprobadas,
  el token de Fenix funciona perfecto.
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

### Opcion A: por API (como se creo `factura_electronica_fenix`, 03/07/2026)

Con el token de management de Dorita. Pasos (script de referencia usado:
`crear_plantilla_factura_fenix.py`, sesion Claude 03/07/2026):
1. `GET /debug_token?input_token={tok}` → `app_id`.
2. Si lleva header DOCUMENT/IMAGE: resumable upload del archivo de muestra →
   `POST /{app_id}/uploads?file_name=..&file_length=..&file_type=..` → `upload_id`,
   luego `POST /{upload_id}` con header `Authorization: OAuth {tok}` + `file_offset: 0`
   y el binario en el body → devuelve `{"h": "<handle>"}`.
3. `POST /{WABA_ID}/message_templates` con:
```json
{
  "name": "nombre_snake_case",
  "language": "es_AR",
  "category": "UTILITY",
  "parameter_format": "NAMED",
  "components": [
    {"type": "HEADER", "format": "DOCUMENT", "example": {"header_handle": ["<handle>"]}},
    {"type": "BODY", "text": "¡Hola {{nombre}}! ...",
     "example": {"body_text_named_params": [{"param_name": "nombre", "example": "Sofía"}]}}
  ]
}
```
4. Queda `PENDING` → poll con `GET /{WABA_ID}/message_templates?name=...&fields=name,status`
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

**Variables nombradas (recomendado):**
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
| `factura_electronica_fenix` | UTILITY | header DOCUMENT + `{{nombre}}` | envio de factura PDF fuera de ventana 24h | `agent/loops.py` `_envio_facturas_fenix_loop` |
| `contenido_hijo` | — | (ver codigo) | contenido social fuera de ventana | `agent/contenido_social.py:124` |
| (Promo Madre) | MARKETING | header IMAGE | envio masivo por endpoint | `agent/main.py` (~979) |

Del WABA compartido tambien estan disponibles las de Dorita (`bienvenido_qr`,
`factura_electronica`, `recordatorio_3h`, ...): listar todas en WhatsApp Manager.
