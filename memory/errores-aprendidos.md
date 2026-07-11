# Errores aprendidos — FENIX KIDS AGENT

> Registro de problemas resueltos que costaron tiempo o tocaron producción.
> Leer ANTES de improvisar ante un problema de infra/deploy/config.

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
