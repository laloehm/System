import asyncio
import os
from playwright.async_api import async_playwright

# Archivo donde se guardarán las cookies y el almacenamiento local de TikTok
TIKTOK_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_state.json")

async def main():
    print("🚀 Iniciando navegador para Login en TikTok...")
    print("⚠️  ATENCIÓN: Tienes 120 segundos para iniciar sesión manualmente.")
    
    async with async_playwright() as p:
        # Iniciamos el navegador de forma VISIBLE (headless=False)
        # NOTA: Si lo corres en un servidor Linux sin interfaz gráfica, esto lanzará error.
        # En ese caso, necesitarás ejecutarlo mediante XVFB o un entorno de escritorio VNC.
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        # Vamos directo a la página de login
        await page.goto("https://www.tiktok.com/login", timeout=60000)

        print("📲 Por favor, inicia sesión. Se recomienda usar la opción 'Usar código QR' y escanearlo con la app de tu celular.")
        
        # Esperamos a que el usuario confirme manualmente en la consola
        try:
            # Usar run_in_executor para no bloquear el event loop de asyncio con el input()
            await asyncio.to_thread(input, "👉 Presiona la tecla ENTER aquí en esta terminal ÚNICAMENTE cuando ya hayas iniciado sesión y veas tu perfil en el navegador...")
            print("✅ ¡Inicio de sesión confirmado por el usuario!")
        except Exception as e:
            print(f"⚠️ Error esperando confirmación: {e}")
            
        print("💾 Guardando el estado de la sesión...")
        await context.storage_state(path=TIKTOK_STATE_FILE)
        print(f"🎉 ¡Sesión guardada en {TIKTOK_STATE_FILE}!")
        print("El bot de publicación de TikTok utilizará este archivo a partir de ahora.")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
