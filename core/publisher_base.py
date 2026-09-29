"""
core/publisher_base.py

Interfaz base abstracta para todos los publishers.
Define el contrato que deben cumplir todos para permitir inyección de dependencias
y intercambiabilidad.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class PublishResult:
    """Resultado estandarizado de una publicación."""

    def __init__(self, success: bool, platform: str, message: str = "", error: Optional[Exception] = None, details: Optional[Dict[str, Any]] = None):
        self.success = success
        self.platform = platform
        self.message = message
        self.error = error
        self.details = details or {}

    def __repr__(self):
        status = "✅" if self.success else "❌"
        return f"{status} {self.platform}: {self.message}"


class Publisher(ABC):
    """
    Interfaz base para todos los publishers.

    Cada publisher concreto hereda de esta clase e implementa el método publish().
    Permite:
    - Inyección de dependencias en Orchestrator
    - Testing mediante mocks
    - Extensión sin modificar Orchestrator
    """

    def __init__(self, telegram_bot=None):
        self.telegram_bot = telegram_bot

    @abstractmethod
    async def publish(self, details: Dict[str, Any], affiliate_link: str, **kwargs) -> PublishResult:
        """
        Publica un producto en la plataforma.

        Args:
            details: Diccionario con datos del producto (title, price, image_url, etc.)
            affiliate_link: URL del link de afiliado
            **kwargs: Parámetros específicos de cada plataforma
                     (ej: group_url para FB, target_channel_id para Telegram, video_path para TikTok)

        Returns:
            PublishResult con status de éxito y detalles
        """
        pass

    async def _notify_telegram(self, message: str):
        """Helper para notificar al bot de Telegram si está disponible."""
        if self.telegram_bot:
            try:
                await self.telegram_bot.send_notification(message)
            except Exception as e:
                print(f"[NOTIFY] Error enviando notificación a Telegram: {e}")
