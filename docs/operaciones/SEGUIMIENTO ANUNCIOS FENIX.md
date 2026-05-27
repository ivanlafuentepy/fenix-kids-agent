up:: [[FENIX KIDS/FENIX KIDS|FENIX KIDS]]

# SEGUIMIENTO ANUNCIOS FENIX KIDS

> Tracking de follow-ups enviados a leads de anuncios CTWA.
> Incluye tasa de respuesta, qué escribieron, y conversión post-followup.

---

## 1ER FOLLOWUP — 5 de mayo 2026

**Tipo:** Masivo de fotos (caricatura + foto real de clase)
**Enviado a:** 147 leads
**Fecha:** 5 de mayo ~9:00 AM PY

### Resultados

| Métrica | Valor |
|---|---|
| Total enviados | 147 |
| Respondieron | 25 |
| No respondieron | 122 |
| **Tasa de respuesta** | **17.0%** |
| Pagaron POST followup | 0 |
| Ya habían pagado antes | 6 |
| Contactados (esperando pago) | 4 |
| Consultas sin avance | 137 |

### Los 25 que respondieron — QUÉ ESCRIBIERON

| # | Teléfono | Hora resp | Qué escribió | Estado |
|---|---|---|---|---|
| 1 | 595983439825 | 09:03 | "Bueno día si me gustaría" | CONTACTADO |
| 2 | 595982891207 | 09:18 | "Que precio tiene" | CONSULTA |
| 3 | 595987405605 | 09:20 | "Buen dia" | CONSULTA |
| 4 | 595984620404 | 09:22 | "Buen día" | CONSULTA |
| 5 | 595972736655 | 09:23 | "Cuál es el costo?" | CONSULTA |
| 6 | 595982400160 | 09:25 | "Buenos Dias" (ya pagado antes) | PAGO |
| 7 | 595972440842 | 09:29 | "Cuanto es mensual?" | CONSULTA |
| 8 | 595981838892 | 09:30 | "11 y 12" (eligió rompehielos) | CONSULTA |
| 9 | 595991526437 | 09:32 | "Buenos días si" | CONSULTA |
| 10 | 595982138554 | 09:37 | "Buenos días sería en mi caso 150mil x niño??" | CONTACTADO |
| 11 | 595985338400 | 09:45 | "Buen día y hay que hablar profe..." | CONSULTA |
| 12 | 595985864829 | 09:48 | "Holaa buen día El número 15" (eligió diagnóstico) | CONSULTA |
| 13 | 595991886511 | 10:25 | "Buenos días" | CONSULTA |
| 14 | 595984179913 | 10:16 | "Me encanta 🥰" (ya pagada antes) | PAGO |
| 15 | 595982670439 | 10:15 | "M podrías embiar la ubicación y precio" | CONSULTA |
| 16 | 595983345901 | 10:04 | "Cuanto seria para ir a ver si le gusta" | CONSULTA |
| 17 | 595992916814 | 10:50 | "Qe tal...qe precio Tiene.." | CONSULTA |
| 18 | 595991928890 | 10:50 | "Mi hija creería que es una niña normal diría, solo busco actividades para ella" | CONSULTA |
| 19 | 595984611996 | 10:27 | "10 años tiene mi hija q precio seria" | CONSULTA |
| 20 | 595974408101 | 11:32 | "Buen dia este sábado aún no. El que viene recien iniciaremos." | CONSULTA |
| 21 | 595992322752 | 12:23 | "1,2,3,5,7,10,12" (eligió 7 rompehielos) | CONTACTADO |
| 22 | 595981966609 | 12:58 | "2,12" (eligió rompehielos) | CONSULTA |
| 23 | 595981284184 | 15:33 | "En dónde sería ? 😊" | CONSULTA |
| 24 | 595971250010 | 17:33 | "Buenas..si..me gustaría" | CONTACTADO |
| 25 | 595982790407 | 18:24 | [audio] (no se transcribió — bug) | CONSULTA |

### Análisis de respuestas

| Tipo de respuesta | Cantidad | % |
|---|---|---|
| Pidieron precio/costo | 7 | 28% |
| Saludaron ("buen día") | 6 | 24% |
| Eligieron rompehielos | 4 | 16% |
| Mostraron interés directo | 3 | 12% |
| Pidieron ubicación | 2 | 8% |
| Ya pagados que volvieron a escribir | 2 | 8% |
| Audio (no transcripto) | 1 | 4% |

### Observaciones

- **17% tasa de respuesta** es buena para un masivo frío
- **0 pagos nuevos** directamente del followup
- **4 avanzaron a CONTACTADO** (recibieron datos bancarios) — pendientes de pago
- La mayoría respondió entre **9:00 y 11:00 AM** (primera hora después del envío)
- Los que pidieron precio son los más calientes — deberían recibir FU2

---

## FOLLOWUP AUTOMATIZADO (a partir del 6 de mayo)

Sistema automático que envía seguimientos a leads en CONTACTADO (recibieron datos bancarios pero no pagaron).

**Lógica:**
- FU1: 24h después de recibir datos bancarios
- FU2: solo si respondió al FU1 (ventana 24h WhatsApp)
- FU3: solo si respondió al FU2
- Si no responde → DESCARTADO (ventana cerrada)

### FU1

| Métrica | Valor |
|---|---|
| Leads elegibles | 19 (CONTACTADO con SEGUIMIENTOS=0) |
| Primer envío programado | 6 de mayo 9:00 AM PY |
| Respondieron | pendiente |
| Pagaron post-FU1 | pendiente |

### FU2

| Métrica | Valor |
|---|---|
| Leads elegibles | solo los que respondieron FU1 |
| Respondieron | pendiente |
| Pagaron post-FU2 | pendiente |

### FU3

| Métrica | Valor |
|---|---|
| Leads elegibles | solo los que respondieron FU2 |
| Respondieron | pendiente |
| Pagaron post-FU3 | pendiente |

---

## Campos Airtable para tracking

| Campo | Tabla | Tipo | Descripción |
|---|---|---|---|
| 1ER FOLLOWUP | LEADS FENIX | Checkbox | Recibió masivo fotos 5/5 |
| RESPONDIO FU1 | LEADS FENIX | Checkbox | Respondió al 1er followup |
| RESPONDIO FU2 | LEADS FENIX | Checkbox | Respondió al 2do followup |
| SEGUIMIENTOS | LEADS FENIX | Number | Contador de FU enviados (0-3) |
| FECHA FOLLOWUP | LEADS FENIX | DateTime | Timestamp del último FU |
| PAGO POST FU | LEADS FENIX | Number | En qué FU estaba cuando pagó |
