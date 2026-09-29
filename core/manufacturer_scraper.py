import os
import asyncio
import urllib.parse
import urllib.request
import numpy as np
from PIL import Image
from playwright.async_api import async_playwright

# Fragmentos de URL que indican imágenes irrelevantes
_URL_BLACKLIST = (
    "logo", "icon", "sprite", "banner", "social", "avatar",
    "pixel", "tracking", "placeholder", "background", "/bg",
    "badge", "ribbon", "star", "rating", "payment", "visa",
    "mastercard", "paypal", "facebook", "instagram", "twitter",
    "whatsapp", "youtube", "tiktok", "arrow", "bullet",
)

# Selectores de contenedores donde suelen estar las fotos de producto
_PRODUCT_SELECTORS = [
    "[class*='gallery'] img",
    "[class*='product-image'] img",
    "[class*='product_image'] img",
    "[class*='carousel'] img",
    "[class*='slider'] img",
    "[class*='swiper'] img",
    "[class*='lightbox'] img",
    "[id*='gallery'] img",
    "[id*='product'] img",
    "[class*='zoom'] img",
    "[class*='media'] img",
    "picture source",  # <picture> moderno
    "picture img",
]


def _is_url_valid(url: str) -> bool:
    low = url.lower()
    return not any(kw in low for kw in _URL_BLACKLIST)


def _is_ratio_valid(w: int, h: int) -> bool:
    if h == 0:
        return False
    ratio = w / h
    return 0.35 <= ratio <= 2.8  # excluye banners muy anchos e iconos altos


def _image_is_product_photo(path: str, min_variance: float = 18.0) -> bool:
    """
    Verifica que la imagen no sea un logo de color plano ni fondo liso.
    Mide la desviación estándar de los píxeles — fotos reales tienen alta varianza.
    """
    try:
        img = Image.open(path).convert("RGB")
        arr = np.array(img).astype(float)
        variance = arr.std()
        if variance < min_variance:
            print(f"[Scraper] Descartada (imagen plana, std={variance:.1f}): {os.path.basename(path)}")
            return False
        return True
    except Exception:
        return True  # Si no se puede leer, la dejamos pasar


async def scrape_manufacturer_images(url: str, save_dir: str, min_images: int = 3) -> list:
    """
    Navega a la URL del fabricante y descarga imágenes del producto.
    Filtra logos, banners e imágenes decorativas automáticamente.
    Retorna lista de paths descargados (pueden ser menos que min_images si el sitio es restrictivo).
    """
    os.makedirs(save_dir, exist_ok=True)
    downloaded_paths = []

    print(f"[Scraper] Iniciando para: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Scroll agresivo para disparar lazy-load
            for _ in range(6):
                await page.evaluate("window.scrollBy(0, window.innerHeight);")
                await page.wait_for_timeout(700)
            await page.evaluate("window.scrollTo(0, 0);")
            await page.wait_for_timeout(800)

            # ── Paso 1: intentar extraer solo de contenedores de galería ──────
            gallery_images = await page.evaluate('''(selectors) => {
                const MIN_W = 250, MIN_H = 250;
                const results = [];
                const seen = new Set();
                for (const sel of selectors) {
                    const nodes = document.querySelectorAll(sel);
                    for (const el of nodes) {
                        const candidates = [
                            el.src,
                            el.getAttribute("data-src"),
                            el.getAttribute("data-lazy-src"),
                            el.getAttribute("data-original"),
                            el.getAttribute("data-lazy"),
                            el.getAttribute("srcset") ? el.getAttribute("srcset").split(" ")[0] : null,
                            el.getAttribute("data-zoom-image"),
                            el.getAttribute("data-large"),
                            el.getAttribute("data-full"),
                        ];
                        for (const src of candidates) {
                            if (!src || !src.startsWith("http")) continue;
                            const base = src.split("?")[0];
                            if (seen.has(base)) continue;
                            const w = el.naturalWidth || el.width || 0;
                            const h = el.naturalHeight || el.height || 0;
                            if (w < MIN_W || h < MIN_H) continue;
                            seen.add(base);
                            results.push({ src, area: w * h });
                        }
                    }
                }
                results.sort((a, b) => b.area - a.area);
                return results;
            }''', _PRODUCT_SELECTORS)

            print(f"[Scraper] {len(gallery_images)} imágenes en contenedores de galería.")

            # ── Paso 2: si no hay suficientes, ampliar a todas las imágenes ───
            if len(gallery_images) < min_images:
                all_images = await page.evaluate('''() => {
                    const MIN_W = 280, MIN_H = 280;
                    const imgs = Array.from(document.querySelectorAll("img"));
                    const results = [];
                    const seen = new Set();
                    for (const img of imgs) {
                        const src = img.src
                            || img.getAttribute("data-src")
                            || img.getAttribute("data-lazy-src")
                            || img.getAttribute("data-original")
                            || (img.getAttribute("srcset") || "").split(" ")[0];
                        if (!src || !src.startsWith("http")) continue;
                        const base = src.split("?")[0];
                        if (seen.has(base)) continue;
                        const w = img.naturalWidth || img.width || 0;
                        const h = img.naturalHeight || img.height || 0;
                        if (w < MIN_W || h < MIN_H) continue;
                        seen.add(base);
                        results.push({ src, area: w * h });
                    }
                    results.sort((a, b) => b.area - a.area);
                    return results;
                }''')
                print(f"[Scraper] Fallback: {len(all_images)} imágenes en página completa.")
                # Combinar sin duplicar
                existing_srcs = {img["src"].split("?")[0] for img in gallery_images}
                for img in all_images:
                    if img["src"].split("?")[0] not in existing_srcs:
                        gallery_images.append(img)

            # ── Paso 3: filtrar por URL y ratio de aspecto ────────────────────
            candidates = []
            for img in gallery_images:
                src = img["src"]
                if not _is_url_valid(src):
                    continue
                candidates.append(src)

            print(f"[Scraper] {len(candidates)} candidatas tras filtro de URL.")

        except Exception as e:
            print(f"[Scraper] Error Playwright: {e}")
            candidates = []
        finally:
            await browser.close()

    # ── Paso 4: descargar, validar ratio y varianza ───────────────────────────
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": url,
    }
    target = min_images * 2  # descargar el doble para tener margen de rechazo
    count = 1

    for img_url in candidates:
        if len(downloaded_paths) >= target:
            break

        raw_ext = img_url.split("?")[0].rsplit(".", 1)[-1].lower()
        ext = raw_ext if raw_ext in ("jpg", "jpeg", "png", "webp") else "jpg"
        dest = os.path.join(save_dir, f"scene_{count}.{ext}")

        try:
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()

            if len(data) < 8000:  # < 8KB → probable icono o pixel
                continue

            with open(dest, "wb") as f:
                f.write(data)

            # Validar ratio de aspecto
            try:
                img_pil = Image.open(dest)
                w, h = img_pil.size
                if not _is_ratio_valid(w, h):
                    print(f"[Scraper] Descartada (ratio {w/h:.2f}): {os.path.basename(dest)}")
                    os.remove(dest)
                    continue
            except Exception:
                pass

            # Validar que no sea imagen plana (logo, fondo liso)
            if not _image_is_product_photo(dest):
                os.remove(dest)
                continue

            downloaded_paths.append(dest)
            print(f"[Scraper] OK ({count}): {os.path.basename(dest)}")
            count += 1

        except Exception as e:
            print(f"[Scraper] Falló {img_url[:80]}: {e}")

    print(f"[Scraper] Total descargadas y validadas: {len(downloaded_paths)}")
    return downloaded_paths
