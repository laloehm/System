"""
Scraper de ofertas de Amazon.com.mx para Linux.
- Sin sesión ni login requerido (páginas públicas)
- Links de afiliado via ?tag= automático
- Filtra productos con menos del 30% de descuento
- Guarda directo en products_list.json (cola general)
"""

import asyncio
import os
import sys
import re
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright
from core.config import Config
from core.storage import json_load, json_save_atomic
from core.discard_manager import is_already_discarded

MIN_DISCOUNT_PCT = 30
DEFAULT_AMAZON_PAGES = 1

PARTNER_TAG = os.getenv("AMAZON_PARTNER_TAG", "")
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SESSION_CANDIDATES = [
    os.path.join(_BASE, "storage_state_amazon.json"),
    os.path.join(_BASE, "storage_state_linux.json"),
    os.path.join(_BASE, "storage_state.json"),
]


def _get_amazon_session() -> str:
    """Detecta sesión en tiempo de ejecución para capturar archivos sincronizados por Syncthing."""
    return next((p for p in _SESSION_CANDIDATES if os.path.exists(p)), "")

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _tag_url(asin: str) -> str:
    base = f"https://www.amazon.com.mx/dp/{asin}/ref=nosim"
    return f"{base}?tag={PARTNER_TAG}" if PARTNER_TAG else f"https://www.amazon.com.mx/dp/{asin}"


def _parse_discount(text: str) -> float:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text or "")
    if match:
        return float(match.group(1).replace(",", "."))
    return 0.0


def _normalize_price(raw: str) -> str:
    nums = re.findall(r"\d+[\d,.]*", raw or "")
    if not nums:
        return ""
    price = nums[0].replace(",", "")
    return f"${price}"


async def _scrape_deals_page(page, search_url: str) -> list[str]:
    await page.goto(search_url, wait_until="commit", timeout=60000)
    await page.wait_for_timeout(4000)

    for _ in range(8):
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(1200)

    urls = []
    for selector in ["a.a-link-normal[href*='/dp/']", "[data-testid='grid-auto-grid'] a"]:
        for el in await page.query_selector_all(selector):
            href = await el.get_attribute("href")
            if href and "/dp/" in href:
                m = re.search(r"/dp/([A-Z0-9]{10})", href)
                if m and m.group(1) not in [re.search(r"/dp/([A-Z0-9]{10})", u).group(1) for u in urls if "/dp/" in u]:
                    urls.append(f"https://www.amazon.com.mx/dp/{m.group(1)}")

    random.shuffle(urls)
    return urls[:40]


async def _scrape_product(page, asin: str, url: str) -> dict | None:
    await page.goto(url, wait_until="commit", timeout=60000)
    try:
        await page.wait_for_selector("#productTitle", timeout=10000)
    except Exception:
        if "sorry" in (await page.title()).lower():
            print(f"[AMAZON] CAPTCHA detectado en {asin}")
        return None

    async def get_price(selector):
        # Buscar SÓLO dentro del contenedor principal del producto para evitar agarrar
        # precios de "Productos Relacionados" o "Patrocinados" más abajo en la página.
        for base in ["#corePriceDisplay_desktop_feature_div", "#corePrice_feature_div", "#apex_desktop", "#centerCol"]:
            el = await page.query_selector(f"{base} {selector}")
            if el:
                nums = re.findall(r"\d+[\d,.]*", await el.inner_text())
                if nums: return nums[0]
        return ""

    title = ((await page.inner_text("#productTitle")) or "").strip()

    # Extraer formatos, subtítulos y categorías de Amazon (ej. "Pasta blanda", "Pasta dura", "Libros")
    format_parts = []
    for sel in ["#productSubtitle", "#tmmSwatches", "#booksTitle", "#bylineInfo", "#wayfinding-breadcrumbs_feature_div", "#rpi-attribute-book_details-fomat"]:
        try:
            el = await page.query_selector(sel)
            if el:
                txt = (await el.inner_text() or "").strip()
                if txt:
                    format_parts.append(txt)
        except Exception:
            pass
    format_text = " ".join(format_parts)

    offer_raw = await get_price(".a-price:not(.a-text-price) span.a-offscreen")
    list_raw = await get_price(".a-price.a-text-price span[aria-hidden='true']")
    discount_text = ""
    disc_el = await page.query_selector(".savingsPercentage")
    if disc_el:
        discount_text = (await disc_el.inner_text()).strip()

    if not title or not offer_raw:
        return None

    discount_pct = _parse_discount(discount_text)

    # Validacion estricta de ahorro
    ahorro_pesos = 0
    offer_val = 0
    list_val = 0

    try:
        from core.utils import parse_price_pesos
        offer_norm = _normalize_price(offer_raw)
        list_norm = _normalize_price(list_raw)
        offer_val = parse_price_pesos(offer_norm)
        list_val = parse_price_pesos(list_norm)
        if list_val > offer_val:
            ahorro_pesos = list_val - offer_val
        elif offer_val > 0 and discount_pct > 0:
            est_list_val = offer_val / (1.0 - (discount_pct / 100.0))
            ahorro_pesos = est_list_val - offer_val
        else:
            ahorro_pesos = 0
    except Exception as e:
        print(f"[AMAZON] {asin} ERROR al calcular ahorro: {e} (offer_raw='{offer_raw}', list_raw='{list_raw}')")
        pass

    is_approved = False
    dyn_config = Config.get_dynamic_config()
    min_ahorro_estricto = dyn_config.get('min_strict', dyn_config.get('min_strict_savings', 100))
    min_price = float(getattr(Config, 'MIN_PRICE', 100.0))
    max_price = dyn_config.get('max_price', 15000.0)

    if (
        offer_val >= min_price
        and (max_price <= 0 or offer_val <= max_price)
        and ahorro_pesos >= min_ahorro_estricto
    ):
        is_approved = True

    if not is_approved:
        print(f"[AMAZON] {asin} RECHAZADO: Precio=${offer_val:.0f}, ListaOrig=${list_val:.0f}, Ahorro=${ahorro_pesos:.0f} (min=${min_ahorro_estricto:.0f})")
        return None

    image_url = await page.get_attribute("#landingImage", "src") or ""

    # Link de afiliado: SiteStripe si hay sesión, ?tag= como fallback
    from scrapers.amazon_scraper import AmazonScraper
    scraper = AmazonScraper()
    affiliate_link = ""
    _session = _get_amazon_session()
    if _session:
        affiliate_link = await scraper.get_sitestripe_link(page)
    if not affiliate_link or affiliate_link == "ENLACE_POR_DEFECTO":
        affiliate_link = _tag_url(asin)

    # Screenshot de imagen + precio
    screenshot_path = ""
    try:
        cap_path = os.path.join(Config.CAPTURES_DIR, f"{asin}.png")
        os.makedirs(Config.CAPTURES_DIR, exist_ok=True)
        if not os.path.exists(cap_path):
            img_el = await page.query_selector("#imgTagWrapperId, #landingImage, #main-image-container")
            title_el = await page.query_selector("#titleSection")
            price_el = await page.query_selector("#corePrice_feature_div, #priceInsideBuyBox_feature_div, #corePriceDisplay_desktop_feature_div")
            center_el = await page.query_selector("#centerCol")
            iconfarm_el = await page.query_selector("#iconfarmv2_feature_div")
            
            if img_el and title_el:
                await page.evaluate("let rc = document.getElementById('rightCol'); if(rc) rc.style.display = 'none';")
                ib = await img_el.bounding_box()
                tb = await title_el.bounding_box()
                pb = await price_el.bounding_box() if price_el else None
                cb = await center_el.bounding_box() if center_el else None
                ifb = await iconfarm_el.bounding_box() if iconfarm_el else None
                
                if ib and tb:
                    x = min(ib["x"], tb["x"]) - 10
                    y = min(ib["y"], tb["y"]) - 10
                    
                    w_ib = ib['x'] + ib['width']
                    w_tb = tb['x'] + tb['width']
                    w_pb = (pb['x'] + pb['width']) if pb else w_tb
                    w = max(w_ib, w_tb, w_pb) - x + 20
                    
                    if cb:
                        w = min(w, (cb['x'] + cb['width']) - x + 20)
                    
                    h_ib = ib['y'] + ib['height']
                    h_pb = (pb['y'] + pb['height']) if pb else (tb['y'] + tb['height'])
                    
                    h_ifb = ifb['y'] if ifb else h_pb
                    h = max(h_ib, h_ifb) - y + 20
                    
                    await page.evaluate("""() => {
                        let selectors = ['#iconfarmv2_feature_div', '#feature-bullets', '#twisterContainer', '#HLCXComparisonWidget_feature_div', '#altImages'];
                        selectors.forEach(sel => {
                            let el = document.querySelector(sel);
                            if(el) el.style.display = 'none';
                        });
                    }""")
                    
                    h = min(h, 950)
                    
                    vp = page.viewport_size
                    await page.screenshot(path=cap_path, clip={
                        "x": max(0, x), "y": max(0, y),
                        "width": min(w, vp["width"] - x),
                        "height": min(h, vp["height"] - y)
                    })
            else:
                ppd = await page.query_selector("#ppd")
                if ppd:
                    await ppd.screenshot(path=cap_path)
        if os.path.exists(cap_path):
            screenshot_path = cap_path
    except Exception as e:
        print(f"[AMAZON] Error captura {asin}: {e}")

    disc_fmt = f"{discount_pct:.0f}% OFF" if discount_pct else discount_text
    return {
        "id": asin,
        "title": title,
        "format_text": format_text,
        "offer_price": _normalize_price(offer_raw),
        "list_price": _normalize_price(list_raw),
        "discount": disc_fmt,
        "image_url": image_url,
        "affiliate_url": affiliate_link,
        "screenshot": screenshot_path,
        "niche": "[CAT:GENERAL]",
        "source": "amazon",
    }


async def run(notify_fn=None, keyword_override: str = None) -> int:
    """Corre el scraper y retorna el número de productos importados."""
    if not PARTNER_TAG:
        msg = "⚠️ AMAZON_PARTNER_TAG no configurado en .env — links sin tag de afiliado"
        print(f"[AMAZON] {msg}")
        if notify_fn:
            await notify_fn(msg)

    from core.history_manager import load_recent_history
    history = load_recent_history()

    queue = json_load(Config.JSON_QUEUE_FILE, default=[])
    if not isinstance(queue, list):
        queue = []

    known_ids = {p.get("id") for p in queue if isinstance(p, dict)}
    known_urls = {p.get("affiliate_url") for p in queue if isinstance(p, dict)}

    # Leer palabras excluidas de la configuración
    scraping_config = json_load(os.path.join(Config.BASE_DIR, "scraping_config.json"), default={})
    excluded_keywords = [w.strip().lower() for w in scraping_config.get("excluded_keywords", []) if w.strip()]
    blacklist_words = Config.BLACKLIST_WORDS  # También incluir blacklist del .env

    imported = []

    amazon_session = _get_amazon_session()
    if amazon_session:
        print(f"[AMAZON] Cargando sesión desde {amazon_session}")
    else:
        print(f"[AMAZON] Sin sesión — links via ?tag={PARTNER_TAG}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--lang=es-MX"]
        )
        ctx_opts = {
            "viewport": {"width": 1366, "height": 800},
            "user_agent": random.choice(USER_AGENTS),
            "locale": "es-MX",
        }
        if amazon_session:
            ctx_opts["storage_state"] = amazon_session

        context = await browser.new_context(**ctx_opts)
        page = await context.new_page()

        try:
            # Obtener palabra clave del turno (o usar keyword_override)
            scraping_config = json_load(os.path.join(Config.BASE_DIR, "scraping_config.json"), default={"general": "", "amazon_pages": 1})
            if keyword_override:
                keyword = keyword_override.strip()
            else:
                from core.apify_refiller import get_scraping_keyword
                keyword = get_scraping_keyword("general", "tecnologia", advance=True)
            
            # Páginas a scrapear de Amazon (cada 'página' equivale a ~10 productos en este script para no tardar tanto)
            amazon_pages = int(scraping_config.get("amazon_pages", DEFAULT_AMAZON_PAGES))
            target_products = amazon_pages * 10
            
            if keyword and keyword.lower() not in ["", "ofertas", "deals"]:
                from urllib.parse import quote
                print(f"[AMAZON] Buscando por palabra clave en turno: '{keyword}' en {amazon_pages} páginas")
                
                for page_num in range(1, amazon_pages + 1):
                    if len(imported) >= target_products:
                        break
                    
                    page_url = f"https://www.amazon.com.mx/s?k={quote(keyword)}&page={page_num}"
                    print(f"[AMAZON] Scrapeando página {page_num}: {page_url}")
                    product_urls = await _scrape_deals_page(page, page_url)
                    
                    for url in product_urls:
                        if len(imported) >= target_products:
                            break
                        m = re.search(r"/dp/([A-Z0-9]{10})", url)
                        if not m:
                            continue
                        asin = m.group(1)

                        # Verificar: ya en cola, ya publicado, o ya descartado
                        if asin in known_ids or asin in history or is_already_discarded(asin):
                            continue

                        aff_url = _tag_url(asin)
                        if aff_url in known_urls or aff_url in history:
                            continue

                        print(f"[AMAZON] Procesando {asin} (Página {page_num})...")
                        await asyncio.sleep(random.uniform(3, 6))

                        product = await _scrape_product(page, asin, url)
                        if not product:
                            continue

                        # Filtrar por palabras excluidas (en título y en formato/categoría de Amazon)
                        search_text = (product.get("title", "") + " " + product.get("format_text", "")).lower()
                        matched_word = next((word for word in excluded_keywords + blacklist_words if word in search_text), None)
                        if matched_word:
                            print(f"[AMAZON] {asin} RECHAZADO: Contiene palabra excluida '{matched_word}'")
                            continue

                        # Guardar producto
                        queue.append(product)
                        json_save_atomic(Config.JSON_QUEUE_FILE, queue, indent=2, ensure_ascii=False)
                        imported.append(product)
                        known_ids.add(asin)
                        known_urls.add(aff_url)
                        print(f"[AMAZON] OK: {asin} importado exitosamente.")
            else:
                start_url = "https://www.amazon.com.mx/deals"
                print(f"[AMAZON] Buscando en sección principal de Ofertas (Deals) hasta {target_products} productos")

                product_urls = await _scrape_deals_page(page, start_url)
                print(f"[AMAZON] {len(product_urls)} productos potenciales encontrados")

                for url in product_urls:
                    if len(imported) >= target_products:
                        break

                    m = re.search(r"/dp/([A-Z0-9]{10})", url)
                    if not m:
                        continue
                    asin = m.group(1)

                    # Verificar: ya en cola, ya publicado, o ya descartado
                    if asin in known_ids or asin in history or is_already_discarded(asin):
                        continue

                    aff_url = _tag_url(asin)
                    if aff_url in known_urls or aff_url in history:
                        continue

                    print(f"[AMAZON] Procesando {asin}...")
                    await asyncio.sleep(random.uniform(3, 6))

                    product = await _scrape_product(page, asin, url)
                    if not product:
                        continue

                    # Filtrar por palabras excluidas (en título y en formato/categoría de Amazon)
                    search_text = (product.get("title", "") + " " + product.get("format_text", "")).lower()
                    matched_word = next((word for word in excluded_keywords + blacklist_words if word in search_text), None)
                    if matched_word:
                        print(f"[AMAZON] {asin} RECHAZADO: Contiene palabra excluida '{matched_word}'")
                        continue

                    queue.append(product)
                    imported.append(product)
                    known_ids.add(asin)
                    known_urls.add(aff_url)
                    print(f"[AMAZON] OK: {product['title'][:50]} | {product['discount']}")

        finally:
            await context.close()
            await browser.close()

    if imported:
        json_save_atomic(Config.JSON_QUEUE_FILE, queue, indent=2, ensure_ascii=False)

    print(f"[AMAZON] {len(imported)} productos importados a la cola general")
    return len(imported)


if __name__ == "__main__":
    asyncio.run(run())
