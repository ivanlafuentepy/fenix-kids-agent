# AUDITORÍA COMPLETA — 2026-07-12

> Auditoría de todo el proyecto con 6 agentes en paralelo (núcleo, datos/Airtable,
> dinero, IA/conversación, background/integraciones, Mundo Fenix/endpoints) +
> verificación local (tests, import) + logs de producción de Railway.
> Todos los hallazgos tienen archivo:línea verificados por lectura directa.
> Hecha con la mira puesta en la migración futura: **eliminar FAMILIAS FENIX**
> (niño como eje de la cuota, tutores linkeados directo al niño).
>
> Estado de prod al auditar: deploy actual SUCCESS (~7h corriendo), sin ningún
> Traceback en logs. El sistema FUNCIONA — esto es deuda y riesgo, no incendio.

---

## 1. CRÍTICOS (P0)

### C1. PII de menores en endpoints públicos sin auth
- `main.py:773-857` `/api/alumnos` — **sin auth, CORS `*`**: nombre, apellido, foto,
  fecha de nacimiento, `cell_padre`, `cell_madre`, `es_prueba` de TODOS los niños.
- `main.py:684-762` `/api/reservas` — sin auth: agenda del sábado con niños por turno,
  foto, nombre del padre y su celular. Con `?fecha=` se barre cualquier sábado
  (dónde va a estar cada niño y a qué hora).
- `main.py:860-913` `/api/alumno/{slug}` — PII del menor sin teléfono.
- `main.py:599-666` `/checkin/prueba/{telefono}` — **enumerable por teléfono**: probando
  números paraguayos se listan nombres de hijos; el `/toggle` además ESCRIBE asistencia sin auth.
- `main.py:503` `/checkin/{record_id}` — **GET que muta** (marca PRESENTE): un prefetch
  de navegador/bot marca asistencia.
- `juego_endpoints.py` `/juego/dia` — público con nombre+APELLIDO de menores (la TV solo necesita nombre/apodo).
- Nacieron para la web pública (B5) y el QR, pero el patrón se extendió a listados masivos.
  **Fix**: definir frontera — público = solo IDs aleatorios no enumerables + datos mínimos
  (nombre de pila/apodo); listados → token (`?k=` firmado o X-JUEGO-KEY) y actualizar los frontends que los consumen.

### C2. Un error de DB en la dedup descarta el mensaje del lead para siempre
- `memory.py:509-516` + `main.py:2104-2105`: cualquier excepción en
  `registrar_mensaje_procesado` (timeout de Postgres, no solo duplicado) devuelve
  `False` → el webhook responde 200 a Meta y el mensaje se pierde **sin log ni alerta**.
  Distinguir `IntegrityError` (duplicado real) de otros errores.

### C3. providers/meta.py: ciego a errores de red, sin retry, sin split
- Todos los métodos de envío (`enviar_mensaje:494`, `enviar_botones:206`,
  `enviar_plantilla:470`, lista/flow/imagen/documento/video) hacen el POST **sin try/except**:
  un `ConnectError`/`ReadTimeout` propaga y mata al caller.
- `_registrar_fallo` solo corre con `status != 200` → **el monitor nunca ve "Meta inalcanzable"**
  (solo ve 401).
- Sin manejo de 429/470, sin reintentos, sin split de mensajes >4096 chars
  (grep `4096|split|chunk` en agent/: 0 matches) — una respuesta larga = 400 y el lead sin respuesta.

### C4. Rate limiting saliente: NO EXISTE
- El único limiter (`concurrencia.py:30-46`, 10 msg/60s) es solo para ENTRANTES (`main.py:2091`).
- Salientes: sleeps ad-hoc dispersos. La promo masiva (`main.py:965`) manda **ráfagas de 50
  plantillas sin pausa** (2s cada 50). `contenido_social.py:116,218` sin ningún sleep (hoy OFF).
- Además la promo masiva (`main.py:1023`) es un `create_task` pelado: una excepción a mitad
  de lista mata el masivo Y deja `_promo_masiva_estado["activo"]=True` trabado hasta reiniciar.
- **Fix**: cola/limiter centralizado de salida en el provider (única puerta a Meta).

### C5. `max_records=100` truncando YA (NIÑOS ~105)
- `_get_records` SÍ pagina (corregido); el bug vigente es el TOPE en los call sites:
  - `main.py:783,787,869` (`/api/alumnos`, `/api/alumno`) — el propio TODO lo admite; alumnos 101+ invisibles / 404 **hoy**.
  - `main.py:721,729` — fichas del sábado sin foto/cell para los que caen fuera.
  - `airtable_client.py:1699` `obtener_familias_inscriptas` — broadcasts pierden familias.
  - `inscripcion.py:149` — full-scan de PRUEBA topeado a 100 y sin sort → "cargar familia" va a dejar de encontrar leads recientes (bloqueante C5 del corte PRUEBA).
  - `airtable_client.py:1629` contenido del menú alumno — cuando pase 100, lo nuevo queda afuera.

---

## 2. ALTOS (P1)

### Dinero
- **A1** `inscripcion.py:491-516` — PAGOS de matrícula+plan con `_post` directo, **sin guard
  anti-duplicado** ni link al LEAD (el patrón exacto del incidente Esteban). Reintento de
  "cargar familia" = pagos duplicados.
- **A2** `airtable_client.py:1339` — el guard anti-dup solo cubre concepto `PRUEBA*` y **solo mismo día**.
- **A3** `pagos.py:143-151` — tras el primer "pago confirmado" en el historial, un segundo
  comprobante (cuota, hermano) **no dispara el flujo de pagos** — depende de que el admin lo vea.
- **A4** `main.py:2458` — ayuda del admin con montos VIEJOS (`90mil|120mil`) vs los reales
  (`100mil|150mil|200mil` en `flujo_pagos.py:304`, que además sigue aceptando 90/120/180 "por compatibilidad").
  Un admin que sigue la ayuda cobra de menos.
- **A5** `pagos_tarjeta.py:34` — la firma HMAC del link cubre solo el monto; `?cliente=`
  (teléfono) viaja sin firmar → se puede atribuir un pago a otra familia editando la URL.
- **A6** `main.py:1567` + `loops.py:306` — dedup `pago-tarjeta:{spid}` vive en
  `mensajes_procesados` que se **purga a las 24h**: un replay de la pasarela pasadas 24h = PAGO duplicado.
  Idempotencia de dinero necesita tabla/retención propia.
- **A7** `flujo_pagos.py:284` — lead que pagó y NO completa el formulario Meta queda **colgado
  para siempre**: sin recordatorio, sin timeout, y el prompt FASE 4 le prohíbe al brain agendar
  (`modo_agenda` nunca se activa). El fallback solo cubre fallo de ENVÍO del form.

### Conversación / reservas
- **A8** `tools/agenda.py:158` + `main.py:2225` — reservas buscadas por **FIND de nombre de
  familia** (substring, sensible a acentos): "FAMILIA GONZALEZ" matchea "GONZALEZ RAMIREZ".
  En `_reagendar` (184-189) las reservas ajenas **se borran**; en el contexto de Aurora se
  muestran niños de otra familia. Y `main.py:2219-2226`: si la familia no tiene nombre, la
  fórmula queda `FIND('FAMILIA',...)` → matchea TODAS las reservas.
- **A9** `tools/agenda.py:181-191` — reagendar borra-primero-crea-después sin rollback:
  si `_agendar` falla, la familia queda SIN reserva.
- **A10** `main.py:3781-3800` — keywords que FUERZAN `tool_choice` con falsos positivos
  (`"sab"` ⊂ "sabemos/saber", `"cambiar"` genérico) → Haiku obligado a llamar `gestionar_reserva`
  en mensajes que no son de reservas. Es un parche regex post-regla-dura.
- **A11** `brain.py:95-124` — **el prompt cache está muerto**: la hora `%H:%M` va al inicio del
  bloque cacheado → cambia cada minuto → se paga +25% de escritura de cache en casi todos los
  mensajes y el ahorro 10x no ocurre. Partir el system en bloque estático (cacheado) + bloque dinámico.
- **A12** `brain.py:195-216` — el retry re-aplica `tool_choice` forzado sobre historial ya mutado
  → tool re-ejecutada (reagendar/confirmar duplican efectos).

### Telegram / espejo
- **A13** `telegram_bridge.py:357,316` — `enviar_a_topic` sin override defaultea al grupo LEADS
  aunque el topic viva en FLIAS → 400 → el recovery **recrea el topic en LEADS y pisa la DB**
  (el bug del 11/07 sigue vivo). Call sites rotos: `hq_endpoints.py:54-57`,
  `juego_endpoints.py:551-556` (familias seguro), `hooks.py:245-247`, `night_mode.py:101-103`,
  `main.py:2893-2895` (modo alumno) y otros.
- **A14** `main.py:3057` vs `main.py:3501` — el grupo se recalcula post-router con
  `group_id_para_agente` y desalinea con el topic ya creado (inscripto nuevo: topic en LEADS,
  espejo a FLIAS).

### Datos / migraciones
- **A15** `airtable_client.py:1699` — `obtener_familias_inscriptas` filtra por
  `CELL PADRE/MADRE` legacy: una familia "pura EJE B" (cell solo en TUTORES) es
  **invisible para broadcasts hoy**.
- **A16** Inyección de comillas en `filterByFormula`: `airtable_client.py:509/515` (nombres),
  `fotos.py:265` (apóstrofes), `agenda.py:158`, y `juego_endpoints.py:117` (`CODIGO FENIX`
  desde request público — input de usuario directo en la fórmula).
- **A17** `main.py:4433` — año `2026-` **hardcodeado** en el cierre de formulario: bomba de
  tiempo para enero 2027 (contrasta con `main.py:4706` que sí usa `today().year`).
- **A18** `juego_endpoints.py:272-312` — ledger de monedas read-modify-write sobre Airtable
  sin atomicidad: doble-tap/retry concurrente puede duplicar oro o pisar saldo (el circuito
  NFC con Postgres sí es transaccional).
- **A19** `meta_capi.py:40-53` — sin `event_id` (dedup de Meta) y Purchase disparado desde
  DOS lugares (`flujo_pagos.py:199` y `main.py:4533`) → conversiones infladas en Ads.
- **A20** Monitor: `_conf_sabado_task` no registrado; `_detectar_sin_respuesta` solo mira
  la última hora (lead viejo desaparece del radar); errores en memoria se pierden con deploy;
  si el loop de salud muere nadie lo vigila; canal de alerta único = Telegram (si Telegram cae, silencio).
- **A21** Tests muertos: `tests/test_local.py` importa `_detectar_activacion_nixie` que ya no
  existe → pytest ni recolecta. El paso 2 del Definition of Done es imposible hoy.

---

## 3. MEDIOS (selección — el detalle vive en los reportes)

- `main.py:2723` — "resumen asistencia" capturado por el comando de pasar lista (orden de ifs).
- `main.py:2828-2871` — bloque "resumen seguimiento" duplicado; el segundo inalcanzable.
- `main.py:2248` — `NameError` `_hoy_cls` tragado por except: las fechas de reservas de Aurora
  salen siempre en ISO crudo (el formateo lindo es código muerto).
- `ab_test.py:56-68,155-164` — `actualizar_agent_actual`/`guardar_familia_id` no-op silencioso
  sin fila previa (`/restaurar-aurora` puede reportar ok sin hacer nada).
- Estado admin en memoria del proceso (se pierde con cada deploy): `_admin_modo_padre`,
  `_fotos_sesion`, `_asistencia_pendiente`, `_inscripcion_pendiente` (inscripción a medias se
  pierde silenciosa), anti-spam escalación (`hooks.py:189`).
- `night_mode.py:93` — respuesta matinal con `agent_actual="ivan"` hardcodeado (familia en
  aurora amanece atendida por el prompt de ventas).
- `pagos.py:98-99` — monto ADIVINADO (100k) se registra en Airtable; mitigado por aviso admin.
- `escalacion.py:41-47` — heurística de nombre agarra "Hola" → "Que tal Hola, soy el profe Ivan".
- `lead_menu.py:318` — el gate del menú bloquea a los detectores: lead que pregunta precio en
  estado menú recibe "Tocá una opción 👇" en loop.
- Detectores con falsos positivos conocidos: "valores", "hermano a mirar", "cuánto es la clase"
  (doble respuesta precio+duración), "qué necesito para inscribirlo".
- `brain.py:228-233` — stop_reason `max_tokens`/refusal con tools → 3 llamadas idénticas y "Ups, algo falló".
- `tools/llamada.py:51` — "llamame a las 8" = 8:00 AM.
- `loops.py:288-292` — recordatorio de clase descartado tras 3 fallos se marca ENVIADO sin avisar.
- `resumenes.py` fotos grupales: `_buscar_multiples_caras` no recorta (identifica ~1 cara por foto).
- `mundo-fenix/mapa.html:191` — avatares indexados por nombre de pila (tocayos se pisan; display-only).
- `main.py:4160` — guard de confirmación mira solo 10 mensajes (mismo patrón que ya se corrigió con ventana 50).
- Facturas: loop poll Airtable cada 90s 24/7 (~960 req/día); guard anti-doble-PDF en memoria.
- Transcripción fallida → el LLM responde al literal "[audio]" sin avisar al padre.
- `_reagendar`/N+1: `obtener_ninos_por_horario` abre un AsyncClient por reserva (rate limit compartido con Dorita, sábado AM).
- `eliminar_todo_de_telefono` no borra TUTORES ni ASISTENCIA → tutores huérfanos que re-matchean.
- `formulario_reserva._guardar_tutor` escribe SOLO en TUTORES (asimetría inversa: facturas lee CI legacy primero).
- Logging de Python a stderr → Railway marca todo INFO como "error": imposible filtrar errores reales.
- Seguridad menor: claves admin comparadas con `!=` (no `compare_digest`); firma Meta log-only
  salvo `META_FIRMA_RECHAZAR=1`; webhook Telegram sin auth si falta el secret.
- `USE_TOOL_USE` default `"false"` — confirmar que está `true` en Railway (si falta, los prompts
  prometen tools que no existen).

## 4. Código muerto (borrar cuando toque, no urgente)

- `airtable_client.py`: `marcar_control_datos`, `actualizar_diagnostico_lead`,
  `obtener_horario_por_id`, `buscar_familia_por_nombre`, `crear_familia_completa`,
  `marcar_formulario_lead`, `eliminar_lead`, `_deducir_genero` (duplicado divergente de `deducir_genero`).
- `tools/registro.py` completo (no está en `_TOOLS`; su wipe de CELL es latente) y
  `consultar_agendados` (disponibilidad.py:85).
- `ab_test.py`: funciones Calendar (Google Calendar eliminado) + columna `calendar_event_id`.
- `main.py`: `_telegram_chats_vistos`, FASE 1 hardcodeada inalcanzable, flujo PROMO MADRE entero
  tras flag False (con bugs latentes adentro), bloque seguimiento duplicado.
- `loops.py`: oneshots retirados (con el anti-patrón de POST directo a Graph API adentro).
- `flujo_pagos.py:356-359`: rama de conceptos 750k/350k inalcanzable.
- Descripciones stale en tools: "los 3 turnos" (hay 2), "usar confirmar_reserva" (no existe).
- Paginación manual reimplementada 5 veces (loops/resumenes/main) que `_get_records` ya hace.

## 5. Estado de las migraciones

### PRUEBA FENIX (en curso, corte 18/07)
La premisa "ya no se lee" NO es exacta: quedan ~12 lecturas vivas (mayoría documentadas como
cortes 2.C/2.D/C5) y 6 call sites de escritura (`crear_prueba_fenix` en flujo_pagos/main/promo).
Bloqueantes reales del corte: `inscripcion.py:149` (cargar familia busca EN PRUEBA con tope 100),
guard del formulario (`main.py:4321-4324`, se voltea en C2), checkins/QR legacy (2.D).
Inventario completo en el reporte de datos.

### FAMILIAS FENIX (aprobada, en pausa hasta cerrar PRUEBA)
Inventario consolidado: **~45 puntos de contacto**. Los 5 huesos duros:
1. **Router leads/familia** (`main.py:3483` + `buscar_familia_por_telefono` + `familia_es_activa`)
   — LA decisión del sistema; el reemplazo (tutor con ≥1 niño activo) debe ser equivalente exacto.
2. **`_build_contexto_aurora`** (`main.py:2118-2303`) — el consumidor más acoplado; rediseñar
   como contexto(tutor, niños). De paso mata A8 (reservas por nombre).
3. **Facturas / robot facturador externo** (`facturas.py:75-107`, lookup `FLIA FENIX RUC`)
   — coordinar con el sistema externo; datos fiscales pasan al tutor que paga.
4. **Guard anti-dup de PAGOS** (`airtable_client.py:1325`) — necesita link inverso PAGOS en
   NIÑOS antes del corte, si no vuelve el bug de duplicados.
5. **`CODIGO FENIX` del juego** (`juego_endpoints.py:99-118`) — la auth de toda la app del
   juego está anclada a FAMILIAS; reanclar (código por niño encaja con la regla de tocayos).
**Bugs que MUEREN solos con esta migración** (no parchear dos veces): A8 (FIND por nombre),
A15 (broadcasts ciegos a EJE B), asimetrías de dual-write, wipe de CELL "temporal",
fórmula 'FAMILIA' a secas, fallbacks legacy de tutores.

## 6. PLAN DE ATAQUE (aprobado por Ivan 2026-07-12 — "vamos con todo")

### ✅ Estado de ejecución (noche del 2026-07-12, 10 pushes, todos SUCCESS y verificados)

**F0 completo:**
- `322f5e8` C1: /api/alumnos, /api/reservas, /api/alumno con ADMIN key (verificado: 401/200 en prod)
- `00a44e4` C2: dedup solo IntegrityError = duplicado
- `dc9ec67` C5: max_records 100→1000 en 8 call sites (verificado: 105 alumnos, antes 100)
- `6a1979c` A4: montos /agenda corregidos, 90/120/180 retirados
- `0cf6db5` C3: meta.py con manejo de red + split >4096 (verificado: test-envio real OK)
- `0c56586` C1: /checkin/prueba con token firmado + /checkin/{id} confirma por POST
  (verificado en prod: 404 sin token, 200 con token, GET no muta PRESENTE)
- `968c336` C1: /juego/dia solo inicial de apellido

**F2 parcial:**
- `2cf7836` A1: guard anti-duplicado en PAGOS de inscripción
- `a2b1f1a` A6: dedup pago-tarjeta exenta de la purga de 24h
- `406e4d0` A3: aviso al admin ante posible segundo comprobante

**F2 segunda tanda (misma noche, aprobada "vamos con todo"):**
- `a3adffa` A7: rescate del lead pagado que no completa el formulario — +2h re-envía
  el Flow, +24h cae a agenda por texto. Recordatorios en Postgres (tipo `form_rescate`),
  clamp nocturno 21-08→09:00 PY, se cancelan al completar, guard al disparar.
- `eb58b43` + pagos-bancard `4f5017f` A5: la firma del link de tarjeta cubre el
  teléfono (`fenix:{monto}:{cliente}`). La pasarela rechaza firma legacy de fenix con
  cliente presente; salsa/curso toleran legacy hasta migrar sus bots (TODO anotado
  en pagos-bancard). Verificado contra prod: las 5 combinaciones (nueva válida,
  cliente cambiado rechazado, legacy+cliente rechazado, legacy sin cliente OK,
  monto manipulado rechazado).

**F2 pendiente:**
- A2 (ampliar guard de registrar_pago_fenix más allá de "PRUEBA hoy"): pensarlo
  junto con la migración cuota-al-niño para no rehacerlo dos veces.
- Migrar bots de salsa/curso a firma-con-cliente y volver estricta la pasarela
  para todos los negocios.

### Plan original

Orden: primero lo que sangra HOY (seguridad + mensajes perdidos), después cerrar PRUEBA
(ya en curso, no mezclar), después dinero, después FAMILIAS (que mata una clase entera de
bugs), y la calidad continua al final. **Deploy incremental: un cambio por push, siempre.**

### F0 — Seguridad y sangrado (esta semana, ~6 pushes chicos)
1. Token para `/api/alumnos`, `/api/reservas`, `/api/alumno` + actualizar frontends que los consumen; sacar apellido de `/juego/dia`.
2. `/checkin/prueba/{telefono}`: token en QR o migrar a record_id; toggle con auth; `/checkin/{record_id}` deja de mutar en GET (confirmación POST).
3. Fix dedup C2 (distinguir IntegrityError).
4. try/except + `_registrar_fallo` de red en providers/meta.py (+ split >4096).
5. Subir `max_records` en los 5 call sites truncados (fix trivial, la paginación ya existe).
6. Fix ayuda `/agenda` montos viejos + quitar 90/120/180 de `_MONTOS_AGENDA`.

### F1 — Cierre migración PRUEBA (según plan existente, corte 18/07)
C2 (guard formulario) + C5 (cargar familia sin PRUEBA — aprovechar y arreglar el tope 100)
+ 2.D (checkins/QR legacy) + retirar `crear_prueba_fenix` y su código muerto asociado.

### F2 — Robustez del dinero (~5 pushes)
Guard anti-dup en inscripción (A1) + ampliar guard (A2) + dedup pago-tarjeta con retención
propia (A6) + firmar teléfono en link de tarjeta (A5) + recordatorio/timeout del formulario
post-pago (A7) + detectar segundo comprobante (A3).

### F3 — Migración FAMILIAS (proyecto en sí, estilo M1-M4, plan detallado aparte)
1. Links directos NIÑOS↔TUTORES + backfill.
2. Cuota/estado/vencimientos al NIÑO en PAGOS (+ link inverso para el guard) + decidir pago multi-hermano.
3. Estado de conversación `familia_id`→`tutor_id` (dual-write en ConversacionAB primero).
4. Router + contexto Aurora + juego + facturas (con el robot externo coordinado).
5. FAMILIAS congelada solo-lectura → archivo.

### F4 — Calidad continua (mechar entre fases)
Cache split del system prompt (A11 — plata todos los días), revivir tests (A21),
Telegram topic única fuente (A13/A14), logging a stdout con niveles, rate limiter saliente
central (C4), monitor gaps (A20), CAPI event_id (A19), código muerto, año 2027 (A17),
tool_choice keywords (A10), reagendar transaccional (A9).

---
*Reportes completos de los 6 agentes: en los archivos de la sesión. Este doc es el consolidado accionable.*
