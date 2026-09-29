"""
affiliate_linker.py
Convierte URLs raw de MercadoLibre en links de afiliado (meli.la/*)
usando el linkbuilder web con la sesion guardada en storage_state.json.

Uso:
  python affiliate_linker.py              -> procesa productos pendientes en products_list.json
  python affiliate_linker.py URL1 URL2    -> procesa URLs especificas y las imprime
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from playwright.async_api import async_playwright
from core.storage import json_load, json_save_atomic
from core.session_manager import SessionManager

STORAGE_STATE = SessionManager.get_storage_state()
PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "products_list.json")
DRAFTS_FILE   = os.path.join(os.path.dirname(__file__), "products_draft.json")
LOGS_DIR      = os.path.join(os.path.dirname(__file__), "logs")
LINKBUILDER   = "https://www.mercadolibre.com.mx/afiliados/linkbuilder#hub"
MAX_BATCH     = 30

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

os.makedirs(LOGS_DIR, exist_ok=True)

EXTRACT_JS = """() => {
    const found = new Set();
    document.querySelectorAll('a[href*="meli.la"]').forEach(el => found.add(el.href));
    document.querySelectorAll('input[value*="meli.la"]').forEach(el => found.add(el.value));
    document.querySelectorAll('textarea').forEach(el => {
        const val = el.value || el.innerText || '';
        val.split(/[\\n,\\s]+/).forEach(tok => {
            if (tok.includes('meli.la')) found.add(tok.trim());
        });
    });
    const bodyText = document.body.innerText || '';
    const matches = bodyText.match(/https?:\\/\\/meli\\.la\\/\\S+/g) || [];
    matches.forEach(m => found.add(m.replace(/[,)>'\"]+$/, '')));
    return [...found];
}"""

RESULT_LINES_JS = """() => {
    const candidates = [...document.querySelectorAll('textarea')]
        .map(el => (el.value || el.innerText || '').trim())
        .filter(value => value.includes('meli.la') || /URL no (esta|es)/i.test(value));
    if (!candidates.length) {
        const bodyText = document.body.innerText || '';
        const found = bodyText.match(/https?:\\/\\/meli\\.la\\/\\S+/g) || [];
        return found.map(m => m.replace(/[,)>'\"]+$/, ''));
    }
    return candidates[candidates.length - 1]
        .split(/\\r?\\n/)
        .map(line => line.trim())
        .filter(line => line && !/campo est[aá] vac[ií]o/i.test(line));
}"""


def load_products(products_file=PRODUCTS_FILE):
    if not os.path.exists(products_file):
        return []
    return json_load(products_file, default=[])


def save_products(products, products_file=PRODUCTS_FILE):
    json_save_atomic(products_file, products, indent=2, ensure_ascii=False)


def needs_affiliate(p):
    url = p.get("affiliate_url", "")
    return (
        bool(url)
        and "meli.la" not in url
        and "mercadolibre" in url
        and p.get("affiliate_status") != "rejected"
    )


def map_result_lines(urls, result_lines):
    clean_lines = [l for l in result_lines if not re.search(r"campo est[aá] vac[ií]o", l, re.IGNORECASE)]
    
    # 1. Caso exacto de líneas alineadas con URLs
    if len(clean_lines) == len(urls):
        mapping = {}
        for original_url, result_line in zip(urls, clean_lines):
            match = re.search(r"https?://meli\.la/[^\s]+", result_line)
            mapping[original_url] = match.group(0).rstrip(",)>'\"") if match else None
        return mapping

    # 2. Si enviamos 1 sola URL y encontramos al menos un link meli.la en el resultado
    meli_matches = []
    for line in clean_lines:
        m = re.search(r"https?://meli\.la/[^\s]+", line)
        if m:
            meli_matches.append(m.group(0).rstrip(",)>'\""))

    if len(urls) == 1 and meli_matches:
        return {urls[0]: meli_matches[0]}

    # 3. Si la cantidad de links meli.la coincide exactamente con la cantidad de URLs
    if len(meli_matches) == len(urls):
        return dict(zip(urls, meli_matches))

    return None


async def run_linkbuilder(urls: list, headless: bool = False) -> dict:
    """
    Abre el linkbuilder, pega las URLs, extrae SOLO los links nuevos generados.
    Retorna {url_original: url_afiliado}.
    """
    mapping = {}
    ts = int(datetime.now().timestamp())

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            storage_state=STORAGE_STATE,
            viewport={"width": 1400, "height": 900},
            user_agent=UA
        )
        page = await context.new_page()

        print("  Abriendo linkbuilder...")
        await page.goto(LINKBUILDER, wait_until="load", timeout=60000)
        await page.wait_for_timeout(3000)

        current_url = page.url
        print(f"  URL: {current_url}")
        if "login" in current_url or "lgz" in current_url:
            print("  AVISO: sesion expirada. Ejecuta manual_login.py y vuelve a intentar.")
            await browser.close()
            return {}

        # Ubicar el textarea de entrada
        textarea = page.locator("textarea.andes-form-control__field--multiline").first
        try:
            await textarea.wait_for(state="visible", timeout=10000)
        except Exception:
            await page.screenshot(path=os.path.join(LOGS_DIR, f"lb_no_textarea_{ts}.png"))
            print("  AVISO: textarea no encontrado. Screenshot guardado.")
            await browser.close()
            return {}

        # Capturar links que ya existen en el DOM (historial de sesion del servidor)
        links_before = set(await page.evaluate(EXTRACT_JS))
        print(f"  Links previos en DOM (historial): {len(links_before)}")

        clean_urls = [u.strip() for u in urls if u and u.strip().startswith("http")]
        if not clean_urls:
            print("  AVISO: No hay URLs válidas para procesar.")
            await browser.close()
            return {}
        urls = clean_urls

        # Pegar las URLs (una por línea) SIN salto de línea final adicional
        await textarea.click()
        await textarea.fill("")
        await textarea.fill("\n".join(urls))
        print(f"  OK: {len(urls)} URL(s) pegadas")

        btn = page.locator("button.andes-button--loud").filter(has_text="Generar")
        await btn.click()
        print("  Generando links...")

        # Esperar a que aparezcan exactamente N links nuevos (max 15s)
        expected_total = len(links_before) + len(urls)
        try:
            await page.wait_for_function(
                f"() => (document.body.innerText.match(/https?:\\/\\/meli\\.la\\/\\S+/g) || []).length >= {expected_total}",
                timeout=15000
            )
        except Exception:
            print("  AVISO: timeout esperando resultados, leyendo lo disponible...")
        await page.wait_for_timeout(500)

        # Screenshot
        shot_path = os.path.join(LOGS_DIR, f"lb_result_{ts}.png")
        await page.screenshot(path=shot_path, full_page=True)
        print(f"  Screenshot: {shot_path}")

        # Conservar tambien las lineas de error: la salida mantiene una linea
        # por URL y permite mapear sin desplazar resultados parciales.
        try:
            result_lines = await page.evaluate(RESULT_LINES_JS)
        except Exception as e:
            print(f"  AVISO: no se pudo leer result_lines ({e}), usando fallback new_links")
            result_lines = []

        # Obtener SOLO los links nuevos (diferencia con los previos)
        all_links_now = await page.evaluate(EXTRACT_JS)
        new_links = [lnk for lnk in all_links_now if lnk not in links_before]

        print(f"  Links nuevos generados: {len(new_links)}")
        for lnk in new_links:
            print(f"    {lnk}")

        aligned_mapping = map_result_lines(urls, result_lines)
        if aligned_mapping is not None:
            mapping.update(aligned_mapping)
            for orig, affiliate_url in aligned_mapping.items():
                if not affiliate_url:
                    print(f"  OMITIDO por LinkBuilder: {orig}")
        elif len(new_links) == len(urls):
            # Caso ideal: mapeo en orden 1-a-1
            for orig, aff in zip(urls, new_links):
                mapping[orig] = aff
        elif len(urls) == 1:
            # Fallback 1-a-1 para 1 sola URL
            recent_melis = [lnk for lnk in all_links_now if "meli.la" in lnk]
            if recent_melis:
                mapping[urls[0]] = recent_melis[-1]
                print(f"  Fallback 1-URL detectó: {recent_melis[-1]}")
        elif new_links:
            print(
                f"  AVISO: salida parcial no alineada ({len(new_links)}/{len(urls)}). "
                "No se guardara ningun enlace ambiguo."
            )
        else:
            # Debug fallback
            html_snippet = await page.evaluate("""() => {
                const el = document.querySelector('main') || document.body;
                return el.innerHTML.substring(0, 3000);
            }""")
            debug_path = os.path.join(LOGS_DIR, f"lb_html_{ts}.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html_snippet)
            print(f"  AVISO: no se generaron links. HTML guardado en: {debug_path}")

        await context.close()
        await browser.close()

    return mapping


async def main(headless: bool = False, limit: int | None = None, products_file=PRODUCTS_FILE):
    # Modo CLI: URLs como argumentos
    if len(sys.argv) > 1:
        raw_args = sys.argv[1:]
        headless = "--no-headless" not in raw_args
        urls = [a.strip() for a in raw_args if not a.startswith("--") and a.strip().startswith("http")]
        if urls:
            print(f"Procesando {len(urls)} URL(s) desde argumentos (headless={headless})...")
            mapping = await run_linkbuilder(urls, headless=headless)
            if mapping:
                print("\nResultados:")
                for orig, aff in mapping.items():
                    if aff:
                        print(f"  {aff}")
            return

    # Modo automatico: leer products_list.json
    products = load_products(products_file)
    pending = [p for p in products if needs_affiliate(p)]

    if not pending:
        print("No hay productos pendientes de conversion a link afiliado.")
        return 0

    if limit is not None:
        pending = pending[:max(0, limit)]
    if not pending:
        print("Limite diario configurado en 0. No se procesaron enlaces.")
        return 0

    print(f"Productos a procesar en esta ejecucion: {len(pending)}")
    urls_pending = [p["affiliate_url"] for p in pending]

    updated = 0
    for i in range(0, len(urls_pending), MAX_BATCH):
        batch = urls_pending[i:i + MAX_BATCH]
        lote  = i // MAX_BATCH + 1
        print(f"\n-- Lote {lote}: {len(batch)} URL(s) --")
        mappings = await run_linkbuilder(batch, headless=headless)
        if mappings:
            batch_updated = 0
            batch_rejected = 0
            for prod in products:
                original_url = prod.get("affiliate_url", "")
                if original_url in mappings:
                    affiliate_url = mappings[original_url]
                    if affiliate_url:
                        prod["affiliate_url"] = affiliate_url
                        prod.pop("affiliate_status", None)
                        prod.pop("affiliate_error", None)
                        if prod.get("source") == "apify":
                            prod.pop("review_status", None)
                        batch_updated += 1
                        print(f"  OK: {prod['id']} -> {affiliate_url}")
                    else:
                        prod["affiliate_status"] = "rejected"
                        prod["affiliate_error"] = "URL rechazada por LinkBuilder"
                        if prod.get("source") == "apify":
                            prod["review_status"] = "needs_review"
                            prod["confidence_score"] = 0
                            prod["confidence_reasons"] = ["URL rechazada por LinkBuilder"]
                        batch_rejected += 1
            if batch_updated or batch_rejected:
                save_products(products, products_file)
                updated += batch_updated
                print(
                    f"  Progreso guardado: {updated} enlace(s), "
                    f"{batch_rejected} rechazado(s) en este lote."
                )
        if i + MAX_BATCH < len(urls_pending):
            await asyncio.sleep(2)

    if not updated:
        print("\nNo se generaron links. Revisa los screenshots en logs/")
        return 0

    print(f"\nListo: {updated} producto(s) actualizados en {products_file}")
    return updated


if __name__ == "__main__":
    asyncio.run(main())
