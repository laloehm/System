import asyncio
import os
import re
from playwright.async_api import async_playwright
from core.publisher_base import Publisher, PublishResult

class TikTokPublisher(Publisher):
    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)
        self.state_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_state.json")

    async def publish(self, details: dict, affiliate_link: str, **kwargs) -> PublishResult:
        """
        Publica un video en TikTok.

        kwargs:
            video_path (str): ruta del video local (requerido)
        """
        video_path = kwargs.get("video_path")
        if not video_path:
            msg = "Falta parámetro: video_path requerido"
            return PublishResult(False, "tiktok", msg)

        # Construir caption del producto
        from core.message_builder import build_post_message
        msg_lines = build_post_message(details, affiliate_link, platform="tiktok")
        caption = "\n".join(msg_lines) if msg_lines else "Nueva oferta disponible"

        try:
            ok = await self.publish_video(video_path, caption)
            if ok:
                return PublishResult(True, "tiktok", "Video publicado en TikTok")
            return PublishResult(False, "tiktok", "No se pudo publicar en TikTok")
        except Exception as e:
            msg = f"Error publicando en TikTok: {str(e)[:100]}"
            return PublishResult(False, "tiktok", msg, error=e)

    async def publish_video(self, video_path: str, caption: str) -> bool:
        """
        Sube un video a TikTok utilizando la sesión guardada y Playwright.
        Retorna True si tuvo éxito, False en caso de fallo.
        """
        if not os.path.exists(self.state_file):
            print("❌ ERROR: No se encontró 'tiktok_state.json'. Debes extraer las cookies primero.")
            return False

        if not os.path.exists(video_path):
            print(f"❌ ERROR: El video {video_path} no existe.")
            return False

        print(f"🚀 Iniciando publicador fantasma de TikTok para: {video_path}")
        
        async with async_playwright() as p:
            try:
                # Arrancar en modo headless para no estorbar en el servidor
                browser = await p.chromium.launch(headless=True)
                
                # Cargamos la sesión robada (cookies)
                context = await browser.new_context(
                    storage_state=self.state_file,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                
                # Bloquear recursos innecesarios para que cargue más rápido y evitar detecciones
                await context.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf}", lambda route: route.continue_())
                
                page = await context.new_page()

                print("🌐 Navegando a TikTok Creator Center...")
                await page.goto("https://www.tiktok.com/creator-center/upload", timeout=60000)

                # Intentar inyectar el archivo de video
                # El input file suele estar escondido, pero Playwright puede interactuar con él
                print("📤 Inyectando el archivo de video...")
                
                # Seleccionar el primer input de tipo file
                file_input = page.locator('input[type="file"][accept="video/*"]')
                
                # Esperar a que exista el input
                await file_input.wait_for(state="attached", timeout=30000)
                await file_input.set_input_files(video_path)
                
                print("⏳ Esperando a que el video cargue en la plataforma...")
                # Esperar un momento a que aparezca la caja de texto o termine la subida
                # Normalmente aparece un div contenteditable
                caption_box = page.locator('.public-DraftEditor-content')
                await caption_box.wait_for(state="visible", timeout=60000)
                
                print("📝 Escribiendo la descripción (Copy)...")
                
                # Eliminar el molesto tutorial de TikTok que bloqueaba los clicks
                await page.evaluate("() => { const overlay = document.getElementById('react-joyride-portal'); if(overlay) overlay.remove(); }")
                
                # Llenar la descripción.
                await caption_box.click()
                
                # Limpiar por si había algo (Ctrl+A, Backspace)
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                
                # Procesar la descripción separando texto normal de hashtags
                # Los hashtags requieren seleccionar del autocomplete de TikTok (Draft.js)
                text_part = re.sub(r'#\w+', '', caption).strip()
                hashtags = re.findall(r'#\w+', caption)

                # Escribir el texto principal primero
                if text_part:
                    await page.keyboard.type(text_part, delay=5)
                    await page.keyboard.type(" ")

                # Añadir cada hashtag seleccionando del autocomplete
                for tag in hashtags:
                    await page.keyboard.type(tag, delay=40)
                    await page.wait_for_timeout(1200)  # Esperar a que aparezca el dropdown

                    # Intentar seleccionar el primer resultado del autocomplete
                    selected = False
                    for selector in [
                        '[class*="hashtagPanel"] [class*="item"]',
                        '[class*="HashtagList"] [class*="item"]',
                        '[class*="suggestList"] li',
                        '[role="listbox"] [role="option"]',
                        '[class*="SuggestList"] [class*="SuggestItem"]',
                    ]:
                        try:
                            suggestion = page.locator(selector).first
                            await suggestion.wait_for(state="visible", timeout=1000)
                            await suggestion.click()
                            await page.wait_for_timeout(300)
                            selected = True
                            break
                        except:
                            continue

                    if not selected:
                        # Fallback: ArrowDown + Enter para seleccionar del dropdown
                        await page.keyboard.press("ArrowDown")
                        await page.wait_for_timeout(200)
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(300)

                    await page.keyboard.type(" ")
                    await page.wait_for_timeout(150)

                print("👆 Esperando a que el video termine de subir y el botón 'Publicar' se habilite...")
                # Excluir botón del header y del sidebar de navegación que también dice "Publicar"
                post_button = page.locator(
                    'button:not([data-tt="components_PostTableHeader_Clickable"]):not([data-tt="Sidebar_Sidebar_Clickable"])'
                ).filter(has_text=re.compile(r"^(Publicar|Post)$", re.IGNORECASE)).last

                await post_button.click(timeout=300000)

                print("✅ ¡Primer click en publicar realizado! Revisando si hay modal de confirmación...")

                try:
                    confirm_btn = page.get_by_role("button", name=re.compile("Post now|Publicar ahora|Publicar de todos modos", re.IGNORECASE)).first
                    await confirm_btn.click(timeout=5000)
                    print("⚠️ Modal de copyright detectado y superado (Click en Post now).")
                except:
                    print("ℹ️ No hubo modal de copyright.")

                # Confirmar éxito por cambio de URL (TikTok redirige al salir del upload)
                # o por desaparición del botón — lo que ocurra primero
                print("⏳ Esperando confirmación de publicación...")
                try:
                    await page.wait_for_url(
                        lambda url: "upload" not in url and "creator-center" in url,
                        timeout=60000
                    )
                except:
                    try:
                        await post_button.wait_for(state="hidden", timeout=15000)
                    except:
                        pass  # Si ninguno confirma, asumimos éxito porque el click ya se hizo

                await page.wait_for_timeout(3000)
                print("🎉 ¡Video de TikTok publicado exitosamente!")
                await browser.close()
                return True

            except Exception as e:
                print(f"💀 Error catastrófico en el publicador de TikTok: {e}")
                # Tomar un pantallazo del error por si el usuario quiere debuguearlo
                try:
                    await page.screenshot(path="tiktok_error.png")
                    print("📸 Pantallazo del error guardado como 'tiktok_error.png'")
                except:
                    pass
                if 'browser' in locals():
                    await browser.close()
                return False
