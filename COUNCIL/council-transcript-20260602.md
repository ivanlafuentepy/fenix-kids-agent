# Council Transcript — Rediseño de datos del universo Iván Lafuente
**Fecha:** 02/06/2026
**Metodología:** LLM Council (Karpathy) — 5 advisors + peer review anonimizado + chairman
**Ejecución:** Workflow multi-agente (11 sub-agentes, ~110s)

---

## Pregunta Original

"No me convence mi sistema en Airtable de Fénix — lo de familia Fénix y niños está complicado, y el pago se me está complicando. Quiero un análisis profundo del universo Fénix (familias, niños, reservas, pagos), que destruyas mi idea de manejar todo bajo una sola tabla de Alumnos, y me des las mejores opciones. Después se reveló que el universo es un holding de ~9 negocios."

---

## Pregunta Enmarcada (con contexto enriquecido)

Iván Lafuente, emprendedor paraguayo, trabaja SOLO. Tiene un holding de ~9 líneas de negocio: Salsa Soul Studio (academia adultos, cuota mensual), Fénix Kids (academia niños, plan familiar — el que asiste no es el que paga), Curso IA (inscripción por edición), ventas de PC, Alma Latina (zapatos/ropa), Mamba Basket (remeras/pelotas) — los tres retail —, Uber/Bolt (gig), alquiler de la casona, y facturación B2B del Edificio Líder.

**Estado de los datos (auditado):** 2 bases Airtable. "CURSO IA" tiene un modelo relacional limpio. "SALSA SOUL APP.2" (39 tablas) mezcla Salsa adultos + Fénix niños, unidos por dos tablas compartidas: PAGOS y FACTURAS. Casona y retail no están en Airtable. Los agentes WhatsApp (Dorita, Fénix Agent) LEEN y ESCRIBEN estos datos por API — el dato es el backend en producción.

**Diagnóstico técnico:** (1) Identidad triplicada en Fénix: el mismo niño/familia se re-tipea en LEADS FENIX, PRUEBA FENIX y FAMILIAS+NIÑOS FENIX; el checkbox CONTROL DATOS delata el chequeo manual. (2) PAGOS polimórfico: cuelga de 4 padres (ALUMNO, FAMILIA FENIX, PRUEBA FENIX, RESERVA LEADS) + plata dispersa en VESTUARIOS/ENTRADAS/GASTOS. (3) El padre de Fénix es texto plano, desconectado de su registro de ALUMNOS si baila salsa. (4) ALUMNOS tiene 79 campos.

**Propuesta original de Iván:** una sola tabla de Alumnos para todo. **Contrapropuesta en discusión:** party model + hub&spoke — núcleo PERSONAS + HOGARES + VENTAS + PAGOS + FACTURAS, cada negocio como radio. **Decisión de herramienta:** Airtable ahora / Postgres+NocoDB después.

**Restricción crítica (council previo sobre Dorita, 24/05/2026):** Iván está solo sosteniendo Dorita (monolito 3594 líneas, 72 bugs, rebuild de 8-10 semanas), Fénix Agent, clases y 2 academias. Conclusión unánime de ese council: el cuello de botella es el TIEMPO de Iván; "escalar antes de estabilizar" es el punto ciego clásico; auditar antes de comprometer; nunca big-bang.

**Las 3 sub-preguntas:** ¿Es correcto el modelo Personas+Ventas+Pagos? ¿Airtable o Postgres? ¿Cuál es el alcance correcto — solo Fenix+Pagos, o el holding completo?

---

## Respuestas de Advisors

### The Contrarian

El fallo fatal no está en el modelo de datos. El modelo Personas+Ventas+Pagos es correcto — de hecho es tan correcto que ahí está la trampa. Es elegante, normalizado, resuelve la identidad triplicada y el pago polimórfico de raíz. Por eso mismo Iván lo va a querer hacer entero. Y ese deseo de hacerlo entero es exactamente el mecanismo por el que este plan se rompe. El council de Dorita ya dijo, unánime, que el cuello de botella es el tiempo de Iván y que el punto ciego es "pensar en plataforma antes de estabilizar". Estamos a punto de repetir el error con un nombre más bonito: "party model".

Hagamos la cuenta que nadie quiere hacer. Rediseñar el holding completo significa: migrar 39 tablas, reescribir las automatizaciones internas de Airtable, y — esto es lo que se está minimizando — re-puntar los agentes que LEEN y ESCRIBEN esos datos por API. Dorita y Fénix Agent no son lectores pasivos: son el backend en producción. El día que PAGOS deje de colgar de 4 padres y pase a colgar de Ventas, todo call site del agente que escribe un pago se rompe. ¿Cuántos call sites hay? Nadie en este council lo contó. Y Dorita ya es un monolito de 3594 líneas con 72 bugs en pleno rebuild de 8-10 semanas. Vas a mover el piso de datos abajo del agente que estás reconstruyendo arriba, al mismo tiempo, vos solo. Eso no es un plan, es dos cirugías a corazón abierto simultáneas sobre el mismo paciente.

Posición sobre el alcance, sin anestesia: NADA de rediseñar el holding. El holding completo es una fantasía de fin de semana que va a comer tres meses. El dolor real que Iván articuló fue una sola frase y fue quirúrgica: "lo de familia Fénix y niños está complicado, y el pago se me está complicando". No dijo "no puedo ver el consolidado de las 9 líneas". No dijo "necesito a la persona unificada entre salsa y fénix". Esos son dolores que VOS proyectaste, no que él sintió. El alcance correcto es brutal y chico: arreglar la identidad triplicada de Fénix (colapsar LEADS+PRUEBA+FAMILIAS+NIÑOS a un flujo sin re-tipeo, matar el checkbox CONTROL DATOS) y arreglar el pago de Fénix. Nada de Salsa, nada de retail, nada de Casona, nada de Uber. Un radio. El que duele.

Sobre Airtable vs Postgres: la pregunta está mal planteada y por eso es cómoda. No es "ahora Airtable, después Postgres". Es: cualquier cosa que toques HOY tiene que dejar de empeorar el costo de salida, no aumentarlo. Si construís el party model completo dentro de Airtable, estás cavando MÁS hondo en la herramienta de la que decís que algún día te vas a ir — más automatizaciones nativas, más fórmulas, más dependencia del agente sobre el schema de Airtable. El "después migramos a Postgres" se vuelve infinitamente más caro con cada tabla nueva que metés. Si de verdad Postgres es el destino, el movimiento honesto no es hacer el gran modelo en Airtable; es hacer el arreglo MÍNIMO de Fénix en Airtable y no construir ni una automatización nueva que no sepas portar. Pero seamos sinceros: Postgres+NocoDB hoy, solo, con Dorita ardiendo, tampoco. Eso es el mismo error de plataforma vestido de open-source.

Hay una mentira piadosa enterrada en "todo es Iván Lafuente". Técnicamente la persona unificada es linda. Operativamente, ¿qué decisión concreta de Iván cambia mañana por saber que el papá de un niño Fénix también baila salsa? ¿Le va a vender un combo? ¿Tiene tiempo para una campaña de cross-sell estando solo y con un agente roto? Si la respuesta es "no por ahora" — y lo es — entonces la persona unificada cross-negocio es belleza arquitectónica que no paga renta. Se diseña para un Iván que tiene equipo, no para el Iván que está solo apagando incendios.

La pregunta que este council está esquivando con el diagrama bonito del party model es esta: si Iván solo tiene, siendo generoso, 6 horas reales por semana libres de Dorita, las clases y las dos academias — ¿en qué universo termina una migración de 39 tablas con re-cableado de dos agentes en producción antes de que algo crítico se caiga y se quede caído durante un mes? Y si la respuesta honesta es "en ninguno", ¿por qué seguimos dibujando el holding entero en vez de preguntarle a Iván cuál es la UNA query de Fénix que hoy no puede responder y que le está costando plata o sueño esta semana?

### The First Principles Thinker

El nombre de esto no es "rediseño de Airtable". Despojado de jerga, lo que tenés es UN libro mayor contable de una sola persona que cobra plata de muchas formas distintas. El verdadero objeto del universo Iván Lafuente no es "Alumno", no es "Familia", no es "Producto": es la TRANSACCIÓN — entró o salió plata, de quién, por qué concepto. Todo lo demás (que el que baila sea niño o adulto, que el producto sea una clase o un par de zapatos) es decoración alrededor de ese hecho. La propuesta de Iván ("una sola tabla de Alumnos para todo") y la contrapropuesta (Personas+Ventas+Pagos) están peleando por la entidad equivocada como centro. El centro es Ventas/Pagos. Personas y Hogares son atributos de la transacción, no al revés.

Y acá está la causa raíz, que el diagnóstico técnico ya tiene servida pero no nombra: el dolor de Iván ("el pago se me complica") y la identidad triplicada son EL MISMO bug. PAGOS es polimórfico (cuelga de 4 padres) precisamente PORQUE no hay una entidad Venta que homogenice el "por qué" del pago. Y la identidad se triplica porque no hay una entidad Persona que homogenice el "quién". Son dos agujeros del mismo modelo: falta la capa intermedia que diga "este evento comercial, de esta persona". Por eso un fix chico de pagos sin Personas, o de Personas sin Ventas, no resuelve nada — son la misma costilla. Eso responde tu primera sub-pregunta: SÍ, el modelo Personas+Ventas+Pagos es correcto, pero por una razón más dura que "es más prolijo": es el mínimo modelo que hace desaparecer los dos dolores a la vez, no es over-engineering, es la forma natural del problema.

Ahora separá complejidad real de accidental, porque acá el consejo se va a equivocar de alcance. La complejidad REAL es: Personas (1 humano = 1 fila), Ventas (todo cobro es una venta), Pagos (cuelga de UNA venta). Eso es irreductible y es chico — tres tablas conceptuales. La complejidad ACCIDENTAL es todo lo demás que el contexto está metiendo en la misma decisión: los 9 negocios, el retail con catálogo+stock, la casona, el patrón de órdenes, Postgres vs NocoDB, el techo de records de Airtable. Nada de eso es el problema de Iván HOY. Iván no dijo "no puedo consolidar el holding", dijo "Fénix y el pago se me complican". El holding completo es un problema que Iván IMAGINA, Fénix+Pagos es el problema que Iván TIENE.

Por eso el alcance correcto es brutalmente más chico que las dos opciones que planteás. No es "Fénix+Pagos con acción chica" NI "rediseñar el holding". Es: instalar el NÚCLEO (Personas + Ventas + Pagos) usando Fénix como primer y único cliente de ese núcleo. Migrás solo Fénix encima del núcleo nuevo, colapsás las 3 tablas de identidad en Personas+Hogares, hacés que PAGOS cuelgue de Ventas. Salsa, Curso, retail, casona NO se tocan — siguen como están, y cada uno se engancha al núcleo después, de a uno, cuando duela. El núcleo se diseña pensando en que un día entren todos (esa es la única concesión al futuro que pagás hoy, y es barata: nombrar bien las tablas). Pero la migración es módulo por módulo, exactamente lo que el council de Dorita ya dictó UNÁNIME: nunca big-bang. Rediseñar el holding completo ahora es el punto ciego que ese mismo council nombró: pensar en plataforma antes de estabilizar.

Sobre la herramienta: quedate en Airtable, y la razón de primeros principios es que el techo de records es un problema FALSO en tu escala. ¿Cuántos humanos hay en todo el universo Iván Lafuente? ¿Miles? Airtable aguanta 50.000 records por base en planes pagos. No vas a tocar ese techo con personas reales de Paraguay en años. El verdadero costo de migrar a Postgres+NocoDB ahora no es el techo — es el TIEMPO de Iván, que es el único recurso escaso del sistema entero, y que ya está comprometido en un rebuild de Dorita de 8-10 semanas. Migrar de herramienta es resolver un problema que no existe (escala) gastando el recurso que sí escasea (Iván). Postgres es la respuesta correcta a una pregunta que todavía no se hizo. Cuando el retail crezca o cuando Airtable realmente duela, migrás — y para entonces el modelo Personas+Ventas+Pagos ya estará probado y será trivial de portar, porque es agnóstico de la herramienta.

La pregunta incómoda que el resto del consejo va a esquivar: si Iván está SOLO, con Dorita en 72 bugs y un rebuild de 8-10 semanas encima, y dos academias y clases corriendo — ¿por qué estamos diseñando el data model del holding en vez de preguntarnos si Fénix+Pagos siquiera merece tiempo de Iván ESTE trimestre, o si lo único honesto es escribir el modelo del núcleo en una hoja, dejarlo guardado, y NO tocar Airtable hasta que Dorita esté de pie? ¿Estamos resolviendo el dolor de Iván, o nos estamos divirtiendo con un problema de modelado bonito mientras el incendio real (Dorita, el único sistema que le da de comer hoy) sigue ardiendo?

### The Expansionist

El modelo Personas+Ventas+Pagos no es solo correcto: es lo único en toda esta conversación que tiene chance de convertirse en un ACTIVO en vez de seguir siendo un costo de mantenimiento. La identidad triplicada y el PAGOS polimórfico de 4 padres no son bugs de Fénix — son el síntoma de que Iván tiene NUEVE negocios y CERO capa de identidad común. Cada negocio nuevo que abrió (retail PC, Alma Latina, Mamba, casona) hoy nace huérfano porque no existe el núcleo donde colgarlo. Lo que estamos diseñando no es "arreglar Fénix", es la columna vertebral de datos del holding Iván Lafuente. Eso es exactamente lo que el resto del consejo va a subestimar.

Y acá está lo que nadie en la mesa está viendo: PERSONAS + HOGARES + VENTAS + PAGOS + FACTURAS no es un esquema de Airtable, es un PRODUCTO. Iván no es el único paraguayo con un micro-holding de academias y retail atado con alambre. Esta party-model + hub&spoke, ya integrada con agentes de WhatsApp que LEEN y ESCRIBEN el backend, es precisamente el sistema que cualquier dueño de gimnasio, academia de música, jardín maternal o cadena de cursos necesita y no sabe pedir. Lo que para el resto del consejo es "deuda técnica de un solo, sostenido por un tipo cansado", para mí es el día-cero de una plataforma vertical de CRM+cobros+agente para PyMEs latinas. El curso de IA + las ventas de PC ya son su canal de distribución: cada alumno que arma su PC es un futuro usuario de este sistema.

Ahora, herramienta: Postgres, pero NO ya. El techo de records de Airtable y la imposibilidad de enlazar entre bases es exactamente la pared con la que Iván se va a estrellar el día que el núcleo unifique 9 negocios — un solo PERSONAS con clientes de salsa + niños + curso + retail revienta los 50k records de Airtable y te obliga a sincronizadas read-only que matan justo el party-model. El destino correcto es el Postgres que YA tiene en Railway, con NocoDB encima. Pero el dato que define una plataforma es el SCHEMA, no el motor. Si modelás PERSONAS/VENTAS/PAGOS bien en Airtable hoy, ese mismo DDL se exporta a Postgres mañana casi 1:1. Airtable es el prototipo pago de tu producto, no tu cementerio.

Sobre el alcance — y acá traiciono un poco mi instinto: el modelo del holding completo es correcto en el PAPEL, hoy. El alcance de EJECUCIÓN tiene que ser Fénix+Pagos solo. No porque pensar en grande esté mal, sino porque el activo se construye encarnando el esquema en el dominio más doloroso primero. Fénix tiene la identidad triplicada Y el PAGOS polimórfico — es el caso de prueba que valida TODA la arquitectura del núcleo. Si PERSONAS+HOGARES+VENTAS+PAGOS resuelve limpio el "papá que paga pero no baila, niño que baila pero no paga", entonces ese mismo núcleo absorbe Salsa, Curso y retail sin rediseño. Diseñás el holding entero en el diagrama; implementás un solo radio. El error no es soñar la plataforma — es construir nueve radios antes de que uno solo respire.

Lo que me preocupa del rebuild de Dorita de 8-10 semanas corriendo en paralelo: ese monolito de 3594 líneas con 72 bugs ESCRIBE en este mismo backend que estamos por rediseñar. Si reconstruís Dorita contra el esquema viejo polimórfico, acabás de pagar 8-10 semanas para acoplar tu agente más caro al modelo de datos que ya decidiste matar. El orden importa más que el alcance: el núcleo PERSONAS/VENTAS/PAGOS debería existir ANTES de que la primera línea del Dorita reconstruido toque la DB.

La pregunta incómoda que todos en la mesa están esquivando: si Iván está tan saturado que el consejo entero define su tiempo como el cuello de botella — ¿qué pasa el día que se enferma una semana? Nueve negocios y un agente de IA en producción dependen de UNA persona que tipea el schema en su cabeza. Construir el núcleo unificado no es un lujo de expansionista; es lo único que convierte el conocimiento que hoy vive solo en la cabeza de Iván en un activo que otra persona — o el próximo agente — podría operar sin él. La verdadera pregunta no es "Fénix o el holding", es: ¿cuánto vale hoy el holding de Iván si Iván no puede trabajar el lunes, y cuánto de ese riesgo es exactamente este schema que nadie más entiende?

### The Outsider

Empiezo por lo que nadie en esta sala dijo en voz alta: no hay un solo número en todo el contexto. ¿Cuántas familias tiene Fénix? ¿20? ¿200? ¿Cuántos pagos por mes se cargan a mano? ¿Cuántas veces en el último mes el checkbox CONTROL DATOS atrapó una discrepancia real? ¿Cuánto tiempo por semana pierde Iván tipeando al mismo niño en tres tablas? Sin esos números, todo lo demás es arquitectura de escritorio. Me huele a que el "dolor" es de 30 minutos por semana de re-tipeo molesto, y la "solución" en discusión es un rediseño del holding completo de 9 negocios. Eso no es resolver un problema, es escaparse hacia adelante hacia el problema más interesante.

Segundo: el problema declarado y el problema real no son el mismo. Iván dijo textual: "lo de familia Fénix y niños está complicado, y el pago se me está complicando." Eso es Fénix + pagos. Punto. No dijo "no puedo ver todo lo que una persona tiene conmigo a través de mis nueve negocios". Esa frase la pusieron ustedes, los técnicos, cuando vieron el party model y se enamoraron. El "todo es Iván Lafuente" suena profundo pero es una racionalización: nadie despierta perdiendo plata porque el papá que baila salsa figura dos veces. ¿Cuándo, en la vida real, Iván necesitó cruzar que un cliente de zapatos Alma Latina es el mismo que alquila la casona? Si la respuesta es "nunca todavía", entonces PERSONAS unificado es una solución a un problema que no existe aún.

Sobre las tres sub-preguntas, tomo posición sin rodeos. El modelo Personas+Ventas+Pagos: conceptualmente correcto, pero correcto y oportuno no son lo mismo — está sobredimensionado para hoy. Airtable vs Postgres: quedarse en Airtable, sin discusión, y ni siquiera por las razones técnicas que dieron (integración con agentes, costo de salida) sino por la única que importa: Iván está SOLO y ya tiene un rebuild de Dorita de 8-10 semanas encima. Migrar de herramienta es regalarle un segundo proyecto monstruo a un hombre que no tiene horas. El alcance: atacar SOLO Fénix + Pagos, acción chica, y diseñarlo de modo que NO contradiga el party model el día que de verdad lo necesite — pero sin construir el party model ahora.

Y acá va el cuestionamiento más básico que el resto va a odiar: ¿de verdad el problema es el MODELO de datos, o es que Iván tiene nueve negocios y un solo cerebro? Porque si rediseñás la base perfecta, mañana seguís siendo una persona sosteniendo Dorita rota, dos academias, clases de IA y retail. El esquema limpio no te devuelve horas; el esquema limpio es donde se van las horas. El council previo ya dictaminó unánime que el cuello de botella es el TIEMPO de Iván y que "pensar en plataforma antes de estabilizar" es su punto ciego clásico — y miren lo que estamos haciendo en esta misma sesión: pensando en la plataforma del holding entero mientras Dorita arde. Repitiendo el patrón exacto que ya nos dijeron que es el error.

Concreto, lo que haría: una sola tabla intermedia de PAGOS que cuelgue de una sola referencia limpia, colapsar las tres tablas de identidad de Fénix (LEADS, PRUEBA, FAMILIAS+NIÑOS) en una sola con un campo de estado (lead → prueba → activo), y matar el checkbox CONTROL DATOS porque deja de existir el doble tipeo. Eso es una semana, no diez. Resuelve TEXTUALMENTE lo que Iván dijo que le duele. Todo lo demás — retail, casona, Uber, el PERSONAS universal — se queda en una nota de "cuando un negocio específico te haga sangrar de verdad, lo integrás, y recién ahí". Hub & Spoke incremental de uno, no de nueve.

La pregunta incómoda que todos están esquivando: si Iván pasara estas próximas dos semanas SIN tocar la base de datos —ni Fénix ni el holding— y las usara para estabilizar a Dorita o cerrar más inscripciones del curso de IA, ¿ganaría o perdería más plata que rediseñando el modelo de Personas? Porque si la respuesta honesta es "ganaría más sin tocar la base", entonces esta conversación entera es el síntoma, no la cura.

### The Executor

El modelo Personas+Ventas+Pagos es correcto en el papel, pero la pregunta de si es correcto no importa el lunes a la mañana. Voy a ser brutal con el cronograma: rediseñar el holding completo — 9 negocios, 3 patrones distintos (suscripción, retail con stock, alquiler), migrar 39 tablas, reescribir las integraciones de DOS agentes que LEEN y ESCRIBEN por API — eso no es un proyecto, es un año-hombre. Iván está SOLO y ya tiene comprometidas 8-10 semanas en el rebuild de Dorita más dos academias funcionando más clases. La matemática no cierra. Si arranca el holding completo, dentro de tres meses no va a tener ni el holding migrado ni Dorita estable: va a tener dos obras a medio terminar y los agentes rotos en producción, que es lo único que hoy le da de comer.

Sobre la herramienta: la pregunta Airtable vs Postgres es una trampa de tiempo disfrazada de decisión técnica. Migrar a Postgres+NocoDB suena maduro, pero significa reescribir TODA la capa de API de los agentes, reconstruir las automatizaciones que hoy viven dentro de Airtable, y debuggear un stack nuevo — semanas que Iván no tiene. Los agentes ya hablan con Airtable hoy. Quedate en Airtable. No porque sea mejor, sino porque migrar de herramienta cuando el modelo de datos todavía está mal es pagar el costo de migración dos veces. Primero arreglás el modelo donde estás; recién cuando el modelo sea estable y choques contra el techo de records de verdad, migrás. Postgres es una decisión de 2027, no del lunes.

El alcance correcto es quirúrgico: SOLO Fénix, y dentro de Fénix, SOLO el problema de pagos y la identidad triplicada. Ese es el dolor que Iván verbalizó textualmente — "lo de familia Fénix y el pago se me está complicando". No dijo "quiero unificar mis 9 negocios". Eso lo inventamos nosotros. El retail (PC/Alma Latina/Mamba), la Casona, Uber, la facturación del Edificio Líder NO existen en Airtable todavía — no hay dolor, no hay deuda, no hay nada que arreglar ahí. Tocarlos ahora es trabajo especulativo sobre negocios que ni sangran. El party model puede esperar a tener un solo radio funcionando bien antes de prometer cinco.

La acción del lunes a la mañana, concreta y verificable en una mañana, no en un sprint: dentro de la base SALSA SOUL APP.2, crear UNA tabla nueva VENTAS y hacer que PAGOS cuelgue de UNA sola Venta en vez de los 4 padres polimórficos. Antes de eso, el paso cero —media hora— es exportar a CSV las tablas PAGOS, FAMILIAS FENIX, NIÑOS FENIX, LEADS FENIX y PRUEBA FENIX, para tener backup y ver el volumen real de filas que hay que mapear. Si son 200 pagos, esto es una semana. Si son 4000, es otra conversación. Nadie en el contexto dio ese número, y sin ese número toda estimación es humo.

El orden de las dos semanas siguientes, si y solo si los agentes siguen vivos después de cada paso: semana 1, colapsar la identidad triplicada de Fénix en una sola entrada (FAMILIAS+NIÑOS como verdad, LEADS y PRUEBA como estados de un registro, no como copias) y matar el checkbox CONTROL DATOS que delata el trabajo manual. Semana 2, hacer que toda plata de Fénix pase por VENTAS→PAGOS y sacar el primer estado de cuenta de una familia sin sumar a mano. Si eso funciona en Fénix, ES el prototipo del party model — pero validado con un negocio real, no dibujado para nueve. Y crítico: cada cambio de esquema en esa base toca los agentes que LEEN Y ESCRIBEN ahí. Cada paso termina con un test de que Dorita y Fénix Agent no se rompieron. No hay paso que no incluya esa verificación.

La pregunta incómoda que el resto del consejo está esquivando: ¿De dónde van a salir, literalmente, las horas para tocar el modelo de datos de Fénix esta semana, si Dorita ya se está comiendo las 8-10 semanas de Iván? O Dorita se pausa para meter este fix, o este fix espera a que Dorita esté estable — pero no existe el universo donde ambos avanzan en paralelo con una sola persona. ¿Cuál de los dos para?

---

## Peer Reviews

### Anonymization Mapping
- Response A = The Contrarian
- Response B = The First Principles Thinker
- Response C = The Expansionist
- Response D = The Outsider
- Response E = The Executor

### Review 1 (lente: ejecutabilidad real por una persona sola)
- **Más fuerte: E** — es la única que baja todo a una acción verificable del lunes a la mañana (crear VENTAS, colgar PAGOS de una sola Venta) e incluye el paso cero que el resto omite: exportar CSV para saber el VOLUMEN real antes de estimar, más un test de no-romper agentes en cada paso.
- **Punto ciego: C** — confunde "activo reutilizable" con "producto SaaS para PyMEs latinas" y termina justificando construir el núcleo entero por una tesis de plataforma que es exactamente el punto ciego que el council de Dorita declaró fatal para un hombre solo.
- **Todos ignoraron:** que la base SALSA SOUL APP.2 está VIVA y compartida con Salsa adultos: tocar PAGOS/identidad ahí para arreglar Fénix puede romper a Dorita (que lee/escribe esa misma base) aunque "solo toques Fénix" — nadie propuso aislar el cambio en una base/tabla nueva de staging antes de migrar la tabla compartida en producción.

### Review 2 (lente: riesgo de producción y pérdida de datos en una migración)
- **Más fuerte: E** — es la única que aterriza el riesgo de producción pedido: cada cambio de esquema toca los agentes que LEEN y ESCRIBEN, exige test post-paso de Dorita/Fénix, y empieza por backup CSV + medir volumen real de filas antes de migrar.
- **Punto ciego: C** — confunde "activo reutilizable" con "producto vendible a PyMEs latinas" y por esa fantasía invierte el orden crítico (núcleo antes que Dorita), ignorando que mover el piso de datos bajo un agente en rebuild es justo la doble cirugía que rompe producción.
- **Todos ignoraron:** nadie planteó el corte de consistencia durante la migración: con Dorita/Fénix Agent ESCRIBIENDO en vivo, hay que congelar escrituras (ventana de mantenimiento o feature flag/dual-write) mientras se mapea PAGOS→VENTAS, o un pago que entra a mitad de migración queda huérfano o duplicado — ninguna respuesta menciono parar las escrituras de los agentes durante el cambio.

### Review 3 (lente: negocio y costo de oportunidad)
- **Más fuerte: B** — identifica la causa raíz única (PAGOS polimórfico e identidad triplicada son el MISMO bug: falta la capa intermedia que homogeniza el "quién" y el "por qué"), y de ahí deriva con rigor que el núcleo Personas+Ventas+Pagos es el mínimo irreductible, no over-engineering, ejecutado solo sobre Fénix.
- **Punto ciego: C** — convertir el schema en "producto vendible a PyMEs latinas" es la fantasía expansionista más peligrosa de las cinco: le agrega un décimo negocio especulativo a un hombre que el propio Council declaró saturado, justo el costo de oportunidad que mata.
- **Todos ignoraron:** ninguna calculó el costo de cobranza real: si el dolor de Fénix es que pagos atrasados/familias morosas se escapan por el caos de datos, la plata perdida en cuotas no cobradas (no las "horas de re-tipeo") puede justificar o no el fix por sí sola, y nadie pidió el % de morosidad ni el ticket mensual familiar para ponerle número al ROI.

### Review 4 (lente: tiempo y recursos disponibles de Iván)
- **Más fuerte: B** — Nombra la causa raíz única (PAGOS polimórfico y la identidad triplicada son el MISMO bug por falta de la capa Venta/Persona), y de ahí deriva el alcance mínimo exacto: instalar el núcleo usando Fénix como único cliente, sin tocar nada más.
- **Punto ciego: B** — Subestima brutalmente el riesgo de los agentes en producción: dice "es agnóstico de la herramienta" y "trivial de portar", pero cambiar PAGOS de 4 padres a Venta rompe cada call site donde Dorita/Fénix Agent ESCRIBEN pagos, y eso no es trivial ni gratis.
- **Todos ignoraron:** Que el plan familiar de Fénix es UN pago que cubre a VARIOS niños del mismo hogar (1 Venta → N asistentes), el caso 1-a-muchos que justamente revienta el modelo viejo; ninguna respuesta verificó cuántas familias/pagos reales hay ni propuso correr el `endpoint`/exportar Airtable para dimensionar el esfuerzo antes de comprometerse a "una semana".

### Review 5 (lente: solidez técnica del modelo de datos y elección de herramienta)
- **Más fuerte: B** — clava la causa raíz técnica (identidad triplicada y PAGOS polimórfico son el MISMO agujero: falta la capa Persona+Venta) y de ahí deriva con rigor el alcance mínimo correcto (instalar el núcleo usando Fénix como único cliente, no fix aislado ni holding) y desmonta el techo de records de Airtable con un número real (50k > población de Paraguay).
- **Punto ciego: C** — confunde solidez técnica con oportunidad: romantiza el party model como "producto/plataforma vertical para PyMEs latinas" y exige el núcleo ANTES del Dorita reconstruido, justo el error de "plataforma antes de estabilizar" que el council previo marcó unánime y que un solo Iván saturado no puede ejecutar.
- **Todos ignoraron:** que VENTAS+PAGOS necesita conciliación contra las FACTURAS reales con IVA (B2B Edificio Líder, IVA recibido) — ninguna respuesta tocó que un libro mayor que no cuadra con lo facturado ante la DGII/SET paraguaya es un pasivo fiscal, no solo un CRM desprolijo; ni que Airtable no maneja decimales monetarios ni multi-moneda (Uber/Bolt) de forma contable confiable.

---

## Chairman Synthesis

### Donde el Consejo Coincide

- **El modelo Personas+Ventas+Pagos es técnicamente correcto.** 4 de 5 advisors lo validan explícitamente. La razón más dura (B, respaldada por 4 reviews): la identidad triplicada y el PAGOS polimórfico son EL MISMO bug — falta la capa intermedia que homogeniza el "quién" (Persona) y el "por qué" (Venta). No es over-engineering, es la forma natural del problema.
- **Quedarse en Airtable, NO migrar a Postgres ahora.** Unánime. El techo de records (50k > población relevante de Paraguay) es un problema falso a esta escala; migrar de herramienta es regalarle un segundo proyecto-monstruo a un hombre sin horas, y los agentes YA hablan con Airtable.
- **El alcance NO es el holding completo.** Unánime. Retail/Casona/Uber no existen en Airtable, no sangran, no hay deuda que arreglar. Diseñarlos ahora es trabajo especulativo sobre negocios que ni duelen.
- **El cuello de botella es el TIEMPO de Iván, no la arquitectura.** El party model vendible como "plataforma para PyMEs latinas" (tesis de C) fue marcado como punto ciego por las 5 reviews — es exactamente "escalar antes de estabilizar", el error que el council de Dorita ya declaró fatal.
- **Cada cambio de esquema toca los agentes en producción.** Dorita y Fénix Agent LEEN y ESCRIBEN esa base. Ningún paso es seguro sin verificar que los agentes no se rompieron.

### Donde el Consejo Choca

El choque central es el **punto de partida del alcance chico**, y es más sutil de lo que parece:

- **B y C (e implícitamente E):** instalar el NÚCLEO (Personas+Ventas+Pagos) usando Fénix como primer y único cliente. El fix de Fénix ES el núcleo, nacido bien desde el día uno.
- **El Contrarian y The Outsider:** ni siquiera eso. Colapsar las 3 tablas de identidad de Fénix y una sola tabla de Pagos limpia, SIN comprometerse al party model. "Persona unificada cross-negocio es belleza que no paga renta."

Por qué chocan: **falta el dato de volumen y de plata.** Nadie sabe (a) cuántas familias/pagos reales tiene Fénix — ¿200 o 4000 filas?, (b) cuánto tiempo/semana pierde Iván en el re-tipeo, (c) el % de morosidad y ticket familiar (review 3: si la plata perdida en cuotas no cobradas es alta, el ROI justifica el fix solo; si es "30 min de re-tipeo molesto" como sospecha The Outsider, no). **Sin esos números, la diferencia entre "núcleo" y "fix aislado" es indecidible.** La buena noticia: el primer paso correcto resuelve este choque, porque medir el volumen es barato y define el resto.

### Puntos Ciegos Detectados

Las reviews destaparon riesgos operativos que NINGÚN advisor vio, y son los más peligrosos:

1. **La base SALSA SOUL APP.2 está VIVA y compartida con Salsa adultos** (review 1). Tocar PAGOS o identidad "solo para Fénix" en esa base puede romper a Dorita, que lee/escribe las mismas tablas compartidas. Nadie propuso **aislar el cambio en staging** antes de tocar la tabla compartida en producción.
2. **Corte de consistencia durante la migración** (review 2). Con los agentes ESCRIBIENDO en vivo, un pago que entra a mitad de mapeo PAGOS→VENTAS queda huérfano o duplicado. Nadie mencionó **congelar escrituras / ventana de mantenimiento / dual-write**.
3. **El plan familiar Fénix es 1 Venta → N niños** (review 4). El caso 1-a-muchos es justo el que revienta el modelo viejo Y el que hay que modelar bien — y nadie verificó cuántas familias reales hay para dimensionarlo.
4. **Conciliación fiscal con FACTURAS + IVA** (review 5). VENTAS/PAGOS tiene que cuadrar con lo facturado ante la SET paraguaya (B2B Edificio Líder, IVA recibido). Un libro mayor que no cuadra es pasivo fiscal, no CRM desprolijo. Airtable además no maneja decimales monetarios ni multi-moneda (Uber/Bolt) de forma contable confiable — argumento extra para NO meter todo el dinero del holding ahí.
5. **El re-cableado de los call sites de los agentes** (Contrarian, review 4). "Trivial de portar" (B) es falso: cambiar PAGOS de 4 padres a Venta rompe cada lugar donde Dorita/Fénix Agent escriben un pago. Nadie los contó.
6. **La colisión de calendario** (Executor): no existe el universo donde el rebuild de Dorita (8-10 semanas) y este fix avanzan en paralelo con una sola persona. Uno de los dos para — y eso no se decidió.

### La Recomendación

**1. ¿Modelo Personas+Ventas+Pagos? SÍ — pero como destino del esquema, no como obra de esta semana.**
El modelo es correcto y es el mínimo irreductible. La concesión al futuro que se paga HOY es barata y única: **nombrar bien las tablas y diseñar el esquema en papel** pensando que algún día entren todos los negocios. Implementar, solo el radio que duele.

**2. ¿Airtable vs Postgres? Airtable, sin discusión.** Postgres es decisión de 2027, cuando el modelo esté probado y el retail realmente choque contra el techo. El modelo Personas+Ventas+Pagos es agnóstico de herramienta: si se modela bien en Airtable, el DDL se exporta a Postgres casi 1:1 el día que haga falta. NO migrar de herramienta con el modelo todavía mal — se paga la migración dos veces.

**3. ¿Alcance? Quirúrgico: SOLO Fénix, SOLO identidad+pagos. Pero con UNA disciplina de diseño:** la tabla VENTAS y la colapsada de Personas/Hogares se nombran y estructuran como el núcleo futuro, no como un parche desechable de Fénix. Así el fix que duele HOY es también el prototipo validado del party model — sin construir ni un radio más.

**QUÉ SÍ hacer (en este orden, módulo por módulo, nunca big-bang):**
- Medir primero (ver sección siguiente).
- Colapsar LEADS+PRUEBA+FAMILIAS+NIÑOS a un flujo con campo de estado (lead→prueba→activo), matar el checkbox CONTROL DATOS.
- Crear VENTAS; modelar explícitamente el caso **1 Venta familiar → N niños**; hacer que PAGOS cuelgue de UNA Venta.
- **Aislar el trabajo de esquema en una base/tabla de staging** antes de tocar las tablas compartidas con Salsa en producción.
- Cada paso termina con: test de que Dorita y Fénix Agent siguen escribiendo bien + verificar que VENTAS cuadra con FACTURAS.

**QUÉ NO hacer ahora:**
- NO tocar Salsa, Curso, retail, Casona, Uber, Edificio Líder.
- NO migrar a Postgres/NocoDB.
- NO construir el PERSONAS cross-negocio unificado (el papá que baila salsa = el papá que paga Fénix) — esa unión espera a que un negocio específico sangre por no tenerla.
- NO meter todo el dinero del holding en una sola base contable de Airtable (límite fiscal/monetario).
- NO arrancar este fix en paralelo al rebuild de Dorita sin decidir explícitamente cuál de los dos para. **Recomendación: el fix de Fénix es chico (1-2 semanas si el volumen es bajo) y ataca un dolor verbalizado; cabe ANTES de retomar Dorita o en una pausa corta — pero esa decisión la toma Iván con el dato de volumen en la mano.**

### Lo Primero que Hay que Hacer

**Exportar a CSV y medir — antes de tocar un solo campo.** Una sola acción, una mañana, cero riesgo de producción:

Exportar (o listar vía API/Airtable MCP) las tablas **PAGOS, FAMILIAS FENIX, NIÑOS FENIX, LEADS FENIX y PRUEBA FENIX** y responder 4 números concretos:
1. ¿Cuántas filas hay en cada una? (define si esto es 1 semana o 1 mes)
2. ¿Cuántas familias Fénix activas reales? ¿Cuál es el promedio niños/familia? (dimensiona el 1→N)
3. De los PAGOS, ¿cuántos cuelgan de cada uno de los 4 padres? (mide el tamaño real del problema polimórfico)
4. ¿Cuánta plata de Fénix NO pasa por PAGOS (VESTUARIOS, ENTRADAS FESTIVAL) y cuánta morosidad hay? (pone número al ROI — review 3)

Este es el STATE_AUDIT equivalente al council de Dorita: **no se compromete ni una hora de migración hasta tener estos 4 números.** Resuelven el único choque real del consejo (núcleo vs fix aislado) y dicen si Fénix+Pagos siquiera merece tiempo de Iván este trimestre o si lo honesto es escribir el esquema del núcleo en papel, guardarlo, y no tocar Airtable hasta que Dorita esté de pie.

---

*Council transcript generado el 02/06/2026 — LLM Council (5 advisors + peer review anonimizado + chairman) vía workflow multi-agente.*
