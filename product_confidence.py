"""Valida productos de Mercado Libre y separa aprobados de revisiones."""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from core.storage import json_load, json_save_atomic


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DRAFTS = BASE_DIR / "products_draft.json"
DEFAULT_QUEUE = BASE_DIR / "products_list.json"
AUTO_APPROVE_SCORE = 90

STOPWORDS = {
    "a", "al", "con", "de", "del", "el", "en", "la", "las", "los",
    "o", "para", "por", "un", "una", "y",
}


def parse_price(value) -> float | None:
    text = str(value or "").strip()
    if not text or "ver precio" in text.lower():
        return None
    cleaned = re.sub(r"[^0-9.,]", "", text)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1 and len(cleaned.rsplit(",", 1)[1]) == 2:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def title_similarity(left: str, right: str) -> float:
    def tokens(value):
        return {
            token for token in re.findall(r"[a-z0-9]+", value.lower())
            if len(token) > 1 and token not in STOPWORDS
        }

    left_tokens = tokens(left or "")
    right_tokens = tokens(right or "")
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    sequence = SequenceMatcher(None, (left or "").lower(), (right or "").lower()).ratio()
    return round(max(overlap, sequence), 3)


def discount_is_coherent(list_price, offer_price, discount) -> bool:
    original = parse_price(list_price)
    offer = parse_price(offer_price)
    if not original or not offer or original <= offer:
        return False
    expected = round((original - offer) / original * 100)
    match = re.search(r"\d+", str(discount or ""))
    return bool(match) and abs(expected - int(match.group(0))) <= 3


def evaluate_confidence(product: dict, live: dict) -> dict:
    score = 0
    reasons = []
    affiliate_url = str(product.get("affiliate_url", ""))
    if "meli.la" in affiliate_url:
        score += 10
    else:
        reasons.append("Falta enlace meli.la")

    redirected = bool(live.get("is_redirected_to_lists"))
    if not redirected:
        score += 10
    else:
        reasons.append("El enlace redirige a una lista o producto no disponible")

    similarity = title_similarity(product.get("title", ""), live.get("title", ""))
    if similarity >= 0.70:
        score += 35
    elif similarity >= 0.50:
        score += 25
        reasons.append(f"Coincidencia de titulo media ({similarity:.0%})")
    else:
        reasons.append(f"Coincidencia de titulo baja ({similarity:.0%})")

    live_price = parse_price(live.get("offer_price"))
    if live_price and live_price > 0:
        score += 25
    else:
        reasons.append("No se pudo confirmar el precio actual")

    image_url = str(live.get("image_url") or "")
    if image_url.startswith(("http://", "https://")):
        score += 15
    else:
        reasons.append("No se pudo confirmar la imagen")

    if discount_is_coherent(live.get("list_price"), live.get("offer_price"), live.get("discount")):
        score += 5
    else:
        reasons.append("Descuento sin confirmacion matematica")

    hard_failure = redirected or similarity < 0.50 or not live_price
    approved = score >= AUTO_APPROVE_SCORE and not hard_failure
    return {
        "score": score,
        "approved": approved,
        "title_similarity": similarity,
        "reasons": reasons,
    }


def apply_live_data(product: dict, live: dict) -> None:
    product["title"] = live.get("title") or product.get("title", "")
    product["offer_price"] = live.get("offer_price") or product.get("offer_price", "")
    product["list_price"] = live.get("list_price") or product.get("list_price", "")
    product["discount"] = live.get("discount") or product.get("discount", "")
    product["image_url"] = live.get("image_url") or product.get("image_url", "")


async def scrape_live_product(page, url: str) -> dict:
    await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    await page.wait_for_timeout(1500)
    data = await page.evaluate("""() => {
        const text = (selector) => {
            const element = document.querySelector(selector);
            return element ? (element.innerText || '').trim() : '';
        };
        const meta = (selector) => {
            const element = document.querySelector(selector);
            return element ? (element.getAttribute('content') || '') : '';
        };
        const cleanPrice = (element) => element ? element.innerText.replace(/[^0-9]/g, '') : '';
        const offer = document.querySelector('.ui-pdp-price__second-line .andes-money-amount__fraction') ||
                      document.querySelector('.poly-price__current .andes-money-amount__fraction') ||
                      document.querySelector('.andes-money-amount__main .andes-money-amount__fraction');
        let original = document.querySelector('s .andes-money-amount__fraction') ||
                       document.querySelector('.andes-money-amount--previous .andes-money-amount__fraction') ||
                       document.querySelector('.poly-price__original .andes-money-amount__fraction');
        if (offer && original && offer === original) original = null;
        const image = document.querySelector('.ui-pdp-gallery__figure img') ||
                      document.querySelector('.poly-component__picture img') ||
                      document.querySelector('figure img');
        return {
            title: text('h1.ui-pdp-title') || text('.ui-pdp-title') ||
                   text('.poly-component__title') || text('h1') || text('h2') ||
                   meta('meta[property="og:title"]'),
            offer: cleanPrice(offer),
            list: cleanPrice(original),
            discount: text('.andes-money-amount__discount') ||
                      text('.ui-pdp-color--GREEN') || text('.poly-price__disc'),
            image: (image && image.src) || meta('meta[property="og:image"]')
        };
    }""")
    return {
        "title": data.get("title", ""),
        "offer_price": f"${data['offer']}" if data.get("offer") else "",
        "list_price": f"${data['list']}" if data.get("list") else "",
        "discount": data.get("discount", ""),
        "image_url": data.get("image", ""),
        "final_url": page.url,
        "is_redirected_to_lists": not data.get("title") or not data.get("offer"),
    }


async def validate_drafts(
    drafts_path: Path = DEFAULT_DRAFTS,
    queue_path: Path = DEFAULT_QUEUE,
    headless: bool = True,
    limit: int | None = None,
) -> dict:
    from playwright.async_api import async_playwright

    drafts_path = Path(drafts_path)
    queue_path = Path(queue_path)

    drafts = json_load(drafts_path, default=[]) if drafts_path.exists() else []
    queue = json_load(queue_path, default=[]) if queue_path.exists() else []
    candidates = [
        product for product in drafts
        if product.get("source") == "apify"
        and product.get("review_status") == "pending_validation"
        and "meli.la" in str(product.get("affiliate_url", ""))
    ]
    if limit is not None:
        candidates = candidates[:max(0, limit)]

    approved_ids = []
    review_ids = []
    known_queue_ids = {product.get("id") for product in queue}

    if candidates:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless, args=["--no-sandbox"])
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            )
            try:
                semaphore = asyncio.Semaphore(3)

                async def validate_one(product):
                    async with semaphore:
                        page = await context.new_page()
                        try:
                            live = await asyncio.wait_for(
                                scrape_live_product(page, product["affiliate_url"]),
                                timeout=35,
                            )
                            result = evaluate_confidence(product, live)
                            if result["title_similarity"] >= 0.50:
                                apply_live_data(product, live)
                            product["confidence_score"] = result["score"]
                            product["confidence_reasons"] = result["reasons"]
                            product["validated_at"] = datetime.now(timezone.utc).isoformat()
                            if result["approved"]:
                                product["review_status"] = "approved_auto"
                                if product.get("id") not in known_queue_ids:
                                    queue.append(product)
                                    known_queue_ids.add(product.get("id"))
                                approved_ids.append(product.get("id"))
                            else:
                                product["review_status"] = "needs_review"
                                review_ids.append(product.get("id"))
                        except Exception as exc:
                            product["confidence_score"] = 0
                            product["confidence_reasons"] = [f"Error de validacion: {str(exc)[:120]}"]
                            product["review_status"] = "needs_review"
                            review_ids.append(product.get("id"))
                        finally:
                            await page.close()

                await asyncio.gather(*(validate_one(product) for product in candidates))
            finally:
                await context.close()
                await browser.close()

    approved_set = set(approved_ids)
    remaining_drafts = [product for product in drafts if product.get("id") not in approved_set]
    if candidates:
        json_save_atomic(str(drafts_path), remaining_drafts, indent=2, ensure_ascii=False)
        json_save_atomic(str(queue_path), queue, indent=2, ensure_ascii=False)

    return {
        "validated": len(candidates),
        "approved": len(approved_ids),
        "needs_review": len(review_ids),
        "approved_ids": approved_ids,
        "review_ids": review_ids,
    }
