"""
Rellena automáticamente las colas desde Apify cuando bajan de MIN_QUEUE_SIZE productos listos.
Se llama desde el scheduler como tarea de fondo — no bloquea los slots de publicación.
"""

import asyncio
import json
import os
import re
from datetime import datetime, timedelta

from core.config import Config
from core.storage import json_load, json_save_atomic

def get_scraping_keyword(niche: str, default: str) -> str:
    import random
    path = os.path.join(Config.BASE_DIR, "scraping_config.json")
    
    # Map old english niche tags to new spanish keys in json
    alias_map = {"baby": "bebes", "pets": "mascotas", "general": "general", "tenis": "tenis", "moda": "moda"}
    json_key = alias_map.get(niche, niche)

    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                val = data.get(json_key)
                if isinstance(val, dict):
                    terms = val.get("search_terms", [])
                    if terms:
                        return random.choice(terms)
                    return default
                elif isinstance(val, str):
                    return val
                return os.getenv(f"APIFY_KEYWORD_{niche.upper()}", default)
    except Exception as e:
        print(f"[APIFY] Error leyendo scraping_config.json: {e}")
    return os.getenv(f"APIFY_KEYWORD_{niche.upper()}", default)

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "karamelo~mercadolibre-scraper-espanol-castellano"
COUNTRY_MX = "https://listado.mercadolibre.com.mx/"
MIN_QUEUE_SIZE = 10
COOLDOWN_HOURS = 4

FIELD_MAP = {
    "id": "SKU",
    "title": "articuloTitulo",
    "offer_price": "nuevoPrecio",
    "list_price": "precioAnterior",
    "discount": "precioDiscount",
    "image_url": "imgDireccion",
    "affiliate_url": "zProductoLink",
}

NICHE_CONFIG = {
    "general": {
        "keyword": lambda: get_scraping_keyword("general", "tecnologia"),
        "queue_file": lambda: Config.JSON_QUEUE_FILE,
        "niche_tag": "[CAT:GENERAL]",
    },
    "baby": {
        "keyword": lambda: get_scraping_keyword("baby", "bebes"),
        "queue_file": lambda: Config.JSON_QUEUE_BABY_FILE,
        "niche_tag": "baby",
    },
    "pets": {
        "keyword": lambda: get_scraping_keyword("pets", "perros"),
        "queue_file": lambda: Config.JSON_QUEUE_PETS_FILE,
        "niche_tag": "pets",
    },
    "tenis": {
        "keyword": lambda: get_scraping_keyword("tenis", "tenis deportivos"),
        "queue_file": lambda: getattr(Config, "JSON_QUEUE_TENIS_FILE", os.path.join(Config.BASE_DIR, "queue_tenis.json")),
        "niche_tag": "[CAT:TENIS]",
    },
    "moda": {
        "keyword": lambda: get_scraping_keyword("moda", "ropa moda"),
        "queue_file": lambda: getattr(Config, "JSON_QUEUE_MODA_FILE", os.path.join(Config.BASE_DIR, "queue_moda.json")),
        "niche_tag": "[CAT:MODA]",
    },
}

_last_refill: dict[str, datetime] = {}


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _normalize_price(value) -> str:
    price = _clean(value)
    if not price:
        return ""
    price = re.sub(r"\s*(MXN|M\.N\.)\s*", "", price, flags=re.IGNORECASE).strip()
    return price if price.startswith("$") else f"${price}"


def _normalize_discount(value) -> str:
    discount = _clean(value).upper()
    match = re.search(r"\d+(?:[.,]\d+)?\s*%", discount)
    return f"{match.group(0).replace(' ', '')} OFF" if match else discount


def _normalize_id(value, url) -> str:
    for candidate in (_clean(value).upper(), url.upper()):
        match = re.search(r"MLM(U)?-?(\d+)", candidate)
        if match:
            prefix = "MLMU" if match.group(1) else "MLM"
            return f"{prefix}{match.group(2)}"
    return ""


def _count_ready(queue_file: str, history: set) -> int:
    products = json_load(queue_file, default=[])
    if not isinstance(products, list):
        return 0
    return sum(
        1 for p in products
        if p.get("affiliate_url")
        and not ((p.get("id") and p["id"] in history) or
                 (p.get("affiliate_url") and p["affiliate_url"] in history))
    )


async def _run_actor_with_fallback(keyword: str, tokens: list, max_pages: int = 2) -> list:
    last_error = None
    for token in tokens:
        try:
            return await _run_actor(keyword, token, max_pages)
        except Exception as e:
            print(f"[APIFY] Token falló ({str(e)[:60]}). Probando siguiente token...")
            last_error = e
    raise last_error or RuntimeError("No hay tokens Apify disponibles")


async def _run_actor(keyword: str, token: str, max_pages: int) -> list:
    import aiohttp
    headers = {"Authorization": f"Bearer {token}"}
    actor_input = {"keyword": keyword, "country": COUNTRY_MX, "maxPages": max_pages, "maxItems": 100}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(
            f"{APIFY_BASE}/acts/{ACTOR_ID}/runs",
            json=actor_input,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json()
            run_id = data.get("data", {}).get("id")
            if not run_id:
                raise RuntimeError(f"No se obtuvo run ID de Apify: {data}")

        print(f"[APIFY] Run iniciado: {run_id}")

        for _ in range(90):
            await asyncio.sleep(10)
            async with session.get(
                f"{APIFY_BASE}/actor-runs/{run_id}",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                run_data = (await resp.json()).get("data", {})
                status = run_data.get("status")
                if status == "SUCCEEDED":
                    break
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    raise RuntimeError(f"Actor de Apify terminó con status: {status}")
        else:
            raise RuntimeError("Timeout esperando al actor de Apify (15 min)")

        async with session.get(
            f"{APIFY_BASE}/actor-runs/{run_id}/dataset/items",
            params={"format": "json"},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            items = await resp.json()
            return items if isinstance(items, list) else []


def _import_items(items: list, niche_tag: str, queue_file: str, history: set) -> dict:
    queue = json_load(queue_file, default=[])
    if not isinstance(queue, list):
        queue = []

    known_ids = {_clean(p.get("id")) for p in queue if isinstance(p, dict)}
    known_urls = {_clean(p.get("affiliate_url")) for p in queue if isinstance(p, dict)}

    imported, skipped_discount, skipped_dupe, skipped_invalid = [], 0, 0, 0

    for record in items:
        if not isinstance(record, dict):
            continue

        product_url = _clean(record.get(FIELD_MAP["affiliate_url"]))
        image_url = _clean(record.get(FIELD_MAP["image_url"]))
        discount_raw = _normalize_discount(record.get(FIELD_MAP["discount"]))

        # Obtener valores en pesos para la validación estricta desde el Panel Web
        ahorro_pesos = 0
        disc_match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", discount_raw)
        disc_val_pct = float(disc_match.group(1).replace(",", ".")) if disc_match else 0.0

        from core.utils import parse_price_pesos
        try:
            offer_price_raw = _normalize_price(record.get(FIELD_MAP["offer_price"]))
            list_price_raw = _normalize_price(record.get(FIELD_MAP["list_price"]))
            o_val_check = parse_price_pesos(offer_price_raw)
            l_val_check = parse_price_pesos(list_price_raw)
            if l_val_check > o_val_check:
                ahorro_pesos = l_val_check - o_val_check
            elif o_val_check > 0 and disc_val_pct > 0:
                est_l_val = o_val_check / (1.0 - (disc_val_pct / 100.0))
                ahorro_pesos = est_l_val - o_val_check
        except Exception:
            pass

        dyn_config = Config.get_dynamic_config()
        min_ahorro_estricto = dyn_config.get('min_strict', dyn_config.get('min_strict_savings', 100))
        min_price = float(getattr(Config, 'MIN_PRICE', 100.0))
        max_price = dyn_config.get('max_price', 15000.0)

        is_approved = False
        if o_val_check >= min_price and (max_price <= 0 or o_val_check <= max_price):
            if ahorro_pesos >= min_ahorro_estricto:
                is_approved = True

        if not is_approved:
            skipped_discount += 1
            # Registrar en descartados
            try:
                discarded_file = os.path.join(Config.BASE_DIR, "discarded_products.json")
                discarded = json_load(discarded_file, default=[])
                
                # Para evitar duplicados en el cementerio, verificar si ya está
                prod_id_check = _normalize_id(record.get(FIELD_MAP["id"]), product_url)
                if not any(d.get("id") == prod_id_check for d in discarded):
                    record_to_save = {
                        "id": prod_id_check,
                        "title": _clean(record.get(FIELD_MAP["title"])),
                        "offer_price": offer_price_raw if 'offer_price_raw' in locals() else "",
                        "list_price": list_price_raw if 'list_price_raw' in locals() else "",
                        "discount": discount_raw,
                        "image_url": image_url,
                        "affiliate_url": product_url,
                        "discard_reason": f"Apify: Ahorro insuficiente (${ahorro_pesos:.2f} < ${min_ahorro_estricto:.2f})",
                        "discard_date": __import__('datetime').datetime.now().isoformat()
                    }
                    discarded.insert(0, record_to_save)
                    # Limitar a los ultimos 500 para que no crezca infinito
                    discarded = discarded[:500]
                    json_save_atomic(discarded_file, discarded, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Error guardando producto descartado: {e}")
            continue

        product_id = _normalize_id(record.get(FIELD_MAP["id"]), product_url)
        title = _clean(record.get(FIELD_MAP["title"]))
        offer_price = _normalize_price(record.get(FIELD_MAP["offer_price"]))

        if not all([product_id, title, offer_price, product_url, image_url]):
            skipped_invalid += 1
            continue

        if product_id in known_ids or product_url in known_urls:
            skipped_dupe += 1
            continue
            
        # Evaluar si es Oferta Estrella
        is_exceptional = False
        disc_val = 0.0
        if disc_match:
            try:
                disc_val = float(disc_match.group(1).replace(",", "."))
            except: pass
            
        if disc_val >= 40.0:
            is_exceptional = True
            
        list_price_str = _normalize_price(record.get(FIELD_MAP["list_price"]))
        try:
            o_val = parse_price_pesos(offer_price)
            l_val = parse_price_pesos(list_price_str)
            if (l_val - o_val) >= 500.0:
                is_exceptional = True
        except: pass

        # Verificar si ya fue descartado
        from core.discard_manager import is_already_discarded
        if is_already_discarded(product_id):
            skipped_dupe += 1
            continue

        if product_id in history or product_url in history:
            if is_exceptional:
                title = f"🔥 [OFERTA ESTRELLA] {title}"
            else:
                skipped_dupe += 1
                continue

        product = {
            "id": product_id,
            "title": title,
            "offer_price": offer_price,
            "list_price": list_price_str,
            "discount": discount_raw,
            "image_url": image_url,
            "affiliate_url": product_url,
            "niche": niche_tag,
            "source": "apify",
            "review_status": "pending_affiliate",
        }

        queue.append(product)
        imported.append(product)
        known_ids.add(product_id)
        known_urls.add(product_url)

    if imported:
        # ACTUALIZACIÓN SEGURA CONTRA RACE CONDITIONS:
        # Recargamos la cola actual desde el disco justo antes de guardar,
        # para no sobreescribir productos manuales añadidos mientras el scraper corría.
        current_queue = json_load(queue_file, default=[])
        current_queue.extend(imported)
        json_save_atomic(queue_file, current_queue, indent=2, ensure_ascii=False)

    return {
        "imported": len(imported),
        "products": imported,
        "skipped_discount": skipped_discount,
        "skipped_dupe": skipped_dupe,
        "skipped_invalid": skipped_invalid,
    }


async def _check_amazon_refill(orchestrator, history: set, now: datetime, status: dict, force: bool = False) -> None:
    """Rellena la cola general con productos de Amazon cuando baja de MIN_QUEUE_SIZE."""
    if not status.get("amazon", True) and not force:
        return

    last = _last_refill.get("amazon")
    if last and (now - last) < timedelta(hours=COOLDOWN_HOURS) and not force:
        return

    ready = _count_ready(Config.JSON_QUEUE_FILE, history)
    if ready >= MIN_QUEUE_SIZE and not force:
        return

    print(f"[AMAZON REFILL] Cola general tiene {ready} productos. Scrapeando Amazon...")
    if orchestrator.telegram_bot:
        await orchestrator.telegram_bot.send_notification(
            f"🛒 *Amazon Refill*\nCola general baja ({ready} productos). Scrapeando ofertas de Amazon..."
        )

    try:
        from scrapers.amazon_deals_linux import run as amazon_run
        notify_fn = orchestrator.telegram_bot.send_notification if orchestrator.telegram_bot else None
        count = await amazon_run(notify_fn=notify_fn)
        _last_refill["amazon"] = now

        if orchestrator.telegram_bot:
            await orchestrator.telegram_bot.send_notification(
                f"✅ *Amazon Refill completado*\n"
                f"📦 {count} productos nuevos en cola general\n"
                f"🔗 Links de afiliado generados automáticamente con `?tag=`"
            )
    except Exception as e:
        print(f"[AMAZON REFILL] Error: {e}")
        if orchestrator.telegram_bot:
            await orchestrator.telegram_bot.send_notification(
                f"❌ *Amazon Refill falló*\n`{str(e)[:120]}`"
            )


async def check_and_refill(orchestrator, force: bool = False) -> None:
    print(f"\n[REFILL DEBUG] Iniciando check_and_refill (force={force})")
    tokens = Config.get_apify_tokens()
    print(f"[REFILL DEBUG] Tokens Apify disponibles: {len(tokens)}")

    from core.history_manager import load_recent_history
    history = load_recent_history()
    now = datetime.now()

    status_file = os.path.join(Config.BASE_DIR, "scraper_status.json")
    scraper_status = json_load(status_file, default={})
    print(f"[REFILL DEBUG] Scraper status: {scraper_status}")

    # Refill Amazon (cola general, sin necesidad de token Apify)
    print(f"[REFILL DEBUG] Llamando _check_amazon_refill...")
    await _check_amazon_refill(orchestrator, history, now, scraper_status, force=force)
    print(f"[REFILL DEBUG] check_and_refill completado\n")

    if not tokens:
        return

    for niche, cfg in NICHE_CONFIG.items():
        if not scraper_status.get(niche, True):
            continue

        last = _last_refill.get(niche)
        if last and (now - last) < timedelta(hours=COOLDOWN_HOURS) and not force:
            continue

        queue_file = cfg["queue_file"]()
        ready = _count_ready(queue_file, history)

        if ready >= MIN_QUEUE_SIZE and not force:
            continue

        keyword = cfg["keyword"]()

        # Leer configuración de páginas a escrapear
        scraping_config = json_load(os.path.join(Config.BASE_DIR, "scraping_config.json"), default={})
        max_pages = int(scraping_config.get("amazon_pages", 2))

        print(f"[APIFY REFILL] Cola '{niche}' tiene {ready} productos listos. Keyword: {keyword}")

        if orchestrator.telegram_bot:
            await orchestrator.telegram_bot.send_notification(
                f"🔄 *Apify Refill — {niche}*\n"
                f"Cola baja ({ready} productos). Importando con `{keyword}` ({max_pages} páginas)..."
            )

        try:
            
            items = await _run_actor_with_fallback(keyword, tokens, max_pages)
            result = _import_items(items, cfg["niche_tag"], queue_file, history)
            _last_refill[niche] = now
            
            # --- AUTO-LINKER INTEGRATION ---
            imported_products = result.get("products", [])
            auto_success = 0
            auto_failed = 0
            urls_to_link = [p.get("affiliate_url") for p in imported_products if p.get("affiliate_url") and "mercadolibre.com.mx" in p.get("affiliate_url") and "meli.la" not in p.get("affiliate_url")]
            
            if urls_to_link:
                if orchestrator.telegram_bot:
                    await orchestrator.telegram_bot.send_notification(
                        f"⚙️ Generando {len(urls_to_link)} links meli\\.la para {niche} en servidor..."
                    )
                
                import affiliate_linker
                mapping = {}
                for i in range(0, len(urls_to_link), 15):
                    batch = urls_to_link[i:i+15]
                    batch_mapping = await affiliate_linker.run_linkbuilder(batch, headless=True)
                    if batch_mapping:
                        mapping.update(batch_mapping)
                    else:
                        for url_single in batch:
                            single_map = await affiliate_linker.run_linkbuilder([url_single], headless=True)
                            if single_map:
                                mapping.update(single_map)
                
                
                if mapping:
                    # ACTUALIZACIÓN SEGURA: Recargar la cola actual desde disco para no sobreescribir
                    # productos manuales que hayan sido añadidos durante la afiliación.
                    current_queue = json_load(queue_file, default=[])
                    
                    for p in imported_products:
                        orig_url = p.get("affiliate_url", "")
                        new_url = mapping.get(orig_url)
                        if new_url:
                            p["affiliate_url"] = new_url
                            p.pop("review_status", None)
                            auto_success += 1
                            # Update in the actual saved queue array
                            for q_prod in current_queue:
                                if q_prod.get("id") == p.get("id"):
                                    q_prod["affiliate_url"] = new_url
                                    q_prod.pop("review_status", None)
                                    break
                    
                    if auto_success > 0:
                        json_save_atomic(queue_file, current_queue, indent=2, ensure_ascii=False)
                    
                    auto_failed = len(urls_to_link) - auto_success
                else:
                    auto_failed = len(urls_to_link)
            # -------------------------------

            msg = (
                f"✅ *Apify Refill completado — {niche}*\n"
                f"📦 Importados: *{result['imported']}*\n"
                f"🔗 Auto-Afiliados: *{auto_success}* (Listos)\n"
                f"⚠️ Fallidos: *{auto_failed}*\n"
                f"⏭️ Duplicados omitidos: {result['skipped_dupe']}\n"
                f"📉 Sin descuento suficiente: {result['skipped_discount']}"
            )
            if orchestrator.telegram_bot:
                await orchestrator.telegram_bot.send_notification(msg)
                
                # Solo notificar individualmente a los fallidos
                for prod in imported_products:
                    if "meli.la" not in prod.get("affiliate_url", ""):
                        title = prod.get("title", "")[:50]
                        ml_url = prod.get("affiliate_url", "")
                        await asyncio.sleep(0.4)
                        await orchestrator.telegram_bot.send_notification(
                            f"🔗 *Falló auto-afiliación \\[{niche}\\]*\n"
                            f"📦 `{title}`\n"
                            f"{ml_url}\n"
                            f"_Responde con el link meli\\.la_"
                        )

        except Exception as e:
            print(f"[APIFY REFILL] Error en '{niche}': {e}")
            if orchestrator.telegram_bot:
                await orchestrator.telegram_bot.send_notification(
                    f"❌ *Apify Refill falló ({niche})*\n`{str(e)[:120]}`"
                )
