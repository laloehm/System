"""
run_scraper_windows.py
Ejecutado automaticamente cada dia a las 8 AM por el Programador de Tareas de Windows.

Flujo:
  1. Scraper de MercadoLibre  -> products_list.json (URLs raw)
  2. Affiliate Linker          -> products_list.json (URLs meli.la)
  3. Syncthing sincroniza al servidor Linux automaticamente
  4. El scheduler del bot de Linux publica a sus horas programadas (9 AM, 1 PM, 5 PM, 10 PM)
"""
import os
import asyncio
import sys
import json
import urllib.request
import aiohttp
from core.storage import json_load, json_save_atomic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

PRODUCTS_FILE = os.path.join(BASE_DIR, "products_list.json")
DRAFTS_FILE   = os.path.join(BASE_DIR, "products_draft.json")
HISTORY_FILE  = os.path.join(BASE_DIR, "published_history.json")
BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID       = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLE_ML_SCRAPER = os.getenv("ENABLE_ML_SCRAPER", "true").strip().lower() in ("1", "true", "yes", "on")
AFFILIATE_DAILY_LIMIT = max(0, int(os.getenv("AFFILIATE_DAILY_LIMIT", "20")))


def send_telegram(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
        req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def count_queue_stats():
    """Retorna (pendientes, con_link_afiliado) leyendo products_list.json."""
    try:
        products = json_load(PRODUCTS_FILE, default=[])
    except Exception:
        return 0, 0

    history = set()
    try:
        data = json_load(HISTORY_FILE, default=[])
        if isinstance(data, list):
            history = set(data)
    except Exception:
        pass

    pending    = [p for p in products if not (p.get("id") and p["id"] in history)]
    con_link   = [p for p in pending  if "meli.la" in (p.get("affiliate_url") or "")]
    return len(pending), len(con_link)


async def run():
    errors = []
    validation_result = {"validated": 0, "approved": 0, "needs_review": 0}

    # ── PASO 1: Scraper ──────────────────────────────────────────────────────
    print("=" * 50)
    print("PASO 1: Scraper de ofertas MercadoLibre")
    print("=" * 50)
    nuevos_antes = count_queue_stats()[0]
    if ENABLE_ML_SCRAPER:
        try:
            from ml_offers_scraper import run_production
            await run_production()
            print("Scraper completado.")
        except Exception as e:
            errors.append(f"Scraper: {e}")
            print(f"Error en scraper: {e}")
    else:
        print("Scraper pausado por ENABLE_ML_SCRAPER=false.")

    nuevos_despues = count_queue_stats()[0]
    nuevos_encontrados = max(0, nuevos_despues - nuevos_antes)

    # ── PASO 1.5: Descargar imágenes localmente ──────────────────────────────
    print()
    print("=" * 50)
    print("PASO 1.5: Descarga de imágenes")
    print("=" * 50)
    img_cache_dir = os.path.join(BASE_DIR, "image_cache")
    os.makedirs(img_cache_dir, exist_ok=True)
    try:
        prods = json_load(PRODUCTS_FILE, default=[])

        img_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.mercadolibre.com.mx/"
        }
        sem = asyncio.Semaphore(5)

        async def download_one(session, prod):
            pid      = prod.get("id", "")
            img_url  = prod.get("image_url", "")
            existing = prod.get("screenshot", "")
            if not pid or not img_url or not img_url.startswith("http"):
                return False, False
            if existing and not existing.startswith("image_cache"):
                return False, False
            ext      = ".webp" if ".webp" in img_url else ".jpg"
            dest_rel = f"image_cache/{pid}{ext}"
            dest_abs = os.path.join(BASE_DIR, dest_rel)
            path_updated = prod.get("screenshot") != dest_rel
            if path_updated:
                prod["screenshot"] = dest_rel
            if os.path.exists(dest_abs):
                return False, path_updated
            async with sem:
                try:
                    async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                        if r.status == 200:
                            with open(dest_abs, "wb") as fh:
                                fh.write(await r.read())
                            print(f"  OK: {dest_rel}")
                            return True, path_updated
                except Exception as e:
                    print(f"  Error {pid}: {e}")
            return False, path_updated

        async with aiohttp.ClientSession(headers=img_headers) as session:
            results = await asyncio.gather(*[download_one(session, p) for p in prods])

        descargadas   = sum(1 for downloaded, _ in results if downloaded)
        prods_updated = any(updated for _, updated in results)

        if prods_updated:
            json_save_atomic(PRODUCTS_FILE, prods, indent=2, ensure_ascii=False)

        print(f"Imágenes descargadas: {descargadas}")
    except Exception as e:
        errors.append(f"Descarga imágenes: {e}")
        print(f"Error en descarga de imágenes: {e}")

    # ── PASO 2: Affiliate Linker (DESACTIVADO para evitar cerrar sesión en Windows)
    # print()
    # print("=" * 50)
    # print("PASO 2: Generacion de links de afiliado")
    # print("=" * 50)
    # try:
    #     from affiliate_linker import main as run_linker
    #     generated = await run_linker(
    #         headless=True,
    #         limit=AFFILIATE_DAILY_LIMIT,
    #         products_file=DRAFTS_FILE,
    #     )
    #     print(f"Links de afiliado generados hoy: {generated}/{AFFILIATE_DAILY_LIMIT}.")
    # except Exception as e:
    #     errors.append(f"Affiliate linker: {e}")
    #     print(f"Error en affiliate linker: {e}")

    print()
    print("=" * 50)
    print("PASO 3: Validacion de confianza")
    print("=" * 50)
    try:
        from product_confidence import validate_drafts
        validation_result = await validate_drafts(
            drafts_path=DRAFTS_FILE,
            queue_path=PRODUCTS_FILE,
            headless=True,
            limit=AFFILIATE_DAILY_LIMIT,
        )
        print(
            f"Validados: {validation_result['validated']} | "
            f"Auto-aprobados: {validation_result['approved']} | "
            f"Revision: {validation_result['needs_review']}"
        )
    except Exception as e:
        errors.append(f"Validacion: {e}")
        print(f"Error en validacion de confianza: {e}")

    _, con_link = count_queue_stats()

    # ── Notificación resumen a Telegram ──────────────────────────────────────
    lines = ["*Rutina diaria completada* (8 AM Windows)"]

    if not ENABLE_ML_SCRAPER:
        lines.append("Scraper de ofertas: *PAUSADO*")
    elif nuevos_encontrados > 0:
        lines.append(f"Nuevos productos scrapeados: *{nuevos_encontrados}*")
    else:
        lines.append("Sin productos nuevos encontrados hoy")

    lines.append(f"En cola con link afiliado: *{con_link}*")
    lines.append(f"Aprobados automaticamente hoy: *{validation_result['approved']}*")
    lines.append(f"Necesitan revision: *{validation_result['needs_review']}*")

    if errors:
        lines.append("")
        lines.append("*Errores:*")
        for err in errors:
            lines.append(f"- {err[:120]}")
    else:
        lines.append("Sin errores")

    send_telegram("\n".join(lines))
    print()
    print("Listo. Syncthing sincronizara products_list.json al servidor Linux.")


if __name__ == "__main__":
    asyncio.run(run())
