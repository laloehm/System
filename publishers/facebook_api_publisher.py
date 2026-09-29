import os
import requests
import logging
from core.config import Config
from core.publisher_base import Publisher, PublishResult

logger = logging.getLogger(__name__)

class FacebookApiPublisher(Publisher):
    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)

    async def publish(self, details: dict, affiliate_link: str, **kwargs) -> PublishResult:
        """
        Publica en la página de Facebook via Graph API.

        kwargs:
            image_path (str, opcional): ruta de imagen local o URL
        """
        from core.message_builder import build_post_message
        msg_lines = build_post_message(details, affiliate_link, platform="facebook")
        message = "\n".join(msg_lines)
        image_path = kwargs.get("image_path") or details.get("visual_capture") or details.get("screenshot")

        try:
            post_id = self.post_to_page(message, image_path)
            if post_id:
                return PublishResult(True, "facebook_page", "Publicado en página de FB (API)", details={"post_id": post_id})
            return PublishResult(False, "facebook_page", "No se pudo publicar en página de FB")
        except Exception as e:
            msg = f"Error publicando en FB Page (API): {str(e)[:100]}"
            return PublishResult(False, "facebook_page", msg, error=e)

    @staticmethod
    def post_to_page(message: str, image_path: str = None) -> str:
        """
        Publica directamente en la página de Facebook usando Graph API.
        Devuelve el ID del post o None si falla.
        """
        if not Config.FB_PAGE_ID or not Config.FB_PAGE_TOKEN:
            logger.error("Credenciales de Facebook Page (FB_PAGE_ID / FB_PAGE_TOKEN) no configuradas.")
            return None

        url = f"https://graph.facebook.com/v19.0/{Config.FB_PAGE_ID}/photos"
        
        payload = {
            "message": message,
            "access_token": Config.FB_PAGE_TOKEN
        }
        
        try:
            if image_path and str(image_path).startswith('http'):
                payload['url'] = image_path
                response = requests.post(url, data=payload, timeout=30)
            elif image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as img:
                    files = {
                        'source': img
                    }
                    response = requests.post(url, data=payload, files=files, timeout=30)
            else:
                # Si no hay imagen, publicar solo texto en el feed
                url_feed = f"https://graph.facebook.com/v19.0/{Config.FB_PAGE_ID}/feed"
                response = requests.post(url_feed, data=payload, timeout=30)

            response_data = response.json()

            if response.status_code == 200 and ("id" in response_data or "post_id" in response_data):
                post_id = response_data.get("post_id") or response_data.get("id")
                logger.info(f"Publicación exitosa en Facebook Page (API). ID: {post_id}")
                return post_id
            else:
                logger.error(f"Error al publicar en FB Page (API): {response_data}")
                return None
                
        except Exception as e:
            logger.error(f"Excepción al usar Graph API: {e}")
            return None

    @staticmethod
    def post_video_to_page(description: str, video_path: str) -> str:
        """
        Publica un video directamente en la página de Facebook usando Graph API.
        Devuelve el ID del post o None si falla.
        """
        if not Config.FB_PAGE_ID or not Config.FB_PAGE_TOKEN:
            logger.error("Credenciales de Facebook Page (FB_PAGE_ID / FB_PAGE_TOKEN) no configuradas.")
            return None

        url = f"https://graph.facebook.com/v19.0/{Config.FB_PAGE_ID}/videos"
        
        payload = {
            "description": description,
            "access_token": Config.FB_PAGE_TOKEN
        }
        
        try:
            if video_path and os.path.exists(video_path):
                with open(video_path, 'rb') as vid:
                    files = {
                        'source': vid
                    }
                    # Timeout extendido a 120 segundos porque los videos pesan más
                    response = requests.post(url, data=payload, files=files, timeout=120)
            else:
                logger.error("El archivo de video no existe o no es válido.")
                return None

            response_data = response.json()

            if response.status_code == 200 and ("id" in response_data or "post_id" in response_data):
                post_id = response_data.get("post_id") or response_data.get("id")
                logger.info(f"Video publicado exitosamente en Facebook Page (API). ID: {post_id}")
                return post_id
            else:
                logger.error(f"Error al publicar video en FB Page (API): {response_data}")
                return None
                
        except Exception as e:
            logger.error(f"Excepción al usar Graph API para video: {e}")
            return None
