up:: [[FENIX KIDS]]

# BITACORA HISTORICA — Follow-Up Masivos FENIX KIDS

> Registro completo de todas las campanas de follow-up masivo realizadas.
> Incluye: texto enviado, numeros, media, horarios, resultados.

---

## Resumen ejecutivo

Se realizaron **5 campanas de Follow-Up** entre el 5 y 8 de mayo de 2026:

| # | Campana | Fecha | Hora PY | Leads | Estado |
|---|---------|-------|---------|-------|--------|
| 1 | 1ER FOLLOWUP — Fotos | 5 mayo | 6:00 AM | ~147 | EXITOSO |
| 2 | 2DO FOLLOWUP — Video | 6 mayo | 6:00 AM | ventana abierta | EXITOSO |
| 3 | FU Grupo A — Texto directo | 7 mayo | 6:00 AM | 139 | FALLIDO (token incorrecto) |
| 4 | FU Grupo B — Links wa.me a Lujan | 7 mayo | 8:00 AM | 467 | FALLIDO (numero equivocado) |
| 5 | FU Video — Reprise | 8 mayo | 6:00 AM | ventana abierta | EN CURSO |

---

## CAMPANA 1: 1ER FOLLOWUP — FOTOS

**Fecha:** 5 de mayo 2026, 6:00 AM PY
**Script:** `agent/main.py` funcion `_followup_fotos_oneshot()`
**Tipo:** OneShot automatico (se ejecuto una vez al arrancar el servidor)

### Audiencia
- Leads creados DESPUES del 4 de mayo 10:00 UTC
- Que NO tengan checkbox "1ER FOLLOWUP" marcado en Airtable
- Formula: `AND(IS_AFTER({FECHA CREACION},'2026-05-04T10:00:00.000Z'),NOT({1ER FOLLOWUP}))`
- Total: ~147 leads

### Contenido enviado

**Media:**
- Foto 1: `static/followup_caricatura.png` (3.2 MB)
- Foto 2: `static/followup_foto.jpeg` (2.6 MB)

**Texto (si el lead YA PAGO):**
```
Aqui es donde {NOMBRE NINO} se transforma, este sabado entrenamos con todo!!
Cupos casi llenos para este sabado, los esperamos! 🔥🌳
```

**Texto (si el lead NO pago):**
```
Aqui es donde tu hijo se transforma, este sabado entrenamos con todo!!
Cupos casi llenos para este sabado, te gustaria confirmar la reserva? 🔥🌳
```

### Timing
- 2 segundos entre foto 1 y foto 2
- 2 segundos entre foto 2 y texto
- 3 segundos entre cada lead

### Resultado
- Enviados: ~147
- Exitosos: ~147
- Campo "1ER FOLLOWUP" marcado en Airtable para cada lead exitoso
- Espejado en Telegram: `"📢 1ER FOLLOWUP: [📸 2 fotos + texto enviado]"`
- Tasa de respuesta: **~17%** (25 de ~147 respondieron)
- Pagos nuevos: **0**

---

## CAMPANA 2: 2DO FOLLOWUP — VIDEO

**Fecha:** 6 de mayo 2026, 6:00 AM PY
**Script:** `agent/main.py` funcion `_followup_video_oneshot()`
**Tipo:** OneShot automatico

### Audiencia
- Leads con ventana 24h abierta (escribieron DESPUES del 5 de mayo 5:00 UTC)
- Consultado en PostgreSQL: mensajes con `role="user"` y `timestamp > 2026-05-05 05:00:00`
- Excluido: admin (595982790407)

### Contenido enviado

**Media:**
- Video: `static/followup_video.mp4` (8.9 MB, H.264)
- Subido UNA sola vez a Meta, media_id reutilizado para todos

**Texto:**
```
Regalale a tu hijo un sabado que recordara por el resto de su vida.
Quedan pocos lugares disponibles.
```

### Timing
- 2 segundos entre video y texto
- 3 segundos entre cada lead

### Resultado
- Enviados: leads con ventana abierta (cantidad exacta no documentada)
- Exitosos: todos los enviados
- Espejado en Telegram

---

## CAMPANA 3: FU GRUPO A — TEXTO DIRECTO

**Fecha:** 7 de mayo 2026, 6:00 AM PY
**Script:** `scripts/fu_grupo_a.py`
**Tipo:** Script manual ejecutado por Ivan

### Audiencia
- Fuente: `ventana_abierta.json`
- Total: **139 leads** con ventana 24h abierta

### Texto enviado
```
Feliz jueves! El sabado se acerca! Ya tenes tu lugar en Fenix?

https://www.instagram.com/p/DYB4KjQGuRO/?img_index=1
```

### Timing
- Espera hasta 6:00 AM PY
- 1 segundo de pausa entre mensajes

### Lista completa de numeros (139)
```
595982534337  595992923848  595992678318  595994206823  595983707238
595982295868  595983107579  595983617232  595992722848  595972191222
595983975531  595974300500  595982872160  595986475503  595981650486
595994810938  595985637282  595982525666  595994138716  595985977366
595981303150  595983047547  595971144130  595976228402  595971663221
595983735050  595983985400  595981151921  595991664366  595981557971
595961801255  595992433604  595986783975  595992286589  595992537773
595983834819  595981972794  595986356167  595975531338  595991530047
595991946447  595993609912  595976670947  595987133100  595986566403
595982175028  595982518813  595961819320  595983026408  595985903084
595981239294  595981367594  595961351352  595981293690  595991386649
595991749452  595981344764  595991221124  595991423915  595981986595
595983368247  595991624210  595991878228  595984051064  595994479963
595981278168  595974529258  595971795501  595983124604  595985571851
595986436168  595991851864  595986481243  595971725530  595982346838
595985426006  595983191291  595981992530  595981818768  595971361041
595976753625  595991437217  595993346513  595992206157  595981542557
595992311596  595981414669  595985153874  595994273978  595982490935
595961636826  595971945155  595974956401  595986536602  595991805949
595981321834  595985945576  595983221799  595981066007  595976658521
595986101199  595986735599  595973984466  595982568993  595972901887
595991833100  595991746442  595983259059  595982995629  595983392490
595982256516  595992871470  595981760028  595974749834  595981331370
595985794783  595982562256  595982165717  595983241709  595983402885
595994557867  595976118281  595983441384  595992758488  595986380070
595971504568  595985499441  595986569092  595983477216  595972129451
595986738732  595981533190  595986405776  595982419803  595981517325
595976758863  595984508855  595971940892  595982207743
```

### Resultado
- **FALLIDO** — token META incorrecto en .env local
- .env tenia `EAAoBc8z...` (invalido) en vez del token real `EAAORCCzn...`
- 0/139 exitosos en primer intento
- Diagnostico tardo ~5 horas
- Reintentado tras correccion de .env — resultado final no confirmado

---

## CAMPANA 4: FU GRUPO B — LINKS WA.ME A LUJAN

**Fecha:** 7 de mayo 2026, 8:00 AM PY
**Script:** `scripts/fu_grupo_b_lujan.py`
**Tipo:** Script manual — envia links a Lujan para que ella los abra y envie

### Audiencia
- Fuente: `ventana_cerrada.json` / `links_lujan.json`
- Total: **467 leads** con ventana 24h cerrada
- Estos leads NO pueden recibir mensaje directo de FENIX (ventana Meta expirada)
- Solucion: Lujan abre cada link wa.me y envia el mensaje ella misma

### Formato de envio
- **47 batches de 10 links** cada uno
- Cada batch = 1 mensaje de WhatsApp a Lujan
- Intervalo: 1 batch cada 10 minutos
- Duracion total: 47 x 10 min = ~7h 50min (8:00 AM a ~15:50 PM PY)

### Texto de cada batch
```
📋 Batch 1/47 — 10 contactos

1. [Nombre o ultimos 4 digitos]
https://wa.me/595XXXXXXXXX?text=Buen%20dia%21%20Te%20saluda%20Lujan%20...

2. [Siguiente contacto]
https://wa.me/595XXXXXXXXX?text=Buen%20dia%21%20Te%20saluda%20Lujan%20...

[... 10 links por batch]
```

### Mensaje pre-cargado en cada link wa.me
```
Buen dia! Te saluda Lujan de Fenix Kids! Estamos por cerrar los cupos
para este sabado, avisame si queres agendarle a tu hijo.

https://www.instagram.com/p/DYB4KjQGuRO/?img_index=1
```

### Destinatario
- **INCORRECTO:** `595982844548` (Ilse Estigarribia, esposa de Elias)
- **CORRECTO:** `595981189205` (Lujan)

### Resultado
- **FALLIDO** — todos los 467 links se enviaron a persona equivocada
- Numero corregido pero NO se reinento
- Campana cancelada

---

## PROBLEMAS Y LECCIONES

### Problema 1: Token META incorrecto (Grupo A)
- **Causa:** .env local tenia un token viejo/invalido
- **Impacto:** 139 mensajes perdidos
- **Leccion:** Verificar token META comparando .env local con reference antes de masivos
- **Regla creada:** `feedback_verificar_token_meta.md`

### Problema 2: Numero de Lujan incorrecto (Grupo B)
- **Causa:** Se uso numero equivocado en el script
- **Impacto:** 467 links enviados a persona equivocada
- **Leccion:** Confirmar numeros con Ivan antes de ejecutar

### Problema 3: Follow-up automatico no autorizado
- **Causa:** Loop automatico (`followup_loop`, 9 AM diario) generaba mensajes sin aprobacion
- **Impacto:** Enviaba "tenes tu lugar, manda el comprobante" sin contexto
- **Fix:** Desactivado. Nueva norma: FU manual, preparado por Ivan a las 6 AM
- **Regla creada:** `feedback_no_auto_fu.md`

### Problema 4: Mensajes FU no quedan en DB
- **Causa:** Scripts bypasean el servidor (usan Meta API directamente)
- **Impacto:** Mensajes masivos no aparecen en historial del lead
- **Pendiente:** Guardar mensajes del FU en DB via POST al servidor

---

## MEDIA UTILIZADA

| Archivo | Tamano | Tipo | Usado en |
|---------|--------|------|----------|
| `static/followup_caricatura.png` | 3.2 MB | PNG | Campana 1 (foto 1) |
| `static/followup_foto.jpeg` | 2.6 MB | JPEG | Campana 1 (foto 2) |
| `static/followup_video.mp4` | 8.9 MB | H.264 | Campana 2 |

---

## ARCHIVOS DE DATOS

| Archivo | Registros | Descripcion |
|---------|-----------|-------------|
| `ventana_abierta.json` | 139 | Leads con ventana 24h abierta (Grupo A) |
| `ventana_cerrada.json` | 467 | Leads con ventana cerrada (Grupo B) |
| `links_lujan.json` | 467 | URLs wa.me pre-generadas para Lujan |
| `grupo_a_fenix.json` | 139 | Datos de Grupo A |
| `grupo_b_lujan.json` | 467 | Datos de Grupo B |
| `sin_mensajes.json` | 2 | Leads sin historial |
| `leads_para_fu.json` | 0 | No utilizado |

---

## SCRIPTS

| Script | Funcion | Ubicacion |
|--------|---------|-----------|
| 1ER FU Fotos | `_followup_fotos_oneshot()` | `agent/main.py` |
| 2DO FU Video | `_followup_video_oneshot()` | `agent/main.py` |
| Grupo A directo | Script independiente | `scripts/fu_grupo_a.py` |
| Grupo B wa.me links | Script independiente | `scripts/fu_grupo_b_lujan.py` |

---

## METRICAS CONSOLIDADAS

| Metrica | Valor |
|---------|-------|
| Total leads contactados (intentados) | ~753 |
| Exitosos confirmados | ~147 (solo campana 1) |
| Fallidos por error tecnico | ~606 (campanas 3 y 4) |
| Tasa de respuesta (campana 1) | ~17% |
| Pagos generados por FU | 0 |
| Campanas exitosas | 2 de 4 |
| Campanas fallidas | 2 de 4 |

---

## CAMPANA 5: FU VIDEO — REPRISE (8 de mayo)

**Fecha:** 8 de mayo 2026, 6:00 AM PY
**Script:** `scripts/fu_video_8mayo.py`
**Tipo:** Script manual, corriendo en background

### Audiencia
- Leads con ventana 24h abierta (mensajes user despues de 7 mayo 9:00 UTC)
- Consultado en PostgreSQL (tabla Mensaje)
- Excluido: admin (595982790407)
- Total: pendiente (se calcula al momento de ejecucion)

### Contenido enviado

**Media:**
- Video: `static/followup_video.mp4` (8.9 MB, H.264)
- Subido UNA sola vez a Meta, media_id reutilizado

**Texto:**
```
Regalale a tu hijo un sabado que recordara por el resto de su vida.
Quedan pocos lugares disponibles.
```

### Timing
- Espera hasta 6:00 AM PY
- Pre-flight: test al admin antes del loop masivo
- 2 segundos entre video y texto
- 3 segundos entre cada lead

### Mejoras vs campana 2
- Pre-flight test al admin (si falla, aborta todo)
- Script independiente (no toca servidor de prod)
- Token META verificado contra reference antes de ejecutar

### Resultado
- Resultado no confirmado

---

## CAMPANA 6: FU VIDEO — 13 de mayo

**Fecha:** 13 de mayo 2026, 13:36 PY
**Script:** `scripts/fu_video_13mayo.py`
**Tipo:** Script manual ejecutado por Ivan

### Audiencia
- Leads CONSULTA/CONTACTADO creados en ultimas 24h (Airtable CREATED_TIME)
- Excluido: admin (595982790407)
- Total: **54 leads**

### Contenido enviado

**Media:**
- Video: `static/followup_video.mp4` (8.9 MB, H.264)
- Subido UNA sola vez a Meta, media_id=1464100364912861

**Texto:**
```
Regalale a tu hijo un sabado que recordara por el resto de su vida. Quedan pocos lugares disponibles.
```

### Timing
- Pre-flight test al admin (OK)
- 2 segundos entre video y texto
- 3 segundos entre cada lead
- Duracion total: ~6 minutos (13:36 a 13:42 PY)

### Resultado
- **EXITOSO** — 54/54 enviados, 0 fallidos
- Token verificado contra reference antes de ejecutar
- Pre-flight al admin exitoso
- Tasa de respuesta: pendiente
