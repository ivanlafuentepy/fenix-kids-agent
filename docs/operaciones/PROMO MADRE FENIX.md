up:: [[FENIX KIDS/FENIX_RESUMEN|FENIX RESUMEN]]

# Promo Madre FENIX KIDS — 15 de Mayo 2026

## Contexto
Replicación del flujo de promo día de la madre de DORITA en [[EDITOR PRO MAX/REDES SOCIALES/Fenix Kids Academy|FENIX KIDS Academy]]. Misma promo: 350.000 Gs, pero 2 meses (no 3) + matrícula exonerada. Implementado como UN SOLO COMMIT inicial, aplicando las lecciones de la sesión de DORITA (que tuvo 5 regresiones por deploys incrementales).

---

## Datos de la promo

| Dato | Valor |
|---|---|
| Monto | 350.000 Gs |
| Incluye | 2 meses de clases + matrícula exonerada |
| Vigencia | Solo hoy 15/05 hasta las 20:00 |
| Plantilla Meta | `fenixpromomadre` (idioma: `es_AR`) |
| Media handle imagen | `1348826603758035` (resubido, el anterior `1295983018794545` expiró) |
| Datos bancarios | Alias CI 1604338, Itaú, Iván Lafuente (mismos que DORITA) |
| Formulario | Nombre+apellido responsable, nombre+apellido hijo, fecha nacimiento hijo |
| WABA | Mismo Business Account que Salsa Soul, pero token diferente |
| PHONE_NUMBER_ID | `1005063086033214` (+595 971 938655, "Profe Ivan - Aurora Info Clases") |

---

## Commits (3 commits totales)

### Commit `fad5d17` — flujo completo + envío masivo (UN SOLO COMMIT)
**Archivos:** `agent/main.py`, `agent/providers/meta.py`, `agent/brain.py`

#### `agent/providers/meta.py`
- **Cambio:** Agregado parámetro `componentes: list[dict] | None = None` a `enviar_plantilla()`
- **Qué hace:** Permite pasar componentes raw (header imagen, botones) además de las variables de texto
- **Backward compatible:** Si se pasa `variables`, funciona como antes. Si se pasa `componentes`, usa los raw.

#### `agent/main.py` — dicts globales (~línea 205)
```python
_esperando_pago_promo_madre: set[str] = set()       # leads esperando comprobante
_leads_promo_madre_enviada: set[str] = set()         # leads que recibieron plantilla
_esperando_formulario_promo: set[str] = set()        # leads que enviaron comprobante, esperan datos
_promo_masiva_estado: dict = {"activo": False, "total": 0, "enviados": 0, "errores": 0, "ultimo_enviado": ""}
```

#### `agent/main.py` — endpoints (ANTES de `/debug/{telefono}`)
1. **`GET /debug/estado-promo-masiva`** — progreso del envío masivo en tiempo real
2. **`GET /debug/enviar-promo-masiva`** — envío masivo en background
   - `?dry_run=true` (default) → lista leads sin enviar
   - `?dry_run=false` → envía en background
   - `?telefono_test=595...` → envía solo a ese número
   - Protección contra doble envío
   - Pagina TODA la tabla LEADS FENIX con httpx (no usa `_get_records` que no pagina)
   - Rate limit: pausa 2s cada 50 envíos
   - Por cada envío exitoso: `PROMOMADRE=True` en Airtable + notificación Telegram

3. **`_enviar_promo_background()`** — función async que corre como `asyncio.create_task()`

#### `agent/main.py` — handlers promo madre (ANTES del handler de comprobante general)

**Handler 1: Formulario promo madre** (~línea 2141)
- Condición: `telefono in _esperando_formulario_promo` + texto no es imagen/audio/holayosoyfenix
- Acción: Envía confirmación "¡Muchas gracias! Tu promo cubre del 15 de mayo al 15 de julio"
- Guarda: `CONVERSION=PAGO` + `PROMOMADRE=True` en LEADS FENIX
- Notifica: admin por WhatsApp + Telegram topic

**Handler 2: Respuesta a plantilla** (~línea 2176)
- Condición: `telefono in _leads_promo_madre_enviada` O texto contiene "quiero" + "promo"
- Exclusión: holayosoyfenix siempre pasa
- Acción: Crea lead si no existe → envía datos bancarios (350k, 2 meses, matrícula exonerada)
- Marca: `_esperando_pago_promo_madre.add(telefono)` + `BOTON PROMOMADRE=True`

**Handler 3: Comprobante promo madre** (~línea 2210)
- Condición: `telefono in _esperando_pago_promo_madre` + texto es imagen/documento
- Acción: Reenvía imagen al admin + espejo Telegram + pide formulario (responsable + hijo + fnac)
- Marca: `_esperando_formulario_promo.add(telefono)`

#### `agent/main.py` — limpieza en holayosoyfenix (~línea 1712)
```python
_esperando_pago_promo_madre.discard(telefono)
_leads_promo_madre_enviada.discard(telefono)
_esperando_formulario_promo.discard(telefono)
```

#### `agent/brain.py` — override promo madre
Inyectado al final del system prompt de Ivan/Aurora:
```
═══ PROMO DÍA DE LA MADRE (vigente) ═══
🎁 350.000 Gs → 2 meses de clases + matrícula exonerada.
Solo hasta las 20:00 de hoy. Cupos limitados.
Si el padre pregunta por la promo, decile que escriba 'quiero la promo'
o contale los datos bancarios: Alias CI 1604338, Itaú, Iván Lafuente.
```

---

### Commit `2ef5b6b` — BOTON PROMOMADRE + texto "quiero la promo" + comando
**Archivo:** `agent/main.py`

#### Detección por texto (no solo plantilla)
- `"quiero" in texto and "promo" in texto` → activa promo madre SIEMPRE
- No depende de `_leads_promo_madre_enviada` (que se pierde al reiniciar Railway)

#### BOTON PROMOMADRE check en Airtable
- Al responder a la promo (botón o texto) → `BOTON PROMOMADRE=True` en LEADS FENIX

#### Comando "promo madre" (solo admin)
- Escanea LEADS FENIX con `PROMOMADRE=TRUE()`
- Revisa historial PostgreSQL de cada lead
- Muestra totales: enviados, respondieron, tasa respuesta, wa.me links

---

### Commit `072548c` — media handle actualizado
**Archivo:** `agent/main.py`
- Handle anterior `1295983018794545` expiró
- Nuevo handle `1348826603758035` (resubido con mismo token FENIX)

---

## Diferencias con implementación DORITA

| Aspecto | DORITA | FENIX |
|---|---|---|
| Promo | 3 meses | 2 meses |
| Commits | 24 (5 regresiones) | 3 (0 regresiones) |
| Formulario | nombre + apellido | responsable + hijo + fnac (5 campos) |
| Handlers admin bypass | 5 handlers con bypass individual | Sin bypass necesario (admin handlers no interceptan texto de leads) |
| holayosoylasalsa/fenix | Roto 3 veces | Excluido desde el inicio |
| Enviar plantilla | Solo desde endpoint web | Desde curl directo en Claude Code |
| Idioma plantilla | es_AR | es_AR |
| WABA | Propio | Mismo Business Account que Salsa Soul pero token diferente |

## Campos Airtable (crear en LEADS FENIX)

| Campo | Tipo | Qué hace |
|---|---|---|
| `PROMOMADRE` | Checkbox | Se marca al enviar plantilla al lead |
| `BOTON PROMOMADRE` | Checkbox | Se marca cuando el lead responde/toca botón |

## Flujo completo

```
1. Plantilla enviada (masivo o manual) → lead recibe flyer + botón "QUIERO LA PROMO"
2. Lead toca botón o escribe "quiero la promo" → datos bancarios 350k
3. Lead envía comprobante → gracias + pedir datos (responsable + hijo + fnac)
4. Lead envía datos → "¡Muchas gracias! Tu promo cubre del 15 de mayo al 15 de julio"
5. Admin notificado por WhatsApp + Telegram en cada paso
```

## Problema encontrado: WABA y tokens

La plantilla `fenixpromomadre` se creó inicialmente en el WABA de Salsa Soul (donde DORITA opera). FENIX usa el mismo Business Account pero con token diferente. La plantilla debe crearse seleccionando el número de FENIX en Meta Business Manager, no el de Salsa Soul. Error descubierto al intentar enviar: "template name does not exist in the translation".

## Media handles expiran

El media handle de la imagen subida a Meta expira después de un tiempo. Si el envío masivo falla con error de media, hay que resubir la imagen:
```bash
curl -s -X POST "https://graph.facebook.com/v21.0/{PHONE_ID}/media" \
  -H "Authorization: Bearer {TOKEN}" \
  -F "messaging_product=whatsapp" \
  -F "type=image/png" \
  -F "file=@/ruta/imagen.png"
```
Y actualizar el handle en el código o env var `PROMO_MADRE_IMAGE_HANDLE`.
