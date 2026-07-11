# Errores aprendidos — FENIX KIDS AGENT

> Registro de problemas resueltos que costaron tiempo o tocaron producción.
> Leer ANTES de improvisar ante un problema de infra/deploy/config.

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
