import os
import re
import random
import asyncio

class AmazonScraper:
    def __init__(self):
        self.amazon_url = "https://www.amazon.com.mx"

    async def scrape_amazon_product(self, page, product_url):
        """Extrae detalles del producto de Amazon.com.mx"""
        print(f"Scrapeando Amazon: {product_url}")
        
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "es-MX,es;q=0.9,en;q=0.8"
        })
        
        await page.goto(product_url, wait_until="commit", timeout=60000)
        
        try:
            await page.wait_for_selector("#productTitle", timeout=10000)
        except Exception:
            print("Tiempo de espera agotado esperando #productTitle. Tomando captura de pantalla...")
            
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
            os.makedirs(log_dir, exist_ok=True)
            await page.screenshot(path=os.path.join(log_dir, "amazon_error.png"))
            
            if "sorry" in (await page.title()).lower() or await page.query_selector("form[action='/errors/validateCaptcha']"):
                print("¡CAPTCHA detectado!")
            return {"title": "Desconocido (¿Bloqueado?)", "offer_price": "N/A", "list_price": "N/A", "discount": "0%", "image_url": None}

        offer_price_str = await page.evaluate('''() => {
            let selectors = ['.priceToPay .a-offscreen', '.apexPriceToPay .a-offscreen', '#corePrice_feature_div .a-offscreen', '.a-price:not(.a-text-price) span.a-offscreen'];
            for(let sel of selectors) {
                let el = document.querySelector(sel);
                if (el && el.innerText.trim().length > 0) {
                    return el.innerText.replace(/[^0-9,.]/g, "");
                }
            }
            return "N/A";
        }''')
        
        list_price_str = await page.evaluate('''() => {
            let selectors = ['.basisPrice .a-offscreen', '.a-text-price .a-offscreen', '.a-price.a-text-price span[aria-hidden="true"]'];
            for(let sel of selectors) {
                let el = document.querySelector(sel);
                if (el && el.innerText.trim().length > 0) {
                    return el.innerText.replace(/[^0-9,.]/g, "");
                }
            }
            
            const el = Array.from(document.querySelectorAll("span")).find(s => 
                s.innerText.includes("Precio de lista") || 
                s.innerText.includes("Precio recomendado") ||
                s.innerText.includes("List Price")
            );
            if (el && el.nextElementSibling) {
                let t = el.nextElementSibling.innerText.replace(/[^0-9,.]/g, "");
                if (t) return t;
            }
            if (el && el.parentElement) {
                let t = el.parentElement.innerText.replace(/[^0-9,.]/g, "");
                if (t && t.length < 15) return t;
            }
            return "N/A";
        }''')
        
        def safe_float(val):
            try:
                if not val or val == "N/A": return 0.0
                return float(val.replace(",", ""))
            except:
                return 0.0

        if list_price_str == "N/A" or not list_price_str or not offer_price_str:
            list_price_str = "N/A"
        elif offer_price_str != "N/A" and list_price_str != "N/A":
            if safe_float(list_price_str) <= safe_float(offer_price_str):
                list_price_str = "N/A"

        details = {
            "title": (await page.inner_text("#productTitle")).strip() if await page.query_selector("#productTitle") else "Producto Desconocido",
            "list_price": f"${list_price_str}" if list_price_str not in ("N/A", "") else "",
            "offer_price": f"${offer_price_str}" if offer_price_str not in ("N/A", "") else "N/A",
            "discount": await page.inner_text(".savingsPercentage") if await page.query_selector(".savingsPercentage") else "0%",
            "image_url": await page.get_attribute("#landingImage", "src") if await page.query_selector("#landingImage") else None
        }

        # Extraer galería de imágenes de Amazon
        gallery_images = await page.evaluate(r'''() => {
            const imgs = document.querySelectorAll('#altImages img, #imageBlock img');
            const urls = [];
            for (const img of imgs) {
                let src = img.src;
                if (src && !src.includes("play-button") && !src.includes("video")) {
                    // Limpiar resolución de Amazon para obtener la imagen original
                    let clean = src.replace(/\._.*_\./, '.');
                    if (!urls.includes(clean)) {
                        urls.push(clean);
                    }
                }
            }
            return urls;
        }''')
        details["gallery_images"] = gallery_images if gallery_images else ([details["image_url"]] if details["image_url"] else [])

        print("Realizando captura visual de la oferta...")

        try:
            img_sel = "#imgTagWrapperId, #landingImage, #main-image-container"
            title_sel = "#titleSection"
            price_sel = "#corePrice_feature_div, #priceInsideBuyBox_feature_div, #corePriceDisplay_desktop_feature_div"
            
            img_elem = await page.wait_for_selector(img_sel, timeout=5000)
            title_elem = await page.wait_for_selector(title_sel, timeout=5000)
            price_elem = await page.query_selector(price_sel)
            center_elem = await page.query_selector("#centerCol")
            iconfarm_elem = await page.query_selector("#iconfarmv2_feature_div")
            
            capture_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "product_capture.png")
            
            if img_elem and title_elem:
                await img_elem.scroll_into_view_if_needed()
                await page.wait_for_timeout(1000)
                
                # Ocultar la columna derecha (rightCol) inyectando CSS temporal
                await page.evaluate("let rc = document.getElementById('rightCol'); if(rc) rc.style.display = 'none';")
                
                ib = await img_elem.bounding_box()
                tb = await title_elem.bounding_box()
                pb = await price_elem.bounding_box() if price_elem else None
                cb = await center_elem.bounding_box() if center_elem else None
                ifb = await iconfarm_elem.bounding_box() if iconfarm_elem else None
                
                if ib and tb:
                    x = min(ib['x'], tb['x']) - 10
                    y = min(ib['y'], tb['y']) - 10
                    
                    w_ib = ib['x'] + ib['width']
                    w_tb = tb['x'] + tb['width']
                    w_pb = (pb['x'] + pb['width']) if pb else w_tb
                    w = max(w_ib, w_tb, w_pb) - x + 20
                    
                    # Garantizar que el ancho nunca pase del centerCol
                    if cb:
                        w = min(w, (cb['x'] + cb['width']) - x + 20)
                    
                    h_ib = ib['y'] + ib['height']
                    h_pb = (pb['y'] + pb['height']) if pb else (tb['y'] + tb['height'])
                    
                    # El alto debe ser lo suficiente para cubrir la imagen COMPLETA, o hasta el inicio del iconfarm
                    h_ifb = ifb['y'] if ifb else h_pb
                    h = max(h_ib, h_ifb) - y + 20
                    
                    # Ocultar todos los divs basura que están debajo de la línea roja para que quede blanco
                    await page.evaluate("""() => {
                        let selectors = ['#iconfarmv2_feature_div', '#feature-bullets', '#twisterContainer', '#HLCXComparisonWidget_feature_div', '#altImages'];
                        selectors.forEach(sel => {
                            let el = document.querySelector(sel);
                            if(el) el.style.display = 'none';
                        });
                    }""")
                    
                    # Límite máximo de seguridad (por si la imagen es absurdamente alta)
                    h = min(h, 950)
                    
                    viewport = page.viewport_size
                    w = min(w, viewport['width'] - x)
                    h = min(h, viewport['height'] - y)
                    
                    await page.screenshot(path=capture_path, clip={'x': x, 'y': y, 'width': w, 'height': h})
                    details["visual_capture"] = capture_path
                    print("Captura de Amazon realizada con recorte preciso.")
            else:
                ppd = await page.query_selector("#ppd")
                if ppd:
                    await ppd.screenshot(path=capture_path)
                    details["visual_capture"] = capture_path
        except Exception as e:
            print(f"Error al capturar oferta: {e}")
            details["visual_capture"] = None

        print(f"Detalles extraídos: {details['title'][:30]}... | {details['list_price']} -> {details['offer_price']}")
        return details

    async def scrape_deals_page(self, page, deals_url):
        """Busca y extrae URLs de productos de la página de ofertas actual de Amazon"""
        print(f"Buscando ofertas en: {deals_url}")
        await page.goto(deals_url, wait_until="commit", timeout=60000)
        
        await page.wait_for_timeout(5000)
        
        print("Realizando scroll programático para revelar inventario...")
        for _ in range(12):
            await page.mouse.wheel(0, 2500)
            await page.wait_for_timeout(1500)
        
        deal_selectors = [
            "a.a-link-normal[href*='/dp/']",
            "[data-testid='grid-auto-grid'] a",
            ".DealGridItem-module__item a"
        ]
        
        product_urls = []
        for selector in deal_selectors:
            elements = await page.query_selector_all(selector)
            for el in elements:
                href = await el.get_attribute("href")
                if href and "/dp/" in href:
                    full_url = href if href.startswith("http") else f"{self.amazon_url}{href}"
                    asin_match = re.search(r"/dp/([A-Z0-9]{10})", full_url)
                    if asin_match:
                        asin = asin_match.group(1)
                        clean_url = f"{self.amazon_url}/dp/{asin}"
                        if clean_url not in product_urls:
                            product_urls.append(clean_url)
        
        print(f"Se encontraron {len(product_urls)} ofertas potenciales.")
        random.shuffle(product_urls)
        return product_urls[:30]

    async def get_sitestripe_link(self, page):
        """Genera un enlace corto usando SiteStripe"""
        print("Obteniendo enlace de SiteStripe...")
        try:
            # Esperar a que la barra de SiteStripe esté lista
            await page.wait_for_selector("#amzn-ss-text-link", timeout=6000)
            await page.wait_for_timeout(2000)
            
            short_link = ""
            # Intentar clickear y esperar el textarea hasta 3 veces
            for attempt in range(3):
                try:
                    # Forzar el clic intentando en el botón interno primero, y luego en el contenedor principal
                    btn_locator = page.locator("#amzn-ss-get-link-button").first
                    if await btn_locator.count() > 0:
                        await btn_locator.click(delay=200)
                    else:
                        await page.locator("#amzn-ss-text-link").click(force=True)
                    
                    # Esperar al textarea usando selectores más genéricos también
                    textarea = await page.wait_for_selector("#amzn-ss-text-shortlink-textarea, textarea[id*='shortlink']", state="visible", timeout=6000)
                    
                    for _ in range(10):
                        code = await textarea.input_value()
                        if code and ("amzn.to" in code or "amazon" in code):
                            short_link = code.strip()
                            break
                        await asyncio.sleep(0.5)
                        
                    if short_link:
                        break  # Éxito, salir del loop de intentos
                except Exception as inner_e:
                    print(f"Intento {attempt + 1} para abrir SiteStripe falló: {inner_e}")
                    await page.wait_for_timeout(1500)
                    
            if short_link:
                await page.keyboard.press("Escape")
                print(f"Enlace generado correctamente: {short_link}")
                return short_link
        except Exception as e:
            print(f"Error principal en SiteStripe: {e}")
            
        # ----------------------------------------------------
        # FALLBACK: Construir enlace manual si SiteStripe falla
        # ----------------------------------------------------
        print("[AMAZON] SiteStripe no abrio. Generando enlace manual usando ASIN y AFFILIATE_TAG...")
        try:
            url = page.url
            asin_match = re.search(r"/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})", url)
            if asin_match:
                asin = asin_match.group(1) or asin_match.group(2)
                tag = os.getenv("AFFILIATE_TAG", "tu_tag-20")
                manual_link = f"https://www.amazon.com.mx/dp/{asin}/ref=nosim?tag={tag}"
                print(f"Enlace de afiliado manual generado: {manual_link}")
                return manual_link
        except Exception as fallback_err:
            print(f"Error generando enlace manual: {fallback_err}")
            
        return "ENLACE_POR_DEFECTO"
