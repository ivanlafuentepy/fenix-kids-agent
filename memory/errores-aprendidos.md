# Errores aprendidos — FENIX KIDS AGENT

> Registro de problemas resueltos que costaron tiempo o tocaron producción.
> Leer ANTES de improvisar ante un problema de infra/deploy/config.

---

## 2026-08-07 — El schema de Airtable se movió abajo del código: `str + list` dejó a Aurora muda

**Qué pasó:** Ivan escribía a Aurora desde su número y no recibía nada. Tampoco respondían
`modo padre` ni `modo alumno`. El webhook procesaba el mensaje y explotaba:
`[WEBHOOK] Error procesando 595982790407: can only concatenate str (not "list") to str`
(`airtable_client.py:430` y `:465`). Como el crash pasaba ANTES de `_admin_modo_padre.add()`,
el modo nunca se activaba y todo lo siguiente caía en el `return` silencioso del modo secre:
un solo bug se veía como dos problemas distintos.

**Causa raíz:** los padres/madres se habían mudado a la tabla **ALUMNOS** (marcados con
`NEGOCIO = FENIX KIDS ACADEMY`), pero el refactor del 03/08 (`6ebaf1f`) seguía leyendo
`TUTORES FENIX`. Los campos `HIJOS (COMO PADRE)` / `(COMO MADRE)` que quedaron en TUTORES son
**singleLineText** — el código los sumaba como listas (`(f.get(...) or []) + (f.get(...) or [])`)
y con un string a la izquierda eso es un TypeError. Los 101 tutores tenían ese campo con texto.
El docstring del router decía "pre-check 03/08: cero tutores sin hijos linkeados" — era cierto
cuando se escribió y falso cuatro días después.

**Cómo se resolvió:** dos deploys incrementales. `95cb067` movió la identidad
(`buscar_tutor_por_telefono` → ALUMNOS por `TELEFONO LIMPIO`, hijos por `HIJOS FENIX (…)`,
niño→tutor por `PADRE/MADRE (ALUMNOS)`) y `3fafa06` los callers. Verificado en prod con
0 errores y `/api/alumnos` devolviendo tutores reales donde antes venía vacío.

**Reglas para la próxima:**
1. **Un refactor que asume la FORMA de un dato de Airtable verifica el schema real
   (Metadata API) antes de deployar.** La doc del repo y el pre-check de una sesión anterior
   describen el pasado, no el presente. `type` del campo, no el nombre.
2. **El traceback ya está en los logs de Railway** (`exc_info=True`): filtrar `deploymentLogs`
   por el teléfono afectado, después por `"line"` → archivo + línea exacta en dos consultas.
   No adivinar leyendo código.
3. **Un campo link que devuelve `str` significa que dejó de ser link.** Si `x or []` puede
   recibir un string, sumar listas revienta — pero el fix no es tolerar el string: es preguntar
   por qué cambió el tipo.
4. **ALUMNOS es una tabla COMPARTIDA** (Salsa/Impulso/Fenix): nunca borrarle una fila en un
   reset de Fenix (se le quita la marca `NEGOCIO`), nunca pisarle campos con datos (solo
   completar vacíos), y nunca traerla entera (filtrar por marca Fenix).
5. **Un mismo teléfono tiene varias filas en ALUMNOS** — el de Ivan matchea 3. Elegir por
   hijos-FENIX-linkeados > `NEGOCIO=FENIX`, nunca "el primero que aparece".

---

## 2026-07-28 — Una memoria que enumera "los N lugares" NO es un inventario: casi quedan precios viejos en producción

**Qué pasó:** al cambiar el precio (mensual 240k → pack de 350k), la memoria
`reference_donde_viven_precios_aurora` decía "4 archivos vivos" y los listaba. Se tocaron esos 4
y todo compilaba. Un grep de control (`240\.000|240mil|4 sábados` sobre `agent/` completo, DESPUÉS
de editar) encontró **3 lugares más**: los dos fallbacks de texto de los interceptores en
`main.py` (~3337 y ~3345, los que responden cuando el afiche YA se envió) y el mensaje de
seguimiento A de `reminders.py`. Sin ese grep, un lead que pedía precios dos veces habría recibido
el precio viejo en la segunda — y el follow-up automático habría seguido diciendo 240mil por
tiempo indefinido.

**Causa raíz:** la memoria se escribió el 24/06 y era correcta ESE día; después se agregaron
fallbacks nuevos. Una lista curada envejece en silencio: nada avisa cuando alguien suma un lugar.
El error no fue la memoria desactualizada — es tratar una lista como si fuera exhaustiva.

**Cómo se resolvió:** grep del valor viejo en todo `agent/` + `config/` después de editar, y
memoria actualizada a 7 lugares con la instrucción explícita de grepear igual.

**Segundo hallazgo de la misma tanda:** los links de pago de la web llevan
`sig = HMAC(LINK_SECRET, "fenix:{monto}")[:16]`. Cambiar el monto sin regenerar la firma deja el
link **roto para el cliente** (la pasarela lo rechaza) sin que nada falle de este lado. Antes de
generar las firmas nuevas se recalculó la vieja (240000 → `2567a029225be754`) y se comparó contra
la que estaba en la web: si el algoritmo no reproduce la firma vigente, está mal y las nuevas
también lo estarían.

**Regla para la próxima:** ante un cambio de valor que vive en varios lugares (precios, horarios,
teléfonos, URLs), **grepear el valor VIEJO en todo el repo después de editar** y no declarar
"listo" hasta que el grep vuelva vacío. Las listas de la memoria son pistas para empezar a buscar,
no la garantía de haber cubierto todo. Y si el valor viaja firmado, verificar la firma vieja antes
de emitir las nuevas.

---

## 2026-07-28 — WhatsApp borra/reescribe el EXIF de las fotos: la fecha "real" no siempre está en la foto

**Qué pasó:** Iván subió 28 fotos que le habían pasado por WhatsApp a la bandeja del catálogo.
17 no tenían EXIF de fecha y 11 tenían un EXIF con la fecha del REENVÍO (no la fecha real en que
se sacó la foto) — la compresión de WhatsApp pisa o borra ese metadato.

**Causa raíz:** el sistema (`scripts/optimizar_fotos.py`) confiaba ciegamente en el EXIF para
fechar cada foto. Eso funciona perfecto para fotos que salen directo de la cámara/celular, pero
se rompe en cualquier foto que haya pasado por WhatsApp (o cualquier app que recomprima).

**Cómo se resolvió:** `fecha_foto()` — si la foto vive en una carpeta `YYYY-MM-DD Día` (las que
arma `organizar_fotos_por_fecha.py`), ESA fecha manda sobre el EXIF; el EXIF solo aporta la HORA
si coincide con el día de la carpeta (para ordenar dentro del día). La fecha se recalcula en
TODAS las corridas, no solo al crear el registro — así que mover una foto ya publicada a la
carpeta correcta la corrige sola, sin re-procesar la imagen.

**Regla para la próxima:** si alguien manda fotos que "no tienen fecha correcta" o "dicen que son
de hoy", sospechar EXIF pisado por WhatsApp/reenvío — no hay forma de recuperar la fecha real
desde el archivo. Soluciones: (1) pedir que las reenvíen como "Documento" en WhatsApp (conserva
el EXIF real); (2) si se sabe la fecha por el chat, mover la foto a mano a la carpeta
`YYYY-MM-DD Día` correcta — el sistema la corrige solo en la próxima corrida del botón.

---

## 2026-07-27 — `wrangler r2 object put` SIN `--remote` escribe en un storage local de simulación (la subida "exitosa" nunca llega al bucket)

**Qué falló:** migración de las 1260 imágenes del catálogo de fotos al bucket R2 `fenix-fotos`.
El loop de `wrangler r2 object put fenix-fotos/... --file ...` terminó con "991 subidos, 0 errores"
— pero el CDN (`cdn.fenixkidsacademy.com`) devolvía 404 para TODO. Los archivos habían ido a
`.wrangler/state/` (479MB de storage local de simulación tipo miniflare) dentro del repo web.

**Causa raíz:** desde wrangler v3.33+, los comandos `r2 object put/get/delete` operan por defecto
sobre el storage LOCAL de desarrollo. Para tocar el bucket real hay que pasar `--remote` explícito.
No falla, no avisa fuerte: dice "Creating object..." igual.

**Cómo se resolvió:** re-migración por la **API REST de Cloudflare** (`PUT /accounts/{acc}/r2/buckets/{bucket}/objects/{key}`
con el oauth_token de wrangler leído de `AppData\Roaming\xdg.config\.wrangler\config\default.toml`) —
además resultó MUCHO más rápida que 1260 spawns de node (minutos vs ~40min) y respeta los headers
`Content-Type` y `Cache-Control` como metadata del objeto. Los scripts que quedaron con wrangler
(`publicar_fotos.py`, `borrar_fotos.py`) llevan `--remote` explícito y un comentario que lo explica.

**Regla para la próxima:** TODO comando `wrangler r2 object ...` lleva `--remote`, siempre. Tras
cualquier subida a R2, verificar con un `curl -I` al dominio público ANTES de dar por migrado nada.
Si aparece un directorio `.wrangler/` en un repo, es storage de simulación desperdiciado: borrarlo
(ya está en el .gitignore del repo web). Bonus del mismo día: el primer 404 tras subir puede ser
**cache negativo del edge** — verificar con `?nc=<random>` antes de asumir que el objeto no está.

---

## 2026-07-27 — Build de Cloudflare Pages colgado en `clone_repo` por repo pesado (y cómo cancelarlo por API)

**Qué falló:** con el repo web en ~520MB (fotos commiteadas), el build de Pages del commit
`adf039a` quedó **colgado en la etapa `clone_repo` 25+ minutos**, y los 2 pushes siguientes
quedaron encolados detrás. `wrangler pages deployment list` mostraba "Active" (ambiguo — no
distingue "en progreso" de "colgado"); el estado real se ve en la API:
`GET /accounts/{acc}/pages/projects/{proyecto}/deployments` → `latest_stage: {name, status}`.

**Causa raíz:** el clone del repo con ~500MB de blobs de fotos. Los builds anteriores pasaban
de casualidad; el crecimiento semanal lo iba a hacer crónico.

**Cómo se resolvió:** (1) cancelación del build colgado vía
`POST /accounts/{acc}/pages/projects/{proyecto}/deployments/{id}/cancel` (wrangler NO tiene este
comando) → la cola avanzó sola y el siguiente deployó en ~1 min. (2) Solución de fondo: migración
de las imágenes a R2 + `cdn.fenixkidsacademy.com`, imágenes fuera de git (`git rm --cached` +
.gitignore) — los commits semanales del botón quedaron en texto puro.

**Regla para la próxima:** binarios que crecen sin límite NUNCA van al repo de un sitio de Pages —
van a R2 con dominio custom. Si un build queda "Active" sospechosamente, mirar `latest_stage` por
API y cancelar por API. OJO: la historia del repo web todavía carga ~600MB de blobs viejos (los
clones frescos son pesados) — la limpieza con `git filter-repo` quedó como opcional CON OK de Iván.

---

## 2026-07-27 — Formulario de reserva: el dato REAL del padre se descartaba si el registro donde apoyarlo no existía todavía

**Qué falló:** primera prueba real en producción del formulario de reserva (25/07, lead 595981941407,
"Blas Páez"). El papá pagó, el bot mandó el Flow de Meta, el papá lo completó — y **todos esos datos
(nombre real del niño, CI, fecha de nacimiento, datos de mamá) se perdieron sin dejar rastro**. Ni en
Airtable, ni en la DB, ni en los logs de Railway (solo un `WARNING` sin el contenido). El único indicio
visible fue el mensaje "📋 Formulario de reserva completado" en Telegram — que no llevaba ningún dato,
solo la palabra "completado". El pago tampoco aparecía en las vistas filtradas de PAGOS.

**Causa raíz (dos bugs compuestos, no uno):**
1. `formulario_reserva.py` — `procesar_formulario_reserva` solo sabía **ACTUALIZAR** un niño que ya
   existiera (`obtener_grupo_familiar`). Si el extractor de Haiku no había capturado el nombre del niño
   antes (así que el niño todavía no existía en Airtable), la función devolvía `None`, el código
   loggeaba un `warning` y **saltaba todo el bloque de datos** — el `flow_data` completo se tiraba ahí
   mismo, sin persistir en ningún lado.
2. `registrar_pago_fenix` arma los links `NIÑOS FENIX`/`PAGA` del PAGO a partir del grupo familiar **en
   el instante del pago** — que ocurre ANTES del formulario. Si el niño nace 5 minutos después (cuando
   el formulario sí lo crea), el PAGO queda huérfano para siempre: nadie vuelve a mirarlo.

De fondo: el diseño trataba el dato **adivinado** (nombre que Haiku extrae del chat) como el eje sobre
el que se construye todo, y el dato **real y verificado** (el formulario) como un complemento opcional
que solo sabe decorar lo adivinado. Cuando la adivinanza fallaba, el dato real no tenía dónde apoyarse
y se perdía.

**Cómo se resolvió** (commits `7541b7e`, `1a8216d`, 27/07):
- Si el niño no existe, `procesar_formulario_reserva` ahora lo **CREA** con los datos reales del
  formulario (no solo actualiza).
- El contenido completo del formulario se guarda en DB **antes** de cualquier lógica, y se espeja
  siempre a Telegram + WhatsApp del admin — aunque todo lo demás falle después, el dato queda visible.
- `esperando_formulario_reserva=False` dejó de ser condición para PROCESAR el formulario — con el flag
  apagado (ej. el padre completa el Flow tarde, tras el rescate +24h), el mensaje caía al pipeline
  normal como texto `"[formulario]"` y se perdía igual.
- `prueba_creada=True` se setea al procesar — desarma el detector legacy de texto que, en el caso real,
  recreó al niño con el nombre ADIVINADO por encima de los datos reales que el formulario acababa de
  guardar.
- Back-fill: al crear/completar el niño, se buscan los PAGOs `PRUEBA` del lead sin `NIÑOS FENIX` y se
  les cuelga el link — cierra el agujero del punto 2 sin tocar `registrar_pago_fenix`.

**Regla para la próxima:** cuando un dato le llega al sistema desde una fuente verificada (formulario,
comprobante, confirmación explícita del usuario) y el registro donde ese dato "encaja" todavía no
existe, **la respuesta es CREAR el registro, nunca descartar el dato**. Y todo dato que viene de un
webhook externo (Meta Flow, pasarela de pago) se persiste crudo en DB **antes** de cualquier lógica de
negocio — si la lógica falla después, el dato sobrevive. Un log `warning` sin el contenido no es un
respaldo, es una miga de pan. Ver [[project_migracion_pago]], [[reference_reserva_formulario_meta]].

---

## 2026-07-25 — RC522/NFC: intentar "seguir la presencia real" de un tag (WakeupA/Select/Halt en loop) NO es confiable en este hardware — usar duración fija

**⚠️ ACTUALIZADO el mismo día — la "regla" original de abajo quedó DESCARTADA.** Se probó en producción
(hardware real, no simulado) y el fix protocolarmente correcto igual colgó el lector. Dejar el historial
completo para no repetir el ciclo de "arreglarlo bien" → volver a romperse.

**Intento 1 (descartado):** en `firmware/estacion/estacion.ino`, para que el LED se quedara prendido
mientras la pulsera seguía apoyada (en vez de un blink fijo), se armó un loop con `PICC_WakeupA` (a
diferencia de `PICC_IsNewCardPresent`/REQA, sí despierta un tag en HALT sin sacarlo del campo). Bug:
tocar una moneda NTAG213 y después un llavero Mifare Classic (o al revés) dejaba de leer el SEGUNDO tag.

**Causa raíz del intento 1:** por ISO14443-3, `HaltA` solo es válido en estado ACTIVE (tras anticolisión +
Select). El código mandaba `HaltA` justo después de un `WakeupA` exitoso, con el tag en READY (no
ACTIVE) — comportamiento no definido por el estándar. Fix "correcto": completar el ciclo
`WakeupA → PICC_Select(&uid) → HaltA`.

**Intento 2 (TAMBIÉN descartado, mismo día, horas después):** con el ciclo completo Wakeup→Select→Halt
ya aplicado (protocolarmente correcto), el bloqueo cruzado moneda/llavero **volvió a pasar, dos veces
más** — y esta vez sin ningún error visible en el log: tras un tap exitoso, el lector quedaba mudo 50+
segundos, sin detectar NINGÚN tag nuevo (ni siquiera un intento fallido registrado). Diagnosticado con
captura de serial en vivo (`arduino-cli monitor` no servía en este harness — se armó un script `pyserial`
para leer el puerto con timestamps). Causa exacta no identificada a nivel de registro del RC522 — solo
se confirmó que el propio mecanismo de mantener el tag "despierto" con Halt/Wakeup/Select repetido es
lo que lo produce, más allá de que sea protocolarmente correcto.

**Regla final:** en este proyecto (RC522 + librería `MFRC522` + ESP32), **NO usar un loop de
WakeupA/Select/Halt para detectar "¿el tag sigue apoyado?"** — es frágil y cuelga el lector para
CUALQUIER tag nuevo, de forma silenciosa. En su lugar, usar **duración fija** para cualquier feedback
que necesite "quedarse encendido un rato" (ej. LED tras un tap) — se pierde precisión (no sigue el
retiro exacto), pero es 100% confiable. Ver commit `315e7f4` (revierte `86f8f87`). Si en el futuro se
quiere retomar la detección de presencia real, primero investigar a nivel de registros del RC522
(dumps de estado) por qué se cuelga — no asumir que "está bien por protocolo" = "va a andar en este
hardware".

**Relacionado (esto SÍ sigue valiendo):** el feedback local (LED) NUNCA debe esperar al POST de red —
si el envío HTTPS es bloqueante y se hace ANTES del apagado del LED, un WiFi lento hace que el LED se
quede prendido de más aunque ya se sacó el tag.

## 2026-07-25 — Web NFC "no funciona" en Android no-mainstream: el diálogo Wallet/Etiquetas tapa la confirmación

**Síntoma:** al vincular pulseras reales en `/profe.html` desde un celular Huawei (sin Google
Play), el escaneo NFC parecía no completar — no se veía el cartel verde de confirmación, y
apareció un aviso nativo de Android "etiqueta vacía". Se sospechó que el Huawei no tenía Chrome
real (por el veto de Google a Huawei) y por lo tanto no soportaba `NDEFReader`.

**Causa raíz — la sospecha era FALSA.** El Web NFC sí funcionó de punta a punta: se confirmó
consultando directo la tabla `pulseras` de Postgres que el UID había quedado vinculado, con
timestamp de recién. Lo que pasaba era **puramente de UX**: al tocar la etiqueta, Android muestra
un diálogo del sistema preguntando "¿Wallet o Etiquetas?" — ese diálogo tapa la pantalla justo
cuando aparecería el toast de confirmación de la web, dando la falsa impresión de que falló.

**Regla:** antes de asumir que un dispositivo Android "no soporta" Web NFC, **verificar el
resultado real en la base de datos** (o el log del backend) en vez de confiar en lo que se ve/no
se ve en pantalla — el diálogo Wallet/Etiquetas es un falso negativo muy convincente. Elegir
siempre **"Etiquetas"** en ese diálogo (nunca Wallet). Si hace falta confirmar visualmente en la
propia app, considerar mover el toast a un lugar que sobreviva la interrupción del diálogo (o
usar el check ✅ persistente en la lista, ya implementado en `/profe.html`).

---

## 2026-07-25 — Para consultar Postgres de Railway desde afuera, usar `DATABASE_PUBLIC_URL`, no `DATABASE_URL`

**Síntoma:** necesité consultar la tabla `pulseras` directo desde esta PC (fuera de Railway) para
verificar una vinculación NFC. La variable `DATABASE_URL` del servicio del agente apunta a
`postgres.railway.internal` — **solo resuelve dentro de la red privada de Railway**, no desde
afuera.

**Causa raíz:** Railway expone DOS connection strings para su Postgres: `DATABASE_URL` (host
`.railway.internal`, para servicios DEL MISMO proyecto Railway) y `DATABASE_PUBLIC_URL` (host
`*.proxy.rlwy.net`, con el proxy TCP público — esa es la que sirve desde una laptop/script
externo). La pública vive en las variables del servicio **Postgres** mismo, no en las del
servicio `fenix-kids-agent`.

**Regla:** para debug de datos en caliente desde fuera de Railway (sin pasar por un endpoint
admin del agente), usar `DATABASE_PUBLIC_URL` del servicio Postgres vía la API GraphQL de
Railway (`variables(projectId, environmentId, serviceId: <id del servicio Postgres>)`), instalar
`psycopg2-binary` si hace falta, y consultar directo. Nunca imprimir la contraseña completa en
texto plano al usuario aunque se use en un comando — son los mismos secretos que ya viven en
Railway.

---

## 2026-07-25 — `crear_evento("vuelta", ...)` animaba la TV pero NUNCA pagaba plata real

**Síntoma:** al armar el circuito NFC físico y probar el cierre de vuelta en `/juego/totem-nfc`,
la TV festejaba "+100 🥈" pero el saldo `PLATA` del guardián en Airtable **nunca subía**. Bug
preexistente, no introducido en esta sesión — solo salió a la luz al probar hardware real por
primera vez.

**Causa raíz:** el cierre de vuelta por NFC solo llamaba `crear_evento("vuelta", ...)` (que
alimenta el polling de la TV) y nunca pasaba por `_acreditar()` — la función que el propio código
documenta como **"única puerta al dinero"** (PATCH del saldo en GUARDIANES + fila en
MOVIMIENTOS). El camino manual (`/juego/vuelta-face`, el botón del profe en la tablet) sí lo hacía
bien; el camino NFC lo omitía por completo.

**Regla:** en `agent/juego_endpoints.py`, **cualquier feature nueva que otorgue oro/plata tiene
que llamar `_acreditar()` explícitamente** — emitir el evento de celebración (`crear_evento`) NO
alcanza, esa función solo anima la TV, no toca el saldo. Antes de dar por ganada una moneda,
grep `_acreditar` en el flujo nuevo y confirmar que está.

---

## 2026-07-24/25 — ESP32: variante "-U" sin antena + SSID con espacio invisible

**Síntoma 1:** un ESP32 nunca lograba conectarse a ninguna red WiFi (`NO_AP_FOUND` constante,
antena o no). **Síntoma 2:** otro ESP32 (DevKitC normal) tampoco conectaba a la red esperada de
La Casona, mismo error.

**Causa raíz 1:** el módulo era la variante **"WROOM-32U"** (nombre en el chip metálico termina
en **-U**) — tiene un conector IPEX/U.FL para antena EXTERNA en vez de la antena de PCB soldada.
Sin antena física conectada ahí, el radio no tiene por dónde transmitir. La variante sin sufijo
(o "-D") trae la antena de PCB integrada y anda de una.

**Causa raíz 2:** el SSID real de la red tenía un **espacio invisible** antes del sufijo
(`LA CASONA LAFUENTE _EXT`, no `..._EXT` pegado) — imposible de notar mirando el celular/router,
y el nombre puesto a mano en el firmware no coincidía ni por asomo.

**Regla:** (1) **antes de comprar/usar un ESP32 para un proyecto con WiFi, confirmar que NO
termina en "-U"** (o asegurarse de tener la antena externa). (2) **Nunca tipear un SSID a mano de
memoria en firmware** — agregar un `WiFi.scanNetworks()` al arranque del sketch que imprima los
SSIDs reales + RSSI (ver `firmware/estacion/estacion.ino::escanear_redes()`) y copiar el nombre
exacto de ahí, no adivinarlo.

## 2026-07-14 — `git commit -m @'…'@` (here-string) de PowerShell se rompe con comillas internas

**Síntoma:** commiteando F7.b-c1 con un mensaje multi-línea vía
`git commit -m @'…texto con "comillas" y (paréntesis)…'@`, PowerShell **no pasó el here-string
como un solo argumento**: git recibió las palabras sueltas como pathspecs →
`error: pathspec 'encontre' did not match any file(s)` y no commiteó. Tuve que rehacerlo.

**Causa raíz:** el here-string `@'…'@` como valor de `-m` es frágil cuando el cuerpo tiene
comillas dobles, paréntesis o apóstrofes — el parser de PowerShell + el paso al exe nativo lo
fragmenta. No es determinístico según el contenido.

**Solución que SÍ funciona:** escribir el mensaje a un archivo (Write tool → scratchpad) y
`git commit -F <ruta>`. Cero problemas de escaping, cualquier contenido. Lo usé para el resto de
los commits de la sesión sin un solo fallo.

**Regla:** para mensajes de commit **multi-línea** en PowerShell, NO usar `-m @'…'@`. Usar
`git commit -F <archivo>` con el mensaje escrito a un archivo. Para mensajes de una línea, `-m "…"`
está bien. (Los `-m "…" -m "…"` múltiples de una línea cada uno también funcionan.)

---

## 2026-07-13 — `FIND(record_id, ARRAYJOIN({campo_link}))` SIEMPRE da 0 — funciones rotas en prod sin que nadie lo note

**Síntoma:** durante la migración FAMILIAS descubrí que `buscar_reservas_familia` y
`cancelar_reservas_familia_fecha` (airtable_client) devolvían **0 resultados aunque la familia
tuviera reservas reales** — verificado en vivo: una familia con 2 reservas futuras → `[]`. La
señal de reagendamiento B7 (main.py) dependía de `buscar_reservas_familia` y por eso **nunca
funcionó**; el fallback de PRUEBA FENIX la tapaba, así que el bug pasó meses invisible.

**Causa raíz:** `ARRAYJOIN({campo_link})` de un campo **link** devuelve los **NOMBRES** de los
registros vinculados (el primary field), **NO** sus `record_id`. Entonces
`FIND('recXXXXXXXX', ARRAYJOIN({FAMILIAS}))` busca un `recXXX...` dentro de un texto que solo
tiene nombres → **siempre 0**. Ya estaba anotado a medias en
`reference_get_records_no_pagina` ("no filtrar links con FIND(id)") pero igual había DOS
funciones vivas haciéndolo.

**Cómo se resolvió:** las lecturas de reservas de una familia pasan a los **links inversos del
niño** (`NIÑOS.RESERVAS FENIX`) → traer esas reservas por `RECORD_ID()`. El contexto Aurora
(C5), la señal de reagendamiento (2.C-C2), el QR (2.D) y las tools (2.C-C1) ya usan ese patrón.

**Regla para la próxima:** para saber qué registros vincula un link, **leé el propio campo link
del registro dueño (te da los record_ids) o el link inverso** — NUNCA `FIND(id, ARRAYJOIN(link))`.
Para filtrar por record_id sobre un conjunto: `OR(RECORD_ID()='recA', RECORD_ID()='recB', ...)`.
Y cuando una función "de búsqueda" devuelve vacío en un caso que debería matchear, sospechá
de ARRAYJOIN antes de asumir que no hay datos. **Pendiente F7.b:** `agenda._cancelar` todavía
usa `cancelar_reservas_familia_fecha` (rota) — arreglarla al cortar FAMILIAS.

---

## 2026-07-13 — "Pago de FENIX" NO se filtra por FUENTE (hay pagos de Fenix con FUENTE='SALSA SOUL STUDIO')

**Síntoma:** tras el backfill de la migración (linkear cada pago a sus niños), dos hermanos —
**Tomas y Joaquín Molinas Silva** — quedaron con `AL DÍA?` **vacío**, mientras su familia decía
`❌ VENCIDO`. Discrepancia entre el modelo nuevo (por niño) y el viejo (por familia).

**Causa raíz:** el script filtraba los pagos con `{FUENTE}='FENIX KIDS ACADEMY'`. Pero PAGOS es
una tabla **compartida con Salsa Soul**, y hay pagos de familias de **FENIX** cargados con
`FUENTE='SALSA SOUL STUDIO'` (ese, concepto `F.SUSCRIPCION`, 150.000). El filtro los dejaba
afuera → el pago nunca se linkeaba a los niños → sin `VENCE EL`.

**Cómo se resolvió:** cambiar el criterio a `{FAMILIA FENIX}!=''`. Un pago es de FENIX si está
**linkeado a una FAMILIA FENIX**, no por su etiqueta de FUENTE. Con eso: 0 discrepancias en los
103 niños comparables.

**Reglas para la próxima:**
1. **La FUENTE de PAGOS no es confiable** para saber si un pago es de Fenix — el LINK sí lo es.
   Aplicar en todo el código de la migración FAMILIAS (y en cualquier consulta de pagos).
2. Después de un backfill, **contrastar el resultado contra el modelo viejo** (acá: `AL DÍA?` del
   niño vs el de su familia). Si hay una sola discrepancia, investigarla — no promediar ni
   ignorarla: fue exactamente la que destapó el dato sucio.

---

## 2026-07-13 — Crear campos por Metadata API: qué acepta y qué no (ensayo-error que no hay que repetir)

**Síntoma:** 3 intentos fallidos con 422 al crear un campo `multipleRecordLinks`; los mensajes de
error eran **contradictorios entre sí** ("isReversed is missing" → "prefersSingleRecordLink is
missing" → "ninguno de los dos está en el schema").

**Causa raíz:** al **crear** un link, la Metadata API solo acepta `options.linkedTableId`.
`prefersSingleRecordLink` e `isReversed` se **rechazan al crear** (se configuran después, o desde
la UI). Los mensajes de error de Airtable describen las variantes del schema, no lo que falta.

**Lo que SÍ funciona (probado):**
- Link: `{"type": "multipleRecordLinks", "options": {"linkedTableId": "tbl..."}}` — nada más.
- **Rollup SÍ se puede crear por API** (contra lo que decía el skill): `{"type": "rollup",
  "options": {"recordLinkFieldId": "fld...", "fieldIdInLinkedTable": "fld...",
  "formula": "MAX(values)"}}` — SIN `result` ni `referencedFieldIds` (los rechaza).
- Fórmula: `{"type": "formula", "options": {"formula": "..."}}` — dentro de la fórmula, los campos
  se referencian por **field id** (`{fldXXXX}`), no por nombre.
- El campo **inverso se crea solo** con un nombre feo ("NIÑOS FENIX 2") → renombrarlo con PATCH.
- **Token:** el de FENIX es data-only → para schema, el de **Dorita** (`whatsapp-agentkit/.env`).

---

## 2026-07-13 — El prompt cache no cacheaba NADA (y el `cache_control` mentía en silencio)

**Síntoma:** creíamos tener prompt cache activo desde siempre (`cache_control: ephemeral` en el
system). En realidad el cache **nunca se leía**: se pagaba el premium de escritura sin ahorro.

**Causa raíz — DOS problemas, no uno:**
1. La hora `%H:%M` se inyectaba al **inicio** del bloque cacheado (`_contexto_fechas()` →
   `cargar_prompt_agente()`). El cache es un **prefix match**: el bloque cambiaba cada minuto,
   así que el prefijo nunca coincidía.
2. Al arreglar (1), el cache **seguía en `r0 w0`**. Medido contra la API con `count_tokens` +
   llamadas reales: el prefijo `tools + system` de ivan es **~4350 tokens** y **no alcanza el
   mínimo cacheable real de Haiku 4.5**. Cuando un prefijo no llega al mínimo, la API
   **ignora el `cache_control` en silencio** — sin error, sin warning, `cache_creation = 0`.

**Cómo se resolvió:**
- System en **dos bloques**: bloque 1 = fechas del día **sin hora** + prompt del YAML (cacheado,
  estable todo el día, compartido entre todas las conversaciones); bloque 2 = hora + contexto
  del lead (sin cache, cambia por mensaje sin invalidar el bloque 1).
- **Segundo breakpoint en el mensaje actual del usuario**: el prefijo `tools+system+historial`
  crece con la conversación y **sí** cruza el mínimo. Los hits se acumulan turno a turno — y el
  grueso del gasto está justo en las conversaciones largas.
- Verificado con llamadas reales: llamada 1 → `cache_creation=6783`, llamada 2 → `cache_read=6783`
  con solo 3 tokens sin cachear. El log de `brain.py` ahora imprime `cache r{N} w{N}` por llamada.

**Reglas para la próxima:**
1. **Un `cache_control` puesto NO significa que el cache funcione.** Verificar SIEMPRE con
   `usage.cache_read_input_tokens` / `cache_creation_input_tokens`. Si son 0 en llamadas
   repetidas, hay un invalidador silencioso o el prefijo no llega al mínimo.
2. **Nada volátil (hora, UUID, contador) dentro o antes del bloque cacheado.** Lo dinámico va
   DESPUÉS del último breakpoint.
3. El **mínimo cacheable de Haiku 4.5 es alto** (nuestro system solo no llega). Si el system no
   alcanza, poner el breakpoint más adelante (mensaje del usuario) para que el prefijo con
   historial lo cruce.

---

## 2026-07-13 — `tests/test_local.py` roto: la suite entera llevaba semanas sin correr

**Síntoma:** `py -3 -m pytest tests/ -q` → `ERROR collecting tests/test_local.py` →
`Interrupted: 1 error during collection`. **Cero tests corriendo** (ni los que sí funcionaban),
y el paso 2 del Definition of Done (`pytest tests/ -q`) era literalmente imposible de cumplir.

**Causa raíz:** el simulador importaba `_detectar_activacion_nixie` y `_detectar_handoff_ivan_nixie`
de `main.py` — funciones del flujo **Nixie, eliminado hace tiempo** — y `_detectar_confirmacion_aurora`
desde `main` cuando se había movido a `detectores_conv.py`. Un `ImportError` a nivel de módulo
**tumba la recolección de TODO pytest**, no solo de ese archivo.

**Cómo se resolvió:** actualizar los imports al flujo actual (router por familia en DB, sin
handoff por texto), sacar el bloque Nixie del simulador y corregir el desempaque de
`_build_contexto_aurora` (ahora retorna tupla). Resultado: **30 tests pasan**.

**Reglas para la próxima:**
1. Al **eliminar una función**, greppear los tests igual que el código de producción — un test
   roto no avisa: silencia la suite completa.
2. Si `pytest` dice "error during collection", **NO es un test que falla**: es un import roto que
   apaga todo. Arreglarlo antes de confiar en cualquier "los tests pasan".
3. Correr `pytest tests/ -q` de verdad antes de decir "listo" (es el DoD, no un adorno).

---

## 2026-07-11 — Un número abría VARIOS temas en Telegram (rebote de grupo por dos fuentes de verdad)

**Síntoma:** un mismo número de WhatsApp abría 2-5 temas (topics) en Telegram, sobre todo
familias. Iván lo vio en el grupo "FENIX KIDS RESERVAS" (que es el grupo de LEADS, nombre
confuso).

**Diagnóstico — mi error primero:** afirmé "un topic por teléfono" leyendo el comentario
del código, y después culpé a que faltaba `unique=True` en el modelo. AMBAS sin mirar los
datos. La base SÍ tiene índice UNIQUE en `telefono` (0 duplicados en DB, 1 fila/teléfono).

**Causa raíz (confirmada con datos):** `obtener_o_crear_topic` crea un topic NUEVO en
Telegram cada vez que el grupo destino ≠ el grupo del topic guardado (cierra el viejo, que
queda VISIBLE). Había DOS fuentes de verdad del grupo que se peleaban: el flujo principal
usa `grupo_telegram_para` (agent_actual), pero los 3 followups de `loops.py` forzaban
`group_id_para_agente("ivan")` = grupo LEADS. Para una familia (aurora): followup→LEADS
(topic nuevo), mensaje→FLIAS (otro topic), followup→LEADS… cada salto = 1 topic. Evidencia
dura: 15 de 25 familias tenían su topic en el grupo de LEADS (cruzando `topics_telegram.group_id`
con `conversaciones_ab.agent_actual`).

**Fix (commit 022b655):** los 3 followups usan `grupo_telegram_para(telefono)`, misma
fuente de verdad que el flujo principal y el envío de facturas. Los 15 desalineados se
auto-corrigen en su próximo mensaje (1 vez, ya sin loop).

**How to apply:** el grupo/topic de un número debe decidirse SIEMPRE por `agent_actual`
(una sola fuente de verdad). Nunca hardcodear el grupo en un call site. Y ante "se abren
muchos X", ir a los DATOS (cruzar tablas en la DB de prod con asyncpg + DATABASE_PUBLIC_URL),
no al comentario del código. La DB de prod se consulta con el token de Railway.

---

## 2026-07-11 — El video del tótem tardaba y se cortaba: Cloudflare Pages sirve TODO con cache 0

**Síntoma:** en la TV del tótem el video del Fenix (fenix_saludo.mp4) tardaba en cargar,
se veía un segundo y se cortaba, "cargando el mp4 desde cero" cada vez. El archivo local
y el de prod eran idénticos y correctos (5s, 590KB, faststart OK).

**Causa raíz:** Cloudflare Pages sirve por defecto TODOS los archivos con
`Cache-Control: public, max-age=0, must-revalidate`. En el navegador de la TV (flojo)
eso obliga a re-pedir/revalidar el video a la red en cada reproducción/reload en vez de
usar el cacheado → buffering, corte al segundo. No era el archivo ni el `<video>` (ya
tenía loop + preload=auto); era el header.

**Fix:** archivo `mundo-fenix/_headers` (Pages lo respeta en direct upload) que cachea
`/assets/*` con `max-age=2592000` (30 días). El HTML queda SIN cachear a propósito para
no romper el auto-reload kiosk. La TV baja cada asset una vez y lo reproduce del cache.

**How to apply:** en cualquier página kiosk de Pages, los assets pesados (video/audio/
imágenes) necesitan `_headers` con cache largo — el default max-age=0 los re-baja siempre.
Si reemplazás un asset con el MISMO nombre, la TV lo ve viejo hasta 30 días → cache purge
en Cloudflare o renombrar (ej `_v2`). Diagnóstico: `curl -sD - -o /dev/null <asset>` y
mirar el Cache-Control real de prod ANTES de tocar el archivo o el frontend.

---

## 2026-07-11 — El comando `selfie` no encontraba nombres largos (acentos + multi-palabra)

**Síntoma:** `selfie Fiorella Gonzalez Aguero` (dos nombres/dos apellidos, escrito sin
tilde) no encontraba al niño; con un solo nombre+apellido sí.

**Causa raíz:** en `fotos.py` la búsqueda tenía DOS ramas: una palabra usaba variantes
sin/​con acento (tolerante), pero **multi-palabra usaba las palabras crudas** contra
`FIND` de Airtable, que es sensible a acentos. Como los apellidos compuestos casi siempre
llevan tilde en el dato (González, Rodríguez) y se escriben sin ella, el AND por palabra
nunca matcheaba. No era "dos nombres y dos apellidos" — era acentos en cualquier búsqueda
de 2+ palabras.

**Fix (commit 556f15e):** unificar las dos ramas — cada palabra matchea por OR de sus
variantes de acento (la palabra, sin acentos, y con una vocal acentuada) sobre
NOMBRE/APODO/APELLIDO, y AND entre palabras. Probado con positivos sin/con tilde, una
palabra y negativos.

**How to apply:** Airtable `FIND`/`SEARCH` NO ignora acentos. Cualquier búsqueda de texto
por nombre debe generar variantes de acento por palabra (o comparar sobre un campo
normalizado). Si hay una rama "tolerante" y otra "cruda", tarde o temprano la cruda muerde.

---

## 2026-07-11 — Dos Fiorellas: el gate de llegada por NOMBRE dejó a la segunda sin oro

**Síntoma:** Fiorella González llegó, el Espejo la reconoció, pero "monedas: 0" — sin
oro, sin movimiento, sin asistencia. Fiorella Perinetto (llegó antes) tenía todo bien.

**Causa raíz:** el "¿ya llegó hoy?" del checkin-face buscaba en `juego_eventos` por
`nino_nombre` — que guarda solo el NOMBRE de pila ("Fiorella"). La segunda Fiorella
matcheó la llegada de la primera → repetido=True → se salteó oro + asistencia + evento.

**Fix (commit d673c70):** repetido = `ult_oro_llegada == hoy` en el ESTADO JSON del
guardián del niño — gate DIARIO POR NIÑO que ya existía para el oro (cross-canal con
NFC). Se eliminó la consulta por nombre. Datos reparados a mano (+10, movimiento,
gate, asistencia) dejando `presentar_avatar` pendiente para que la TV la celebre.

**How to apply:** en el juego NUNCA identificar niños por nombre de pila — siempre
`nino_id` (Airtable record) o gates en el estado del guardián. `nino_nombre` en
eventos es SOLO display para TV/mapa. Ojo con hermanos y tocayos: es el caso normal,
no el edge case.

---

## 2026-07-11 — FENIX tiene WABA propio: el Flow "cargar niño" falló por crearse en el WABA de Dorita

**Síntoma:** el comando `cargar niño` respondía "No pude enviar el formulario"; Meta
devolvía #131009 "flow_id is invalid... belongs to your WhatsApp Business Account".

**Causa raíz:** la doc del repo (scripts/crear_flow_fenix.py, bitácora) decía "Fenix
vive en el WABA compartido con Salsa Soul (2112324596219739)". FALSO: ese WABA solo
contiene el número de Dorita (verificado con lista paginada completa). Lo compartido
es el Business Portfolio; el número de FENIX tiene WABA propio: **896276490105251**.
La confusión Business Account ≠ WABA venía desde abril. El Flow `fenix_inscripcion`
(FENIX_FLOW_ID) tiene el mismo problema y nunca hubiera funcionado.

**Cómo se descubrió el WABA:** ningún token disponible (Fenix, Dorita, app token)
puede listar los WABAs del negocio (falta scope business_management). La única fuente
es el `entry.id` de cualquier webhook — quedó log permanente en parsear_webhook
(meta.py): "[META] WABA de este numero".

**Fix:** Flow recreado en 896276490105251 con el PROPIO token de FENIX (administra su
WABA sin ayuda de Dorita) → FLOW_CARGAR_NINO_ID=2122521084980809 en Railway + restart.
También corregido WHATSAPP_BUSINESS_ACCOUNT_ID (apuntaba al WABA de Dorita; lo usa CAPI)
y el token META_ACCESS_TOKEN muerto del .env local. Flow huérfano deprecado.

**How to apply:** flows/plantillas/subscribed_apps de FENIX van SIEMPRE en el WABA
896276490105251 con el token de FENIX. Pendientes detectados: recrear fenix_inscripcion
en el WABA correcto cuando se conecte su handler; META_CAPI_ACCESS_TOKEN está muerto
(error 190) — los eventos CTWA no deben estar llegando.

---

## 2026-07-12 — Dos sesiones, un índice git: el stage de una viajó en el commit de la otra

**Síntoma:** el Push 1.2 de la migración (staged con git apply --cached) apareció
commiteado dentro de d2b3b33 ("docs(skill): plantilla...") de la sesión paralela,
con mensaje que no describe ese cambio.

**Causa raíz:** las dos sesiones comparten el MISMO working tree e índice. Sesión A
stageó su hunk y ejecutó el commit en un tool call POSTERIOR; entre medio, sesión B
corrió su propio git commit y se llevó el índice completo (su cambio + el hunk ajeno).

**How to apply:** con sesiones paralelas, stage y commit SIEMPRE en una sola cadena
atómica (git add/apply --cached && git commit && git push). Nunca separar stage y
commit en pasos distintos. Antes de commitear, git diff --cached para confirmar que
solo viaja lo propio. Si un hunk ajeno ya viajó en un commit propio: avisar a la otra
sesión con el hash y NO reescribir historia (el push compartido lo resuelve).

---

## 2026-07-11 — El atajo numérico del menú secre pisaba las selecciones pendientes

**Síntoma:** `selfie Horacio González` encontró 2 candidatos y pidió responder con un
número; al responder "1" el agente mostró el resumen de reservas en vez de seleccionar.

**Causa raíz:** el remapeo del menú secre (`"1"` → `"resumen reservas"`, main.py ~2450)
corre ANTES que todos los handlers de estado pendiente y solo excluía `_admin_modo_padre`.
Cualquier flujo que espera respuesta numérica del admin (`_cara_candidatos`,
`_asistencia_pendiente`, `_inscripcion_pendiente`) quedaba en sombra: el "1" nunca
llegaba a su handler.

**Fix:** el atajo se salta cuando hay un estado pendiente que consume la respuesta
(commit 82d196c — quedó mezclado con el fix del WABA ID de otra sesión paralela que
barrió el staging; los dos cambios eran de bajo riesgo y ya estaba pusheado).

**How to apply:** todo atajo/interceptor GLOBAL de admin debe excluir explícitamente
los estados pendientes que esperan input — al agregar un flujo nuevo con respuesta
numérica, sumarlo a `_admin_espera_respuesta`. Y con dos sesiones de Claude en paralelo
sobre el mismo repo: nunca dejar cambios en staging sin commitear al instante.

---

## 2026-07-11 — La asistencia por FACE nunca se creó (select sin la opción)

**Síntoma:** ASISTENCIA FENIX tenía UN solo registro histórico (QR 06/06) pese a que
`checkin-face` llama `crear_asistencia(..., metodo="FACE")` en cada llegada desde el 08/07.

**Causa raíz:** el campo `MÉTODO` es un single-select que solo tenía la opción "QR" —
cada POST con "FACE" devolvía 422 `INVALID_MULTIPLE_CHOICE_OPTIONS`, y el try/except
best-effort del check-in lo tragaba sin que nadie lo viera.

**Fix:** crear la opción una sola vez con un POST con `"typecast": true` (crea la opción
del select si el token tiene permiso de creator) y borrar el registro de prueba. El
código no cambió — ahora el POST normal funciona.

**How to apply:** clásico airtable-seguro — un flujo "best-effort" que escribe en un
select AJENO al código necesita que la opción exista EXACTA. Ante una tabla que "no se
llena", probar a mano el POST exacto del código y mirar el 422. `typecast:true` es la
salida para crear opciones sin ir al UI de Airtable.

---

## 2026-07-11 — La tablet/TV no reciben los deploys de mundo-fenix (bug "AlanTest")

**Síntoma:** Iván probó el check-in facial como AlanTest (sin avatar) y el tótem fusionó
directo con Mamba en vez de ofrecer el selector de Guardián — con el backend correcto
(GUARDIANES tenía la fila con ROBOT vacío) y el código nuevo deployado en Pages.

**Causa raíz:** la tablet y la TV viven con la página ABIERTA por días. Chrome/Fully
Kiosk no recargan solos una página abierta → un `wrangler pages deploy` nuevo no llega
nunca al dispositivo hasta un reload manual. La evidencia decisiva en los logs de
Railway: cero POSTs a `/juego/elegir-robot` y `/juego/vuelta-face` en toda la mañana —
el frontend nuevo jamás se ejecutó.

**Fix:** auto-reload en `totem.html` e `index.html` (modo ?tv): cada 10 min bajan su
propio HTML (`fetch cache:no-store`) y comparan un hash del texto; si cambió y la
pantalla está EN REPOSO (tótem: `!ocupado`; TV: portada o mapa visible, nunca en
celebración) → `location.reload()`. La TV además guarda `mf_tv_despierto` en
sessionStorage para saltar la portada "Tocá para despertar" tras un auto-reload.
OJO: Cloudflare Pages NO manda ETag/Last-Modified en el HTML — por eso se hashea el
texto completo, no sirven los headers.

**How to apply:**
- Ante "el flujo nuevo no aparece en la tablet/TV", la PRIMERA hipótesis es página
  vieja abierta: mirar en los logs si los endpoints nuevos recibieron requests.
- Tras un deploy de mundo-fenix, los dispositivos se actualizan solos en ≤10 min
  (estando en reposo). Para verlo YA: recargar a mano.
- Cualquier página kiosk nueva del ecosistema debe nacer con este auto-reload.
