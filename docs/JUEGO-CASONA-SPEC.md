# EL JUEGO DE LA CASONA — spec base (idea capturada 04/07/2026)
> Idea de Iván. Estado: PARQUEADA en PRIORIDAD (Genesis va primero), pero el 05/07/2026
> se definió el MODELO DE NEGOCIO v2 completo y hay un PROTOTIPO JUGABLE. Ver secciones
> "MODELO DE NEGOCIO v2" y "ESTADO DEL PROTOTIPO" al final. Este doc no pierde nada.

## La idea (en palabras de Iván)
Fenix Academy vive en una mansión de 3.000 m² frente al río: pileta, cancha de básquet,
cancha de vóley, zona de árboles con casa del árbol (castillo de los niños), espacio para
correr alrededor de la casa. Niños de 3 a 12 años.

Crear un **juego que se vive dentro de la casona**: cada niño inscripto tiene su avatar y
sigue jugando desde su casa — "Fenix Academy en tu casa". Ganan **monedas** haciendo
desafíos físicos filmados (parada de manos, flexiones, abdominales). Las monedas se
canjean por **premios reales** (remeras, premios en la casona). Cada semana hay una
**historia diferente** que juegan en la app y después vienen a vivirla en la realidad
(búsqueda del tesoro, desafíos en la casa del árbol).

**Por qué es potente:** único en Paraguay, retención brutal ("se van a morir por querer
volver"), convierte la distancia/lejanía de la casona en destino, y engancha a los papás
(los videos de desafíos son contenido orgánico para redes con permiso).

## Decisión estratégica (auditoría 04/07)
NO construir la app ahora — el foco es Genesis + contenido + relanzamiento. PERO hay un
**MVP sin app** que usa la infraestructura ya construida y cuesta 1-2 días:

### Fase 0 — "El juego por WhatsApp" (MVP, 1-2 días, sin app nueva)
- El papá/mamá manda el **video del desafío al agente de Fenix** (Aurora/Nixie) por WhatsApp
  — el canal ya existe y los papás ya lo usan.
- El agente registra el desafío cumplido → suma **monedas en Airtable** (tabla nueva
  MONEDAS/DESAFIOS vinculada a ALUMNOS).
- **Desafío de la semana:** se anuncia con el envío masivo ya existente (plantilla aprobada)
  + la historia de la semana como texto/imagen.
- **Tabla de posiciones semanal** generada por el agente (los loops de resúmenes ya existen).
- Canje de monedas: el sábado en la casona, contra la tabla de Airtable.
- Validación del video: manual al principio (Iván/Lujan aprueban con un botón en el espejo
  Telegram o Command Center); con volumen, visión IA (Haiku) como pre-filtro.
- **Con esto se valida si el juego engancha ANTES de invertir en una app.**

### Fase 1 — PWA con avatares (cuando el MVP valide, construir con Opus)
- PWA (como el Command Center / app uber ya hechos): avatar por niño, monedas, historia
  semanal ilustrada, ranking, galería de logros.
- Generación de historias semanales con IA (texto + imágenes de la casona tematizadas).
- QR de acceso ya existente (lector HikVision) puede marcar "misiones presenciales" cumplidas.
- Integración con asistencias (salsa-soul-acceso registra ASISTENCIAS) → monedas por asistir.

### Fase 2 — El diferenciador completo
- Historias con capítulos que solo se desbloquean viniendo a la casona (QR escondidos =
  búsqueda del tesoro real).
- Eventos especiales de temporada (campus verano dic-ene como "temporada 1").
- Tienda de premios gestionada en Airtable.

## Monedas por VALORES, no solo por ganar (clave del diseño)
La moneda NO premia al niño que ya es fuerte. Premia los valores que Fenix quiere formar.
Esto convierte el juego de competitivo en formativo — y es lo más difícil de copiar.

Se ganan monedas por:
- **Coraje** — intentó algo que le daba miedo (aunque no le salga).
- **Disciplina** — completó el desafío/circuito sin abandonar.
- **Compañerismo** — ayudó a otro niño.
- **Exploración** — encontró una pista escondida / misión presencial.
- **Mejora personal** — superó su propio registro anterior (no el de otros).
- **Respeto** — siguió instrucciones y cuidó el espacio.
- **Liderazgo** — guió a su equipo sin mandar mal.

Reglas de la economía:
- Las monedas NUNCA se compran con plata — solo se ganan entrenando/participando.
- El "Banco" (nombre tentativo: Banco de Brasas) deja ahorrar, gastar, donar al equipo o
  "invertir" (congelar una semana → bonus si vuelve el sábado siguiente = re-enganche).
- Premio principal = estatus/historia/logro. Premios físicos existen pero no son el alma:
  chicos (stickers, pulseras, parches) / medianos (remeras, gorras) / especiales (capitán,
  misión nocturna, mural Fenix, dormir en la casona).

## MODELO DE NEGOCIO v2 — El Reto Fénix (definido 05/07/2026, sesión con Opus)
La idea evolucionó de "juego de rastreo" a un EMBUDO COMPLETO de captación y retención.
El corazón físico sigue siendo el mismo (entrenar, circuitos en La Casona); la app le da
sentido, estatus y recompensa.

### El Reto Fénix — 5 días (puerta de entrada, GRATIS = lead magnet)
- Lead escribe → se le da la app → arranca su Reto de 5 días. CAMADA SEMANAL: todos
  arrancan el mismo lunes y se gradúan juntos el sábado (comunidad + ritual grupal).
- Lunes a viernes, en casa: 1 video por día con los ejercicios (10 flexiones, 10
  abdominales, 10 saltos, parada de manos 10s, 10 saltos estrella). Toda la familia empuja.
- FLEXIBLE: si falla un día lo recupera. La meta es completar los 5, no castigar el tropiezo.
- Completar los 5 = acceso al PRIMER ENTRENAMIENTO GRATIS (el sábado en La Casona).
- Es una MÁQUINA DE CONVERSIÓN, no solo un filtro: la familia invierte 5 días de esfuerzo
  ANTES de pagar → "pie en la puerta" → llegan al sábado ya comprometidos.

### La graduación = la clase de prueba (NO hay clase de prueba aparte)
- El sábado de graduación ES la primera experiencia presencial. No se mantiene una clase
  de prueba suelta — la graduación la reemplaza y es mejor (pico emocional).
- Ceremonia de la Capa: se le pone su CAPA BLANCA física delante de todos. Pasa de
  Aspirante a Guardián Fénix.

### Las Capas = los cinturones (motor de retención)
- La capa es FÍSICA (capa tipo superhéroe que Iván pone a los niños en el entrenamiento)
  Y DIGITAL (el avatar la lleva). Ese es el puente phygital, lo más difícil de copiar.
- Baratísima de producir, percepción altísima, y es marketing caminando (niños con capa
  Fénix por la ciudad).
- Colores = niveles, se ganan ENTRENANDO cada mes (acumulando puntos), NO ganándole a
  nadie: Blanca → Roja → Naranja → Dorada → Fénix.
- Regla de oro: la capa se GANA, no se compra. Protege el espíritu del proyecto.

### El pago — se vende en el pico emocional
- NO se vende durante los 5 días (son puro valor/emoción).
- Se vende en la CEREMONIA, con la capa puesta y la familia emocionada.
- Paquete: 5 sábados. Precio: **350 mil si se inscribe EN EL MOMENTO, 450 mil si lo deja
  para después** (ancla + urgencia; el 450 existe para que el 350 se vea como regalo).
  OJO: el 350 tiene que ser rentable por sí solo — casi todos se inscriben a ese precio.
- Retención: "a tu hijo le faltan X puntos para la Capa Roja — con el paquete la gana".

### El papá que no quiere el Reto ("quiero pagar ya") — DOS PUERTAS
- Nunca se rechaza plata. Se maneja así:
  - Papá frío/dudando → puerta del Reto gratis (el imán).
  - Papá decidido → paga ya, pero su hijo hace el Reto de 5 días igual, como su primera
    semana. Paga el ACCESO; la capa y el rango se los gana entrenando como todos.

### Avatar = robotitos Guardianes Fénix (el SVG dibujado quedó DESCARTADO)
- Estilo: los robotitos chibi 3D premium de `ivanlafuente-web/assets` (agente-fenix,
  agente-neo, agente-dorita) — negro/dorado, cara LED, con actitud. Espectaculares.
- Los 3 existentes están branded (Fénix/Neo/Dorita). Se necesita un SET genérico de
  Guardianes Fénix CON CAPA, variados (nene/nena, rubio/moreno/claro/oscuro).
- HECHO: Iván generó 10 Guardianes en ChatGPT (05/07 ~04:00 AM). Copiados al proyecto en
  `mundo-fenix/assets/guardianes/` con nombres por color (guardian-negro/blanco/cobre/rojo/
  azul/verde/violeta/naranja/rosa/dorado.png). Originales en Downloads/NIÑOS FENIX. ~2MB c/u.
  Estilo consistente: chibi
  3D negro-fondo, capa blanca, emblema fénix dorado, alas de fénix doradas atrás. Variados:
  5 nenes (negro/dorado, cobre-moreno, azul, naranja fuego, violeta) + 5 nenas (blanco-perla/
  moño, rojo-rubia, verde-coletas, negro-rosa cola de caballo, violeta-dorado pelo largo).
- Al integrar: optimizar a ~320px (los originales pesan 2MB, no van crudos al Artifact/repo).
- CAPA POR RANGO — decisión pendiente (recomendación de Opus): NO recolorear la capa sobre el
  PNG (queda feo/caro). Mejor: el avatar mantiene su capa blanca y el RANGO se muestra con un
  AURA/anillo de color alrededor del robot + etiqueta. La capa FÍSICA en La Casona sí cambia
  de color (que es lo que le importa al niño). Confirmar con Iván antes de codear.

## Reglas de diseño (para cuando se construya)
- Niños 3-12: la interfaz la usa el PAPÁ en su teléfono (COPPA/privacidad: no cuentas de
  niños, no chat entre niños, videos solo del papá al agente).
- Consentimiento explícito para usar videos en redes (opt-in por video, nunca default).
- Premios físicos con costo controlado (remeras = merchandising que además hace marketing).
- El juego debe funcionar aunque el niño falte una semana (no castigar, re-enganchar).

## Métrica de éxito del MVP
- % de familias activas que mandan ≥1 video/semana (meta: >40%).
- Retención: niños con juego activo vs sin juego (churn mensual).
- Si el MVP WhatsApp supera esas metas 4 semanas seguidas → construir la PWA.

## PLAN MAESTRO DE LA APP (05/07/2026)
Existe `mundo-fenix/PLAN-MAESTRO.md`: todos los módulos y funciones de la app (3 productos:
App PWA + Panel admin + Motor), modelo de datos Airtable, integraciones con Aurora/QR,
economía de brasas con números, fases F0-F6 y decisiones abiertas. Es LA referencia para
construir; este spec queda como el documento del modelo de negocio.

## ESTADO DEL PROTOTIPO (05/07/2026)
- Vive en: `mundo-fenix/index.html` (dentro del repo fenix-kids-agent). Self-contained, PWA,
  un solo archivo, dark ember. Persiste en localStorage (key `mundofenix_v2`).
- Publicado como Artifact: https://claude.ai/code/artifact/2a237e72-570f-4001-bfc2-8c52e87b3d9e
- v2 jugable incluye: constructor de avatar (SVG — A DESCARTAR por los robotitos), Reto de
  5 días con racha, Ceremonia de la Capa, mapa de zonas de La Casona, Banco de Brasas
  (invertir/donar/ahorrar/gastar), sistema de capas por rango (XP), insignias por valor,
  tienda (chico/mediano/especial), ranking por valores. Todo con datos mock.
- PRÓXIMOS PASOS (cuando se retome):
  1. Meter los 8 robotitos Guardianes reales (Iván los genera en ChatGPT) + resolver la
     capa-por-rango (ver TEMA ABIERTO arriba).
  2. Definir categorías de edad (Mini 3-5 / Fénix 6-8 / Titanes 9-12) para justicia.
  3. Si el modelo convence en la práctica → conectar Airtable (backend real) e integrar con
     el embudo de Aurora (el lead recibe la app y arranca el Reto del lunes).
- Decisión de prioridad SIN CAMBIOS: Genesis + relanzamiento primero. Esto avanza en paralelo
  como prototipo, no desplaza el foco.
