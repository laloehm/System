import os
import asyncio
import aiohttp
import re
from core.utils import with_retry
from core.message_builder import build_post_message
from core.publisher_base import Publisher, PublishResult

class PinterestPublisher(Publisher):
    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)
        self._session = None

    async def _get_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def _download_image(self, url, filepath):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 200:
                        with open(filepath, 'wb') as f:
                            f.write(await r.read())
                        return os.path.exists(filepath) and os.path.getsize(filepath) > 0
        except Exception as e:
            print(f"Error descargando imagen: {e}")
        return False

    async def _wait_for_link_field(self, page, timeout_ms=25000):
        """Espera activa a que el campo de enlace exista y NO esté disabled."""
        print("  Esperando campo de enlace...")
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) * 1000 < timeout_ms:
            try:
                link_input = page.locator('[placeholder="Agregar un enlace de destino"], [placeholder="Agrega un enlace"]')
                count = await link_input.count()
                if count > 0:
                    disabled = await link_input.first.evaluate("el => el.disabled")
                    read_only = await link_input.first.evaluate("el => el.readOnly")
                    if not disabled and not read_only:
                        is_visible = await link_input.first.is_visible()
                        if is_visible:
                            val = await link_input.first.input_value()
                            print(f"  Campo enlace listo: disabled={disabled}, value='{val[:40]}'")
                            return link_input.first
            except Exception as e:
                pass
            await page.wait_for_timeout(800)
        return None

    async def _find_save_button(self, page):
        """Busca el botón para guardar/publicar. Retorna el locator si lo encuentra."""
        print("  Buscando boton de guardar...")
        
        selectors_to_try = [
            ("button[data-test-id='board-dropdown-save-button']", "data-test-id save"),
            ("button:has-text('Guardar')", "texto 'Guardar'"),
            ("button:has-text('Guardar Pin')", "texto 'Guardar Pin'"),
            ("button:has-text('Publicar')", "texto 'Publicar'"),
            ("[data-test-id='pin-form-save-button']", "form save button"),
            ("button[type='submit']", "submit button"),
        ]
        
        for selector, desc in selectors_to_try:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    is_vis = await btn.is_visible()
                    txt = await btn.inner_text()
                    disabled = await btn.get_attribute("disabled")
                    print(f"  {desc}: visible={is_vis}, text='{txt.strip()}', disabled={disabled}")
                    return btn
            except:
                pass
        
        # Buscar todos los botones y listar los que tienen texto
        all_btns = page.locator('button')
        total = await all_btns.count()
        print(f"  Total botones en pagina: {total}")
        for i in range(total):
            try:
                txt = await all_btns.nth(i).inner_text()
                disabled = await all_btns.nth(i).get_attribute("disabled")
                if txt.strip():
                    print(f"  [{i}] '{txt.strip()}' disabled={disabled}")
            except:
                pass
        
        return None

    async def publish(self, details: dict, affiliate_link: str, **kwargs) -> PublishResult:
        """
        Publica en Pinterest via Playwright.

        kwargs:
            page (Playwright.Page): página del navegador (requerido)
        """
        page = kwargs.get("page")
        if not page:
            msg = "Falta parámetro: page requerido"
            return PublishResult(False, "pinterest", msg)

        try:
            ok = await self.post_to_pinterest(page, details, affiliate_link)
            if ok:
                return PublishResult(True, "pinterest", "Pin publicado en Pinterest")
            return PublishResult(False, "pinterest", "No se pudo publicar en Pinterest")
        except Exception as e:
            msg = f"Error publicando en Pinterest: {str(e)[:100]}"
            return PublishResult(False, "pinterest", msg, error=e)

    @with_retry(max_attempts=3, base_delay=10)
    async def post_to_pinterest(self, page, product_details, affiliate_link):
        """Publica un Pin organico en Pinterest."""
        print("=== PINTEREST PUBLISHER INICIADO ===")
        try:
            # Maximizar y asegurar que estamos en la ventana correcta
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await page.bring_to_front()
            
            # 0. Cerrar posibles popups de extensiones
            context = page.context
            if len(context.pages) > 1:
                print(f"  Cerrando {len(context.pages)-1} ventanas extra (popups)...")
                for extra_page in context.pages:
                    if extra_page != page:
                        await extra_page.close()
            
            # 1. Navegar al creador de pins (anuncios)
            await page.goto("https://mx.pinterest.com/pin-builder/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(6000)

            if "login" in page.url.lower():
                print("ERROR: Sesion expirada.")
                if self.telegram_bot:
                    asyncio.create_task(self.telegram_bot.send_notification("❌ Error en Pinterest: Sesión expirada (Requiere Login). Por favor, ingresa desde la computadora."))
                return False

            # 2. SUBIR IMAGEN — usar archivo local si existe, o descargar de URL
            image_path = product_details.get("visual_capture") or product_details.get("screenshot")
            if image_path and not os.path.isabs(image_path):
                from core.config import Config
                image_path = os.path.join(Config.BASE_DIR, image_path)
            local_file = None

            if image_path:
                if os.path.exists(image_path):
                    local_file = image_path
                    print(f"Usando imagen local: {local_file}")
                elif image_path.startswith("http"):
                    temp_file = os.path.abspath("temp_pin_download.jpg")
                    downloaded = await self._download_image(image_path, temp_file)
                    if downloaded:
                        local_file = temp_file
                        print(f"Imagen descargada: {temp_file} ({os.path.getsize(temp_file)} bytes)")
                    else:
                        print(f"Fallo descargando imagen desde URL")
                        await page.screenshot(path="pinterest_img_dl_failed.png")

            if not local_file or not os.path.exists(local_file):
                print(f"ERROR: No se encontro imagen valida. path={image_path}")
                await page.screenshot(path="pinterest_no_image.png")
                if self.telegram_bot:
                    asyncio.create_task(self.telegram_bot.send_notification("❌ Error en Pinterest: No se encontró imagen válida para subir."))
                return False

            img_path = local_file
            print(f"Subiendo imagen: {img_path} ({os.path.getsize(img_path)} bytes)")
            
            # Intentar encontrar el input de archivos oculto (más fiable)
            file_input = page.locator('input[type="file"]').first
            await file_input.set_input_files(img_path)
            
            print("Imagen subida. Esperando procesamiento (10s)...")
            await page.wait_for_timeout(10000)

            # Verificar que la imagen se procesó (buscar preview)
            preview_ok = await page.evaluate("""() => {
                const imgs = document.querySelectorAll('img[src*="pin"], .pin-image img, .image-upload img, [data-test-id="pin-image"] img, .create-tab-image img');
                return Array.from(imgs).some(img => img.naturalWidth > 100);
            }""")
            print(f"Preview de imagen detectado: {preview_ok}")
            if not preview_ok:
                print("ADVERTENCIA: Preview de imagen no detectado.")

            await page.wait_for_timeout(2000)

            # 3. TITULO - Formato Clickbait / Oferta Directa
            raw_title = product_details.get("title", "Producto")
            clean_title = raw_title.split('(')[0].split(',')[0].strip()
            
            # Cortamos a 40 chars para dar espacio al texto clickbait
            if len(clean_title) > 40:
                clean_title = clean_title[:37].rsplit(' ', 1)[0]
                
            import re
            import random
            discount = product_details.get('discount', '').strip()
            discount = re.sub(r'\s*(off|dto|descuento|de descuento)\s*', '', discount, flags=re.IGNORECASE).strip()
            has_discount = discount and discount not in ('0%', '0', '')
            
            p_name = clean_title.lower()
            if has_discount:
                templates = [
                    f"😱 {discount} de descuento en {p_name}.",
                    f"🚨 Última oportunidad: {p_name} en promo.",
                    f"✨ {p_name} con {discount} de rebaja.",
                    f"💥 {discount} OFF en {p_name}."
                ]
            else:
                templates = [
                    f"🔥 Oferta en {p_name} hoy.",
                    f"✨ Regalo útil: {p_name} con descuento.",
                    f"💥 {p_name} en oferta especial.",
                    f"🚨 ¡No te pierdas este {p_name}!"
                ]
                
            clean_title = random.choice(templates)
            # Capitalizar la primera letra real después del emoji (posición 2)
            clean_title = clean_title[:2] + clean_title[2].upper() + clean_title[3:]

            print(f"Llenando Título: {clean_title}")
            title_el = None
            for ph in ["Agrega un título", "Cuéntales a todos de qué se trata tu Pin"]:
                el = page.get_by_placeholder(ph)
                if await el.count() > 0:
                    title_el = el
                    break

            if title_el:
                await title_el.wait_for(state="visible", timeout=10000)
                await title_el.click()
                await title_el.fill(clean_title)
                print("- Título OK.")

            # 4. DESCRIPCIÓN (Consumiendo el message_builder unificado)
            lines = build_post_message(product_details, affiliate_link, platform="pinterest")
            description = "\n".join(lines)

            print("Llenando Descripcion...")
            desc_el = page.locator('div.public-DraftEditor-content').last
            
            if await desc_el.count() > 0:
                await desc_el.click()
                await page.wait_for_timeout(400)
                await page.keyboard.type(description, delay=15)
                print("- Descripcion OK.")
            else:
                print("ADVERTENCIA: Campo descripcion DraftEditor no encontrado. Fallback...")
                # Fallback por placeholder alternativo (aunque Pinterest suele usar Draft.js)
                for ph in ["Cuéntales a todos de qué se trata tu Pin", "Describe tu Pin", "Agregar una descripcion"]:
                    el = page.get_by_placeholder(ph)
                    if await el.count() > 0:
                        await el.first.click()
                        await page.wait_for_timeout(400)
                        await page.keyboard.type(description, delay=15)
                        print("- Descripcion OK (Fallback).")
                        break

            # 5. TABLERO — Omitir si ya está seleccionado "Promos"
            print("Verificando tablero...")
            board_trigger = page.locator('[data-test-id="board-dropdown-select-button"]').first
            await board_trigger.wait_for(state="visible", timeout=5000)
            current_board = await board_trigger.inner_text()
            print(f"  Tablero actual: '{current_board.strip()}'")

            if "Promos" in current_board:
                print("  Tablero 'Promos' ya seleccionado por defecto. Saltando...")
            else:
                print("  Seleccionando tablero 'Promos'...")
                await board_trigger.click()
                await page.wait_for_timeout(2000)

                search_input = page.get_by_placeholder("Buscar").first
                await search_input.fill("Promos")
                await page.wait_for_timeout(2000)

                board_row = page.locator('[data-test-id="board-row"]').filter(has_text="Promos").first
                await board_row.wait_for(state="visible", timeout=5000)
                await board_row.click()
                print("- Tablero 'Promos' seleccionado.")
                await page.wait_for_timeout(2000)

            # 6. ENLACE
            print("Llenando Enlace...")
            link_el = await self._wait_for_link_field(page, timeout_ms=25000)
            if link_el:
                await link_el.click()
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(affiliate_link, delay=30)
                await page.keyboard.press("Tab")
                print(f"- Enlace OK: {affiliate_link}")
            else:
                print("ERROR: Campo de enlace no disponible.")

            await page.screenshot(path="antes_de_publicar.png")

            # 7. PUBLICAR — Acción definitiva tras asegurar carga de imagen
            print("Buscando botón Publicar en el header...")
            publish_btn = page.locator('div[role="button"]:has-text("Publicar"), button:has-text("Publicar")').last
            
            if await publish_btn.count() > 0:
                box = await publish_btn.bounding_box()
                if box:
                    # Movimiento humano del ratón
                    await page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    await page.wait_for_timeout(500)
                    await page.mouse.down()
                    await page.wait_for_timeout(100)
                    await page.mouse.up()
                    print("- Clic físico de ratón ejecutado en el botón.")
                else:
                    await publish_btn.click(force=True)
                
                print("- Secuencia de publicación completada.")
            else:
                print("ERROR: No se encontró el botón de publicar.")

            await page.wait_for_timeout(8000)

            # 8. VERIFICAR PUBLICACION
            if "/pin/" in page.url:
                print(f"PUBLICADO! URL: {page.url}")
                if self.telegram_bot:
                    asyncio.create_task(self.telegram_bot.send_notification(f"📌 ¡PIN PUBLICADO!\n🔗 {page.url}"))
                return page.url

            # Intentar "Ver pin" link
            try:
                ver = page.get_by_text("Ver").or_(page.get_by_text("Ver Pin")).first
                await ver.wait_for(state="visible", timeout=6000)
                href = await ver.get_attribute("href")
                if href:
                    if href.startswith("/"):
                        href = "https://www.pinterest.com" + href
                    print(f"Pin publicado via enlace 'Ver': {href}")
                    if self.telegram_bot:
                        asyncio.create_task(self.telegram_bot.send_notification(f"📌 ¡PIN PUBLICADO!\n🔗 {href}"))
                    return href
            except:
                pass

            await page.screenshot(path="despues_de_publicar.png")
            print("No se detecto confirmacion de publicacion.")
            if self.telegram_bot:
                asyncio.create_task(self.telegram_bot.send_notification(f"📌 ¡PIN PUBLICADO!\n🔗 (No se pudo capturar el link exacto, verificar en el perfil)"))
            return "Publicado (verificar manualmente)"

        except Exception as e:
            print(f"Error en Pinterest: {e}")
            try:
                error_path = os.path.abspath("pinterest_error_dump.png")
                await page.screenshot(path=error_path)
                if self.telegram_bot:
                    asyncio.create_task(self.telegram_bot.send_photo(
                        photo_path=error_path,
                        caption=f"❌ **Error en Pinterest:**\n\n```text\n{str(e)}\n```\n_Captura de pantalla generada en el momento del error._",
                        parse_mode="Markdown"
                    ))
            except Exception as screenshot_e:
                print(f"No se pudo tomar la captura de error de Pinterest: {screenshot_e}")
                if self.telegram_bot:
                    asyncio.create_task(self.telegram_bot.send_notification(f"❌ Error crítico en Pinterest: {e}"))
            return False