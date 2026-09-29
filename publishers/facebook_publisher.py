from core.facebook_groups_notes import get_note
import os
import asyncio
from core.message_builder import build_post_message
from core.publisher_base import Publisher, PublishResult

class FacebookLimitedException(Exception):
    """Excepción lanzada cuando Facebook bloquea temporalmente por límite de frecuencia de publicaciones."""
    pass

class FacebookPublisher(Publisher):
    def __init__(self, telegram_bot=None):
        super().__init__(telegram_bot)

    # ═══════════════════════════════════════════════════════════════════════════
    # FASE 1: MÉTODOS DE UTILIDAD
    # ═══════════════════════════════════════════════════════════════════════════

    async def _navigate_to_group(self, page, group_url: str):
        """Navega al URL del grupo de Facebook."""
        print(f"Navegando al grupo: {group_url}")
        await page.goto(group_url, wait_until="load", timeout=60000)
        await page.wait_for_timeout(4000)

    async def _check_rate_limit_upfront(self, page):
        """Detecta rate limit inmediatamente al entrar al grupo."""
        limit_detected = await page.evaluate('''() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes("limitamos la frecuencia") ||
                   text.includes("we limit how often") ||
                   text.includes("temporalmente bloqueado") ||
                   text.includes("temporarily blocked");
        }''')
        if limit_detected:
            raise FacebookLimitedException("Facebook detectó y aplicó un bloqueo temporal por límite de frecuencia en la cuenta.")

    def _get_log_dir(self) -> str:
        """Obtiene o crea el directorio de logs."""
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

    async def _capture_evidence(self, page, log_dir: str, filename_prefix: str = "fb_posted_evidence") -> str:
        """Toma una captura de pantalla de evidencia."""
        try:
            evidence_path = os.path.join(log_dir, f"{filename_prefix}_{int(__import__('time').time())}.png")
            await page.screenshot(path=evidence_path)
            print(f"📸 Captura de evidencia guardada: {evidence_path}")
            return evidence_path
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════════════════
    # FASE 2: ABRIR COMPOSITOR (Estrategia principal + rescate)
    # ═══════════════════════════════════════════════════════════════════════════

    async def _open_post_composer(self, page, log_dir: str):
        """Abre el compositor de posts. Intenta estrategia principal y rescate si falla."""
        print("Buscando el compositor de post principal...")

        # Estrategia 0: Selectores Nativos de Playwright (Muy precisos y manejan visibilidad automáticamente)
        exact_selectors = [
            "div[role='button']:has(span:text-is('Escribe algo...'))",
            "div[role='button']:has(span:text-is('Write something...'))",
            "div[role='button']:has(span:text-is('¿Qué tienes en mente?'))",
            "div[role='button']:has(span:text-is('What\\'s on your mind?'))",
            "div[role='button']:has(span:text-is('Crear publicación pública'))"
        ]
        for sel in exact_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=1000):
                    await loc.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)
                    await loc.click(timeout=3000)
                    print(f"Clic exitoso usando selector nativo: {sel}")
                    return True
            except Exception:
                continue

        # Estrategia 1: JS robusto que busca por ESTRUCTURA HTML (más confiable que texto)
        js_find_composer = '''() => {
            // Búsqueda por texto contenido, yendo hacia arriba al botón padre
            const elements = document.querySelectorAll('div[role="button"], span');
            for(let el of elements) {
                const txt = (el.textContent || "").toLowerCase().trim();
                
                const validTexts = [
                    "escribe algo...", "escribe algo",
                    "write something...", "write something",
                    "¿qué tienes en mente?", "qué tienes en mente",
                    "on your mind", "crear publicación pública",
                    "create a public post"
                ];
                let match = false;
                for (let v of validTexts) {
                    if (txt === v || txt.startsWith("escribe algo") || txt.startsWith("write something")) {
                        match = true;
                        break;
                    }
                }
                              
                if (match) {
                    if (txt.includes("coment") || txt.includes("comment") || txt.includes("responder")) continue;
                    
                    let target = el;
                    let current = el;
                    while (current && current !== document.body) {
                        if (current.getAttribute("role") === "button" || current.tagName === "BUTTON") {
                            target = current;
                            break;
                        }
                        current = current.parentElement;
                    }
                    
                    const rect = target.getBoundingClientRect();
                    if (rect.width > 20 && rect.height > 10 && rect.y >= -100 && rect.y < 1200) {
                        target.scrollIntoView({ behavior: 'auto', block: 'center' });
                        target.id = 'bot_composer_target_btn';
                        return true;
                    }
                }
            }
            return false;
        }'''

        found = await page.evaluate(js_find_composer)
        if found:
            print("Haciendo clic nativo en el compositor (ID inyectado)...")
            await page.click('#bot_composer_target_btn', timeout=5000)
            return True

        # Estrategia 1B: Selectores directos
        alt_selectors = [
            "div[role='button']:has-text('Escribe algo...')",
            "div[role='button']:has-text('Write something...')"
        ]
        for sel in alt_selectors:
            try:
                await page.click(sel, timeout=3000)
                return True
            except:
                continue

        # Estrategia 2: Rescate para grupos de Compra/Venta (ir a pestaña Conversación)
        print("⚠️ Compositor no encontrado. Posible grupo de Compra/Venta. Intentando rescate (Pestaña Conversación)...")
        return await self._rescue_composer_via_discussion_tab(page, js_find_composer, alt_selectors, log_dir)

    async def _rescue_composer_via_discussion_tab(self, page, js_find_composer: str, alt_selectors: list, log_dir: str) -> bool:
        """Intenta abrir el compositor via pestaña de Conversación (rescate)."""
        js_find_discussion_tab = '''() => {
            const tabs = Array.from(document.querySelectorAll('a[role="tab"], div[role="tab"], a[role="link"]'));
            for (const tab of tabs) {
                const text = (tab.innerText || "").toLowerCase();
                if (text === "conversación" || text === "conversacion" || text === "discussion" || text.includes("conversación")) {
                    tab.scrollIntoView({ behavior: 'auto', block: 'center' });
                    tab.id = 'bot_discussion_tab_btn';
                    return true;
                }
            }
            return false;
        }'''

        found_tab = await page.evaluate(js_find_discussion_tab)
        if not found_tab:
            print("Error: No se pudo abrir la caja de post ni con rescate. Tomando captura...")
            await self._capture_evidence(page, log_dir, "fb_composer_not_found")
            raise Exception("No se encontró el botón de 'Escribe algo...' (Compositor de publicación).")

        print("Pestaña de Conversación encontrada. Haciendo clic...")
        try:
            await page.click('#bot_discussion_tab_btn', timeout=5000)
            await page.wait_for_timeout(4000)
            print("Reintentando búsqueda del compositor...")

            found_again = await page.evaluate(js_find_composer)
            if found_again:
                print("Haciendo clic nativo en el compositor rescatado...")
                await page.click('#bot_composer_target_btn', timeout=5000)
                return True

            for sel in alt_selectors:
                try:
                    await page.click(sel, timeout=3000)
                    return True
                except:
                    continue
        except Exception as resc_err:
            print(f"Error en el clic de rescate: {resc_err}")

        print("Error: No se pudo abrir la caja de post ni con rescate. Tomando captura...")
        await self._capture_evidence(page, log_dir, "fb_composer_not_found")
        raise Exception("No se encontró el botón de 'Escribe algo...' (Compositor de publicación).")

    async def _wait_modal_open(self, page):
        """Espera a que el modal del compositor se abra completamente."""
        print("Esperando la apertura del modal del compositor...")
        try:
            await page.wait_for_selector('div[role="dialog"] [contenteditable="true"]', timeout=15000)
        except:
            pass
        await page.wait_for_timeout(4000)

    async def _find_modal_textbox(self, page, log_dir: str):
        """Encuentra y retorna la caja de texto dentro del modal de publicación."""
        js_find_modal_textbox = '''() => {
            const allTb = document.querySelectorAll('[contenteditable="true"], textarea, [data-lexical-editor="true"]');
            for (const tb of allTb) {
                const rect = tb.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                
                const label = (tb.getAttribute("aria-label") || "").toLowerCase();
                const placeholder = (tb.getAttribute("placeholder") || "").toLowerCase();
                const text = label + " " + placeholder;
                
                if (!text.includes("coment") && !text.includes("comment") && !text.includes("buscar") && !text.includes("search") && !text.includes("título") && !text.includes("title")) {
                    tb.id = 'bot_modal_textbox_target';
                    return true;
                }
            }
            return false;
        }'''

        found_modal = await page.evaluate(js_find_modal_textbox)
        if not found_modal:
            print("Alerta: No se encontró caja de texto segura. Tomando captura...")
            await self._capture_evidence(page, log_dir, "fb_modal_error")
            raise Exception("No se encontró la caja de texto dentro de la ventana de publicación.")

        textbox = page.locator('#bot_modal_textbox_target')
        await textbox.focus()
        return textbox

    async def _upload_product_image(self, page, product_details: dict):
        """Sube la imagen del producto si existe."""
        img_path = product_details.get("visual_capture") or product_details.get("screenshot")
        if img_path and not os.path.isabs(img_path):
            from core.config import Config
            img_path = os.path.join(Config.BASE_DIR, img_path)

        if not img_path or not os.path.exists(img_path):
            print("Aviso: No se encontró imagen local válida para subir.")
            return

        print(f"Subiendo imagen del producto ({img_path})...")
        try:
            photo_btn_sel = "div[aria-label='Foto/video'], div[aria-label='Photo/video'], div[data-testid='media-attachment-button']"
            async with page.expect_file_chooser() as fc_info:
                await page.click(photo_btn_sel, timeout=5000)
            file_chooser = await fc_info.value
            await file_chooser.set_files(img_path)
            print("Imagen cargada automáticamente.")
            await page.wait_for_timeout(5000)
        except Exception as img_err:
            try:
                await page.locator("input[type='file'][accept*='image']").first.set_input_files(img_path)
                print("Imagen cargada mediante fallback de input file.")
                await page.wait_for_timeout(4000)
            except Exception as fallback_err:
                print(f"Aviso: No se pudo subir la imagen: {fallback_err}")

    def _build_message_text(self, product_details: dict, affiliate_link: str, group_url: str) -> tuple:
        """Construye el texto del mensaje. Retorna (clean_lines, message_oneline)."""
        if "388464343440887" in group_url:
            print("Grupo de enlace directo detectado. Usando solo el link de afiliado.")
            clean_lines = [affiliate_link]
            message_oneline = affiliate_link
        else:
            lines = build_post_message(product_details, affiliate_link, platform="facebook")
            clean_lines = [l.strip() for l in lines if l.strip()]
            message_oneline = " ".join(clean_lines)
        return clean_lines, message_oneline

    async def _paste_text_to_textbox(self, page, textbox, message_oneline: str) -> bool:
        """Pega el texto en la caja. Intenta portapapeles primero, luego fallback a teclado."""
        try:
            await textbox.click(force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.wait_for_timeout(500)

            print("1. Intentando pegado de texto en una sola línea (portapapeles)...")
            await page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
            await page.evaluate("""text => {
                return Promise.race([
                    navigator.clipboard.writeText(text),
                    new Promise((_, reject) => setTimeout(() => reject(new Error('Clipboard timeout')), 3000))
                ]);
            }""", message_oneline)
            await page.keyboard.press("Control+V")
            await page.wait_for_timeout(1500)
            return True
        except Exception as clipboard_err:
            print(f"Advertencia: Pegado por portapapeles falló ({clipboard_err}). Fallback a inyección por teclado...")
            try:
                await textbox.click(force=True)
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(500)
                await page.keyboard.insert_text(message_oneline)
                await page.wait_for_timeout(1500)
                return True
            except Exception as insert_err:
                print(f"Error inyectando texto base en una sola línea: {insert_err}")
                return False

    async def _restore_line_breaks(self, page, clean_lines: list):
        """Restaura los saltos de línea en el mensaje pasted."""
        try:
            print("2. Restaurando saltos de línea visuales (Enters manuales en reversa)...")
            for i in range(len(clean_lines) - 1, 0, -1):
                search_text = clean_lines[i].strip()[:15]

                found = await page.evaluate(
                    """(searchText) => {
                        let result = window.find(searchText, false, true, false, false, false, false);
                        if (result) {
                            window.getSelection().collapseToStart();
                        }
                        return result;
                    }""",
                    search_text
                )

                if found:
                    await page.keyboard.down("Shift")
                    await page.keyboard.press("Enter")
                    await page.keyboard.up("Shift")
                    await page.wait_for_timeout(200)

            print("✅ Saltos de línea restaurados con éxito usando la Estrategia de Reversa.")
            await page.wait_for_timeout(2000)
        except Exception as rev_err:
            print(f"Error durante Enters Inversos: {rev_err}")

    async def _check_rate_limit_in_modal(self, page):
        """Detecta rate limit dentro del modal de publicación."""
        limit_in_modal = await page.evaluate('''() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes("limitamos la frecuencia") ||
                   text.includes("we limit how often") ||
                   text.includes("temporalmente bloqueado") ||
                   text.includes("temporarily blocked") ||
                   text.includes("vuelve a intentarlo más tarde") ||
                   text.includes("try again later");
        }''')
        if limit_in_modal:
            raise FacebookLimitedException("Rate limit detectado en modal de publicación. Facebook bloqueó la acción.")

    async def _click_post_button(self, page):
        """Hace clic en el botón de Publicar."""
        print("Intentando enviar publicación (Paso Final)...")

        # Verificar rate limit antes de hacer clic
        await self._check_rate_limit_in_modal(page)

        post_btns = [
            "div[role='dialog'] div[aria-label='Publicar']",
            "div[role='dialog'] div[aria-label='Post']",
            "div[role='dialog'] div[role='button'] span:text-is('Publicar')",
            "div[role='dialog'] div[role='button'] span:text-is('Post')"
        ]

        post_done = False
        for btn_sel in post_btns:
            try:
                btn = await page.wait_for_selector(btn_sel, timeout=3000)
                if btn:
                    # Esperar activamente hasta 15s a que el botón se habilite
                    for _ in range(15):
                        is_disabled = await btn.get_attribute("aria-disabled")
                        if is_disabled != "true":
                            break
                        print("⏳ Botón 'Publicar' deshabilitado. Esperando 1s...")
                        await page.wait_for_timeout(1000)

                    # Verificar una última vez si hay rate limit
                    limit_check = await page.evaluate('''() => {
                        const text = document.body.innerText.toLowerCase();
                        return text.includes("limitamos la frecuencia") || text.includes("we limit how often");
                    }''')
                    if limit_check:
                        raise FacebookLimitedException("Rate limit detectado justo antes del clic en Publicar.")

                    await btn.click()
                    print(f"Clic en '{btn_sel}' realizado.")
                    post_done = True
                    break
            except FacebookLimitedException:
                raise
            except:
                continue

        if not post_done:
            print("Fallo selectores. Intentando Control+Enter...")
            await page.keyboard.press("Control+Enter")

    async def _wait_post_confirmation(self, page) -> bool:
        """Espera la confirmación de que la publicación fue exitosa."""
        print("Esperando a que Facebook procese el envío...")
        publish_confirmed = False

        # Estrategia 1: Cierre del diálogo (señal más fuerte)
        try:
            await page.wait_for_selector("div[role='dialog']", state="hidden", timeout=20000)
            print("✅ Publicación confirmada: diálogo cerrado por Facebook.")
            publish_confirmed = True
        except Exception:
            pass

        # Estrategia 2: Toast/snackbar de éxito
        if not publish_confirmed:
            try:
                success_sel = (
                    "div[role='alert']:has-text('publicado'), "
                    "div[role='alert']:has-text('posted'), "
                    "div[data-testid='toast']:has-text('publicado'), "
                    "div[data-testid='toast']:has-text('posted'), "
                    "span:has-text('Tu publicación está disponible'), "
                    "span:has-text('Your post is now available')"
                )
                await page.wait_for_selector(success_sel, timeout=8000)
                print("✅ Publicación confirmada: toast de éxito detectado.")
                publish_confirmed = True
            except Exception:
                pass

        # Estrategia 3: Botón 'Publicar' ya no está disponible
        if not publish_confirmed:
            try:
                btn_gone = await page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll("div[aria-label='Publicar'], div[aria-label='Post']"));
                    const dialog = document.querySelector("div[role='dialog']");
                    return !dialog || btns.length === 0;
                }""")
                if btn_gone:
                    print("✅ Publicación confirmada: botón 'Publicar' ya no está en DOM.")
                    publish_confirmed = True
            except Exception:
                pass

        return publish_confirmed

    async def _check_post_click_rate_limit(self, page):
        """Verifica rate limit DESPUÉS de hacer clic en Publicar."""
        limit_post_click = await page.evaluate('''() => {
            const text = document.body.innerText.toLowerCase();
            return text.includes("limitamos la frecuencia") ||
                   text.includes("we limit how often") ||
                   text.includes("temporalmente bloqueado") ||
                   text.includes("temporarily blocked") ||
                   text.includes("vuelve a intentarlo") ||
                   text.includes("try again later");
        }''')
        if limit_post_click:
            raise FacebookLimitedException("Rate limit detectado después de intentar publicar. Abortando todos los grupos.")

    def _extract_group_name(self, group_url: str) -> str:
        """Extrae y escapa el nombre del grupo para Telegram."""
        group_name = group_url.split("/groups/")[-1].strip("/") if "/groups/" in group_url else group_url
        return group_name.replace("_", "\\_").replace("*", "\\*")

    async def _notify_telegram_success(self, product_details: dict, group_url: str, group_name_clean: str):
        """Notifica a Telegram del éxito de la publicación (incluyendo notas del Panel Web si existen)."""
        if not self.telegram_bot:
            return

        note_info = get_note(group_url)
        note_txt = note_info.get("note", "").strip() if isinstance(note_info, dict) else ""
        note_str = f"\n📝 *Nota:* _{note_txt}_" if note_txt else ""

        caption = (
            f"✅ *FB Publicado* en [Grupo {group_name_clean}]({group_url})\n"
            f"📦 {product_details.get('title', 'Producto')[:60]}\n"
            f"💰 {product_details.get('offer_price', '')}"
            f"{note_str}"
        )
        asyncio.create_task(self.telegram_bot.send_notification(caption))

    async def _notify_telegram_unconfirmed(self, product_details: dict, group_url: str, group_name_clean: str, evidence_path: str = None):
        """Notifica a Telegram cuando no se confirma la publicación (incluyendo notas)."""
        if not self.telegram_bot:
            return

        note_info = get_note(group_url)
        note_txt = note_info.get("note", "").strip() if isinstance(note_info, dict) else ""
        note_str = f"\n📝 *Nota:* _{note_txt}_" if note_txt else ""

        caption = (
            f"⚠️ *FB — No confirmado* en [Grupo {group_name_clean}]({group_url})\n"
            f"📦 {product_details.get('title', 'Producto')[:60]}\n"
            f"⚠️ Verifica manualmente si se publicó."
            f"{note_str}"
        )

        if evidence_path and os.path.exists(evidence_path):
            asyncio.create_task(self.telegram_bot.send_photo(evidence_path, caption=caption))
        else:
            asyncio.create_task(self.telegram_bot.send_notification(caption))

    async def _notify_telegram_rate_limit(self, log_dir: str):
        """Notifica a Telegram de un rate limit detectado."""
        if not self.telegram_bot:
            return

        try:
            rl_path_captured = await self._capture_evidence(None, log_dir, "fb_ratelimit")
            if rl_path_captured:
                asyncio.create_task(self.telegram_bot.send_photo(
                    rl_path_captured,
                    caption=f"🛑 *Rate Limit detectado en Facebook*\nCola abortada. Espera unas horas antes de reintentar."
                ))
        except Exception:
            pass

    async def _notify_telegram_error(self, group_url: str, group_name_clean: str, error_msg: str, log_dir: str):
        """Notifica a Telegram de un error durante la publicación (incluyendo notas)."""
        if not self.telegram_bot:
            return

        try:
            note_info = get_note(group_url)
            note_txt = note_info.get("note", "").strip() if isinstance(note_info, dict) else ""
            note_str = f"\n📝 *Nota:* _{note_txt}_" if note_txt else ""

            err_path = await self._capture_evidence(None, log_dir, "fb_error")
            if err_path:
                asyncio.create_task(self.telegram_bot.send_photo(
                    err_path,
                    caption=f"❌ *Error en FB Grupo:* [{group_name_clean}]({group_url})\n*Motivo:* `{error_msg[:200]}`{note_str}"
                ))
            else:
                asyncio.create_task(self.telegram_bot.send_notification(
                    f"❌ *Error en FB Grupo:* [{group_name_clean}]({group_url})\n*Motivo:* `{error_msg[:200]}`{note_str}"
                ))
        except Exception:
            pass

    async def publish(self, details: dict, affiliate_link: str, **kwargs) -> PublishResult:
        """
        Publica en Facebook via Playwright.

        kwargs:
            page (Playwright.Page): página del navegador (requerido)
            group_url (str): URL del grupo de Facebook (requerido)
        """
        page = kwargs.get("page")
        group_url = kwargs.get("group_url")

        if not page or not group_url:
            msg = "Faltan parámetros: page y group_url requeridos"
            return PublishResult(False, "facebook", msg)

        try:
            ok = await self.post_to_group(page, group_url, details, affiliate_link)
            if ok:
                return PublishResult(True, "facebook", f"Publicado en {group_url}", details={"group_url": group_url})
            return PublishResult(False, "facebook", f"No se pudo publicar en {group_url}")
        except FacebookLimitedException as e:
            msg = f"Límite de Facebook: {str(e)}"
            return PublishResult(False, "facebook", msg, error=e, details={"rate_limited": True})
        except Exception as e:
            msg = f"Error publicando en Facebook: {str(e)[:100]}"
            return PublishResult(False, "facebook", msg, error=e)

    async def post_to_group(self, page, group_url, product_details, affiliate_link):
        """
        Router puro: Publica el producto en el grupo especificado.

        Cascada de pasos:
        1. Navegar al grupo + verificar rate limit
        2. Abrir compositor de posts
        3. Preparar modal (esperar + encontrar textbox)
        4. Subir imagen
        5. Componer y pegar mensaje
        6. Restaurar saltos de línea
        7. Clic en Publicar
        8. Esperar confirmación
        9. Notificar a Telegram
        """
        print(f"\n--- INICIANDO PUBLICACIÓN EN GRUPO: {group_url} ---")
        log_dir = self._get_log_dir()

        try:
            # [1] Navegar al grupo
            await self._navigate_to_group(page, group_url)
            await self._check_rate_limit_upfront(page)

            # [2] Abrir compositor
            await self._open_post_composer(page, log_dir)
            await self._wait_modal_open(page)

            # [3] Preparar modal
            textbox = await self._find_modal_textbox(page, log_dir)

            # [4] Subir imagen
            await self._upload_product_image(page, product_details)

            # [5] Componer mensaje
            clean_lines, message_oneline = self._build_message_text(product_details, affiliate_link, group_url)

            # [6] Pegar texto
            pasted = await self._paste_text_to_textbox(page, textbox, message_oneline)
            if pasted:
                await self._restore_line_breaks(page, clean_lines)

            # [7] Clic en Publicar
            await self._click_post_button(page)

            # [8] Esperar confirmación
            publish_confirmed = await self._wait_post_confirmation(page)

            # Verificar rate limit después de clic
            try:
                await self._check_post_click_rate_limit(page)
            except FacebookLimitedException:
                raise

            # [9] Capturar evidencia
            evidence_path = await self._capture_evidence(page, log_dir)
            await page.wait_for_timeout(4000)

            # [10] Notificar a Telegram
            group_name_clean = self._extract_group_name(group_url)
            if publish_confirmed:
                await self._notify_telegram_success(product_details, group_url, group_name_clean)
            else:
                print("⚠️ Aviso: No se pudo confirmar publicación automáticamente. Se asume éxito (la publicación pudo completarse).")
                await self._notify_telegram_unconfirmed(product_details, group_url, group_name_clean, evidence_path)

        except FacebookLimitedException as fle:
            await self._notify_telegram_rate_limit(log_dir)
            raise fle

        except Exception as e:
            print(f"Error al redactar o publicar: {e}")
            group_name_clean = self._extract_group_name(group_url)
            await self._notify_telegram_error(group_url, group_name_clean, str(e), log_dir)
            return False

        return True

