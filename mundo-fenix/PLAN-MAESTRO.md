# MUNDO FÉNIX — Plan Maestro
> Creado 05/07/2026. Documento de referencia de TODO lo que la app contiene y sus funciones.
> El modelo de negocio vive en `docs/JUEGO-CASONA-SPEC.md`. Esto es el QUÉ y CÓMO de la app.

---

## 0. Visión en una frase

**La Casona es el juego. La app es la memoria, el estatus y la recompensa del juego.**
El niño entrena de verdad (en casa y en La Casona); la app convierte ese esfuerzo en una
aventura visible: su Guardián, sus brasas, su capa, su historia.

## 1. Principios no negociables (heredan del spec)

1. **La capa se GANA, no se compra.** Las brasas nunca se compran con plata.
2. **Se premian VALORES** (coraje, disciplina, compañerismo, exploración, mejora personal,
   respeto, liderazgo), no solo ganar. El más fuerte no barre con todo.
3. **El teléfono es del PADRE** (niños 3-12, COPPA): sin cuentas de niños, sin chat entre
   niños, sin fotos de niños en la app pública. Videos: solo del padre al canal oficial.
4. **Nadie que completa se va con las manos vacías** — el que no ganó igual progresó.
5. **No castigar la ausencia** — re-enganchar (invertir brasas, recuperar días).
6. **Todo lo digital tiene consecuencia física** en La Casona (y viceversa).

## 2. Los 3 productos (una app, tres caras)

| Producto | Usuario | Qué es |
|---|---|---|
| **App Mundo Fénix** (PWA) | Padre + hijo mirando juntos | El juego: avatar, reto, mapa, banco, tienda, ranking |
| **Panel Fénix** (admin) | Iván / Lujan / profes | Validar videos, otorgar brasas, gestionar desafíos, canjes, ceremonias |
| **Motor** (backend + integraciones) | Sistema | Airtable como DB, Aurora/WhatsApp como canal, QR/asistencias como sensor presencial |

---

## 3. APP MUNDO FÉNIX — módulos y funciones

### 3.1 Entrada y cuenta
- **Acceso sin contraseña**: Aurora manda un link mágico por WhatsApp con código de familia
  (`mundofenix.app/f/XXXX`). El padre lo abre y la app queda vinculada a su familia.
- **Multi-hijo**: una familia, N Guardianes. Selector de hijo al entrar (cada hermano tiene
  su avatar, sus brasas, su capa — las brasas son POR NIÑO; puede haber metas de familia).
- **Modo demo**: sin código se puede jugar con datos de muestra (lo que ya hace el prototipo).

### 3.2 Creación del Guardián (onboarding)
- Elegir 1 de los 10 **robotitos Guardianes** (ya generados, `assets/guardianes/`).
- Nombre de Guardián (el nombre real del niño o apodo).
- Categoría por edad, automática por fecha de nacimiento (ya está en Airtable NIÑOS):
  **Mini (3-5) · Fénix (6-8) · Titanes (9-12)** — define ejercicios, rivales de ranking y metas.
- Estado inicial: **Aspirante, sin capa**.

### 3.3 Reto Fénix — 5 días (el corazón del embudo)
- Camada semanal: todos arrancan el lunes, se gradúan el sábado.
- Pantalla del día: los 5 ejercicios de SU categoría + botón "Ya entrenamos — subir video".
- **El video SE SUBE EN LA APP** (decisión Iván 07/07/2026, reemplaza el flujo por WhatsApp):
  botón "Ya entrenamos — subir video" → upload directo del navegador a **Cloudflare R2**
  (bucket privado) vía URL prefirmada que emite una Pages Function. *Razón: mandar por
  WhatsApp es incómodo y saca al usuario de la app; el loop subir→revisión→aprobado→brasas
  viviendo completo en la app incentiva su uso diario.*
  - Privacidad: bucket PRIVADO, solo el admin ve los videos (coherente con COPPA — nada
    público). Retención corta: se borran a los 30 días (config).
  - Costo: R2 no cobra egress; videos de 30-60s → centavos por mes.
  - Trade-off asumido: se pierde la ventana de 24h de Meta que abrían los videos entrantes
    → las notificaciones salientes que la necesiten van por plantilla (el anuncio del lunes
    ya estaba planificado así).
- **Acreditación INMEDIATA, control DESPUÉS** (decisión Iván 07/07: "no puedo recibir 100
  videos por día"). Al subir, el día se marca ✅ y las brasas caen al toque (dopamina
  inmediata). Nadie espera a un humano. El control es asíncrono, en 3 capas:
  1. **Checks automáticos al subir** (gratis): duración mínima, hash anti-duplicado (mismo
     video re-subido), máx. 1 video/día/niño. La economía ya acota el fraude: el tope es
     50 plata/día, hagas lo que hagas.
  2. **Validación IA async**: un job extrae 3-4 frames del video y le pregunta a Claude
     (Haiku vision, centavos) "¿se ve un niño haciendo ejercicio?" → score. Videos OK no
     los ve nadie; los sospechosos van a una cola de revisión.
  3. **Revisión humana solo por excepción**: la cola de sospechosos + muestreo aleatorio
     ocasional. Si algo era trampa → se revocan las brasas (estado "revocado", caso raro).
- Día fallado se recupera (la meta es completar 5, no la perfección).
- Racha visible (los 5 puntos que se van llenando) + puntos por día.
- Día 5 completado → **pantalla de invitación a la Graduación del sábado** (fecha, hora,
  qué llevar, mapa de cómo llegar a La Casona).

### 3.4 Ceremonia y Capas (rangos)
- Al graduarse: animación de **Ceremonia de la Capa** (ya en el prototipo) + capa blanca.
- **Rangos por puntos acumulados** (XP de por vida, nunca baja):
  Blanca → Roja → Naranja → Dorada → **Fénix**.
- El avatar mantiene su capa blanca de imagen; el rango se muestra con **aura de color +
  marco + etiqueta** (decisión: no recolorear los PNG). La capa FÍSICA de color se entrega
  en La Casona al subir de rango → **Ceremonia presencial cada vez** (ritual + contenido).
- Pantalla "Mis Capas": progresión, cuántos puntos faltan, historial de ceremonias.

### 3.5 Entrenamiento semanal en casa (post-graduación — el motor de retención)
- Después del Reto, el juego sigue: **desafío semanal en casa** (mismo mecanismo: video
  subido en la app, acreditación inmediata) + **misión presencial del sábado**.
- Mínimo mensual por categoría → mantiene la **llama encendida** (indicador visual). No
  cumplir NO castiga: la llama se apaga y se reenciende entrenando (nunca se pierde rango).
- Puntos por: día entrenado, semana completa, asistencia al sábado, valores mostrados.

### 3.6 El Sábado en La Casona (historia + circuito)
- Se fue el mapa de zonas fijas. Ahora hay una **historia temática por temporada** (~2 meses):
  Piratas, Astronautas, Guerreros... El mismo circuito físico cambia de relato cada temporada
  → contenido infinito sin obra nueva.
- El niño **completa vueltas al circuito**. Cada vuelta la **carga el profe en la app** cuando
  el niño la termina (el niño NO se auto-carga). 1 vuelta = 100 plata; 5 = +200; 10 = +500 +
  caja sorpresa.
- **Toda la economía la disparan adultos/hardware, nunca el niño:** oro = lector facial
  (asistencia), plata = profe (vueltas). Por eso ambas monedas son **infalsificables** y el
  piso duro se sostiene. Coherente con COPPA: el niño VE su progreso, no transacciona.

### 3.7 Banco de Brasas
- Saldo por niño + historial de movimientos (ya en prototipo).
- **Ganar**: reto diario, semana completa, asistencia sábado, valores otorgados por profe,
  misiones, bonus de racha.
- **Gastar**: Tienda Fénix.
- **Invertir**: congelar X brasas → bonus si asiste el sábado siguiente (re-enganche).
- **Donar**: a la meta grupal de su patrulla/equipo (compañerismo jugable).
- Regla anti-inflación: los precios de tienda y los montos de brasas viven en Airtable
  (config), ajustables sin tocar código.

### 3.8 Insignias de Valor
- 7 insignias (una por valor). Las otorga el PROFE desde el Panel (no automáticas): "hoy
  Benja mostró Coraje". Notificación push/WhatsApp al padre con el porqué → oro puro para
  el padre ("me contaron algo bueno de mi hijo").
- Niveles por insignia (bronce/plata/oro = 1/5/15 veces).

### 3.9 Tienda Fénix
- Catálogo desde Airtable (foto, precio en brasas, stock): chicos (stickers, pulseras,
  parches) / medianos (botella, gorra, remera) / especiales (Capitán del sábado, misión
  nocturna, mural, dormir en La Casona).
- El canje genera un **pedido pendiente** → se retira EN La Casona el sábado (nada se
  envía): la tienda también empuja asistencia. El profe marca "entregado" en el Panel.

### 3.10 Ranking y Patrullas
- Ranking semanal POR CATEGORÍA de edad (Mini/Fénix/Titanes) — nunca mezclados.
- Rankea una métrica compuesta que pesa constancia y valores (no fuerza): el "Guardián de
  la Semana" puede ser un nene de 4 que vino siempre.
- **Patrullas** (equipos): meta grupal semanal (ej: "juntar 500 brasas de equipo") →
  recompensa grupal. Donaciones alimentan esto.
- Hall de la Fama: Guardianes de la Semana históricos + Mural digital.

### 3.11 Comunicación (sin chat)
- La app NO tiene chat. Todo lo conversacional pasa por **Aurora en WhatsApp** (canal ya
  construido, con espejo Telegram para Iván).
- Notificaciones de la app → por WhatsApp vía Aurora: insignia otorgada,
  desafío nuevo del lunes, recordatorio del sábado, subiste de rango, canje listo.
- Push web (PWA) como refuerzo opcional en Fase 2+.

### 3.12 Pantalla Familia (el padre)
- Progreso de cada hijo, calendario de sábados, estado del paquete (cuántos sábados le
  quedan — dato de Airtable PAGOS), botón directo a Aurora para pagar/renovar.
- **Aquí se cierra el círculo del negocio**: "A Mateo le faltan 120 pts para la Capa Roja
  — renovar paquete" con botón a WhatsApp.

---

## 4. PANEL FÉNIX (admin — Iván/Lujan/profes)

Reutiliza el patrón Command Center (PWA protegida con clave).

1. **Cola de revisión de videos** (solo excepciones): los videos se acreditan solos al
   subirse a la app; acá aparecen ÚNICAMENTE los flaggeados por la IA + un muestreo
   aleatorio → botones Confirmar / Revocar brasas con motivo. *(v1: la cola se puede
   espejar a Telegram con botones, patrón comprobantes — pero solo los sospechosos,
   nunca los 100 del día.)*
2. **Otorgar valores**: elegir niño + valor + nota de una línea → insignia + brasas + notif.
3. **Registrar el sábado**: marcar asistencia (→ oro; mientras no haya lector facial) y
   **cargar las vueltas** que completa cada niño en el circuito (→ plata). Con el lector
   instalado, la asistencia se automatiza; las vueltas las sigue cargando el profe.
4. **Gestión de desafíos**: crear/editar desafío semanal por categoría (texto + ejercicios),
   historia de la semana, zona activa. Todo en Airtable, editable sin deploy.
5. **Tienda**: catálogo, stock, cola de canjes pendientes, marcar entregado.
6. **Ceremonias**: quiénes se gradúan este sábado, quiénes suben de rango (lista para el
   ritual presencial + capas físicas a preparar).
7. **Camadas**: quiénes están en el Reto esta semana, en qué día van, quiénes se trabaron
   (→ Aurora manda empujón de ánimo).
8. **Métricas**: familias activas, % que manda video, retención por cohorte, conversión
   Reto→pago, brasas emitidas vs canjeadas.

---

## 5. MOTOR — datos e integraciones

### 5.1 Airtable (base Salsa Soul, tablas nuevas con sufijo FENIX)
| Tabla | Campos clave | Nota |
|---|---|---|
| **GUARDIANES** | link NIÑO, robotito elegido, XP total, rango actual, llama encendida, patrulla | 1 por niño jugador |
| **RETOS** (config) | semana, categoría, ejercicios, historia, zona activa | editable sin deploy |
| **DESAFIOS CUMPLIDOS** | link GUARDIAN, fecha, tipo (reto-día/semanal/misión), estado (pendiente/aprobado/rechazado), brasas, aprobó quién | el ledger del juego |
| **MOVIMIENTOS BRASAS** | link GUARDIAN, +/-, motivo, saldo | como PAGOS pero de brasas |
| **INSIGNIAS OTORGADAS** | link GUARDIAN, valor, nota, profe, fecha | alimenta notifs |
| **TIENDA** | ítem, foto, precio brasas, stock, tier | catálogo |
| **CANJES** | link GUARDIAN, ítem, estado (pendiente/entregado) | cola del sábado |
| **PATRULLAS** | nombre, meta semanal, brasas grupales | equipos |
| **CAMADAS** | lunes de inicio, link LEADS/FAMILIAS inscriptos | el embudo |
- Reusa lo existente: NIÑOS (fecha nac → categoría), FAMILIAS/TUTORES (acceso), PAGOS
  (estado del paquete), ASISTENCIAS (brasas por venir), LEADS (origen del embudo).
- OJO reglas conocidas: rollups=array (buscar sobre formula `&""`), paginar >100, typecast.

### 5.2 Aurora / agente WhatsApp (el repo actual)
- **Embudo**: lead nuevo → Aurora ofrece el Reto → crea GUARDIAN + manda link mágico →
  camada del lunes. (Reemplaza a la "clase de prueba" como CTA principal.)
- **Videos: ya NO pasan por WhatsApp** (07/07: se suben en la app → R2, acreditación
  automática + IA async). Aurora queda solo como canal conversacional y de notificaciones.
- **Notificaciones salientes**: plantilla Meta para el anuncio del lunes y demás avisos
  fuera de ventana (al no entrar videos por WhatsApp, la ventana de 24h se abre menos —
  asumido como trade-off de la decisión del 07/07).
- **Regla de oro**: TODO cambio en el agente pasa por /pre-cambio y /pre-deploy, deploy
  incremental como siempre. El juego NUNCA rompe el flujo de leads/pagos.

### 5.3 Presencial
- **Asistencia = LECTOR FACIAL** (reconocimiento al entrar). El niño llega, la cámara lo
  reconoce, se marca la asistencia y **se le acredita el oro automáticamente**. El niño NO
  se auto-marca. Esto hace el oro **infalsificable** → blinda el piso duro (8 sábados de oro
  = vino 8 veces de verdad). En el prototipo el botón "Llegué" solo lo simula.
- **Estado del hardware (05/07/2026): el lector facial TODAVÍA NO está instalado.** Base de
  software ya existe: AWS Rekognition (`agent/face_recognition.py`, collection `fenix-kids`,
  campos FOTO+FACE_ID en NIÑOS FENIX). Falta el dispositivo en La Casona.
- **Fallback para el piloto:** hasta que esté el lector, la asistencia se marca a mano — el
  profe desde el Panel, o botón en el espejo Telegram (patrón ya usado con los comprobantes).
  El oro se acredita igual; solo cambia quién dispara la marca.
- Futuro: QR escondidos = misiones de exploración autovalidadas.

### 5.3b MODO TV — la pantalla gigante de La Casona (pedido Iván 05/07, ya en prototipo)
- **Smart TV grande en el ingreso** corriendo la misma PWA en modo TV (URL /tv, fullscreen).
- **El momento mágico:** el niño llega → se le escanea el rostro (cel del profe + Rekognition,
  la infra ya existe) o el profe lo marca → **la TV lo recibe con su nombre gigante, su robot
  Guardián y lluvia de monedas de oro** delante de todos. Tras cada vuelta, lo mismo (+plata).
- Escenas: bienvenida (+10 🥇), vuelta/bonus/caja, dragón vencido (insignia), tesoro hallado.
  Cada escena lleva una línea de la mini-historia de la temporada ("⚓ ¡Lola abordó el barco!").
- Idle: historia de la temporada + robots flotando + ticker con ranking y el desafío del día.
- **Arquitectura real (F2+):** app del profe escribe el evento → backend (CF Functions) →
  la TV lo levanta (polling corto o WebSocket) y dispara la animación. En el prototipo ya
  funciona cross-ventana en un mismo dispositivo (localStorage storage events) + botón Demo.
- La TV es el REFUERZO SOCIAL del sistema: el depósito de monedas deja de ser un número en
  una app y pasa a ser un momento público que todos ven. Estatus puro.

### 5.3c OJOS DE LA CASONA — 32 cámaras HikVision + pulseras (idea Iván 06/07, fase F7)
- **Infra existente (VERIFICADO 06/07):** 32 cámaras HikVision **analógicas/HD-TVI** (coaxial)
  sobre un **DVR HikVision `DS-7232HGHI-M2`** (Turbo HD, 32 canales, 2 bahías SATA, SN GD2379556).
  NO es NVR IP → no hay IP por cámara; único punto de acceso = el DVR. Alimentación por fuentes
  `DS-2FA1205-C8` (8 canales c/u). El DVR soporta **RTSP** (`rtsp://IP:554/Streaming/Channels/N01`
  para live) e **ISAPI** (buscar/descargar grabaciones por canal + rango de tiempo = el VAR).
  Acceso actual: Hik-Connect (celular, hay salida a internet) + salida HDMI directa a una TV.
  Piloto F7 = LAN local. **PENDIENTE:** IP local del DVR (Menú→Config→Red) + credenciales admin.
- **Tracker:** GPS indoor no sirve; lo realista es pulsera BLE (tipo parque acuático) +
  receptores por zona → ubicación a NIVEL ZONA (pileta/cancha/circuito/árbol). Suficiente.
- **EL ORO — clips por EVENTO (no vigilancia):** evento de la app (vuelta/tesoro/desafío, con
  timestamp + zona) → mapa zona→cámara → descarga automática del clip de ±40s → esa noche el
  papá recibe por Aurora: "🎬 la vuelta 7 de Benja". Retención + contenido orgánico brutal.
  Pipeline: NVR → backend → (Editor Pro Max opcional) → WhatsApp. También reproducible en TV.
- **Seguridad de zona:** pulsera en zona no permitida (muelle/río) → alerta al profe. Vendible
  y defendible.
- **REGLA DE DISEÑO (decisión de Opus, importante):** sistema POR EVENTOS, NO vigilancia
  continua con archivo por niño. Menores + ubicación + video = dato ultra sensible (PY ya
  tiene ley de protección de datos). Todo opt-in por familia (mismo patrón que el opt-in de
  fotos para redes). Narrativa: "seguridad + momentos destacados de tu hijo", jamás "tracking".
- **PROPÓSITO PRINCIPAL (aclarado por Iván 06/07): el VAR de La Casona.** Después de cada
  vuelta el niño puede VER su vuelta (replay en TV/app = premio) y a la vez sabe que el
  circuito se monitorea → **anti-trampa por diseño** ("los niños quieren ser muy tramposos").
  El replay es a la vez recompensa y árbitro: nadie puede inventarse vueltas.
- **Roadmap:** requiere F2 (backend). CONFIRMADO por Iván: se implementa. La planificación
  técnica (NVR, zona piloto, pulseras, replay en TV) queda para una sesión propia dedicada.
  Piloto: 1 zona (circuito) + 2-3 cámaras mapeadas + clips semi-manuales → después las 32.
- **✅ PIPELINE VERIFICADO EN VIVO (06/07/2026) — el VAR ya funciona con hardware real.**
  Prueba de punta a punta ejecutada contra el DVR real: ISAPI autenticado → buscar grabación
  por cámara+hora (`POST /ISAPI/ContentMgmt/search`) → descargar segmento
  (`POST /ISAPI/ContentMgmt/download`) → convertir IMKH→MP4/H.264 + recortar con FFmpeg →
  clip de 30s de la cámara 31 reproducible. Dejó de ser teoría: es código que corre.
  Credenciales y datos del DVR viven en `CLAUDE.local.md` (no-git). Hallazgos técnicos:
  (1) descarga en formato propietario **IMKH** → siempre convertir con FFmpeg a H.264;
  (2) el recorte por API se ignora → recortar en FFmpeg localmente;
  (3) **DHCP mueve la IP del DVR** → PENDIENTE fijarla (IP fija + usuario dedicado, se puede
  por API ya sin teclado); (4) disco lleno en overwrite → bajar el clip el MISMO día;
  (5) cámaras con nombres genéricos → renombrar por zona (mapa zona→cámara);
  (6) trackID = canal*100+1 (cam31=3101); FFmpeg 8.1 ya instalado en la PC de Iván.
  **Próximo:** fijar IP + usuario dedicado por API, renombrar cámaras por zona, y armar el
  pipeline RTSP+FFmpeg para recorte por evento con hora exacta.

### 5.3d MAPA VIVO — segunda TV con el mapa de La Casona (pedido Iván 07/07, construido)
- **`mundo-fenix/mapa.html`**: mapa ilustrado de La Casona en otra TV — cada niño es su
  robot Guardián en el último fuego que encendió; camina por el sendero al tocar la
  siguiente estación NFC; vuelta reclamada en el tótem = lluvia de monedas en el mapa.
- Render puro del canal de eventos existente (localStorage demo + polling backend). Muda
  (la voz vive en la TV principal). Detalle en `SPEC-NFC-CIRCUITO.md` §6b.
- **Nivel 2 — movimiento continuo por zonas (pulseras BLE + los mismos ESP32 como
  receptores): decidido NO ahora.** Diseño completo + privacidad + gate de decisión en
  `SPEC-BLE-TRACKING.md`. Se evalúa recién después del piloto NFC.

### 5.4 Hosting — ✅ DEPLOYADO 07/07/2026
- **Repo propio `mundo-fenix-app` (GitHub privado) + Cloudflare Pages** — EN VIVO:
  - Juego / **Modo TV**: `https://mundo-fenix.pages.dev/?tv` (la Smart TV apunta acá, FIJO)
  - **Espejo** (tablet): `https://mundo-fenix.pages.dev/totem` (pide la clave UNA vez)
  - **Mapa Vivo** (2da TV): `https://mundo-fenix.pages.dev/mapa`
  - Deploy: `npx wrangler pages deploy . --project-name=mundo-fenix` (direct upload; sin
    secrets en el sitio → el bug de secrets de Pages no aplica). La carpeta
    `fenix-kids-agent/mundo-fenix/` sigue siendo el WORKSPACE (specs + edición);
    `Projects/mundo-fenix-app/` es el repo que se publica — copiar y deployar al cambiar.
  - Seguridad: `totem.html` ya NO lleva la key hardcodeada (localStorage, se tipea 1 vez).
  - Esto MATA los líos de LAN/túneles/caché/charset de las sesiones 26-27.
- Backend liviano para hablar con Airtable sin exponer el token: **Cloudflare Pages
  Functions** (mismo repo) o endpoints nuevos en el Railway del agente. *Decisión en F2.*

---

## 6. ECONOMÍA v2 — dos monedas SIN cambio (definida 05/07/2026, Opción B)

**Regla del niño: "el oro es por VENIR, la plata por ESFORZARTE."** No hay conversión entre
ellas — esa separación es lo que blinda el piso duro.

**🥇 ORO — se gana SOLO viniendo. Compra lo grande.**
| Acción | Oro |
|---|---|
| Asistir al sábado | 10 |

**🥈 PLATA — se gana esforzándote. Compra lo del día.**
| Acción | Plata |
|---|---|
| Reto: cada día (×5) | 50 |
| Reto: bonus por los 5 seguidos (duplica) | +250 → **500 total** |
| Cada vuelta del circuito | 100 |
| 5 vueltas | +200 |
| 10 vueltas | +500 + **caja sorpresa** 🎁 |

**Entrada al entrenamiento** (pago único al graduarse): **500 plata** = tus 500 del reto.
Arrancás en 0 y construís desde ahí (ritual: tu esfuerzo del reto es tu entrada).

**Tienda (oro):**
| Ítem | Precio | = |
|---|---|---|
| 🧢 Kepi | **120 oro** | 12 sábados de venir |
| 👕 Remera | **180 oro** | 18 sábados de venir |
| 🎁 Caja sorpresa | **NO se compra** | se GANA a las 10 vueltas (adentro: stickers/llaveros/gadgets) |

**Uso de la PLATA — escalera de valor (NO un peaje de entrada).** La plata compra EXPERIENCIAS
y VENTAJAS extra, nunca el acceso básico (eso es la cuota + venir):
- **Semanal / barato:** Ayuda del Mapa 150 (pista extra del tesoro) → dopamina del día.
- **Mensual:** Encuentro Dominical 500.
- **Aspiracional:** Cumpleaños en La Casona 2.000 + alquiler que pagan los papás.
- Regla: NO cobrar peaje por sábado (castigaría la asistencia, y ya pagan cuota). Bonus de
  negocio: los eventos son ingreso — la plata del niño empuja al papá a pagar la parte real.
- DESCARTADOS (05/07): poderes "Escudo Fénix" y "Turno Doble" — nadie los entendía sin
  explicación. Regla: lo que necesita explicación, no va.

**BÚSQUEDA DEL TESORO (semanal — mantiene al niño pensando lun-vie):**
- 1 tesoro por semana, tematizado por la temporada (Piratas: el cofre de Barbafuego).
- **3 pistas** que se resuelven en la semana, alternando cabeza y cuerpo:
  1. 🧮 **Mate** (test de matemática por categoría de edad; la respuesta abre la siguiente pista)
  2. 💪 **Física** (mini reto filmado — video subido en la app, como el reto)
  3. 🦜 **Acertijo/lógica** (adivinanza cuya respuesta es un lugar/objeto de La Casona)
- Cada pista: +50 plata. Las 3 → se revela el **acertijo final**: un verso que apunta a un
  lugar REAL de La Casona ("donde el agua duerme y el sol se mira…" = la pileta).
- El sábado el niño busca el **cofre físico escondido** ahí. Hallado (confirma el profe):
  +300 plata + premio del cofre. Los gadgets viven en cajas/cofres, no en la góndola.
- Dificultad por categoría: Mini = pictogramas/contar, Fénix = sumas, Titanes = problemas.
- Con el lector/QR futuro: pistas que se desbloquean escaneando en zonas (fase 2).

**Piso duro garantizado:** como el oro SOLO se gana viniendo (10/sábado), el kepi (80) sale
exactamente en 8 sábados y la remera (120) en 12 — imposible antes, por más vueltas que dé.
Las vueltas dan plata (cajas y cositas), no oro. Esa separación ES todo el diseño.

**Capas = por DRAGONES VENCIDOS (disciplina + constancia), NO monedas ni asistencia.**
Decisión de Iván 05/07: la capa se conquista con entrenamiento en casa + desafíos superados,
no con solo venir. Métrica: dragones vencidos (~4/mes si es constante). Blanca (graduación) ·
Roja 12 · Naranja 24 · Dorada 36 · Fénix 48 (~1 año). Cada capa ≈ 3 meses. Ver sección 10
(Código Fénix). Números en config, ajustables.

## 7. FASES DE CONSTRUCCIÓN

| Fase | Qué | Estado / esfuerzo |
|---|---|---|
| **F0** | Prototipo jugable mock (avatar, reto, ceremonia, banco, tienda, ranking) | ✅ HECHO (Artifact) |
| **F1** | Robotitos integrados (PNG optimizados + aura por rango) + selector multi-hijo + categorías de edad + pantalla Familia mock + pulido | ✅ multi-hijo/Familia HECHOS en F2 (07/07); resta pulido |
| **F2** | Repo propio + Cloudflare + Airtable REAL (tablas nuevas, link mágico) — la app deja de ser mock | ✅ **HECHO 07/07/2026.** Arquitectura HÍBRIDA (decidida con Iván, supersede "todo Functions"): lógica/datos en Railway `/juego/*` + CF Function SOLO videos→R2. Tablas: GUARDIANES/MOVIMIENTOS BRASAS/DESAFIOS CUMPLIDOS FENIX + CODIGO FENIX en FAMILIAS. Link mágico `/?f=CODIGO` (POST /juego/familia-codigo). Selector multi-hijo = pantalla Familia v1 (saldos, capa, botón WhatsApp). Acciones vía POST /juego/accion (montos §6 en el servidor, ledger + anti-dup diario). Sin `?f=` la app sigue siendo demo. |
| **F3** | Upload de video en la app + acreditación automática + checks anti-abuso | ✅ **HECHO 07/07/2026** (v1): PUT /api/video (Pages Function → R2 `fenix-videos`, binding sin credenciales, la familia solo ve SUS videos) + POST /juego/reto-video (1/día, +50/+250, ledger, muestreo espejado a Telegram con link). **Validación IA (Haiku vision) = iteración 2** (decidido). |
| **F4** | Embudo Aurora completo (lead→Reto→camada→graduación→venta 350/450) + notificaciones + pantalla Familia con PAGOS | 2-3 días |
| **F5** | Panel Fénix completo (valores, misiones, tienda, ceremonias, métricas) | 2-3 días |
| **F6** | Temporadas, patrullas, QR en zonas, eventos especiales (Copa Fénix / semana intensiva paga como evento de temporada) | continuo |

**Saludo personalizado (07/07):** las llegadas (tótem NFC y checkin facial) llevan
`{dias_casa, sub:"Entrenaste en casa N días esta semana 💪"}` contando DESAFIOS CUMPLIDOS
de 7 días — la TV lo muestra bajo el nombre. Voz por variantes = iteración 2.

**Gate de negocio**: F3+ recién cuando el piloto (F1-F2 con 5-10 familias reales elegidas
a mano) muestre que los niños se enganchan. Métricas gate: >40% manda ≥1 video/semana,
4 semanas seguidas (las del spec).

## 8. DECISIONES (resueltas 05/07 + abiertas)

**RESUELTAS por Iván (05/07/2026):**
1. **Rango visual = AURA ahora** + a futuro los Guardianes **EVOLUCIONAN de aspecto** por
   rango (Iván genera las evoluciones en ChatGPT — como evoluciones Pokémon, no solo capa).
2. **Backend F2 = Cloudflare Pages Functions** (repo propio del juego, separado del agente).
3. **Naming**: "Mundo Fénix" es el mundo/la app; "Guardianes Fénix" son los niños dentro.
   Ambos conviven: *en el Mundo Fénix están los Guardianes Fénix*.

**RESUELTAS por Iván (07/07/2026):**
4. **Videos EN la app, no por WhatsApp**: subir a R2 desde la app; WhatsApp era incómodo y
   sacaba al usuario del juego. El loop completo (subir→✅→brasas) vive en la app.
5. **Acreditación inmediata + control posterior**: nada de aprobar 100 videos/día a mano.
   Brasas al toque; checks automáticos + IA (Haiku vision sobre frames) + revisión humana
   solo de excepciones flaggeadas.

**ABIERTAS:**
4. **Piloto**: qué 5-10 familias reales invitar a la camada 1 y qué lunes arranca.
5. Copa Fénix (semana intensiva paga con premio grande): ¿evento de Temporada 1 o más adelante?

## 9. MÉTRICAS DE ÉXITO (del spec + negocio)

- % familias activas con ≥1 video/semana (meta >40%).
- Conversión Reto completado → paquete pagado (meta inicial: >50% de los graduados).
- Retención: churn mensual con juego vs sin juego.
- Asistencia promedio de sábado (el juego debe subirla).
- Monedas emitidas vs gastadas (salud de la economía).

## 10. CÓDIGO FÉNIX — los 4 Dragones (narrativa, propuesta 05/07/2026)

Marco de formación de carácter. El niño no entrena para hacer flexiones: entrena para vencer a
los 4 dragones internos. Eslogan: **"En casa los debilitás. En La Casona los vencés."**

Los 4 (y SOLO 4 — más se vuelve confuso):
- **Pigrus** — Pereza → insignia *Llama de Disciplina*
- **Timor** — Miedo → *Corazón Valiente*
- **Khaos** — Desorden → *Escudo del Orden*
- **Dubius** — Duda → *Ojo de Confianza*

Reemplazan las 7 insignias de valor (las consolidan y les dan narrativa memorable).

**Integración sin duplicar sistemas (esto es lo clave):**
- Los dragones son la **MÉTRICA DE LAS CAPAS** — resuelve el pedido "capas por disciplina, no
  asistencia". Vencer dragones (entrenamiento en casa + desafío único del sábado + tesoros/
  acertijos de la semana) sube tu capa/rango. Las capas dejan de depender de asistir.
- Las **monedas** siguen aparte (billetera): oro por venir → kepi/remera; plata por esfuerzo →
  poderes/eventos. No se cruzan con los dragones.
- El **circuito del sábado** = la batalla contra el dragón de esa semana. Las **vueltas** dan
  plata (+ caja a las 10). La **temporada** (piratas/astronautas) es la estética; los dragones,
  la estructura de formación. Conviven: 1 dragón por semana dentro de la temporada.

**RIESGO a cuidar (recomendación de Opus):** la narrativa de los 4 dragones es ORO y va. Pero
el aparato de 400 puntos exactos/mes + 280 mínimo + estados + aprobación/pausa/reactivación es
DEMASIADA contabilidad para arrancar. Para el piloto: cada dragón = una insignia que se gana
venciéndolo (casa + sábado); los 4 del mes = tu progreso de capa. Los umbrales finos se calibran
con datos reales. La misma regla que Iván aplicó a los dragones ("no 8-10") vale para las
mecánicas: no apilar sub-sistemas de golpe.

**Entrada de nuevos ("Despertar Fénix"):** el Reto de 5 días debilita a Pigrus (constancia) y
Khaos (orden); Timor y Dubius se enfrentan ya adentro. No tirarle los 4 de golpe al nuevo.

**Ritmo:** 1 dragón por semana → 4/mes (la Batalla). Capas: Roja 12 🐉 (3 meses) · Naranja 24
(6m) · Dorada 36 (9m) · Fénix 48 (1 año).

**El entrenamiento en casa SUBE con cada capa** (decisión Iván 05/07). Progresión tipo
cinturones, y los ejercicios retirados del inicio (flexiones, saltos estrella) VUELVEN como
desbloqueo de rango:
| Capa | Rutina diaria en casa |
|---|---|
| Blanca | 10 abd · 10 saltos · parada 10s · Silla 30s · Puente 30s |
| Roja | 15 · 15 · 15s · 45s · 45s · **+5 flexiones (nuevo)** |
| Naranja | 20 · 20 · 20s · 60s · 60s · 10 flexiones |
| Dorada | 25 · 25 · 30s · 75s · 75s · 15 flexiones · **+10 saltos estrella (nuevo)** |
| Fénix | 30 · 30 · 45s · 90s · 90s · 20 flexiones · 15 estrella |
(Los números los calibra Iván con los profes; la mecánica es lo definido.)

## 11. MECÁNICA DEL SÁBADO v2 — vueltas → desafío → insignia (definida 2026-07-12)

Cierra el "cómo" operativo del §3.6 y §10: cómo, en la práctica de cada sábado, un niño
**vence al dragón de la semana** y se lleva la insignia (= progreso de capa). Mantiene las dos
reglas de oro: las **vueltas dan plata, NO capa**; la **capa se gana superando el desafío**
(disciplina). Las vueltas solo **habilitan el acceso** al desafío.

### 11.1 Requisito para vencer al dragón (las tres cosas)
1. 🏠 **3 misiones en casa** durante la semana (lo *debilitan*) — ya existe: acción `mision-casa`,
   `CASA_META=3`, 1/día, +50 plata c/u.
2. 🔄 **7 vueltas el sábado** (dentro de la ventana del entrenamiento) — **habilitan/desbloquean el
   desafío** (NO otorgan la insignia por sí solas).
3. ⚔️ **Superar el desafío presencial** del sábado → la insignia se otorga con el **SÍ de Iván por
   WhatsApp** (post-cierre). Nada se dispara automático — ese es el anti-abuso (Iván 2026-07-12:
   confirmó que la 7ma vuelta NO otorga sola, evita que un niño la dispare logueándose). Insignia
   **genérica** (no la del dragón específico, al menos en el piloto).

### 11.2 El entrenamiento del día lo ABRE y CIERRA un profe (por comando de WhatsApp)
Cada horario (11:00 / 15:30) tiene ciclo: `CERRADO → (profe ABRE) → ABIERTO → (profe CIERRA) →
CERRADO`. Durante ABIERTO se cuentan llegadas y vueltas. El CIERRE congela quién quedó elegible
(7 vueltas + 3 misiones) y habilita la fase de insignias. Abrir/cerrar = **comando de WhatsApp**.

### 11.3 Flujo del día
```
El profe ABRE el entrenamiento (comando WhatsApp).
ABIERTO:
  · login facial niño   → llegada (+10 oro)            [existe: checkin-face]
  · cada vuelta         → +100 plata                    [existe: vuelta-face / juego_vueltas]
  · vuelta 7            → DESBLOQUEA el desafío + audio (anuncia, NO da insignia)
  · vuelta 10           → CAJA MÁGICA (retira en Banco Fenix) + audio
  · la LISTA (TV) muestra por niño → ✅7 vueltas / ✅3 misiones = quién accede al desafío

El profe CIERRA (comando WhatsApp): se congela quién quedó elegible.

POST-CIERRE, el niño vuelve a hacer login facial:
  · si ELEGIBLE (7v + 3m) → WhatsApp a Iván: "¿[nombre] superó el desafío?"
                              SÍ → TV reproduce video de felicitación + se anota la INSIGNIA (capa)
                              NO → no pasa nada
  · si NO elegible        → despedida en TV, NO molesta a Iván:
                              "¡Hoy estuviste espectacular, {nombre}! Nos vemos el próximo sábado."
```
**Anti-abuso (la razón del diseño):** post-cierre nada se dispara solo. La insignia siempre pasa
por el SÍ de un adulto por WhatsApp (reusa el patrón `_admin_espera_respuesta` ya existente).

### 11.4 Guiones de voz (George) — v2, quedaron NEUTROS (sin género)
Al reescribirlos desaparecieron "campeón"/"héroe": ya casi no hace falta versión niño/niña.
- **Llegada:** "¡{nombre} llegó a La Casona! El Guardián Fenix te da la bienvenida. Gracias por
  venir a cuidar La Casona. Ganaste diez monedas de oro… ¡que comience la aventura!"
- **Vuelta:** "Muy bien, {nombre}. Vuelta completada. Te ganaste 100 monedas de plata. Vamos
  otra vuelta más."
- **7 vueltas (desbloquea el desafío — anuncia, NO da insignia):** "¡Séptima vuelta completada,
  {nombre}! Desbloqueaste el desafío del día. ¡Con tres vueltas más te ganás la caja mágica!"
- **Dragón (post-cierre, se dispara con el SÍ de Iván):** "¡{nombre} venció al dragón! Completaste
  la misión de hoy. Ganaste una nueva insignia."
- **Caja mágica (10 vueltas):** "¡{nombre} completó 10 vueltas! ¡Sos genial! Te ganaste una caja
  mágica. Podés retirarla en el Banco Fenix."
- **Despedida no elegible:** "¡Hoy estuviste espectacular, {nombre}! Nos vemos el próximo sábado."
- **Tesoro:** ⏳ PENDIENTE (Iván lo va a estudiar; el viejo dice "héroe" → único con género).
> Al cambiar Llegada y Vuelta hay que **regenerar esos audios para TODOS los niños** (el guión
> cambió para todos), no solo las nenas. Costo de quota ElevenLabs (free 10k/mes o $5 Creator).

### 11.5 Qué ya existe vs qué falta construir
**Existe (reusar):** `checkin-face` (login niños) · `vuelta-face`+`juego_vueltas` (conteo por día
con número de vuelta) · `/juego/dia`+`lista.html` (lista con `vueltas_hoy`) · `PLATA_VUELTA=100`
y bonus 5/10 · `mision-casa`+`CASA_META=3` · `dragon-vencido` (otorga insignia, +200 plata) ·
patrón de aprobación admin por WhatsApp (SÍ/NO) · TV que reproduce eventos/videos.

**Falta:** estado ABIERTO/CERRADO por horario · caso `vuelta==7` (evento/audio desbloqueo) ·
mostrar en la lista ✅7 vueltas + ✅3 misiones (elegibles) · flujo post-cierre (login elegible →
pregunta WhatsApp; no elegible → despedida) · SÍ → video felicitación + anotar insignia (reusa
`dragon-vencido`) · abrir/cerrar del profe (facial admin o comando) · audios nuevos/regenerados ·
video de felicitación (asset).

### 11.6 Decisiones
- **Abrir/cerrar del profe:** ✅ (Iván 2026-07-12) → **por comando de WhatsApp** (descartado el
  login facial admin con menú en el tótem).
- **Insignia por la 7ma vuelta:** ✅ **NO es automática** — la 7ma solo desbloquea/anuncia; la
  insignia se otorga con el **SÍ de Iván post-cierre**. Y es **genérica** (Iván 2026-07-12).
- **Texto del audio de la 7ma vuelta:** ✅ definido (§11.4).
- Abiertas: **video de felicitación** (¿genérico o por niño?) · **texto del audio de Tesoro**.

### 11.7 Incrementos sugeridos (menor→mayor riesgo, uno por deploy con /pre-cambio)
1. **Lista del día** muestra ✅7 vueltas + ✅3 misiones (display puro, no toca economía).
2. **Audio/evento en la 7ma vuelta** (mismo patrón que 5/10) + audios regenerados Llegada/Vuelta.
3. **Abrir/cerrar del entrenamiento** (comando del profe) + estado del día.
4. **Post-cierre**: login elegible → pregunta WhatsApp → SÍ → video + insignia; no elegible →
   despedida.
> Dependencia NFC: hoy las vueltas se cuentan con cara+SÍ/NO manual (puente). Cuando lleguen las
> pulseras (~20-25/07) solo cambia el ORIGEN de la vuelta; la mecánica de arriba no cambia.
