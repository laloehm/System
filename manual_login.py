import asyncio
from playwright.async_api import async_playwright
import os
from core.session_manager import SessionManager

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def manual_login():
    async with async_playwright() as p:
        print("--- INICIANDO SESIÓN MANUAL (CLON PERFECTO) ---")
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            storage_state=SessionManager.get_storage_state(),
            viewport={'width': 1366, 'height': 768},
            user_agent=UA
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Abrir sitios para login
        await page.goto("https://www.mercadolibre.com.mx/ofertas")
        page_aff = await context.new_page()
        await page_aff.goto("https://www.mercadolibre.com.mx/afiliados/linkbuilder#hub")
        page_fb = await context.new_page()
        await page_fb.goto("https://www.facebook.com")
        page_amz = await context.new_page()
        await page_amz.goto("https://www.amazon.com.mx")

        print("\n1. Inicia sesión en TODAS las pestañas (incluida la de Afiliados ML).")
        print("2. En la pestaña de Afiliados: asegúrate de ver el linkbuilder cargado.")
        print("3. CIERRA LA VENTANA cuando termines para guardar el archivo maestro.")
        
        while len(context.pages) > 0:
            await asyncio.sleep(1)
            
        await SessionManager.save_session(context)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(manual_login())
