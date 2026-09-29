import unittest
import os
import shutil
import asyncio
from unittest.mock import patch, MagicMock
from core.orchestrator import Orchestrator
from core.config import Config

class PremiumGenerationTest(unittest.TestCase):
    def setUp(self):
        # Asegurarse de que el directorio temporal exista y no choque con nada
        self.orchestrator = Orchestrator(headless=True, dry_run=True)
        # Mock de bot de telegram para evitar llamadas reales a Telegram API
        class MockTelegramBot:
            async def send_notification(self, text, reply_markup=None):
                print(f"[MOCK TELEGRAM NOTIFICATION]: {text}")
            async def send_video(self, video_path, caption=None):
                print(f"[MOCK TELEGRAM VIDEO]: {video_path} - Caption: {caption}")
            def get_master_keyboard(self):
                return None
            @property
            def user_state(self):
                return {"active_networks": {"tiktok": True}, "fb_paused": False}
        self.orchestrator.telegram_bot = MockTelegramBot()

    @patch('publishers.tiktok_publisher.TikTokPublisher.publish_video')
    @patch('publishers.youtube_publisher.YouTubePublisher.publish_video')
    def test_premium_video_generation_flow(self, mock_yt_publish, mock_tk_publish):
        # Configurar mocks asíncronos para simular subidas exitosas
        async def mock_upload(*args, **kwargs):
            print(f"[MOCK UPLOAD CALLED] args: {args}, kwargs: {kwargs}")
            return True
        mock_tk_publish.side_effect = mock_upload
        mock_yt_publish.side_effect = mock_upload
        # 1. Configurar un producto de prueba calificado para premium
        test_product = {
            "id": "MLM2615332949_test_premium",
            "title": "Tenis adidas Casual Grand Court Hombre Blanco Jq7295",
            "offer_price": "$959",
            "list_price": "$1599",
            "discount": "40% OFF",
            "image_url": "https://http2.mlstatic.com/D_NQ_NP_779673-MLM100956260891_122025-O.webp",
            "affiliate_url": "https://meli.la/16muTnJ",
            "source": "apify",
            "review_status": "approved_manual",
            "skip_scrape": True,
            "gallery_images": [
                "https://http2.mlstatic.com/D_NQ_NP_779673-MLM100956260891_122025-O.webp",
                "https://http2.mlstatic.com/D_NQ_NP_779673-MLM100956260891_122025-O.webp"
            ],
            "script": [
                "¿Buscas unos tenis casuales clásicos y súper cómodos?",
                "Los tenis adidas Grand Court para hombre son la opción ideal.",
                "Con las icónicas tres franjas negras sobre fondo blanco.",
                "Normalmente cuestan mil quinientos noventa y nueve pesos.",
                "Pero hoy te los llevas con el cuarenta por ciento de descuento.",
                "Consigue esta ganga en el enlace de la descripción ahora."
            ]
        }

        # Asegurar de que no existan archivos previos del test
        out_video = os.path.join(Config.BASE_DIR, "tiktok_videos", f"{test_product['id']}.mp4")
        if os.path.exists(out_video):
            os.remove(out_video)

        # 2. Ejecutar run_publication en modo asíncrono
        loop = asyncio.get_event_loop()
        success = loop.run_until_complete(
            self.orchestrator.run_publication(
                url=test_product["affiliate_url"],
                target_platform=["tiktok"],
                pre_scraped_details=test_product
            )
        )

        # 3. Validaciones
        self.assertTrue(success, "El flujo de publicación debería ser exitoso en modo dry-run")
        self.assertTrue(os.path.exists(out_video), f"El video premium final debería existir en {out_video}")
        print(f"🎉 ¡Prueba exitosa! El video premium se generó correctamente en {out_video}")

if __name__ == "__main__":
    unittest.main()
