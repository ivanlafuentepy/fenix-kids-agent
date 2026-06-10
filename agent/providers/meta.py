# agent/providers/meta.py — Adaptador para Meta WhatsApp Cloud API
# Generado por AgentKit

import os
import hmac
import hashlib
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


def _registrar_fallo(status: int, texto_error: str, contexto: str):
    """Loguea un fallo de envío a Meta y lo reporta al monitor.

    El monitor de salud mira esto para detectar el token muerto (401) y avisar
    por Telegram. Import perezoso para evitar import circular meta↔monitor.
    """
    logger.error(f"Error Meta {contexto}: {status} — {texto_error}")
    try:
        from agent.monitor import registrar_error_meta
        registrar_error_meta(status, texto_error, contexto)
    except Exception as e:
        logger.warning(f"No se pudo registrar error Meta en monitor: {e}")


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando la API oficial de Meta (Cloud API)."""

    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("META_PHONE_NUMBER_ID")
        self.verify_token = os.getenv("META_VERIFY_TOKEN", "agentkit-verify")
        self.api_version = "v21.0"

    async def validar_webhook(self, request: Request) -> int | None:
        """Meta requiere verificación GET con hub.verify_token."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if mode == "subscribe" and token == self.verify_token:
            # Meta espera el challenge como respuesta en texto plano
            return int(challenge)
        return None

    def verificar_firma(self, body_bytes: bytes, firma_header: str | None) -> bool:
        """
        Valida la firma X-Hub-Signature-256 del webhook (HMAC-SHA256 con el App Secret).

        Sin META_APP_SECRET configurado no se puede validar → devuelve True
        (con warning) para no dejar a Fenix mudo por falta de config (fail-open).
        """
        app_secret = os.getenv("META_APP_SECRET", "")
        if not app_secret:
            logger.warning("[FIRMA] META_APP_SECRET no configurado — firma NO validada")
            return True
        if not firma_header or not firma_header.startswith("sha256="):
            return False
        esperada = hmac.new(app_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(esperada, firma_header[len("sha256="):])

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """
        Parsea el payload anidado de Meta Cloud API.

        Tipos reconocidos:
          text     → texto normal
          image    → imagen (posible comprobante) → texto = "[imagen]"
          document → documento (posible comprobante) → texto = "[documento]"
        """
        body = await request.json()
        mensajes = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                # Filtrar por phone_number_id — ignorar mensajes de otros números
                # (ej: Dorita comparte la misma app de Meta)
                webhook_phone_id = value.get("metadata", {}).get("phone_number_id", "")
                if self.phone_number_id and webhook_phone_id != self.phone_number_id:
                    logger.info(f"[META] Ignorando mensaje para phone_number_id={webhook_phone_id} (no es {self.phone_number_id})")
                    continue
                # Ignorar notificaciones de estado (delivered, read, etc.) — no son mensajes
                if value.get("statuses") and not value.get("messages"):
                    continue
                for msg in value.get("messages", []):
                    tipo = msg.get("type", "")
                    telefono = msg.get("from", "")
                    mensaje_id = msg.get("id", "")

                    media_id = None
                    es_boton = False
                    btn_id = None
                    _img_caption = ""
                    if tipo == "text":
                        texto = msg.get("text", {}).get("body", "")
                    elif tipo == "image":
                        media_id = msg.get("image", {}).get("id")
                        _img_caption = msg.get("image", {}).get("caption", "")
                        texto = "[imagen]"
                    elif tipo == "document":
                        media_id = msg.get("document", {}).get("id")
                        texto = "[documento]"
                    elif tipo == "audio":
                        media_id = msg.get("audio", {}).get("id")
                        texto = "[audio]"
                    elif tipo == "interactive":
                        # Respuesta a botón interactivo o ítem de lista
                        _interactive = msg.get("interactive", {})
                        _int_type = _interactive.get("type", "")
                        if _int_type == "list_reply":
                            # Ítem elegido en una lista desplegable
                            _list_reply = _interactive.get("list_reply", {})
                            texto = _list_reply.get("title", "") or _list_reply.get("id", "")
                            btn_id = _list_reply.get("id", "")
                        else:
                            # Botón de respuesta rápida
                            _btn_reply = _interactive.get("button_reply", {})
                            texto = _btn_reply.get("title", "") or _btn_reply.get("id", "")
                            btn_id = _btn_reply.get("id", "")
                        es_boton = True
                    elif tipo == "button":
                        # Quick reply de template
                        texto = msg.get("button", {}).get("text", "")
                        es_boton = True
                    elif tipo == "sticker":
                        continue  # stickers: ignorar silenciosamente
                    elif tipo in ("video", "location", "contacts", "reaction"):
                        continue  # tipos no soportados: ignorar
                    else:
                        continue  # cualquier otro tipo desconocido

                    # Capturar ctwa_clid y source_id del anuncio Click-to-WhatsApp
                    _referral = msg.get("referral", {})
                    _ctwa_clid = _referral.get("ctwa_clid") if _referral else None
                    _ad_source_id = _referral.get("source_id") if _referral else None

                    if texto:
                        mensajes.append(MensajeEntrante(
                            telefono=telefono,
                            texto=texto,
                            mensaje_id=mensaje_id,
                            es_propio=False,
                            media_id=media_id,
                            caption=_img_caption,
                            es_boton=es_boton,
                            btn_id=btn_id,
                            ctwa_clid=_ctwa_clid,
                            ad_source_id=_ad_source_id,
                        ))
        return mensajes

    async def enviar_botones(
        self,
        telefono: str,
        texto: str,
        botones: list[dict],
    ) -> bool:
        """Envía mensaje interactivo con botones via Meta WhatsApp Cloud API.
        botones: [{"id": "si", "title": "✅ Confirmar"}, {"id": "no", "title": "❌ Rechazar"}]
        """
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": b}
                        for b in botones
                    ],
                },
            },
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                _registrar_fallo(r.status_code, r.text, "botones")
            return r.status_code == 200

    async def enviar_lista(
        self,
        telefono: str,
        texto: str,
        boton_texto: str,
        secciones: list[dict],
    ) -> bool:
        """Envía mensaje interactivo con lista desplegable via Meta WhatsApp Cloud API.

        Se usa cuando hay más de 3 opciones (los botones de Meta soportan máx 3).

        Args:
            telefono: Número del destinatario
            boton_texto: Texto del botón que abre la lista (máx 20 chars)
            secciones: [{"title": "Info clases", "rows": [
                            {"id": "lead_precios", "title": "Precios"},
                            {"id": "lead_horarios", "title": "Horarios"},
                        ]}]
        """
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": texto},
                "action": {
                    "button": boton_texto,
                    "sections": secciones,
                },
            },
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                _registrar_fallo(r.status_code, r.text, "lista")
            return r.status_code == 200

    async def enviar_imagen(self, telefono: str, media_id: str, caption: str = "") -> bool:
        """Reenvía una imagen por media_id ya subido a Meta."""
        if not self.access_token or not self.phone_number_id:
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        image_obj = {"id": media_id}
        if caption:
            image_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "image",
            "image": image_obj,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                _registrar_fallo(r.status_code, r.text, "imagen")
            return r.status_code == 200

    async def subir_media(self, image_bytes: bytes, mime_type: str = "image/png") -> str | None:
        """Sube un archivo a Meta y retorna el media_id."""
        if not self.access_token or not self.phone_number_id:
            return None
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/media"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        _ext_map = {"image/png": "png", "image/jpeg": "jpg", "video/mp4": "mp4", "video/quicktime": "mov"}
        ext = _ext_map.get(mime_type.split(";")[0].strip(), "bin")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    url,
                    headers=headers,
                    data={"messaging_product": "whatsapp", "type": mime_type},
                    files={"file": (f"media.{ext}", image_bytes, mime_type)},
                )
                if r.status_code == 200:
                    media_id = r.json().get("id")
                    logger.info(f"Media subida OK: {media_id}")
                    return media_id
                _registrar_fallo(r.status_code, r.text, "subir_media")
                return None
        except Exception as e:
            logger.error(f"Error subiendo media: {e}")
            return None

    async def enviar_imagen_bytes(
        self, telefono: str, image_bytes: bytes, mime_type: str = "image/png", caption: str = ""
    ) -> bool:
        """Sube una imagen y la envía en un solo paso."""
        media_id = await self.subir_media(image_bytes, mime_type)
        if not media_id:
            return False
        return await self.enviar_imagen(telefono, media_id, caption)

    async def enviar_video_bytes(
        self, telefono: str, video_bytes: bytes, mime_type: str = "video/mp4", caption: str = ""
    ) -> bool:
        """Sube un video y lo envía."""
        media_id = await self.subir_media(video_bytes, mime_type)
        if not media_id:
            return False
        if not self.access_token or not self.phone_number_id:
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        video_obj = {"id": media_id}
        if caption:
            video_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "video",
            "video": video_obj,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                _registrar_fallo(r.status_code, r.text, "video")
            return r.status_code == 200

    async def enviar_plantilla(
        self,
        telefono: str,
        template_name: str,
        variables: list[str] | None = None,
        componentes: list[dict] | None = None,
        language: str = "es",
    ) -> bool:
        """
        Envía un mensaje de plantilla aprobada por Meta.
        Necesario para: contacto fuera de ventana 24h, mensajes a contactos fríos.

        Args:
            telefono: Número del destinatario
            template_name: Nombre de la plantilla en Meta Business
            variables: Lista de variables {{1}}, {{2}}, etc. (backward compat)
            componentes: Componentes raw (header, body, buttons) — prioridad sobre variables
            language: Código de idioma (default: es)
        """
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        template = {
            "name": template_name,
            "language": {"code": language},
        }
        if componentes:
            # Componentes raw (header imagen, botones, etc.)
            template["components"] = componentes
        elif variables:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": v} for v in variables
                    ],
                }
            ]
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "template",
            "template": template,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                _registrar_fallo(r.status_code, r.text, f"plantilla '{template_name}'")
            else:
                logger.info(f"Plantilla '{template_name}' enviada a {telefono}")
            return r.status_code == 200

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Meta WhatsApp Cloud API."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": mensaje},
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                _registrar_fallo(r.status_code, r.text, "texto")
            return r.status_code == 200

    async def descargar_media(self, media_id: str) -> bytes | None:
        """
        Descarga los bytes de un media de WhatsApp (imagen, audio, video).

        Meta Cloud API requiere dos pasos:
          1. GET /{media_id} → URL real del archivo
          2. GET {url} → bytes del archivo

        Returns:
            bytes del archivo o None si falla.
        """
        if not self.access_token:
            logger.warning("[Meta] No hay access_token para descargar media")
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with httpx.AsyncClient(timeout=30) as client:
            # Paso 1: obtener URL
            r = await client.get(
                f"https://graph.facebook.com/{self.api_version}/{media_id}",
                headers=headers,
            )
            if r.status_code != 200:
                logger.error(f"[Meta] Error obteniendo URL de media {media_id}: {r.status_code}")
                return None

            media_url = r.json().get("url")
            if not media_url:
                logger.error(f"[Meta] No se obtuvo URL para media {media_id}")
                return None

            # Paso 2: descargar bytes
            r = await client.get(media_url, headers=headers)
            if r.status_code != 200:
                logger.error(f"[Meta] Error descargando media: {r.status_code}")
                return None

            logger.info(f"[Meta] Media descargado: {media_id} ({len(r.content)} bytes)")
            return r.content
