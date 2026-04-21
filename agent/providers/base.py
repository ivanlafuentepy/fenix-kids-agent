# agent/providers/base.py — Clase base para proveedores de WhatsApp
# Generado por AgentKit

"""
Define la interfaz común que todos los proveedores de WhatsApp deben implementar.
Esto permite cambiar de proveedor sin modificar el resto del código.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from fastapi import Request


@dataclass
class MensajeEntrante:
    """Mensaje normalizado — mismo formato sin importar el proveedor."""
    telefono: str            # Número del remitente
    texto: str               # Contenido del mensaje
    mensaje_id: str          # ID único del mensaje
    es_propio: bool          # True si lo envió el agente (se ignora)
    media_id: str | None = None   # ID de media (audio, imagen, documento)
    es_boton: bool = False        # True si es respuesta a botón interactivo


class ProveedorWhatsApp(ABC):
    """Interfaz que cada proveedor de WhatsApp debe implementar."""

    @abstractmethod
    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Extrae y normaliza mensajes del payload del webhook."""
        ...

    @abstractmethod
    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía un mensaje de texto. Retorna True si fue exitoso."""
        ...

    async def enviar_botones(self, telefono: str, texto: str, botones: list[dict]) -> bool:
        """Envía mensaje interactivo con botones. Default: no soportado."""
        return False

    async def enviar_imagen(self, telefono: str, media_id: str, caption: str = "") -> bool:
        """Reenvía una imagen por media_id. Default: no soportado."""
        return False

    async def enviar_imagen_bytes(
        self, telefono: str, image_bytes: bytes, mime_type: str = "image/png", caption: str = ""
    ) -> bool:
        """Sube y envía una imagen desde bytes. Default: no soportado."""
        return False

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """Verificación GET del webhook (solo Meta la requiere). Retorna respuesta o None."""
        return None
