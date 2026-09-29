import asyncio
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

async def scrape_ml_product_headless(page, url):
    """
    Realiza un scrape de Mercado Libre usando una página ya abierta.
    Obtiene título, precios y descuento.
    """
    print(f"Obteniendo datos de Mercado Libre: {url}")
    details = {
        "title": "Oferta Especial en Mercado Libre",
        "list_price": "",
        "offer_price": "Ver precio en el enlace",
        "discount": "0%",
        "image_url": None,
        "visual_capture": None,
        "affiliate_url": url
    }
    
    try:
        # Ir al link (soporta redirecciones de meli.la)
        print(f"🔗 Navegando a: {url}")
        await page.goto(url, wait_until="load", timeout=60000)
        
        current_url = page.url
        print(f"URL cargada final: {current_url}")
        
        is_lists_redirect = False
        if "/social/" in current_url:
            details["is_social_redirect"] = True
            print("⚠️ [REDIRECCIÓN] Página social detectada. Extrayendo datos sin navegar al producto...")

            # 1. OG tags: título e imagen (página pública, siempre disponible)
            try:
                og = await page.evaluate("""() => {
                    const get = (sel) => {
                        const el = document.querySelector(sel);
                        return el ? (el.getAttribute('content') || el.content || '') : '';
                    };
                    return {
                        title: get('meta[property=\"og:title\"]') || get('meta[name=\"og:title\"]'),
                        image: get('meta[property=\"og:image\"]') || get('meta[name=\"og:image\"]')
                    };
                }""")
                if og.get("title") and len(og["title"]) > 5:
                    details["title"] = og["title"]
                    print(f"✅ Título OG: {og['title'][:60]}")
                if og.get("image"):
                    details["image_url"] = og["image"]
            except Exception as e:
                print(f"⚠️ OG extraction falló: {e}")

            # 2. Precios y descuento directamente de la tarjeta de producto en la página social
            # La tarjeta es pública y muestra precio, precio tachado y badge de descuento
            try:
                social_data = await page.evaluate("""() => {
                    const getCleanPrice = (el) => el ? el.innerText.replace(/[^0-9]/g, "") : "";

                    // Buscar la tarjeta específica del producto objetivo (NO mezclar elementos de tarjetas distintas)
                    const cards = Array.from(document.querySelectorAll('.poly-card, .poly-component'));
                    let targetCard = null;
                    for (const c of cards) {
                        const tEl = c.querySelector('.poly-component__title, h2, a[title]');
                        if (tEl && tEl.innerText.trim().length > 3) {
                            targetCard = c;
                            break;
                        }
                    }
                    if (!targetCard) targetCard = document;

                    // Precio de oferta: buscar el actual (NO el tachado) dentro de la tarjeta objetivo
                    const offerEl = targetCard.querySelector('.poly-price__current .andes-money-amount__fraction') ||
                                    targetCard.querySelector('.andes-money-amount__main .andes-money-amount__fraction') ||
                                    targetCard.querySelector('.ui-pdp-price__second-line .andes-money-amount__fraction');

                    // Precio original (tachado con <s>) dentro de la MISMA tarjeta objetivo
                    const listEl  = targetCard.querySelector('s .andes-money-amount__fraction') ||
                                    targetCard.querySelector('.andes-money-amount--previous .andes-money-amount__fraction') ||
                                    targetCard.querySelector('.poly-price__original .andes-money-amount__fraction');

                    // Guardia: si los dos selectores apuntan al mismo nodo, limpiar listEl
                    const sameNode = offerEl && listEl && offerEl === listEl;

                    const discEl  = targetCard.querySelector('.poly-price__disc') ||
                                    targetCard.querySelector('.andes-money-amount__discount') ||
                                    targetCard.querySelector('.ui-pdp-color--GREEN');

                    const titleEl = targetCard.querySelector('h2.poly-component__title') ||
                                    targetCard.querySelector('.poly-component__title') ||
                                    targetCard.querySelector('h2');

                    let offer = getCleanPrice(offerEl);
                    let list = sameNode ? "" : getCleanPrice(listEl);
                    let discount = discEl ? discEl.innerText.trim() : "";
                    let title = titleEl ? titleEl.innerText.trim() : "";

                    // REGLA MATEMÁTICA ESTRICTA: El precio de oferta DEBE ser menor al precio de lista
                    if (offer && list && Number(offer) >= Number(list)) {
                        list = "";
                        discount = "";
                    }

                    return {
                        offer: offer,
                        list: list,
                        discount: discount,
                        title: title
                    };
                }""")

                if social_data.get("offer"):
                    details["offer_price"] = f"${social_data['offer']}"
                    print(f"✅ Precio oferta desde social: {details['offer_price']}")
                if social_data.get("list"):
                    details["list_price"] = f"${social_data['list']}"
                    print(f"✅ Precio lista desde social: {details['list_price']}")
                else:
                    details["list_price"] = ""
                if social_data.get("discount"):
                    details["discount"] = social_data["discount"]
                    print(f"✅ Descuento desde social: {details['discount']}")
                else:
                    details["discount"] = "0%"
                if social_data.get("title") and len(social_data["title"]) > 3:
                    details["title"] = social_data["title"]
                    print(f"✅ Título desde tarjeta social: {social_data['title'][:60]}")
            except Exception as e:
                print(f"⚠️ Extracción de precios desde página social falló: {e}")

            # 3. Buscar MLM ID en el HTML para nombrar la captura correctamente
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            real_url = None
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ("/p/MLM" in href or "articulo.mercadolibre.com.mx/MLM" in href) and "mercadolibre.com.mx" in href:
                    real_url = href.split("#")[0].split("?")[0]
                    break

            if real_url:
                details["real_url"] = real_url
                match = re.search(r'MLM-?(\d+)', real_url)
                if match:
                    details["id"] = f"MLM{match.group(1)}"
                    print(f"✅ ID extraído: {details['id']}")
            else:
                is_lists_redirect = True

            # 4. Si ya tenemos el precio, retornar sin navegar al producto
            # (navegar requiere sesión activa de ML y causaría la redirección a login)
            if details.get("offer_price") and details["offer_price"] != "Ver precio en el enlace":
                print("✅ Datos completos desde página social. Omitiendo navegación al producto.")
                if details.get("image_url"):
                    details["gallery_images"] = [details["image_url"]]
                return details

            # Fallback: intentar navegar al producto real (solo funciona con sesión activa de ML)
            if real_url:
                print(f"🔗 Fallback: navegando al producto real: {real_url}")
                await page.goto(real_url, wait_until="load", timeout=60000)

        if is_lists_redirect:
            print("⚠️ [ERROR] No se pudo encontrar un producto único en la página redirigida. Abortando scrape.")
            details["is_redirected_to_lists"] = True
            return details
        
        # Esperar a que aparezca al menos el título o un precio (max 10s)
        try:
            await page.wait_for_selector("h1, .andes-money-amount__fraction", timeout=10000)
        except:
            print("⚠️ Aviso: La página tardó mucho en mostrar elementos clave.")
            # Si ya tenemos datos del OG, no es un error crítico
            if details["title"] != "Oferta Especial en Mercado Libre":
                print("ℹ️ Usando datos obtenidos de la página social (OG tags).")
                return details

        # 1. TÍTULO (Con fallback al título de la página)
        title = await page.evaluate('''() => {
            const selectors = ['h1.ui-pdp-title', '.ui-pdp-title', '.poly-component__title', 'h1'];
            for (let s of selectors) {
                const el = document.querySelector(s);
                if (el && el.innerText.trim().length > 3) return el.innerText;
            }
            return document.title.split('|')[0].replace('Mercado Libre', '').trim();
        }''')
        if title: details["title"] = title.strip()
            
        # 2. PRECIOS (Extracción con reintentos internos)
        # Soporta tanto páginas de listado (/MLM...) como páginas de catálogo (/p/MLM...)
        prices = await page.evaluate('''() => {
            const getCleanPrice = (el) => el ? el.innerText.replace(/[^0-9]/g, "") : "";

            // Precio de oferta: orden de prioridad para cubrir PDPs y catálogos
            let offerEl =
                document.querySelector('.ui-pdp-price__second-line .andes-money-amount__fraction') ||
                document.querySelector('.andes-money-amount__main .andes-money-amount__fraction') ||
                document.querySelector('.poly-price__current .andes-money-amount__fraction') ||
                document.querySelector('.ui-pdp-price .andes-money-amount__fraction') ||
                document.querySelector('[class*="price"] .andes-money-amount__fraction');

            // Precio original (tachado)
            let listEl =
                document.querySelector('.andes-money-amount--previous .andes-money-amount__fraction') ||
                document.querySelector('s .andes-money-amount__fraction') ||
                document.querySelector('.poly-price__original .andes-money-amount__fraction') ||
                document.querySelector('.ui-pdp-price__original-value .andes-money-amount__fraction');

            // Guardia: si offerEl y listEl apuntan al mismo elemento, limpiar listEl
            if (offerEl && listEl && offerEl === listEl) listEl = null;

            let cleanOffer = getCleanPrice(offerEl);
            let cleanList = getCleanPrice(listEl);
            if (cleanOffer && cleanList && Number(cleanOffer) >= Number(cleanList)) {
                cleanList = "";
            }

            return {
                list: cleanList,
                offer: cleanOffer
            };
        }''')
        
        if prices['list']:
            details["list_price"] = f"${prices['list']}"
        else:
            details["list_price"] = ""
        if prices['offer']:
            details["offer_price"] = f"${prices['offer']}"
            
        # 3. DESCUENTO
        discount = await page.evaluate('''() => {
            const el = document.querySelector('.andes-money-amount__discount') || 
                       document.querySelector('.ui-pdp-color--GREEN') ||
                       document.querySelector('.poly-price__disc');
            return el ? el.innerText : null;
        }''')
        if discount: details["discount"] = discount.strip()

        # 4. IMAGEN LIMPIA DEL PRODUCTO
        image_url = await page.evaluate(r'''() => {
            const selectors = [
                '.ui-pdp-gallery__figure img',
                '.poly-component__picture img',
                'figure.ui-pdp-gallery__figure img',
                '.ui-pdp-image',
                'img.poly-component__picture'
            ];
            for (let s of selectors) {
                const el = document.querySelector(s);
                if (el && el.src && el.naturalWidth > 100) {
                    return el.src.replace(/-[A-Z]_[0-9]+x[0-9]+\.jpg/, '-O.jpg')
                               .replace(/\?.*$/, '');
                }
            }
            return null;
        }''')
        if image_url: details["image_url"] = image_url

        # 4b. GALERÍA DE IMÁGENES SECUNDARIAS
        gallery_images = await page.evaluate(r'''() => {
            const imgs = document.querySelectorAll('.ui-pdp-gallery__thumbnail img, span.ui-pdp-gallery__wrapper img, .ui-pdp-gallery__figure img');
            const urls = [];
            for (const img of imgs) {
                let src = img.getAttribute('data-zoom') || img.src;
                if (src) {
                    let clean = src.replace(/-[A-Z]_[0-9]+x[0-9]+\.jpg/, '-O.jpg')
                                   .replace(/-[A-Z]\.jpg/, '-O.jpg')
                                   .replace(/-[A-Z]\.webp/, '-O.webp')
                                   .replace(/\?.*$/, '');
                    if (!urls.includes(clean)) {
                        urls.push(clean);
                    }
                }
            }
            return urls;
        }''')
        details["gallery_images"] = gallery_images if gallery_images else ([image_url] if image_url else [])


        # 4. CAPTURAR LINK DE AFILIADO (Si estamos logueados)
        try:
            modal_input = await page.query_selector('textarea.andes-form-control__field, input[value*="meli.la"]')
            if modal_input:
                details["affiliate_url"] = await modal_input.evaluate('el => el.value')
            else:
                # Si no hay modal, intentar disparar el botón de compartir
                share_btn = await page.query_selector('.ui-pdp-affiliate-share-button, button:has-text("Compartir")')
                if share_btn:
                    await share_btn.click()
                    await page.wait_for_timeout(2000)
                    modal_input = await page.query_selector('textarea.andes-form-control__field, input[value*="meli.la"]')
                    if modal_input:
                        details["affiliate_url"] = await modal_input.evaluate('el => el.value')
        except: pass

        # 5. ID DEL PRODUCTO (para URLs directas de producto, no social)
        if "/social/" not in current_url:
            try:
                match = re.search(r'MLM-?(\d+)', page.url)
                if match:
                    details["id"] = f"MLM{match.group(1)}"
            except Exception:
                pass

    except Exception as e:
        print(f"Aviso: Fallo extrayendo datos ML: {e}")
        
    return details


async def get_gallery_images_headless(page, url):
    """
    Extrae la galería de imágenes de un producto de Mercado Libre usando
    una página Playwright ya abierta. Navega al URL del producto si es necesario.
    Retorna una lista de URLs de imágenes limpias (formato -O.jpg).
    """
    try:
        current_url = page.url
        # Solo navegar si la página actual no es ya el producto
        if url and url not in current_url and current_url not in url:
            # Convertir link corto meli.la a URL directa del producto si es posible
            target_url = url
            import re as _re
            ml_match = _re.search(r'MLM-?(\d+)', url)
            if ml_match and ("meli.la" in url or "/social/" in url):
                clean_id = f"MLM-{ml_match.group(1)}"
                target_url = f"https://articulo.mercadolibre.com.mx/{clean_id}"
            
            print(f"[GALERÍA ML] Navegando a: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # Si aterrizamos en una página social, buscar el enlace real y navegar a él
            if "/social/" in page.url:
                print("[GALERÍA ML] Página social detectada, buscando URL real del producto...")
                html = await page.content()
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if ("/p/MLM" in href or "articulo.mercadolibre.com.mx/MLM" in href) and "mercadolibre.com.mx" in href:
                        real_url = href.split("#")[0].split("?")[0]
                        print(f"[GALERÍA ML] Redirigiendo a URL real: {real_url}")
                        await page.goto(real_url, wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(2000)
                        break

        # Esperar a que la galería cargue
        try:
            await page.wait_for_selector(
                '.ui-pdp-gallery__thumbnail img, .ui-pdp-gallery__figure img',
                timeout=5000
            )
        except Exception:
            pass  # Continuar aunque no aparezca el selector exacto

        gallery_images = await page.evaluate(r'''() => {
            const imgs = document.querySelectorAll('.ui-pdp-gallery__thumbnail img, span.ui-pdp-gallery__wrapper img, .ui-pdp-gallery__figure img');
            const urls = [];
            for (const img of imgs) {
                let src = img.getAttribute('data-zoom') || img.src;
                if (src) {
                    let clean = src.replace(/-[A-Z]_[0-9]+x[0-9]+\.jpg/, '-O.jpg')
                                   .replace(/-[A-Z]\.jpg/, '-O.jpg')
                                   .replace(/-[A-Z]\.webp/, '-O.webp')
                                   .replace(/\?.*$/, '');
                    if (!urls.includes(clean) && clean.startsWith('http')) {
                        urls.push(clean);
                    }
                }
            }
            // Fallback: buscar imagen principal si no hay galería
            if (urls.length === 0) {
                const selectors = [
                    '.ui-pdp-gallery__figure img',
                    '.poly-component__picture img',
                    '.ui-pdp-image'
                ];
                for (let s of selectors) {
                    const el = document.querySelector(s);
                    if (el && el.src && el.naturalWidth > 100) {
                        let clean = el.src.replace(/-[A-Z]_[0-9]+x[0-9]+\.jpg/, '-O.jpg')
                                          .replace(/\?.*$/, '');
                        if (clean.startsWith('http')) urls.push(clean);
                        break;
                    }
                }
            }
            return urls;
        }''')

        print(f"[GALERÍA ML] {len(gallery_images)} imágenes extraídas de {url}")
        return gallery_images if gallery_images else []

    except Exception as e:
        print(f"[GALERÍA ML] Error extrayendo galería de {url}: {e}")
        return []
