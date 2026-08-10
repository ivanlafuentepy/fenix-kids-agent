# Próxima sesión — primer contacto del Desafío FENIX

> Escrito el 2026-08-10 al cerrar la sesión del lanzamiento del Desafío.
> **El primer campus es el viernes 14, sábado 15 y domingo 16 de agosto.**

## Contexto: qué quedó funcionando anoche

El DESAFÍO FENIX (campus de 3 días) reemplazó a la clase de prueba. Ya está en producción:
precios que se calculan solos (350.000 hasta el jueves 23:59 / 550.000 desde el viernes,
+150.000 por hermano), el prompt de ventas, la elección de turnos post-pago con botones, el
`CONCEPTO=DESAFIO` en PAGOS, el afiche, y la web (`fenixkidsacademy.com` + la landing
`/desafio`). La lógica del campus vive en **`agent/desafio.py`** y, del lado web, en
`assets/campus.js`.

El WhatsApp público es **595971938655** (el `595971669832` está muerto).

---

## El bug que hay que arreglar primero

**Endpoint 595982790407, 2026-08-10 04:31.** El lead escribió *"Hola, quiero pagar con
tarjeta el Desafío FENIX"* (el texto que manda el botón de la web) y Aurora contestó el
saludo genérico + los botones viejos: `Info sobre clases · Reservar lugar · Hablar con Aurora`.

**Causa raíz:** `procesar_menu_lead` corre ANTES del brain, y en
[`agent/lead_menu.py:346`](../agent/lead_menu.py#L346) hace:

```python
if es_primer_contacto and not menu_estado:
    # manda SALUDO_AURORA + botones, sin mirar QUÉ dijo el lead
```

Se responde por el estado, no por el contenido. Por eso la instrucción que se agregó a
`config/prompts.yaml` ("viene de la web a pagar con tarjeta") **nunca se evalúa**: el mensaje
no llega al brain. Cualquier arreglo tiene que ser en el menú, no en el prompt.

---

## Los tres trabajos

### 1. "Quiero pagar con tarjeta" tiene su propio camino

Cuando el primer mensaje ya dice que quiere pagar con tarjeta, no hay nada que vender:

1. *"Hola! Te saluda Aurora 🌟 de Fenix Kids. Te paso la info para abonar con tarjeta."*
2. Pregunta **solo cuántos hijos** — nada de nombre ni edad.
3. Con la respuesta arma el link y lo manda.

El link ya se genera solo cuando la respuesta del agente contiene el CI bancario
([`main.py:4135`](../agent/main.py#L4135)) y abre el Pedido, que es lo que después dispara el
formulario y la reserva de los 3 días. **Ojo con el monto**: `monto_prueba_por_hijos_detallado`
lo saca del historial y si lo adivina NO manda link. Con "cuántos hijos" hay que decir el monto
explícito (`precio_desafio(hijos)` de `agent/desafio.py`), no dejarlo al parser.

### 2. El saludo de primer contacto pasa a ser el Desafío

`SALUDO_AURORA` (`lead_menu.py:38`) todavía cuenta la academia en general. Tiene que contar el
**campus de 3 días**, con el mismo relato de la web: una experiencia transformadora en La Casona
Lafuente, viernes descubre / sábado supera / domingo conquista, más de 3.000 m² frente al río.

- Mandar también **la imagen de La Casona**: `mundo-fenix/assets/mapa_casona.jpg` (en la web
  está como `assets/casona-mapa.jpg`, 1400px / 349 KB). Hay que copiarla a `static/` del agente
  para poder enviarla por WhatsApp.
- **Botones nuevos** (máx. 3, títulos ≤20 caracteres):
  `📅 Info y precios` · `🎯 Reservar lugar` · `📞 Agendar llamada`
  (reemplaza a "Hablar con Aurora"). Los ids viejos (`lead_info`, `lead_agendar`,
  `lead_aurora`) están mapeados en `_ID_A_OPCION` — si se cambian, revisar los handlers.

### 3. Flujo nuevo: agendar llamada

Al tocar `📞 Agendar llamada`:

1. Aurora: *"Perfecto, agendamos una llamada con el profe Iván. ¿A qué hora te viene bien?"*
   con **botones de horario**.
2. Elige horario → *"Listo, el profe Iván te contacta en breve. ¿Cuál es tu nombre?"*
3. Responde el nombre → a Iván (`ADMIN_PHONE` 595982790407) le llega un WhatsApp con
   **nombre + teléfono + horario elegido**.

**A definir con Iván:** las opciones de horario de los botones (Meta permite 3).
Sugerencia: `Ahora` · `Más tarde hoy` · `Mañana`.

Ya existe la tool `programar_llamada(hora_llamada)` en `TOOLS_IVAN`
(`agent/tools/llamada.py`) — **revisar si sirve tal cual antes de escribir algo nuevo.**

---

## Cómo probarlo

```bash
py -3 -m pytest tests/ -q          # hoy: 79 passed
py -3 -c "import agent.main"
```

- Reset del número de prueba: `POST /reset/{telefono}` con `X-ADMIN-KEY` — deja el número como
  lead nuevo (no borra la fila de ALUMNOS, solo le saca la marca FENIX).
- Probar desde un número que **no** sea el de Iván, o desde el suyo en modo padre.
- El primer contacto hay que probarlo con `/reset` cada vez: el saludo solo sale una vez
  (`menu_estado`).

**Sigue pendiente de anoche**: la prueba end-to-end real por WhatsApp (pago → formulario →
turnos → 3 reservas en Airtable con `CONCEPTO=DESAFIO`).

## Reglas que aplican

- `/pre-cambio` antes de tocar `lead_menu.py`, `main.py` o `prompts.yaml`; `/pre-deploy` antes
  de pushear. Un cambio por push.
- Los textos de precios son **funciones** (`texto_precios()`, `texto_hermanos()`), no
  constantes: el precio depende del día.
- La marca se escribe **FENIX**, sin tilde.
