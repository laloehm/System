import asyncio
import os
from playwright.async_api import async_playwright

FLOW_PROJECT_URL = os.getenv("FLOW_PROJECT_URL", "https://labs.google/fx/es/tools/flow/project/1b646f0a-d51f-4e6e-aa45-df47289da97f")
CDP_PORT = os.getenv("CHROME_CDP_PORT", "9222")

async def generate_flow_images(prompts: list[str], base_output_path: str) -> list[str]:
    """
    Automatiza Google Labs Flow para generar múltiples imágenes secuencialmente.
    Intenta primero conectarse a un Chrome activo vía CDP (puerto 9222) para reusar la sesión activa.
    Si no hay Chrome CDP, lanza un contexto persistente.
    """
    print(f"[FLOW] Iniciando generación de {len(prompts)} imágenes...")
    
    user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow_chrome_profile")
    output_paths = []
    
    async with async_playwright() as p:
        browser = None
        is_cdp = False
        page = None
        
        try:
            # 1. Intentar conectar a Chrome activo con CDP en puerto 9222
            try:
                print(f"[FLOW] Intentando conectar a Chrome activo vía CDP en http://127.0.0.1:{CDP_PORT}...")
                browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}", timeout=3000)
                is_cdp = True
                print("[FLOW] ✅ ¡Conectado con éxito a Chrome activo por CDP!")
                context = browser.contexts[0]
                
                # Buscar si ya hay pestaña con labs.google
                for p_tab in context.pages:
                    if "labs.google" in p_tab.url:
                        page = p_tab
                        print(f"[FLOW] Usando pestaña activa existente: {page.url}")
                        break
                        
                if not page:
                    page = await context.new_page()
                    print(f"[FLOW] Abriendo nueva pestaña en Chrome CDP hacia: {FLOW_PROJECT_URL}")
                    await page.goto(FLOW_PROJECT_URL, timeout=60000)
            except Exception as cdp_err:
                print(f"[FLOW] Chrome CDP no disponible ({cdp_err}). Lanzando nuevo navegador persistente...")
                browser = None
                
            if not browser:
                # Lanzar contexto persistente
                print("[FLOW] Lanzando Chrome con perfil persistente...")
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"],
                    permissions=["clipboard-read", "clipboard-write"]
                )
                page = await browser.new_page()
                print(f"[FLOW] Navegando a {FLOW_PROJECT_URL}...")
                await page.goto(FLOW_PROJECT_URL, timeout=60000)
            
            # Esperar a que cargue la interfaz
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
            except:
                pass
            await asyncio.sleep(2)
            
            input_selector = 'div[data-slate-editor="true"], [contenteditable="true"], textarea'
            submit_selector = 'button:has(i:text-is("arrow_forward"))'
            card_selector = 'div[data-index="0"][data-item-index="0"] > div > div:nth-child(1) img'
            
            for idx, prompt in enumerate(prompts):
                output_path = f"{base_output_path}_{idx+1}.png"
                print(f"[FLOW] Generando imagen {idx+1}/{len(prompts)}: '{prompt[:40]}...'")
                
                await page.wait_for_selector(input_selector, timeout=20000)
                await page.focus(input_selector)
                await page.click(input_selector, force=True)
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                
                try:
                    await page.evaluate(f"navigator.clipboard.writeText({repr(prompt)})")
                    await page.keyboard.press("Control+V")
                except:
                    await page.keyboard.type(prompt, delay=5)
                    
                await asyncio.sleep(0.5)
                
                try:
                    await page.locator(submit_selector).first.click(timeout=3000)
                except:
                    await page.press(input_selector, "Enter")
                    
                print("[FLOW] Generando imagen en la nube (esperando max 45s)...")
                
                try:
                    await page.wait_for_selector(card_selector, timeout=45000)
                    img_locator = page.locator(card_selector).first
                    await img_locator.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)
                    await img_locator.click(button="right", force=True, position={"x": 50, "y": 50})
                    await asyncio.sleep(1.5)
                    
                    download_button_selector = 'i.google-symbols:has-text("download")'
                    try:
                        await page.locator(download_button_selector).first.hover(timeout=2000)
                        await asyncio.sleep(0.5)
                    except:
                        pass
                    
                    await page.locator(download_button_selector).first.click(force=True)
                    await asyncio.sleep(1.5)
                    
                    async with page.expect_download(timeout=12000) as download_info:
                        one_k_selector = 'button[role="menuitem"]:has-text("1K"), button.sc-16c4830a-1:has-text("1K")'
                        await page.click(one_k_selector, force=True)
                    download = await download_info.value
                    
                    await download.save_as(output_path)
                    print(f"[FLOW] ✅ [EXITO] Imagen {idx+1} generada y guardada en: {output_path}")
                    output_paths.append(output_path)
                    
                except Exception as e:
                    print(f"[FLOW] ⚠️ Error en descarga de imagen {idx+1}: {e}")
                    print(f"[FLOW] Fallback: Tomando screenshot SOLO de la imagen generada...")
                    img_locator = page.locator(card_selector).first
                    if await img_locator.count() > 0:
                        await img_locator.screenshot(path=output_path)
                        output_paths.append(output_path)
                        print(f"[FLOW] ✅ [EXITO] Imagen {idx+1} extraída mediante screenshot del elemento.")
                    else:
                        print(f"[FLOW] ❌ Fallo total en la imagen {idx+1}.")
            
            await browser.close()
            return output_paths

        except Exception as e:
            print(f"[FLOW] ❌ Error general durante la generación: {e}")
            if 'browser' in locals():
                await browser.close()
            return output_paths

async def generate_flow_image(prompt: str, output_path: str) -> bool:
    """Wrapper para backward compatibility"""
    base = output_path.rsplit('.', 1)[0]
    res = await generate_flow_images([prompt], base)
    if res:
        import shutil
        shutil.move(res[0], output_path)
        return True
    return False

if __name__ == "__main__":
    # Prueba rápida
    test_prompt = "A cute small dog wearing a hat"
    test_output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_flow.png")
    asyncio.run(generate_flow_image(test_prompt, test_output))
