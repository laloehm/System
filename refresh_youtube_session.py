"""
refresh_youtube_session.py
Abre un navegador visible para que hagas login en YouTube Studio
y guarda la sesión en youtube_state.json.

Corre en el VPS con pantalla:
    python3 refresh_youtube_session.py
"""
import asyncio
import os
import json
from core.storage import json_load

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "youtube_state.json")


async def main():
    from playwright.async_api import async_playwright

    print("🌐 Abriendo navegador para login de YouTube...")
    print("   Inicia sesión en tu cuenta de Google/YouTube.")
    print("   Cuando estés en YouTube Studio, presiona ENTER aquí.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        existing_state = None
        if os.path.exists(STATE_FILE):
            existing_state = json_load(STATE_FILE, default=None)
            if existing_state is not None:
                print(f"ℹ️  Cargando sesión existente de {STATE_FILE}")

        context = await browser.new_context(
            storage_state=existing_state,
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()
        await page.goto("https://studio.youtube.com/")

        print("\n⏳ Navegador abierto. Inicia sesión si es necesario.")
        print("   Cuando estés dentro de YouTube Studio, presiona ENTER para guardar la sesión.")
        input()

        await context.storage_state(path=STATE_FILE)
        print(f"✅ Sesión guardada en: {STATE_FILE}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
