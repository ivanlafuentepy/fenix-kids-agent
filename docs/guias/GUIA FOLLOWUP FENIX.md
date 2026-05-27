up:: [[FENIX KIDS]]

# GUIA COMPLETA — Follow-Up Masivos FENIX KIDS

> Documento operativo para preparar, ejecutar y medir campanas de follow-up masivo.
> Incluye: como encontrar numeros, como seleccionar audiencia, historial de campanas,
> media disponible, registro en Airtable, y como sacar estadisticas.

---

## 1. Como encontrar los numeros

### Fuente principal: Airtable (LEADS FENIX)

Todos los leads estan en la tabla **LEADS FENIX** de la base **Salsa Soul Studio** (`appWwCQxALdMMV4MA`).

**Campos clave para FU:**

| Campo | Tipo | Que guarda |
|-------|------|------------|
| `TELEFONO` | Texto | Numero WhatsApp del lead |
| `NOMBRE RESPONSABLE` | Texto | Nombre del padre/madre |
| `NOMBRE NINO` | Texto | Nombre del hijo |
| `CONVERSION` | Select | Estado: CONSULTA, CONTACTADO, PRUEBA, PAGO, INSCRIPTO, DESCARTADO |
| `FECHA CREACION` | DateTime | Cuando llego el lead |
| `1ER FOLLOWUP` | Checkbox | Si recibio el primer FU masivo (fotos, 5 mayo) |
| `RESPONDIO FU1` | Checkbox | Si respondio despues del FU1 |
| `RESPONDIO FU2` | Checkbox | Si respondio despues del FU2 |
| `SEGUIMIENTOS` | Number | Contador de seguimientos individuales (0-3) |
| `FECHA FOLLOWUP` | DateTime | Timestamp del ultimo followup enviado |
| `PAGO POST FU` | Number | Si pago despues de un followup |
| `ULTIMO MENSAJE` | DateTime | Timestamp del ultimo mensaje del user (se actualiza automatico en cada mensaje entrante) |
| `AGENT_ACTUAL` | Texto | IVAN o AURORA |

### Ventana 24h — ahora directamente desde Airtable

Desde el 13 de mayo 2026, el campo `ULTIMO MENSAJE` se actualiza automaticamente cada vez que un lead escribe. Para encontrar leads con ventana abierta:

```
filterByFormula: IS_AFTER({ULTIMO MENSAJE}, DATEADD(NOW(), -24, "hours"))
```

Ya no es necesario consultar PostgreSQL para verificar ventana 24h.

### Fuente secundaria: PostgreSQL (Railway)

La base de datos de produccion tiene la tabla `mensajes` con el historial completo de cada conversacion. Se usa para:
- Historial completo de conversaciones (backup, no necesario para ventana 24h)
- Saber si un lead respondio o no despues de un FU
- Endpoint: `GET /conversacion/{telefono}` con header `X-ADMIN-KEY`

---

## 2. Como seleccionar la audiencia

### Paso 1 — Definir el universo

Elegir que leads queremos contactar segun su estado:

| Audiencia | Formula Airtable | Descripcion |
|-----------|------------------|-------------|
| Todos los leads recientes | `IS_AFTER(CREATED_TIME(), DATEADD(NOW(), -48, "hours"))` | Leads de las ultimas 48h |
| Solo CONSULTA | `{CONVERSION}="CONSULTA"` | No respondieron o solo consultaron |
| Solo CONTACTADO | `{CONVERSION}="CONTACTADO"` | Ivan ya les mando datos bancarios |
| CONSULTA + CONTACTADO | `OR({CONVERSION}="CONSULTA", {CONVERSION}="CONTACTADO")` | Todos los que no pagaron |
| Ya recibieron FU1 | `{1ER FOLLOWUP}=TRUE()` | Para enviar FU2 |
| Respondieron FU1 | `{RESPONDIO FU1}=TRUE()` | Ventana reabierta, candidatos a FU2 |
| Nunca recibieron FU | `NOT({1ER FOLLOWUP})` | Para primer contacto masivo |

### Paso 2 — Filtrar por ventana 24h de WhatsApp

**CRITICO:** Meta solo permite enviar mensajes a numeros que escribieron en las ultimas 24 horas (ventana de conversacion). Si la ventana esta cerrada, el mensaje falla silenciosamente.

**Como verificar ventana (desde 13 mayo 2026):**

Directo desde Airtable con el campo `ULTIMO MENSAJE`:
```
Formula combinada (CONSULTA/CONTACTADO + ventana abierta):
AND(
  OR({CONVERSION}="CONSULTA", {CONVERSION}="CONTACTADO"),
  IS_AFTER({ULTIMO MENSAJE}, DATEADD(NOW(), -24, "hours"))
)
```

**Metodo anterior (legacy, ya no necesario):**
Consultar PostgreSQL por mensajes con `role="user"` y `timestamp > (ahora - 24h)`

### Paso 3 — Separar en Grupo A y Grupo B

| Grupo | Condicion | Metodo de envio |
|-------|-----------|-----------------|
| **Grupo A** — Ventana abierta | Ultimo msg del user < 24h | Envio directo via Meta API |
| **Grupo B** — Ventana cerrada | Ultimo msg del user > 24h | Links wa.me para que alguien los abra manualmente |

**Grupo B requiere una persona (ej: Lujan) que abra cada link wa.me y envie el mensaje.**

---

## 3. Historial de campanas

### CAMPANA 1: 1ER FOLLOWUP — Fotos
- **Fecha:** 5 de mayo 2026, 6:00 AM PY
- **Script:** `agent/main.py` → `_followup_fotos_oneshot()`
- **Audiencia:** ~147 leads creados despues del 4 mayo, sin 1ER FOLLOWUP
- **Contenido:**
  - Foto 1: `static/followup_caricatura.png` (3.2 MB) — caricatura del parque
  - Foto 2: `static/followup_foto.jpeg` (2.6 MB) — foto real del parque
  - Texto (si pago): "Aqui es donde {NOMBRE NINO} se transforma, este sabado entrenamos con todo!! Cupos casi llenos para este sabado, los esperamos!"
  - Texto (si no pago): "Aqui es donde tu hijo se transforma, este sabado entrenamos con todo!! Cupos casi llenos para este sabado, te gustaria confirmar la reserva?"
- **Resultado:** EXITOSO — ~147 enviados, tasa de respuesta ~17% (25 respondieron), 0 pagos
- **Registro Airtable:** campo `1ER FOLLOWUP` marcado como TRUE para cada lead

### CAMPANA 2: 2DO FOLLOWUP — Video
- **Fecha:** 6 de mayo 2026, 6:00 AM PY
- **Script:** `agent/main.py` → `_followup_video_oneshot()`
- **Audiencia:** Leads con ventana 24h abierta (escribieron despues del 5 mayo 5:00 UTC)
- **Contenido:**
  - Video: `static/followup_video.mp4` (8.9 MB, H.264) — video del parque
  - Texto: "Regalale a tu hijo un sabado que recordara por el resto de su vida. Quedan pocos lugares disponibles."
- **Resultado:** EXITOSO — todos los enviados recibidos
- **Registro Airtable:** no se marco campo adicional (solo envio)

### CAMPANA 3: FU Grupo A — Texto + Link IG
- **Fecha:** 7 de mayo 2026, 6:00 AM PY
- **Script:** `scripts/fu_grupo_a.py`
- **Audiencia:** 139 leads con ventana abierta (de `ventana_abierta.json`)
- **Contenido:**
  - Texto: "Feliz jueves! El sabado se acerca! Ya tenes tu lugar en Fenix?"
  - Link IG: https://www.instagram.com/p/DYB4KjQGuRO/?img_index=1
- **Resultado:** FALLIDO — token META incorrecto en .env local (EAAoBc8z... en vez de EAAORCCzn...)
- **Leccion:** SIEMPRE verificar token comparando .env local con reference_meta_prod_token.md

### CAMPANA 4: FU Grupo B — Links wa.me a Lujan
- **Fecha:** 7 de mayo 2026, 8:00 AM PY
- **Script:** `scripts/fu_grupo_b_lujan.py`
- **Audiencia:** 467 leads con ventana cerrada (de `ventana_cerrada.json`)
- **Contenido:** Links wa.me pre-cargados con mensaje de Lujan
  - Texto: "Buen dia! Te saluda Lujan de Fenix Kids! Estamos por cerrar los cupos para este sabado, avisame si queres agendarle a tu hijo."
  - Link IG: https://www.instagram.com/p/DYB4KjQGuRO/?img_index=1
- **Resultado:** FALLIDO — enviado a numero equivocado (Ilse en vez de Lujan)
- **Leccion:** Confirmar numeros con Ivan antes de ejecutar

### CAMPANA 5: FU Video Reprise
- **Fecha:** 8 de mayo 2026, 6:00 AM PY
- **Script:** `scripts/fu_video_8mayo.py`
- **Audiencia:** Leads con ventana 24h abierta (escribieron despues del 7 mayo 9:00 UTC)
- **Contenido:** Mismo que campana 2 (video + texto)
- **Mejoras:** Pre-flight test al admin, script independiente, token verificado
- **Resultado:** EN CURSO (pendiente confirmacion)

---

## 4. Media disponible

Archivos en `static/` del repo:

| Archivo | Tamano | Tipo | Descripcion | Usado en |
|---------|--------|------|-------------|----------|
| `followup_caricatura.png` | 3.2 MB | PNG | Caricatura del parque FENIX | Campana 1 |
| `followup_foto.jpeg` | 2.6 MB | JPEG | Foto real del parque FENIX | Campana 1 |
| `followup_video.mp4` | 8.9 MB | H.264 | Video del parque FENIX en accion | Campanas 2, 5 |

### Links de Instagram usados

| Link | Descripcion | Usado en |
|------|-------------|----------|
| https://www.instagram.com/p/DYB4KjQGuRO/?img_index=1 | Post IG de FENIX | Campanas 3, 4 |

---

## 5. Como se registra todo en Airtable

### Registro automatico (hecho por el codigo)

El servidor en `agent/main.py` registra automaticamente estos campos en LEADS FENIX:

| Evento | Campo actualizado | Valor | Funcion en main.py |
|--------|-------------------|-------|---------------------|
| FU masivo de fotos enviado | `1ER FOLLOWUP` | TRUE | `_followup_fotos_oneshot()` (linea ~5770) |
| Lead responde post-FU1 | `RESPONDIO FU1` | TRUE | Deteccion en webhook (linea ~2110) |
| Lead responde post-FU2 | `RESPONDIO FU2` | TRUE | Deteccion en webhook (linea ~2113) |
| Lead responde a cualquier FU | `FECHA FOLLOWUP` | Ahora (UTC) | Deteccion en webhook (linea ~2109) |
| FU individual enviado (loop 9AM) | `SEGUIMIENTOS` | +1 | `_incrementar_seguimiento()` (linea ~3571) |
| FU individual enviado | `FECHA FOLLOWUP` | Ahora (UTC) | `_incrementar_seguimiento()` (linea ~3572) |
| Ivan manda datos bancarios | `SEGUIMIENTOS` | 0 (reset) | `_resetear_seguimiento()` (linea ~3556) |
| Ivan manda datos bancarios | `FECHA FOLLOWUP` | Ahora (UTC) | `_resetear_seguimiento()` (linea ~3556) |
| No respondio FU1 tras 24h | `CONVERSION` | DESCARTADO | `_ejecutar_followup()` (linea ~3665) |
| No respondio FU2 tras 24h | `CONVERSION` | DESCARTADO | `_ejecutar_followup()` (linea ~3670) |
| 3 seguimientos completados | `CONVERSION` | DESCARTADO | `_ejecutar_followup()` (linea ~3725) |

### Loop automatico de seguimiento individual

El sistema tiene un loop (`_followup_loop()`) que corre a las **9:00 AM PY todos los dias**:

1. Busca leads con `CONVERSION=CONTACTADO` y `SEGUIMIENTOS < 3`
2. Verifica que pasaron 24h desde `FECHA FOLLOWUP`
3. Verifica ventana 24h: FU2 solo si `RESPONDIO FU1=TRUE`, FU3 solo si `RESPONDIO FU2=TRUE`
4. Genera mensaje personalizado con Claude (Ivan) segun numero de seguimiento:
   - **FU1 (SEGUIMIENTOS=0):** "recordar que tiene el lugar reservado, mandar comprobante"
   - **FU2 (SEGUIMIENTOS=1):** "agendar un sabado inolvidable, ofrecer ayuda"
   - **FU3 (SEGUIMIENTOS=2):** "ultimo seguimiento, necesito confirmar"
5. Envia el mensaje, incrementa SEGUIMIENTOS, espeja en Telegram

**IMPORTANTE:** Este loop esta **DESACTIVADO** por norma (feedback_no_auto_fu.md). Los FU masivos se hacen manualmente con aprobacion de Ivan.

---

## 6. Como sacar estadisticas

### Desde Airtable (formulas utiles)

```
Total leads con 1ER FOLLOWUP:
  filterByFormula: {1ER FOLLOWUP}=TRUE()

Leads que respondieron al FU1:
  filterByFormula: {RESPONDIO FU1}=TRUE()

Leads que respondieron al FU2:
  filterByFormula: {RESPONDIO FU2}=TRUE()

Leads con seguimiento individual activo:
  filterByFormula: NOT({FECHA FOLLOWUP}=BLANK())

Leads CONTACTADO esperando pago:
  filterByFormula: {CONVERSION}="CONTACTADO"

Leads DESCARTADOS por no responder FU:
  filterByFormula: AND({CONVERSION}="DESCARTADO", {SEGUIMIENTOS}>=1)

Tasa de respuesta FU1:
  Dividir: count({RESPONDIO FU1}=TRUE()) / count({1ER FOLLOWUP}=TRUE())
```

### Desde el servidor (endpoints admin)

Todos requieren header `X-ADMIN-KEY: 23ebc7b3d716f558f4ba53a4b3f000dbceb09b350aa5a65fc3f6475227a1e8d9`

| Endpoint | Que devuelve |
|----------|--------------|
| `GET /resumen-followup` | Resumen completo: en curso, respondieron, descartados, pagaron post-FU |
| `GET /conversacion/{telefono}` | Historial completo de un lead (para verificar si respondio) |
| `GET /debug/{telefono}` | Estado actual: agente, modo, familia_id, ultimos 5 mensajes |
| `GET /stats` | Estadisticas generales de conversiones |

### Estadisticas actuales (13 mayo 2026)

| Metrica | Valor |
|---------|-------|
| Leads con 1ER FOLLOWUP | 100+ |
| RESPONDIO FU1 | 24 |
| RESPONDIO FU2 | 0 |
| Con FECHA FOLLOWUP (sistema individual) | 100+ |
| SEGUIMIENTOS >= 1 | 22 |
| SEGUIMIENTOS >= 2 | 0 |
| SEGUIMIENTOS = 3 | 0 |

---

## 7. Checklist para preparar un FU masivo

1. **Definir audiencia** — que formula de Airtable usar
2. **Verificar ventana 24h** — consultar PostgreSQL, separar Grupo A (abierta) y Grupo B (cerrada)
3. **Definir contenido** — texto + media (video/foto/link)
4. **Verificar token META** — comparar `.env` local con `reference_meta_prod_token.md`
   - Token correcto: `EAAORCCznM1IBR...`
   - Phone Number ID: `1005063086033214`
5. **Pre-flight** — enviar test al admin (595982790407) ANTES del masivo
6. **Aprobar con Ivan** — NUNCA enviar sin aprobacion explicita
7. **Ejecutar** — correr script con rate limiting (3s entre leads)
8. **Registrar en bitacora** — actualizar `BITACORA FOLLOWUP FENIX.md`
9. **Medir resultados** — verificar `/resumen-followup` al dia siguiente

---

## 8. Scripts disponibles

| Script | Ubicacion | Proposito |
|--------|-----------|-----------|
| FU fotos oneshot | `agent/main.py` → `_followup_fotos_oneshot()` | Envio masivo de 2 fotos + texto |
| FU video oneshot | `agent/main.py` → `_followup_video_oneshot()` | Envio masivo de video + texto |
| FU Grupo A directo | `scripts/fu_grupo_a.py` | Texto directo a ventana abierta |
| FU Grupo B wa.me | `scripts/fu_grupo_b_lujan.py` | Links para envio manual |
| FU Video reprise | `scripts/fu_video_8mayo.py` | Video + texto con pre-flight |
| Cargar seguimiento | `scripts/cargar_seguimiento_9may.py` | Carga datos de seguimiento |
| Enviar seguimiento | `scripts/enviar_seguimiento_9may.py` | Envio de seguimiento 9 mayo |
| Reenviar v2 | `scripts/reenviar_v2.py` | Reenvio con mejoras |
| Reenviar largos | `scripts/reenviar_largos.py` | Reenvio de mensajes largos |
| Export conversaciones | `scripts/export_conversaciones.py` | Exportar historial a archivos |

---

## 9. Reglas de oro

1. **NUNCA enviar FU masivo sin aprobacion de Ivan** — feedback_no_auto_fu.md
2. **SIEMPRE verificar token META antes de masivos** — feedback_verificar_token_meta.md
3. **SIEMPRE hacer pre-flight al admin** — si falla, abortar todo
4. **Respetar ventana 24h de WhatsApp** — enviar solo a ventana abierta o usar wa.me para cerrada
5. **Registrar en [[SALSA SOUL/DORITA/INTERFAZ DORITA/BITACORA|bitacora]]** — fecha, hora, contenido, cantidad, resultado
6. **Rate limiting** — minimo 3 segundos entre cada lead
7. **Los mensajes de FU masivo NO quedan en la DB** — los scripts bypasean el servidor (pendiente fix)
