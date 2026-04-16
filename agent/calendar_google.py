# agent/calendar_google.py — Integración con Google Calendar
# FENIX KIDS ACADEMY

"""
Crea automáticamente un evento en Google Calendar cuando Nixie
confirma una clase de prueba o una reserva.

Requiere una Service Account de Google Cloud con acceso al calendar
de FENIX Kids (configurado en GOOGLE_CALENDAR_ID).
"""

import json
import logging
import os
from datetime import datetime, timedelta, date

logger = logging.getLogger("agentkit")

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "config/google_credentials_fenix.json")

# Días de la semana en español → número Python (0=lunes)
_DIAS_SEMANA: dict[str, int] = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}

# Palabras clave que indican confirmación de horario + día concreto
_KEYWORDS_DIA = list(_DIAS_SEMANA.keys())
_HORARIOS_ACADEMIA = ["9:30", "09:30", "11:00", "15:30"]
_KEYWORDS_CONFIRMACION = [
    "anotad",           # "anotado/a"
    "confirmad",        # "confirmado/a"
    "reservad",         # "reservado/a"
    "te espero",        # "te espero el..."
    "te esperamos",     # "te esperamos el..." ← forma común que usa Nixie
    "primera clase",
    "quedás para",
    "quedas para",
    "nos vemos el",
    "nos vemos la",
    "te agend",         # "te agendé", "te agendo"
    "quedaste",
    "quedás confirm",
    "quedas confirm",
]


def detectar_confirmacion_horario(texto: str) -> bool:
    """
    Retorna True si el texto de la respuesta del agente indica que
    está confirmando un día y horario concreto al alumno.
    """
    t = texto.lower()
    tiene_dia          = any(d in t for d in _KEYWORDS_DIA)
    tiene_hora         = any(h in t for h in _HORARIOS_ACADEMIA)
    tiene_confirmacion = any(k in t for k in _KEYWORDS_CONFIRMACION)
    resultado          = tiene_dia and tiene_hora and tiene_confirmacion

    logger.info(
        f"[Calendar] detectar_confirmacion → dia={tiene_dia} hora={tiene_hora} "
        f"confirmacion={tiene_confirmacion} → {resultado}"
    )
    return resultado


def extraer_dia_hora_de_texto(texto: str) -> tuple[str, str] | tuple[None, None]:
    """
    Extrae el primer día de la semana y el primer horario que aparecen en el texto.
    Usado cuando keyword detection ya confirmó que están presentes,
    evitando una llamada a Haiku innecesaria.

    Returns:
        ("martes", "19:30") o (None, None) si no encuentra.
    """
    t = texto.lower()
    dia_encontrado  = next((d for d in _DIAS_SEMANA if d in t), None)
    hora_encontrada = next((h for h in _HORARIOS_ACADEMIA if h in t), None)
    return dia_encontrado, hora_encontrada


def _proxima_fecha(nombre_dia: str, hora_str: str) -> tuple[datetime, datetime]:
    """
    Calcula inicio y fin del próximo [nombre_dia] a la [hora_str] dada.
    Si el día es hoy y la clase todavía no empezó → usa hoy.
    Si el día es hoy y la clase ya empezó → usa la semana siguiente.

    Returns:
        (inicio, fin)  — el evento dura 1 hora
    """
    from zoneinfo import ZoneInfo

    dia_num = _DIAS_SEMANA.get(nombre_dia.lower().strip())
    if dia_num is None:
        raise ValueError(f"Día no reconocido: '{nombre_dia}'")

    # Normalizar hora: aceptar "9:30h", "09:30hs", "9h30", "9:30" → "9:30"
    hora_clean = hora_str.strip().lower().replace("hs", "").replace("h", ":").rstrip(":")

    tz_py    = ZoneInfo("America/Asuncion")
    ahora_py = datetime.now(tz_py)
    hoy      = ahora_py.date()

    dias_hasta = (dia_num - hoy.weekday()) % 7

    partes = hora_clean.split(":")
    hora_int = int(partes[0])
    minuto_int = int(partes[1]) if len(partes) > 1 and partes[1] else 0

    if dias_hasta == 0:
        # Hoy es el día correcto — verificar si la clase ya empezó
        hora_clase = ahora_py.replace(hour=hora_int, minute=minuto_int, second=0, microsecond=0)
        if ahora_py >= hora_clase:
            dias_hasta = 7  # clase ya empezó → próxima semana

    fecha_evento = hoy + timedelta(days=dias_hasta)

    inicio = datetime(fecha_evento.year, fecha_evento.month, fecha_evento.day,
                      hora_int, minuto_int)
    # Sábado a las 17:15 → cubre dos clases seguidas hasta las 19:30 (2h15m)
    if fecha_evento.weekday() == 5 and hora_int == 17 and minuto_int == 15:
        fin = datetime(fecha_evento.year, fecha_evento.month, fecha_evento.day, 19, 30)
    else:
        fin = inicio + timedelta(hours=1)
    return inicio, fin


def _get_service():
    """
    Retorna el servicio de Google Calendar autenticado con Service Account.

    Prioridad de credenciales:
    1. Variable de entorno GOOGLE_CREDENTIALS_JSON (Railway)
    2. Archivo local en GOOGLE_CREDENTIALS_PATH (desarrollo)
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    # Opción 1: JSON completo en variable de entorno (Railway)
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if credentials_json:
        info = json.loads(credentials_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build("calendar", "v3", credentials=creds)

    # Opción 2: archivo local (desarrollo)
    if os.path.exists(GOOGLE_CREDENTIALS_PATH):
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
        )
        return build("calendar", "v3", credentials=creds)

    raise FileNotFoundError(
        "Credenciales de Google no encontradas. "
        "Configurá GOOGLE_CREDENTIALS_JSON en Railway o "
        f"guardá el archivo en '{GOOGLE_CREDENTIALS_PATH}'."
    )


MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def fecha_proxima_texto(nombre_dia: str, hora_str: str) -> str:
    """
    Retorna texto legible como 'martes 8 de abril' para usar en mensajes al lead.
    En caso de error, retorna solo el nombre del día.
    """
    try:
        inicio, _ = _proxima_fecha(nombre_dia, hora_str)
        return f"{nombre_dia} {inicio.day} de {MESES_ES[inicio.month - 1]}"
    except Exception:
        return nombre_dia


async def extraer_datos_para_evento(historial: list[dict], telefono: str) -> dict | None:
    """
    Usa Claude Haiku para extraer del historial de conversación:
    nombre completo, día y horario confirmado.

    Returns:
        {"nombre": "...", "telefono": "...", "dia": "martes", "hora": "19:30"}
        o None si no se pueden extraer los datos mínimos.
    """
    from anthropic import AsyncAnthropic
    from dotenv import load_dotenv
    load_dotenv()

    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Usar los últimos 40 mensajes para tener contexto completo del registro
    conversacion = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in historial[-40:]
    )

    prompt = f"""Del siguiente historial de WhatsApp de una academia de baile,
extraé los datos del alumno en formato JSON estricto.

Reglas:
- "nombre_completo": nombre y apellido que el alumno proporcionó. Si solo dio nombre, usalo.
- "dia": día de la semana confirmado para la primera clase (en minúsculas, sin tilde). Ej: "martes", "sabado".
- "hora": horario confirmado en formato HH:MM. Ej: "19:30", "17:15".
- Si algún campo no está confirmado en la conversación, poné null.
- Respondé SOLO el JSON, sin texto adicional ni bloques de código.

Formato esperado:
{{"nombre_completo": "...", "dia": "...", "hora": "..."}}

Conversación:
{conversacion}"""

    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        texto = response.content[0].text.strip()

        # Limpiar bloques de código si los hay
        if "```" in texto:
            texto = texto.split("```")[1].replace("json", "").strip()

        datos = json.loads(texto)
        datos["telefono"] = telefono

        # Solo dia y hora son obligatorios para crear el evento.
        # El nombre puede llegar después (cuando el lead llena el formulario).
        if datos.get("dia") and datos.get("hora"):
            return datos

        logger.warning(f"[Calendar] Haiku no encontró dia/hora en el historial de {telefono}: {datos}")
        return None

    except Exception as e:
        logger.error(f"Error extrayendo datos del historial: {e}")
        return None


async def insertar_evento_google(dia: str, hora: str, telefono: str, nombre: str | None = None) -> dict | None:
    """
    Crea el evento en Google Calendar con dia/hora ya conocidos.
    No llama a Haiku — usa los datos directamente.
    Es la misma lógica que el endpoint /test/calendar pero con datos reales.

    Returns:
        dict con {dia, hora, telefono, nombre_completo} si OK, None si error.
    """
    try:
        import asyncio
        import traceback
        from googleapiclient.errors import HttpError

        inicio, fin   = _proxima_fecha(dia, hora)
        nombre_display = nombre or telefono

        evento = {
            "summary": f"FENIX Kids — {nombre_display} ({telefono})",
            "description": (
                f"Niño/a: {nombre_display}\n"
                f"Teléfono: {telefono}\n"
                f"Registrado via Nixie (FENIX Kids WhatsApp)"
            ),
            "start": {"dateTime": f"{inicio.strftime('%Y-%m-%dT%H:%M:%S')}-04:00", "timeZone": "America/Asuncion"},
            "end":   {"dateTime": f"{fin.strftime('%Y-%m-%dT%H:%M:%S')}-04:00",   "timeZone": "America/Asuncion"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 120},
                    {"method": "email", "minutes": 120},
                ],
            },
        }

        def _insertar():
            service = _get_service()
            return service.events().insert(
                calendarId=GOOGLE_CALENDAR_ID,
                body=evento,
            ).execute()

        print(f"[CALENDAR] Insertando evento directo: dia={dia} hora={hora} calendarId={GOOGLE_CALENDAR_ID}", flush=True)
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, _insertar)

        link     = resultado.get("htmlLink", "")
        event_id = resultado.get("id", "")
        print(f"[CALENDAR] ✅ Evento insertado — id={event_id} link={link}", flush=True)
        logger.info(f"[Calendar] Evento creado: {nombre_display} {dia} {hora} → {link}")
        return {"dia": dia, "hora": hora, "telefono": telefono, "nombre_completo": nombre, "evento_link": link, "evento_id": event_id}

    except HttpError as e:
        print(f"[CALENDAR] ❌ HttpError {e.status_code}: {e.reason}", flush=True)
        logger.error(f"[Calendar] HttpError {e.status_code}: {e.reason} — {e.content[:300]}")
        return None
    except Exception as e:
        import traceback
        print(f"[CALENDAR] ❌ {type(e).__name__}: {e}", flush=True)
        logger.error(f"[Calendar] Error: {traceback.format_exc()}")
        return None


async def crear_evento_primera_clase(historial: list[dict], telefono: str) -> dict | None:
    """
    Extrae los datos del alumno del historial y crea el evento en Google Calendar.

    El evento incluye:
    - Título: "FENIX Kids — [Nombre] ([teléfono])"
    - Descripción: nombre completo y teléfono
    - Duración: 1 hora
    - Recordatorio: 2 horas antes (popup + email)
    - Zona horaria: America/Asuncion

    Returns:
        dict con {"nombre_completo", "dia", "hora", "telefono"} si el evento
        fue creado exitosamente, None si hubo error o datos insuficientes.
        (Retornar el dict en lugar de bool permite al caller enviar notificaciones)
    """
    datos = await extraer_datos_para_evento(historial, telefono)
    if not datos:
        logger.warning(f"[Calendar] No se creó evento para {telefono}: Haiku no encontró dia/hora en el historial")
        print(f"[CALENDAR] ❌ crear_evento_primera_clase abortado para {telefono}: sin dia/hora", flush=True)
        return None

    print(f"[CALENDAR] Haiku extrajo datos para {telefono}: {datos}", flush=True)

    try:
        import asyncio
        import traceback
        from googleapiclient.errors import HttpError

        inicio, fin = _proxima_fecha(datos["dia"], datos["hora"])
        nombre_display = datos.get("nombre_completo") or datos["telefono"]

        evento = {
            "summary": f"FENIX Kids — {nombre_display} ({datos['telefono']})",
            "description": (
                f"Niño/a: {nombre_display}\n"
                f"Teléfono: {datos['telefono']}\n"
                f"Registrado via Nixie (FENIX Kids WhatsApp)"
            ),
            "start": {"dateTime": f"{inicio.strftime('%Y-%m-%dT%H:%M:%S')}-04:00", "timeZone": "America/Asuncion"},
            "end":   {"dateTime": f"{fin.strftime('%Y-%m-%dT%H:%M:%S')}-04:00",   "timeZone": "America/Asuncion"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 120},
                    {"method": "email", "minutes": 120},
                ],
            },
        }

        # Ejecutar en thread para no bloquear el event loop async de Railway
        def _insertar():
            service = _get_service()
            return service.events().insert(
                calendarId=GOOGLE_CALENDAR_ID,
                body=evento,
            ).execute()

        print(f"[CALENDAR] Llamando Google API (calendarId={GOOGLE_CALENDAR_ID})...", flush=True)
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, _insertar)

        link = resultado.get("htmlLink", "")
        print(f"[CALENDAR] ✅ Evento insertado — link={link}", flush=True)
        logger.info(f"[Calendar] Evento creado: {nombre_display} ({datos['dia']} {datos['hora']}) → {link}")
        datos["evento_link"] = link
        return datos

    except FileNotFoundError as e:
        print(f"[CALENDAR] ❌ Credenciales no encontradas: {e}", flush=True)
        logger.error(f"[Calendar] Credenciales no encontradas: {e}")
        return None
    except HttpError as e:
        print(f"[CALENDAR] ❌ HttpError {e.status_code}: {e.reason} — contenido: {e.content[:300]}", flush=True)
        logger.error(f"[Calendar] HttpError {e.status_code}: {e.reason} — {e.content[:300]}")
        return None
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[CALENDAR] ❌ {type(e).__name__}: {e}\n{tb}", flush=True)
        logger.error(f"[Calendar] Error inesperado:\n{tb}")
        return None


def _extraer_nombre_dia(dia: str) -> str:
    """
    Extrae el nombre del día de la semana de strings como:
      'martes 7 de abril'  → 'martes'
      'martes 7'           → 'martes'
      '7 de abril'         → busca el día de semana para esa fecha
      'martes'             → 'martes'

    Retorna el nombre del día en minúsculas, sin tilde normalizada para _proxima_fecha().
    """
    t = dia.strip().lower()

    # Intentar encontrar un nombre de día de semana en el string
    for nombre in _DIAS_SEMANA:
        if nombre in t:
            return nombre

    # No hay nombre de día — intentar parsear fecha numérica 'N de mes' o 'N/M'
    _MESES_ES = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    import re as _re
    from datetime import date as _date
    # Formato 'N de mes'
    m = _re.search(r'(\d{1,2})\s+de\s+(\w+)', t)
    if m:
        dia_num = int(m.group(1))
        mes_nombre = m.group(2)
        mes_num = _MESES_ES.get(mes_nombre)
        if mes_num:
            anio = _date.today().year
            try:
                fecha = _date(anio, mes_num, dia_num)
                return list(_DIAS_SEMANA.keys())[fecha.weekday()]
            except ValueError:
                pass

    # Fallback: retornar el string original (dejará que _proxima_fecha falle con error claro)
    return t


def fecha_iso_from_dia_hora(dia: str, hora: str) -> str:
    """
    Retorna ISO 8601 del próximo [dia] a la [hora], en zona horaria de Paraguay.
    Usa el offset real de America/Asuncion (UTC-3 en verano, UTC-4 en invierno).
    Formato: YYYY-MM-DDTHH:MM:SS-03:00  o  YYYY-MM-DDTHH:MM:SS-04:00

    Acepta variantes de dia:
      'martes'             → próximo martes
      'martes 7 de abril'  → extrae 'martes', calcula próxima ocurrencia
      'martes 7'           → extrae 'martes'
      '7 de abril'         → determina el día de semana de esa fecha
      '**martes 7 de abril' → limpia asteriscos de markdown antes de procesar
    """
    from zoneinfo import ZoneInfo
    # Limpiar asteriscos de markdown y espacios extra
    dia = dia.strip().lstrip('*').strip()
    nombre_dia = _extraer_nombre_dia(dia)
    inicio, _ = _proxima_fecha(nombre_dia, hora)
    # Aplicar timezone real de Paraguay (respeta DST automáticamente)
    tz_py = ZoneInfo("America/Asuncion")
    inicio_aware = inicio.replace(tzinfo=tz_py)
    offset = inicio_aware.strftime("%z")  # "-0300" o "-0400"
    offset_fmt = f"{offset[:3]}:{offset[3:]}"  # "-03:00" o "-04:00"
    return f"{inicio.strftime('%Y-%m-%dT%H:%M:%S')}{offset_fmt}"


# Número de weekday Python → nombre en español
_DIAS_NUM_A_ESP: dict[int, str] = {
    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
    4: "viernes", 5: "sábado", 6: "domingo",
}


async def insertar_evento_desde_fecha_iso(
    fecha_iso: str,
    telefono: str,
    nombre: str | None = None,
) -> dict | None:
    """
    Crea un evento en Google Calendar a partir de un string ISO 8601 con offset -04:00.
    fecha_iso: "YYYY-MM-DDTHH:MM:SS-04:00"

    Returns:
        {"evento_link": ..., "evento_id": ..., "dia": "martes", "hora": "19:30"} o None.
    """
    try:
        import asyncio
        from googleapiclient.errors import HttpError
        from zoneinfo import ZoneInfo

        tz_py = ZoneInfo("America/Asuncion")

        # Airtable devuelve el ISO en UTC ("...Z" o "....000Z") — convertir a hora local Paraguay
        fecha_norm = fecha_iso.replace(".000Z", "+00:00").replace("Z", "+00:00") if "Z" in fecha_iso else fecha_iso
        dt_aware = datetime.fromisoformat(fecha_norm)
        dt_py    = dt_aware.astimezone(tz_py)
        inicio   = dt_py.replace(tzinfo=None)  # naive, hora local Paraguay (ej: 19:30)

        # Offset real de Paraguay en esa fecha (respeta DST: -03:00 o -04:00)
        py_offset     = dt_py.strftime("%z")           # "-0300" o "-0400"
        py_offset_fmt = f"{py_offset[:3]}:{py_offset[3:]}"  # "-03:00" o "-04:00"

        # Duración: sábado 17:15 cubre dos clases (hasta 19:30 = 135 min), resto 1 hora
        if inicio.weekday() == 5 and inicio.hour == 17 and inicio.minute == 15:
            fin        = datetime(inicio.year, inicio.month, inicio.day, 19, 30)
            duracion_min = 135
        else:
            fin        = inicio + timedelta(hours=1)
            duracion_min = 60

        nombre_display = nombre or telefono
        dia_nombre = _DIAS_NUM_A_ESP.get(inicio.weekday(), "")
        hora_str   = f"{inicio.hour:02d}:{inicio.minute:02d}"

        evento = {
            "summary": f"FENIX Kids — {nombre_display} ({telefono})",
            "description": (
                f"Niño/a: {nombre_display}\n"
                f"Teléfono: {telefono}\n"
                f"Registrado via Nixie (FENIX Kids WhatsApp)"
            ),
            "start": {"dateTime": f"{inicio.strftime('%Y-%m-%dT%H:%M:%S')}{py_offset_fmt}", "timeZone": "America/Asuncion"},
            "end":   {"dateTime": f"{fin.strftime('%Y-%m-%dT%H:%M:%S')}{py_offset_fmt}",   "timeZone": "America/Asuncion"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 120},
                    {"method": "email", "minutes": 120},
                ],
            },
        }

        def _insertar():
            service = _get_service()
            return service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=evento).execute()

        print(f"[CALENDAR] Insertando evento desde ISO: {fecha_iso} calendarId={GOOGLE_CALENDAR_ID}", flush=True)
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, _insertar)

        html_link = resultado.get("htmlLink", "")
        event_id  = resultado.get("id", "")
        add_to_cal_link = generar_link_add_to_calendar(fecha_iso, duracion_min)
        print(f"[CALENDAR] ✅ Evento insertado — id={event_id} link_interno={html_link}", flush=True)
        logger.info(f"[Calendar] Evento creado desde ISO {fecha_iso} → {html_link}")
        return {"evento_link": add_to_cal_link, "evento_id": event_id, "dia": dia_nombre, "hora": hora_str}

    except HttpError as e:
        print(f"[CALENDAR] ❌ HttpError {e.status_code}: {e.reason}", flush=True)
        logger.error(f"[Calendar] HttpError {e.status_code}: {e.reason}")
        return None
    except Exception as e:
        import traceback
        print(f"[CALENDAR] ❌ {type(e).__name__}: {e}", flush=True)
        logger.error(f"[Calendar] Error: {traceback.format_exc()}")
        return None


def generar_link_add_to_calendar(fecha_iso: str, duracion_min: int = 60) -> str:
    """
    Genera un link para que el lead agregue el evento a su propio Google Calendar.
    No requiere que el lead tenga ninguna cuenta vinculada — abre el formulario
    de Google Calendar con el título y fecha/hora precargados.

    Formato: https://calendar.google.com/calendar/render?action=TEMPLATE&text=...&dates=...
    Usa tiempos en UTC con sufijo Z para evitar ambigüedad de zona horaria.
    """
    from urllib.parse import urlencode
    from datetime import timezone

    # Parsear el ISO con su offset (-04:00) y convertir a UTC
    dt_aware = datetime.fromisoformat(fecha_iso)
    dt_utc   = dt_aware.astimezone(timezone.utc)
    fin_utc  = dt_utc + timedelta(minutes=duracion_min)

    fmt = "%Y%m%dT%H%M%SZ"
    params = {
        "action": "TEMPLATE",
        "text":   "FENIX Kids Academy — Clase",
        "dates":  f"{dt_utc.strftime(fmt)}/{fin_utc.strftime(fmt)}",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


async def borrar_evento_google(event_id: str) -> bool:
    """
    Elimina un evento de Google Calendar por su ID.
    Usado para reschedules: borrar el evento anterior antes de crear uno nuevo.
    """
    if not event_id:
        return False
    try:
        import asyncio as _asyncio
        from googleapiclient.errors import HttpError

        def _borrar():
            service = _get_service()
            service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()

        loop = _asyncio.get_event_loop()
        await loop.run_in_executor(None, _borrar)
        print(f"[CALENDAR] 🗑️ Evento eliminado: id={event_id}", flush=True)
        logger.info(f"[Calendar] Evento eliminado: {event_id}")
        return True
    except Exception as e:
        print(f"[CALENDAR] ⚠️ No se pudo eliminar evento {event_id}: {e}", flush=True)
        logger.warning(f"[Calendar] Error al eliminar evento {event_id}: {e}")
        return False
