"""
ml_offers_scraper.py
Scraper anónimo de ofertas de Mercado Libre.
- Sin sesión, sin storage_state, sin riesgo de invalidar cookies.
- Extrae todo del listado (sin visitar productos individuales).
- Filtra: tecnología + moda + hogar (productos buenos) con mínimo 50% de descuento.
- Envía los links crudos a Telegram para procesamiento manual.
"""
import asyncio
import os
import json
import re
from playwright.async_api import async_playwright
from datetime import datetime
from core.storage import json_load, json_save_atomic

BASE_OFFERS_URL  = "https://www.mercadolibre.com.mx/ofertas"
OUTPUT_FILE      = "products_list.json"
HISTORY_FILE     = "published_history.json"
MIN_DISCOUNT_PCT = 50

# Tecnología
_TECH = [
    "laptop", "computadora", "notebook", "pc ", "monitor", "tablet ", "ipad",
    "celular", "smartphone", "iphone", "samsung", "pixel", "motorola", "xiaomi",
    "redmi", "poco ", "realme", "oppo",
    "airpods", "audifonos", "auriculares", "audífonos", "bocina bluetooth",
    "bocina inalambrica", "bocina inalámbrica", "speaker", "nothing ear",
    "teclado", "mouse", "webcam", "disco duro", "ssd", "memoria ram",
    "procesador", "tarjeta de video", "gpu", "ram ddr",
    "nintendo", "playstation", "xbox", "consola", "control inalambrico",
    "smart tv", "televisor", "smartwatch", "proyector",
    "impresora", "cámara", "camara", "router", "wifi", "drone",
    "reloj inteligente", "kindle", "echo alexa", "alexa", "google nest",
    "gopro", "batería portátil", "powerbank", "cargador inalambrico", "cargador inalámbrico",
    "tws", "anc ", "earbuds", "lenovo", "dell ", "hp ", "asus", "acer ",
    "macbook", "apple watch", "galaxy watch", "galaxy s", "galaxy a",
]

# Moda y calzado (marcas + categorías)
_FASHION = [
    "tenis ", "tenis nike", "tenis adidas", "tenis puma", "tenis reebok",
    "nike ", "adidas ", "puma ", "reebok ", "under armour", "jordan ",
    "new balance", "vans ", "converse ", "fila ", "skechers",
    "pants ", "pantalon ", "pantalón ", "jogger ", "jeans ", "leggings ",
    "playera ", "camiseta ", "polo ", "camisa ",
    "sudadera ", "hoodie ", "chamarra ", "chamara ", "jacket ", "abrigo ",
    "tenis hombre", "tenis mujer", "tenis niño",
    "zapatos", "botas ", "sandalias ",
]

# Perfumería y cuidado personal (marcas reconocidas únicamente)
_BEAUTY = [
    "perfume ", "colonia ", "fragancia ",
    "carolina herrera", "hugo boss", "calvin klein", "armani ", "versace ",
    "dior ", "chanel ", "prada ", "givenchy", "burberry", "lacoste ",
    "ralph lauren", "dolce gabbana", "mont blanc", "viktor&rolf",
]

# Herramientas y hogar (categorías populares)
_HOME = [
    "herramienta ", "taladro ", "sierra ", "lijadora ", "compresor ",
    "destornillador ", "llave inglesa", "dewalt", "milwaukee", "makita",
    "set de herramientas", "caja de herramientas",
    "cafetera ", "licuadora ", "freidora de aire", "air fryer", "olla express",
    "aspiradora ", "roomba", "robot aspirador",
]

ALLOWED_KEYWORDS = _TECH + _FASHION + _BEAUTY + _HOME

# Palabras que descartan el producto aunque coincida un keyword
BLACKLIST = [
    " mg", " ml", "tabletas", "cápsulas", "capsulas", "comprimidos",
    "medicamento", "farmacia", "dosis", "tratamiento", "suplemento",
    "proteína en polvo", "creatina", "vitamina", "suero", "ampolleta",
    "shampoo", "acondicionador", "jabón", "desodorante", "toalla",
    "pañal", "servilleta", "papel higiénico",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def load_history():
    existing = json_load(HISTORY_FILE, default=[])
    return set(existing) if isinstance(existing, list) else set()


def is_valid_product(title: str, product_id: str = "", url: str = "", offer_price: str = "", list_price: str = "", discount: str = "") -> bool:
    """
    Valida si un producto es válido según keywords y blacklist.
    Si es descartado, registra automáticamente el evento.
    """
    from core.config import Config
    from core.discard_logger import log_discarded_product

    t = title.lower()

    # Check hardcoded BLACKLIST
    for blacklist_word in BLACKLIST:
        if blacklist_word in t:
            log_discarded_product(
                product_id=product_id,
                title=title,
                reason=f"Blacklist: {blacklist_word}",
                details={"blacklist_word": blacklist_word, "field": "title"},
                url=url,
                offer_price=offer_price,
                list_price=list_price,
                discount=discount,
                scraper_source="ml_offers_scraper"
            )
            return False

    # Check dynamic excluded_keywords from scraping_config.json
    try:
        config = Config.SCRAPING_CONFIG
        excluded = config.get("excluded_keywords", [])
        if isinstance(excluded, list):
            for keyword in excluded:
                if keyword.lower() in t:
                    log_discarded_product(
                        product_id=product_id,
                        title=title,
                        reason=f"Excluded keyword: {keyword}",
                        details={"excluded_keyword": keyword, "field": "title"},
                        url=url,
                        offer_price=offer_price,
                        list_price=list_price,
                        discount=discount,
                        scraper_source="ml_offers_scraper"
                    )
                    return False
    except Exception as e:
        print(f"[WARN] Error cargando excluded_keywords: {e}")

    # Check si coincide con algún keyword permitido
    if any(k in t for k in ALLOWED_KEYWORDS):
        return True

    # No coincide con ningún keyword permitido
    log_discarded_product(
        product_id=product_id,
        title=title,
        reason="No matched keywords",
        details={"category_keywords_matched": 0},
        url=url,
        offer_price=offer_price,
        list_price=list_price,
        discount=discount,
        scraper_source="ml_offers_scraper"
    )
    return False


async def run_production():
    print(f"--- SCRAPER ANÓNIMO INICIANDO: {datetime.now()} ---")
    await send_scraper_status_message("start")

    history = load_history()
    found = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-translate",
            "--disable-features=Translate",
            "--lang=es-MX"
        ])
        # Contexto completamente anónimo — sin sesión de ML
        context = await browser.new_context(
            viewport={"width": 1536, "height": 900},
            user_agent=UA
        )
        page = await context.new_page()

        for page_num in range(1, 6):
            url_page = f"{BASE_OFFERS_URL}?page={page_num}"
            print(f"\n[Página {page_num}] {url_page}")
            try:
                await page.goto(url_page, wait_until="commit", timeout=30000)
            except:
                print(f"   Timeout en página {page_num}, saltando...")
                continue
            await asyncio.sleep(4)

            # Scroll para cargar todos los productos del listado
            for i in range(1, 4):
                await page.evaluate(f"window.scrollTo(0, {i * 1500})")
                await asyncio.sleep(1)

            # Extraer datos directamente de las tarjetas del listado
            products_in_page = await page.evaluate("""() => {
                const results = [];
                const cards = document.querySelectorAll('li.promotion-item, .promotion-item, .poly-card');
                cards.forEach(card => {
                    // URL del producto
                    const linkEl = card.querySelector('a.poly-component__title, a[href*="articulo.mercadolibre"]');
                    if (!linkEl) return;
                    const url = linkEl.href || '';
                    if (!url.includes('mercadolibre')) return;

                    // Título
                    const titleEl = card.querySelector('.poly-component__title, h2.poly-box');
                    const title = titleEl ? titleEl.innerText.trim() : '';
                    if (!title) return;

                    // Descuento
                    const discEl = card.querySelector('.poly-price__disc, .andes-money-amount__discount');
                    const discText = discEl ? discEl.innerText.trim() : '';
                    const discMatch = discText.match(/(\\d+)/);
                    const discount = discMatch ? parseInt(discMatch[1]) : 0;

                    // Precio oferta
                    const priceEl = card.querySelector('.poly-price__current .andes-money-amount__fraction') || card.querySelector('.andes-money-amount__fraction');
                    const price = priceEl ? priceEl.innerText.replace(/[^0-9]/g, '') : '';

                    // Precio original
                    const origEl = card.querySelector('s .andes-money-amount__fraction') || card.querySelector('.andes-money-amount--previous .andes-money-amount__fraction');
                    const original = origEl ? origEl.innerText.replace(/[^0-9]/g, '') : '';

                    // Imagen del producto
                    const imgEl = card.querySelector('img.poly-component__picture, img[data-src*="mlstatic"], img[src*="mlstatic"]');
                    const rawImg = imgEl ? (imgEl.getAttribute('data-src') || imgEl.getAttribute('src') || '') : '';
                    const image_url = rawImg.replace(/[?#].*$/, '');

                    results.push({ url, title, discount, price, original, image_url });
                });
                return results;
            }""")

            print(f"   Encontradas {len(products_in_page)} tarjetas en el listado.")

            for item in products_in_page:
                from core.discard_logger import log_discarded_product

                url   = item.get("url", "").split("?")[0].split("#")[0]
                title = item.get("title", "")
                disc  = item.get("discount", 0)
                price = item.get("price", "")
                orig  = item.get("original", "")
                offer_price_str = f"${price}" if price else ""
                list_price_str = f"${orig}" if orig else ""
                discount_str = f"{disc}% OFF" if disc > 0 else ""

                # Extraer ID del producto
                match = re.search(r'MLM-?(\d+)', url)
                if not match:
                    continue
                product_id = f"MLM{match.group(1)}"

                # Filtro 1: Ya fue publicado
                if product_id in history:
                    log_discarded_product(
                        product_id=product_id,
                        title=title,
                        reason="Already in history",
                        url=url,
                        offer_price=offer_price_str,
                        list_price=list_price_str,
                        discount=discount_str,
                        scraper_source="ml_offers_scraper"
                    )
                    continue

                # Filtro 2: Descuento insuficiente (badge)
                if disc > 0 and disc < MIN_DISCOUNT_PCT:
                    log_discarded_product(
                        product_id=product_id,
                        title=title,
                        reason=f"Discount too low: {disc}%",
                        details={"discount_badge": disc, "minimum": MIN_DISCOUNT_PCT},
                        url=url,
                        offer_price=offer_price_str,
                        list_price=list_price_str,
                        discount=discount_str,
                        scraper_source="ml_offers_scraper"
                    )
                    continue

                # Filtro 3: Validación de keywords y blacklist
                if not is_valid_product(title, product_id, url, offer_price_str, list_price_str, discount_str):
                    continue

                # Filtro 4: Ahorro en pesos insuficiente
                if price and orig:
                    try:
                        ahorro = int(orig) - int(price)
                        if ahorro < 100:
                            log_discarded_product(
                                product_id=product_id,
                                title=title,
                                reason=f"Savings too low: ${ahorro}",
                                details={"savings": ahorro, "minimum": 100},
                                url=url,
                                offer_price=offer_price_str,
                                list_price=list_price_str,
                                discount=discount_str,
                                scraper_source="ml_offers_scraper"
                            )
                            continue
                    except:
                        pass

                # Filtro 5: Calcular descuento si no vino del badge
                if disc == 0 and price and orig:
                    try:
                        pct = int(round((1 - int(price) / int(orig)) * 100))
                        if pct < MIN_DISCOUNT_PCT:
                            discount_str = f"{pct}% OFF"
                            log_discarded_product(
                                product_id=product_id,
                                title=title,
                                reason=f"Discount too low: {pct}%",
                                details={"calculated_discount": pct, "minimum": MIN_DISCOUNT_PCT},
                                url=url,
                                offer_price=offer_price_str,
                                list_price=list_price_str,
                                discount=discount_str,
                                scraper_source="ml_offers_scraper"
                            )
                            continue
                        disc = pct
                    except:
                        continue

                found.append({
                    "id": product_id,
                    "title": title,
                    "offer_price": offer_price_str,
                    "list_price": list_price_str,
                    "discount": f"{disc}% OFF",
                    "image_url": item.get("image_url", ""),
                    "affiliate_url": url,
                    "screenshot": ""
                })
                print(f"   ✅ {disc}% | {title[:50]}")

        await context.close()
        await browser.close()

    # Guardar en la cola para publicación posterior
    existing = json_load(OUTPUT_FILE, default=[])
    if not isinstance(existing, list):
        existing = []

    existing_ids = {p.get("id") for p in existing}
    nuevos = [p for p in found if p["id"] not in existing_ids]
    existing = nuevos + existing

    json_save_atomic(OUTPUT_FILE, existing, indent=2, ensure_ascii=False)

    # Notificar a Telegram con los links crudos
    await send_tg_results(found)

    # Notificar resumen de descartados
    await send_discard_summary()

    # Notificar fin del scraper con estadísticas
    await send_scraper_status_message("end", products_found=len(found))

    print(f"\n--- FINALIZADO: {len(found)} ofertas de tecnología con {MIN_DISCOUNT_PCT}%+ encontradas ---")


async def send_scraper_status_message(status: str, products_found: int = 0):
    """Envía notificación de inicio/fin del scraper a Telegram."""
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    try:
        if status == "start":
            msg = f"🚀 *Scraper iniciando* — Buscando ofertas con {MIN_DISCOUNT_PCT}%+ de descuento..."
        elif status == "end":
            msg = f"✅ *Scraper finalizado*\n✅ *{products_found}* productos encontrados y agregados a la cola"
        else:
            return

        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"[WARN] Error enviando estado de scraper a Telegram: {e}")


async def send_discard_summary():
    """Envía a Telegram un resumen de productos descartados en el scraper actual."""
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    from core.discard_logger import get_discarded_products

    try:
        result = get_discarded_products(days=1)
        total_discarded = result.get("total", 0)

        if total_discarded == 0:
            return

        reasons = result.get("summary", {})

        # Construir mensaje de resumen
        msg_lines = [
            "🔍 *Resumen de Descartados*",
            f"❌ Total: *{total_discarded}* productos descartados",
            "",
            "📊 *Desglose por Razón:*",
        ]

        # Ordenar por cantidad descendente
        sorted_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
        for reason, count in sorted_reasons:
            msg_lines.append(f"  • {reason}: *{count}*")

        msg_lines.extend([
            "",
            "📋 [Ver todos los descartados en el panel](https://gangasmx.com/panel/descartados)",
        ])

        msg = "\n".join(msg_lines)

        import aiohttp
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"[WARN] Error enviando resumen de descartados a Telegram: {e}")


async def send_tg_results(products):
    token   = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    import aiohttp
    import sys
    sys.path.append('.')
    from core.telegram_bot import TelegramBot
    dummy_bot = TelegramBot(token, chat_id, None)
    kb = dummy_bot.get_master_keyboard()

    if not products:
        msg = f"🔍 *Scraper finalizado* — No se encontraron ofertas destacadas con {MIN_DISCOUNT_PCT}%+ de descuento."
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "reply_markup": kb})
        return

    # Enviar en bloques de 5 para no saturar
    header = (f"🛍️ *{len(products)} oferta(s) destacada(s) encontrada(s)* "
              f"(+{MIN_DISCOUNT_PCT}% descuento)\n"
              f"Genera los links de afiliado y pégalos al bot:\n\n")

    lines = []
    for p in products:
        lines.append(
            f"*{p['discount']}* — {p['title'][:45]}\n"
            f"{p['list_price']} → {p['offer_price']}\n"
            f"`{p['affiliate_url']}`"
        )

    # Partir en mensajes de máx 10 productos
    chunk_size = 10
    for i in range(0, len(lines), chunk_size):
        chunk = lines[i:i + chunk_size]
        text = (header if i == 0 else "") + "\n\n".join(chunk)
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        
        # Solo adjuntamos el teclado al último mensaje
        if i + chunk_size >= len(lines):
            payload["reply_markup"] = kb
            
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
        await asyncio.sleep(1)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(run_production())
