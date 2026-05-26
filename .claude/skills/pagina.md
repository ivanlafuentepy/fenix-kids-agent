# /pagina — Generar página de mensajes masivos y deployar a Cloudflare Pages

Recibís como argumento: $ARGUMENTS (slug de la página, ej: "aviso-cambio-horario", "fu-prueba-24mayo").

## Contexto

Las páginas estáticas de FENIX (follow-up, avisos, broadcast) se sirven desde **Cloudflare Pages** via el repo:
- **Repo local:** `C:/Users/IVAN LAFUENTE/Projects/fenixkidsacademy-web/`
- **GitHub:** `ivanlafuentepy/fenixkidsacademy-web` (branch `master`)
- **URL pública:** `https://fenixkidsacademy-web.pages.dev/{slug}`

## Paso 1 — Preguntar qué tipo de página

Si Ivan no lo especificó en el prompt, preguntar:

1. **Aviso general** (mismo mensaje para todos, personalizado con nombre)
2. **Follow-up post-prueba** (mensajes distintos por familia, usar `/fusabado` en su lugar)

Si es aviso general → continuar aquí.
Si es follow-up → redirigir a `/fusabado`.

## Paso 2 — Definir audiencia y mensaje

Preguntar a Ivan (si no lo dijo ya):
1. ¿A quién va? (familias inscriptas, pruebas/leads, o ambos)
2. ¿Cuál es el mensaje? (se personaliza con el nombre de cada padre/madre)

## Paso 3 — Obtener datos de Airtable

Usar el endpoint de Railway para obtener los datos (NO curl directo a Airtable):

```bash
# FAMILIAS + PRUEBAS (todo junto)
curl -s "https://fenix-kids-agent-production.up.railway.app/api/alumnos" \
  -H "X-ADMIN-KEY: $ADMIN_API_KEY"
```

Leer `ADMIN_API_KEY` de la memoria `reference_railway_prod.md`.

### Agrupar datos

1. Parsear el JSON de alumnos
2. Agrupar por familia (usando `cell_padre` como key primario, `cell_madre` como fallback)
3. Separar en inscriptos (`es_prueba` = false/ausente) y pruebas (`es_prueba` = true)
4. Para cada familia extraer: padre, madre, cell_padre, cell_madre, hijos con edad

## Paso 4 — Generar HTML

Crear el HTML con estas características:

### Diseño
- Dark mode: fondo `#0a0a0a`, texto `#e0e0e0`, acento `#ff6b00`
- Mobile-first, max-width 800px
- Font: system fonts (-apple-system, etc.)

### Estructura
- **Header:** título + stats (familias/pruebas)
- **Preview del mensaje** (en bloque con borde naranja)
- **Sección FAMILIAS INSCRIPTAS** — cards con botones papá/mamá
- **Sección PRUEBAS/LEADS** — cards con botón del contacto registrado

### Cards
Cada card tiene:
- Nombre del padre (y madre si hay ambos)
- Hijos con badge de edad coloreado (verde=3-5, azul=6-8, naranja=9-12, gris=s/edad)
- Teléfonos
- **Botón azul** → wa.me del papá con mensaje personalizado
- **Botón rosa** → wa.me de la mamá con mensaje personalizado
- Si solo hay un contacto, un solo botón verde

### Links wa.me
- Normalizar teléfonos: quitar espacios/guiones, asegurar prefijo 595
- URL encode del mensaje con el nombre del padre/madre
- `https://wa.me/{TELEFONO}?text={MENSAJE_URL_ENCODED}`

### Tracking de enviados
- localStorage con key única por página (ej: `fenix-{slug}-sent`)
- Al hacer click en botón: se marca como enviado (opacidad 0.4 + ✓)
- **El botón SIGUE CLICKEABLE** después de marcado (nunca pointer-events: none)
- Contador fijo en esquina inferior derecha: "X/Y enviados"

## Paso 5 — Guardar HTML

```bash
# Guardar en AMBOS repos
cp pagina.html "C:/Users/IVAN LAFUENTE/Projects/fenixkidsacademy-web/{slug}.html"
cp pagina.html "C:/Users/IVAN LAFUENTE/Projects/fenix-kids-agent/static/{slug}.html"
```

## Paso 6 — Deploy a Cloudflare Pages

```bash
cd "C:/Users/IVAN LAFUENTE/Projects/fenixkidsacademy-web"
git add {slug}.html
git commit -m "feat: {descripción breve de la página}"
git push origin master
# IMPORTANTE: branch es MASTER, no main. Cloudflare escucha master.
```

Cloudflare Pages deploya automáticamente en ~30 segundos.

## Paso 7 — Reportar

Mostrar:
```
═══ Página generada ═══
Familias: [N] inscriptas + [N] pruebas
Links wa.me: [N] total
URL: https://fenixkidsacademy-web.pages.dev/{slug}
Deploy: Cloudflare Pages (automático ~30s)
```

## REGLAS

- **NUNCA** enviar mensajes automáticamente — solo generar la página con links
- **NUNCA** curl directo a Meta API — solo links wa.me
- **SIEMPRE** deployar via fenixkidsacademy-web → GitHub → Cloudflare Pages
- **NUNCA** deployar páginas estáticas via Railway (eso es para el agente)
- El HTML debe funcionar 100% standalone (sin JS externo, sin APIs, sin auth)
- Normalizar TODOS los teléfonos a formato 595XXXXXXXXX
