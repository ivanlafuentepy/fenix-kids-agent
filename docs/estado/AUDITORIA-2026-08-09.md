# AUDITORÍA COMPLETA — 2026-08-09

> **ESTADO DE EJECUCIÓN (misma sesión, 09/08 noche): los 3 críticos, los 14 altos
> y la migración TUTORES→ALUMNOS completa están ARREGLADOS y en prod** (24 commits
> en fenix + 1 en facturador-set, cada uno deployado SUCCESS y verificado).
> También: M1, M2, M8, M10, M11 y A6 (con limpieza de los 4 leads atrapados).
> La tabla quedó renombrada "TUTORES FENIX LEGACY" (canario ~30 días).
> Pendientes: pegar la automation en la UI (docs/operaciones/), prueba
> end-to-end con WhatsApp real, y los medios M4/M5/M6/M7/M9/M13-M20 + bajos.

> Auditoría post-migraciones: tutores→ALUMNOS, ESTADO2, pack de clases (saldo calculado),
> identidad por número, flujo Aurora y sistema Airtable. 5 agentes en paralelo + verificación
> cruzada contra el schema REAL de la base (Metadata API, solo lectura) y registros reales.
> Los hallazgos críticos fueron verificados a mano contra el código (línea por línea).
>
> Baseline sano: `import agent.main` OK, 30/30 tests pasan.

---

## 🔴 CRÍTICOS — plata que no se registra

### CR1. El link `PAGOS.PAGA` apunta a TUTORES FENIX (legacy) pero el código le manda ids de ALUMNOS → el POST del PAGO entero muere con 422

- `agent/airtable_client.py:1318` (`registrar_pago_fenix`): `campos_pago["PAGA"] = [tutor_paga_id]` — `tutor_paga_id` sale de `obtener_grupo_familiar` = filas de **ALUMNOS**.
- `agent/inscripcion.py:566` (`_ejecutar_inscripcion`): `_campos_nino_eje["PAGA"] = [tutor_id]` — mismo bug, afecta los DOS POST (matrícula :591 y plan :609).
- **Schema verificado**: `PAGOS.PAGA` (fldK5jhrlKdRIQnc1) → linkedTable `tblYlRqpGqtQGyUJA` = TUTORES FENIX. El campo correcto es **`PAGA (ALUMNOS)`** (fld2g0N0o0q13pqna → ALUMNOS). `formulario_reserva.py:176-177` YA usa el correcto — el fix quedó a medias.
- **Consecuencias en cascada**: el pago de la prueba no queda en Airtable (el lead recibe "Pago confirmado! 🎉" igual); en la inscripción no se crean ni matrícula ni cuota/pack, y al morir el pago del plan **tampoco corre `marcar_inicio_pack`** → niño del pack con 0 clases compradas.
- **Evidencia en datos reales**: último PAGO creado por código (con `LEAD FENIX`) = 25/07. Los pagos de agosto (Galeano 08/08, Alfaro PAQUETE5 09/08) tienen `PAGA (ALUMNOS)` + nro de comprobante + `FECHA PAGO` — campos que este código no escribe → cargados a mano. El bug es intermitente: si el tutor no se resuelve (`tutor_paga_id=None`), el pago nace huérfano y sobrevive — por eso no se notó.
- **Matiz**: no se pudo confirmar el 422 en logs (Railway purgó los deployments viejos). Queda pendiente cruzar comprobantes de Telegram vs filas de PAGOS desde el 25/07 para saber si se perdió alguno de verdad.
- **Fix**: `"PAGA"` → `"PAGA (ALUMNOS)"` en los 2 lugares (deploys separados, `/pre-cambio`). Ojo con `resumenes.py:934` que filtra por `{PAGA}` legacy (ver M-12).

### CR2. `LEADS.TUTOR FENIX` también linkea a TUTORES legacy → el PATCH que marca INSCRIPTO muere entero

- `agent/inscripcion.py:643-646`: patchea `{"CONVERSION": "INSCRIPTO", "TUTOR FENIX": [tutor_id]}` con `tutor_id` de ALUMNOS → 422 → **CONVERSION nunca queda en INSCRIPTO**. El campo correcto es `TUTOR (ALUMNOS)` (ya usado bien en `vincular_tutor_a_lead`, `airtable_client.py:402`).

### CR3. El texto de Aurora crea/cancela reservas reales sin confirmación del padre

Tres piezas que se combinan:
1. **Regex sobre la respuesta de Aurora** (`main.py:3780-3792` → `4364-4389` + `detectores_conv.py:263-311`): si Aurora no usó la tool ese turno, patrones como `"agendam.*sábado ... a las ..."` matchean **preguntas y ofertas** ("¿Querés que agendemos para el sábado 15 a las 11:00h?") → se crea la RESERVA real para TODOS los hijos, sin guard (el guard de pago existe solo para ivan). Lo mismo con "te cambio a las 15:30" y con "cancelé la reserva…" (`main.py:3748-3774` cancela de verdad lo que Aurora diga).
2. **`tool_choice` forzado por substring** (`main.py:3441-3460`): `"sab"` matchea "no **sab**emos si vamos", `"cambiar"` matchea "cambiar mi número", `^(si|va|...)` matchea "vamos a ver" → Haiku queda OBLIGADO a llamar `gestionar_reserva` y puede elegir `cancelar`/`agendar` con datos del contexto. (Era el pendiente A10 de la auditoría del 12/07 — sigue vivo y ahora con tools de Aurora.)
3. **`reagendar` borra TODAS las reservas futuras** (`tools/agenda.py:154-181`): familia con reservas el 15 y el 22 pide mover la del 15 → la del 22 desaparece en silencio (el Telegram solo reporta la nueva).

Nota de diseño: esto NO se arregla con más regex (regla dura #10) — el puente texto→acción hay que apagarlo o ponerle confirmación explícita, y la exclusión de un hijo necesita un parámetro en la tool (hoy `gestionar_reserva` no puede reservar/cancelar para UN hermano: siempre todos — contradice el prompt "solo excluir si el padre lo dice").

---

## 🟠 ALTOS

### A1. Pack pagado por comprobante en el chat = PAGO con CONCEPTO=PRUEBA → 0 clases acreditadas
`agent/pagos.py:232-247` + `agent/flujo_pagos.py:69-81,128-151,268`. `detectar_tipo_pago` no conoce el pack: default `tipo="prueba"` → un comprobante de 350k queda como PRUEBA (la fórmula CLASES COMPRADAS solo suma PAQUETE5) y sale el formulario de prueba. Si matchea keyword de inscripción, no se registra PAGO y el lead queda colgado sin post-pago. Bonus: el keyword `"de una"` (`pagos.py:234`) es muletilla de asentimiento y el propio afiche la induce.

### A2. Confirmación del sábado leería un campo que ya no existe (`AL DÍA?`) → lista siempre vacía
`agent/airtable_client.py:886-890` (`obtener_ninos_al_dia`). Con el cambio del 08/08 la fórmula pasó a llamarse `ESTADO` en NIÑOS FENIX (el comentario de `airtable_client.py:46-49` documenta el cambio pero la función no se actualizó). Feature hoy APAGADA (`CONFIRMACION_SABADO_ACTIVA=false`) → bomba silenciosa: el día que se prenda, no sale ni una plantilla y ningún log lo delata.

### A3. `actualizar_diagnostico_lead` está muerta: `LEADS.DIAGNOSTICO` ya no es link, es texto
`agent/airtable_client.py:309-329`. El campo es `singleLineText` (la tabla DIAGNOSTICO ya no existe en la base). Lead con texto previo → `str + list` = TypeError tragado; lead sin valor → PATCH de rec-ids a un campo texto = 422 silencioso. El rompehielos dejó de registrar diagnósticos desde el cambio de schema.

### A4. `marcar_inicio_pack` se saltea en el reintento de "cargar familia"
`agent/inscripcion.py:604-637`. Si la corrida 1 crea el PAGO PAQUETE5 y muere antes de marcar, el reintento entra por la rama "ya registrado hoy — no dupliqué" que NO marca → `PACK DESDE` vacío para siempre → la asistencia de la prueba previa come una clase del pack. El retorno de `marcar_inicio_pack` (False si falla) no lo mira nadie.

### A5. Inscribir a una familia NO cambia el modo de la conversación → el inscripto sigue hablando con el agente de VENTAS
`agent/main.py:3135-3146` (router solo `es_nuevo`) + grep de `actualizar_agent_actual`: ningún flujo de inscripción lo llama. Consecuencias: (a) el padre pregunta por su clase y recibe pitch de precios; (b) el botón "Sí, mandame fotos" de la plantilla `checkin_fenix` solo se intercepta en modo aurora (`main.py:3181-3221`) → cae al brain de leads, `fotos_pedidas` no se setea y **nunca recibe las fotos**. Hoy el paso a aurora es 100% manual (`/registro`, `/restaurar-aurora`, "modo alumno").

### A6. Flujo `/registro` roto: el tutor nunca se crea y el número queda atrapado en aurora sin contexto
`agent/main.py:4605-4686` + `3688-3701`. El registro depende del marker `"REGISTRO PADRE:"` en la respuesta de Aurora, pero el `aurora_prompt` actual ya no lo menciona (se quitó en el refactor Wave 2) y `registrar_familia`/`registrar_hijo` no están en TOOLS_AURORA → la madre responde su nombre y no pasa nada; cada mensaje siguiente cae en el camino de alucinación (A7). Probable fábrica de los "4 leads viejos en aurora".

### A7. `grupo=None` apaga TODAS las protecciones de familia y Aurora alucina (el #301, ampliado)
`agent/main.py:3197-3250` + `airtable_client.py:830-867`. Sin rama `else`: con grupo None no hay contexto, ni menú, ni interceptores de confirmación — y el prompt no tiene instrucción para ese caso → Haiku responde desde el historial (la reserva inventada a Ilse). Agravante: `obtener_grupo_familiar` devuelve None **también cuando Airtable está caído** (excepts tragados) — una madre real en un hiccup de Airtable recibe respuestas de memoria. Pariente: si falla solo la lectura de reservas (`main.py:1905-1953`), `_reservas_texto=""` → va sin bloque DATOS y el prompt le hace ofrecer agendar a quien SÍ tiene reserva.

### A8. Guard "RESERVA DOBLE" muerto: `FIND(rec_id, ARRAYJOIN({NINO}))` nunca matchea
`agent/main.py:4375`. El patrón prohibido (ARRAYJOIN devuelve NOMBRES) — la alerta al admin no se disparó nunca. El dedup de `crear_reserva` solo cubre mismo niño + mismo HORARIO; mismo día en otro turno pasa.

### A9. `TALLA REMERA` es singleSelect y la tool de Aurora manda texto libre → el alta del niño ENTERO muere con 422
`agent/tools/registro.py:105-106` + `airtable_client.py:759-760`. Opciones reales: `6,8,10,12,14,P,M,G,XG`. "talla 4" o "S" → 422 → se pierden nombre, fecha y links del niño, no solo la talla.

### A10. El fallo del registro de pago es silencioso: el admin recibe "💰 PAGO RECIBIDO ✅" aunque Airtable rechazó el POST
`agent/flujo_pagos.py:148-153, 222-230`. Solo `logger.error` — es lo que mantuvo invisible a CR1 dos semanas. El "NO SE REGISTRÓ" debe viajar en el mensaje al admin.

### A11. El guard "ya pagó" vive en la ventana de 50 mensajes del historial
`agent/pagos.py:146-153` + `main.py:2946`. Familia que pagó hace semanas y chateó >50 mensajes + un comprobante nuevo → re-dispara todo el flujo de prueba (PAGO PRUEBA + formulario de reserva a una inscripta). `tiene_pago_confirmado_db` (`memory.py:408`) existe y nadie lo usa acá.

### A12. `crear_o_actualizar_tutor` deduplica solo por `TELEFONO LIMPIO` → un número que vive en TELEFONO2 de otra fila crea duplicado (el #302, confirmado)
`agent/airtable_client.py:669`. Writers desprotegidos que la llaman directo: `cargar_nino.py:89-90` (alta admin por Flow) y `formulario_reserva.py:87` (que además avisa en su comentario que el form "puede traer OTRO teléfono").

### A13. Mamás linkeadas como PADRE: el parentesco se lee de la tabla equivocada (2 lugares)
- `agent/inscripcion.py:469-481`: busca el tutor_id (fila ALUMNOS) en `_TUTORES` con `RECORD_ID()` → nunca matchea → `parentesco=""` → todo hermano nuevo linkea por `padre_id`.
- `agent/tools/registro.py:95-96`: lee `PARENTESCO` de una fila de ALUMNOS (campo que no existe ahí) → siempre `padre_id`.
- Fix en ambos: `_parentesco_de_alumno` (como hace `crear_grupo_a_prueba`, `airtable_client.py:1194`).

### A14. Escalación: el silencio dura 5 min y la re-escalación se bloquea 1 hora → Aurora termina respondiendo el tema sensible
`agent/tools/escalacion.py:94` + `telegram_bridge.py:22,136-145` + `hooks.py:192-216`. `MINUTOS_SILENCIO=5` reactiva al agente; `anti_escalacion_spam` bloquea la segunda escalación 1h; a la madre que insiste a los 6 minutos le contesta Haiku sin salida.

---

## 🟡 MEDIOS

- **M1. Dedup de pagos compara `FECHA` (createdTime UTC) contra "hoy" PY** — `airtable_client.py:1280-1287` + `inscripcion.py:551-557`. Franja 21:00–23:59 PY: bloquea pagos legítimos ("ya registrado hoy") y deja pasar duplicados reales. Usar fecha convertida a PY o `FECHA PAGO`/`FECHA EFECTIVA`.
- **M2. Carrera check-then-create en `crear_asistencia`** — `airtable_client.py:1363-1367`. Tótem + QR simultáneos = dos filas = dos GASTA CLASE. Sin lock.
- **M3. POST de asistencia fallido en el check-in facial = clase gratis sin reintento** — `juego_endpoints.py:1096-1105`: la asistencia es best-effort pero el gate diario (`ult_oro_llegada`) lo setea el oro → el re-escaneo da `repetido` y no recrea la fila. Además el aviso al padre sale con el saldo sin descontar.
- **M4. El aviso con saldo solo existe en el check-in facial** — QR (`main.py:505-517`) y HQ (`hq_endpoints.py:155-179`) descuentan sin avisar (el docstring de `checkin_aviso.py` promete las tres puertas).
- **M5. Saldo negativo repite "Era la última clase de su pack" cada sábado** — `checkin_aviso.py:61-62` (`saldo <= 0`). Nada frena el saldo negativo; el mensaje esconde la deuda.
- **M6. Cache: la hora `%H:%M` invalida el segundo breakpoint casi siempre** — `brain.py:196-216,232-242`. El bloque 2 contiene "Hora actual: HH:MM" antes del breakpoint de conversación → se paga +25% de escritura y casi nunca se lee. Costo, no corrección.
- **M7. `stop_reason=max_tokens` con tools → loop de 3 reintentos idénticos y "Ups, algo falló" al padre** — `brain.py:263-311`.
- **M8. `/restaurar-aurora` es no-op silencioso si el número no tiene fila de conversación** — `main.py:1203-1214` + `ab_test.py:56-68` (no inserta ni avisa; devuelve ok igual).
- **M9. Menú de `/registro` (5 opciones) diverge del menú del prompt (4)** — `main.py:4646-4653` vs `prompts.yaml:131-135`; la opción 2 promete una lista que el prompt prohíbe.
- **M10. Año con `date.today()` del server (UTC) en la cancelación/confirmación por regex** — `main.py:3748-3774` y `4308`. Viola la regla dura #5 y en diciembre arma fechas del pasado → cancelación falla en silencio.
- **M11. Parser de montos: el skip de afiches quedó viejo** — `pagos.py:60` busca "1 hijo"+"2 hijo" pero los afiches dicen "2 hermanos" → las líneas del afiche vuelven a matchear patrones y pueden registrar 100k donde eran 150k, SIN el aviso de "monto ADIVINADO".
- **M12. `resumenes.py:934` filtra pagos por `{PAGA}` legacy** — no contempla `{PAGA (ALUMNOS)}`; ajustar junto con el fix de CR1. (El comentario sobre `FAMILIA FENIX` en :919 quedó obsoleto — ese campo ya no existe en PAGOS.)
- **M13. Links de tarjeta sin expiración ni versión de precio** — `pagos_tarjeta.py:36-39`: HMAC(monto:tel) eterno; un link viejo cobra el precio viejo y `/pago-confirmado` lo procesa como completo. El Pedido `esperando_pago` tampoco expira. (La dedup por `shop_process_id` + lock está bien.)
- **M14. CAPI Purchase sin value/currency y colapsado por día** — `meta_capi.py:88-92` (sin custom_data) y `:45-49` (event_id por día colapsa dos pagos legítimos). Pierde señal de ads, no plata.
- **M15. Notificadores salientes ignoran TELEFONO2** — `airtable_client.py:1500` (aviso check-in), `:1660` (broadcasts), `confirmacion_sabado.py:107,119`, `resumenes.py:109`: mandan al TELEFONO principal (puede ser el de Salsa) aunque Aurora reconozca a la familia por TELEFONO2.
- **M16. Stubs en TUTORES (juego/facturas) nacen con el CELL principal de ALUMNOS** — `juego_endpoints.py:233-237` + `facturas.py:87-92`: para familias TELEFONO2 el stub no se re-encuentra → CODIGO nuevo del juego en cada pedido / datos fiscales que se vuelven a pedir.
- **M17. Planilla de asistencia por nombres: tope 200 sobre NIÑOS** — `resumenes.py:489,566` (`max_records=200`, NIÑOS ~105 y creciendo). Horizonte meses.
- **M18. Inyección de comillas en fórmulas con texto libre** — `fotos.py:256-267` (apellido "D'Amico" rompe la fórmula → 422 → "no encontré"). Escapar `'`.
- **M19. Segundo comprobante: el aviso solo va al topic de Telegram (best-effort)** — `main.py:2955-2965`. Si se pierde, la recarga del pack jamás se carga.
- **M20. `obtener_horarios_disponibles` sin sort con `max_records=8`** — `airtable_client.py:895-920`: con >8 horarios futuros el sábado más cercano puede quedar afuera.

---

## 🔵 BAJOS

- **B1.** QR de reserva sin link NIÑO → `crear_asistencia(nino_id="")` sin dedup, fila huérfana (`main.py:509-513`).
- **B2.** HQ desmarcar borra la fila pero el gate del juego queda → re-escaneo no la recrea (`hq_endpoints.py:181-183`).
- **B3.** Marcado manual del HQ etiquetado MÉTODO=QR (el comentario "no tiene otras opciones" es falso: FACE existe) (`hq_endpoints.py:164-165`).
- **B4.** `flujo_pagos.py:402`: `350_000 → CLASE` es rama muerta hoy y trampa mañana (un link de tarjeta del pack registraría CONCEPTO=CLASE = 0 clases).
- **B5.** `ES QUIEN PAGA` no existe en ALUMNOS → la priorización "el que paga" en `padre_de_nino`/`registrar_pago_fenix`/`confirmacion_sabado` es siempre False (cae al primer tutor con teléfono).
- **B6.** `_inscripcion_pendiente` en memoria del proceso — restart de Railway a mitad de "cargar familia" y el "si" posterior muere (`inscripcion.py:13`).
- **B7.** `_escalaciones_recientes` y locks de flags en memoria del proceso (`hooks.py:189`, `ab_test.py:298`).
- **B8.** Heurística de escalación toma "Hola" como nombre del padre (`escalacion.py:39-51`).
- **B9.** Tool ejecutada + error de API posterior → acción real + "Ups, algo falló" al padre (`brain.py:313-323`).
- **B10.** `consultar_agendados` (nombres de niños) es código muerto listo para reconectarse sin límite por familia — no registrarla tal cual (`disponibilidad.py:85-117`).
- **B11.** Identidad: primer mensaje hardcodeado firma "profe Iván", el prompt dice "Sos Aurora" (`main.py:3306` vs `prompts.yaml:6`).
- **B12.** `_CAMPO_PACK_DESDE` duplicado (`airtable_client.py:1432-1433`), `GASTOS` max 100 (`resumenes.py:1014`), CONTENIDO tope 1000 (`airtable_client.py:1575`), `backfill_estado_ninos.py:111` KeyError en dry-run, `tests/test_local.py:86-91` resuelve padres por TUTORES legacy, montos de 7 dígitos no matchean el parser (`pagos.py:63-98`), `.claude/skills/cambioprecio.md:107` y `FENIX_RESUMEN.md:443` describen el modelo muerto (`recargar_pack`/`CLASES DISPONIBLES`).

---

## ✅ Verificado SANO (para no re-auditar)

- `ESTADO2` consistente en todos los readers/writers del estado del niño.
- `crear_asistencia` idempotente por día (fórmula `DATETIME_FORMAT` sobre campo date — correcto); timezone Asunción en los 3 check-ins.
- `_get_records` pagina con offset (el bug histórico de 100 está resuelto); los GET directos de main/loops/resumenes también paginan.
- Todos los selects que el código escribe existen con nombre exacto (ESTADO2, PLAN, CONCEPTO incl. PAQUETE5, MÉTODO incl. FACE, etc.) — salvo TALLA REMERA (A9).
- `obtener_saldo_clases` distingue 0 de None; `marcar_inicio_pack` solo escribe si vacío; no queda código vivo tocando `CLASES DISPONIBLES`/`ULTIMO DESCUENTO`/`descontar_clase`/`recargar_pack`.
- Precios consistentes en los lugares vivos del agente (350k pack, +150k hermano, 100k matrícula, prueba 100/150/200). Web fuera de alcance.
- Dedup de pasarela atómica por `shop_process_id` + lock por teléfono; formulario de reserva espeja todo antes de tocar Airtable y backfillea el pago huérfano; el saludo de Aurora sale del número matcheado; fallbacks a FAMILIAS eliminados de verdad; facturación funciona vía stubs en TUTORES (deuda, no bug).
- Crash str+list: sin otros casos vivos (los sitios sensibles defienden con isinstance/str).

## Dudas abiertas

1. **¿Se perdió algún pago real por CR1?** Los logs viejos de Railway ya no existen. Cruzar comprobantes del topic de Telegram vs filas de PAGOS desde el 25/07.
2. ¿Quién cargó los pagos de agosto con `PAGA (ALUMNOS)`? (¿Iván a mano? ¿pagos-bancard? — auditar que ese repo también haya migrado).
3. Fórmulas de Airtable del pack con hermanos: ¿`CLASES FENIX (PACK)` da 5 por niño cuando un pago de 500k cubre 2 hermanos?
4. Contrato con el mostrador (`salsa-soul-acceso/gui_acceso.py`): ¿escribe `PACK DESDE` al cobrar un pack?
5. ¿La ausencia de transición inscripción→aurora (A5) es hábito operativo deliberado (Iván corre `/registro`)?
6. Los 4 leads viejos en `agent_actual='aurora'`: ¿con qué `modo_nixie` quedaron?

## Orden de ataque sugerido (un cambio por deploy, con `/pre-cambio`)

1. **CR1a**: `"PAGA"` → `"PAGA (ALUMNOS)"` en `airtable_client.py:1318`.
2. **CR1b**: ídem en `inscripcion.py:566`.
3. **CR2**: `"TUTOR FENIX"` → `"TUTOR (ALUMNOS)"` en `inscripcion.py:645`.
4. **A10**: el fallo de registro viaja en el mensaje al admin (hace visible cualquier resto).
5. **A2**: `AL DÍA?` → `ESTADO` en `obtener_ninos_al_dia` (antes de prender la confirmación).
6. **CR3**: decidir con Iván el rediseño del puente texto→acción de Aurora (no es un parche regex).
7. El resto por severidad; A13 (parentesco) y A9 (talla) son fixes chicos y seguros.
