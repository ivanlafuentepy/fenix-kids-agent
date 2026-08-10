# SPEC — DEFENSA DE LA CASONA (videojuego)
> Creado 12/07/2026 a partir de la visión de Iván (sesión de este día).
> Videojuego para que los Guardianes jueguen EN SU CASA, conectado a la economía
> real del Mundo Fénix. Hermano de `PLAN-MAESTRO.md` — no lo reemplaza: es un
> módulo más de la app (la "sala de juegos" del Mundo Fénix).

---

## 0. Visión en una frase

**La Casona es tu hogar y tenés que defenderla.** El niño juega en su casa como
su Guardián, protege La Casona de invasores que entran por el río y por la calle,
y gasta ahí las monedas que ganó ENTRENANDO de verdad. El esfuerzo físico real
compra poder en el juego — y el juego empuja a volver a entrenar.

## 1. Por qué existe (negocio)

1. **Retención lunes-viernes**: hoy el Mundo Fénix vive del reto/video diario.
   El juego da una razón MÁS para abrir la app todos los días.
2. **Sumidero de plata**: la economía necesita dónde gastar (salud monetaria =
   emitidas vs gastadas, PLAN-MAESTRO §9). El juego es el sumidero perfecto:
   armas, vidas y muros consumen plata sin costo físico para Fenix.
3. **Círculo único**: entrenás en La Casona → ganás monedas reales → sos más
   fuerte en el juego → querés más monedas → volvés a entrenar. Nadie más tiene esto.

## 2. El concepto

Género: **defensa de base con héroe** (tower defense + acción). No es solo
"disparar": es PROTEGER un lugar que el niño conoce y quiere de verdad.

### 2.1 El héroe
- El niño juega con **SU robotito Guardián** (el mismo que eligió en el onboarding,
  `assets/guardianes/` — ya existen los 10 PNG/webp optimizados).
- Se mueve por el mapa, dispara/pelea, junta poder.
- **Beto** (el labrador negro REAL de La Casona) lo acompaña en ciertas ocasiones:
  aparece en misiones, avisa por dónde viene el ataque, muerde enemigos cercanos.
  Beto no se compra ni se pierde: es un aliado que APARECE (cariño, no economía).

### 2.2 El escenario: La Casona real
- Mapa basado en La Casona de verdad (`assets/mapa_casona.jpg` como referencia).
- **Dos frentes de ataque, como en la realidad**:
  - 🌊 **Entrada del RÍO** (el muelle) — oleadas que llegan por el agua.
  - 🛣️ **Entrada de la CALLE** (los portones) — oleadas que llegan por tierra.
- Adentro: el **Banco** (donde vive su plata — si los enemigos llegan al banco,
  perdés la ronda), la casa, el patio.
- Afuera: **aventuras/misiones** en el río, el monte y la calle (salir a pelear
  fuera de los muros, riesgo mayor / recompensa mayor).

### 2.3 Los enemigos
- **Avatars invasores**: robotitos de OTRO color (paleta claramente distinta a
  los 10 Guardianes — rojos/violetas oscuros) que vienen en oleadas crecientes.
- **Jefes: los 4 Dragones del Código Fénix** (ya existen en la narrativa,
  PLAN-MAESTRO §10 — NO inventar un quinto):
  | Dragón | Vicio | Estilo de pelea en el juego |
  |---|---|---|
  | **Pigrus** | Pereza | Lento y gordo, aplasta muros, aguanta muchísimo daño |
  | **Timor** | Miedo | Aparece y desaparece, ataca por sorpresa desde el río |
  | **Khaos** | Desorden | Desordena tus defensas, invoca oleadas caóticas |
  | **Dubius** | Duda | Se clona en copias falsas; hay que encontrar al real |
- El dragón gigante llega CON su horda de avatars — jefe + oleada, como pidió Iván.
- Coherencia narrativa total: *"En casa los debilitás. En La Casona los vencés.
  En el juego los enfrentás."*

### 2.4 Construcción
- Mejorar la defensa de La Casona entre oleadas: **muros más altos**, portón
  reforzado en la calle, empalizada en el muelle, torretas (a definir cuáles).
- Lo construido **persiste** entre sesiones (tu Casona va quedando más fuerte —
  esa persistencia es el enganche de largo plazo).

### 2.5 Progresión dentro del juego
- Puntos por enemigo, combos, oleadas sobrevividas.
- Armas que evolucionan (mejor cadencia, más daño, disparo doble…).
- Vidas/escudos.
- Ranking de "Defensores de la semana" por categoría de edad (Mini/Fénix/Titanes),
  el mismo criterio de nunca mezclar edades del ranking existente.

## 3. Economía — LA REGLA DE ORO (no negociable)

El juego debe respetar la arquitectura de dos monedas del PLAN-MAESTRO §6.
Si el juego rompe la economía, rompe TODO el sistema. Reglas duras:

1. **El juego NUNCA emite monedas reales.** Ni oro ni plata. La regla madre es
   "toda la economía la disparan adultos/hardware, nunca el niño" — un juego en
   el celular de la casa es 100% falsificable. El juego emite solo **puntaje,
   trofeos y progreso interno** (rango de defensor, muros construidos).
2. **El juego GASTA plata real** (del ledger que ya existe): armas, vidas extra,
   materiales de construcción. La plata se gana entrenando (reto en casa, vueltas
   del circuito) → coherente con "la plata es por esforzarte".
3. **El oro NO se toca en el juego.** El oro sigue comprando lo físico (kepi,
   remera) en la Tienda Fénix existente — el juego puede MOSTRAR la tienda real
   ("con tu oro podés canjear la remera el sábado") pero el canje sigue siendo
   el flujo actual (pedido pendiente → retiro en La Casona).
4. **Precios en config** (Airtable, como todo): ajustables sin deploy. Arranque
   sugerido (calibrar con datos): vida extra 50 plata · mejora de arma 100-300 ·
   muro 150 · con topes diarios de gasto para que un nene no se funda en una tarde.
5. **Sin plata no se bloquea el juego.** Jugar es gratis siempre (arma básica,
   vidas base). La plata compra VENTAJA y ESTILO, nunca el acceso — misma
   filosofía "escalera de valor, no peaje" del PLAN-MAESTRO §6.

**Bonus de diseño**: el banco DENTRO del juego es el mismo Banco de Brasas real.
El niño defiende (literalmente) el edificio donde está su saldo verdadero. Si un
dragón llega al banco no pierde plata real (jamás castigar con plata real) —
pierde la RONDA y el puntaje de la ronda.

## 4. Identidad y seguridad (COPPA — heredado del Mundo Fénix)

- Acceso por **link mágico de familia** (`/?f=CODIGO`), igual que el resto de la
  app. Sin cuentas de niños, sin chat, sin nombres públicos.
- Identidad SIEMPRE por `nino_id` / GUARDIAN — nunca por nombre de pila (tocayos).
- **Sin juego online entre niños** en v1: los "otros avatars" enemigos son del
  juego (IA), NO otros niños conectados. PvP real = decisión aparte, mucho más
  adelante, con sus propios riesgos (COPPA, moderación, servidores).
- Modo demo sin código (como toda la app): se puede jugar con monedas de mentira.

## 5. Tecnología

- **HTML5 canvas + JS vanilla, un solo archivo** (`defensa.html`), como el resto
  de mundo-fenix. Sin motores, sin build, sin dependencias.
- Corre en el celular del padre / tablet (PWA existente). Vertical u horizontal
  a definir en el prototipo (probable horizontal).
- Controles táctiles: mover con el dedo (izquierda) + disparo automático o botón
  (derecha). Simple: lo juega un nene de 6.
- Persistencia: localStorage en demo; en la fase conectada, el estado del juego
  (construcciones, armas) viaja por los endpoints `/juego/*` de Railway que ya
  existen (patrón de F2: POST `/juego/accion`, montos del lado del servidor).
- Sprites: los guardianes ya existen; enemigos, dragones, Beto y el mapa los
  genero con las herramientas de imagen conectadas (Higgsfield) + retoque.
  El estilo debe matchear los robotitos existentes.

## 6. Fases de construcción

| Fase | Qué entra | Criterio de salida |
|---|---|---|
| **D0 — Prototipo jugable** | Un frente (la calle), héroe que se mueve y dispara, oleadas de avatars enemigos, vidas, puntaje, 1 dragón jefe (Pigrus). Beto aparece y ayuda. Todo local, monedas mock, arte placeholder + guardianes reales. | Iván lo juega en su celu y dice "esto es divertido" |
| **D1 — Los dos frentes + construcción** | Entrada del río, muros mejorables, portón, persistencia local, tienda del juego con plata mock, los 4 dragones | Un niño real lo juega 3 días seguidos sin que se lo pidan |
| **D2 — Conexión al ledger real** | Link mágico, gastar plata REAL vía `/juego/*`, topes diarios, banco real visible, ranking semanal | Piloto con 3-5 familias del piloto Mundo Fénix |
| **D3 — Arte y alma** | Sprites finales (enemigos, 4 dragones, Beto animado, mapa Casona ilustrado), sonidos, música, misiones afuera (río/monte) | Se siente "juego de verdad" |

**Gate**: D2 recién si D0/D1 demuestran diversión real. No conectar la economía
real a un juego que nadie juega.

## 7. Decisiones tomadas (12/07/2026)

1. Género: defensa de base con héroe (no shooter suelto) — visión de Iván.
2. Dos frentes = las dos entradas reales (río + calle) — visión de Iván.
3. Jefes = los 4 dragones del Código Fénix, no un dragón nuevo (Opus, coherencia).
4. Beto el labrador como aliado que aparece, fuera de la economía (visión Iván + Opus).
5. El juego es sumidero de plata: gasta monedas reales, NUNCA las emite (Opus,
   protege el piso duro y la regla adultos/hardware).
6. Remeras y cosas físicas siguen en la Tienda Fénix con oro — el juego solo
   las vitrinea (coherencia con PLAN-MAESTRO §6).
7. Enemigos "otros avatars" = IA del juego, no PvP online en v1 (COPPA/alcance).

## 8. Decisiones ABIERTAS (para Iván)

1. **Nombre del juego** para los niños: "Defensa de La Casona", "La Batalla de
   La Casona", "Guardianes al ataque"… (el archivo/código queda `defensa`).
2. ¿El juego vive DENTRO de la app Mundo Fénix (un botón más del menú) o como
   pantalla propia con link directo? (Propuesta: dentro, es un módulo más.)
3. Topes de gasto diario de plata en el juego (propuesta inicial: 300/día).
4. ¿Vidas se regeneran solas con el tiempo (estilo mobile) o solo se compran?
   (Propuesta: 3 vidas gratis por día + extras con plata — jugar nunca se bloquea.)
5. Horizontal vs vertical (se decide probando el prototipo D0).
