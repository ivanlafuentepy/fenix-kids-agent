up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# BITÁCORA DE SESIONES — FENIX KIDS AGENT

Registro de cada sesión de trabajo: qué pidió Ivan, qué se hizo.

---

## 2026-05-26 (sesión 4 — fix PRUEBA FENIX + QR + auditoría + docs)

**Ivan:** endpoint 595985175667 — por qué no cargó el nombre del papá en Airtable cuando registró el pago?
**Fenix:** Encontré el bug: _procesar_comprobante solo patcheaba CONVERSION=PAGO, nunca nombre/apellido. El guard "ya existe PRUEBA FENIX" abortaba sin actualizar datos. Fix: actualizar_prueba_fenix() patchea campos vacíos + envía QR.

**Ivan:** tb tiene que actualizar apellido del hijo... y fecha de nacimiento... pero en la tabla PRUEBA FENIX
**Fenix:** Agregado al fix. La función patchea NOMBRE, APELLIDO, NOMBRE HIJO, APELLIDO HIJO, FECHA NACIMIENTO solo si están vacíos.

**Ivan:** el QR se envió?
**Fenix:** No, el código de envío de QR estaba dentro del bloque que se abortaba. Arreglado.

**Ivan:** quiero campos QR RESERVA y QR ENVIADO en PRUEBA FENIX y RESERVAS FENIX
**Fenix:** Creados 4 campos por API de Airtable (url + checkbox en cada tabla). Código marca automáticamente al enviar QR.

**Ivan:** enviale el QR a Víctor
**Fenix:** Error: envié URL como texto sin preguntar. Después creé endpoint /enviar-qr/{telefono} con param ?destino= para preview. QR imagen enviado correctamente.

**Ivan:** necesito un sub agente que audite todas las conversaciones
**Fenix:** Investigué patrones CRM externos (BSWEN, Salesforce, KDnuggets). Creé scripts/auditoria_flujo.py con checks modulares. Primera ejecución: 64 leads, solo 1 completo.

**Ivan:** las docs de Obsidian se pueden perder si pierdo la compu
**Fenix:** Migré 28 docs de Obsidian a docs/ del repo. Se deja de usar Obsidian para este proyecto.

### Commits
- `b488492` fix(pagos): actualizar datos faltantes en PRUEBA FENIX post-formulario + tracking QR
- `63c0ec6` feat(qr): endpoint /enviar-qr/ + espejo Telegram "QR Reserva enviado"
- `cfd8619` fix(qr): agregar param ?destino= en /enviar-qr/ para preview
- `5b0d867` feat(audit): script de auditoría de flujo de leads con datos bancarios
- `b92f8ad` docs: migrar documentación de Obsidian a docs/ del repo

---

## 2026-05-25 (sesión 4 — organización y sesiones)

**Ivan:** yosoyfenix
**Fenix:** Briefing. 52 commits de drift detectados en FENIX_RESUMEN.md.

**Ivan:** El monolito ya lo hicimos, Dorita ya lo hicimos
**Fenix:** Tachados de pendientes. Quedan QR email + limpieza Airtable.

**Ivan:** ¿Por qué hay drift?
**Fenix:** Investigado: los cierres se ejecutaban pero no actualizaban FENIX_RESUMEN.md correctamente.

**Ivan:** ¿Por qué no se hace push con cada cierre?
**Fenix:** Agregado push automático al cierre (.claude/commands/cierre.md).

**Ivan:** Investigá cómo hacen los pro su cierre
**Fenix:** Investigación web: dual-layer (doc vivo + log append-only), ADRs, changelogs. Decisión: reestructurar docs/ con ARCHITECTURE.md + CHANGELOG.md + adr/.

**Ivan:** ¿Dónde están nuestras conversaciones crudas?
**Fenix:** Confusión inicial (conversaciones WhatsApp → "no se guardan" → finalmente encontradas en ~/.claude/projects/*.jsonl). Memoria creada para no confundirse de nuevo.

**Ivan:** Quiero aliases con nombres claros para mis alumnos
**Fenix:** Aliases en .bashrc: retomar-sesion, continuar-sesion, historial-sesion, nombrar-sesion, exportar-sesion.

**Ivan:** Haceme una guía de esto para principiantes
**Fenix:** Creado docs/GUIA-SESIONES-CLAUDE-CODE.md — problema, solución, paso a paso, ejemplos.

### Commits
- 9894013 docs: cierre sesión 2026-05-25 — organización sesiones y docs

---

## 2026-05-25 (sesión 5 — AGENTE BLUEPRINT CURSO IA)

**Ivan:** yosoyfenix
**Fenix:** Briefing. Estado en producción, 52 commits de drift.

**Ivan:** Necesito crear un agente para Curso IA, copia de Fenix. Y un subagente que documente todo paso a paso como manual/curso vendible.
**Fenix:** Plan Mode. Exploración completa de Fenix (31 módulos, 19.600 líneas). Diseño de plan con 8 fases. Decisiones: repo separado, main.py reescrito limpio, solo Meta, con QR+audios.

**Ivan:** El proyecto se llama AGENTE BLUEPRINT CURSO IA, alias AGENTEBLUE
**Fenix:** Nombre aplicado a CLAUDE.md, main.py, settings.json, aliases en .bashrc.

**Ivan:** Aplicar setup del prompt-maestro (memoria, hooks, commands)
**Fenix:** Creado: memory/ (3 archivos), .claude/commands/ (4 commands), hooks (SessionStart/End/PostToolUse/Stop), CLAUDE.local.md.

**Ivan:** Cada paso completado se escribe en el blueprint DETALLADAMENTE
**Fenix:** Blueprint 01-entorno-y-estructura.md escrito completo en Obsidian (10 pasos, errores comunes, checkpoint).

**Ivan:** No veo la carpeta en VS Code
**Fenix:** Encontrado projects.json de Project Manager, agregado proyecto. Reescrito el paso en prompt-maestro con instrucciones exactas.

**Ivan:** Lo de push y GitHub está mal explicado en el prompt-maestro
**Fenix:** Reescrita Sección 9 completa: Personal Access Token paso a paso, crear repo via curl, remote con token embebido, sin depender de gh CLI.

**Ivan:** Dame prompt para explicarle a cursos-ia los cambios
**Fenix:** Prompt generado con los 3 cambios del prompt-maestro.

### Commits (en este repo)
- Ninguno — los cambios fueron en curso-ia-agent y cursos-ia

### Commits (en curso-ia-agent)
- 85ce7f1 feat: estructura completa del agente + sistema profesional CC (pushed a GitHub)

---

## 2026-05-25 (sesión 3 — auditoría)

**Ivan:** yosoyfenix
**Fenix:** Briefing completo del estado del proyecto.

**Ivan:** Auditoría completa de Dorita, comparar migración con Fenix, qué tiene pendiente
**Fenix:** Exploración profunda de ambos proyectos. Creado FENIX VS DORITA 25-5-26.md en Obsidian — comparativa estructural, tools, hooks, pendientes P0/P1/P2 para Dorita.

**Ivan:** Auditoría completa de nuestra migración, estado actual, antes/después, lecciones
**Fenix:** Creado AUDITORIA FENIX POST MIGRACION 25-5-26.md en Obsidian — 559 líneas, 12 secciones: arquitectura antes/después, flujos detallados, comparativas costo/latencia/confiabilidad, cronología 5 fases, 10 lecciones + 8 errores, diagrama dependencias, métricas.

**Ivan:** Quiero leerlo acá
**Fenix:** Leído completo en terminal para revisión.

**Ivan:** Podemos decir que la migración fue completada y todo funciona bien?
**Fenix:** Arquitectura sí, pero faltaba verificar flujo end-to-end.

**Ivan:** Ya fue verificado y funciona
**Fenix:** Migración oficialmente completada y verificada. Estado actualizado.

### Commits
- (ninguno — sesión de documentación, sin cambios de código)

---

## 2026-05-24/25 (sesion larga)

**Ivan:** yosoyfenix, retomamos donde estamos
**Fenix:** Briefing completo, estado del proyecto, pendientes Paso 2

**Ivan:** Estoy probando como padre, como vemos los cambios de tools?
**Fenix:** Fetch de logs Railway + /conversacion. Tools muestran 0 en cada round — Haiku no las usa.

**Ivan:** El prompt de Ivan no tiene seccion HERRAMIENTAS
**Fenix:** Agregada seccion HERRAMIENTAS al final del prompt. Haiku genero respuestas truncadas. Revertido.

**Ivan:** Las tools reemplazan texto del prompt, no se suman
**Fenix:** Refactor prompt Ivan: 8854→5379 chars (-39%). Tools integradas en cada fase del flujo. Plan Mode.

**Ivan:** Nuevo mensaje de apertura + precios Plan Invierno + eliminar 9:30 + eliminar paquetes
**Fenix:** 13 archivos actualizados: prompts, tools, hooks, pagos, brain, reminders, info, disponibilidad, contenido_social, main, afiches. Plan Invierno deployado.

**Ivan:** Eliminar concepto papa entrena
**Fenix:** Eliminado frame JUNTOS, profe papas, gancho papa del prompt.

**Ivan:** Follow-up despues de afiche horarios
**Fenix:** Agregado "Te gustaria agendar un sabado?" despues de enviar imagen.

**Ivan:** Simplificar datos bancarios
**Fenix:** ALIAS 1604338 / Banco Itau / Ivan Lafuente en 3 archivos.

**Ivan:** CTA prueba/inscripcion en vez de "sabado inolvidable"
**Fenix:** Actualizado en afiche followup, CTA general y seguimientos.

**Ivan:** Aurora no usa tools, bloque HERRAMIENTAS tampoco funciona
**Fenix:** Eliminado bloque HERRAMIENTAS de Aurora. Tools ya estaban inline en cada seccion.

**Ivan:** Aurora de 7 tools a 4, quitar consultar/registrar del menu
**Fenix:** Eliminadas consultar_agendados, registrar_familia, registrar_hijo. Menu renumerado.

**Ivan:** Reagendar crea nueva reserva en vez de modificar!
**Fenix:** Varios intentos: borrar todas futuras (mal), borrar mismo dia (mal), PATCH existente (formula Airtable fallo). Solucion final: tool reagendar_reserva unica que cancela+crea en una llamada.

**Ivan:** Tool_choice auto no funciona, any con regex es fragil
**Fenix:** Investigacion Anthropic: auto/any/tool/none. Regex detection implementada y despues eliminada por fragil. Quedo en auto.

**Ivan:** Aurora muestra reservas pasadas! Caso Victor Quinonez
**Fenix:** Fix: IS_AFTER en Airtable + ZoneInfo America/Asuncion + doble check Python.

**Ivan:** date.today() en vez de ZoneInfo — esta en CLAUDE.md global!
**Fenix:** Corregido. Actualizada memoria checklist con incidentes de esta sesion.

**Ivan:** CHECKLIST.md existe y no lo ejecutaste ni una vez
**Fenix:** Actualizada memoria: es MI responsabilidad ejecutarla, no esperar que Ivan la pida.

**Ivan:** Guia completa del agente + guia tool use Anthropic
**Fenix:** AGENTE FENIX ESTRUCTURA.md + GUIA TOOL USE ANTHROPIC.md creados en Obsidian.

**Ivan:** QR check-in para asistencia
**Fenix:** FENIX QR CHECKIN.md creado: guia completa con flujo, codigo, fases de implementacion.

### Commits de la sesion (20+):
```
bda2336 fix: IS_AFTER incluir hoy — usar ayer como referencia
5845229 fix: usar timezone Paraguay para filtrar reservas futuras
73f25f1 fix: filtrar reservas futuras en Airtable + doble check en Python
4919408 fix: renumerar opciones menu Aurora
9c9e462 fix: quitar opcion ver lista agendados del menu Aurora
f74e46e refactor: Aurora de 7 tools a 4
bbd3d4a fix: eliminar regex de tool_choice
7e3cc54 fix: regex tool_choice matchea prefijos + Aurora confia en CONTEXTO
96dc960 feat: reagendar_reserva — tool unica para Aurora
a21cd87 fix: agendar_clase solo borra reservas del MISMO dia
ab89225 fix: agendar_clase borra reservas futuras antes de crear nueva
4d752cd feat: tool_choice=any cuando mensaje indica accion concreta
a190654 fix: agendar_clase actualiza reserva existente en vez de duplicar
d32e19a fix: mapear aurora -> NIXIE en AGENT_ACTUAL de LEADS FENIX
84de1a8 fix: Aurora — eliminar bloque HERRAMIENTAS separado
7b2df4c fix: Aurora reagendar DEBE cancelar antes de agendar
7b30bf2 fix: Aurora consulta reservas antes de ofrecer agendar
7c56d57 fix: CTA prueba/inscripcion en vez de "sabado inolvidable"
ea4bc83 fix: simplificar datos bancarios
0eccadf fix: agregar follow-up despues de afiche horarios
a0f43f9 fix: eliminar concepto papa entrena del prompt
c784343 fix: ajustar texto apertura — transformadoras, m2, 10 min del centro
46c2b2f feat: Plan Invierno — nuevos precios, horarios y apertura
8cb13ae refactor: ivan_prompt -40% con tools integradas en flujo
b3b8f36 Revert: agregar seccion HERRAMIENTAS al prompt de Ivan
f3ea19b fix: agregar seccion HERRAMIENTAS al prompt de Ivan (revertido)
```

---

## 2026-05-19

**Ivan:** "sacamos el prompt que el padre tb entrena" — sacar toda referencia a que el padre entrena junto al hijo
**Fenix:** hice checklist completo: grep en prompts.yaml (3 refs) + main.py (1 ref en mensaje de apertura). Presenté los 4 cambios a Ivan, aprobó. No se llegó a ejecutar — sesión corta.

### Commits
- (ninguno — sesión sin cambios de código)

---

## 2026-05-18 (sesión 2)

**Ivan:** FENIX no está usando el afiche combo hermanos, le pido precio hermanos y no me lo pasa (mostró imagen del Plan Hermanos FENIX)
**Fenix:** diagnostiqué con /endpoint — `_AFICHE_HERMANOS_PATH` estaba definido pero nunca usado. El afiche general se enviaba siempre. Haiku confundió "2" (cantidad hijos) con "2 años" (edad). Fix: nuevo detector `_padre_pregunta_hermanos()`, nueva función `_enviar_afiche_hermanos_y_followup()` con descuentos exactos del afiche (Paq 5: 30%/50% OFF, Paq 12: 40%/GRATIS). Hermanos prioriza sobre afiche general.

### Commits
- `8a7d279` feat: afiche hermanos — FENIX envía Plan Hermanos cuando piden precio de hermanos/2+ hijos

---

## 2026-05-18

**Ivan:** quiero una página web con mensajes de follow-up personalizados por edad para los papás que vinieron a prueba el sábado 16/5, con links de WhatsApp directos para enviar desde el celu
**Fenix:** consulté Airtable PRUEBA FENIX, filtré PRESENTE=true, excluí INSCRIPTO (5 familias). Generé 13 cards con mensajes personalizados por rango etario (3-5/6-8/9-12). Endpoint `/fu/{archivo}?key=ADMIN_KEY` en main.py. HTML dark mode con botones wa.me

**Ivan:** el mensaje no me gusta, quiero pregunta abierta + consejo de profe + promo 750k
**Fenix:** reescribí estructura: saludo → "¿qué tal se sintió?" → consejo por edad (trepar árboles, pantallas, etc.) → promo 12 clases 750k sin matrícula → P.D. sin vencimiento 🎁

**Ivan:** no me llega el mensaje por WhatsApp
**Fenix:** intenté curl directo a Meta (4 veces, 200 OK pero no entrega). Creé endpoint `/test-envio/{tel}` en Railway. Resulta que la ventana 24h estaba cerrada — Meta acepta pero no entrega. Después de que Ivan escribió al bot, el envío via Railway funcionó

**Ivan:** quiero un slash command /fusabado que haga esto automático
**Fenix:** creé skill en `.claude/skills/fusabado.md` con todo el flujo (Airtable → filtrar → mensajes → HTML → deploy → WhatsApp)

**Ivan:** quiero carpeta skills separada de commands
**Fenix:** creé `.claude/skills/` con endpoint.md y fusabado.md, proxies en commands/

**Ivan:** endpoint mi número, por qué no me responde cuando escribo "hola"
**Fenix:** diagnostiqué — admin está en modo secre por defecto (línea 2840 main.py). Mensajes no-comando se ignoran silenciosamente. "modo padre" ahora resetea todo + activa flujo padre

### Commits
- `38e8806` feat: página follow-up pruebas 16/mayo con wa.me personalizados por edad
- `5a5a3b8` debug: endpoint /test-envio/{tel} para diagnosticar envío desde Railway
- `eae86fa` fix: mensajes FU con pregunta abierta + consejo de profe + promo 750k
- `3b1f164` fix: FU mensaje ajustado — "venir a probar" + P.D. sin vencimiento 🎁
- `82e8963` fix: botón FU sigue clickeable después de enviado — solo cambia color
- `82bea0f` fix: FU excluye familias con CONVERSION=INSCRIPTO (5 removidas, quedan 13)
- `1199850` feat: "modo padre" ahora resetea todo + entra directo como padre nuevo

---

## 2026-05-15

**Ivan:** compartió video de ventas sobre método 4P (precio+oportunidad+presión+pregunta) y preguntó cómo aplicarlo a FENIX
**Fenix:** análisis de puntos fuertes y débiles del flujo actual vs las 4P

**Ivan:** compartió doc FENIX_System_Prompt_Ivan.md + tabla precios nuevos (prueba normal + promo hoy + paquetes 5/12 + familiares + remera)
**Fenix:** auditoría completa: 10 archivos a tocar, 5 contradicciones con prompt actual, 6 bugs potenciales identificados

**Ivan:** la remera NO tiene precio definido, NO va gratis con nada. Prueba multi-hijo: 120k/150k normal, 150k/180k promo. Paquete 12 x 3 hijos = 1.200.000 (no 1.500.000). Las 4P las maneja el CÓDIGO, no Claude. Rompehielos igual, objeciones en código.
**Fenix:** implementación completa: prompts.yaml (precios+paquetes+descuentos+reglas), main.py (interceptor 4P + msg_precios + MONTOS + alerta silencio), pagos.py (conceptos nuevos), airtable_client.py (conceptos 100k/180k). 2 afiches nuevos copiados a static/.

**Ivan:** AUDITORIA COMPLETA, no quiero bugs
**Fenix:** 3 rondas de auditoría. Bugs encontrados y corregidos: followup variable indefinida, CTA desactualizado, "promo"/"paquete" no en detector, prompt contradictorio "NUNCA des precios", regex fecha reserva no aceptaba "|", descuentos familiares faltaban en prompt.

**Ivan:** Claude tiene que PODER dar precios, lo que tiene prohibido es ALUCINAR e INVENTAR
**Fenix:** reescritura de reglas: "Podés dar precios SOLO los de la lista. NUNCA inventar." Eliminadas todas las prohibiciones contradictorias.

**Ivan:** si no sabe algo → "Te respondo en un minuto" + silencio + alerta a mi WhatsApp
**Fenix:** regla de silencio en prompt + detección en código + función _alertar_silencio_ivan (doble canal WA+Telegram)

**Ivan:** no dar precio en PARTE 3, primero enganchar. Precio solo cuando dice sí.
**Fenix:** PARTE 3 → "¿Te gustaría regalarte un sábado diferente?" FASE 2B → precio+promo+afiche automático

**Ivan:** demasiado texto después del afiche, no envíes multi-hijo
**Fenix:** msg_precios simplificado: solo 1 hijo + promo + paquetes en 1 línea

**Ivan:** endpoint 595973564545 — no carga fecha en Airtable
**Fenix:** bug encontrado: Claude escribía "📅 Sábado 16 de mayo | 11:00h" con pipe, regex solo aceptaba "a las". Fix: regex acepta ambos + break solo si fecha extraída. Registro corregido manualmente.

**Ivan:** Airtable conceptos F.PRUEBA 100MIL y 180MIL
**Fenix:** creados via API (typecast:true + borrado registros test)

### Commits
- `61e1cce` feat: nueva estructura precios + promo 4P + regla de silencio
- `7b2f41e` fix: regex fecha reserva no matcheaba formato "Sábado X | Yh"
- `18888fc` fix: PARTE 3 sin precio — primero enganchar, precio solo cuando dice sí
- `d1b54a4` fix: msg_precios post-afiche más corto — sin multi-hijo ni paquetes detallados

---

## 2026-05-12 (sesión 4 — noche)

**Ivan:** limpiemos el prompt, cuánto consume y cómo mejorar
**Fenix:** Análisis completo: ivan_prompt ~3,440 tokens. Desglose por sección. Plan: mover objeciones fáciles a código, comprimir prompt.

**Ivan:** las fáciles que no salgan desde código?
**Fenix:** 6 objeciones movidas a intercepción pre-Claude (duración, qué llevar, devolución, efectivo, ya transferí, alias). Detectores regex + respuestas fijas. 0 tokens.

**Ivan:** "lo voy a pensar" no es problema, atacamos con seguimiento
**Fenix:** Eliminada del prompt. Se maneja con followup al día siguiente.

**Ivan:** las difícil dejamos en el prompt
**Fenix:** Comprimidas: más de un hijo, planes, 3-4 años, diagnóstico. De respuestas literales a reglas cortas. FASE 1 literal eliminada ("el sistema envía automáticamente"). Resultado: -41% tokens (3,440 → 2,020).

**Ivan:** endpoint 595982790407 que puta respuesta es esa???
**Fenix:** FASE 1 NO tenía intercepción por código — lo inventé sin verificar. Lead recibió mensaje genérico de Haiku. Fix: mensaje de apertura fijo desde código.

**Ivan:** me sigue respondiendo una mierda!
**Fenix:** Segundo bug: condición `not historial` siempre False por early save (mensaje ya guardado). Fix: `len(historial) <= 1`.

**Ivan:** siempre decís no va a volver a pasar y pasa cada vez más seguido
**Fenix:** Creado CHECKLIST.md obligatorio: leer, grep dependencias, verificar cobertura con evidencia, simular impacto, presentar a Ivan. Comando "checklist" lo ejecuta.

**Ivan:** endpoint 595981980706 porque no cargo los datos a airtable!
**Fenix:** El padre escribió "22 Dic 2021" y el detector buscaba "/" o "-". No matcheaba. Fix: ahora detecta meses en español (ene, feb, mar...). Lead Nancy Segovia / Sebastián García cargado manualmente en PRUEBA FENIX.

**Commits:**
- e5b93da opt: -41% tokens Ivan — objeciones fáciles a código, prompt comprimido
- 66de57b fix: FASE 1 interceptada por código — mensaje apertura fijo sin Claude
- 579c54e fix: FASE 1 condición — historial tiene 1 msg por early save
- 15eed18 fix: formulario acepta fechas en texto — "22 Dic 2021" no tenía "/" ni "-"

---

## 2026-05-12 (sesión 3 — noche)

**Ivan:** necesito llevar estadísticas de cada anuncio, crear tabla ANUNCIOS FENIX en Airtable
**Fenix:** tabla ANUNCIOS FENIX creada con NOMBRE, META AD ID, TIPO, ESTADO, MONTO, etc. 2 anuncios cargados: Carrusel niño/hombre (52594358497413) + Giuli Equilibrio (52587952070813).

**Ivan:** ya tenés todo listo para rastrear los anuncios que entran?
**Fenix:** faltaba capturar `source_id` del referral Meta (el ad ID). Implementado flujo completo: meta.py captura source_id → memory.py guarda en DB → crear_lead() busca anuncio en Airtable y linkea automáticamente. Campo ANUNCIO (linked record) creado en LEADS FENIX.

**Ivan:** CONVERSACIONES y CIERRES deberían ser automáticos
**Fenix:** reemplazados campos manuales por Count (CONVERSACIONES) y Rollup (CIERRES). API de Airtable no soporta crear Count/Rollup → Ivan los creó desde la UI.

**Commits:**
- 7282d4e feat: rastreo automático de anuncio por lead — ad_source_id desde referral Meta

---

## 2026-05-12 (sesión 2 — tarde)

**Ivan:** historia de Fenix/[[SALSA SOUL/SALSA SOUL|Salsa Soul]]/Meta, desvinculé IG de FB pero no me acuerdo el siguiente paso
**Fenix:** guiado: faltaba conectar IG Fenix desde Business Suite de Salsa Soul. Creado `CONEXION FENIX - SALSA SOUL - META.md` en Obsidian con paso a paso completo + checklist. Actualizado MOC.

Sin commits (sesión sin cambios de código).

---

## 2026-05-12 (sesión 1 — madrugada)

**Ivan:** endpoint 595981149599... en vez de estar respondiendo así cuando no sabe qué hacer, que silencie y me avise
**Fenix:** detección spam/scam (links .buzz, "me dieron 800mil"). NO responde, silencia, alerta Telegram. Prompt injection también silencia.

**Ivan:** hacemos un MD de las conversaciones del 11/5
**Fenix:** all_phones.txt desactualizado (772 vs 998). Actualizado desde Airtable. Re-exportado: 66 conversaciones (no 4).

**Ivan:** ninguno agendó! (los labels decían "Agendó" cuando no pagaron)
**Fenix:** fix labels: "AGENDÓ ✅" solo si está en PRUEBA FENIX. "Datos enviados" si Ivan mandó banco pero no pagó.

**Ivan:** parece que el tema de la evaluación no está siendo bien aceptada
**Fenix:** análisis de 66 convos: "si es aceptado" asusta, transferir a cuenta personal + evaluación suena a estafa, [SISTEMA:] se mostraba al padre. Revert evaluación → clase de prueba.

**Ivan:** (comparte FENIX_GUION_PARQUE_v3_FINAL.md) tenemos un cambio a 360 grados
**Fenix:** REFRAME COMPLETO: prompt Ivan reescrito desde cero. Parque FENIX, papá+hijo juntos, 90mil no descuenta, sin menú dolor, sin evaluación. Limpieza total de basura en reminders.py, telegram_bridge.py. Eliminado código muerto.

**Ivan:** te gustaría agendar un sábado inolvidable para vos y tu hijo?
**Fenix:** frase ancla en TODOS los CTAs: prompt, afiche, reminders, followup.

**Ivan:** se va demasiado rápido a la agenda
**Fenix:** FASE 2 dividida en 3 partes: personalización por edad → gancho papá ("a vos también te entrenamos!") → cierre emocional → fechas solo si dice sí.

**Ivan:** [[EDITOR PRO MAX/REDES SOCIALES/Fenix Kids Academy|FENIX KIDS ACADEMY]] sigue siendo el nombre, el parque es el lugar
**Fenix:** corregido frame: "FENIX KIDS ACADEMY se desarrolla en el PARQUE FENIX".

**Ivan:** vincula todos los MDs de FENIX en Obsidian
**Fenix:** up:: agregado a 12 archivos de [[FENIX KIDS/CONVERSACIONES FENIX/CONVERSACIONES FENIX|CONVERSACIONES FENIX]] + 4 de raíz que faltaban. MOC actualizado.

**Commits:**
- c0b92c2 feat: detección spam/scam — silenciar + alertar
- 1b1f413 fix: revertir evaluación → clase de prueba + fix leak [SISTEMA:]
- 5a11c84 feat: PARQUE FENIX — reframe completo papá+hijo
- 5d27b88 fix: limpiar basura flujo anterior en reminders/telegram
- a760b5b feat: frase ancla "sábado inolvidable" en todos los CTAs
- 7caad16 fix: FASE 2 más lenta — personalización + gancho papá
- 96b98f2 fix: FENIX KIDS ACADEMY sigue siendo el nombre

---

## 2026-05-09

**Ivan:** "595982935412 le negó agendamiento en el día" — Aurora dijo que no se puede agendar para hoy.

**Fenix:** Prompt Aurora + Ivan: "SIEMPRE se puede agendar para el mismo día. INCLUIDO HOY si es sábado."

---

**Ivan:** "porque ese número en telegram no aparece con el nombre?" — topic de Verónica Martínez mostraba solo el teléfono.

**Fenix:** Agregué topic_telegram al debug endpoint, encontré topic_id=72, renombré a "Veronica Martinez" via API. Creé endpoint POST /restaurar-aurora/{tel}.

---

**Ivan:** "todos tenían reserva para hoy y a ninguno se les anotó" — Aurora confirmaba pero no creaba en Airtable.

**Fenix:** Bug: familias pre-existentes no tenían familia_id en DB local. Fix: fallback a buscar_familia_por_telefono (CELL LIMPIO). Creé reservas manuales para Yandry (Tito+Cami), Helena, Yessi (Lucas+Anita), Anto (Oli), Lujan (Thiago), David Meire (Demian).

---

**Ivan:** "PAGO CONFIRMADO PRUEBA 90.000 cuando son 150 y tres hijos" — Dirse Alcaraz.

**Fenix:** monto_prueba no detectaba "Monto: **150.000 Gs**". Nuevos patrones. Corregido en Airtable.

---

**Ivan:** "respondió qué onda, eso nunca" — falta de respeto.

**Fenix:** Prohibido "qué onda", "qué tal" en prompt. Siempre "Hola [nombre]! En qué te puedo ayudar?"

---

**Ivan:** "envió imagen del mapa y le volvió a cargar pago" — 595985770539.

**Fenix:** Cualquier imagen post "pago confirmado" ya no se trata como comprobante.

---

**Ivan:** "quiero comando ASISTENCIA por turno, automático"

**Fenix:** Comando `asis 9.30`/`asis 11`/`asis 15.30`. Lista numerada, respondés ok o números ausentes. Envío automático sábados al terminar turno. Campo PRESENTE en PRUEBA FENIX.

---

**Ivan:** "edad en años y meses, 3,5 = 3 años 5 meses"

**Fenix:** Fórmula Airtable actualizada en PRUEBA FENIX + campo EDAD creado en NIÑOS FENIX. Resumen muestra (3,5).

---

**Ivan:** "quiero que endpoint [nombre] busque por nombre"

**Fenix:** Directorio contactos_fenix.md en memoria: 50 familias + 25 pruebas FENIX.

---

**Commits de la sesión:**
- `4b03133` fix: Aurora no pone negritas en nombres
- `13e5921` fix: monto_prueba detecta "Monto: 150.000 Gs"
- `bcc53cd` fix: reagendamiento PRUEBA FENIX actualiza fecha
- `94dacf4` feat: intercepción pre-Claude horarios/precios/ubicación
- `44f39e7` fix: imagen post-pago no es comprobante
- `b7ede11` fix: prohibido "qué onda"
- `a8f0984` feat: endpoint /restaurar-aurora
- `9c8b469` fix: fallback familia por CELL LIMPIO
- `d70d743` fix: Ivan ofrece sábado corriente
- `faadc45` feat: debug con topic_telegram
- `4d69f53` fix: Aurora agenda hoy
- `7cd15ba` fix: resumen telegram con nombre padre
- `f83babe` feat: comando resumen telegram
- `e89c483` feat: edad años,meses
- `a42450f` fix: cambio hora sin fecha
- `dac67eb` feat: comando asistencia automático
- `269167d` feat: asis por turno
- `60382be` fix: asistencia safe split

---

## 2026-05-08 (sesión 2)

**Ivan:** "ENDPOINT 595981634024 PAGO 120, CONFIRMADO, PERO NO ESTA EN AIRTABLE" — padre mandó datos del formulario pero sin keywords ("nombre", "mamá"), sistema no lo detectó, no creó PRUEBA FENIX.

**Fenix:** Fix en detección: si pago+formulario ya confirmados, no exigir keywords. Creé manualmente Amira + Eladio Martinez Acosta en PRUEBA FENIX (sáb 16 mayo 15:30h, 120mil).

---

**Ivan:** "LE DIJO QUE ENTRENAMOS AL AIRE LIBRE SIEMPRE, LA LLUVIA SUMA... SI LLUEVE SE ENTRENA BAJO TECHO" — prompt decía "NUNCA inventar infraestructura" y Claude inventó que lluvia es parte de la experiencia.

**Fenix:** Prompt corregido: "Si llueve o hace frío se entrena BAJO TECHO dentro de La Casona (3000m2)".

---

**Ivan:** "PAGO CONFIRMADO — PRUEBA 90.000... tiene todos los datos de que es 120 mil y son dos" — regex monto tenía typo (ransferi vs ransfere) y no toleraba markdown.

**Fenix:** Fix regex en pagos.py: `Transfer(ir|encia)`, tolera `**markdown**`, patrón extra "120.000 Gs (prueba".

---

**Ivan:** "envia todo doble! afiche precio, texto precio, claude también..." — padre 595983139264, Claude tiraba toda la info junta ignorando POST-DIAGNÓSTICO.

**Fenix:** Implementé intercepción pre-Claude: si padre pregunta precio/horario/ubicación → código responde SIN llamar a Claude. Ahorra tokens, no duplica. Combinaciones funcionan.

---

**Ivan:** "595973686713 reagendó pero no cambió la reserva en Airtable"

**Fenix:** Christopher cambió de 9 a 16 mayo. Actualicé manualmente + agregué detección de reagendamiento: si Ivan confirma nueva fecha y ya hay PRUEBA FENIX → actualiza FECHA RESERVA/HORA.

---

**Ivan:** "necesito MD con todas las conversaciones por fecha"

**Fenix:** Script export_conversaciones_v2.py: descarga 772 teléfonos de prod, genera 7 MDs diarios (1-7 mayo, solo leads Ivan) + [[FENIX KIDS/CONVERSACIONES FENIX/CONVERSACIONES_RESERVAS|CONVERSACIONES_RESERVAS]].md cruzado con Airtable.

---

**Commits de la sesión:**
- `6f97ac1` fix: detección formulario sin keywords + respuesta con nombres + prompt lluvia
- `da3c621` fix: monto_prueba_por_hijos detecta "A transferir" y tolera markdown
- `a7ef473` fix: horarios envía afiche en vez de texto + refuerzo POST-DIAGNÓSTICO
- `94dacf4` feat: intercepción pre-Claude para horarios, precios y ubicación
- `bcc53cd` fix: reagendamiento PRUEBA FENIX actualiza fecha en Airtable

---

## 2026-05-01

**Ivan:** Necesitaba que las familias que escriben por WhatsApp se registren automáticamente en el sistema, y que los topics de Telegram caigan en el grupo correcto (FLIAS vs LEADS).

**Fenix:** Implementé auto-registro de familias por WhatsApp. Fix: topics Telegram se rutean directo al grupo correcto según si es familia o lead.

---

**Ivan:** Aurora estaba usando el nombre completo del padre en vez del apodo o primer nombre — sonaba robótico.

**Fenix:** Fix: Aurora usa apodo si tiene, sino solo primer nombre. Nunca nombre completo.

---

**Ivan:** "Hola Aurora" no funcionaba siempre. Necesitaba que /registro en Telegram mandara WhatsApp al padre y mostrara el mensaje exacto de Aurora.

**Fenix:** Fix "Hola Aurora" funciona siempre. /registro manda WhatsApp al padre (saluda por nombre si registrado). /fenix resetea conversación. Mensaje exacto de Aurora se muestra en Telegram.

---

**Ivan:** Topics duplicados en Telegram al migrar de grupo (LEADS a FLIAS).

**Fenix:** Fix: cerrar topic viejo al migrar. Asignar variante ANTES de detectar registro para evitar topic duplicado. Aurora saluda normal si reconoce, registra si no.

---

**Ivan:** Necesitaba un kill switch para frenar todo el agente en caso de emergencia.

**Fenix:** Implementé KILL SWITCH — variable AGENTE_PAUSADO en .env frena todo el procesamiento.

---

**Commits sesión 2026-05-01:**
- `be1b5c2` feat: auto-registro familias por WhatsApp + fix topic Telegram
- `52846eb` feat: KILL SWITCH — AGENTE_PAUSADO env var para frenar todo
- `31e68c8` fix: topic Telegram va directo al grupo correcto — familia=FLIAS, lead=LEADS
- `0522f35` fix: Aurora usa apodo o solo primer nombre, nunca nombre completo
- `389acf2` fix: Hola Aurora funciona siempre + /registro en Telegram
- `19abcb3` feat: /fenix en Telegram resetea conversación + /registro inicia Aurora
- `7fc93ce` fix: /registro manda WhatsApp al padre — saluda por nombre si registrado
- `17a47c4` fix: /registro muestra el mensaje exacto de Aurora en Telegram
- `fb59adf` fix: cerrar topic viejo en Telegram al migrar de grupo (LEADS→FLIAS)
- `c4996be` fix: asignar_variante ANTES de detectar registro — fix topic duplicado
- `602c137` debug: logging en /registro para diagnosticar búsqueda de familia
- `13690a9` fix: Aurora saluda normal si reconoce, registra si no reconoce

---

## 2026-05-02

**Ivan:** El seguimiento automático estaba molestando — desactivar temporalmente.

**Fenix:** Desactivé seguimiento automático.

---

**Ivan:** Al registrar un niño, la fecha de nacimiento no se guardaba bien en NIÑOS FENIX. Y al registrar padre/madre, no deducía quién era papá y quién mamá.

**Fenix:** Fix: fecha nacimiento se convierte a ISO antes de guardar. Fix: deducir papá/mamá del nombre y guardar en campos correctos.

---

**Ivan:** Aurora pedía confirmación extra antes de confirmar una reserva — innecesario. Además no podía cancelar ni reagendar reservas.

**Fenix:** Fix: Aurora confirma reserva directo, NUNCA pide confirmación extra. Feature: Aurora puede cancelar reservas en Airtable y ofrecer reagendar. Muestra reservas activas cuando padre elige opción 1. Menú Aurora actualizado (opción 1 = Agendar / cancelar clase).

---

**Commits sesión 2026-05-02:**
- `748d916` fix: desactivar seguimiento automático temporalmente
- `2ebee61` fix: convertir fecha nacimiento a ISO antes de guardar en NIÑOS FENIX
- `84f1c27` fix: deducir papá/mamá del nombre al registrar — guarda en campos correctos
- `2c95937` fix: Aurora confirma reserva directo, NUNCA pide confirmación extra
- `6f93293` fix: Aurora puede cancelar y reagendar reservas
- `dc75577` feat: Aurora cancela reservas en Airtable + ofrece reagendar
- `5eaa4df` fix: menú Aurora — opción 1 es Agendar / cancelar clase
- `d8fed38` feat: Aurora muestra reservas activas cuando padre elige opción 1
- `1947186` docs: cierre sesión 2026-05-02 — auto-registro Aurora + cancelar/reagendar

---

## 2026-05-03

**Ivan:** Bugs P0 en producción — nombre del hijo se extraía mal, Aurora repetía preguntas, descuento hermanos no se aplicaba bien.

**Fenix:** Fix nombre hijo, repetición de preguntas, descuento hermanos. Descuento ampliado a primos/sobrinos + mejor logging de alerta llamada.

---

**Ivan:** Diagnóstico tardaba mucho ("dame unos minutitos"). Pago necesitaba confirmación manual con botones admin — era cuello de botella.

**Fenix:** Diagnóstico corto e inmediato (sin delay). Pago auto-confirmado sin botones admin, notificación informativa al admin. Post-pago simplificado con link wa.me al admin ("te espero con [hijo] [fecha]"). Formulario post-pago en un solo mensaje, no uno por uno.

---

**Ivan:** Aurora rechazaba niños por edad. Nunca debería rechazar — siempre ofrecer clase de prueba.

**Fenix:** Fix: nunca rechazar por edad, siempre ofrecer clase de prueba para evaluar.

---

**Ivan:** Necesitaba afiche con precios escritos, promo trimestral, ahorro total. Ivan responde directo a los números — eliminar FASE 1.5.

**Fenix:** Afiche + precios con promo trimestral y ahorro total. Eliminé FASE 1.5 — Ivan responde directo, pregunta nombre al final. Afiche se espeja completo a Telegram (imagen + precios + CTA).

---

**Ivan:** Mensajes se perdían durante deploys. PRUEBA FENIX se creaba antes de tiempo. Keepalive mandaba demasiado.

**Fenix:** Eliminé cache dedup en memoria (causa raíz de pérdidas en deploy). Dedup registra DESPUÉS del procesamiento. PRUEBA FENIX solo 1 vez por lead, se crea DESPUÉS del formulario. CONVERSION=PAGO (no AGENDA). Keepalive reducido a 2 veces al día (9:00 y 22:00 PY).

---

**Ivan:** "2 niños de 8 y 11 años" — el sistema no detectaba la edad en esas frases. Y para familias de 3+ hijos necesitaba speech especial con plan 3x2.

**Fenix:** Fix: detectar edad en frases como "2 niños de 8 y 11 años". Speech especial familias 3+ hijos con plan 3x2 + mes de regalo. Math clara con tabla de números exactos para cada plan.

---

**Ivan:** No confirmar pago si padre dice "mañana te paso el comprobante". Link wa.me se enviaba antes del formulario. Contradicción hermanos en inscripción.

**Fenix:** Fix: no confirmar pago futuro. Link wa.me DESPUÉS del formulario. Eliminé contradicción hermanos.

---

**Ivan:** Webhook se perdía mensajes. Graceful shutdown + timeout Claude + dedup robusto.

**Fenix:** Webhook SÍNCRONO (como Dorita — nunca pierde mensajes). Fixes críticos: graceful shutdown + timeout Claude + dedup robusto.

---

**Commits sesión 2026-05-03:**
- `1bb2222` fix: P0 bugs — nombre hijo mal extraído, repetición de preguntas, descuento hermanos
- `e4efec7` fix: descuento incluye primos/sobrinos + mejor logging alerta llamada
- `de8ba95` feat: keepalive admin — mensaje cada 6h para mantener ventana WhatsApp abierta
- `6fb657c` feat: diagnóstico corto e inmediato — sin delay, sin dame unos minutitos
- `190c1a8` feat: pago auto-confirmado — sin botones admin, notificación informativa
- `7d74ab9` feat: post-pago simplificado + link wa.me al admin con mensaje de agradecimiento
- `4460f56` fix: formulario post-pago en un solo mensaje, no uno por uno
- `5f20f06` fix: link wa.me con formato correcto — "te espero con [hijo] [fecha]"
- `389a18d` fix: nunca rechazar por edad — siempre ofrecer clase de prueba para evaluar
- `8a2a860` feat: afiche + precios escritos con promo trimestral y ahorro total
- `7232567` fix: eliminar FASE 1.5 — Ivan responde directo a los números, pregunta nombre al final
- `93538e4` fix: espejar afiche completo en Telegram (imagen + precios + CTA)
- `8a24eed` fix: dedup registra DESPUÉS del procesamiento — no se pierden msgs en deploys
- `6d68560` fix: link wa.me se envía DESPUÉS del formulario, no al confirmar reserva
- `50c9e1e` fix: separar tablas — RESERVAS FENIX solo Aurora, PRUEBA FENIX solo Ivan
- `71f2704` feat: PRUEBA FENIX se crea post-formulario con datos completos + link LEAD
- `4165953` fix: max 2 veces pregunta edad/nombre + afiche siempre espeja a Telegram
- `5a1d7e3` fix: eliminar cache dedup en memoria — causa raíz de mensajes perdidos en deploys
- `791a0d6` fix: keepalive solo 2 veces al día — 9:00 y 22:00 PY
- `c8ca184` fix: afiche no se espejaba a Telegram — _tg_group no se pasaba a la función
- `7d09e53` fix: detectar edad en frases como "2 niños de 8 y 11 años"
- `d55f077` feat: speech especial para familias 3+ hijos — plan 3x2 + mes de regalo
- `0bca01a` fix: 3 fixes críticos — graceful shutdown + timeout Claude + dedup robusto
- `1eec297` fix: webhook SÍNCRONO como Dorita — NUNCA pierde mensajes
- `5b829fe` fix: PRUEBA FENIX solo 1 vez por lead + CONVERSION=PAGO no AGENDA
- `ec5e866` fix: PRUEBA FENIX se crea DESPUÉS del formulario, no con la confirmación
- `17644d1` fix: no confirmar pago si padre dice "mañana te paso el comprobante"
- `26b5100` fix: PRUEBA FENIX default CONVERSION=PAGO (era AGENDA)
- `7ca4768` fix: /agenda PAGO no AGENDA + eliminar contradicción hermanos en inscripción
- `959060f` fix: math 3 hijos clara — tabla con números exactos para cada plan
- `fbd2d70` docs: cierre sesion 2026-05-03 — analisis 78 leads + 25 fixes produccion

---

## 2026-05-04

**Ivan:** Síncrono causaba loop infinito de reintentos Meta — volver a async.

**Fenix:** Vuelto a async. CTA siempre menciona 90mil. No repetir diagnóstico cuando padre da nombre.

---

**Ivan:** Refactor completo de bienvenida y personalización por edad. Rompehielos con autoridad y promesas personalizadas.

**Fenix:** Nuevo mensaje de bienvenida + personalización por edad (refactor completo). Rompehielos 15 números + autoridad + promesas personalizadas. "registro" ya no activa Aurora — solo "aurora" explícito.

---

**Ivan:** Monto prueba siempre tiene que ser 90mil, pero el regex matcheaba "150.000" del afiche. Nombres falsos se filtraban mal ("Gracias", "De Dianosticaron").

**Fenix:** Fix monto prueba siempre 90mil. Ampliación blacklists nombres. Validación positiva con filtro morfológico + lista 1000+ nombres (ampliada a 3520). Nombre padre directo de Haiku sin buscar.

---

**Ivan:** Claude appendeaba preguntas automáticas que pisaban la respuesta. Comprobante se detectaba con texto cuando solo debería ser con imagen.

**Fenix:** Eliminé append automático de preguntas. Comprobante SOLO con imagen — texto NUNCA es comprobante. Chequear nombre+edad en mensaje ACTUAL antes de appendar.

---

**Ivan:** PRUEBA FENIX necesitaba campos completos: CONCEPTO, METODO DE PAGO, GENERO, REGISTRAR, INSCRIPCION, ORIGEN LEAD.

**Fenix:** Campos completos en PRUEBA FENIX. CONCEPTO con prefijo F.PRUEBA (sin espacio). ORIGEN LEAD como select (ANUNCIO default).

---

**Ivan:** Espejo nocturno a Telegram no funcionaba.

**Fenix:** Fix espejo nocturno + noche termina 6AM.

---

**Ivan:** Comprobante detection crasheaba. MONTO no existe en PRUEBA FENIX (422). CTA extra afiche sobraba.

**Fenix:** Fix crash tiene_keyword. Fix MONTO inexistente. CONCEPTO sin espacio (F.PRUEBA). Eliminé CTA extra.

---

**Ivan:** Mensajes se perdían. Clase NUNCA se suspende por lluvia.

**Fenix:** Early save (mensaje se guarda ANTES de procesar). Espejo imagen real a Telegram. NUNCA suspender clase por lluvia — se entrena adentro.

---

**Ivan:** Notificación de agenda usaba teléfono en vez de nombre del hijo. Link wa.me agenda sin personalizar.

**Fenix:** Notificación usa nombre del hijo. Link wa.me personalizado con nombre + hijos.

---

**Ivan:** Reducir costos API — Sonnet es muy caro para el flujo conversacional.

**Fenix:** Haiku en vez de Sonnet (reduce costos ~95%). Prompt compactado de 783 a 210 líneas. Historial reducido de 40 a 20 mensajes. Meta CAPI Business Messaging para atribución de conversiones.

---

**Commits sesión 2026-05-04:**
- `b257895` fix: volver a async — síncrono causaba loop infinito de reintentos Meta
- `069960b` fix: CTA siempre menciona 90mil + no repetir diagnóstico cuando padre da nombre
- `31a817d` feat: nuevo mensaje de bienvenida + personalización por edad (refactor completo)
- `5d2f322` feat: rompehielos 15 números + autoridad + promesas personalizadas
- `87dabb1` fix: "registro" ya no activa Aurora — solo "aurora" explícito
- `2ac78ac` fix: monto prueba siempre 90mil — el regex "150.000" matcheaba el afiche de precios
- `c738224` fix: ampliar blacklists nombres padre+hijo — "Gracias", "De Dianosticaron", etc
- `8c6ebdf` feat: validación positiva de nombres — filtro morfológico + lista 1000+ nombres
- `9fa92a8` feat: lista nombres ampliada a 3520 (fusión con lista generada)
- `281e265` fix: link wa.me busca nombre padre en Haiku si regex no lo encuentra
- `09bea11` fix: nombre padre directo de Haiku (datos_form), sin buscar
- `59a1cd2` fix: chequear nombre+edad en mensaje ACTUAL antes de appendar pregunta
- `4fbf879` fix: eliminar append automático de preguntas — pisaba respuesta de Claude
- `50361e7` fix: comprobante SOLO con imagen — texto NUNCA es comprobante
- `8251ff4` feat: PRUEBA FENIX campos completos — CONCEPTO, METODO DE PAGO, GENERO, REGISTRAR, INSCRIPCION
- `f667198` feat: ORIGEN LEAD (select) en PRUEBA FENIX — ANUNCIO default
- `04e3242` fix: CONCEPTO con prefijo F. — F. PRUEBA 90MIL/120MIL/150MIL
- `4ea0d6d` docs: cierre sesion 2026-05-04 — flujo final + validacion nombres + campos Airtable
- `f46b45a` fix: espejo nocturno a Telegram + noche termina 6AM
- `f196ece` docs: cierre sesión 2026-05-04 — espejo nocturno + wakeup 6AM
- `1eb02a6` fix: comprobante detection crasheaba por tiene_keyword undefined
- `8cf055b` fix: MONTO no existe en PRUEBA FENIX (422) + eliminar CTA extra afiche
- `1ea63a5` fix: CONCEPTO sin espacio — F.PRUEBA no F. PRUEBA
- `df68dd3` fix: nunca más perder mensajes — early save + espejo imagen real
- `623c51c` fix: NUNCA suspender clase por lluvia — se entrena adentro
- `0a8a7c6` docs: cierre sesion 2026-05-04 — fixes criticos produccion
- `4a9c10e` fix: notificación agenda Telegram usa nombre del hijo (no teléfono)
- `818bc74` feat: Meta CAPI Business Messaging — atribución de conversiones
- `c4eb891` fix: reducir costos API ~95% — Haiku en vez de Sonnet + prompt compactado + historial 20
- `e55e75a` docs: CLAUDE.md actualizado — Haiku 4.5 + prompt compactado + CAPI
- `9cbd423` fix: notificación agenda usaba teléfono cuando ninos sin nombre
- `9e56d2b` fix: link wa.me agenda con nombre + hijos personalizado
- `d6f17f1` docs: cierre sesion 2026-05-04 — Haiku CAPI notificaciones

---

## 2026-05-05

**Ivan:** FASE 2 autoridad necesitaba reescritura. Nombre/edad se preguntaba más de una vez.

**Fenix:** FASE 2 autoridad reescrita. Nombre/edad se pregunta una sola vez.

---

**Ivan:** Imágenes no llegaban a Telegram. Comprobante fallaba si lead mandaba imagen tarde. Aurora confirmaba reserva sin pago.

**Fenix:** Fix: enviar_media_a_topic no estaba importada (imágenes nunca llegaban). Fix comprobante tardío. Guard + prompt reforzado: NUNCA confirmar reserva sin pago.

---

**Ivan:** Monto multi-hijo no detectaba "niñas/nenas" ni contaba nombres con edad. Tokens auxiliares eran excesivos.

**Fenix:** Fix monto detecta niñas/nenas + cuenta nombres con edad. Reducción tokens: resumir 800→300, formulario 800→300, historial 30→15.

---

**Ivan:** Quería comando "resumen anuncios" — agendados y montos por fecha, que funcione con audio/Whisper.

**Fenix:** Comando `resumen anuncios` con filtro mes/hoy/ayer + desglose montos. Transcripción audio ANTES de comandos admin. Funciona con audio.

---

**Ivan:** Follow-up automático a leads. Aurora no debía tocar LEADS FENIX al confirmar reserva.

**Fenix:** Follow-up automático leads (loop diario 9AM PY). Fix: Aurora no toca LEADS FENIX al confirmar. Refactor: unificar FOLLOWUP en CONVERSION + campo SEGUIMIENTOS.

---

**Ivan:** Reserva NUNCA antes de pago. Formulario separado. Alias=CI. Campos PRUEBA FENIX ajustados.

**Fenix:** Guard reforzado: NUNCA confirmar reserva antes de pago. Formulario separado. Alias=CI. Campos NOMBRE/APELLIDO + METODO DE PAGO array. Limpieza campos inexistentes. CONCEPTO gratis = F.GRATIS. REGISTRAR=True al crear PRUEBA FENIX.

---

**Ivan:** Follow-up masivo fotos programado para mañana 6AM. Después cambió a hoy 6AM.

**Fenix:** Script follow-up masivo fotos. Reprogramado de mañana a hoy 6AM PY (oneshot).

---

**Ivan:** Extracción de nombres fallaba — datos bancarios se filtraban. Link al topic Telegram faltaba en notificación de pago. Precios post-afiche poco claros.

**Fenix:** Fix extracción nombres: precedencia ternario + filtrar datos bancarios de Haiku. Link al topic Telegram en notificación de pago. Mensaje precios post-afiche con formato claro (totales y % OFF).

---

**Commits sesión 2026-05-05:**
- `2247e3d` fix: FASE 2 autoridad reescrita + nombre/edad una sola vez
- `f89133d` fix: enviar_media_a_topic no estaba importada — imágenes nunca llegaban a Telegram
- `e0f4e19` fix: comprobante fallaba si lead mandaba imagen tarde
- `26f2af5` fix: NUNCA confirmar reserva sin pago — guard + prompt reforzado
- `6681aa1` fix: monto multi-hijo detecta niñas/nenas + cuenta nombres con edad
- `d27acc4` fix: reducir tokens auxiliares — resumir 800→300, formulario 800→300, historial 30→15
- `8dd6966` feat: comando 'resumen anuncios' — agendados y montos por fecha
- `8fba012` fix: transcripción audio ANTES de comandos admin
- `cd57495` fix: comando resumen anuncios flexible — funciona con audio/Whisper
- `686151c` feat: resumen anuncios mejorado — filtro mes/hoy/ayer + desglose montos
- `6a0c1cd` debug: logging detallado en transcripción de audio
- `88d353c` feat: follow-up automático leads — loop diario 9AM PY
- `7b8806e` fix: Aurora no toca LEADS FENIX al confirmar reserva
- `c809789` refactor: unificar FOLLOWUP en CONVERSION + campo SEGUIMIENTOS
- `012fff3` fix: NUNCA confirmar reserva antes de pago + formulario separado + alias=CI
- `cd431c3` fix: campos PRUEBA FENIX — NOMBRE/APELLIDO + METODO DE PAGO array
- `16835bf` fix: limpiar campos Airtable inexistentes en código
- `5c17e8e` fix: CONCEPTO gratis es F.GRATIS (no F.PRUEBA GRATIS)
- `5ff2613` feat: REGISTRAR=True al crear PRUEBA FENIX (lead pagó + formulario)
- `c96aeec` docs: cierre sesion 2026-05-05 — CONVERSION unificado + follow-up + fixes
- `a5fc6b5` feat: follow-up masivo fotos — 6AM PY 2026-05-06 oneshot
- `2f23e58` fix: follow-up fotos a 6AM PY HOY 2026-05-05 (no mañana)
- `4e0b092` docs: cierre sesion 2026-05-05 — follow-up fotos oneshot 6AM
- `9746cb3` fix: extracción nombres — precedencia ternario + filtrar datos bancarios de Haiku
- `f3d3611` feat: link al topic de Telegram en notificación de pago
- `538bda0` fix: mensaje de precios post-afiche — formato claro con totales y % OFF
- `f4171af` docs: cierre sesion 2026-05-05 — fix nombres + notif pago + precios

---

## 2026-05-06

**Ivan:** FASE 2B necesitaba reescritura. Seguimiento con ventana 24h.

**Fenix:** FASE 2B reescrita + seguimiento con ventana 24h.

---

**Ivan:** Afiche de horarios mezclado con precios. Necesitaba afiches separados. Precios simplificados: solo mensual + trimestral, énfasis 40% OFF. Quincenal como opción secundaria.

**Fenix:** Afiche horarios separado del de precios. Prompt horarios distinto al de precios. Simplificación: solo mensual + trimestral con 40% OFF. Quincenal como opción secundaria. Nuevo afiche precios con enfoque trimestral.

---

**Ivan:** Audio/imagen no se descargaban — problema con token de media.

**Fenix:** META_MEDIA_TOKEN: primero probé token Dorita, después confirmé que token Fenix (META_ACCESS_TOKEN) sí funciona para media.

---

**Ivan:** Resumen anuncios necesitaba gasto diario (200mil) + totales + diferencia. Endpoint /resumen-followup para trackear PAGO POST FU.

**Fenix:** Resumen anuncios con gasto diario 200mil + totales + diferencia. Endpoint /resumen-followup revisa 1ER FOLLOWUP masivo del 5 mayo. Distingue pagos ANTES vs DESPUÉS del FU.

---

**Ivan:** Afiche tiene que ir primero. Notificación de pago y agenda necesitaban link Telegram y "profe Ivan". Monto prueba leía mal cuando había frases genéricas.

**Fenix:** Afiche primero + link Telegram en notif pago. RESERVA COMPLETA usa datos Haiku + link Telegram. Notif agenda usa "profe Ivan" para leads. Fix monto_prueba: no cuenta frases genéricas, lee el precio que Ivan confirmó en la conversación.

---

**Ivan:** Timezone mal en resumen anuncios y FECHA CREACION. Espejo Telegram del 1ER FOLLOWUP masivo faltaba.

**Fenix:** Timezone Paraguay (UTC-3) en resumen anuncios. Convierte timestamps UTC viejos a fecha PY. Espejo Telegram del 1ER FOLLOWUP masivo de fotos.

---

**Ivan:** 2DO FOLLOWUP con video programado para 6AM PY. Necesitaba anotar si es 1ER o 2DO según historial.

**Fenix:** 2DO FOLLOWUP video 6AM PY. Anota 1ER o 2DO según si ya recibió masivo fotos. Ventana 24h abierta.

---

**Commits sesión 2026-05-06:**
- `2f4c4dc` fix: FASE 2B reescrita + seguimiento con ventana 24h
- `8053526` fix: afiche horarios separado + prompt horarios ≠ precios
- `78d365d` update: afiche precios nuevo con horarios + plan hermanos
- `319d70e` fix: no inventar infraestructura + responder SOLO lo que pidió
- `b1cc2a5` fix: simplificar precios — solo mensual + trimestral, énfasis en 40% OFF
- `d6d8604` fix: quincenal como opción secundaria en prompt
- `91b8886` update: afiche precios — enfoque trimestral 40% OFF
- `3312d80` fix: META_MEDIA_TOKEN para descarga de audio/imagen
- `3b6692a` fix: META_MEDIA_TOKEN usa token Dorita para descargar audio/media
- `3810a66` fix: usar META_ACCESS_TOKEN para media (token Fenix sí funciona)
- `1388b91` feat: resumen anuncios con gasto diario 200mil + totales + diferencia
- `fa91d71` feat: endpoint /resumen-followup + tracking PAGO POST FU
- `549b345` feat: /resumen-followup revisa 1ER FOLLOWUP masivo del 5 mayo
- `b336efb` fix: resumen-followup distingue pagos ANTES vs DESPUÉS del FU
- `e9b3037` docs: cierre sesion 2026-05-06 — FASE2B + audios + seguimiento + afiches
- `f85e295` fix: afiche primero + link Telegram en notif pago WhatsApp
- `4a1f333` fix: RESERVA COMPLETA usa datos Haiku + link Telegram
- `dd8dbbc` fix: notif agenda usa "profe Ivan" para leads + link Telegram
- `6a60514` fix: monto_prueba_por_hijos no cuenta frases genéricas como hijos
- `210abb4` fix: monto_prueba lee el precio que Ivan confirmó en la conversación
- `0a3ef80` fix: usar timezone Paraguay (UTC-3) en resumen anuncios y FECHA CREACION
- `45c709d` fix: resumen anuncios convierte timestamps UTC viejos a fecha PY
- `a5fae8a` fix: espejo Telegram del 1ER FOLLOWUP masivo de fotos
- `87a613b` feat: 2DO FOLLOWUP video 6AM PY — ventana 24h abierta
- `35fe727` fix: video FU anota 1ER o 2DO según si ya recibió masivo fotos
- `3ad17ab` docs: cierre sesion 2026-05-06 — video FU + espejo telegram

---

## 2026-05-07

**Ivan:** "resumen anuncios me trae así... xke si hoy es miércoles tdv y son las 23h" — el resumen mostraba jueves 7 cuando en PY era miércoles 6.

**Fenix:** El servidor Railway corre en UTC. A las 23h PY = 2am UTC del día siguiente. Fix: `_parsear_filtro_fecha` ahora usa `datetime.now(UTC-3).date()`. También cambié `FECHA CREACION` en `crear_lead` y `crear_prueba_fenix` a UTC-3. Agregué `_fecha_py()` para convertir timestamps UTC viejos al leer.

---

**Ivan:** "Paraguay es UTC-3" — me corrigió (yo dije -4).

**Fenix:** Corregido a UTC-3.

---

**Ivan:** "cuáles son mis comandos con FENIX por WhatsApp... si escribo comandos me trae una lista?"

**Fenix:** No existía un comando "comandos". Listé los existentes: `holayosoyfenix`, `modo alumno`, `resumen anuncios` (+ hoy/ayer/mes).

---

**Ivan:** "resumen reservas... me trae todas las reservas del sábado más cercano por horario. cuántos niños, nombre y edad"

**Fenix:** Creé comando `resumen reservas` — busca sábado próximo, consulta Aurora (RESERVAS FENIX via HORARIOS) y Fenix (PRUEBA FENIX), agrupa por turno 9:30/11:00/15:30.

---

**Ivan:** "y que separe tb las reservas de Aurora y de Fenix"

**Fenix:** Actualicé la función para mostrar secciones separadas: 🌳 Aurora y 🔥 Fenix por cada turno.

---

**Ivan:** "resumen reservas me trajo 0 en todo"

**Fenix:** FECHA RESERVA en PRUEBA FENIX se guarda como texto ("9 de mayo"), no ISO. La query buscaba "2026-05-09". Fix: buscar ambos formatos.

---

**Ivan:** "ahora me trajo aurora 0"

**Fenix:** `obtener_ninos_por_horario` buscaba `{FECHA}='2026-05-09'` pero FECHA en HORARIOS es tipo Date en Airtable — la comparación string no matchea. Fix: `DATESTR({FECHA})='2026-05-09'`. También arreglé `obtener_o_crear_horario`. Verificado local: trae datos.

---

**Ivan:** "veo que benja y lu quiñonez tiene doble reserva el sab 9... si ya tienen reserva ese dia no deberia de volver a cargar Aurora"

**Fenix:** Agregué guard de duplicados en `crear_reserva` — verifica si ya existe antes de crear. Borré los duplicados de Airtable (2 registros).

---

**Ivan:** "no me trae la edad de las reservas fenix... y agregale a lado del horario la edad media de los niños"

**Fenix:** Usé el campo EDAD HIJO (número) de PRUEBA FENIX para mostrar edad. Agregué promedio de edad por turno al lado del horario.

---

**Ivan:** "no creaste el campo 2do followup ni 3er, como sabemos a quién enviamos el 2do y 3ro?"

**Fenix:** Expliqué que el sistema usa SEGUIMIENTOS (número 0→3) + RESPONDIO FU1/FU2 (checkboxes). No hay campos separados por FU.

---

**Ivan:** "el tema es que en seguimiento no veo nadie con 2, cuando varios ya recibieron 2 seguimientos"

**Fenix:** Revisé la lógica completa del incremento. Posible timing issue o fallo silencioso del PATCH.

---

**Ivan:** "el tema es que no está siendo claro y fácil de seguir este sistema, debería de ser más simple"

**Fenix:** Propuse checkboxes separados. Ivan dijo que no le interesa ver desde Airtable, le interesa que los resúmenes sean claros. Creé comando `resumen followup` / `resumen fu` que muestra mapa completo: 🟡 en curso (con horas), ✅ respondieron, 💰 pagaron post-FU, ❌ descartados.

---

**Ivan:** "vamos a llevar un MD de todas nuestras conversaciones... tipo bitácora, con fecha"

**Fenix:** Creé BITACORA_SESIONES.md en Obsidian y actualicé el skill /cierre para incluir la carga de la bitácora.

---

---

**Ivan:** "enviame un link de wa.me a mi 595982790407... el link es para el 595982844548 y el texto en el link es: Buen dia! Te saluda Lujan de [[FENIX KIDS]]..."

**Fenix:** Generé el link wa.me codificado con el texto e IG link. Lo envié via API Meta al número de Ivan.

---

**Ivan:** "vamos a preparar el followup de hoy... a las 6am a todos los que escribieron en las últimas 24hs... y los que no tienen ventana abierta, links para lujan"

**Fenix:** Consulté Airtable con todos los leads no-PAGO (608). Clasifiqué: 139 con ventana abierta (escribieron últimas 24h), 467 ventana cerrada. Guardé JSONs locales.

---

**Ivan:** "primero armamos este fu y los links para lujan" + link de IG

**Fenix:** Creé `scripts/fu_grupo_a.py` — 139 mensajes directos desde FENIX a las 6am PY (pausa 1s entre mensajes). Creé `scripts/fu_grupo_b_lujan.py` — genera 467 links wa.me, los envía en 47 batches de 10 a Lujan (595982844548) cada 10min desde las 8am PY.

---

**Ivan:** "sacale los emojis para evitar problemas"

**Fenix:** Eliminé emojis 🌳💪 del texto de los mensajes en ambos scripts. Scripts corriendo en terminales propias.

---

**Commits (13 totales — 8 sesión + 5 arrastre):**

Sesión 2026-05-07:
- `0a3ef80` fix: timezone Paraguay (UTC-3) en resumen anuncios y FECHA CREACION
- `45c709d` fix: resumen anuncios convierte timestamps UTC viejos a fecha PY
- `23356d3` feat: comando "resumen reservas" — sábado próximo por turno
- `d94668e` feat: comando "resumen followup" por WhatsApp
- `6a3ca80` fix: resumen reservas busca FECHA RESERVA en formato texto
- `a30759a` fix: HORARIOS FECHA es tipo Date — usar DATESTR()
- `a35ec43` fix: guard duplicados en crear_reserva
- `831e6a4` feat: resumen reservas muestra edad + promedio por turno

Arrastre (comprometidos antes de la sesión, no registrados en cierre anterior):
- `f85e295` fix: afiche primero + link Telegram en notif pago WhatsApp
- `4a1f333` fix: RESERVA COMPLETA usa datos Haiku + link Telegram
- `dd8dbbc` fix: notif agenda usa "profe Ivan" para leads + link Telegram
- `6a60514` fix: monto_prueba_por_hijos no cuenta frases genéricas como hijos
- `210abb4` fix: monto_prueba lee el precio que Ivan confirmó en la conversación

Scripts no commiteados (archivos locales):
- `scripts/fu_grupo_a.py` — FU directo 139 leads (6am PY)
- `scripts/fu_grupo_b_lujan.py` — batches wa.me a Lujan (8am–15:50 PY)

---

## 2026-05-07 (sesión 2)

**Ivan:** corrió fu_grupo_a.py y todos dieron FAIL.

**Fenix:** Diagnóstico: script no mostraba el error de Meta. Modifiqué para imprimir código de error. Intenté usar heredoc bash en PowerShell (error mío — no funciona en PS). Creé scripts/test_meta.py. Error: HTTP 400 "Object with ID '1005063086033214' does not exist" — token local (EAAoBc8z...) diferente al de prod (EAAORCCzn...). Actualicé .env local con token correcto.

---

**Ivan:** "ESTAMOS DESFASADOS DE 5 HORAS!! PERDIMOS VENTANA CON MUCHOS!!"

**Fenix:** Confirmé que enviar ahora igual vale para los que tienen ventana abierta. Los cerrados dan error 131047 visible en el log. Instrucción: correr los dos scripts ahora.

---

**Ivan:** número de Lujan es 595981189205 (el script tenía 595982844548 = Ilse Estigarribia).

**Fenix:** Corregí LUJAN_PHONE en fu_grupo_b_lujan.py. El batch 1 ya había llegado a Ilse.

---

**Ivan:** "LE ESCRIBIS DICIENDO QUE TIENE SU LUGAR Y QUE TIENE QUE PAGAR, A UN DESCONOCIDO" — el followup_loop automático generaba mensajes Claude sin aprobación.

**Fenix:** Encontré el loop en main.py línea 392 (`_fire_and_forget(_followup_loop())`). Lo comenté. Pusheado a prod. FU de ahora en adelante: manual, preparado por Ivan a las 6am.

---

**Commits sesión 2:**
- `dc4db7d` fix: desactivar followup_loop automático — FU manual por Ivan a las 6am

---

## 2026-05-08

**Ivan:** "yosoyfenix" — inicio de sesión.

**Fenix:** Briefing completo. 0 drift, 14 archivos sin trackear (JSONs del FU masivo).

---

**Ivan:** "preparame un resumen de todas las funciones de FENIX y como lo construimos. [[FENIX KIDS/AGENTE FENIX PROYECTO|AGENTE FENIX PROYECTO]] MD"

**Fenix:** Exploré el proyecto completo (16 archivos Python, configs, scripts). Creé AGENTE FENIX PROYECTO.md en Obsidian y Desktop/PROYECTOS MD con: arquitectura, 11 módulos detallados, flujo completo de 31 pasos, cronología de construcción, variables de entorno, comandos.

---

**Ivan:** "endpoint 595973686713 analiza la conversacion completa... mira como envia dos veces precios, y al final no carga el nombre en airtable!!"

**Fenix:** Análisis: (1) Precios duplicados — dos bloques enviaban afiche (pre y post respuesta Claude). (2) PRUEBA FENIX sin datos — trigger era "Ivan dice los esperamos" que se disparó con "Ya está" del padre (7 chars, sin datos), guard bloqueó cuando llegaron datos reales.

---

**Ivan:** "tiene que buscar datos despues de haber pedido formulario, y cuando recibe decir muchas gracias por tus datos"

**Fenix:** Fix: trigger cambiado a "padre manda datos reales" (texto >20 chars + "/" + keywords nombre/mamá/hijo). Respuesta fija "Muchas gracias por tus datos!". Eliminado bloque B de afiche post-respuesta. Deployado.

---

**Ivan:** "haceme un MD [[BITACORA]] HISTORICO de lo fu que hicimos"

**Fenix:** Creé BITACORA FOLLOWUP FENIX.md en Desktop/PROYECTOS MD. 4 campañas documentadas: fotos 5/5, video 6/5, grupo A 7/5 (fallido), grupo B 7/5 (fallido). Texto exacto, números, media, resultados.

---

**Ivan:** "envia ese followup hoy a las 6am... a todos los que tienen ventana abierta"

**Fenix:** Creé scripts/fu_video_8mayo.py — video FU con pre-flight test al admin. Token verificado. Corriendo en background, espera hasta 6am PY.

---

**Ivan:** "carga en tu memoria, cada vez que preparamos un FU tenes que actualizar la bitacora de fu"

**Fenix:** Memoria guardada: feedback_bitacora_fu.md. Bitácora actualizada con campaña 5.

---

**Ivan:** "endpoint 595985296645 pago, se cargo sus datos perfecto... desaparecio de la tabla leads!!"

**Fenix:** Revisé Airtable: PRUEBA FENIX existía con datos, LEAD no. Busqué en código: no hay delete automático de leads. Lead fue borrado manualmente.

---

**Ivan:** "porque no lees y no haces el control de manera diligente!?!? ni miraste airtable!!!"

**Fenix:** Tenía razón — debí chequear Airtable directamente en vez de suponer.

---

**Ivan:** "carga de nuevo en leads, y carga los datos de biviana en prueba"

**Fenix:** Lead César recreado en LEADS + vinculado a PRUEBA. Para Biviana creé un registro NUEVO en vez de actualizar el existente (error mío). Ivan lo arregló manual.

---

**Ivan:** "tengo 21 reservas, pero mi resumen dice 17 para el sab 9 y hay 3 para el 16/5.. falta 1"

**Fenix:** El faltante era Christopher con HORA="11h" (mi error al crear). Normalización no matcheaba. Fix: HORA corregida a "11:00" + normalización mejorada (strip "h"/"hs").

---

**Ivan:** "cuando le escribo a fenix COMANDOS, me deberia de pasar los comandos que puedo usar"

**Fenix:** Agregué comando "comandos" que lista todos los comandos admin disponibles. Deployado.

---

**Commits sesión 2026-05-08:**
- `4f96c6e` fix: formulario post-pago crea PRUEBA FENIX con datos reales + elimina precios duplicados
- `07f959c` feat: comando "comandos" por WhatsApp + fix normalización HORA en resumen reservas

---

## 2026-05-10 (sesión 2)

**Ivan:** quiero reconocimiento facial de los niños en las fotos de clase
**Fenix:** Plan diseñado → AWS Rekognition elegido. Módulo `agent/face_recognition.py`, script `indexar_caras.py`, comando "fotos [turno]" y "registrar cara [nombre]". `descargar_media()` en provider Meta.

**Ivan:** cual es la pagina de aws?
**Fenix:** aws.amazon.com — guía paso a paso para crear IAM user + Access Key

**Ivan:** listo tengo las claves
**Fenix:** Cargadas en .env + Railway. Collection `fenix-kids` creada. Test OK.

**Ivan:** subi algunas fotos de niños a airtable
**Fenix:** Corrido `indexar_caras.py` — 7 caras indexadas (6 OK, 1 fallo formato imagen Lucas)

**Ivan:** tb tenemos que crear para PRUEBA FENIX y migrar al inscribir
**Fenix:** Campos FOTO+FACE_ID en PRUEBA FENIX. Script lee ambas tablas. Migración automática en `cargar familia`.

**Ivan:** quiero enviar mensajes personalizados a los padres del sábado
**Fenix:** Tabla SEGUIMIENTO FENIX creada (FECHA, NINO, PRUEBA, FAMILIA, MENSAJE, ENVIADO, DESCARTADO). Campo DESCARTADO agregado.

**Ivan:** pasame los mensajes con link wa.me
**Fenix:** 22 mensajes enviados al admin con link + botones ENVIADO/DESCARTADO. MD guardado en Obsidian.

**Ivan:** los links largos se cortaron, reenviar
**Fenix:** Reenviados como texto para copiar + link wa.me separado.

**Ivan:** dame un comando resumen asis
**Fenix:** Comando "resumen asis [fecha]" — presentes/ausentes por turno. Fix split() strings vacíos. Fix queries directas a reservas.

**Ivan:** quiero resumen prueba con asistencia, pagos, inscripción, seguimiento
**Fenix:** Comando "resumen prueba [fecha]" — agrupa por familia (padre + hijos), pagos desde link record PAGOS, inscripción desde FAMILIA FENIX en PAGOS, filtro FUENTE=FENIX.

**Ivan:** cargar familia no reconoce tildes
**Fenix:** Normalización unicodedata — "Veronica" matchea "Verónica".

**Ivan:** shift enter no funciona para nueva línea!
**Fenix:** Creado `~/.claude/keybindings.json` con `shift+enter` y `alt+enter` → `chat:newline`.

---

**Commits sesión 2026-05-10 (sesión 2):**
- `c051636` feat: reconocimiento facial de niños con AWS Rekognition
- `7d35b44` feat: reconocimiento facial en PRUEBA FENIX + migración al inscribir
- `b28d899` feat: comando "resumen asis" + tabla SEGUIMIENTO FENIX
- `6683509` fix: resumen asis usa queries directas a reservas
- `266312d` fix: resumen asis — proteger split() contra strings vacíos
- `50edd13` feat: botones seguimiento — ENVIADO/DESCARTADO en SEGUIMIENTO FENIX
- `e5e4826` fix: cargar familia ignora tildes al buscar nombre
- `2912a9e` feat: comandos resumen prueba + resumen seguimiento
- `6ea122e` fix: resumen prueba lee pagos de link record PAGOS
- `91050a4` fix: resumen prueba — nombre padre, monto inscripción, total recaudado
- `c277332` fix: resumen prueba busca pagos inscripción desde FAMILIA FENIX linked
- `4210230` fix: resumen prueba filtra pagos por FUENTE=FENIX

---

## 2026-05-11

**Ivan:** quiero refactorear el prompt de Ivan — frame evaluativo, 10 opciones, cupos, evaluación obligatoria
**Fenix:** Prompt nuevo aplicado paso a paso. Primero solo prompts.yaml, después texto hardcodeado, después normalización 15→10.

**Ivan:** se cayó el agente! no responde!
**Fenix:** El human-in-the-loop (en_evaluacion_manual en PostgreSQL) crasheaba silenciosamente. Revertido todo. Reimplementado paso a paso sin tocar la DB.

**Ivan:** quiero alerta cuando padre menciona diagnóstico
**Fenix:** detectar_diagnostico() con keywords → alerta Telegram con link topic. Sin pausar agente.

**Ivan:** dame /aprobado y /rechazado en Telegram
**Fenix:** Comandos en webhook Telegram. /aprobado envía EVALUACION_APROBADA via Claude. /rechazado envía EVALUACION_RECHAZADA.

**Ivan:** primero diagnóstico, después pregunta evaluación con costo, fechas solo si dice sí
**Fenix:** FASE 2B corregida en prompt: cierre = pregunta + costo 90mil. Fechas solo cuando padre confirma.

**Ivan:** sin cupos, solo fechas
**Fenix:** Cupos eliminados del prompt. Solo sábado más cercano + 3 turnos.

**Ivan:** renombrar conversaciones, mover al vault, reconstruir sesiones 1-6 mayo
**Fenix:** BITACORA SESIONES FENIX.md renombrado. CONVERSACIONES FENIX movida al Vault. Export auto al iniciar sesión. Sesiones 1-6 mayo reconstruidas desde git log.

---

**Commits sesión 2026-05-11:**
- `e25cd85` docs: cierre sesion 2026-05-10 — rekognition + seguimiento + comandos admin
- `11f5abf` feat(ivan): refactor a frame evaluativo + menú 10 opciones + cupos + human-in-the-loop
- `f2e4c8b` feat: detección leads retornantes (1-10 mayo) + mensaje especial evaluativo
- `054458c` fix: migrar columna en_evaluacion_manual en PostgreSQL
- `f2e0174` fix: proteger esta_en_evaluacion_manual con try/except
- `9c70247` hotfix: deshabilitar retornantes + eval manual temporalmente
- `7f52230` revert: volver a estado funcional pre-refactor evaluativo
- `63dca57` feat: prompt evaluativo — 10 opciones + frame evaluativo (solo prompt)
- `bdf8f77` feat: prueba → evaluación en todos los mensajes al padre
- `5df22f0` feat: normalización menú viejo 15→10 para leads en curso
- `caf241f` feat: alerta Telegram cuando padre menciona diagnóstico
- `b95e02e` fix: quitar cupos de horarios
- `884d69f` fix: FASE 2B cierra con pregunta, NO con fechas
- `528ac46` fix: cierre FASE 2B menciona costo 90mil
- `f6d50ca` feat: /aprobado y /rechazado en Telegram + link topic en alerta diagnóstico

---

## 2026-05-13

**Ivan:** Hacemos seguimiento a los que escribieron en las últimas 24h, tenemos dos mensajes (video + link IG)
**Fenix:** FU masivo video a 54 leads, 54/54 exitosos. Script `scripts/fu_video_13mayo.py`

**Ivan:** Donde encontraste los FU? Creá un MD específico para FU con toda la info
**Fenix:** Creada [[FENIX KIDS/GUIA FOLLOWUP FENIX|GUIA FOLLOWUP FENIX]].md en Obsidian con: cómo encontrar números, selección audiencia, historial campañas, media, registro Airtable, estadísticas. Movida [[FENIX KIDS/BITACORA FOLLOWUP FENIX|BITACORA FOLLOWUP FENIX]].md al Vault también

**Ivan:** Cómo hacer registro automático de los que escribieron en las últimas 24h
**Fenix:** Campo ULTIMO MENSAJE (DateTime) creado en LEADS FENIX. Se actualiza automático en cada mensaje entrante. Filtro ventana 24h directo desde Airtable

**Ivan:** endpoint 595984417866 — por qué cargó 90mil?? se inventó adicional por la mamá!!
**Fenix:** Bug `monto_prueba_por_hijos` no detectaba "Papá + 2 hijos: 120.000" → fallback 90mil. Fix: detectar monto junto a datos bancarios. Prompt: mamá incluida gratis

**Ivan:** endpoint 595971462496 — no le cargó datos del hijo
**Fenix:** RUC "3971573-6" activó formulario antes de recibir datos reales. Fix: guiones solo cuentan como fecha con formato dd-mm-yyyy

**Ivan:** El formulario dice "nene/a" — insultante! Que diga hijo/a con emojis diferentes
**Fenix:** Formulario: 👤 padre, 👦 hijo, 🎂 fecha nac. NUNCA "nene/a"

**Ivan:** endpoint 595992287742 — cobró mamá+2 hijos 150mil! Los padres no pagan!
**Fenix:** Precios reescritos: "1 hijo → 90mil TOTAL, 2 hijos → 120mil TOTAL". Padres gratis. Eliminado "papá + hijo" de todo el sistema

**Ivan:** endpoint 595994158680 — inventó 210mil (90+120)! Precios TOTAL no por hijo!
**Fenix:** Regla explícita: "NUNCA sumar precios individuales. NUNCA desglosar por hijo"

**Ivan:** Además pasó plan mensual sin trimestral
**Fenix:** Si preguntan planes → solo "te paso un afiche". NUNCA dar precios de planes

**Ivan:** Y apura al padre a decidir, no respeta su intención
**Fenix:** Reescrito estilo: "Esto es CONVERSACIÓN no pitch. Si pregunta algo, respondé ESO. Si quiere pensar, dejalo"

**Ivan:** endpoint 595976403990 — "el pibe" a una nena que se llama Coti!
**Fenix:** Prohibido: pibe, piba, nene, nena, chico, chica, campeón, crack. Siempre "tu hijo" o el nombre

**Ivan:** endpoint 595984720482 — dijo 90mil por sábado venís cuando quieras!
**Fenix:** Clase de PRUEBA, no pase suelto. NUNCA "venís cuando quieras sin compromiso"

**Ivan:** endpoint fernando zayas — que pase total agendados sin nombres, incluir prueba
**Fenix:** Aurora muestra solo "7 agendados" por horario, sin nombres, sumando inscriptos + prueba

### Commits de la sesión
- `5716099` feat: ULTIMO MENSAJE en Airtable — tracking automático ventana 24h
- `f560858` fix: monto multi-hijo + mamá incluida sin costo adicional
- `f60827b` fix: revertir monto multi-hijo — solo primer hijo lleva monto
- `eba19bc` fix: convertir fecha reserva a ISO
- `f35e249` fix: RUC con guión no debe activar formulario completo
- `0dd8bf9` fix: formulario post-pago — formato exacto con emojis
- `37c1fed` fix: precios por HIJOS, padres entran gratis
- `f7e6c4d` fix: notificaciones Telegram — pago solo tipo+link
- `70ac5c8` fix: precios TOTAL no por hijo — NUNCA sumar
- `2054cc7` fix: NUNCA dar precios de planes — siempre afiche
- `a4f47b9` fix: conversación no pitch — no apurar
- `1e29887` fix: NUNCA pibe/nene/chico/campeón
- `3e92c29` fix: clase de PRUEBA no pase suelto
- `bf015d5` fix: Aurora solo total agendados sin nombres
- `2a565d8` fix: solo total agendados sin desglose
- `63ae665` feat: resumen anuncios con leads totales, % conversión, media por día
- `e01a0be` fix: espacio entre días en resumen anuncios
- `37f5755` fix: resumen mayo desde el 3
- `270d116` feat: comandos Telegram en menú admin
- `0affb85` feat: resumen diario 8AM PY — anuncios + reservas automático
- `993421f` fix: "quiero hablarlo con mi esposa" no es pedido de llamada

**Ivan:** Que el resumen anuncios muestre leads totales, % conversión, media por día
**Fenix:** Resumen reescrito con header + leads por día + % + desglose

**Ivan:** Espacio entre días, sacar 1-2 mayo, total gastado 11x200
**Fenix:** Espacio agregado, mayo desde el 3

**Ivan:** Agregá comandos de Telegram al menú
**Fenix:** Sección Telegram con /silenciar, /reactivar, /aprobado, etc.

**Ivan:** Enviame todos los días a las 8AM resumen anuncios y reservas
**Fenix:** Loop diario 8AM PY reemplaza keepalive, envía ambos resúmenes

**Ivan:** endpoint 595972139612 — "hablarlo con mi esposa" activó alerta de llamada
**Fenix:** Regex restringido: "hablar" solo matchea con vos/usted/ivan/por teléfono

**Ivan:** Vinculá archivos sueltos de conversaciones en Obsidian
**Fenix:** up:: agregado a 11/05 y 12/05, MOC con links individuales

---

## 2026-05-15 (sesión 2)

**Ivan:** Nuevo campo MONTO en PRUEBA FENIX, concepto por tipo de compra
**Fenix:** MONTO numérico + CONCEPTO: PRUEBA 1HIJO/2HIJOS/3HIJOS, PAQUETE5, PAQUETE12, FENIXMAMA

**Ivan:** Endpoint para marcar PAGO PROMOMADRE a los que pagaron
**Fenix:** Endpoint marcar-pago-promomadre, auditoría cruzada Airtable vs PostgreSQL, 7 pagos reales confirmados, 3 falsos revertidos

**Ivan:** Comando promo madre con detalle de pagos
**Fenix:** Línea Pagaron + nombre + link Telegram + teléfono de cada lead

**Ivan:** Alertas de llamada no llegan a WhatsApp
**Fenix:** Alertas iban a ADMIN_PHONE (mismo número bot). Corregido. Link Telegram incluido.

**Ivan:** Formulario dice "nene/a"
**Fenix:** Cambiado a "tu hijo/a"

**Ivan:** Padre 595994468797 bloqueado, no le responde
**Fenix:** "quiero" + "promo" lo mandó al handler de promo madre (350k en vez de 100k). Promo madre DESACTIVADA con flag.

**Ivan:** Precios sin aclarar cantidad de hijos
**Fenix:** msg_precios ahora muestra 1 hijo y 2 hijos separado

**Ivan:** Formulario pide 2 hijos cuando pagó por 1
**Fenix:** Regla en prompt: cantidad de hijos según monto pagado, no según mención

**Ivan:** Cargar FENIXMAMA en FAMILIAS, NIÑOS, RESERVAS
**Fenix:** 7 familias creadas con papa/mama en campos correctos + niños + reservas sáb 16/5 + vinculación LEADS/PRUEBA/PAGOS

**Ivan:** Promo madre anotó como PAQUETE en vez de FENIXMAMA
**Fenix:** Corregidos uno a uno: 595982419803 (duplicado borrado), 595971886648 (2 hijos corregidos)

**Ivan:** Lista agendados muestra 0 — son 41
**Fenix:** Fechas PRUEBA FENIX en 3 formatos (ISO, "16 de mayo", "16/5/26"). Código solo busca ISO. PENDIENTE normalizar.

**Ivan:** Número 595971389662 no es mío, delirio
**Fenix:** Error mío al interpretar respuesta. Alertas corregidas a ADMIN_PHONE 595982790407.

### Commits sesión
```
8cac506 feat: nuevo campo MONTO + concepto por tipo de compra en PRUEBA FENIX
52aeae6 feat: endpoint marcar-pago-promomadre + auto-mark al pagar promo madre
a191a65 fix: revertir PAGO PROMOMADRE mal marcado + endpoint correcto
b526ace feat: comando "promo madre" ahora muestra línea Pagaron con PAGO PROMOMADRE
c51a8d1 feat: endpoint auditoria-promomadre — cruza Airtable vs historial PostgreSQL
61ee8e5 fix: alertas llamada/silencio van a números personales de Ivan, no al bot
c2ca886 feat: alertas llamada/silencio incluyen link al topic de Telegram del lead
68add9b feat: comando promo madre muestra nombre + link Telegram de cada lead que pagó
ed9c354 fix: formulario dice "tu hijo/a" en vez de "nene/a"
4cc3c7e feat: endpoint fix-prueba-promomadre
4ce3cab feat: comando promo madre muestra teléfono debajo del link de Telegram
54d94eb feat: desactivar promo madre — flag _PROMO_MADRE_ACTIVA=False
335d391 fix: msg_precios aclara precio por 1 hijo y 2 hijos separado
9522ea3 fix: formulario post-pago pide hijos segun monto pagado, no segun mencion
8cdc32e fix: alertas llamada/silencio van a ADMIN_PHONE (595982790407)
56b11a6 feat: comando "resumen flias" — nombre hijo | nombre padre + link wa.me por turno
ae4b53d fix: resumen flias con emojis rotativos diferentes por cada niño
96c87d3 feat: INSCRIPTO checkbox en PRUEBA FENIX — excluye de conteo agendados
```

**Ivan:** Fechas PRUEBA FENIX en 3 formatos, lista agendados no cuenta bien
**Fenix:** Normalizadas todas a ISO en Airtable (35 registros)

**Ivan:** Haceme comando "resumen flias" con nombre hijo + padre + link wa.me
**Fenix:** Nuevo comando con emojis rotativos, busca familia para inscriptos

**Ivan:** Se mezclan reservas de familias con pruebas, se cuentan doble
**Fenix:** Checkbox INSCRIPTO en PRUEBA FENIX. 9 FENIXMAMA marcados. Excluidos del conteo.

---

## 2026-05-16

**Ivan:** Una mamá quiso agendar para hoy y no le mostraba el sábado de hoy
**Fenix:** Fix en brain.py: `>=` en vez de `>` para incluir sábado corriente en fechas disponibles

**Ivan:** Comando nuevo PRESENTE nombre para cargar asistencia individual
**Fenix:** Comando PRESENTE nombre (inscriptos) y PRESENTE PRUEBA nombre (pruebas). Si no tiene reserva, crea una y marca presente. Turno deducido por hora actual.

**Ivan:** endpoint 595971961717 reagendó, creó registro sin nombre con 150mil
**Fenix:** Fix reagendamiento: ahora solo actualiza FECHA RESERVA/HORA en existentes, no crea nuevo. Notifica admin por WhatsApp. Guard en formulario previene duplicados post-redeploy. Corregido Airtable manualmente.

**Ivan:** Reconocimiento facial tb para PRUEBA FENIX
**Fenix:** `registrar cara` busca en NIÑOS + PRUEBA FENIX. Campo NINO FENIX (linked record) creado en PRUEBA. Al migrar con `cargar familia` se vincula automáticamente.

**Ivan:** Diana Jara, Carolina Benitez, Erica Bogado no tienen hijos vinculados
**Fenix:** Vinculados manualmente: Paula León Jara, Horacio Gonzalez, Tomas Benjamin Bogado → NINO FENIX + INSCRIPTO

**Ivan:** Catalina y Ernesto Galeano tienen reserva doble (11 y 15:30)
**Fenix:** Borradas reservas 11:00. Agregada alerta admin cuando se detecta reserva doble.

**Ivan:** En lista asis aparecen niños dobles (NIÑOS + PRUEBA)
**Fenix:** Dedup: si ya está como inscripto no lo trae de PRUEBA. También filtra INSCRIPTO=true.

**Ivan:** Con asis hora, poder cargar nombres extra que no están en la lista
**Fenix:** Después de `asis 9.30`, se pueden escribir nombres (coma o línea) → crea reserva + marca presente. Se sale del modo después de una carga.

**Ivan:** Que no haga problemas por tildes ni nombres incompletos
**Fenix:** Match por palabras: todas las palabras del input deben estar en el nombre completo. Sin tildes, case insensitive.

**Ivan:** Campo AUSENTE + mostrar ✅/❌ en la lista
**Fenix:** Campo AUSENTE (checkbox) creado en RESERVAS y PRUEBA FENIX. Al marcar ausentes se pone AUSENTE=true. Lista muestra ✅/❌ si ya fue cargada.

### Commits de la sesión
```
e60dc6d fix: incluir sábado corriente en fechas disponibles (>=, no >)
a8ca483 feat: comando "PRESENTE nombre" — marca asistencia individual por nombre
5f0a7a8 feat: PRESENTE separado — sin prefijo busca inscriptos, PRESENTE PRUEBA busca en pruebas
887015e feat: PRESENTE crea reserva automática si niño inscripto no reservó para hoy
3ac4be1 fix: reagendamiento PRUEBA FENIX — solo actualiza fecha, no crea registro nuevo
24e14cc feat: registrar cara busca en NIÑOS + PRUEBA FENIX (migración ya existía)
a99d49e feat: alerta admin cuando se detecta reserva doble (mismo niño, mismo día, otro horario)
6b59af5 fix: asistencia no muestra duplicados — si niño está en NIÑOS ya no lo trae de PRUEBA
a39c226 feat: al migrar PRUEBA→NIÑOS, vincula registro PRUEBA FENIX con NIÑO FENIX (linked record)
ea8e4ed feat: asistencia acepta nombres extra — crea reserva + marca presente para niños fuera de lista
fc7badb fix: match por palabras — 'Enzo Echeverz' matchea 'Enzo Manuel Echeverz Golin'
4791083 fix: modo asistencia se cierra después de cargar nombres extra (una sola vez)
013367a feat: asistencia muestra ✅/❌ si ya fue cargada + marca AUSENTE en Airtable
```

---

## 2026-05-16/17

**Ivan:** endpoint 595991278888 — no tiene sentido que anote 90k en Airtable cuando le dijo 150k
**Fenix:** Análisis de monto_prueba_por_hijos. Bug: afiche con "Prueba: 90.000 Gs" matcheaba regex antes del monto real. Fix: skip afiches + nuevos patrones.

**Ivan:** cargale reserva para el próximo sábado 15:30
**Fenix:** Cargados 2 registros PRUEBA FENIX (Matheo + Hannah Rojas) para 24/5 15:30h.

**Ivan:** registrar cara con nombre parcial me muestra lista numerada para elegir
**Fenix:** Implementado: múltiples matches → lista 1-N, admin responde número, espera foto.

**Ivan:** quiero enviar la foto ya con el comando, todo de una
**Fenix:** Caption de imagen se pasa como campo. Si mandás foto con caption "registrar cara nombre" procesa directo.

**Ivan:** no encontró a César (tiene acento)
**Fenix:** Búsqueda tolerante a acentos: genera variantes cesar/césar/cesár.

**Ivan:** puse max lee y no encontró (tiene más nombres entre medio)
**Fenix:** Multi-palabra: busca cada palabra por separado en NOMBRE + APELLIDO de ambas tablas.

**Ivan:** busca solo en NIÑOS, no en PRUEBA
**Fenix:** Ahora busca en NIÑOS + PRUEBA simultáneamente y muestra lista combinada.

**Ivan:** no subió la foto como attachment en Airtable
**Fenix:** Nueva función subir_attachment_airtable (base64 a content.airtable.com). Campo FOTO se llena al registrar cara.

### Commits
```
7d89acb fix: monto_prueba_por_hijos matcheaba 90k del afiche en vez del monto real acordado
4e8c739 feat: registrar cara con nombre parcial muestra lista numerada para seleccionar
06318d8 feat: registrar cara acepta foto+nombre en un solo mensaje (caption)
9527df5 fix: registrar cara busca con tolerancia a acentos (cesar→césar)
e08c797 fix: registrar cara busca en NIÑOS + PRUEBA FENIX simultáneamente
64b5e37 feat: registrar cara sube foto como attachment a campo FOTO en Airtable
1985a4b fix: registrar cara busca por palabras individuales en NOMBRE + APELLIDO
```

### Sesión 2 (misma noche)

**Ivan:** podríamos hacer una página con ficha por cada niño? foto, nombre, edad, asistencia, reservas
**Fenix:** Creado endpoint /api/alumnos + /api/reservas en Railway. Frontend alumnos.html + reservas.html. Repo fenixkidsacademy-web creado en GitHub y conectado a Cloudflare Pages.

**Ivan:** que cada ficha tenga su propio link, para el resumen reservas
**Fenix:** Slug por niño (ej: mariano-emanuel-centurion-saucedo). Link web como header en resumen reservas. Links individuales removidos por exceder 4096 chars WhatsApp.

**Ivan:** cargale en Airtable el link a cada niño
**Fenix:** Campo LINK WEB creado en NIÑOS + PRUEBA FENIX. 47+58 links cargados.

**Ivan:** resumen anuncios — vie 15 y sab 16 da total 0
**Fenix:** Bug: usaba concepto→monto (dict fijo), FENIXMAMA/paquetes quedaban en 0. Fix: lee campo MONTO directo.

**Ivan:** el gasto no es fijo 200k — el 15 gasté 450, 16 y 17 gasté 0
**Fenix:** Tabla GASTOS FENIX creada en Airtable. 15 registros cargados. Resumen lee gasto real, fallback 200k.

**Ivan:** que me separe pruebas / fenixmama / plan inscriptos
**Fenix:** Total al final separado: Pruebas + Fenixmama + Plan inscriptos → Total recaudado vs Total anuncios → Diferencia.

### Commits sesión 2
```
6b85a78 feat: API pública /api/alumnos + link ficha en resumen reservas
aaae67e fix: link ficha alumno en resumen reservas — clickeable con https://
ba77f6b fix: quitar links del resumen reservas — excedía 4096 chars de WhatsApp
bf8745d feat: endpoint /api/reservas con foto, padre, cell por turno
f47c6ca feat: resumen reservas incluye link web como header
48b1a92 fix: resumen anuncios usa campo MONTO directo + agrega PAQ5/PAQ12 al desglose
7e87557 feat: resumen anuncios lee gasto real de tabla GASTOS FENIX
7fe31ee fix: resumen anuncios crasheaba — dict cambió a conceptos pero desglose no
2fa73bd fix: _GASTO_DIARIO renombrado a _GASTO_DEFAULT — NameError
2233d0f fix: resumen anuncios — solo monto>0, FENIXMAMA en conceptos, total sin x200
0278440 feat: resumen anuncios muestra inscriptos + monto PLAN + total recaudado
9c33788 feat: resumen anuncios separa pagos: pruebas + fenixmama + plan inscriptos
```

---

## 2026-05-22

**Ivan:** me pasa el prompt maestro del curso de IA, pide comparación con FENIX
**Fenix:** Análisis completo: FENIX más avanzado (memoria auto CC + Obsidian > archivos .md locales). Pero para enseñar, los .md locales son mejores (visibilidad, control, valor pedagógico).

**Ivan:** entonces para el curso sería mejor usar lo de FENIX?
**Fenix:** No — son contextos distintos. Curso = principiante que necesita VER la mecánica. FENIX = proyecto maduro que necesita escalar. Recomendación: curso mantiene .md locales, puede agregar skills + checklist + trigger de FENIX.

**Ivan:** pero cuando el proyecto crece y se vuelve maduro?
**Fenix:** Los .md locales se vuelven lastre (errores.md enorme, progreso.md desactualizado, handoff redundante con git log). Solución: dejar el curso como está, agregar "nivel 2" cuando gradúe.

**Ivan:** justamente la idea es darle algo que escale sin modificar
**Fenix:** Entonces cambió el enfoque. Propuesta: /cierre como skill (no command), memoria auto CC desde día 1, bitácora solo como export visible. Skills en vez de commands para tareas complejas.

**Ivan:** implementá lo que pensás que sirve + los cambios de hora que hicimos en Dorita
**Fenix:** Implementado: (1) brain.py con hora + MAÑANA + PASADO pre-calculados (patrón Dorita), (2) hooks SessionStart/End en settings.json (sin TZ para Git Bash), (3) CLAUDE.local.md + .gitignore.

**Ivan:** qué son esos archivos sin trackear? (gen_aviso_horario + html)
**Fenix:** Template reutilizable del aviso de cambio horario del 23/5 por frío. Genera página HTML con botones wa.me por familia.

**Ivan:** si volvemos a necesitar algo similar no sirve como ejemplo?
**Fenix:** Sí, lo commiteamos como template reutilizable.

### Commits sesión
```
3c88911 feat: inyectar hora + MAÑANA + PASADO en context de fechas + CLAUDE.local.md
c5011c5 feat: template aviso cambio horario — página con botones WA por familia
```

---

## 2026-05-23

### Tema: Migración a Tool Use + FSM

**Ivan:** endpoint 595994468797 — le cambió el horario pero en Airtable NO
**Fenix:** Diagnóstico completo. Marcelo Saucedo pidió cambiar de 11:00 a 15:30. Claude respondió "te cambio a las 15:30h para el sábado 23", pero el regex esperaba formato "sábado X a las Y" (fecha antes de hora). Claude puso hora antes de fecha → no matcheó. Además, guard de pago buscaba "pago confirmado" en últimos 10 msgs pero estaba en msg #26.

**Ivan:** no podemos depender de cómo Claude responde, buscame 5 modelos de agentes
**Fenix:** Investigación de 7 arquitecturas: Tool Use (Anthropic), Router+Workers, LangGraph, ReAct Loop, Rasa CALM, FSM+LLM, Multi-Agent. Recomendación: Tool Use + FSM híbrido.

**Ivan:** diseñamos la migración, creé un Frankenstein jaja
**Fenix:** Inventario completo del Frankenstein: 8000 líneas main.py, 15 interceptores regex, 6 detectores post-Claude, 17 variables in-memory, 0 tools. Plan de migración en 5 fases incrementales.

**Ivan:** comenzamos la migración
**Fenix:** Fases 0-3 ejecutadas en una sesión:
- Fase 0: 5 sets in-memory migrados a columna estado_json en PostgreSQL
- Fase 1: 10 funciones _padre_pregunta_* extraídas a agent/tools/detectores.py (-110 líneas)
- Fase 2: brain.py con soporte tool_use retrocompatible + tool_definitions + tool_executor + tools/reservas.py
- Fase 3: Feature flag USE_TOOL_USE conecta tools al flujo principal

**Ivan:** usar tools consume tokens, mantener regex para FAQ simples
**Fenix:** Reducido de 10 tools a 2 (reagendar_clase + confirmar_reserva). FAQ (precios, horarios, ubicación) se queda como interceptores regex (gratis).

**Ivan:** activamos USE_TOOL_USE=true en Railway
**Fenix:** Activado. Pendiente probar con lead real.

### Commits sesión
```
d560f46 refactor: persistir flags in-memory en DB (Fase 0 migración Tool Use)
2012ad0 refactor: extraer detectores de intención a agent/tools/detectores.py (Fase 1)
2cfac2f feat: soporte Tool Use en brain.py + tools iniciales (Fase 2)
528a861 feat: conectar Tool Use al flujo principal con feature flag (Fase 3)
ed6d8e3 fix: reducir tools a solo acciones (reagendar + confirmar reserva)
```

---

## 2026-05-24

**Ivan:** Necesito una auditoría completa del agente y un plan de rediseño basado en buenas prácticas de Anthropic. El proyecto fue construido incrementalmente con parches y hoy tiene errores frecuentes y fragilidad.
**Fenix:** Lectura exhaustiva de los 26 archivos Python (14,393 líneas). Análisis de main.py completo (8,010 líneas, 34 pasos del webhook, 25 rutas, 6 background loops). Referencia cruzada con guía Anthropic Certified Architect. Diagnóstico: 3 críticos, 4 altos, 4 medios.

**Ivan:** Es un cambio total, me gusta, no tengo problemas en hacer todo desde cero, quiero poder disponer de un agente que responda bien y cuando aplicamos una corrección no rompa todo lo demás.
**Fenix:** Plan completo de reconstrucción: ~50 archivos organizados por dominio, 11 tools (5 Ivan + 6 Aurora), agentic loop con hooks, errores estructurados, escalada como tool. Migración en 5 fases.

**Ivan:** ¿Qué pensás de hacer que el council analice esta migración?
**Fenix:** Council de 5 advisors (Contrarian, First Principles, Expansionist, Outsider, Executor) con peer review anónimo. Veredicto: "la dirección es correcta, la secuencia no". Contrarian (el más fuerte según peer review): "No está mal diseñado. Está mal secuenciado."

**Ivan:** Cada conversación tiene potencial de error y tengo que estar haciendo el fix en el momento, respondiendo personalmente a los clientes. Es una constante diaria.
**Fenix:** Ese dato cambia la ecuación — el costo del monolito es ALTO. Secuencia corregida: (1) fix 3 bugs activos, (2) implementar 11 tools con hooks en brain.py actual, (3) partir monolito.

**Ivan:** Arrancamos con paso 1
**Fenix:** Implementado: confirmar_reserva con executor (bomba desactivada), escalar_a_humano como tool determinística, errores estructurados en tool_executor, is_error en brain.py, descripciones mejoradas. main.py NO tocado.

**Ivan:** Cargá todo en MIGRACION TOTAL.md
**Fenix:** Documento de 700+ líneas con: estado actual detallado, diagnóstico, plan, council completo, decisión final, registro de implementación.

### Commits sesión
```
0dece4d feat: fix 3 bugs criticos — confirmar_reserva executor + escalar_a_humano tool + errores estructurados
```

---

## 2026-05-24 (sesión 2)

**Ivan:** yosoyfenix
**Fenix:** Briefing completo. Paso 1 hecho (3 bugs fixeados), pendiente deployar + arrancar Paso 2.

**Ivan:** Leemos el MIGRACION TOTAL.md y retomamos el trabajo
**Fenix:** Leído completo (773 líneas). Mapa: Paso 1 hecho, Paso 2 pendiente (11 tools + hooks), Paso 3 futuro.

**Ivan:** Deploy Paso 1 primero
**Fenix:** Push a Railway — 3 commits (fix bugs + docs). Deploy automático.

**Ivan:** Vamos con Paso 2
**Fenix:** Plan Mode. Exploración de 3 áreas en paralelo (tools+brain, Aurora regex en main.py, Airtable client). Plan: 2 waves incrementales.

**Ivan:** [aprueba plan]
**Fenix:** Wave 1 — Ivan 2 tools nuevas (consultar_disponibilidad, programar_llamada) + sistema hooks (validar_fecha_hora, anti_escalacion_spam, notificar_telegram, enviar_capi_event) + brain.py con hooks en loop + main.py con context. TOOLS_IVAN 3→5.

**Ivan:** Deploy
**Fenix:** Push Wave 1 a Railway.

**Ivan:** Vamos con Wave 2
**Fenix:** Wave 2 — Aurora 6 tools (agendar_clase, cancelar_reserva, consultar_agendados, registrar_familia, registrar_hijo, escalar_a_humano). TOOLS_AURORA creado. tool_executor 5→10 + resolver familia_id auto. main.py: Aurora recibe tools + 5 guards regex. prompts.yaml: HERRAMIENTAS + quitar REGISTRO PADRE/HIJO.

**Ivan:** Deploy
**Fenix:** Push Wave 2 a Railway.

**Ivan:** ¿Cómo seguimos?
**Fenix:** Cierre recomendado. Monitorear prod mañana, luego Paso 3 (partir monolito).

### Commits sesión
```
921653a feat: Wave 1 Paso 2 — 2 tools Ivan + hooks system
f288a30 feat: Wave 2 Paso 2 — Aurora con 6 tools (fin de regex)
```

---

## 2026-05-25 (sesión 2 — 12+ horas, QR + tools unificadas)

**Ivan:** yosoyfenix — arrancamos con QR check-in
**Fenix:** Briefing completo. QR está en prioridad 3, subido a prioridad 0.

**Ivan:** El QR puede tener el logo de FENIX?
**Fenix:** Sí, con ERROR_CORRECT_H permite 30% del área tapada.

**Ivan:** Creá carpeta marketing con todo el material
**Fenix:** Carpeta marketing/ creada con logos, afiches, anuncios, caricaturas, docs.

**Ivan:** Arrancamos QR Fase 1
**Fenix:** agent/qr.py + endpoint /checkin/{record_id} + campo HORA_CHECKIN en Airtable.

**Ivan:** QR Fase 2 — enviar por WhatsApp
**Fenix:** QR se envía después de agendar_clase/reagendar en main.py post-tool.

**Ivan:** Me volvió a aparecer "ver lista agendados" en el menú Aurora
**Fenix:** Prompt decía "menú de opciones" sin especificar cuáles. Ahora textual.

**Ivan:** FENIX dice "no tenés reservas" cuando acaba de agendar!
**Fenix:** Datos de Airtable iban en system prompt, Haiku los ignoraba por historial. Fix: inyectar en mensaje del usuario.

**Ivan:** ARRAYJOIN no funciona con record links!!!
**Fenix:** Probé 6 fórmulas por trial/error en vez de googlear. Fix: usar lookup texto FAMILIA.

**Ivan:** Reagendar no funciona — 0 tools ejecutadas
**Fenix:** tool_choice era auto, Haiku respondía conversacionalmente sin ejecutar. Fix: tool_choice forzado.

**Ivan:** Por qué 3 tools si es el mismo concepto?!
**Fenix:** Unificado: gestionar_reserva (Aurora) con param accion. Una tool, un tool_choice.

**Ivan:** Ahora tools de Ivan
**Fenix:** gestionar_prueba — mismo patrón. confirmar + reagendar en 1.

**Ivan:** Keywords no alcanzan para detectar flujo de reservas
**Fenix:** Para Ivan: no forzar por keywords. Forzar por flag modo_agenda post-pago.

**Ivan:** Después del pago es IMPOSIBLE equivocarse
**Fenix:** Flujo determinístico: pago→mensaje fijo con horarios→modo_agenda=True→tool forzada.

**Ivan:** El prompt sigue ofreciendo horarios antes del pago!!
**Fenix:** Prompt invertido: FASE 3 = cobrar primero. Agendar automático post-pago.

**Ivan:** No se generó el QR para leads!
**Fenix:** La tool daba error porque PRUEBA FENIX no existía aún. QR movido a post-formulario.

**Ivan:** Armá AIRTABLE ERRORES.md
**Fenix:** Creado en Obsidian con 6 errores + reglas. Referenciado en memoria.

**Ivan:** Cargá todo en el manual de agendas
**Fenix:** COMO ARMAR TOOL AGENDAS - QR - AIRTABLE.md actualizado con 17 errores + nuevas subsecciones.

### Commits sesión
```
0c859cc feat: QR check-in — generar QR con logo FENIX + endpoint /checkin/{record_id}
059bbed fix: menú Aurora — poner opciones EXACTAS en mensajes siguientes
f758a04 fix: Aurora DEBE usar Airtable como única fuente de verdad para reservas
759b9d7 fix: reservas Airtable inyectadas en mensaje del usuario, no en system prompt
18a187b fix: reservas Airtable como parámetro separado en mensaje del usuario
ff0f568 fix: logo QR al repo + caption "Fenix Kids Academy"
669c66e fix: buscar reservas por lookup FAMILIA (texto), no por record link
6e7d4f5 feat: gestionar_reserva — una sola tool para agendar/reagendar/cancelar
00e3f39 fix: notificación reserva solo a Telegram, no WhatsApp admin
27ec8e0 feat: QR check-in para leads de prueba (PRUEBA FENIX)
d3ce8f1 feat: gestionar_prueba — tool unificada para confirmar/reagendar pruebas (Ivan)
0af0ec7 fix: detectar respuesta a horarios para forzar tool_choice
ad5a241 feat: flujo agenda determinístico post-pago para leads
9c1fd34 fix: Ivan cobra PRIMERO, agenda DESPUÉS (automático post-pago)
ca2194f fix: QR se envía post-formulario, no post-agenda
```

---

## 2026-05-26 — IMPLEMENTACION SISTEMA OSMANI

**Ivan:** yosoyfenix → briefing. Endpoint 595985175667: padre preguntó si podían ir mamá+papá+Joaquín "en familia" → sistema le mandó afiche de hermanos (incorrecto). Además el agente dijo "LA MANSIÓN LAFUENTE" y pidió datos con tono imperativo ("pasame los datos y listo").

**Fenix:** Fix detector hermanos — sacado "familia" y "plan familiar" de `padre_pregunta_hermanos` en detectores.py. Corregido nombre: "LA MANSIÓN LAFUENTE" → "LA CASONA LAFUENTE" en prompts.yaml ("mansión" solo como descripción). Nueva regla PROHIBIDO: siempre "por favor" al pedir datos. Deploy a Railway.

**Ivan:** investigar repo addyosmani/agent-skills (45k stars, 23 skills de ingeniería). ¿Nos sirve para FENIX?

**Fenix:** Investigación profunda del repo. Conclusión: no instalarlo como plugin, pero el sistema de auto-inyección de skills es exactamente lo que necesitamos. El agente tiene 30+ memorias y CHECKLIST.md pero nunca los lee antes de actuar. La innovación de Osmani: SessionStart hook inyecta un meta-skill (router) que enseña al agente cuándo activar cada skill automáticamente, con anti-racionalizaciones que contrarrestan excusas del agente.

**Ivan:** no inventar, seguir el sistema de Osmani exacto

**Fenix:** Plan Mode → implementación del sistema agent-skills para FENIX siguiendo arquitectura de Osmani:
- Meta-skill router: `.claude/skills/using-fenix-skills/SKILL.md`
- 4 skills nuevos: `/pre-cambio`, `/pre-deploy`, `/debug`, `/verificar`
- 4 commands como entry points
- SessionStart hook en `.claude/hooks/session-start.sh`
- Documentación completa: `agent-skills-implementacion.md` (628 líneas) + copia en Obsidian guias/

**Ivan:** guardar doc en Obsidian, commit y push

### Commits
```
6679b5e fix: detector hermanos no intercepta "familia", corregir nombre mansión→casona, tono amable
310a320 docs: manual de implementación agent-skills (basado en addyosmani/agent-skills)
```

## 2026-05-26 (sesión 2) — Monitor + Guardian + Agent Blue

**Ivan:** quiero implementar el sistema Guardian y Monitor de Dorita, me pasó el link al manual en Obsidian
**Fenix:** leyó GUARDIAN Y MONITOR MANUAL.md, analizó las 3 capas, propuso adaptar Capa 1 primero

**Ivan:** vamos
**Fenix:** ejecutó /pre-cambio, leyó main.py + telegram_bridge + memory + detectores. Creó agent/monitor.py (2 loops: conversaciones sin respuesta + salud). Integró en main.py (lifespan + error tracking)

**Ivan:** listo (agregó TELEGRAM_MONITOR_GROUP_ID en Railway)
**Fenix:** creó Guardian remoto con RemoteTrigger (6 checks, cada 1h, Sonnet 4.6). Forzó primera ejecución

**Ivan:** aplicalo a Dorita también, y al md
**Fenix:** actualizó Guardian Dorita para reportar a Telegram. Actualizó manual en Obsidian con tabla de triggers

**Ivan:** necesito instalar esto en Agent Blue (cursos-ia) y que sea parte del curso
**Fenix:** diseñó plan y escribió prompt fundacional (427 líneas) para que Agent Blue se construya a sí mismo

**Ivan:** hermanos mayores??
**Fenix:** lo cambió... Ivan dijo que estaba bien, lo restauró

**Ivan:** el /cierre debería preguntar nombre de sesión con sugerencias
**Fenix:** agregó paso 6 al cierre con 3 sugerencias

### Commits
```
603ae31 feat: monitor interno de producción (Capa 1)
8cb92f3 feat: prompt fundacional Agent Blue (en cursos-ia)
```

---

## 2026-05-26 (sesión 3)

**Ivan:** endpoint 595981101080 — lead preguntó horario después de que FENIX ofreció precios, FENIX ignoró el "sí" y se puso a agendar sin cobrar
**Fenix:** analizó la conversación completa. Detectores `_padre_muestra_interes` y `padre_pregunta_horarios` no capturaban "si si a que hora seria" — 31 de 34 variaciones afirmativas fallaban por anchors `^sí$` estrictos. Reescrito con set de exactos + patrones flexibles

**Ivan:** y si dice "ok" o "yes" el mismo problema!
**Fenix:** testeó 32 casos, confirmó que casi todos fallaban. Fix cubría todos

**Ivan:** cuando envía datos bancarios cierra con "¿Dale?" — imperativo y falta de respeto, que cierre con "Quedo atento."
**Fenix:** editó FASE 3 en prompts.yaml, cierre "Quedo atento." + prohibición explícita de "¿Dale?", "¿Va?", etc.

**Ivan:** no recibí mensaje en telegram de the guardian
**Fenix:** grupo era normal (no supergrupo), topics no funcionan en grupos normales. Ivan convirtió a supergrupo, ID cambió a -1003834000116. Topic "Monitor FENIX" creado (thread_id=7). Pendiente: actualizar var en Railway

### Commits
```
f2241b3 fix(detectores): ampliar detección de respuestas afirmativas y "a qué hora"
4d522d1 fix(prompt): FASE 3 cierra con "Quedo atento." en vez de "¿Dale?"
```

---

## 2026-05-30 (sesión 7 — fix lluvia + carga pagos)

**Ivan:** ¿qué hace nuestro comando endpoint?
**Fenix:** explicó el flujo del skill /endpoint (resolver tel/nombre → 2 curls a prod /debug y /conversacion → leer cada mensaje crudo → reportar; solo lectura)

**Ivan:** endpoint 595992287742 — esta mamá preguntó si se suspende por lluvia y FENIX respondió "3000m² bajo techo", y le dijo sábado 30 a las 9:30 cuando ya cambiamos los horarios; además en Telegram solo veo la conversación del 29
**Fenix:** analizó. La clienta (Leticia Paredes) había PAGADO el 13/5 reserva 9:30, llegó hoy y la mandaron al centro → pidió reembolso. 3 bugs: (1) "3000m² bajo techo" sale del prompt línea 36; (2) el 9:30 venía de la reserva vieja huérfana (cambiaron horarios sin migrar reservas existentes); (3) Telegram probablemente cambió de grupo entre el 13 y el 29

**Ivan:** ya le respondí a Leticia, le devolví su dinero y le regalé un mes gratis... arreglamos el prompt
**Fenix:** corrió /pre-cambio, grep confirmó que "bajo techo" vive solo en prompts.yaml:36. Aclaró con Ivan: los 3000m² son el parque, la mansión (~300m²) es el refugio. Corrigió la línea a "si llueve, entrenan dentro de la mansión". Push (commit 5d1a572)

**Ivan:** endpoint 595983047547 — pagó 230 por mensualidad, le pasé bien el precio, pero en Airtable cargó 100
**Fenix:** causa raíz: `detectar_tipo_pago()` clasifica por keywords; "mensualidad" no está en la lista → cayó a "prueba" → monto 100mil. Cargó registro nuevo F.MENSUAL 230mil INSCRIPTO en PRUEBA FENIX + asiento en PAGOS, sin pisar la prueba de 100mil. Fix de fondo (por estado del lead) queda para el menú interactivo

**Ivan:** César Mendez 595985296645 pagó 350mil x 5 clases concepto PAQUETE5, anotar en PRUEBA FENIX; este y el anterior van a PAGOS también
**Fenix:** verificó tablas, creó César en PRUEBA FENIX (PAQUETE5 350mil INSCRIPTO) + 2 asientos en PAGOS (César PAQUETE5 350mil, Edith MENSUAL 230mil), vinculados a sus registros de PRUEBA FENIX

**Ivan:** el papá de Max (Lee Jun Yob) pagó de nuevo 90mil prueba, me pagó personalmente; y cargar reserva+pago+formulario de Johanna Britez 595971580929
**Fenix:** Johanna (2 hijos Gastón+Danna, prueba 120mil) nunca se procesó en el sistema → cargó 2 registros PRUEBA FENIX + PAGOS. Fecha nac de Gastón quedó vacía (el padre puso "2026"). Lee/Max (3era prueba) → registro PRUEBA FENIX + PAGOS (TRANSFER)

**Ivan:** eliminamos el pago de Leticia del 13/5, le devolví su dinero
**Fenix:** propuso no borrar (mantener rastro). Ivan eligió asiento -150.000 DEVOLUCION en PAGOS + las 2 pruebas marcadas CANCELADO. Creó concepto DEVOLUCION nuevo en PAGOS

### Commits
```
5d1a572 fix(prompt): corregir info de lluvia — la mansion es el refugio, no 3000m2 bajo techo
```
(El resto de la sesión fue carga operacional en Airtable, sin commits de código.)
