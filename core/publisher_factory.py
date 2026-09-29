"""
core/publisher_factory.py

Factory para crear instancias de publishers con dependencias inyectadas.
Centraliza la creación de publishers para facilitar testing y extensión.
"""

from typing import Dict, Optional
from core.publisher_base import Publisher
from publishers.facebook_publisher import FacebookPublisher
from publishers.facebook_api_publisher import FacebookApiPublisher
from publishers.pinterest_publisher import PinterestPublisher
from publishers.telegram_publisher import TelegramPublisher
from publishers.web_publisher import WebPublisher
from publishers.tiktok_publisher import TikTokPublisher
from publishers.youtube_publisher import YouTubePublisher
from publishers.twitter_publisher import TwitterPublisher


class PublisherFactory:
    """Factory para crear y gestionar instancias de publishers."""

    @staticmethod
    def create_default_publishers(telegram_bot=None) -> Dict[str, Publisher]:
        """
        Crea instancias de todos los publishers disponibles.

        Args:
            telegram_bot: Instancia del TelegramBot para notificaciones

        Returns:
            Dict con publishers {nombre: instancia}
        """
        return {
            "facebook": FacebookPublisher(telegram_bot),
            "facebook_page": FacebookApiPublisher(telegram_bot),
            "pinterest": PinterestPublisher(telegram_bot),
            "telegram": TelegramPublisher(telegram_bot),
            "web": WebPublisher(telegram_bot),
            "tiktok": TikTokPublisher(telegram_bot),
            "youtube": YouTubePublisher(telegram_bot),
            "twitter": TwitterPublisher(telegram_bot),
        }

    @staticmethod
    def create_publisher(publisher_type: str, telegram_bot=None) -> Optional[Publisher]:
        """
        Crea una instancia de un publisher específico.

        Args:
            publisher_type: Tipo de publisher (facebook, pinterest, telegram, etc.)
            telegram_bot: Instancia del TelegramBot para notificaciones

        Returns:
            Instancia del publisher o None si el tipo es desconocido
        """
        publishers = {
            "facebook": FacebookPublisher,
            "facebook_page": FacebookApiPublisher,
            "pinterest": PinterestPublisher,
            "telegram": TelegramPublisher,
            "web": WebPublisher,
            "tiktok": TikTokPublisher,
            "youtube": YouTubePublisher,
            "twitter": TwitterPublisher,
        }
        publisher_cls = publishers.get(publisher_type)
        if publisher_cls:
            return publisher_cls(telegram_bot)
        return None
