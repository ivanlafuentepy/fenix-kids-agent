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
- Pantalla del día: los 5 ejercicios de SU categoría + botón "Ya entrenamos — enviar video".
- **El video NO se sube a la app**: el botón abre WhatsApp con mensaje pre-armado hacia el
  número de Fénix ("Video Reto Día 2 — familia XXXX"). El padre adjunta el video ahí.
  *Razón: canal ya existente, cero costo de storage/moderación, y cada video mantiene la
  ventana de 24h de Meta abierta.*
- La app muestra el día como "en revisión" → "aprobado ✅" cuando el admin valida.
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
- Después del Reto, el juego sigue: **desafío semanal en casa** (mismo mecanismo de video
  por WhatsApp) + **misión presencial del sábado**.
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
- Notificaciones de la app → por WhatsApp vía Aurora: video aprobado, insignia otorgada,
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

1. **Bandeja de videos**: cola de videos del día (llegan por WhatsApp; el espejo Telegram
   ya los muestra) → botones Aprobar / Rechazar con motivo → acredita brasas y marca el día.
   *(v1: se aprueba directo desde Telegram con botones, como los comprobantes de pago —
   patrón ya construido en el agente.)*
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
- **Recepción de videos**: detectar video entrante con contexto de reto activo → registrar
  DESAFIO CUMPLIDO pendiente → espejo a Telegram con botones Aprobar/Rechazar (patrón
  comprobantes). Aprobación acredita brasas y avisa al padre.
- **Notificaciones salientes**: plantilla Meta para el anuncio del lunes (fuera de ventana);
  el resto aprovecha la ventana abierta por los propios videos.
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

### 5.4 Hosting
- **Repo propio** (`mundo-fenix-app`) + **Cloudflare Pages** (patrón de las 5 webs: git
  push = deploy). El repo del agente NO carga con el juego (por eso los PNGs siguen sin
  commitear acá). El Panel puede ser ruta protegida de la misma PWA.
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
  2. 💪 **Física** (mini reto filmado — video por WhatsApp como siempre)
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
| **F1** | Robotitos integrados (PNG optimizados + aura por rango) + selector multi-hijo + categorías de edad + pantalla Familia mock + pulido | 1-2 días |
| **F2** | Repo propio + Cloudflare + Airtable REAL (tablas nuevas, link mágico, lectura/escritura vía Functions) — la app deja de ser mock | 2-4 días |
| **F3** | Circuito de video por WhatsApp + aprobación por Telegram + acreditación de brasas (toca el agente: /pre-cambio) | 2-3 días |
| **F4** | Embudo Aurora completo (lead→Reto→camada→graduación→venta 350/450) + notificaciones + pantalla Familia real con PAGOS | 2-3 días |
| **F5** | Panel Fénix completo (valores, misiones, tienda, ceremonias, métricas) | 2-3 días |
| **F6** | Temporadas, patrullas, QR en zonas, eventos especiales (Copa Fénix / semana intensiva paga como evento de temporada) | continuo |

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
