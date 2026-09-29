"""
publishers/telegram_publisher.py
Módulo encargado exclusivamente de publicar en el Canal de Telegram.
No depende del orquestador ni del TelegramBot de control — solo necesita
el token, el channel_id y los datos del producto.
"""
import os
import re
import json
import aiohttp
from core.publisher_base import Publisher, PublishResult


class TelegramPublisher(Publisher):
    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)
        self.token      = os.getenv("TELEGRAM_BOT_TOKEN")
        self.channel_id = os.getenv("TELEGRAM_CHANNEL_ID")

    async def publish(self, details: dict, affiliate_link: str, **kwargs) -> PublishResult:
        """
        Construye el mensaje y lo publica en el canal de Telegram.
        Adjunta la imagen local si existe, o la URL de imagen si no.
        Retorna PublishResult con status de éxito.

        kwargs:
            target_channel_id (str, opcional): ID de canal alternativo
        """
        target_channel_id = kwargs.get("target_channel_id")
        channel_id = target_channel_id or self.channel_id
        if not self.token or not channel_id:
            msg = "TOKEN o CHANNEL_ID no configurados"
            print(f"[TELEGRAM PUBLISHER] Error: {msg}")
            return PublishResult(False, "telegram", msg)

        # Construir texto del post
        from core.message_builder import build_post_message
        msg_lines = build_post_message(details, affiliate_link, platform="telegram")
        message   = "\n".join(msg_lines)

        # Botones inline de compra y sitio web
        buy_url = affiliate_link
        from core.message_builder import _detect_store
        store_name, _ = _detect_store(details, buy_url or "")
        
        if "amazon" in store_name.lower():
            btn_text = "🛒 VER OFERTA EN AMAZON"
        elif "mercado" in store_name.lower():
            btn_text = "🛒 VER EN MERCADO LIBRE"
        else:
            btn_text = "🛒 VER OFERTA AHORA"

        reply_markup = {
            "inline_keyboard": [
                [{"text": btn_text, "url": buy_url}],
                [{"text": "🛍️ VER MÁS OFERTAS", "url": "https://gangasmx.com"}]
            ]
        } if buy_url else None

        img_path = details.get("visual_capture") or details.get("screenshot")
        if img_path and not os.path.isabs(img_path):
            from core.config import Config
            img_path = os.path.join(Config.BASE_DIR, img_path)
        img_url  = details.get("image_url")  # Fallback: URL de imagen del scraper

        # Sanitizar el mensaje para evitar errores de Markdown en Telegram
        # (los títulos de productos pueden tener _, *, `, [ que rompen el parser)
        def safe_msg(text):
            for ch in ['_', '*', '`', '[']:
                text = text.replace(ch, f'\\{ch}')
            return text
        # No usamos parse_mode para evitar conflictos — texto plano siempre funciona

        # Log de diagnóstico para saber qué imagen se usará
        if img_path and os.path.exists(img_path):
            print(f"[TELEGRAM PUBLISHER] Usando imagen local: {img_path}")
        elif img_url:
            print(f"[TELEGRAM PUBLISHER] Sin imagen local, usando URL: {img_url}")
        else:
            print(f"[TELEGRAM PUBLISHER] ⚠️ Sin imagen disponible (ni local ni URL). Publicando solo texto.")

        try:
            async with aiohttp.ClientSession() as session:

                if img_path and os.path.exists(img_path):
                    api_url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                    data = aiohttp.FormData()
                    data.add_field("chat_id", channel_id)
                    data.add_field("caption",  message)
                    if reply_markup:
                        data.add_field("reply_markup", json.dumps(reply_markup))
                    with open(img_path, "rb") as f:
                        data.add_field("photo", f)
                        async with session.post(api_url, data=data) as resp:
                            res = await resp.json()
                            ok  = res.get("ok", False)
                            if not ok:
                                print(f"[TELEGRAM PUBLISHER] Error enviando foto local: {res}")
                                msg = f"Error enviando foto local: {res.get('description', 'unknown')}"
                                return PublishResult(False, "telegram", msg, details=res)
                            return PublishResult(True, "telegram", "Publicado con imagen local", details={"message_id": res.get("result", {}).get("message_id")})

                elif img_url:
                    api_url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                    payload = {
                        "chat_id": channel_id,
                        "photo":   img_url,
                        "caption": message,
                    }
                    if reply_markup:
                        payload["reply_markup"] = reply_markup
                    async with session.post(api_url, json=payload) as resp:
                        res = await resp.json()
                        ok  = res.get("ok", False)
                        if not ok:
                            print(f"[TELEGRAM PUBLISHER] Error enviando foto por URL: {res}. Intentando solo texto...")
                            fallback_payload = {"chat_id": channel_id, "text": message}
                            if reply_markup:
                                fallback_payload["reply_markup"] = reply_markup
                            async with session.post(
                                f"https://api.telegram.org/bot{self.token}/sendMessage",
                                json=fallback_payload
                            ) as r2:
                                res2 = await r2.json()
                                ok2 = res2.get("ok", False)
                                if ok2:
                                    return PublishResult(True, "telegram", "Publicado solo texto (fallback)", details={"message_id": res2.get("result", {}).get("message_id")})
                                return PublishResult(False, "telegram", "Error en fallback de texto", details=res2)
                        return PublishResult(True, "telegram", "Publicado con imagen por URL", details={"message_id": res.get("result", {}).get("message_id")})

                else:
                    api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                    payload = {
                        "chat_id": channel_id,
                        "text":    message
                    }
                    if reply_markup:
                        payload["reply_markup"] = reply_markup
                    async with session.post(api_url, json=payload) as resp:
                        res = await resp.json()
                        ok  = res.get("ok", False)
                        if not ok:
                            print(f"[TELEGRAM PUBLISHER] Error enviando texto: {res}")
                            msg = f"Error enviando texto: {res.get('description', 'unknown')}"
                            return PublishResult(False, "telegram", msg, details=res)
                        return PublishResult(True, "telegram", "Publicado solo texto", details={"message_id": res.get("result", {}).get("message_id")})

        except Exception as e:
            print(f"[TELEGRAM PUBLISHER] Excepcion: {e}")
            return PublishResult(False, "telegram", f"Excepción: {str(e)}", error=e)
