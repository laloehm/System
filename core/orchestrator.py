import os
import asyncio
import random
import datetime
import time
import re
from typing import Optional
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from core.storage import json_load, json_save_atomic

from core.config import Config
from core.session_manager import SessionManager
from core.publisher_factory import PublisherFactory
from core.storage_manager import StorageManager
from core.publication_constants import PublicationConstants
from core.product_types import ProductDetails, EnrichedProductDetails
from scrapers.amazon_scraper import AmazonScraper
from scrapers.ml_scraper import scrape_ml_product_headless
from publishers.facebook_publisher import FacebookLimitedException
from tiktok_generator import create_tiktok_video
from affiliate_linker import run_linkbuilder



class Orchestrator:
    def __init__(self, headless=True, dry_run=False, publishers=None, telegram_bot=None, storage=None):
        """
        Inicializa el orquestador con dependencias inyectadas.

        Args:
            headless: Si True, ejecuta Playwright en modo headless
            dry_run: Si True, simula publicaciones sin realmente publicar
            publishers: Dict de {nombre: Publisher}. Si None, usa PublisherFactory.create_default_publishers()
            telegram_bot: Instancia del TelegramBot para notificaciones
            storage: Instancia de StorageManager. Si None, crea una nueva
        """
        self.headless = headless
        self.dry_run = dry_run
        self.amazon_scraper = AmazonScraper()
        self.telegram_bot = telegram_bot
        self.storage = storage or StorageManager()

        # Inyección de dependencias de publishers
        if publishers is None:
            self.publishers = PublisherFactory.create_default_publishers(telegram_bot)
        else:
            self.publishers = publishers

        # Mantener referencias directas para compatibilidad con código existente
        self.facebook_publisher = self.publishers.get("facebook")
        self.facebook_api_publisher = self.publishers.get("facebook_page")
        self.pinterest_publisher = self.publishers.get("pinterest")
        self.telegram_publisher = self.publishers.get("telegram")
        self.web_publisher = self.publishers.get("web")
        self.tiktok_publisher = self.publishers.get("tiktok")
        self.youtube_publisher = self.publishers.get("youtube")
        self.twitter_publisher = self.publishers.get("twitter")

        self._publish_lock = asyncio.Lock()
        self._lock_acquired_time = None

    async def _publish_fb_queue_items(
        self,
        context,
        queue_items,
        max_retries=None,
        label="RETRY",
    ):
        """
        Lógica común para reintentar publicaciones en Facebook.
        Cubre tanto reintentos automáticos como manuales.

        Args:
            context: Contexto de Playwright (reutilizado)
            queue_items: Lista de {group_url, details, affiliate_url, retries (opcional)}
            max_retries: Máximo de intentos antes de descartar (default: PublicationConstants.FB_MAX_RETRIES)
            label: Prefijo para logs (ej: "FB RETRY AUTO", "FB RETRY MANUAL")
        """
        if max_retries is None:
            max_retries = PublicationConstants.FB_MAX_RETRIES

        still_pending = []
        success_count = 0
        discarded_count = 0

        for item in queue_items:
            retries = item.get("retries", 0)
            if retries >= max_retries:
                discarded_count += 1
                print(f"[{label}] Descartando {item.get('group_url', '')} tras {retries} intentos")
                continue

            group_url = item.get("group_url", "")
            details = item.get("details", {})
            aff_url = item.get("affiliate_url", "")

            page = await context.new_page()
            try:
                result = await asyncio.wait_for(
                    self.facebook_publisher.publish(details, aff_url, page=page, group_url=group_url),
                    timeout=PublicationConstants.FB_PUBLISH_TIMEOUT_S,
                )
                if result.success:
                    success_count += 1
                    print(f"[{label}] ✅ Éxito en {group_url}")
                else:
                    item["retries"] = retries + 1
                    still_pending.append(item)
            except asyncio.TimeoutError:
                print(f"[{label}] ❌ Error en {group_url}: Timeout ({PublicationConstants.FB_PUBLISH_TIMEOUT_S}s)")
                item["retries"] = retries + 1
                still_pending.append(item)
            except FacebookLimitedException as e:
                print(f"[{label}] 🔴 RATE LIMIT FB: {e}")
                # AUTO-PAUSAR FACEBOOK
                asyncio.create_task(self._handle_facebook_rate_limit(
                    notify=lambda msg, **kw: self.telegram_bot.send_notification(msg) if self.telegram_bot else None
                ))
                # No reintentar este slot, esperar a que se reanude
                break
            except Exception as e:
                print(f"[{label}] ❌ Error en {group_url}: {e}")
                item["retries"] = retries + 1
                still_pending.append(item)
            finally:
                await page.close()

            delay_min, delay_max = PublicationConstants.FACEBOOK_RETRY_DELAY_RANGE
            await asyncio.sleep(random.randint(delay_min, delay_max))

        return {"success": success_count, "pending": still_pending, "discarded": discarded_count}

    async def _fetch_product_details(
        self,
        url: str,
        browser,
        pre_scraped_details: Optional[dict] = None,
        stealth=None,
    ) -> Optional[ProductDetails]:
        """
        Obtiene detalles del producto desde scrape en vivo o datos precargados.

        Args:
            url: URL del producto
            browser: Instancia de Playwright browser
            pre_scraped_details: Datos precargados (opcional, evita scrape)
            stealth: Instancia de Stealth para anti-detección

        Returns:
            ProductDetails si fue exitoso, None si falla
        """
        is_ml = "mercadolibre.com.mx" in url or "meli.la" in url

        def safe_price_parse(price_val):
            if price_val is None or price_val == "":
                return 0.0
            if isinstance(price_val, (int, float)):
                return float(price_val)
            try:
                clean = str(price_val).replace("$", "").replace(",", "").replace("N/A", "").strip()
                return float(clean) if clean else 0.0
            except (ValueError, AttributeError):
                print(f"⚠️ No se pudo parsear precio '{price_val}', usando 0.0")
                return 0.0

        try:
            if is_ml:
                print(f"📦 Scrapeando Mercado Libre: {url}")

                # Usar datos precargados si están disponibles
                if pre_scraped_details and pre_scraped_details.get("skip_scrape"):
                    print("📦 Omitiendo scrape, usando datos precargados")
                    details = pre_scraped_details
                else:
                    # Crear contexto anónimo para evitar que ML detecte el bot
                    anon_context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                    )
                    if stealth:
                        await stealth.apply_stealth_async(anon_context)

                    temp_page = await anon_context.new_page()
                    details = await scrape_ml_product_headless(temp_page, url)
                    await anon_context.close()

                    if not details:
                        print("⚠️ Scrape de ML devolvió None, usando fallback")
                        details = {}
                    print(f"🔍 Detalles extraídos: {details.get('title', 'N/A')}")

                    # GUARDA DE INTEGRIDAD DE DATOS: Evitar productos Frankenstein (Título A + Imagen B)
                    if pre_scraped_details and pre_scraped_details.get("title"):
                        pre_title = pre_scraped_details.get("title", "")
                        live_title = details.get("title", "")
                        
                        sim = 1.0
                        if live_title and pre_title:
                            try:
                                from product_confidence import title_similarity
                                sim = title_similarity(pre_title, live_title)
                            except Exception:
                                sim = 1.0

                        is_social = details.get("is_social_redirect", False)
                        
                        if sim < 0.35 or is_social:
                            print(f"⚠️ [INTEGRIDAD DE DATOS] Scrape en vivo ({live_title[:35]}...) no coincide con el producto en cola ({pre_title[:35]}..., similitud {sim:.0%}, social={is_social}). Preservando TÍTULO E IMAGEN de la cola.")
                            details["title"] = pre_title
                            if pre_scraped_details.get("image_url"):
                                details["image_url"] = pre_scraped_details["image_url"]
                            if pre_scraped_details.get("screenshot"):
                                details["screenshot"] = pre_scraped_details["screenshot"]
                            if pre_scraped_details.get("visual_capture"):
                                details["visual_capture"] = pre_scraped_details["visual_capture"]

                # Validar que los datos no sean corruptos
                if not details or details.get("title") == "Oferta Especial en Mercado Libre":
                    print("⚠️ Scrape falló, regenerando capture...")
                    prod_id = details.get("id", "")
                    if prod_id:
                        stale_cap = os.path.join(Config.CAPTURES_DIR, f"{prod_id}.png")
                        if os.path.exists(stale_cap):
                            os.remove(stale_cap)
                    return None

                # Determinar el precio final
                final_price = details.get("price")
                if final_price is None or final_price == 0 or final_price == 0.0:
                    final_price = safe_price_parse(details.get("offer_price"))
                else:
                    final_price = safe_price_parse(final_price)

                final_original = details.get("original_price")
                if final_original is None:
                    final_original = safe_price_parse(details.get("list_price"))
                    if final_original == 0.0:
                        final_original = None
                else:
                    final_original = safe_price_parse(final_original)
                    if final_original == 0.0:
                        final_original = None

                return ProductDetails(
                    id=details.get("id", ""),
                    title=details.get("title", ""),
                    price=final_price,
                    original_price=final_original,
                    discount=details.get("discount", ""),
                    image_url=details.get("image_url"),
                    affiliate_url=details.get("affiliate_url"),
                    url=url,
                    niche=pre_scraped_details.get("niche", "[CAT:GENERAL]") if pre_scraped_details else "[CAT:GENERAL]",
                    is_redirected_to_lists=details.get("is_redirected_to_lists", False),
                    source="mercadolibre",
                )
            else:
                # Amazon u otro source
                print(f"📦 Scrapeando Amazon: {url}")

                details = None

                # Si hay datos precargados y skip_scrape, usarlos directamente
                if pre_scraped_details and pre_scraped_details.get("skip_scrape"):
                    print("📦 Omitiendo scrape de Amazon, usando datos pre-guardados.")
                    details = pre_scraped_details
                else:
                    # Scrape en vivo con timeout
                    try:
                        page_amz = await browser.new_page()
                        details = await asyncio.wait_for(
                            self.amazon_scraper.scrape_amazon_product(page_amz, url),
                            timeout=30.0
                        )
                        await page_amz.close()

                        if details:
                            print(f"✅ Scrape en vivo exitoso: {details.get('title', 'N/A')[:50]}")

                            # Fallback a datos precargados si falta list_price o offer_price
                            if details and pre_scraped_details:
                                if pre_scraped_details.get("list_price") and (not details.get("list_price") or details.get("list_price") in ("N/A", "$", "")):
                                    details["list_price"] = pre_scraped_details["list_price"]
                                if pre_scraped_details.get("offer_price") and (not details.get("offer_price") or details.get("offer_price") in ("N/A", "$", "")):
                                    details["offer_price"] = pre_scraped_details["offer_price"]
                                if pre_scraped_details.get("discount") and (not details.get("discount") or details.get("discount") in ("N/A", "")):
                                    details["discount"] = pre_scraped_details["discount"]
                    except asyncio.TimeoutError:
                        print(f"⚠️ Scrape en vivo tardó más de 30s, usando datos precargados")
                        details = None
                    except Exception as e:
                        print(f"⚠️ Scrape en vivo falló: {e}, usando datos precargados")
                        details = None

                # Fallback final: usar datos precargados si el scrape falló completamente
                if not details and pre_scraped_details:
                    print("📦 Usando datos precargados como fallback")
                    details = pre_scraped_details

                if not details:
                    print("❌ No hay detalles (ni scrape ni precargados)")
                    return None

                # Validar que los datos tengan lo mínimo
                if not details.get("title") or not details.get("offer_price"):
                    print(f"❌ Detalles de Amazon incompletos: {details}")
                    return None

                product = ProductDetails(
                    id=details.get("id", ""),
                    title=details.get("title", ""),
                    price=safe_price_parse(details.get("offer_price")),
                    original_price=safe_price_parse(details.get("list_price")) if details.get("list_price") and details.get("list_price") not in ("N/A", "$", "") else None,
                    discount=details.get("discount", ""),
                    image_url=details.get("image_url"),
                    affiliate_url=details.get("affiliate_url", url),
                    url=url,
                    niche=pre_scraped_details.get("niche", "[CAT:GENERAL]") if pre_scraped_details else "[CAT:GENERAL]",
                    is_redirected_to_lists=False,
                    source="amazon",
                )
                # Guardar visual_capture del scraper si existe
                if details.get("visual_capture"):
                    product._visual_capture = details.get("visual_capture")

                return product

        except Exception as e:
            print(f"❌ Error obteniendo detalles: {e}")
            return None

    async def _validate_product_for_publication(
        self, details: ProductDetails, context=None
    ) -> tuple[bool, str]:
        """
        Valida que el producto sea adecuado para publicar.

        Args:
            details: Detalles del producto
            context: Contexto de Playwright (opcional, para validaciones complejas)

        Returns:
            (is_valid: bool, reason_if_invalid: str)
            Si es válido: (True, "")
            Si no es válido: (False, "Razón por la que se rechaza")
        """

        prod_title = (details.title or details.id or "Sin título").strip()[:80]
        prod_url = details.affiliate_url or details.url or ""
        url_snippet = f"\n🔗 {prod_url}" if prod_url else ""

        # 1.1 VERIFICAR REDIRECCIÓN A LISTA GENERAL
        if details.is_redirected_to_lists:
            reason = (
                f"⚠️ **PRODUCTO OMITIDO (PAUSADO/FUERA DE STOCK)**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"El enlace redirige automáticamente a lista general.{url_snippet}"
            )
            await self._register_in_history(details.url, details.to_dict())
            return False, reason

        # 1.2 VERIFICAR SI ESTÁ EN HISTORIAL RECIENTE DE PUBLICADOS (TTL de 21 días)
        allow_duplicates = False
        if self.telegram_bot:
            allow_duplicates = self.telegram_bot.user_state.get("allow_duplicate_products", False)
        if not allow_duplicates:
            from core.history_manager import load_recent_history, get_history_ttl_days
            recent_history = load_recent_history()
            ttl_days = get_history_ttl_days()
            if (
                (details.affiliate_url and details.affiliate_url in recent_history)
                or (details.url and details.url in recent_history)
                or (details.id and details.id in recent_history)
            ):
                reason = (
                    f"⚠️ **PRODUCTO YA PUBLICADO RECIENTEMENTE**\n"
                    f"📦 **Producto:** {prod_title}\n"
                    f"Este producto ya fue publicado en los últimos {ttl_days} días.{url_snippet}"
                )
                return False, reason

        # 1.3 VERIFICAR BLACKLIST (Config.BLACKLIST_WORDS + excluded_keywords de scraping_config.json)
        blacklist_words = list(Config.BLACKLIST_WORDS)
        dynamic_excluded = Config.SCRAPING_CONFIG.get("excluded_keywords", [])
        if dynamic_excluded:
            blacklist_words.extend([str(w).strip().lower() for w in dynamic_excluded if str(w).strip()])

        product_title_lower = (details.title or "").lower()
        matched_excluded = next((word for word in blacklist_words if word in product_title_lower), None)
        if product_title_lower and matched_excluded:
            reason = (
                f"⚠️ **PRODUCTO EN BLACKLIST**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"Término excluido detectado: '{matched_excluded}'.{url_snippet}"
            )
            return False, reason

        # 1.4 VALIDACIONES DE PRECIO
        if not details.price or details.price <= 0 or (details.original_price and details.original_price <= 0):
            reason = (
                f"⚠️ **PRECIO INVÁLIDO**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"El producto tiene precio cero o negativo ($ {details.price}).{url_snippet}"
            )
            return False, reason

        if details.price < PublicationConstants.MIN_PRODUCT_PRICE:
            reason = (
                f"⚠️ **PRECIO BAJO**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"El producto cuesta ${details.price:.0f} (mínimo requerido: ${PublicationConstants.MIN_PRODUCT_PRICE}).{url_snippet}"
            )
            return False, reason

        # Validar precio máximo
        max_price = Config.SCRAPING_CONFIG.get("max_price", 10000.0)
        if details.price > max_price:
            reason = (
                f"⚠️ **PRECIO DEMASIADO ALTO**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"El producto cuesta ${details.price:.0f} (máximo configurado: ${max_price:.0f}).{url_snippet}"
            )
            return False, reason

        # 1.5 VALIDACIONES DE DESCUENTO (Basado estrictamente en el Ahorro en Pesos configurado en el Panel Web)
        if not details.original_price:
            reason = (
                f"⚠️ **PRODUCTO SIN DESCUENTO ACTIVO**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"El producto no tiene precio original con descuento o la oferta ya caducó (Precio actual: ${details.price:.2f}).{url_snippet}"
            )
            return False, reason

        if details.original_price <= details.price:
            reason = (
                f"⚠️ **PRECIOS INCOHERENTES (OFERTA >= ORIGINAL)**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"Precio oferta: ${details.price:.2f} >= Precio original: ${details.original_price:.2f}.{url_snippet}"
            )
            return False, reason

        savings_pesos = details.original_price - details.price
        min_savings = Config.SCRAPING_CONFIG.get("min_strict_savings", 100)
        if savings_pesos < min_savings:
            reason = (
                f"⚠️ **DESCUENTO INSUFICIENTE**\n"
                f"📦 **Producto:** {prod_title}\n"
                f"💰 Ahorro: ${savings_pesos:.0f} (mínimo configurado en panel: ${min_savings})\n"
                f"💵 Precio: ${details.price:.0f} (Antes: ${details.original_price:.0f})"
                f"{url_snippet}"
            )
            return False, reason

        # Si todas las validaciones pasaron
        return True, ""

    async def _prepare_product_for_publication(
        self, details: ProductDetails, context=None, manual_image: Optional[str] = None
    ) -> EnrichedProductDetails:
        """
        Prepara el producto para publicación: affiliate link, imagen, título limpio.

        Args:
            details: ProductDetails básicos
            context: Contexto de Playwright (para rescatar affiliate link si es necesario)
            manual_image: Ruta manual de imagen (override)

        Returns:
            EnrichedProductDetails listo para publicar
        """
        enriched = EnrichedProductDetails.from_details(details)

        # 1. VERIFICAR/RESCATAR AFFILIATE LINK
        if not enriched.affiliate_url or "meli.la" not in enriched.affiliate_url:
            print("🔗 Generando link de afiliado automáticamente...")
            if enriched.affiliate_url and "mercadolibre" in enriched.affiliate_url:
                try:
                    # Convertir URL cruda a meli.la usando linkbuilder
                    mapping = await run_linkbuilder([enriched.affiliate_url], headless=True)
                    if mapping and enriched.affiliate_url in mapping:
                        new_link = mapping[enriched.affiliate_url]
                        if new_link and "meli.la" in new_link:
                            enriched.affiliate_url = new_link
                            enriched.aff_link_verified = True
                            print(f"✅ Link de afiliado generado: {new_link[:50]}...")
                        else:
                            print(f"⚠️ Linkbuilder retornó URL inválida, usando original")
                            enriched.aff_link_verified = bool(enriched.affiliate_url)
                    else:
                        print(f"⚠️ No se pudo generar link de afiliado, usando original")
                        enriched.aff_link_verified = bool(enriched.affiliate_url)
                except Exception as e:
                    print(f"⚠️ Error en linkbuilder: {e}, usando URL original")
                    enriched.aff_link_verified = bool(enriched.affiliate_url)
            else:
                print(f"⚠️ URL no es de Mercado Libre, usando original")
                enriched.aff_link_verified = bool(enriched.affiliate_url)
        else:
            enriched.aff_link_verified = True
            print(f"✅ Link de afiliado ya disponible: {enriched.affiliate_url[:50]}...")

        # 2. LIMPIAR TÍTULO CON GEMINI (si está disponible)
        try:
            from core.config import Config
            from core.ai_service import generate_with_gemini_rotation

            if Config.get_gemini_keys() and enriched.title:
                prompt = (
                    f"Eres un experto copywriter de e-commerce en México. Tu ÚNICA tarea es generar un título conciso, profesional y atractivo para este producto en oferta (máximo 75 caracteres).\n\n"
                    f"Título original: {enriched.title}\n\n"
                    f"REGLAS ESTRICTAS:\n"
                    f"1. Conserva la identidad REAL del producto (ej: si es una mochila para laptop, es una Mochila, NO una laptop; si es un soporte para monitor, es un Soporte, NO un monitor; si es un escritorio, es un Escritorio).\n"
                    f"2. Conserva marca, modelo y características esenciales, eliminando el spam de palabras clave SEO secundarias.\n"
                    f"3. NUNCA inventes palabras ni alteres lo que es el producto.\n"
                    f"4. Máximo 75 caracteres. Devuelve ÚNICAMENTE el título final limpio, sin comillas, sin introducciones ni saludos."
                )
                response = generate_with_gemini_rotation(prompt)
                if response and response.text:
                    raw_res = response.text.strip()
                    # Si Gemini responde con varias líneas, tomar la primera no vacía que no sea saludo
                    lines = [l.strip().strip('"').strip("'") for l in raw_res.splitlines() if l.strip()]
                    clean_lines = [l for l in lines if not any(l.lower().startswith(w) for w in ["aquí tienes", "¡claro", "opciones", "hola", "a continuación"])]
                    enriched.clean_title = (clean_lines[0] if clean_lines else (lines[0] if lines else enriched.title))[:75]
                else:
                    from core.message_builder import _clean_title
                    enriched.clean_title = _clean_title(enriched.title)
                print(f"✨ Título limpio: {enriched.clean_title}")
            else:
                from core.message_builder import _clean_title
                enriched.clean_title = _clean_title(enriched.title or "")
        except Exception as e:
            print(f"⚠️ Error limpiando título con Gemini: {e}")
            from core.message_builder import _clean_title
            enriched.clean_title = _clean_title(enriched.title or "")

        # 3. GENERAR GUION DE 6 LÍNEAS (P+B+CTA) AUTOMÁTICAMENTE (Solo si redes de video están ON)
        try:
            from core.config import Config
            from core.ai_service import generate_with_gemini_rotation

            user_state = self.storage.load("user_state", default={})
            active_nets = user_state.get("active_networks", {})
            is_video_active = active_nets.get("tiktok", False) or active_nets.get("youtube", False)
            is_no_video_niche = (enriched.niche or "").lower() in ("[cat:bebes]", "baby", "[cat:mascotas]", "pets")

            # FILTRO ESTRICTO DE VIDEO: Ahorro >= $250 y Precio >= $300 (Protege cuota de ElevenLabs y llamadas IA)
            p_price = enriched.price or 0.0
            p_orig = enriched.original_price or 0.0
            p_savings = (p_orig - p_price) if p_orig > p_price else 0.0
            meets_video_threshold = (p_savings >= 250.0 and p_price >= 300.0)

            if Config.get_gemini_keys() and is_video_active and not is_no_video_niche and meets_video_threshold:
                title = enriched.title or "este producto"
                category = enriched.category or ""
                price_info = "Tiene un gran descuento actualmente. (NO mencionar el precio exacto)"

                is_video_ia = details.get("is_video_ia", False) if isinstance(details, dict) else getattr(details, 'is_video_ia', False)

                if is_video_ia:
                    guion_prompt = (
                        f"Eres experto en marketing de contenido viral y creación de TikToks/Shorts educativos en México.\n"
                        f"Genera un guion de 6 líneas dando un CONSEJO o TRUCO ÚTIL sobre el nicho del producto, terminando con la recomendación del producto.\n"
                        f"También genera 3 PROMPTS distintos en inglés para una IA de imágenes.\n\n"
                        f"Datos:\n"
                        f"- Producto: {title}\n"
                        f"{'- Categoría: ' + category if category else ''}\n\n"
                        f"ESTRUCTURA EXACTA DE 9 LÍNEAS:\n"
                        f"L1-2 (GANCHO IMPACTANTE): Un dato curioso, error común o revelación que capture la atención de inmediato.\n"
                        f"L3-4 (DESARROLLO EDUCATIVO): La explicación práctica de por qué ocurre esto y cómo resolverlo.\n"
                        f"L5-6 (RECOMENDACION NATURAL): Presenta el producto como la solución ideal y menciona el link en el perfil/descripción.\n"
                        f"L7 (IMAGE PROMPT 1): Cinematic photorealistic prompt in English for scene 1 (e.g. 'Hyper-realistic lifestyle photo of... 8k, warm cinematic lighting').\n"
                        f"L8 (IMAGE PROMPT 2): Cinematic photorealistic prompt in English for scene 2.\n"
                        f"L9 (IMAGE PROMPT 3): Cinematic photorealistic prompt in English for scene 3.\n\n"
                        f"REGLAS OBLIGATORIAS:\n"
                        f"- ⛔ ESTRICTAMENTE PROHIBIDO empezar con '¿Buscas...', '¿Estás buscando...', '¿Quieres...', o fórmulas trilladas.\n"
                        f"- ✅ USA GANCHOS DINÁMICOS: 'El 90% comete este error...', 'Si tienes este problema...', 'Pocos saben este truco...', 'Esto cambió por completo cómo...', 'Cuidado si haces esto...'\n"
                        f"- TONO: Creador casual, cercano y auténtico. NADA de '¡Cómpralo ya!'.\n"
                        f"- SALIDA: EXACTAMENTE 9 líneas de texto plano. Sin prefijos, sin numeración, sin comillas ni asteriscos.\n"
                    )
                    expected_lines = 9
                else:
                    guion_prompt = (
                        f"Eres experto en marketing orgánico y creación de Shorts educativos en México.\n"
                        f"Genera un guion de 6 líneas dando un CONSEJO EDUCATIVO sobre el nicho del producto, terminando con la recomendación del producto.\n"
                        f"También genera un PROMPT en inglés para una IA de imágenes.\n\n"
                        f"Datos:\n"
                        f"- Producto: {title}\n"
                        f"{'- Categoría: ' + category if category else ''}\n\n"
                        f"ESTRUCTURA EXACTA DE 7 LÍNEAS:\n"
                        f"L1-2 (GANCHO): Un tip o dato útil sobre el cuidado relacionado al producto.\n"
                        f"L3-4 (DESARROLLO): Por qué es importante esto o cómo aplicarlo.\n"
                        f"L5-6 (RECOMENDACION): Presenta el producto sutilmente y llama a la acción.\n"
                        f"L7 (IMAGE PROMPT): Prompt descriptivo en inglés para Midjourney/Flow.\n\n"
                        f"REGLAS:\n"
                        f"- TONO: Creador casual, amigable. NADA de '¡Cómpralo ya!'.\n"
                        f"- SALIDA: EXACTAMENTE 7 líneas de texto plano. Sin prefijos, sin números.\n"
                    )
                    expected_lines = 7

                response = generate_with_gemini_rotation(guion_prompt)
                if response and response.text:
                    lines = [l.strip() for l in response.text.strip().split("\n") if l.strip()][:expected_lines]
                    if len(lines) >= 6:
                        guion = {f"escena{i+1}": line for i, line in enumerate(lines[:6])}
                        if is_video_ia and len(lines) >= 9:
                            guion["image_prompt_1"] = lines[6]
                            guion["image_prompt_2"] = lines[7]
                            guion["image_prompt_3"] = lines[8]
                        elif not is_video_ia and len(lines) >= 7:
                            guion["image_prompt"] = lines[6]
                        
                        script_path = os.path.join(Config.BASE_DIR, "guion.json")
                        json_save_atomic(script_path, guion, indent=2, ensure_ascii=False)
                        print(f"🎬 Guion educativo generado ({len(lines)} líneas de IA extraídas)")
                    else:
                        print(f"⚠️ Gemini retornó solo {len(lines)} líneas, esperaba {expected_lines}")
                else:
                    print(f"⚠️ Gemini no retornó guion")
            else:
                print("⚠️ GEMINI_API_KEY no configurada, saltando generación de guion")
        except Exception as e:
            print(f"⚠️ Error generando guion automático: {e}")

        # 4. CATEGORIZACIÓN AUTOMÁTICA CON GEMINI
        try:
            if not enriched.category or enriched.category == "general":
                category = await self._categorize_with_gemini(enriched.title, enriched.description or "")
                enriched.category = category
                print(f"🏷️ Categoría detectada: {enriched.category}")
        except Exception as e:
            print(f"⚠️ Error categorizando: {e}")

        # 5. GENERAR DESCRIPCIÓN AUTOMÁTICAMENTE
        try:
            if not enriched.description or enriched.description == "":
                description = await self._generate_description_gemini(
                    enriched.title, enriched.category or "general", f"Precio: ${enriched.price}"
                )
                if description:
                    enriched.description = description
                    print(f"📝 Descripción generada automáticamente")
        except Exception as e:
            print(f"⚠️ Error generando descripción: {e}")

        # 6. GENERAR HASHTAGS INTELIGENTES
        try:
            if not getattr(enriched, "hashtags", None):
                hashtags = await self._generate_hashtags_gemini(enriched.title, enriched.category or "general")
                if hashtags:
                    enriched.hashtags = " ".join(hashtags)
                    print(f"#️⃣ Hashtags generados: {enriched.hashtags}")
        except Exception as e:
            print(f"⚠️ Error generando hashtags: {e}")

        # 7. AUTO-CAPTURAR IMAGEN
        # Prioridad: manual_image > visual_capture del scraper > captura local existente > usar URL de imagen
        if manual_image:
            enriched.visual_capture = manual_image
            print(f"📸 Usando imagen manual: {manual_image}")
        elif enriched.visual_capture:
            # Ya tiene visual_capture del scraper en vivo, mantenerlo
            print(f"📸 Usando captura en vivo del scraper: {enriched.visual_capture}")
            if not os.path.exists(enriched.visual_capture):
                print(f"⚠️ Captura del scraper no existe: {enriched.visual_capture}")
        elif enriched.image_url and enriched.id:
            # Buscar captura local
            capture_path = os.path.join(Config.CAPTURES_DIR, f"{enriched.id}.png")
            if os.path.exists(capture_path):
                enriched.visual_capture = capture_path
                print(f"📸 Usando captura local: {capture_path}")
            else:
                print(f"📸 Sin captura local, Telegram usará URL de imagen directamente")
                enriched.visual_capture = None
        else:
            enriched.visual_capture = None

        return enriched

    async def _publish_to_all_platforms(
        self,
        enriched: EnrichedProductDetails,
        context,
        target_platform = "both",
        notify=None,
    ) -> dict:
        """
        Publica el producto en todas las plataformas configuradas.

        Args:
            enriched: EnrichedProductDetails listo para publicar
            context: Contexto de Playwright
            target_platform: str ("facebook", "pinterest", "telegram", "both") o list (["FACEBOOK", "TELEGRAM"])
            notify: Función async para notificar progreso

        Returns:
            Dict con resultados por plataforma {platform: success}
        """
        # Validaciones defensivas
        if not enriched or not context:
            print("❌ Error: enriched o context es None en _publish_to_all_platforms")
            return {}

        results = {}

        async def do_notify(msg: str, immediate: bool = False):
            """Helper para notificar."""
            if notify:
                await notify(msg, immediate=immediate)

        # Convertir a minúsculas si es lista
        if isinstance(target_platform, list):
            target_platform = [p.lower() for p in target_platform]
        else:
            target_platform = target_platform.lower()

        # Determinar plataformas activas
        targets_active = []
        if isinstance(target_platform, list):
            # Si es lista, incluir las que estén en ella
            if any(p in target_platform for p in ("facebook", "fb_page")):
                targets_active.append("facebook")
            if "pinterest" in target_platform:
                targets_active.append("pinterest")
            if "telegram" in target_platform:
                targets_active.append("telegram")
            if "web" in target_platform:
                targets_active.append("web")
            if "twitter" in target_platform:
                targets_active.append("twitter")
        else:
            # Si es string, usar la lógica original
            if target_platform in ("both", "facebook"):
                targets_active.append("facebook")
            if target_platform in ("both", "pinterest"):
                targets_active.append("pinterest")
            if target_platform in ("both", "telegram"):
                targets_active.append("telegram")
            if target_platform in ("both", "web"):
                targets_active.append("web")
            if target_platform in ("both", "twitter"):
                targets_active.append("twitter")

        # PINTEREST
        if "pinterest" in targets_active:
            if not self.dry_run:
                for attempt in range(1, 4):
                    page_pin = None
                    try:
                        page_pin = await context.new_page()
                        result = await self.pinterest_publisher.publish(
                            enriched.to_dict(),
                            enriched.affiliate_url,
                            page=page_pin,
                        )
                        if result.success:
                            results["pinterest"] = True
                            await do_notify("✅ Pinterest: Publicado")
                            break
                        else:
                            if attempt < 3:
                                await asyncio.sleep(10)
                    except Exception as e:
                        print(f"❌ Pinterest error: {e}")
                        if attempt == 3:
                            results["pinterest"] = False
                            await do_notify(f"❌ Pinterest: {str(e)[:100]}")
                    finally:
                        if page_pin:
                            await page_pin.close()
            else:
                results["pinterest"] = True

        # FACEBOOK
        if "facebook" in targets_active:
            if not self.dry_run:
                fb_groups = self._get_fb_groups_block(enriched.niche)
                fb_success = 0
                for group_url in fb_groups:
                    page_fb = None
                    try:
                        page_fb = await context.new_page()
                        result = await asyncio.wait_for(
                            self.facebook_publisher.publish(
                                enriched.to_dict(),
                                enriched.affiliate_url,
                                page=page_fb,
                                group_url=group_url,
                            ),
                            timeout=PublicationConstants.FB_PUBLISH_TIMEOUT_S,
                        )
                        if result.success:
                            fb_success += 1
                    except Exception as e:
                        print(f"❌ Facebook {group_url}: {e}")
                    finally:
                        if page_fb:
                            await page_fb.close()
                    await asyncio.sleep(random.randint(15, 30))

                results["facebook"] = fb_success > 0
                if fb_success > 0:
                    await do_notify(f"✅ Facebook: {fb_success} grupos publicados")
                else:
                    await do_notify("❌ Facebook: No se pudo publicar")
            else:
                results["facebook"] = True

        # TELEGRAM
        if "telegram" in targets_active:
            if not self.dry_run:
                result = await self.telegram_publisher.publish(
                    enriched.to_dict(),
                    enriched.affiliate_url,
                )
                results["telegram"] = result.success
                if result.success:
                    await do_notify("✅ Telegram: Publicado")
                else:
                    await do_notify(f"❌ Telegram: {result.message[:100]}")
            else:
                results["telegram"] = True

        # TWITTER / X
        user_active_nets = self.storage.load("user_state", default={}).get("active_networks", {})
        if "twitter" in targets_active or ("both" in target_platform and user_active_nets.get("twitter", False)):
            if not self.dry_run and getattr(self, "twitter_publisher", None):
                page_tw = None
                try:
                    if context:
                        page_tw = await context.new_page()
                    result = await self.twitter_publisher.publish(
                        enriched.to_dict(),
                        enriched.affiliate_url,
                        page=page_tw,
                    )
                    results["twitter"] = result.success
                    if result.success:
                        await do_notify("✅ Twitter (X): Publicado")
                    else:
                        await do_notify(f"⚠️ Twitter (X): {result.message[:100]}")
                except Exception as e:
                    print(f"❌ Twitter error: {e}")
                    results["twitter"] = False
                finally:
                    if page_tw:
                        await page_tw.close()

        # WEB
        if "web" in targets_active:
            if not self.dry_run:
                result = await self.web_publisher.publish(
                    enriched.to_dict(),
                    enriched.affiliate_url,
                )
                results["web"] = result.success
                if result.success:
                    await do_notify(f"✅ Web: {result.message}")
                else:
                    await do_notify(f"❌ Web: {result.message[:100]}")
            else:
                results["web"] = True

        return results

    async def _generate_and_publish_tiktok(self, enriched: EnrichedProductDetails):
        """
        Genera video TikTok y lo publica (background task).
        Guarda estado en tiktok_upload_state.json.
        """
        try:
            if not self.tiktok_publisher:
                print("[TikTok] ⚠️ TikTok publisher no configurado")
                return

            # FILTRO ESTRICTO DE VIDEO: Ahorro >= $250 y Precio >= $300
            p_price = enriched.price or 0.0
            p_orig = enriched.original_price or 0.0
            p_savings = (p_orig - p_price) if p_orig > p_price else 0.0
            if p_savings < 250.0 or p_price < 300.0:
                print(f"[TikTok] ⏭️ Omitiendo video para '{enriched.title[:30]}': No cumple umbral mínimo (Precio: ${p_price:.0f} >= $300, Ahorro: ${p_savings:.0f} >= $250)")
                return

            product_dict = enriched.to_dict()
            video_path = None

            # 1. Generar video
            print(f"[TikTok] 🎬 Generando video para: {enriched.title[:40]}")
            video_path = create_tiktok_video(product_dict)

            if not video_path or not os.path.exists(video_path):
                print(f"[TikTok] ❌ No se pudo generar video")
                return

            # 2. Publicar en TikTok
            print(f"[TikTok] 📤 Subiendo a TikTok: {video_path}")
            result = await self.tiktok_publisher.publish(
                details=product_dict,
                affiliate_link=enriched.affiliate_link,
                video_path=video_path
            )

            # 3. Guardar estado de upload
            tiktok_state = {
                "product_id": enriched.id,
                "product_title": enriched.title,
                "video_path": video_path,
                "timestamp": datetime.datetime.now().isoformat(),
                "success": result.success,
                "message": result.message,
                "platform_url": result.message if result.success else None
            }

            state_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_upload_state.json")
            json_save_atomic(state_file, tiktok_state, indent=2)

            if result.success:
                print(f"[TikTok] ✅ Video publicado: {result.message}")
            else:
                print(f"[TikTok] ⚠️ Error: {result.message}")

        except Exception as e:
            print(f"[TikTok] ❌ Error en generación/publicación: {e}")

    async def _categorize_with_gemini(self, title: str, description: str = "") -> str:
        """Categoriza automáticamente el producto con Gemini."""
        try:
            from core.config import Config
            from core.ai_service import generate_with_gemini_rotation
            if not Config.get_gemini_keys():
                return "general"

            prompt = (
                f"Categoriza este producto en UNA sola categoría:\n\n"
                f"Título: {title}\n"
                f"{'Descripción: ' + description if description else ''}\n\n"
                f"Categorías válidas: tech, moda, perfumería, hogar, herramientas, deportes, general\n"
                f"Responde SOLO la categoría, nada más."
            )

            response = generate_with_gemini_rotation(prompt)
            if response and response.text:
                category = response.text.strip().lower()
                valid = ["tech", "moda", "perfumería", "hogar", "herramientas", "deportes", "general"]
                return category if category in valid else "general"
        except Exception as e:
            print(f"[Gemini] Error categorizando: {e}")
        return "general"

    async def _generate_description_gemini(self, title: str, category: str, price_info: str = "") -> str:
        """Genera descripción del producto automáticamente."""
        try:
            from core.config import Config
            from core.ai_service import generate_with_gemini_rotation
            if not Config.get_gemini_keys():
                return ""

            prompt = (
                f"Genera una descripción SEO corta (2-3 líneas) para este producto:\n\n"
                f"Título: {title}\n"
                f"Categoría: {category}\n"
                f"{'Contexto de oferta: ' + price_info if price_info else ''}\n\n"
                f"Responde SOLO la descripción, sin introducción."
            )

            response = generate_with_gemini_rotation(prompt)
            if response and response.text:
                return response.text.strip()[:200]
        except Exception as e:
            print(f"[Gemini] Error generando descripción: {e}")
        return ""

    async def _generate_hashtags_gemini(self, title: str, category: str) -> list:
        """Genera hashtags inteligentes por categoría con Gemini."""
        try:
            from core.config import Config
            from core.ai_service import generate_with_gemini_rotation
            if not Config.get_gemini_keys():
                return []

            prompt = (
                f"Genera 8 hashtags virales para este producto en {category}:\n\n"
                f"Producto: {title}\n\n"
                f"Formato: #hashtag1 #hashtag2 etc. (SIN espacios entre hashtags)\n"
                f"Responde SOLO los hashtags."
            )

            response = generate_with_gemini_rotation(prompt)
            if response and response.text:
                tags = response.text.strip().split()
                return [t for t in tags if t.startswith("#")][:8]
        except Exception as e:
            print(f"[Gemini] Error generando hashtags: {e}")
        return []

    def _remove_from_queue(self, prod_id: str, url: str = None):
        """Elimina un producto descartado de todas las colas del sistema."""
        from core.storage import json_load, json_save_atomic
        queue_files = [
            os.path.join(Config.BASE_DIR, "products_list.json"),
            os.path.join(Config.BASE_DIR, "products_list_baby.json"),
            os.path.join(Config.BASE_DIR, "products_list_pets.json"),
            os.path.join(Config.BASE_DIR, "queue_tenis.json"),
            os.path.join(Config.BASE_DIR, "queue_moda.json"),
        ]
        for q_file in queue_files:
            if not os.path.exists(q_file):
                continue
            try:
                products = json_load(q_file, default=[])
                if not isinstance(products, list):
                    continue
                new_prods = [
                    p for p in products
                    if p.get("id") != prod_id and (not url or (p.get("affiliate_url") != url and p.get("url") != url))
                ]
                if len(new_prods) < len(products):
                    json_save_atomic(q_file, new_prods, indent=2, ensure_ascii=False)
                    print(f"[ORCHESTRATOR] Producto {prod_id} removido de {os.path.basename(q_file)}")
            except Exception as e:
                print(f"[ORCHESTRATOR] Error removiendo {prod_id} de {os.path.basename(q_file)}: {e}")

    def _cleanup_temp_files(self):
        """Limpia archivos temporales (imágenes/audios sin usar)."""
        import glob
        import time

        cleanup_dirs = [
            os.path.join(Config.BASE_DIR, "tiktok_videos"),
            os.path.join(Config.BASE_DIR, "captures"),
        ]

        try:
            current_time = time.time()
            cutoff_time = current_time - (7 * 24 * 3600)  # 7 días

            for dir_path in cleanup_dirs:
                if not os.path.exists(dir_path):
                    continue

                for file_path in glob.glob(os.path.join(dir_path, "*")):
                    try:
                        if os.path.isfile(file_path):
                            file_time = os.path.getmtime(file_path)
                            if file_time < cutoff_time:
                                os.remove(file_path)
                                print(f"[Cleanup] Eliminado: {os.path.basename(file_path)}")
                    except Exception as e:
                        print(f"[Cleanup] Error eliminando {file_path}: {e}")
        except Exception as e:
            print(f"[Cleanup] Error en limpieza: {e}")

    async def _handle_facebook_rate_limit(self, notify=None):
        """Pausa Facebook automáticamente cuando detecta rate limit."""
        try:
            # Pausar FB en user_state
            if self.telegram_bot:
                self.telegram_bot.user_state["facebook_paused"] = True
                self.telegram_bot.user_state["facebook_paused_at"] = datetime.datetime.now().isoformat()

                # Guardar estado
                from core.storage import json_save_atomic
                json_save_atomic(
                    os.path.join(Config.BASE_DIR, "user_state.json"),
                    self.telegram_bot.user_state,
                    indent=2
                )

                msg = (
                    "🔴 **FACEBOOK PAUSADO AUTOMÁTICAMENTE**\n"
                    "Rate limit detectado. Esperando 2 horas antes de reintentar.\n"
                    "Puedes reanudar manualmente desde el panel de Telegram."
                )
                if notify:
                    await notify(msg, immediate=True)
                print(f"[FB] Auto-pausado por rate limit")
        except Exception as e:
            print(f"[FB] Error pausando automáticamente: {e}")

    async def _send_alert(self, msg: str):
        """Envía alerta a Telegram cuando algo falla."""
        try:
            if self.telegram_bot:
                await self.telegram_bot.send_notification(msg)
        except Exception as e:
            print(f"[Alert] Error enviando alerta: {e}")



    async def _finalize_publication(
        self,
        enriched: EnrichedProductDetails,
        results: dict,
        context=None,
        notify=None,
        target_platform=None,
    ) -> bool:
        """
        Finaliza la publicación: historial, web, video, reportes.

        Args:
            enriched: EnrichedProductDetails publicado
            results: Dict de resultados por plataforma
            context: Contexto de Playwright (opcional)
            notify: Función para notificar

        Returns:
            True si la finalización fue exitosa
        """

        async def do_notify(msg: str, immediate: bool = False):
            """Helper para notificar."""
            if notify:
                await notify(msg, immediate=immediate)

        # Validación defensiva
        if not enriched or not results:
            print("❌ Error: enriched o results es None en _finalize_publication")
            return False

        try:
            # 1. REGISTRAR EN HISTORIAL
            if not enriched.url:
                print("⚠️ Advertencia: enriched.url es None en _finalize_publication")
                return False

            await self._register_in_history(enriched.url, enriched.to_dict())
            self._remove_from_queue(enriched.id, enriched.url)

            # 2. ACTUALIZAR LAST_PUBLISHED
            last_published = {
                "id": enriched.id,
                "title": enriched.title,
                "url": enriched.url,
                "timestamp": datetime.datetime.now().isoformat(),
            }
            self.storage.save("last_published", last_published)

            # 3. ACTUALIZAR WEBSITE_DB Y PUSH GITHUB
            if results.get("web", False):
                print("🌐 Website ya actualizado por web_publisher")

            # 4. GENERAR VIDEO TIKTOK (background task)
            is_tiktok_active = False
            if self.telegram_bot and getattr(self.telegram_bot, 'user_state', None):
                is_tiktok_active = self.telegram_bot.user_state.get("active_networks", {}).get("tiktok", False)
            
            if self.tiktok_publisher and is_tiktok_active:
                asyncio.create_task(self._generate_and_publish_tiktok(enriched))

            # 5. REPORTAR FINAL
            report_parts = []
            for platform, success in results.items():
                status = "✅" if success else "⏭️"
                report_parts.append(f"{status} {platform.capitalize()}")

            final_report = "📊 **PUBLICACIÓN COMPLETADA**\n" + "\n".join(report_parts)
            await do_notify(final_report, immediate=True)

            # 6. LIMPIAR ARCHIVOS TEMPORALES (background, no bloquea)
            asyncio.create_task(asyncio.to_thread(self._cleanup_temp_files))

            if target_platform and isinstance(target_platform, str) and target_platform not in ("both", "all"):
                plat_success = bool(results.get(target_platform, False))
                print(f"[FINALIZER] Éxito específico para {target_platform}: {plat_success}")
                return plat_success
            return any(results.values()) if results else False

        except Exception as e:
            print(f"❌ Error en finalización: {e}")
            await do_notify(f"❌ Error en finalización: {str(e)[:100]}")
            return False

    async def _retry_fb_failed(self, context, notify):
        """Reintenta automáticamente los grupos FB fallidos de slots anteriores. Máx 3 intentos por grupo."""
        pending = self.storage.load("fb_failed_queue")
        if not pending:
            return

        print(f"[FB RETRY AUTO] {len(pending)} grupos fallidos pendientes. Reintentando...")
        await notify(f"🔄 *Reintentando {len(pending)} grupos FB fallidos de slots anteriores...*", immediate=True)

        stats = await self._publish_fb_queue_items(context, pending, label="FB RETRY AUTO")

        # Guardar cambios usando StorageManager
        if stats["pending"]:
            self.storage.save("fb_failed_queue", stats["pending"])
        else:
            self.storage.save("fb_failed_queue", [])

        parts = []
        if stats["success"]:
            parts.append(f"✅ {stats['success']} reintentados con éxito")
        if stats["discarded"]:
            parts.append(f"🗑️ {stats['discarded']} descartados (3 intentos fallidos)")
        if stats["pending"]:
            parts.append(f"⏳ {len(stats['pending'])} pendientes para próximo slot")
        if parts:
            await notify(f"📊 *Resultado reintentos FB:* {' | '.join(parts)}", immediate=True)

    async def retry_specific_fb_posts(self, queue_items):
        """Reintenta manualmente posts específicos en Facebook."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=self.headless)
            context = await browser.new_context()

            stats = await self._publish_fb_queue_items(context, queue_items, max_retries=999, label="FB RETRY MANUAL")

            await context.close()
            await browser.close()

            if stats["success"] > 0:
                msg = f"✅ {stats['success']} publicaciones manuales reintentadas con éxito en FB."
                if self.telegram_bot:
                    await self.telegram_bot.send_notification(msg)
                else:
                    print(msg)


    async def run_publication(
        self,
        url: str,
        target_platform: str = "both",
        manual_image: Optional[str] = None,
        pre_scraped_details: Optional[dict] = None,
        affiliate_override: Optional[str] = None,
        video_mode: str = "normal",
        comparison_url: Optional[str] = None,
    ) -> bool:
        """
        Orquestador refactorizado de publicación de productos.

        Flujo:
        1. Validar lock
        2. Setup browser + context + stealth
        3. Verificar sesión FB
        4. Reintentar grupos FB fallidos
        5. Obtener detalles del producto
        6. Validar producto
        7. Preparar para publicación
        8. Publicar en plataformas
        9. Finalizar (historial, web, video)

        Cada paso es independiente y puede ser testeado.
        """

        # ─────────────────────────────────────────────────────────────────
        # PASO 0: VALIDAR LOCK (con barredora automática de locks huérfanos >10 min)
        # ─────────────────────────────────────────────────────────────────
        if self._publish_lock.locked():
            now = time.time()
            lock_duration = (now - self._lock_acquired_time) if getattr(self, '_lock_acquired_time', None) else 0
            if lock_duration > 600:
                print(f"[ORCHESTRATOR] ⚠️ Lock de publicación trabado por {lock_duration:.1f}s (>600s). Forzando liberación de emergencia...")
                self._publish_lock = asyncio.Lock()
                self._lock_acquired_time = None
                if self.telegram_bot:
                    asyncio.create_task(self.telegram_bot.send_notification(
                        "🛡️ *Auto-Recuperación:* El bloqueo de publicación llevaba más de 10 min atascado y fue liberado automáticamente."
                    ))
            else:
                if self.telegram_bot:
                    await self.telegram_bot.send_notification(
                        "⚠️ Ya hay una publicación en curso. Petición ignorada para evitar duplicados."
                    )
                return False

        async with self._publish_lock:
            self._lock_acquired_time = time.time()
            # ─────────────────────────────────────────────────────────────
            # SETUP: Browser, context, stealth, notify helper
            # ─────────────────────────────────────────────────────────────
            report_lines = []

            async def notify(msg: str, immediate: bool = False):
                """Acumula mensajes para reporte final o envía inmediatamente."""
                print(f"[NOTIFY] {msg}")
                if not self.telegram_bot:
                    return
                if immediate:
                    await self.telegram_bot.send_notification(msg)
                else:
                    report_lines.append(msg)

            # Asegurar vinculación del bot de Telegram a los publishers
            self.facebook_publisher.telegram_bot = self.telegram_bot
            self.pinterest_publisher.telegram_bot = self.telegram_bot

            from playwright.async_api import async_playwright
            from playwright_stealth import Stealth

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--no-sandbox",
                        "--disable-translate",
                        "--disable-features=Translate",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                context = await browser.new_context(
                    storage_state=SessionManager.get_storage_state(),
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                )

                stealth = Stealth()
                await stealth.apply_stealth_async(context)

                try:
                    # ─────────────────────────────────────────────────────
                    # VERIFICAR SESIÓN FB
                    # ─────────────────────────────────────────────────────
                    page_check = None
                    try:
                        page_check = await context.new_page()
                        await page_check.route(
                            "**/*.{png,jpg,jpeg,gif,webp,woff,woff2,ttf,css}",
                            lambda route: route.abort(),
                        )

                        print("🔍 Verificando sesión (Carga rápida)...")
                        await page_check.goto(
                            "https://www.facebook.com", wait_until="load", timeout=30000
                        )
                        if "login" in page_check.url or await page_check.query_selector(
                            "input[name='email']"
                        ):
                            msg = "⚠️ **ADVERTENCIA: Sesión Expirada.**\nEjecuta `python3 amazon_deal_bot.py --login`"
                            if self.telegram_bot:
                                await self.telegram_bot.send_notification(msg)
                    except Exception as e:
                        print(f"⚠️ Aviso: Timeout al verificar Facebook. {e}")
                    finally:
                        if page_check is not None:
                            try:
                                await page_check.close()
                            except Exception as close_err:
                                print(f"⚠️ Error al cerrar page_check: {close_err}")

                    # ─────────────────────────────────────────────────────
                    # REINTENTAR GRUPOS FB FALLIDOS
                    # ─────────────────────────────────────────────────────
                    await self._retry_fb_failed(context, notify)

                    # ─────────────────────────────────────────────────────
                    # PASO 1: OBTENER DETALLES
                    # ─────────────────────────────────────────────────────
                    niche_header = (
                        pre_scraped_details.get("niche", "[CAT:GENERAL]")
                        if pre_scraped_details
                        else "[CAT:MANUAL]"
                    )
                    prod_title_hint = (pre_scraped_details.get("title") or "") if pre_scraped_details else ""
                    hint_line = f"\n📦 {prod_title_hint[:70]}" if prod_title_hint else ""
                    await notify(f"🚀 **INICIANDO PUBLICACIÓN: {niche_header}**{hint_line}", immediate=True)

                    details = await self._fetch_product_details(
                        url,
                        browser,
                        pre_scraped_details=pre_scraped_details,
                        stealth=stealth,
                    )
                    if not details:
                        fallback_name = prod_title_hint or "Sin título"
                        await notify(
                            f"❌ **No se pudieron obtener detalles del producto**\n📦 **Producto:** {fallback_name[:70]}\n🔗 {url}",
                            immediate=True,
                        )
                        return False

                    # ─────────────────────────────────────────────────────
                    # PASO 2: VALIDAR PRODUCTO
                    # ─────────────────────────────────────────────────────
                    is_valid, reason = await self._validate_product_for_publication(
                        details, context=context
                    )
                    if not is_valid:
                        await notify(reason, immediate=True)
                        try:
                            prod_id = details.id or (pre_scraped_details.get("id") if pre_scraped_details else "")
                            if prod_id:
                                from core.discard_manager import register_discard
                                register_discard(prod_id, reason, details.to_dict())
                                self._remove_from_queue(prod_id, details.url)
                                print(f"[ORCHESTRATOR] Producto {prod_id} descartado y removido de la cola por: {reason[:60]}")
                        except Exception as discard_err:
                            print(f"[ORCHESTRATOR] Error guardando producto descartado: {discard_err}")
                        return False

                    # ─────────────────────────────────────────────────────
                    # PASO 3: PREPARAR PRODUCTO
                    # ─────────────────────────────────────────────────────
                    enriched = await self._prepare_product_for_publication(
                        details, context=context, manual_image=manual_image
                    )
                    await notify(f"✨ Listo: {enriched.clean_title}")

                    # ─────────────────────────────────────────────────────
                    # PASO 4: PUBLICAR EN TODAS LAS PLATAFORMAS
                    # ─────────────────────────────────────────────────────
                    results = await self._publish_to_all_platforms(
                        enriched,
                        context,
                        target_platform=target_platform,
                        notify=notify,
                    )

                    # ─────────────────────────────────────────────────────
                    # PASO 5: FINALIZAR PUBLICACIÓN
                    # ─────────────────────────────────────────────────────
                    success = await self._finalize_publication(
                        enriched,
                        results,
                        context=context,
                        notify=notify,
                        target_platform=target_platform,
                    )

                    # ─────────────────────────────────────────────────────
                    # ENVIAR REPORTE FINAL
                    # ─────────────────────────────────────────────────────
                    if report_lines and self.telegram_bot:
                        report = "\n".join(report_lines)
                        await self.telegram_bot.send_notification(f"📋\n{report}")

                    return success

                except Exception as e:
                    print(f"❌ Error inesperado en publicación: {e}")
                    import traceback

                    traceback.print_exc()
                    await notify(f"❌ Error inesperado: {str(e)[:100]}", immediate=True)
                    return False

                finally:
                    self._lock_acquired_time = None
                    try:
                        await context.close()
                    except:
                        pass
                    try:
                        await browser.close()
                    except:
                        pass

    def _get_fb_groups_block(self, niche_tag="[CAT:GENERAL]"):
        """Devuelve los grupos de FB correspondientes al nicho de forma exclusiva."""
        if niche_tag == "[CAT:BEBES]" or niche_tag == "baby":
            groups = list(getattr(Config, "FB_GROUPS_BABY", []))
            blocks = self.telegram_bot.user_state.get("fb_bebes_split_blocks", 1) if self.telegram_bot else 1
            index_key = "fb_bebes_block_index"
        elif niche_tag == "[CAT:MASCOTAS]" or niche_tag == "pets":
            groups = list(getattr(Config, "FB_GROUPS_PETS", []))
            blocks = self.telegram_bot.user_state.get("fb_pets_split_blocks", 1) if self.telegram_bot else 1
            index_key = "fb_pets_block_index"
        elif niche_tag == "[CAT:TENIS]" or niche_tag == "tenis":
            groups = list(getattr(Config, "FB_GROUPS_TENIS", []))
            blocks = self.telegram_bot.user_state.get("fb_tenis_split_blocks", 1) if self.telegram_bot else 1
            index_key = "fb_tenis_block_index"
        elif niche_tag == "[CAT:MODA]" or niche_tag == "moda":
            groups = list(getattr(Config, "FB_GROUPS_MODA", []))
            blocks = self.telegram_bot.user_state.get("fb_moda_split_blocks", 1) if self.telegram_bot else 1
            index_key = "fb_moda_block_index"
        else:
            groups = list(Config.FB_GROUPS)
            blocks = self.telegram_bot.user_state.get("fb_split_blocks", 1) if self.telegram_bot else 1
            index_key = "fb_gen_block_index"
            
        groups = list(dict.fromkeys(groups)) # Eliminar duplicados
        
        target = "https://www.facebook.com/groups/388464343440887"
        if target in groups:
            groups.remove(target)
            groups.append(target)

        # Lógica de rotación de bloques (distribución equitativa)
        if blocks > 1 and len(groups) > blocks and self.telegram_bot:
            current_index = self.telegram_bot.user_state.get(index_key) or 0

            if not isinstance(current_index, int) or current_index >= blocks:
                current_index = 0

            # Distribución equitativa: algunos bloques +1 si hay residuo
            base_size = len(groups) // blocks
            remainder = len(groups) % blocks

            # Calcular start/end para este bloque
            if current_index < remainder:
                # Los primeros 'remainder' bloques reciben base_size + 1
                start = current_index * (base_size + 1)
                end = start + (base_size + 1)
            else:
                # El resto reciben solo base_size
                start = remainder * (base_size + 1) + (current_index - remainder) * base_size
                end = start + base_size

            groups_chunk = groups[start:end]

            # Avanzar el contador para la próxima vez
            self.telegram_bot.user_state[index_key] = current_index + 1 if (current_index + 1) < blocks else 0
            self.telegram_bot._save_user_state()

            return groups_chunk

        return groups
        # rotation_file = os.path.join(Config.BASE_DIR, "fb_rotation.json")
        # block_idx = 0
        # try:
        #     rotation_data = json_load(rotation_file, default={})
        #     if isinstance(rotation_data, dict):
        #         block_idx = rotation_data.get("block", 0) % 3
        # except Exception:
        #     block_idx = 0
        #
        # block_size = (n + 2) // 3  # ceil(n/3)
        # start = block_idx * block_size
        # selected = groups[start:min(start + block_size, n)]
        #
        # try:
        #     json_save_atomic(rotation_file, {"block": (block_idx + 1) % 3}, indent=2)
        # except Exception:
        #     pass
        #
        # return selected

    async def _register_in_history(self, url, details):
        """Registra el producto en published_history.json con timestamp mediante history_manager."""
        from core.history_manager import register_in_history
        try:
            register_in_history(url, details or {})
        except Exception as e:
            print(f"Error escribiendo en el historial: {e}")


    async def scrape_product_details(self, url):
        """Scrapea en vivo un producto de Amazon o Mercado Libre y devuelve sus detalles."""
        is_ml = "mercadolibre.com.mx" in url or "meli.la" in url
        details = {}
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-gpu', '--no-sandbox', '--disable-setuid-sandbox']
            )
            
            ua = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" if is_ml else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=ua
            )
            stealth = Stealth()
            await stealth.apply_stealth_async(context)
            page = await context.new_page()
            
            try:
                if is_ml:
                    details = await scrape_ml_product_headless(page, url)
                else:
                    details = await self.amazon_scraper.scrape_amazon_product(page, url)
            except Exception as e:
                print(f"[SCRAPE_LIVE] Error scrapeando {url}: {e}")
            finally:
                await context.close()
                await browser.close()
                
        return details
