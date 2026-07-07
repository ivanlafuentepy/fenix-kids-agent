# /masivo — Envío masivo de WhatsApp con pre-flight obligatorio

Recibís como argumento: $ARGUMENTS (descripción del envío, ej: "video FU a leads de mayo", "aviso cambio de horario a familias").

> Cada regla de este skill salió de un incidente real: 139 mensajes fallidos por token
> desalineado, 45 min perdidos por curl directo a Meta, envíos sin permiso marcados
> como error grave. NO saltear pasos.

## Paso 0 — Permiso

**NUNCA ejecutar un masivo sin OK explícito de Ivan.** Antes de tocar nada, confirmar:
audiencia exacta, mensaje/media exacto, y que Ivan diga "dale/sí/enviá".

## Paso 1 — Pre-flight del token

1. Ejecutar el diagnóstico del skill global `renovar-token-meta` (Paso 1: `/test-envio/` al admin).
2. Si el script usa `.env` local (`load_dotenv()` + `META_ACCESS_TOKEN`): comparar los primeros
   10 caracteres del token local contra la memoria `reference_meta_prod_token.md`. Si difieren,
   actualizar `.env` ANTES de correr nada.

## Paso 2 — Armar la audiencia

- Datos SIEMPRE desde los endpoints de Railway (`/api/alumnos`, Airtable via API) — ver skill
  global `airtable-seguro` si hay que leer tablas (paginación >100, etc.).
- Mostrar a Ivan: cantidad de destinatarios + 3 ejemplos con nombre y teléfono.
- Excluir duplicados por teléfono. Verificar que ningún número sea el de un lead confundido
  con el de Ivan (su número es 595982790407).

## Paso 3 — Test a 1 número (el admin)

Enviar el mensaje EXACTO (con personalización real de un destinatario de ejemplo) a
595982790407 via `/test-envio/` de Railway:

```bash
curl -s -H "X-ADMIN-KEY: $ADMIN_API_KEY" \
  "https://fenix-kids-agent-production.up.railway.app/test-envio/595982790407?msg=$MSG_URLENCODED"
```

Esperar que Ivan confirme que le llegó y se ve bien. Sin esa confirmación, NO seguir.

## Paso 4 — Envío con rate limit

- SIEMPRE via el servidor de Railway (mismo `proveedor.enviar_mensaje()`), NUNCA curl
  directo a la Graph API (ventana 24h: Meta devuelve 200 y no entrega).
- Batches con pausa (referencia: 10 mensajes cada 10 min en `fu_grupo_b_lujan.py`;
  para listas cortas, mínimo 2-3 s entre mensajes). Meta puede silenciar el número por spam.
- Loguear cada envío: teléfono, status, respuesta. Al primer patrón de errores (3 seguidos),
  PARAR y diagnosticar — no quemar la lista completa.
- Si los destinatarios están fuera de ventana 24h → no sirve mensaje libre: usar plantilla
  aprobada (ver `/plantilla`) o links wa.me pre-cargados para que Ivan envíe manual.

## Paso 5 — Cierre y registro

1. Reportar: enviados OK / fallidos (con teléfonos) / salteados.
2. **Registrar en la bitácora**: `BITACORA FOLLOWUP FENIX.md` (Desktop/PROYECTOS MD) —
   fecha, audiencia, mensaje, resultados.
3. Si hubo fallidos con 401 → correr `renovar-token-meta` completo antes de reintentar.

## Anti-errores

- ❌ Correr un script de FU viejo (fu_grupo_a, fu_video_*) sin revisar: tienen fechas y
  lógica hardcodeadas de campañas pasadas — leerlos completos antes de reutilizar.
- ❌ "Ya probé una vez la semana pasada" — el pre-flight es POR CADA masivo.
- ❌ Reintentar los fallidos en loop sin diagnosticar la causa raíz.
