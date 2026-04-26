# ENGRANAJE REDES SOCIALES + REFERIDOS + FOLLOW-UP

> Documento que registra el proceso de diseño completo.
> Desde la idea inicial hasta la decisión final.
> Fecha: 2026-04-26

---

## 1. Cómo empezó: recordatorios post-Calendar

Con Google Calendar eliminado, arrancamos buscando **plantillas WhatsApp para recordatorios de clase**. La pregunta del usuario fue: "¿cómo manejan esto las empresas?" y "¿qué estrategia usa Hormozi?"

---

## 2. Lo que descubrimos de Hormozi y la industria

### Industria (WhatsApp Business)
- Secuencia estándar: confirmación inmediata → recordatorio 24h antes → último empujón 2h antes
- WhatsApp tiene 98% de apertura vs 20% del email
- Reducción de no-shows: 35-50% con recordatorios automáticos
- Clave: ofrecer **reagendar fácil** (si puede cambiar en 10 segundos, lo hace en vez de no venir)

### Hormozi (Gym Launch / $100M Leads)
- Show rate promedio: 49%. Target: 70%+
- **Confirmación activa** ("respondé CONFIRMO") > recordatorio pasivo — principio de consistencia de Cialdini
- Follow-up agresivo: 5-7 toques, nunca el mismo mensaje, cada uno agrega valor
- Sunk cost: el pago adelantado genera compromiso, pero durante la espera hay que **subir la expectativa** con contenido
- Prueba: Hormozi usa gratuita (Free 6-Week Challenge), pero su modelo es USA con competencia feroz. FENIX cobra 90k descontable de la primera cuota (modelo $100M Offers: riesgo percibido cero)

### Decisión: show rate post-pago no preocupa (si pagaron van a venir). El valor está en el **follow-up de contenido variado** para los que todavía no se inscribieron, y en un **sistema de referidos**.

---

## 3. Primera idea: follow-up semanal variado

Secuencia para leads post-prueba que no se inscribieron:

| Día | Tipo | Contenido |
|---|---|---|
| Lunes | Foto/video de la clase | "Mirá lo que hicieron los chicos este sábado" |
| Miércoles | Tip de desarrollo infantil | Contenido educativo de valor |
| Viernes | Testimonio de otro padre | Social proof real |
| Sábado AM | FOMO + invitación | "Hoy hay clase, todavía podés sumarte" |

**Estado:** idea válida, queda como P2. Se necesitan plantillas Meta para cada tipo.

---

## 4. Primera idea de referidos: pedir números en el chat

**Idea inicial:**
- Padre se inscribe → Aurora le pide 3 números de otros padres
- Sistema envía plantilla Meta al referido con un video del hijo del padre que refirió
- Por cada referido inscripto, el padre gana un mes de FENIX

**Evolución 1:** No solo post-inscripción, sino solo post-inscripción. El padre que ya se inscribió recomienda con convicción porque su hijo ya lo vive.

**Evolución 2:** No es Aurora quien pide los números — Ivan les pide **en persona** cuando vienen a FENIX. "Pasale todo a FENIX por WhatsApp." El sistema detecta los números automáticamente.

---

## 5. Idea del menú de Aurora para inscriptos

Cuando un padre inscripto escribe, Aurora muestra un menú fijo:

```
Hola [padre/apodo]! Gusto verte por acá!
Saludos a [hijo1] y [hijo2]

En qué te puedo ayudar?

1  Agendar entrenamiento
2  Fotos de [hijo/apodo]
3  Videos de [hijo/apodo]
4  Referidos
5  Instagram
6  Facebook
7  TikTok
8  YouTube
9  Threads
10 Escribime lo que necesites
```

---

## 6. Enviar fotos/videos directamente vs links

**Pregunta del usuario:** "¿puedo enviar el documento directo en vez de un link?"

**Respuesta:** Sí, es posible. Ya existe `enviar_imagen` y `subir_media` en el provider Meta. Solo falta `enviar_video`. WhatsApp soporta fotos hasta 5MB y videos hasta 16MB. Costo adicional = prácticamente cero (Meta cobra por conversación, no por media).

**Almacenamiento evaluado:**

| Opción | Pro | Contra |
|---|---|---|
| Google Drive | Gratis, links permanentes | URLs no directas, necesita API |
| Cloudinary | URLs permanentes, optimiza | Free tier 25GB |
| Airtable attachments | Ya lo tiene | URLs expiran cada 2h |

**Decisión:** Google Drive como almacenamiento, descarga + reenvío por WhatsApp.

---

## 7. Evolución clave: vincular contenido de redes con niños

**Idea del usuario:** No solo enviar fotos guardadas — vincular cada publicación de redes sociales con los niños que aparecen. Cuando se publica, el padre recibe WhatsApp automático: "Tu hijo aparece en este posteo!"

Esto logra dos cosas:
1. El padre recibe contenido de su hijo (valor emocional)
2. El padre accede a la red social (engagement + followers)

**Pregunta crítica:** ¿cómo vincular automáticamente los niños con cada posteo?

---

## 8. Opciones de vinculación evaluadas

### Opción A — Tags en el caption de Postiz
Agregar `#fenix_benja #fenix_mati` al caption. Fenix los intercepta del webhook y los matchea.
- Pro: cero trabajo extra
- Contra: depende de que Postiz envíe el caption en el webhook

### Opción B — Marcar en Airtable manualmente
Postiz publica → Fenix crea registro → usuario selecciona niños en Airtable (3 clicks).
- Pro: imposible equivocarse
- Contra: paso manual (10 segundos)

### Opción C — Híbrida
Tags si los pone, si no los pone Airtable queda para completar.

---

## 9. La pieza que lo resolvió: Editor Pro Max + nombres de archivos

**Contexto descubierto:** Ivan tiene un proyecto llamado Editor Pro Max que:
- Edita videos/fotos con Claude Code + Remotion
- Publica en redes sociales via Postiz (Instagram, TikTok, YouTube, Facebook, Threads)
- Postiz corre como servicio Docker con APIs de todas las redes conectadas

**Insight del usuario:** Las fotos en las carpetas YA TIENEN el nombre/apodo del niño como nombre de archivo:

```
Carpeta: SAB 2-4-26 - 09.30/
  benja_lafuente_01.jpg
  mati_gonzalez_01.jpg
  sofi_perez_01.jpg
```

**Flujo resuelto:** Claude de Editor Pro Max lee los nombres de archivos → sabe qué niños aparecen → genera los tags automáticamente en el caption.

---

## 10. Evaluación: webhook Postiz vs Airtable como puente

### Webhook directo Postiz → Fenix
- Postiz publica → webhook POST a Fenix con link + caption
- Riesgo: no está 100% confirmado que el payload incluya caption con tags

### Airtable como puente (DECISIÓN FINAL)
- Claude de Postiz publica + crea registro en CONTENIDO FENIX (Airtable) con link + niños vinculados
- Fenix hace polling o webhook de Airtable → detecta registros nuevos → envía WhatsApp
- Ventaja: Airtable ya es el centro de datos, todo queda registrado, no depende del webhook de Postiz

---

## 11. Diseño final del sistema

### Estrategia de ventana abierta: CONTACTO DIARIO

**Objetivo:** mantener la ventana de 24h de WhatsApp SIEMPRE abierta con cada padre inscripto. Si le escribís todos los días con contenido de valor, nunca perdés la ventana. Esto significa que podés enviar mensajes sin plantilla Meta (gratis) porque el padre siempre tiene una conversación activa.

**Calendario semanal de contenido — una red diferente por día:**

| Día | Red social | Tipo de mensaje |
|---|---|---|
| **Lunes** | Instagram | "Hola [padre]! Mirá nuestro último posteo en Instagram [link]" |
| **Martes** | Facebook | "Hola [padre]! Nueva publicación en Facebook [link]" |
| **Miércoles** | TikTok | "Hola [padre]! Nuevo video en TikTok [link]" |
| **Jueves** | YouTube | "Hola [padre]! Nuevo contenido en YouTube [link]" |
| **Viernes** | Threads | "Hola [padre]! Mirá esto en Threads [link]" |
| **Sábado** | Fotos del día | Fotos de la clase del día (directo en el chat) |
| **Domingo** | Videos del sábado | Videos de la clase de ayer (directo en el chat) |

**Capa adicional: "TU HIJO APARECE"**

Cuando un posteo incluye fotos/videos donde aparece un niño específico, ese padre recibe un mensaje **diferenciado** además del mensaje diario genérico:

```
Mensaje genérico (todos los padres):
"Hola [padre]! Mirá nuestro nuevo posteo en Instagram [link]"

Mensaje personalizado (padre cuyo hijo aparece):
"Hola [padre]! Te cuento que [hijo] aparece en nuestro 
nuevo posteo de Instagram! Miralo acá [link]"
```

El personalizado tiene prioridad — si el hijo aparece, se envía ese en vez del genérico. Si no aparece en ningún posteo del día, recibe el genérico.

**Beneficios de esta estrategia:**
1. **Ventana 24h siempre abierta** — si el padre responde (aunque sea un emoji), la ventana se renueva gratis
2. **Engagement en todas las redes** — cada día empujás una red diferente, los followers crecen orgánicamente
3. **El padre se siente parte** — no es spam, es "mirá a tu hijo"
4. **Retención brutal** — el padre ve contenido de FENIX todos los días, es imposible que se olvide
5. **Referidos naturales** — el padre comparte el posteo donde sale su hijo, otros padres lo ven

**Sábado y domingo son especiales:**
- Sábado: Ivan saca fotos durante la clase → las sube nombradas con apodo_apellido → Claude de Postiz crea registro en CONTENIDO FENIX → Fenix envía directo a cada padre las fotos donde aparece su hijo
- Domingo: mismo flujo pero con los videos editados del día anterior

**Sobre leads no inscriptos:**
Esta misma estrategia aplica como follow-up para leads post-prueba que no se inscribieron. Reciben el contenido genérico (sin el "tu hijo aparece" porque no están inscriptos), lo cual funciona como nurturing: ven lo que se pierden todos los días.

### Flujo completo

```
IVAN: nombra fotos con apodo_apellido.jpg
        |
CLAUDE (Editor Pro Max): lee nombres, arma carrusel/reel
        |
CLAUDE (Postiz): publica en redes + obtiene link del posteo
        |
CLAUDE (Postiz): crea registro en CONTENIDO FENIX (Airtable)
    -> link, red social, tipo, vincula NIÑOS por apodo/apellido
        |
FENIX (polling cada 5-10 min): detecta NOTIFICADO = falso
        |
FENIX determina tipo de mensaje:
    - Si el padre tiene hijo vinculado al posteo:
      "Hola [padre]! [hijo] aparece en este posteo de [red]! [link]"
    - Si no tiene hijo vinculado (mensaje diario genérico):
      "Hola [padre]! Mirá nuestro nuevo posteo en [red] [link]"
        |
FENIX: marca NOTIFICADO = verdadero
```

### Flujo sábado/domingo (fotos y videos directos)

```
SABADO durante la clase:
    IVAN saca fotos → las nombra apodo_apellido.jpg
        |
    Sube a carpeta Drive o directo a Airtable
        |
    FENIX detecta fotos nuevas
        |
    FENIX envía cada foto al padre del niño que aparece
    (directo en el chat, no link)

DOMINGO:
    IVAN edita videos del sábado en Editor Pro Max
        |
    Los sube nombrados igual
        |
    FENIX envía videos a cada padre
```

### Flujo de referidos

```
IVAN (en persona): le pide al padre inscripto que 
    pase números de otros padres a FENIX por WhatsApp
        |
PADRE escribe a FENIX: "Anota estos números: 
    0981123456, 0982234567, 0971345678"
        |
AURORA: detecta números, los guarda en REFERIDOS FENIX
    vinculados a la FAMILIA del padre
        |
AURORA -> padre: "Listo, les voy a escribir de tu parte.
    Por cada uno que se inscriba te regalamos un mes"
        |
FENIX: envia plantilla Meta a cada referido 
    (mensaje personalizado con nombre del padre que refirió)
        |
Si referido se inscribe -> padre original gana 1 mes
    -> Aurora le avisa
```

### Tablas nuevas en Airtable

#### CONTENIDO FENIX
| Campo | Tipo | Descripción |
|---|---|---|
| TITULO | Texto | Descripción del posteo |
| RED | Select | Instagram / TikTok / YouTube / Facebook / Threads |
| TIPO | Select | Reel / Posteo / Historia / Carrusel |
| LINK | URL | Link directo al posteo |
| NIÑOS | Link records (-> NIÑOS FENIX) | Niños que aparecen |
| FAMILIAS | Lookup (desde NIÑOS -> FAMILIA) | Se llena automático |
| NOTIFICADO | Checkbox | Fenix marca al enviar WhatsApps |
| FECHA | DateTime | Auto al crear |

#### REDES FENIX
| Campo | Tipo | Descripción |
|---|---|---|
| RED | Texto | Nombre de la red social |
| PERFIL | URL | Link al perfil de FENIX Kids |
| ICONO | Texto | Emoji identificador |

#### REFERIDOS FENIX
| Campo | Tipo | Descripción |
|---|---|---|
| TELEFONO REFERIDO | Texto | Número del padre referido |
| FAMILIA ORIGEN | Link record (-> FAMILIAS FENIX) | Familia que refirió |
| NOMBRE REFERIDOR | Texto | Nombre del padre que refirió |
| NOMBRE HIJO REFERIDOR | Texto | Nombre del hijo del referidor |
| ESTADO | Select | ENVIADO / RESPONDIO / PRUEBA / INSCRIPTO |
| MESES BONIFICADOS | Número | Acumulado por familia |
| FECHA ENVIO | DateTime | Cuándo se envió el mensaje |

### Plantillas Meta necesarias

**Para el contacto diario (ventana abierta):**
Si el padre respondió en las últimas 24h → mensaje gratis (service window), no necesita plantilla.
Si la ventana está cerrada (no respondió ayer) → necesita plantilla Meta.

| Plantilla | Uso | Variables |
|---|---|---|
| `contenido_diario` | Posteo genérico del día (lun-vie) | nombre_padre, red_social, link |
| `contenido_hijo` | Posteo donde aparece el hijo | nombre_padre, nombre_hijo, red_social, link |
| `fotos_clase` | Sábado: fotos de la clase | nombre_padre, nombre_hijo |
| `videos_clase` | Domingo: videos de la clase | nombre_padre, nombre_hijo |
| `referido_invitacion` | Contacto al padre referido | nombre_referidor, nombre_hijo_referidor |
| `referido_premio` | Avisar mes ganado | nombre_padre, meses_ganados |
| `recordatorio_clase` | Viernes pre-clase | nombre_padre, nombre_hijo, hora |

**Nota sobre ventana 24h:** El objetivo de la estrategia diaria es que el padre responda al menos una vez por semana (un emoji, un "jaja", un "qué lindo"). Eso mantiene la ventana abierta y reduce la necesidad de plantillas pagas. En la práctica, si mandás una foto del hijo, el padre SIEMPRE responde.

### Menú Aurora (padres inscriptos)

```
Hola [padre/apodo]! Gusto verte por acá!
Saludos a [hijo1] y [hijo2]

En qué te puedo ayudar?

1  Agendar entrenamiento
2  Fotos de [hijo/apodo]
3  Videos de [hijo/apodo]
4  Referidos
5  Instagram
6  Facebook
7  TikTok
8  YouTube
9  Threads
10 Escribime lo que necesites
```

### Costos estimados

**Escenario ideal (ventana siempre abierta):**

| Concepto | Costo |
|---|---|
| Mensajes dentro de ventana 24h | GRATIS |
| Google Drive API | Gratis |
| Claude API (no se usa para envío de media) | $0 |
| Railway (ancho de banda) | Marginal |
| **Total si la ventana se mantiene abierta** | **~$0/semana** |

**Escenario conservador (50% de padres no responden):**

| Concepto | Costo |
|---|---|
| Plantilla Meta (marketing) | ~$0.04 USD por mensaje |
| 15 padres x 7 días x 50% plantilla | ~$2.10 USD/semana |
| Fotos/videos sábado-domingo (estos siempre generan respuesta) | ~$0 (ventana abierta) |
| **Total conservador** | **~$2 USD/semana** |

**Nota:** Las fotos del hijo son el ancla. Cuando el padre recibe "mirá a [hijo] entrenando", responde SIEMPRE. Eso reabre la ventana para toda la semana. Los mensajes lun-vie de redes sociales van gratis dentro de esa ventana.

---

## 12. Orden de ejecución

### En FENIX KIDS AGENT (este proyecto)
1. Crear tablas en Airtable (CONTENIDO, REDES, REFERIDOS)
2. Código: polling CONTENIDO FENIX + envío WhatsApp a padres
3. Código: detección de números en chat Aurora + tabla REFERIDOS
4. Código: envío plantilla Meta a referidos
5. Código: menú Aurora para inscriptos
6. Crear plantillas en Meta Business
7. Código: recordatorio viernes pre-clase

### En EDITOR PRO MAX / POSTIZ (otro proyecto)
1. Actualizar CLAUDE.md: leer nombres de archivos -> generar tags #fenix_[apodo]
2. Después de publicar: crear registro en CONTENIDO FENIX (Airtable) con link + niños

---

## 13. Referencias consultadas

- Hormozi Gym Launch: show rate, follow-up agresivo, Free 6-Week Challenge
- $100M Leads: principio de consistencia, 5-7 toques de follow-up
- Industria WhatsApp Business: 98% apertura, secuencia confirmación/recordatorio/empujón
- Postiz API: POST /public/v1/posts, webhooks disponibles
- Editor Pro Max: Remotion + Claude Code, integrado con Postiz
