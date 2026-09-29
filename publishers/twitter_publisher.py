"""
publishers/twitter_publisher.py

Publisher para publicar ofertas automáticamente en Twitter / X:
1. Intenta vía API v2 de Tweepy (si hay credenciales válidas en .env).
2. Si la API falla (ej. error 402 Paywall) o no está configurada, utiliza Playwright Headless
   con la sesión guardada en storage_state_linux.json / storage_state.json / storage_state_twitter.json (100% GRATIS).
"""

import os
import re
import sys
import asyncio
import platform
from typing import Dict, Any, Optional

from core.publisher_base import Publisher, PublishResult
from core.config import Config


def _safe_print(*args, **kwargs):
    """Imprime de forma segura en consolas con diferente encoding (Windows cp1252 vs Linux utf-8)."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        msg = " ".join(str(a) for a in args)
        safe_msg = msg.encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii")
        print(safe_msg, **kwargs)


class TwitterPublisher(Publisher):
    """Publisher para publicar promociones en Twitter / X."""

    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)
        self.api_key = os.getenv("TWITTER_API_KEY", "")
        self.api_secret = os.getenv("TWITTER_API_SECRET", "")
        self.access_token = os.getenv("TWITTER_ACCESS_TOKEN", "")
        self.access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
        self.enabled = True

    def _has_api_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret and self.access_token and self.access_token_secret)

    def _get_clients(self):
        """Inicializa los clientes de v1.1 (para imágenes) y v2 (para crear tweets)."""
        if not self._has_api_credentials():
            raise RuntimeError("Credenciales de API Twitter/X no configuradas en .env")

        import tweepy
        auth = tweepy.OAuth1UserHandler(
            self.api_key, self.api_secret, self.access_token, self.access_token_secret
        )
        api_v1 = tweepy.API(auth)

        client_v2 = tweepy.Client(
            consumer_key=self.api_key,
            consumer_secret=self.api_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret
        )
        return api_v1, client_v2

    def format_tweet_text(self, details: Dict[str, Any], affiliate_link: str) -> str:
        """
        Formatea el texto del tweet respetando el límite de 280 caracteres de Twitter/X.
        """
        raw_title = details.get("title", "Oferta Especial")
        ai_clean = (details.get("clean_title") or "").strip()
        if ai_clean and ai_clean != raw_title and len(ai_clean) <= 85:
            clean_title = ai_clean
        else:
            from core.message_builder import _clean_title
            clean_title = _clean_title(ai_clean or raw_title)

        offer_price = details.get("offer_price") or (f"${details.get('price'):,.0f}" if details.get('price') else "")
        list_price = details.get("list_price") or (f"${details.get('original_price'):,.0f}" if details.get('original_price') else "")
        discount = details.get("discount", "")
        source = str(details.get("source", "")).lower()

        is_amazon = "amazon" in source or "amzn" in str(affiliate_link).lower() or "amazon" in str(affiliate_link).lower()
        store_tag = "#AmazonMX" if is_amazon else "#MercadoLibreMX"
        hashtags = f"#Ofertas #Descuentos {store_tag}"

        price_line = ""
        if offer_price and list_price and list_price != offer_price:
            price_line = f"🔥 De {list_price} a solo {offer_price}"
            if discount:
                price_line += f" ({discount})"
        elif offer_price:
            price_line = f"🔥 Por solo {offer_price}"
            if discount:
                price_line += f" ({discount})"

        overhead = len(f"🚨 \n\n{price_line}\n\n🛒 Ver oferta: \n\n{hashtags}") + 23
        max_title_len = max(30, 275 - overhead)

        clean_title = clean_title.strip()
        if len(clean_title) > max_title_len:
            clean_title = clean_title[:max_title_len - 3] + "..."

        parts = [
            f"🚨 {clean_title}",
            price_line if price_line else "",
            f"🛒 Ver oferta: {affiliate_link}",
            hashtags
        ]
        return "\n\n".join([p for p in parts if p]).strip()

    async def publish(self, details: Dict[str, Any], affiliate_link: str, **kwargs) -> PublishResult:
        """
        Publica una oferta en Twitter / X.
        Intenta vía API primero (si está configurada); si falla o no existe, usa Playwright.
        """
        tweet_text = self.format_tweet_text(details, affiliate_link)

        # 1. Intentar vía API oficial si hay credenciales
        if self._has_api_credentials():
            try:
                _safe_print("[TWITTER] Intentando publicar vía API v2 oficial...")
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, self._post_tweet_sync, details, tweet_text)
                tweet_id = result.get("tweet_id")
                tweet_url = f"https://x.com/i/status/{tweet_id}" if tweet_id else ""
                msg = f"Tweet publicado exitosamente en X vía API: {tweet_url}"
                _safe_print(f"✅ [TWITTER] {msg}")

                if self.telegram_bot:
                    notify_msg = (
                        f"🐦 *Tweet publicado en X (API)*\n"
                        f"📦 {details.get('title', 'Producto')[:50]}\n"
                        f"🔗 [Ver Tweet]({tweet_url})"
                    )
                    asyncio.create_task(self.telegram_bot.send_notification(notify_msg))

                return PublishResult(True, "twitter", msg, details={"tweet_id": tweet_id, "url": tweet_url})

            except Exception as e:
                _safe_print(f"⚠️ [TWITTER] API v2 falló ({e}). Cambiando a modo Playwright (Gratuito)...")

        # 2. Modo Playwright Headless (Gratis)
        page = kwargs.get("page")
        if page:
            return await self._publish_via_playwright(page, details, tweet_text, affiliate_link)

        # Si no nos pasaron una 'page', creamos un browser temporal usando Playwright
        return await self._publish_with_own_browser(details, tweet_text, affiliate_link)

    def _post_tweet_sync(self, details: Dict[str, Any], tweet_text: str) -> dict:
        """Método síncrono interno para API v2."""
        api_v1, client_v2 = self._get_clients()
        media_ids = []

        image_path = details.get("screenshot") or details.get("visual_capture") or details.get("manual_image")
        if not image_path or not os.path.exists(str(image_path)):
            prod_id = details.get("id")
            if prod_id:
                cap_path = os.path.join(Config.CAPTURES_DIR, f"{prod_id}.png")
                if os.path.exists(cap_path):
                    image_path = cap_path

        if image_path and os.path.exists(str(image_path)):
            try:
                _safe_print(f"[TWITTER] Subiendo imagen a X vía API: {image_path}")
                media = api_v1.media_upload(filename=str(image_path))
                if media and hasattr(media, "media_id"):
                    media_ids.append(media.media_id)
            except Exception as e:
                _safe_print(f"⚠️ [TWITTER] Falló subida de imagen API: {e}")

        kwargs = {"text": tweet_text}
        if media_ids:
            kwargs["media_ids"] = media_ids

        resp = client_v2.create_tweet(**kwargs)
        tweet_id = resp.data["id"] if resp and resp.data else None
        return {"tweet_id": tweet_id}

    async def _publish_via_playwright(self, page, details: Dict[str, Any], tweet_text: str, affiliate_link: str) -> PublishResult:
        """Publica un Tweet directamente desde https://x.com/home usando Playwright."""
        _safe_print("[TWITTER PLAYWRIGHT] Navegando a https://x.com/home...")
        try:
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)

            # Verificar si redirigió a login
            current_url = page.url.lower()
            if "login" in current_url or "i/flow/login" in current_url:
                err = "Sesión no iniciada en Twitter/X. Guarda la sesión en storage_state_linux.json o storage_state_twitter.json"
                _safe_print(f"❌ [TWITTER PLAYWRIGHT] {err}")
                if self.telegram_bot:
                    asyncio.create_task(self.telegram_bot.send_notification(f"❌ *Error en Twitter/X (Playwright):*\n{err}"))
                return PublishResult(False, "twitter", err)

            # Buscar la caja de texto principal en el Home feed
            textbox = None
            selectors = [
                '[data-testid="tweetTextarea_0"]',
                'div[role="textbox"][contenteditable="true"]',
                'div[role="textbox"][aria-label*="¿Qué está pasando?"]',
                'div[role="textbox"][aria-label*="What"]',
                'div.public-DraftEditor-content',
                'div[role="textbox"]'
            ]

            start_t = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_t) < 15:
                for ph in ["¿Qué está pasando?", "What's happening?", "What is happening?"]:
                    try:
                        loc = page.get_by_placeholder(ph).first
                        if await loc.count() > 0 and await loc.is_visible():
                            textbox = loc
                            break
                    except Exception:
                        pass
                if textbox:
                    break

                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            textbox = loc
                            break
                    except Exception:
                        pass
                if textbox:
                    break
                await page.wait_for_timeout(800)

            if not textbox:
                err = "No se encontró el campo de texto para redactar Tweet en X (/home)"
                _safe_print(f"❌ [TWITTER PLAYWRIGHT] {err}")
                try:
                    await page.screenshot(path="twitter_no_textbox.png")
                except Exception:
                    pass
                return PublishResult(False, "twitter", err)

            # Escribir el texto
            await textbox.click()
            await page.wait_for_timeout(500)
            await page.keyboard.type(tweet_text, delay=15)
            _safe_print("   [TWITTER PLAYWRIGHT] Texto redactado.")

            # Adjuntar imagen si existe
            image_path = details.get("screenshot") or details.get("visual_capture") or details.get("manual_image")
            if not image_path or not os.path.exists(str(image_path)):
                prod_id = details.get("id")
                if prod_id:
                    cap_path = os.path.join(Config.CAPTURES_DIR, f"{prod_id}.png")
                    if os.path.exists(cap_path):
                        image_path = cap_path

            if image_path and os.path.exists(str(image_path)):
                try:
                    file_input = page.locator('input[type="file"]').first
                    if await file_input.count() > 0:
                        _safe_print(f"   [TWITTER PLAYWRIGHT] Subiendo imagen: {image_path}")
                        await file_input.set_input_files(str(image_path))
                        await page.wait_for_timeout(3500)
                except Exception as img_err:
                    _safe_print(f"⚠️ [TWITTER PLAYWRIGHT] Error adjuntando imagen: {img_err}")

            # Buscar botón Postear / Post (`button[data-testid="tweetButtonInline"]`)
            post_btn = None
            btn_selectors = [
                'button[data-testid="tweetButtonInline"]',
                '[data-testid="tweetButtonInline"]',
                'button[data-testid="tweetButton"]',
                '[data-testid="tweetButton"]',
                'button:has-text("Postear")',
                'button:has-text("Publicar")',
                'button:has-text("Post")',
                'div[role="button"]:has-text("Postear")',
                'div[role="button"]:has-text("Publicar")'
            ]
            for sel in btn_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        post_btn = loc
                        break
                except Exception:
                    pass

            if not post_btn:
                err = "No se encontró el botón Postear en X (/home)"
                _safe_print(f"❌ [TWITTER PLAYWRIGHT] {err}")
                try:
                    await page.screenshot(path="twitter_no_post_btn.png")
                except Exception:
                    pass
                return PublishResult(False, "twitter", err)

            # ⏳ Esperar activamente a que el botón esté habilitado (subida de imagen terminada)
            _safe_print("   [TWITTER PLAYWRIGHT] Esperando a que el botón Postear se habilite (procesando imagen)...")
            start_w = asyncio.get_event_loop().time()
            btn_ready = False
            while (asyncio.get_event_loop().time() - start_w) < 15:
                try:
                    is_dis = await post_btn.is_disabled()
                    aria_dis = await post_btn.get_attribute("aria-disabled")
                    if not is_dis and aria_dis != "true":
                        btn_ready = True
                        break
                except Exception:
                    pass
                await page.wait_for_timeout(500)

            _safe_print(f"   [TWITTER PLAYWRIGHT] Estado botón Postear listo: {btn_ready}. Enviando tweet...")

            # Intento 1: Click normal o Control+Enter
            try:
                await post_btn.click(timeout=5000)
            except Exception:
                await textbox.focus()
                await page.keyboard.press("Control+Enter")

            await page.wait_for_timeout(4000)

            # Si el texto sigue presente en el editor, reintentar con Control+Enter y click forzado
            try:
                if await textbox.count() > 0 and await textbox.is_visible():
                    val = await textbox.text_content()
                    if val and len(val.strip()) > 5:
                        _safe_print("   [TWITTER PLAYWRIGHT] Reintentando envío con Control+Enter...")
                        await textbox.focus()
                        await page.keyboard.press("Control+Enter")
                        await page.wait_for_timeout(2000)
                        if await textbox.count() > 0 and await textbox.is_visible():
                            val2 = await textbox.text_content()
                            if val2 and len(val2.strip()) > 5:
                                await post_btn.click(force=True, timeout=5000)
                                await page.wait_for_timeout(4000)
            except Exception:
                pass

            # 📸 Evidencia visual y validación post-envío
            import time
            timestamp = int(time.time())
            logs_dir = os.path.join(Config.BASE_DIR, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            ev_path = os.path.join(logs_dir, f"tw_posted_evidence_{timestamp}.png")
            try:
                await page.screenshot(path=ev_path)
                _safe_print(f"📸 Captura de evidencia guardada en X: {ev_path}")
            except Exception:
                pass

            # Verificar si el texto se limpió (si el texto sigue en la caja, el post falló)
            text_still_present = False
            try:
                if await textbox.count() > 0 and await textbox.is_visible():
                    val = await textbox.text_content()
                    if val and len(val.strip()) > 5:
                        text_still_present = True
            except Exception:
                pass

            if text_still_present:
                err_msg = f"X no procesó el envío: el texto permaneció en el editor. Captura guardada en {ev_path}"
                _safe_print(f"❌ [TWITTER PLAYWRIGHT] {err_msg}")
                return PublishResult(False, "twitter", err_msg)

            _safe_print("✅ [TWITTER PLAYWRIGHT] Tweet publicado exitosamente desde /home!")
            if self.telegram_bot:
                notify_msg = (
                    f"🐦 *Tweet publicado en X (Playwright)*\n"
                    f"📦 {details.get('title', 'Producto')[:50]}\n"
                    f"🔗 {affiliate_link}"
                )
                asyncio.create_task(self.telegram_bot.send_notification(notify_msg))

            return PublishResult(True, "twitter", "Tweet publicado en X (Playwright)")

        except Exception as e:
            err = f"Error en Playwright Twitter: {str(e)[:150]}"
            _safe_print(f"❌ [TWITTER PLAYWRIGHT] {err}")
            return PublishResult(False, "twitter", err, error=e)

    async def _publish_with_own_browser(self, details: Dict[str, Any], tweet_text: str, affiliate_link: str) -> PublishResult:
        """Crea un navegador de Playwright independiente si no nos proporcionaron una página."""
        from playwright.async_api import async_playwright
        storage_file = None
        for candidate in ["storage_state_linux.json", "storage_state.json", "storage_state_twitter.json"]:
            cand_path = os.path.join(Config.BASE_DIR, candidate)
            if os.path.exists(cand_path):
                try:
                    content = open(cand_path, "r", encoding="utf-8").read()
                    if "auth_token" in content or "ct0" in content:
                        storage_file = cand_path
                        break
                except Exception:
                    pass
        if not storage_file:
            storage_file = Config.STORAGE_PATH

        async with async_playwright() as p:
            launch_args = ["--no-sandbox", "--disable-setuid-sandbox"]
            browser = await p.chromium.launch(headless=True, args=launch_args)
            context = None
            if os.path.exists(storage_file):
                context = await browser.new_context(storage_state=storage_file)
            else:
                context = await browser.new_context()

            page = await context.new_page()
            try:
                res = await self._publish_via_playwright(page, details, tweet_text, affiliate_link)
                return res
            finally:
                await context.close()
                await browser.close()
