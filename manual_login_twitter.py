import asyncio
import os
import platform
from playwright.async_api import async_playwright
from core.config import Config

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def manual_login_twitter():
    async with async_playwright() as p:
        print("=== INICIANDO SESIÓN MANUAL EN TWITTER / X (MODO STEALTH) ===")

        launch_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--start-maximized"
        ]

        browser = None
        try:
            # Intentar lanzar usando Chrome instalado para evitar bloqueos de bot
            browser = await p.chromium.launch(channel="chrome", headless=False, args=launch_args, ignore_default_args=["--enable-automation"])
            print("🌐 Iniciando con Google Chrome oficial...")
        except Exception:
            browser = await p.chromium.launch(headless=False, args=launch_args, ignore_default_args=["--enable-automation"])
            print("🌐 Iniciando con Chromium...")

        state_file = Config.STORAGE_PATH
        tw_state_file = os.path.join(Config.BASE_DIR, "storage_state_twitter.json")
        existing_state = tw_state_file if os.path.exists(tw_state_file) else (state_file if os.path.exists(state_file) else None)

        context = await browser.new_context(
            storage_state=existing_state,
            viewport=None,
            user_agent=UA
        )

        page = await context.new_page()
        # Ocultar indicador de automatización
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        await page.goto("https://x.com/i/flow/login")

        print("\n👉 1. Inicia sesión con tu usuario/correo y contraseña en la ventana del navegador.")
        print("👉 2. Si te pide verificación de 2 pasos o correo, complétala normalmente.")
        print("👉 3. Cuando llegues al inicio de X (https://x.com/home), CIERRA LA VENTANA para guardar la sesión.\n")

        while len(context.pages) > 0:
            try:
                await asyncio.sleep(1)
            except Exception:
                break

        await context.storage_state(path=tw_state_file)
        print(f"💾 Sesión de Twitter guardada exitosamente en: {tw_state_file}")

        if os.path.exists(state_file):
            try:
                await context.storage_state(path=state_file)
                print(f"💾 Sesión de Twitter sincronizada con: {state_file}")
            except Exception as e:
                print(f"⚠️ No se pudo sincronizar con {state_file}: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(manual_login_twitter())
