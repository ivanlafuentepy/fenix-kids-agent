# agent/telegram_bridge.py — Integración con Telegram
# FENIX KIDS ACADEMY

"""
Espejo bidireccional entre WhatsApp y Telegram.

Requisitos en Telegram:
  1. El grupo debe tener "Topics" activados (modo Foro).
  2. El bot debe ser administrador con permiso "Gestionar temas".
"""

import os
import logging
import httpx
from datetime import datetime, timedelta
from sqlalchemy import select
from agent.memory import async_session, TopicTelegram

logger = logging.getLogger("agentkit")

MINUTOS_SILENCIO = 5

# Números que no se espejan a Telegram (pruebas del admin)
TELEGRAM_IGNORE_PHONES = set(
    p.strip() for p in os.getenv("TELEGRAM_IGNORE_PHONES", "").split(",") if p.strip()
)


def _token() -> str:
    """Lee el token en cada llamada para evitar problemas de orden de carga."""
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _group_id() -> int:
    """Grupo de leads (Profe Ivan)."""
    return int(os.getenv("TELEGRAM_GROUP_ID", "0"))


def _group_id_flias() -> int:
    """Grupo de familias inscriptas (Aurora)."""
    return int(os.getenv("TELEGRAM_GROUP_ID_FLIAS", "0"))


def group_id_para_agente(agent_actual: str) -> int:
    """Retorna el group_id según el agente. Aurora → FLIAS, Ivan → LEADS."""
    if agent_actual == "aurora":
        gid = _group_id_flias()
        return gid if gid else _group_id()  # fallback a leads si no hay FLIAS
    return _group_id()


def _api_url(metodo: str) -> str:
    return f"https://api.telegram.org/bot{_token()}/{metodo}"


def _telegram_ok() -> bool:
    """Verifica que las credenciales de Telegram están configuradas."""
    token = _token()
    group = _group_id()
    print(
        f"[TELEGRAM] _telegram_ok check — TOKEN={'OK ('+token[:8]+')' if token else '*** VACÍO ***'} "
        f"GROUP_ID={group if group else '*** VACÍO ***'}",
        flush=True
    )
    if not token or not group:
        return False
    return True


# ── DB ────────────────────────────────────────────────────────────────────────

async def obtener_topic(telefono: str) -> TopicTelegram | None:
    """Retorna el primer topic para este teléfono (cualquier grupo)."""
    async with async_session() as session:
        result = await session.execute(
            select(TopicTelegram).where(TopicTelegram.telefono == telefono)
        )
        return result.scalars().first()



async def obtener_telefono_por_topic(topic_id: int) -> str | None:
    async with async_session() as session:
        result = await session.execute(
            select(TopicTelegram.telefono).where(TopicTelegram.topic_id == topic_id)
        )
        return result.scalar_one_or_none()


async def silenciar_dorita(telefono: str):
    async with async_session() as session:
        result = await session.execute(
            select(TopicTelegram).where(TopicTelegram.telefono == telefono)
        )
        topic = result.scalar_one_or_none()
        if topic:
            topic.agente_silenciado = True
            topic.ultimo_mensaje_ivan = datetime.utcnow()
            await session.commit()
            logger.info(f"[Telegram] Agente silenciado para {telefono}")


async def reactivar_dorita(telefono: str):
    async with async_session() as session:
        result = await session.execute(
            select(TopicTelegram).where(TopicTelegram.telefono == telefono)
        )
        topic = result.scalar_one_or_none()
        if topic:
            topic.agente_silenciado = False
            topic.ultimo_mensaje_ivan = None
            await session.commit()
            logger.info(f"[Telegram] Agente reactivado para {telefono}")


async def dorita_esta_activa(telefono: str) -> bool:
    topic = await obtener_topic(telefono)
    if not topic or not topic.agente_silenciado:
        return True
    if topic.ultimo_mensaje_ivan:
        transcurrido = datetime.utcnow() - topic.ultimo_mensaje_ivan
        if transcurrido >= timedelta(minutes=MINUTOS_SILENCIO):
            await reactivar_dorita(telefono)
            return True
    return False


# ── Telegram API ──────────────────────────────────────────────────────────────

async def _crear_topic_api(nombre: str, group_override: int = 0) -> int | None:
    """Crea un topic en el grupo. Logea la respuesta completa de Telegram."""
    group = group_override or _group_id()
    url = _api_url("createForumTopic")
    payload = {"chat_id": group, "name": nombre[:128]}

    print(f"[TELEGRAM] createForumTopic → chat_id={group}, name='{nombre[:40]}'", flush=True)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            print(f"[TELEGRAM] createForumTopic HTTP {r.status_code} → {data}", flush=True)
            if data.get("ok"):
                topic_id = data["result"]["message_thread_id"]
                print(f"[TELEGRAM] Topic creado OK: id={topic_id}", flush=True)
                return topic_id
            print(
                f"[TELEGRAM] createForumTopic FALLÓ: "
                f"error_code={data.get('error_code')} — {data.get('description')}",
                flush=True
            )
            return None
    except Exception as e:
        print(f"[TELEGRAM] Excepción en createForumTopic: {e}", flush=True)
        return None


async def obtener_o_crear_topic(telefono: str, nombre: str, group_override: int = 0) -> int | None:
    """
    Un solo topic por teléfono. Si el grupo cambió (lead→familia o vice versa),
    crea topic nuevo en el grupo correcto y actualiza el registro.
    """
    group = group_override or _group_id()
    print(f"[TELEGRAM] obtener_o_crear_topic para {telefono} en grupo {group}", flush=True)

    if not _token() or not group:
        print("[TELEGRAM] token o group vacío, saliendo", flush=True)
        return None

    if telefono in TELEGRAM_IGNORE_PHONES:
        print(f"[TELEGRAM] {telefono} en IGNORE_PHONES, no se espeja", flush=True)
        return None

    # Buscar topic existente para este teléfono (cualquier grupo)
    topic = await obtener_topic(telefono)
    if topic:
        # group_id=0 es legacy (pre-migración) → tratar como grupo de leads
        topic_group = topic.group_id if topic.group_id else _group_id()
        if topic_group == group:
            # Mismo grupo → usar el topic existente (actualizar group_id si era 0)
            if not topic.group_id:
                async with async_session() as session:
                    result = await session.execute(
                        select(TopicTelegram).where(TopicTelegram.telefono == telefono)
                    )
                    t = result.scalars().first()
                    if t:
                        t.group_id = group
                        await session.commit()
            print(f"[TELEGRAM] Topic existente para {telefono}: id={topic.topic_id}", flush=True)
            return topic.topic_id

        # Grupo cambió (ej: lead→familia) → crear topic en el nuevo grupo
        print(f"[TELEGRAM] Grupo cambió para {telefono}: {topic_group} → {group} — creando topic nuevo", flush=True)
        nuevo_topic_id = await _crear_topic_api(nombre, group_override=group)
        if nuevo_topic_id is None:
            # Fallback: usar el topic viejo si no se pudo crear el nuevo
            print(f"[TELEGRAM] No se pudo crear topic en grupo nuevo, usando el existente", flush=True)
            return topic.topic_id

        # Cerrar el topic viejo en el grupo anterior (best-effort)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    _api_url("closeForumTopic"),
                    json={"chat_id": topic_group, "message_thread_id": topic.topic_id},
                )
            print(f"[TELEGRAM] Topic viejo cerrado: {topic.topic_id} en grupo {topic_group}", flush=True)
        except Exception:
            pass

        # Actualizar el registro (un solo topic por teléfono)
        async with async_session() as session:
            result = await session.execute(
                select(TopicTelegram).where(TopicTelegram.telefono == telefono)
            )
            existente = result.scalars().first()
            if existente:
                existente.topic_id = nuevo_topic_id
                existente.group_id = group
                existente.nombre = nombre
                await session.commit()

        print(f"[TELEGRAM] Topic migrado: {telefono} → topic_id={nuevo_topic_id} grupo={group}", flush=True)
        return nuevo_topic_id

    # No existe → crear topic nuevo
    print(f"[TELEGRAM] Sin topic previo para {telefono} — creando...", flush=True)
    topic_id = await _crear_topic_api(nombre, group_override=group)
    if topic_id is None:
        print(f"[TELEGRAM] No se pudo crear topic para {telefono}", flush=True)
        return None

    async with async_session() as session:
        session.add(TopicTelegram(
            telefono=telefono,
            topic_id=topic_id,
            nombre=nombre,
            group_id=group,
        ))
        await session.commit()

    print(f"[TELEGRAM] Topic guardado en DB: {telefono} → topic_id={topic_id} grupo={group}", flush=True)
    return topic_id


async def _borrar_topic_db(telefono: str, topic_id_fallido: int):
    """
    Elimina el registro de topic de la DB SOLO si el topic_id almacenado
    coincide con el que falló. Evita borrar un topic recién recreado por
    una coroutine concurrente.
    """
    async with async_session() as session:
        result = await session.execute(
            select(TopicTelegram).where(TopicTelegram.telefono == telefono)
        )
        topic = result.scalar_one_or_none()
        if topic and topic.topic_id == topic_id_fallido:
            await session.delete(topic)
            await session.commit()
            print(f"[TELEGRAM] Topic DB eliminado para {telefono} topic_id={topic_id_fallido} (forzar recreación)", flush=True)
        elif topic and topic.topic_id != topic_id_fallido:
            print(
                f"[TELEGRAM] _borrar_topic_db: topic en DB ya es {topic.topic_id} "
                f"(falló {topic_id_fallido}) — no se borra (ya fue recreado)", flush=True
            )


async def enviar_media_a_topic(
    topic_id: int,
    media_bytes: bytes,
    tipo: str,
    caption: str = "",
    telefono: str | None = None,
    group_override: int = 0,
) -> bool:
    """
    Reenvía una imagen o documento al topic de Telegram.
    tipo: "imagen" → sendPhoto, "documento" → sendDocument
    """
    group = group_override or _group_id()
    if not _token() or not group:
        return False
    metodo = "sendPhoto" if tipo == "imagen" else "sendDocument"
    campo  = "photo"     if tipo == "imagen" else "document"
    url    = _api_url(metodo)

    data_fields = {
        "chat_id":           str(group),
        "message_thread_id": str(topic_id),
    }
    if caption:
        data_fields["caption"] = caption

    nombre_archivo = "imagen.jpg" if tipo == "imagen" else "documento"
    mime            = "image/jpeg" if tipo == "imagen" else "application/octet-stream"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                url,
                data=data_fields,
                files={campo: (nombre_archivo, media_bytes, mime)},
            )
            data = r.json()
            if data.get("ok"):
                print(f"[TELEGRAM] {metodo} OK → topic={topic_id}", flush=True)
                return True
            print(f"[TELEGRAM] {metodo} FALLÓ: {data}", flush=True)
            return False
    except Exception as e:
        print(f"[TELEGRAM] Excepción en {metodo}: {e}", flush=True)
        return False


async def enviar_a_topic(topic_id: int, texto: str, telefono: str | None = None, group_override: int = 0) -> bool:
    """
    Envía un mensaje a un topic.
    Si recibe HTTP 400 'message thread not found' y se pasa telefono,
    elimina el topic de la DB y lo recrea automáticamente antes de reintentar.
    """
    group = group_override or _group_id()
    if not _token() or not group:
        return False
    url = _api_url("sendMessage")
    payload = {
        "chat_id": group,
        "message_thread_id": topic_id,
        "text": texto,
    }

    print(f"[TELEGRAM] sendMessage → topic_id={topic_id}, texto='{texto[:60]}'", flush=True)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if data.get("ok"):
                print(f"[TELEGRAM] sendMessage OK → message_id={data['result'].get('message_id')}", flush=True)
                return True

            print(
                f"[TELEGRAM] sendMessage FALLÓ HTTP {r.status_code}: "
                f"error_code={data.get('error_code')} — {data.get('description')}",
                flush=True
            )

            # Si el topic ya no existe y tenemos el teléfono, recrearlo y reintentar
            if r.status_code == 400 and "message thread not found" in data.get("description", "") and telefono:
                print(f"[TELEGRAM] Topic {topic_id} no encontrado — recreando para {telefono}", flush=True)
                await _borrar_topic_db(telefono, topic_id)
                nuevo_topic_id = await _crear_topic_api(f"📱 {telefono}", group_override=group)
                if nuevo_topic_id:
                    async with async_session() as session:
                        # Upsert: puede que otra coroutine ya haya recreado el topic
                        result2 = await session.execute(
                            select(TopicTelegram).where(TopicTelegram.telefono == telefono)
                        )
                        existente = result2.scalars().first()
                        if existente:
                            existente.topic_id = nuevo_topic_id
                            existente.group_id = group
                            existente.nombre = f"📱 {telefono}"
                        else:
                            session.add(TopicTelegram(
                                telefono=telefono,
                                topic_id=nuevo_topic_id,
                                nombre=f"📱 {telefono}",
                                group_id=group,
                            ))
                        await session.commit()
                    print(f"[TELEGRAM] Topic recreado: {nuevo_topic_id} — reintentando envío", flush=True)
                    payload["message_thread_id"] = nuevo_topic_id
                    r2 = await client.post(url, json=payload)
                    data2 = r2.json()
                    if data2.get("ok"):
                        print(f"[TELEGRAM] Reintento OK → message_id={data2['result'].get('message_id')}", flush=True)
                        return True
                    print(f"[TELEGRAM] Reintento FALLÓ: {data2}", flush=True)

            return False
    except Exception as e:
        print(f"[TELEGRAM] Excepción en sendMessage: {e}", flush=True)
        return False


async def notificar_referido_telegram(
    lead_nombre_completo: str,
    referidor_nombre_completo: str,
    referidor_link_whatsapp: str,
    dia: str | None,
    hora: str | None,
) -> bool:
    """
    Envía notificación al grupo 'Referidos Salsa Soul' cuando un lead referido
    agenda o paga. Usa TELEGRAM_REFERIDOS_SALSA_SOUL_CHAT_ID.
    """
    chat_id = int(os.getenv("TELEGRAM_REFERIDOS_SALSA_SOUL_CHAT_ID", "0"))
    token = _token()
    if not token or not chat_id:
        logger.warning("[Telegram] TELEGRAM_REFERIDOS_SALSA_SOUL_CHAT_ID no configurado — notif referido omitida")
        return False

    if dia and hora:
        fecha_display = f"{dia} a las {hora}"
    else:
        fecha_display = "fecha a confirmar"

    primer_nombre_referidor = referidor_nombre_completo.split()[0] if referidor_nombre_completo else referidor_nombre_completo

    msg_wa = (
        f"Hola {primer_nombre_referidor} 👋\n\n"
        f"{lead_nombre_completo} se registró con tu link de referido "
        f"para una clase de prueba gratuita.\n\n"
        f"📅 Clase agendada para el {fecha_display}.\n\n"
        f"Te estaremos teniendo al tanto si viene a probar y si se inscribe eventualmente.\n\n"
        f"¡Muchísimas gracias por ayudarnos a crecer! 🙌 "
        f"Esperamos poder recibir más referidos de tu parte."
    )

    if referidor_link_whatsapp:
        from urllib.parse import quote
        wa_link = f"{referidor_link_whatsapp}?text={quote(msg_wa)}"
        wa_referidor = f"\n📲 WhatsApp del referidor: {wa_link}"
    else:
        wa_referidor = ""

    texto = (
        f"Hola {primer_nombre_referidor} 👋\n\n"
        f"{lead_nombre_completo} se registró con tu link de referido "
        f"para una clase de prueba gratuita.\n\n"
        f"📅 Clase agendada para el {fecha_display}."
        f"{wa_referidor}\n\n"
        f"Te estaremos teniendo al tanto si viene a probar y si se inscribe eventualmente.\n\n"
        f"¡Muchísimas gracias por ayudarnos a crecer! 🙌 "
        f"Esperamos poder recibir más referidos de tu parte."
    )

    url = _api_url("sendMessage")
    payload = {"chat_id": chat_id, "text": texto}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if data.get("ok"):
                print(f"[TELEGRAM] notif_referido OK → {referidor_nombre_completo}", flush=True)
                return True
            print(f"[TELEGRAM] notif_referido FALLÓ: {data}", flush=True)
            return False
    except Exception as e:
        logger.error(f"[Telegram] Error notif referido: {e}")
        return False


async def notificar_agenda_telegram(
    telefono: str,
    dia: str | None,
    hora: str | None,
    nombre: str | None = None,
    nombre_hijos: str | None = None,
    agente: str = "ivan",
) -> bool:
    """
    Envía notificación de nueva agenda al grupo de Telegram de notificaciones.
    Usa TELEGRAM_AGENDA_GROUP_ID (grupo separado del de topics/espejo).
    """
    agenda_group_id = int(os.getenv("TELEGRAM_AGENDA_GROUP_ID", "0"))
    token = _token()
    if not token or not agenda_group_id:
        logger.warning("[Telegram] TELEGRAM_AGENDA_GROUP_ID no configurado — notif omitida")
        return False

    if dia and hora:
        fecha_display = f"{dia} a las {hora}"
    else:
        fecha_display = "fecha a confirmar"

    nombre_display = nombre or telefono
    primer_nombre = (nombre or "").split()[0] if nombre else ""

    # Mensaje wa.me personalizado según agente
    saludo = f"Hola {primer_nombre}, " if primer_nombre else "Hola, "
    if agente == "aurora":
        intro = "me contó Aurora que reservaste"
    else:
        intro = "te saluda el profe Ivan de Fenix Kids. Recibí tu reserva"
    fecha_parte = f" para el {dia or ''} a las {hora or ''}" if dia else ""
    if nombre_hijos:
        wa_text_preescrito = (
            f"{saludo}{intro}{fecha_parte}. "
            f"Le espero a {nombre_hijos} para descuearle con todo! 🔥🌳"
        )
    else:
        wa_text_preescrito = (
            f"{saludo}{intro}{fecha_parte}. "
            f"Los espero para descuearle con todo! 🔥🌳"
        )

    from urllib.parse import quote
    wa_link = f"https://wa.me/{telefono}?text={quote(wa_text_preescrito)}"

    # Link al topic de Telegram de este lead
    tg_link = ""
    try:
        topic = await obtener_topic(telefono)
        if topic and topic.topic_id and topic.group_id:
            gid = str(topic.group_id).replace("-100", "", 1)
            tg_link = f"\n💬 https://t.me/c/{gid}/{topic.topic_id}"
    except Exception:
        pass

    texto = (
        f"📅 {nombre_display} agendó para el {fecha_display}\n"
        f"📱 {wa_link}"
        f"{tg_link}"
    )

    url = _api_url("sendMessage")
    payload = {"chat_id": agenda_group_id, "text": texto}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if data.get("ok"):
                print(f"[TELEGRAM] notif_agenda OK → {nombre_display}", flush=True)
                return True
            print(f"[TELEGRAM] notif_agenda FALLÓ: {data}", flush=True)
            return False
    except Exception as e:
        logger.error(f"[Telegram] Error notificación agenda: {e}")
        return False


async def notificar_pago_telegram(
    telefono: str,
    nombre: str,
    estado: str,
    tipo: str = "",
    monto: int = 0,
) -> bool:
    """
    Envía notificación de pago al grupo de Telegram.
    estado: "comprobante_recibido", "confirmado", "rechazado"
    """
    agenda_group_id = int(os.getenv("TELEGRAM_AGENDA_GROUP_ID", "0"))
    token = _token()
    if not token or not agenda_group_id:
        logger.warning("[Telegram] TELEGRAM_AGENDA_GROUP_ID no configurado — notif pago omitida")
        return False

    monto_fmt = f"{monto:,}".replace(",", ".") if monto else ""

    if estado == "comprobante_recibido":
        emoji = "💳"
        titulo = "COMPROBANTE RECIBIDO"
        extra = f"\n💰 Tipo: {tipo}\n⏳ Esperando confirmación del admin"
    elif estado == "confirmado":
        emoji = "✅"
        titulo = "PAGO CONFIRMADO"
        extra = f"\n💰 {tipo} — {monto_fmt} Gs" if monto_fmt else f"\n💰 {tipo}"
    elif estado == "rechazado":
        emoji = "❌"
        titulo = "PAGO RECHAZADO"
        extra = f"\n💰 {tipo}"
    else:
        return False

    wa_link = f"https://wa.me/{telefono}"

    # Link al topic de Telegram de este lead
    tg_link = ""
    try:
        topic = await obtener_topic(telefono)
        if topic and topic.topic_id and topic.group_id:
            # Convertir group_id negativo (-100XXXXXXXXXX) a ID interno para t.me/c/
            gid = str(topic.group_id).replace("-100", "", 1)
            tg_link = f"\n💬 https://t.me/c/{gid}/{topic.topic_id}"
    except Exception:
        pass

    texto = (
        f"{emoji} {titulo}\n\n"
        f"👤 {nombre}\n"
        f"📱 {telefono}"
        f"{extra}\n\n"
        f"📲 {wa_link}"
        f"{tg_link}"
    )

    url = _api_url("sendMessage")
    payload = {"chat_id": agenda_group_id, "text": texto}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if data.get("ok"):
                print(f"[TELEGRAM] notif_pago OK → {estado} {telefono}", flush=True)
                return True
            print(f"[TELEGRAM] notif_pago FALLÓ: {data}", flush=True)
            return False
    except Exception as e:
        logger.error(f"[Telegram] Error notif pago: {e}")
        return False


async def notificar_llamada_urgente(telefono: str, nombre: str, wa_link: str) -> bool:
    """
    Envía alerta al grupo de Telegram cuando un lead pide hablar por teléfono.
    Usa TELEGRAM_AGENDA_GROUP_ID (mismo grupo que notificaciones de agenda).
    """
    agenda_group_id = int(os.getenv("TELEGRAM_AGENDA_GROUP_ID", "0"))
    token = _token()
    if not token or not agenda_group_id:
        logger.warning("[Telegram] TELEGRAM_AGENDA_GROUP_ID no configurado — alerta llamada omitida")
        return False

    texto = (
        f"🚨 URGENTE — UN PADRE FENIX QUIERE HABLAR CONTIGO\n\n"
        f"👤 {nombre}\n"
        f"📱 {telefono}\n\n"
        f"📲 {wa_link}"
    )

    url = _api_url("sendMessage")
    payload = {"chat_id": agenda_group_id, "text": texto}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if data.get("ok"):
                print(f"[TELEGRAM] notif_llamada_urgente OK → {telefono}", flush=True)
                return True
            print(f"[TELEGRAM] notif_llamada_urgente FALLÓ: {data}", flush=True)
            return False
    except Exception as e:
        logger.error(f"[Telegram] Error notif llamada urgente: {e}")
        return False


async def configurar_webhook(url_base: str) -> dict:
    """Registra el webhook de Telegram."""
    webhook_url = f"{url_base.rstrip('/')}/telegram/webhook"
    url = _api_url("setWebhook")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json={
            "url": webhook_url,
            "allowed_updates": ["message"],
        })
        data = r.json()
        logger.info(f"[Telegram] setWebhook → {data}")
        return data


async def obtener_info_webhook() -> dict:
    """Retorna info del webhook actual (para debugging)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(_api_url("getWebhookInfo"))
        return r.json()
