# Errores aprendidos — FENIX KIDS AGENT

> Registro de problemas resueltos que costaron tiempo o tocaron producción.
> Leer ANTES de improvisar ante un problema de infra/deploy/config.

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
