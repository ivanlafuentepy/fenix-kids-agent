# SPEC — MUNDO FÉNIX SOCIAL (Roblox) · MVP V1
> Creado 12/07/2026. Autor de la visión: Iván. Decisiones de arquitectura/seguridad
> trabajadas con Opus en esta sesión.
> Documento OFICIAL del videojuego. Reemplaza a `SPEC-DEFENSA-CASONA.md` (shooter/
> tower-defense), DESCARTADO el 12/07 por pivote de concepto.
> Hermano de `PLAN-MAESTRO.md` — el Mundo Social es la "cara para el niño" del Mundo Fénix.

---

## 0. Visión

Fénix **no compite con Roblox.** Usa Roblox para crear una comunidad donde los niños
**muestran el progreso que consiguieron en la vida real.** El verdadero juego ocurre
entrenando; el mundo virtual existe para mantener la motivación entre un sábado y el
siguiente.

> **Misión: entrenar en la vida real para convertirse en el Guardián Fénix más
> respetado de la Academia.**

## 1. Filosofía (la inversión)

En casi todos los videojuegos: **jugás para hacer crecer a tu personaje.**
En Fénix: **entrenás para hacer crecer a tu personaje.**
El videojuego nunca reemplaza el entrenamiento. Siempre lo recompensa.

**Por qué esto es correcto (y por qué se descartó el shooter):** un juego de acción
divierte por sí solo → *compite* con el entrenamiento (el niño juega en vez de entrenar).
El Mundo Social es anti-adictivo por diseño (sin combate, sin gameplay que enganche solo,
energía limitada) → **no puede comerse al entrenamiento**, solo lo celebra. Coherente con
el objetivo del PLAN-MAESTRO: *"no buscamos que pasen horas conectados"*.

## 1b. El verbo del juego — EN ROBLOX NO SE GANA, SE DECIDE Y SE GASTA (corazón del diseño)

Resuelve la tensión central: si en Roblox el niño *hiciera algo que le da valor*, el juego
competiría con entrenar; si *solo mirara*, se aburriría. La salida es el **verbo**:

> **En Roblox el niño no GANA nada. RECLAMA, DECIDE y GASTA lo que ya ganó entrenando en la
> vida real.**

Analogía: la plata se gana trabajando (esfuerzo real); lo divertido no es *imprimirla* —eso
sería trampa— sino **gastarla con criterio** y ver el resultado. El "hacer" en Roblox no es
la fuente del valor: es donde el niño **materializa** el esfuerzo que trajo de La Casona. Así
no compite con entrenar, lo **corona**.

**Las 5 acciones del niño en Roblox (todas gastan/deciden, ninguna emite valor):**
1. **RECLAMAR (la cosecha).** Lo ganado entrenando no cae solo: el niño entra a recogerlo
   ("entrené 3 días → tengo Plata + una Llave esperando"). Es la acción diaria, la dopamina
   del hábito, el motivo de los 10 minutos.
2. **DECIDIR en qué invertir (el gameplay real).** Plata escasa: ¿subo de nivel la Casa?
   ¿evoluciono el Fénix? ¿guardo para una caja grande? No alcanza para todo → elegís → tus
   elecciones te definen. **La decisión ES el juego** (sin disparar a nada).
3. **CUIDAR al Fénix (vínculo emocional).** Lo alimentás con Plata, crece, cambia con vos.
   ⚠️ Regla dura (PLAN-MAESTRO): el Fénix **nunca sufre ni muere por ausencia** (no castigar
   la ausencia) — solo prospera *más* cuando lo cuidás. Positivo, jamás punitivo.
4. **ABRIR cajas (el momento mágico).** Llaves ganadas entrenando → abrir es un acto con
   suspenso; la caja queda para siempre con tu nombre. Coleccionar.
5. **CONTEMPLAR la evolución propia.** El museo del esfuerzo: Casa que subió de nivel, Fénix
   más grande, cajas abiertas. Pasivo, pero es el "para qué".

**Por qué alcanza para enganchar:** la comparación NO es Fortnite, es el **Tamagotchi / el
reclamo diario de los juegos de celular / los coleccionables tipo Pokémon** — enganchan a
millones con poco "hacer": progreso visible + hábito diario + una mascota + coleccionar.
Nadie dispara y vuelven todos los días.

**El motor secreto = la ESCASEZ.** Si sobrara Plata, nada importaría. Como cuesta sudor,
cada decisión pesa y el mundo de cada niño termina único (refleja SUS elecciones sobre SU
esfuerzo). Esa diferencia se ve en la pantalla web de La Casona (§6.1).

**Ajuste con §4.1 (Casa evoluciona sola):** gastar Plata **sube el NIVEL** de la Casa, y al
subir de nivel cambia sola de aspecto. No es decorar libremente (eso es el editor
descartado) — es *asignar esfuerzo escaso* entre pocas vías (Casa / Fénix / cajas). Esa es
la decisión con valor, sin abrir la personalización libre.

## 2. Loop principal

**En casa** → el niño entrena → obtiene **Plata** + **Energía Fénix** (10 min de acceso).
**En La Casona (sábado)** → asiste, completa circuitos → **Plata + Oro**, sube en el
Ranking, gana Insignias, puede conseguir una **Llave** y desbloquear una **Caja**.
**En el Mundo Fénix (Roblox)** → con la energía, el niño puede: ver su Casa del Árbol,
ver su Fénix, reclamar recompensas, abrir Cajas, visitar a otros Guardianes, comparar
Rankings, ver la evolución de sus amigos. Cuando la energía se acaba → **a entrenar de nuevo.**

## 3. Qué ES y qué NO ES el Mundo Fénix

**ES** una comunidad / red social diseñada para niños, donde todo gira alrededor del
progreso. **NO ES** un MMORPG, ni juego de aventuras. **Sin** misiones, enemigos, combates.

## 4. Los cinco pilares

### 4.1 🌳 Casa del Árbol
Una por jugador. **No se construye, no se edita, no se personaliza libremente: EVOLUCIONA.**
10 niveles; cada nivel cambia automáticamente toda la apariencia. Representa el progreso
del niño. *(Decisión clave: al no haber editor de construcción, el trabajo visual se reduce
a preparar los 10 estados de la casa — no un mundo entero. Esto resuelve el problema del
"mapa 3D manual".)*

### 4.2 🔥 El Fénix
Compañero permanente, siempre presente. Evoluciona conforme el niño progresa. Representa
visualmente el esfuerzo.

### 4.3 👑 Las Capas
El mayor símbolo de prestigio. **Solo se ganan entrenando; nunca se compran.** Cada capa
nueva modifica automáticamente: el avatar, el aspecto del Fénix y las banderas de la Casa.
Desde lejos, cualquiera reconoce el nivel alcanzado. *(Métrica de capas = dragones vencidos,
según PLAN-MAESTRO §10 — no monedas ni asistencia.)*

### 4.4 🎁 La Bóveda
Las Llaves abren Cajas; el jugador decide cuál abrir. Cada caja abierta queda abierta para
siempre, con el nombre del ganador y el premio encima. Las cajas legendarias requieren
muchas llaves + Oro + varios meses de constancia, y contienen premios importantes,
generalmente **físicos** (remeras, gorras, botellas, mochilas). Ver §6.3 sobre cómo se
manejan los premios físicos.

### 4.5 🏆 Ranking
El corazón del mundo. Los niños ven quién entrenó más, quién tiene más Plata/Oro, la mejor
Casa, el Fénix más evolucionado, la capa más alta. **La competencia es entre niños que se
conocen de verdad** → mucho más compromiso que competir contra desconocidos.

## 5. Economía (hereda del PLAN-MAESTRO §6)

- **🥈 Plata** — se gana entrenando en casa + circuitos del sábado. Sirve para: evolucionar
  la Casa del Árbol, alimentar/evolucionar el Fénix, abrir ciertas cajas, mejoras de progreso.
- **🥇 Oro** — se gana por asistencia y grandes logros. Es prestigio; da acceso a contenido
  exclusivo.
- **⚡ Energía Fénix** — entrenar genera energía; la energía habilita **10 min** de acceso al
  Mundo. **Nunca se compra, solo se entrena.** Cuando se acaba, hay que volver a entrenar.

**Regla madre (no negociable):** el Mundo en Roblox **LEE y GASTA** monedas reales, pero
**NUNCA las emite.** Toda emisión de Plata/Oro/Energía la disparan adultos/hardware (profe,
lector facial, validación de video) — igual que hoy. Un cliente Roblox es falsificable; si
emitiera monedas, rompería el piso duro de toda la economía.

## 6. Decisiones de arquitectura y seguridad (resueltas 12/07/2026)

### 6.1 🚨 COPPA — lo SOCIAL vive en La Casona, no en Roblox (decisión Iván 12/07)
El sistema es para niños 3-12 (COPPA + ley de datos PY). El problema: Roblox endureció las
reglas de comunicación entre menores (age-check facial, chat apagado para <9 — ver §9 🔴).
**Solución de Iván:** sacar TODA la capa social de Roblox y mostrarla en una **pantalla real
en La Casona**, controlada por Fenix. Así las reglas de Roblox sobre comunicación entre
menores **no aplican** (no es cuenta-a-cuenta en Roblox, es una pantalla nuestra). La
división:
- **Roblox (en casa) = mundo PERSONAL, single-player.** El niño ve y hace crecer SU Fénix,
  SU Casa, SUS cajas, SU progreso. **No ve a otros niños, no interactúa con nadie dentro de
  Roblox.** Cero comunicación entre menores → cero fricción de edad.
- **Pantalla en La Casona = la VITRINA SOCIAL.** Ahí se ven las Casas de los compañeros, el
  Ranking, quién subió de capa, quién abrió una caja legendaria. Presencial, en la TV, como
  ya hacen el Mapa Vivo y el Modo TV (PLAN-MAESTRO §5.3b: *"la TV es el refuerzo social...
  estatus puro"*). El niño se motiva viendo a los demás EN La Casona, no en su casa.
- **Identidad por nombre de Guardián / apodo**, nunca el nombre real, en la pantalla y el
  ranking.
- **La pantalla de La Casona es WEB** (decisión Iván 12/07). Reusa el patrón `mapa.html`:
  lee el mismo Airtable y muestra el progreso de todos (casas, ranking, capas). El look 3D
  lindo de la Casa lo ve el niño en Roblox en su casa; la comparación social se ve en la web
  de La Casona. No hace falta correr Roblox en la TV.
- **Mensajes de aliento entre compañeros: DESCARTADOS** (decisión Iván 12/07). No aportan lo
  suficiente como para justificar reintroducir comunicación menor-a-menor. Fuera del alcance.

### 6.2 🔗 Vínculo de identidad (cuenta Roblox ↔ GUARDIAN de Airtable)
Todo depende de que Roblox sepa qué GUARDIAN es cada cuenta, para leer su Plata/Oro/Capas
reales. Mecanismo (aprobado 12/07, reusa el patrón del link mágico):
- **Aurora manda por WhatsApp un código de vinculación** (como `/?f=CODIGO`). El niño (con
  el padre) lo pega **una vez** dentro de Roblox → queda emparejado para siempre.
- Padre siempre de por medio. Roblox llama a los endpoints `/juego/*` del Railway del agente
  (vía HttpService) para leer el estado real; nunca escribe monedas.

### 6.3 🎁 Premios físicos — asignados en Roblox, retirados afuera
- Cuando el niño gana un premio físico (remera, gorra), **Roblox solo le ASIGNA el ítem como
  trofeo visual** ("tenés una remera Fénix"). Queda ahí como estatus.
- Roblox **no** promete ni procesa la entrega. El retiro material es un asunto **entre Iván y
  el padre, por fuera** (Airtable marca "premio pendiente de retiro" → se entrega en La
  Casona, como la Tienda Fénix actual). El niño no necesita instrucciones de retiro dentro
  del juego.
- Esto muy probablemente esquiva las reglas de Roblox sobre bienes reales (Roblox no procesa
  la transacción). **PENDIENTE de verificar** los términos de Roblox antes de lanzar (§8).

### 6.4 🪟 División app web (padre) vs Roblox (niño)
Para no construir dos veces lo mismo (ranking/perfil/banco/tienda ya existen o están
planeados en la app web del PLAN-MAESTRO):
- **App web Mundo Fénix = para el PADRE:** pagos, progreso del hijo, gestión, subir videos.
- **Roblox = para el NIÑO:** su Fénix, su Casa, estatus, ver a los amigos.
- **Una sola fuente de datos (Airtable), dos ventanas** según quién mira. El Railway del
  agente es el backend común.

## 7. Perfil del Guardián
Nombre de Guardián, avatar, capa actual, nivel de Casa, evolución del Fénix, Plata, Oro,
insignias, récords, entrenamientos en casa, asistencias a La Casona. Es el historial completo
de su crecimiento.

## 8. Qué NO tendrá la V1 (disciplina de scope)
Sin: combates, dragones enemigos, RPG, historia, NPC, construcción libre, editor de casas,
misiones, comercio entre jugadores, objetos complejos, minijuegos. Todo eso se evalúa para
versiones futuras SOLO si aporta valor real. *(Misma regla que el PLAN-MAESTRO §10: no apilar
sub-sistemas de golpe.)*

## 9. Verificación de términos de Roblox (hecha 12/07/2026)

Semáforo por tema, con lo verificado en las fuentes oficiales:

### ✅ VERDE — permitido, valida el diseño
- **Conectar a tu servidor Railway.** HttpService es feature soportado: las experiencias
  pueden llamar a servidores externos (GET/POST) para leer/escribir estado. El vínculo con
  `/juego/*` es legal. (Hay que habilitar HttpService en Studio; algunos headers están
  bloqueados; cuidar seguridad.)
- **Las Cajas con Llaves GANADAS entrenando NO son "paid random item".** Textual de Roblox:
  *"Si un usuario localiza una llave que abre un cofre, no necesitás indicar las
  probabilidades."* → nuestras cajas (llaves ganadas por esfuerzo, nunca compradas con
  Robux/dinero) quedan FUERA de la regulación de loot boxes y de la obligación de mostrar
  odds. ⚠️ Si algún día se vendieran llaves por Robux, ahí SÍ caería en esa regulación
  (mostrar probabilidades, restricciones a menores). Diseño actual: limpio.
- **Progreso personal visible** (Fénix, Casa que evoluciona, Capas, Ranking, perfil): no
  toca ninguna regla de comunicación. Es el núcleo seguro del MVP.

### 🟡 AMARILLO — se puede, con cuidado
- **Premios físicos.** La política de random items NO cubre bienes físicos (fuera de su
  alcance); los términos generales dicen que el contenido virtual "no tiene valor del mundo
  real". Roblox tiene un programa Commerce restringido para vender productos físicos (vía
  Shopify autorizado). Nuestro modelo §6.3 (Roblox solo muestra el trofeo; el canje material
  se hace 100% afuera, entre Iván y el padre) es defendible porque Roblox no procesa nada.
  **Conviene confirmarlo** cuando tengamos cuenta de creador, pero no es bloqueante.
- **Vínculo por código WhatsApp.** Traer un código HACIA Roblox (el niño lo pega adentro)
  está bien. PERO Roblox prohíbe **dirigir usuarios FUERA de la plataforma**: nada de links,
  QR ni "andá a WhatsApp" dentro del juego (solo se permiten links a redes sociales
  aprobadas — YouTube, Discord, Instagram… WhatsApp NO está en la lista). Regla: el juego
  NUNCA empuja al niño hacia afuera; la comunicación con el padre/negocio vive afuera.

### 🔴 ATENCIÓN GRANDE — la EDAD es el mayor condicionante
Roblox endureció fuertemente las reglas de comunicación para menores (nov-2025 → 2026):
- **Age-check obligatorio** (incluso estimación facial) para acceder al chat.
- **Menores de 13:** chat filtrado (contenido + bloqueo de datos personales).
- **Menores de 9:** comunicación **apagada por defecto**, salvo consentimiento parental tras
  age-check. Grupos de edad (under-9 / 9-12 / …) definen quién puede comunicarse con quién.
- **La franja de Fénix (3-12, muchos <9) es JUSTO la más restringida de la plataforma.**

**Implicancia para el diseño → RESUELTO por §6.1:** en vez de pelear con estas reglas, la
capa social se saca de Roblox y se muestra en la **pantalla de La Casona**. Roblox queda
**100% personal / single-player** (sin comunicación entre menores) → estas restricciones de
edad **dejan de aplicar** al mundo de Roblox. El MVP en Roblox es el progreso personal
(Fénix, Casa, Capas, cajas); lo social es presencial en La Casona. Riesgo neutralizado.

### Otros pendientes (no legales)
- **Trabajo visual en Studio es humano.** Claude escribe el 100% de scripts (Luau) y genera
  geometría por código, pero no opera el editor visual con el mouse. Los assets que
  evolucionan (10 casas, Fénix, capas) los arma Iván/colaborador — acotado, no un mundo.
- **Latencia HttpService ↔ Railway** — validar que leer el estado del Guardián no trabe.
- **Los 10 min de energía** deben tener suficiente dopamina (abrir cajas, ver evoluciones).

**Fuentes:** [Roblox Requires Age Checks for Chat](https://about.roblox.com/newsroom/2025/11/roblox-requires-age-checks-limits-minor-and-adult-chat) ·
[Paid random items policy](https://create.roblox.com/docs/production/monetization/paid-random-items) ·
[HttpService docs](https://create.roblox.com/docs/cloud-services/http-service) ·
[Advertising Standards (off-platform)](https://en.help.roblox.com/hc/en-us/articles/13722260778260-Advertising-Standards) ·
[Safety Features: Chat/Privacy](https://en.help.roblox.com/hc/en-us/articles/203313120-Safety-Features-Chat-Privacy-Filtering)

## 10. Fases sugeridas (borrador — refinar tras validar §9)
| Fase | Qué | Nota |
|---|---|---|
| **R0** | Iván juega Roblox unas noches + baja Roblox Studio; verificar términos (§9.1) | Cero código. Decide si el camino es viable |
| **R1** | "Hola mundo": una Casa del Árbol básica + avatar que camina + vínculo por código WhatsApp leyendo Plata/Oro reales | Prueba el flujo técnico end-to-end con 1 familia |
| **R2** | Los 5 pilares en V1: Casa (10 niveles), Fénix, Capas, Bóveda/Cajas, Ranking + mensajes predefinidos + visitas asíncronas | El MVP jugable |
| **R3** | Piloto con las 5-10 familias del piloto Mundo Fénix + ajuste de economía/energía | Gate de negocio |

## 10.1 Desglose del R1 (en curso desde 13/07)
El R1 se parte en pasos chicos para no arriesgar producción (deploy incremental):
- **R1.1 — El loop local (SIN Railway, SIN producción).** ✅ arrancado 13/07.
  `roblox/R1_CasaDelArbol.lua`: LocalScript que corre en Studio con Plata SIMULADA. Prueba el
  verbo §1b (reclamar → decidir → gastar → ver la Casa evolucionar de nivel). Objetivo: que
  Iván *sienta* el loop antes de conectar nada. Nota: Claude NO puede ejecutar Luau — el
  script se escribe con cuidado pero se prueba en el Studio de Iván; ajustes ahí.
- **R1.2 — Conectar Plata/Oro REALES.** El "Reclamar" deja de ser mock y lee el estado del
  Guardián desde un endpoint de Railway vía HttpService. Tocar el agente = requiere
  `/pre-cambio` + `/pre-deploy` + un endpoint de solo-lectura (Roblox NUNCA escribe monedas).
- **R1.3 — Vínculo por código.** Aurora manda un código por WhatsApp; el niño lo pega una vez
  en Roblox → empareja la cuenta Roblox con su GUARDIAN (§6.2). Recién acá el flujo es
  end-to-end con 1 familia.

## 11. Frase del proyecto
> **El entrenamiento ocurre en la vida real. El Mundo Fénix lo convierte en una aventura
> compartida.**
