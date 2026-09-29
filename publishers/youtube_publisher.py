import asyncio
import os
import re
from playwright.async_api import async_playwright
from core.publisher_base import Publisher, PublishResult

class YouTubePublisher(Publisher):
    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)
        self.state_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "youtube_state.json")

    async def publish(self, details: dict, affiliate_link: str, **kwargs) -> PublishResult:
        """
        Publica un video en YouTube Shorts.

        kwargs:
            video_path (str): ruta del video local (requerido)
        """
        video_path = kwargs.get("video_path")
        if not video_path:
            msg = "Falta parámetro: video_path requerido"
            return PublishResult(False, "youtube", msg)

        title = details.get("title", "Nueva oferta")[:50]
        description = f"Oferta especial: {affiliate_link}"

        try:
            result = await self.publish_video(video_path, title, description)
            if result:
                return PublishResult(True, "youtube", f"Video publicado: {result}")
            return PublishResult(False, "youtube", "No se pudo publicar en YouTube")
        except Exception as e:
            msg = f"Error publicando en YouTube: {str(e)[:100]}"
            return PublishResult(False, "youtube", msg, error=e)

    async def publish_video(self, video_path: str, title: str, description: str):
        """
        Sube un video a YouTube Shorts utilizando la sesión guardada y Playwright.
        Retorna la URL del video (str) si tuvo éxito, False en caso de fallo.
        """
        if not os.path.exists(self.state_file):
            print("❌ ERROR: No se encontró 'youtube_state.json'. Debes extraer las cookies primero.")
            return False

        if not os.path.exists(video_path):
            print(f"❌ ERROR: El video {video_path} no existe.")
            return False

        print(f"🚀 Iniciando publicador fantasma de YouTube para: {video_path}")
        from playwright_stealth import Stealth
        async with Stealth().use_async(async_playwright()) as p:
            try:
                # Añadimos flags anti-detección para que Google no bloquee la API de "createvideo" en headless
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled'],
                    ignore_default_args=["--enable-automation"]
                )
                
                context = await browser.new_context(
                    storage_state=self.state_file,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                
                # Bloquear recursos innecesarios
                await context.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf}", lambda route: route.continue_())
                
                page = await context.new_page()

                print("🌐 Navegando a YouTube Studio...")
                await page.goto("https://studio.youtube.com/", timeout=60000)
                await page.wait_for_timeout(5000)
                
                # Verificar si logramos entrar al Studio (Google redirige a accounts.google.com cuando la sesión expiró)
                if "studio.youtube.com" not in page.url or "accounts.google.com" in page.url:
                    print(f"❌ ERROR: Sesión de YouTube expirada. Redirigido a: {page.url}")
                    print("💡 Regenera youtube_state.json ejecutando: python3 refresh_youtube_session.py")
                    if hasattr(self, 'telegram_bot') and self.telegram_bot:
                        pass
                    await browser.close()
                    return False

                print("📤 Iniciando flujo de subida...")
                # YouTube Studio cambia selectores frecuentemente — probar varios
                create_btn = None
                for selector in [
                    '#create-icon',
                    'ytcp-button#create-icon',
                    'button[aria-label*="Create"]',
                    'button[aria-label*="Crear"]',
                    '#upload-icon',
                    'ytcp-icon-button[id="create-icon"]',
                ]:
                    try:
                        candidate = page.locator(selector)
                        await candidate.wait_for(state="visible", timeout=8000)
                        create_btn = candidate
                        print(f"✅ Botón Crear encontrado con selector: {selector}")
                        break
                    except:
                        continue

                if not create_btn:
                    raise Exception("No se encontró el botón Crear en YouTube Studio — el selector cambió.")

                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(1000)
                    await page.evaluate("document.querySelectorAll('tp-yt-iron-overlay-backdrop').forEach(el => el.remove());")
                except:
                    pass

                await create_btn.click(force=True)

                # Dar click en Subir Video (solo si no se abrió el modal directo)
                file_input = page.locator('input[type="file"]')
                try:
                    await file_input.wait_for(state="attached", timeout=5000)
                except:
                    upload_item = None
                    for selector in ['#text-item-0', '[test-id="upload-beta-button"]', 'tp-yt-paper-item:first-child']:
                        try:
                            candidate = page.locator(selector)
                            await candidate.wait_for(state="visible", timeout=8000)
                            upload_item = candidate
                            break
                        except:
                            continue

                    if not upload_item:
                        raise Exception("No se encontró la opción 'Subir video' en el menú de Crear.")

                    await upload_item.click()
                    await file_input.wait_for(state="attached", timeout=30000)
                
                print("🎬 Inyectando el archivo de video...")
                await file_input.set_input_files(video_path)
                
                print("⏳ Esperando que cargue el panel de detalles...")
                # Esperar a que el modal de subida cambie a la vista de detalles
                # Buscamos el textbox del título
                title_box = page.locator('#title-textarea #textbox')
                await title_box.wait_for(state="visible", timeout=60000)
                
                # IMPORTANTE: Esperar a que YouTube genere el ID del video y guarde el borrador inicial.
                # Si borramos el título instantáneamente en un VPS rápido, la API de YouTube se corrompe y se queda en "Creando enlace."
                print("⏳ Esperando estabilización del borrador inicial...")
                await page.wait_for_timeout(5000)

                # Intentar capturar la URL del video
                video_url = "Publicado"
                try:
                    video_link_el = page.locator('a.ytcp-video-info')
                    await video_link_el.wait_for(state="attached", timeout=5000)
                    video_url = await video_link_el.get_attribute("href")
                    print(f"🔗 URL del video extraída: {video_url}")
                except Exception as ex:
                    print(f"⚠️ No se pudo extraer la URL del video: {ex}")
                
                print("📝 Llenando el título y la descripción...")
                # Limpiar el título por defecto (suele poner el nombre del archivo mp4)
                await title_box.click()
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(title, delay=10)
                await page.wait_for_timeout(1000)
                
                # Llenar la descripción
                desc_box = page.locator('#description-textarea #textbox')
                await desc_box.click()
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                
                # Inyectar texto simulando pegado (dispara eventos nativos de Polymer y React correctamente)
                await page.keyboard.insert_text(description)
                await page.keyboard.type(" ")
                await page.wait_for_timeout(2000)

                print("👶 Seleccionando 'No es contenido para niños'...")
                # Scroll y click en el radio button de No para niños
                kids_radio = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]')
                await kids_radio.scroll_into_view_if_needed()
                await kids_radio.click()
                await page.wait_for_timeout(1000)

                print("⏭️ Avanzando por las pestañas...")
                next_btn = page.locator('#next-button')
                
                # Pestaña 1 -> 2 (Detalles a Elementos)
                await next_btn.click()
                await page.wait_for_timeout(1000)
                # Pestaña 2 -> 3 (Elementos a Chequeos)
                await next_btn.click()
                await page.wait_for_timeout(1000)
                # Pestaña 3 -> 4 (Chequeos a Visibilidad)
                await next_btn.click()
                await page.wait_for_timeout(2000)

                print("👁️ Seleccionando Visibilidad 'Público'...")
                # Ya en la última pestaña, seleccionamos Público
                public_radio = page.locator('tp-yt-paper-radio-button[name="PUBLIC"]')
                await public_radio.scroll_into_view_if_needed()
                await public_radio.click(force=True)
                await page.wait_for_timeout(2000)

                print("👆 Esperando a que el video termine de subir y procesar para poder Publicar...")
                publish_btn = page.locator('#done-button')
                
                published = False
                for _ in range(60):
                    # 1. Ejecutar script ninja para cerrar cualquier modal molesto (Publicar de todas formas / Cerrar éxito)
                    try:
                        await page.evaluate('''() => {
                            const buttons = document.querySelectorAll('ytcp-button, tp-yt-paper-button, button');
                            for (const btn of buttons) {
                                const txt = (btn.textContent || "").toLowerCase().trim();
                                // Solo clickear alertas de Copyright ("Publicar de todas formas")
                                if (txt.includes('publicar de todas') || txt.includes('publicar de todos') || 
                                    txt.includes('publish anyway') || txt.includes('guardar de todos')) {
                                    btn.click();
                                }
                                // Solo clickear "Cerrar" si es el botón del modal de éxito final
                                if (btn.id === 'close-button' && (txt.includes('cerrar') || txt === 'close')) {
                                    btn.click();
                                }
                            }
                        }''')
                    except:
                        pass
                        
                    # 2. Verificar éxito: Si el dialog principal de subida desapareció y ya no hay warning modals
                    try:
                        # Si el botón #done-button ya no existe en el DOM, es porque cerramos todo con éxito
                        if await publish_btn.count() == 0:
                            published = True
                            break
                    except:
                        pass

                    # 3. Intentar hacer clic en el botón principal si todavía existe y está habilitado
                    try:
                        if await publish_btn.count() > 0 and not await publish_btn.is_hidden():
                            if await publish_btn.get_attribute("aria-disabled") != "true" and await publish_btn.get_attribute("disabled") is None:
                                await publish_btn.click(force=True)
                    except:
                        pass
                        
                    await page.wait_for_timeout(4000)
                    
                if not published:
                    raise Exception("El botón 'Publicar' nunca se habilitó o el modal nunca se cerró tras 5 minutos.")
                
                print("🎉 ¡Video de YouTube Shorts publicado exitosamente!")
                await browser.close()
                return video_url

            except Exception as e:
                print(f"💀 Error catastrófico en el publicador de YouTube: {e}")
                try:
                    await page.screenshot(path="youtube_error.png")
                    print("📸 Pantallazo del error guardado como 'youtube_error.png'")
                except:
                    pass
                await browser.close()
                return False
