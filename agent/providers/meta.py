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


# WhatsApp corta el body de texto en 4096 chars — mensajes más largos daban 400
# y el lead se quedaba sin respuesta (solo un log). Se parten en el último salto
# de línea (o espacio) antes del límite.
_MAX_TEXTO = 4096


def _partir_mensaje(texto: str, limite: int = _MAX_TEXTO) -> list[str]:
    """Parte un texto en pedazos <= limite, cortando en salto de línea o espacio."""
    partes = []
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = texto.rfind(" ", 0, limite)
        if corte <= 0:
            corte = limite
        partes.append(texto[:corte])
        texto = texto[corte:].lstrip("\n ")
    if texto:
        partes.append(texto)
    return partes


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando la API oficial de Meta (Cloud API)."""

    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("META_PHONE_NUMBER_ID")
        self.verify_token = os.getenv("META_VERIFY_TOKEN", "")
        self.api_version = "v21.0"

    async def _post_mensajes(self, payload: dict, contexto: str) -> bool:
        """POST a /messages con manejo de errores de red (única puerta de envío).

        Antes cada método hacía el POST pelado: un ConnectError/ReadTimeout
        propagaba al caller (y mataba loops de envío enteros), y el monitor
        solo veía errores HTTP — era ciego a "Meta inalcanzable". Ahora el
        error de red se registra con status 0 y el método retorna False.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    },
                )
        except Exception as e:
            _registrar_fallo(0, f"red: {type(e).__name__}: {e}", contexto)
            return False
        if r.status_code != 200:
            _registrar_fallo(r.status_code, r.text, contexto)
            return False
        return True

    async def validar_webhook(self, request: Request) -> int | None:
        """Meta requiere verificación GET con hub.verify_token."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if self.verify_token and mode == "subscribe" and token == self.verify_token:
            # Meta espera el challenge como respuesta en texto plano
            return int(challenge)
        if not self.verify_token:
            logger.warning("[META] META_VERIFY_TOKEN no configurado — verificación GET rechazada")
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
            # entry.id = WABA ID real del número (dato que la Graph API no expone
            # con los tokens actuales) — se loguea una vez por proceso
            if not getattr(self, "_waba_logueado", False):
                self._waba_logueado = True
                logger.info(f"[META] WABA de este numero (entry.id): {entry.get('id')}")
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
                    flow_data = None
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
                        # Respuesta a botón interactivo, ítem de lista o formulario (Flow)
                        _interactive = msg.get("interactive", {})
                        _int_type = _interactive.get("type", "")
                        if _int_type == "nfm_reply":
                            # Respuesta de un Meta Flow (formulario nativo)
                            import json as _json
                            _nfm = _interactive.get("nfm_reply", {})
                            try:
                                flow_data = _json.loads(_nfm.get("response_json", "{}"))
                            except Exception:
                                flow_data = {}
                            texto = "[formulario]"
                            btn_id = "flow_completado"
                        elif _int_type == "list_reply":
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
                            flow_data=flow_data,
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
        return await self._post_mensajes(payload, "botones")

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
        return await self._post_mensajes(payload, "lista")

    async def enviar_flow(
        self,
        telefono: str,
        flow_id: str,
        screen: str,
        texto: str,
        boton_texto: str = "Completar mis datos",
        flow_token: str | None = None,
    ) -> bool:
        """Envía un Meta Flow (formulario nativo) en modo navigate.

        flow_id: ID del Flow publicado en la WABA. screen: pantalla inicial (ej "FORMULARIO").
        boton_texto: CTA que abre el formulario (máx 30 chars).
        flow_token: correlación (default: el teléfono); vuelve en el nfm_reply.
        """
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "flow",
                "body": {"text": texto},
                "action": {
                    "name": "flow",
                    "parameters": {
                        "flow_message_version": "3",
                        "flow_token": flow_token or telefono,
                        "flow_id": flow_id,
                        "flow_cta": boton_texto[:30],
                        "flow_action": "navigate",
                        "flow_action_payload": {"screen": screen},
                    },
                },
            },
        }
        return await self._post_mensajes(payload, "flow")

    async def enviar_imagen(self, telefono: str, media_id: str, caption: str = "") -> bool:
        """Reenvía una imagen por media_id ya subido a Meta."""
        if not self.access_token or not self.phone_number_id:
            return False
        image_obj = {"id": media_id}
        if caption:
            image_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "image",
            "image": image_obj,
        }
        return await self._post_mensajes(payload, "imagen")

    async def enviar_documento_url(
        self, telefono: str, doc_url: str, filename: str = "documento.pdf", caption: str = ""
    ) -> bool:
        """Envía un documento por URL pública (ej. el PDF de factura desde Airtable)."""
        if not self.access_token or not self.phone_number_id:
            return False
        doc_obj = {"link": doc_url, "filename": filename}
        if caption:
            doc_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "document",
            "document": doc_obj,
        }
        return await self._post_mensajes(payload, "documento")

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
        video_obj = {"id": media_id}
        if caption:
            video_obj["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "video",
            "video": video_obj,
        }
        return await self._post_mensajes(payload, "video")

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
        ok = await self._post_mensajes(payload, f"plantilla '{template_name}'")
        if ok:
            logger.info(f"Plantilla '{template_name}' enviada a {telefono}")
        return ok

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Meta WhatsApp Cloud API.

        Textos > 4096 chars se parten en varios mensajes (antes Meta devolvía
        400 y el destinatario no recibía nada)."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        # Texto vacío: _partir_mensaje devuelve [] → el for no itera y esto
        # devolvía True SIN haber mandado nada. El caller lo daba por
        # respondido y el padre quedaba en silencio. Ahora se dice la verdad.
        if not (mensaje or "").strip():
            logger.error(f"[META] enviar_mensaje con texto VACÍO para {telefono} — no se envía nada")
            return False
        ok = True
        for parte in _partir_mensaje(mensaje):
            payload = {
                "messaging_product": "whatsapp",
                "to": telefono,
                "type": "text",
                "text": {"body": parte},
            }
            if not await self._post_mensajes(payload, "texto"):
                ok = False
                break  # si una parte falla, no mandar las siguientes sueltas
        return ok

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

        try:
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
        except Exception as e:
            logger.error(f"[Meta] Error de red descargando media {media_id}: {e}")
            return None
