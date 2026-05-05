# Sistema de Follow-Up Automático — FENIX KIDS

## El problema que resuelve

Hay leads que llegan hasta el punto de recibir los datos bancarios para la transferencia, pero nunca mandan el comprobante. Hoy se pierden silenciosamente. Con este sistema, el bot les manda seguimiento automático cada 24h (máximo 3 veces), y si no responden, se marcan como DESCARTADO.

## Cómo funciona

**Un solo campo `CONVERSION` (select) en la tabla de LEADS maneja todo el embudo:**

```
CONSULTA → CONTACTADO → PAGO / GRATIS → INSCRIPTO
                ↘ DESCARTADO (tras 3 seguimientos sin respuesta)
```

| Estado | Significado | Cuándo se marca |
|---|---|---|
| `CONSULTA` | Lead nuevo, todavía no recibió precios/datos | Auto al crear el lead (primer mensaje) |
| `CONTACTADO` | Ya recibió datos bancarios, esperando pago | Auto cuando el bot envía datos bancarios |
| `PAGO` | Pagó | Auto al confirmar comprobante |
| `GRATIS` | Prueba gratis (referidos, promo) — sin pago | Manual desde Telegram (/agenda gratis nombre) |
| `INSCRIPTO` | Inscripto con plan activo | Manual o automático |
| `DESCARTADO` | 3 follow-ups sin respuesta, se deja de contactar | Auto tras 3er seguimiento |

**Campos auxiliares (en la misma tabla de LEADS):**

| Campo | Tipo | Para qué |
|---|---|---|
| `SEGUIMIENTOS` | Number (entero, default 0) | Cuántos mensajes de follow-up se enviaron (0, 1, 2, 3) |
| `FECHA FOLLOWUP` | DateTime | Cuándo fue el último follow-up o cuándo se envió los datos bancarios (para calcular si ya pasaron 24h) |

## Trigger: cuándo marcar CONTACTADO

Cuando el bot envía los datos bancarios al lead. Se detecta buscando el CI/alias del banco en el mensaje del bot:

```python
CI_BANCARIO = "1604338"  # marcador — si aparece en respuesta del bot, significa que mandó datos bancarios

# Después de que el bot envía su respuesta:
if CI_BANCARIO in respuesta and agent == "ivan":
    await actualizar_conversion_lead(telefono, "CONTACTADO")
    await _resetear_seguimiento(telefono)  # pone SEGUIMIENTOS=0, FECHA FOLLOWUP=ahora
```

## Las 3 funciones del sistema

```python
async def _resetear_seguimiento(telefono: str):
    """Se llama cuando el bot envía datos bancarios.
    Pone SEGUIMIENTOS=0 y FECHA FOLLOWUP=ahora (UTC)."""
    record_id = await obtener_lead_record_id(telefono)
    campos = {
        "SEGUIMIENTOS": 0,
        "FECHA FOLLOWUP": datetime.now(timezone.utc).isoformat()
    }
    await _patch(TABLA_LEADS, record_id, campos)


async def _incrementar_seguimiento(telefono: str) -> int:
    """Se llama después de enviar un follow-up exitoso.
    Incrementa SEGUIMIENTOS en 1 y actualiza FECHA FOLLOWUP.
    Retorna el nuevo valor (1, 2, o 3)."""
    record_id = await obtener_lead_record_id(telefono)
    # Leer valor actual
    records = await _get_records(TABLA_LEADS, formula=f"{{TELEFONO}}='{telefono}'", max_records=1)
    actual = records[0].get("fields", {}).get("SEGUIMIENTOS", 0) or 0
    nuevo = actual + 1
    campos = {
        "SEGUIMIENTOS": nuevo,
        "FECHA FOLLOWUP": datetime.now(timezone.utc).isoformat()
    }
    await _patch(TABLA_LEADS, record_id, campos)
    return nuevo


async def _ejecutar_followup():
    """Loop principal — se ejecuta 1x por día a las 9:00 AM hora local.
    Busca leads con CONVERSION=CONTACTADO y SEGUIMIENTOS<3 donde
    pasaron al menos 24h desde FECHA FOLLOWUP."""

    formula = "AND({CONVERSION}='CONTACTADO',OR({SEGUIMIENTOS}<3,{SEGUIMIENTOS}=BLANK()))"
    records = await buscar_leads(formula)

    for rec in records:
        telefono = rec["TELEFONO"]
        fecha_fu = rec["FECHA FOLLOWUP"]
        seguimientos = rec["SEGUIMIENTOS"] or 0

        # ¿Pasaron 24h desde el último contacto?
        horas_desde = calcular_horas(fecha_fu)
        if horas_desde < 24:
            continue

        # Safety check: si pagó entre medio (por si Airtable no se actualizó)
        if detectar_pago_en_historial(telefono):
            await actualizar_conversion(telefono, "PAGO")
            continue

        # Generar mensaje según número de seguimiento
        nombre_hijo = rec.get("NOMBRE NIÑO", "su hijo/a")
        nombre_padre = rec.get("NOMBRE RESPONSABLE", "").split()[0]

        if seguimientos == 0:
            instruccion = (
                f"[SISTEMA: El padre {nombre_padre} recibió los datos bancarios hace 24h "
                f"pero no mandó el comprobante. Mandá un mensaje corto y amable "
                f"recordándole que tiene el lugar reservado para {nombre_hijo} y que "
                f"te mande el comprobante cuando pueda. No presiones. Máximo 2 líneas.]"
            )
        elif seguimientos == 1:
            instruccion = (
                f"[SISTEMA: Segundo seguimiento a {nombre_padre}. Ya le recordaste ayer. "
                f"Preguntá si sigue interesado/a. Ofrecé ayuda si tiene alguna duda. "
                f"Corto y directo. Máximo 2 líneas.]"
            )
        elif seguimientos == 2:
            instruccion = (
                f"[SISTEMA: Tercer y último seguimiento a {nombre_padre}. "
                f"Decile que el lugar sigue disponible pero que necesitás confirmar. "
                f"Si no responde, no se le contacta más. Máximo 2 líneas.]"
            )

        # Enviar con Claude (personalizado según historial)
        respuesta = await generar_respuesta(instruccion, historial, agent_actual="vendedor")
        await enviar_whatsapp(telefono, respuesta)
        nuevo = await _incrementar_seguimiento(telefono)

        # Si llegó a 3 → DESCARTADO automático
        if nuevo >= 3:
            await actualizar_conversion(telefono, "DESCARTADO")

        await asyncio.sleep(3)  # pausa entre leads para no saturar
```

## El scheduler (loop diario)

```python
async def _followup_loop():
    """Background task que arranca con el servidor.
    Calcula cuánto falta para las 9:00 AM hora local, duerme, ejecuta, repite."""
    TZ_LOCAL = ZoneInfo("America/Asuncion")

    while True:
        ahora = datetime.now(TZ_LOCAL)
        target = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
        if ahora >= target:
            target += timedelta(days=1)
        delay = (target - ahora).total_seconds()
        await asyncio.sleep(delay)
        try:
            await _ejecutar_followup()
        except Exception as e:
            logger.error(f"[FOLLOWUP] Error en ciclo: {e}")

# Se lanza al arrancar el servidor (en lifespan o startup):
asyncio.create_task(_followup_loop())
```

## Reglas de negocio

1. **1 mensaje cada 24h** — nunca más de uno por día
2. **Máximo 3 intentos** — después DESCARTADO y no se contacta más
3. **Si el lead responde**: el follow-up se detiene solo. Cuando el lead responde, el bot procesa su mensaje normalmente. Si manda comprobante → PAGO. Si responde cualquier otra cosa, el bot conversa normal y el campo sigue en CONTACTADO (el próximo ciclo verificará si pasaron 24h DESDE ESE MOMENTO)
4. **Horario**: 9:00 AM hora local (un solo envío por día, a todos los pendientes)
5. **Tono de los mensajes**: Claude los genera personalizados con contexto del historial. Son cortos (2 líneas max), amables, sin presión
6. **Escalación progresiva**:
   - Seguimiento 1: recordatorio suave ("tenés el lugar, mandame el comprobante cuando puedas")
   - Seguimiento 2: pregunta directa ("¿seguís interesada?")
   - Seguimiento 3: último aviso ("necesito confirmar, si no escucho de vos libero el lugar")

## Pasos para replicar en otro proyecto

1. **Airtable**: agregar opciones `CONTACTADO` y `DESCARTADO` al campo CONVERSION de la tabla LEADS
2. **Airtable**: crear campo `SEGUIMIENTOS` (Number) y verificar que `FECHA FOLLOWUP` (DateTime) exista
3. **Código**: identificar el marcador de "datos bancarios enviados" (CI, CBU, alias, número de cuenta)
4. **Código**: agregar las 3 funciones (`_resetear_seguimiento`, `_incrementar_seguimiento`, `_ejecutar_followup`)
5. **Código**: agregar el trigger después de enviar respuesta: si el marcador aparece → marcar CONTACTADO + resetear seguimiento
6. **Código**: lanzar `_followup_loop()` al startup del servidor
7. **Prompt del bot**: adaptar las instrucciones de seguimiento al tono y contexto del negocio

## Ventajas de este enfoque

- **Un solo campo** para ver todo el embudo en Airtable (filtrar "CONTACTADO" = leads esperando pago)
- **Sin estados paralelos** — todo en CONVERSION, sin campo FOLLOWUP separado
- **Numérico** — fácil de filtrar (SEGUIMIENTOS >= 1 = ya se le dio seguimiento)
- **Automático** — una vez configurado, corre solo todos los días a las 9AM
- **Personalizado** — Claude genera cada mensaje con el historial real, no son templates genéricos
- **Compatible con promos** — GRATIS u otros estados no interfieren (el follow-up solo corre para CONTACTADO)
