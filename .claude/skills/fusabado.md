# /fusabado — Generar página de follow-up post-prueba

Recibís como argumento: $ARGUMENTS (fecha del sábado, ej: "16/5", "24/5", "2026-05-24").

## Paso 1 — Parsear fecha

Convertir el argumento a formato ISO (YYYY-MM-DD). Si solo tiene día/mes, asumir año 2026.
Ejemplos: "16/5" → "2026-05-16", "24/5" → "2026-05-24", "2026-05-24" → "2026-05-24".

Guardar como variable `$FECHA_ISO`.

## Paso 2 — Consultar Airtable PRUEBA FENIX

Leer `AIRTABLE_API_KEY` y `AIRTABLE_BASE_ID` del `.env` del proyecto.

```bash
curl -s -H "Authorization: Bearer $AIRTABLE_API_KEY" \
  "https://api.airtable.com/v0/$AIRTABLE_BASE_ID/PRUEBA%20FENIX?filterByFormula=AND(%7BFECHA+RESERVA%7D%3D'$FECHA_ISO')&fields%5B%5D=NOMBRE&fields%5B%5D=APELLIDO&fields%5B%5D=NOMBRE+HIJO&fields%5B%5D=APELLIDO+HIJO&fields%5B%5D=EDAD+HIJO&fields%5B%5D=TELEFONO&fields%5B%5D=PRESENTE&fields%5B%5D=HORA&fields%5B%5D=CONVERSION"
```

Si hay 0 resultados, reportar "No hay pruebas para esa fecha" y terminar.

## Paso 3 — Procesar datos

1. **Filtrar**: solo registros con `PRESENTE: true`
2. **Excluir INSCRIPTOS**: si un teléfono tiene CUALQUIER registro con `CONVERSION: "INSCRIPTO"`, excluir a toda la familia (ya están inscriptos, no necesitan FU de venta)
3. **Agrupar por teléfono** (mismo padre puede tener múltiples hijos)
4. Para cada familia extraer:
   - Nombre y apellido del padre
   - Lista de hijos con nombre y edad
   - Teléfono
   - Horario (turno)
5. **Clasificar edad** de cada hijo:
   - EDAD HIJO viene como "años,meses" (ej: "4,5" = 4 años 5 meses)
   - 3-5 años → rango "3-5"
   - 6-8 años → rango "6-8"  
   - 9-12 años → rango "9-12"
   - Sin edad → rango "general"
   - Si un padre tiene hijos en rangos distintos → "mixto"

## Paso 4 — Generar mensajes personalizados

Para cada familia, generar un mensaje de WhatsApp con esta estructura EXACTA:

### Bloque 1 — Saludo + pregunta abierta
```
Hola [NOMBRE_PADRE] 😊 Soy Iván, profe de FENIX Kids.

Quería agradecerte por haber venido a probar el sábado con [NOMBRE_HIJO]. Contame, ¿qué tal se sintió [NOMBRE_HIJO] después del entrenamiento? ¿Qué dijo? ¿Le gustó?
```

Si tiene múltiples hijos: "con [HIJO1] y [HIJO2]" y "¿qué tal se sintieron ... ¿Qué dijeron? ¿Les gustó?"

### Bloque 2 — Consejo de profe personalizado por edad

Escribir como consejo profesional desde la experiencia de Iván, NO como descripción de FENIX.

**3-5 años** (1 hijo):
```
Te aconsejo vivamente que sigas haciendo este tipo de actividad con [HIJO] al aire libre. Cada vez que puedas, llevá a [HIJO] al parque, hacele trepar árboles, subir murallas, hacer cosas que le desafíen. A esta edad eso le desarrolla muchísimo la coordinación, la confianza y la autoestima. La valentía se construye desde chiquitos superando desafíos reales.
```

**6-8 años** (1 hijo):
```
Te aconsejo vivamente que sigas fomentando este tipo de actividad con [HIJO]. A esta edad necesita desafíos físicos reales: trepar, saltar, correr, caerse y levantarse. Eso le desarrolla la confianza, la independencia y la capacidad de superar miedos. Es la mejor forma de canalizar toda esa energía de forma positiva.
```

**9-12 años** (1 hijo):
```
Te aconsejo vivamente que sigas fomentando este tipo de actividad con [HIJO]. A esta edad el entrenamiento funcional le desarrolla disciplina, fuerza mental y liderazgo. Es la etapa perfecta para construir hábitos saludables, desconectar de las pantallas y fortalecer la autoestima a través del esfuerzo real. Lo que construya ahora le queda para siempre.
```

**Mixto** (hijos en rangos distintos):
```
Te aconsejo vivamente que sigas haciendo este tipo de actividades con ellos. Cada uno a su edad necesita cosas distintas: los más chiquitos desarrollan coordinación y confianza a través del juego y los desafíos físicos, y los más grandes fortalecen la disciplina, la fuerza mental y hábitos saludables. La valentía y la autoestima se construyen superando desafíos reales, y eso es exactamente lo que hacemos en FENIX.
```

**General** (sin edad):
```
Te aconsejo vivamente que sigas fomentando este tipo de actividad con [HIJO]. El entrenamiento funcional al aire libre desarrolla la confianza, la coordinación y la autoestima de una forma que ninguna otra actividad logra. La valentía se construye desde chicos superando desafíos reales.
```

Para múltiples hijos del mismo rango, adaptar los pronombres: "llevalos", "haceles", "les desafíen", "les desarrolla", etc.

### Bloque 3 — Cierre comercial
```
Te cuento que estoy teniendo mucha demanda y la promoción que tenemos de 12 clases a 750.000 guaraníes sin matrícula en estos días ya estaré cerrando.

Si te interesa asegurar el lugar de [HIJO] con esa promo, avisame y te paso todos los datos 🙌

P.D: Las 12 clases que comprás con el paquete son sin vencimiento, solo cuando venís se descuentan 🎁
```

### Tono
- Humano, premium, emocional, profesional, natural
- NO agresivo en ventas
- Nombres de hijos: usar solo el PRIMER nombre
- Firmar como Iván (sin apellido)

## Paso 5 — Generar HTML

Leer `scripts/generar_fu_prueba.py` como REFERENCIA del estilo visual. Crear un NUEVO archivo HTML con:

- Header: "FENIX Kids — Follow-up Prueba [FECHA]"
- Stats: cantidad de familias y niños
- Leyenda de colores: verde=3-5, azul=6-8, naranja=9-12
- Cards para cada familia:
  - Nombre del padre + turno
  - Hijos con badge de edad coloreado
  - Teléfono
  - Preview del mensaje (primeros 150 chars)
  - Botón verde "Enviar mensaje por WhatsApp" → `https://wa.me/{TEL}?text={MSG_URL_ENCODED}`
- Diseño: dark mode, mobile-first, fondo #0a0a0a, acento #ff6b00
- Al hacer click en el botón: cambia a verde oscuro (#1a8a3e) y opacidad 0.7, pero **SIGUE CLICKEABLE** (nunca pointer-events: none)
- localStorage con key única por fecha para recordar cuáles se enviaron

Guardar en AMBOS repos:
```bash
cp static/fu-prueba-{slug}.html "C:/Users/IVAN LAFUENTE/Projects/fenixkidsacademy-web/fu-prueba-{slug}.html"
```

## Paso 6 — Deploy a Cloudflare Pages

Las páginas estáticas se sirven desde **Cloudflare Pages**, NO desde Railway.

```bash
cd "C:/Users/IVAN LAFUENTE/Projects/fenixkidsacademy-web"
git add fu-prueba-{slug}.html
git commit -m "feat: follow-up prueba {FECHA}"
git push origin master
```

Cloudflare Pages deploya automáticamente en ~30 segundos.
URL pública: `https://fenixkidsacademy-web.pages.dev/fu-prueba-{slug}`

## Paso 7 — Enviar link a Ivan

Leer `ADMIN_API_KEY` de la memoria `reference_railway_prod.md`.

```bash
curl -s -H "X-ADMIN-KEY: $ADMIN_API_KEY" \
  "https://fenix-kids-agent-production.up.railway.app/test-envio/595982790407?msg=URL_ENCODED_MESSAGE"
```

El mensaje debe incluir:
- Cantidad de familias y niños
- Cantidad de INSCRIPTOS excluidos
- Link directo a la página (URL de Cloudflare Pages)

**NUNCA** enviar via curl directo a Meta API — siempre usar el endpoint `/test-envio/` de Railway.

## Paso 8 — Reportar

Mostrar resumen en terminal:
```
═══ Follow-up Prueba [FECHA] ═══
Familias: [N] | Niños: [N] | Excluidos (inscriptos): [N]
URL: https://fenixkidsacademy-web.pages.dev/fu-prueba-{slug}
Deploy: Cloudflare Pages (automático ~30s)
```

## REGLAS

- **SOLO LECTURA en Airtable** — nunca modificar registros
- Solo incluir familias con PRESENTE=true
- Excluir familias con CONVERSION=INSCRIPTO
- Si un padre tiene hijos sin PRESENTE y otros con PRESENTE, incluir al padre pero solo mencionar los hijos que asistieron
- **NUNCA** enviar mensajes a los padres automáticamente — solo generar la página con links
- **NUNCA** usar WebFetch — solo curl via Bash
- **NUNCA** enviar via curl directo a Meta — siempre usar `/test-envio/` de Railway
