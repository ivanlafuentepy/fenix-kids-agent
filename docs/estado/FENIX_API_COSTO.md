up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# FENIX KIDS — Análisis de Costos API

> Última actualización: 2026-04-23

---

## Modelos utilizados

| Modelo | Uso | Input | Output |
|---|---|---|---|
| Claude Sonnet 4.6 | Todas las respuestas (Ivan + Aurora) | $3 / MTok | $15 / MTok |
| Claude Haiku 4.5 | Extracción de formularios (post-pago) | $0.80 / MTok | $4 / MTok |

---

## Tokens por mensaje

### System prompt (se envía en CADA llamada)

| Prompt | Tokens aprox | Nota |
|---|---|---|
| Ivan (prompt completo) | ~2,200 | Incluye identidad, negocio, flujo, reglas, ejemplos |
| Contexto de fechas (dinámico) | ~250 | Sábados disponibles del mes |
| Aurora | ~650 | Mucho más liviano |
| **Ivan total por llamada** | **~2,450** | 45% del consumo total |

### Historial de conversación

| Config | Valor | Tokens aprox |
|---|---|---|
| Límite actual | 40 mensajes | ~600-800 tokens |
| Promedio por mensaje | ~15-20 tokens | Varía según largo |

### Respuestas generadas

| Tipo de respuesta | Output tokens |
|---|---|
| Respuesta corta (edad, nombre) | 30-80 |
| Respuesta normal | 150-250 |
| Diagnóstico completo | 350-500 |
| Rompehielos (mensaje fijo) | ~200 |

---

## Costo por tipo de mensaje

| Interacción | Input tokens | Output tokens | Costo |
|---|---|---|---|
| Rompehielos (1er msg) | ~2,450 | ~200 | $0.010 |
| FASE 1.5 (pedir nombres) | ~2,600 | ~50 | $0.009 |
| FASE 1.5 (pedir edad) | ~2,700 | ~40 | $0.009 |
| Diagnóstico (msg largo) | ~2,900 | ~450 | $0.015 |
| Cierre diagnóstico | ~3,100 | ~100 | $0.011 |
| Respuesta normal post-afiche | ~3,200 | ~200 | $0.013 |
| Confirmación de pago | ~3,300 | ~200 | $0.013 |
| Haiku extracción formulario | ~1,000 | ~150 | $0.001 |

---

## Costo por conversación completa

### Lead → clase de prueba (~15 mensajes)

| Etapa | Msgs | Costo acumulado |
|---|---|---|
| Rompehielos | 1 | $0.010 |
| FASE 1.5 (nombres + edad) | 2-3 | $0.028 |
| Diagnóstico | 1 | $0.043 |
| Cierre + respuesta padre | 2 | $0.067 |
| Afiche + follow-up + respuesta | 2 | $0.093 |
| Pago + confirmación | 2-3 | $0.132 |
| Agendamiento | 2 | $0.158 |
| Haiku extracción | 1 | $0.159 |
| **Total conversión completa** | **~15** | **$0.15 - $0.20** |

### Lead que no convierte (~5 mensajes)

| Etapa | Msgs | Costo |
|---|---|---|
| Rompehielos + FASE 1.5 | 3 | $0.028 |
| Diagnóstico | 1 | $0.043 |
| Seguimientos automáticos | 1-3 | $0.070 |
| **Total lead no convertido** | **~5** | **$0.05 - $0.08** |

### Aurora (cliente inscripto, reserva) ~5 msgs

| Etapa | Msgs | Costo |
|---|---|---|
| Saludo + búsqueda familia | 2 | $0.008 |
| Elegir horario + confirmar | 3 | $0.015 |
| **Total reserva Aurora** | **~5** | **$0.02 - $0.03** |

---

## Proyección mensual

| Volumen | Leads nuevos | No convierten (70%) | Convierten (30%) | Costo total |
|---|---|---|---|---|
| Bajo | 50 | $2.80 | $2.70 | **$5.50** |
| Medio | 200 | $11.20 | $10.80 | **$22.00** |
| Alto | 500 | $28.00 | $27.00 | **$55.00** |
| Agresivo | 1,000 | $56.00 | $54.00 | **$110.00** |

*No incluye reservas de Aurora (costo mínimo: ~$0.03/reserva)*

---

## Distribución del consumo

```
System prompt Ivan ████████████████████░░░░░░░░  45%
Historial            ██████████░░░░░░░░░░░░░░░░░  25%
Respuestas output    ████████░░░░░░░░░░░░░░░░░░░  20%
Haiku extracción     ██░░░░░░░░░░░░░░░░░░░░░░░░░   5%
Contexto fechas      ██░░░░░░░░░░░░░░░░░░░░░░░░░   5%
```

---

## Prompt caching (ya implementado)

El system prompt usa `cache_control: ephemeral`. Esto significa que en mensajes consecutivos del mismo lead (dentro de 5 min), el prompt se cachea y los tokens de input se cobran al 10% del precio normal.

| Escenario | Sin cache | Con cache | Ahorro |
|---|---|---|---|
| 15 msgs seguidos | $0.20 | $0.08 | 60% |
| Msgs espaciados (+5min) | $0.20 | $0.20 | 0% |

En la práctica, la mayoría de conversaciones tienen intercambios rápidos, así que el cache funciona bien.

---

## Optimizaciones posibles (no implementadas)

| Cambio | Ahorro estimado | Riesgo | Prioridad |
|---|---|---|---|
| Reducir historial de 40 a 20 msgs | -20% | Bajo | P2 |
| Acortar prompt Ivan (quitar ejemplos) | -15% | Medio | P3 |
| Reducir max_tokens de 1024 a 600 | -5% | Bajo | P3 |
| Haiku para msgs rutinarios | -40% | Alto | P4 |

**Conclusión:** con los precios actuales de Sonnet, el costo es bajo ($20-55/mes para 200-500 leads). No vale la pena arriesgar calidad por ahorrar centavos. Revisar si el volumen supera 1,000 leads/mes.

---

## Otros servicios con costo

| Servicio | Costo | Nota |
|---|---|---|
| Groq Whisper (audios) | Gratis (tier free) | Transcripción de audio |
| Airtable | Gratis (tier free) o $20/mes | Depende del volumen de registros |
| Railway | ~$5-10/mes | Server + PostgreSQL |
| Meta WhatsApp API | Gratis primeras 1,000 conv/mes | Después ~$0.05/conversación |
| Google Calendar API | Gratis | Service Account |
| Telegram Bot | Gratis | Sin límites prácticos |
