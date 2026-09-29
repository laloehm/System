import core.force_ipv4  # noqa: E402 - debe importarse antes de cualquier llamada de red

import asyncio
import argparse
import sys
import os

import datetime

class DualLogger(object):
    def __init__(self, filename="bot.log"):
        self.terminal = sys.stdout
        self.log = open(filename, "a", encoding="utf-8")
        self.at_line_start = True

    def write(self, message):
        if not message:
            return
        lines = message.splitlines(True)
        for line in lines:
            if self.at_line_start and line != '\n':
                ts = datetime.datetime.now().strftime("[%I:%M:%S %p] ")
                self.terminal.write(ts)
                self.log.write(ts)
            self.terminal.write(line)
            self.log.write(line)
            self.at_line_start = line.endswith('\n')
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = DualLogger()
sys.stderr = sys.stdout
sys.stdout.terminal.reconfigure(encoding='utf-8')
from playwright.async_api import async_playwright

from core.config import Config
from core.session_manager import SessionManager
from core.orchestrator import Orchestrator
from core.scheduler import Scheduler
from core.telegram_bot import TelegramBot

async def api_supervisor():
    """Vigila que la API de FastAPI en el puerto 8001 esté siempre activa.
    Si se cae o fue cerrada, la levanta automáticamente en segundo plano."""
    import socket
    import subprocess

    def is_api_alive(port=8001):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                return s.connect_ex(('127.0.0.1', port)) == 0
        except Exception:
            return False

    await asyncio.sleep(5)
    while True:
        try:
            if not is_api_alive(8001):
                print("[SUPERVISOR API] Puerto 8001 inactivo. Intentando restaurar gangas_api...")
                restored = False
                try:
                    subprocess.run(["systemctl", "start", "gangas_api.service"], capture_output=True, timeout=3)
                    await asyncio.sleep(3)
                    if is_api_alive(8001):
                        print("[SUPERVISOR API] gangas_api restaurado exitosamente vía systemctl.")
                        restored = True
                except Exception:
                    pass

                if not restored and not is_api_alive(8001):
                    cmd = [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "api.main:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "8001"
                    ]
                    proc = subprocess.Popen(
                        cmd,
                        cwd=Config.BASE_DIR,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    print(f"[SUPERVISOR API] gangas_api iniciado directamente en subproceso PID {proc.pid}")
                    await asyncio.sleep(5)
        except Exception as e:
            print(f"[SUPERVISOR API] Excepción en supervisor: {e}")
        await asyncio.sleep(20)

async def main():
    parser = argparse.ArgumentParser(description="Afiliados Bot Master Orchestrator")
    parser.add_argument("url", nargs="?", help="URL de Amazon o ML para publicar manualmente")
    parser.add_argument("--schedule", action="store_true", help="Activar vigilante de JSON y Telegram")
    parser.add_argument("--headless", action="store_true", help="Argumento heredado para compatibilidad de servicio")
    parser.add_argument("--visible", action="store_true", help="Ejecutar con navegador visible (debug)")
    parser.add_argument("--dry-run", action="store_true", help="Simular sin publicar")
    parser.add_argument("--login", action="store_true", help="Modo gestión de sesiones")
    
    args = parser.parse_args()

    # 1. Modo Login (Gestión de Sesiones)
    if args.login:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
            context = await browser.new_context(
                storage_state=SessionManager.get_storage_state(),
                viewport={"width": 1920, "height": 1080}
            )
            pages = [await context.new_page() for _ in range(4)]
            urls = ["https://amazon.com.mx", "https://facebook.com", "https://mercadolibre.com.mx", "https://pinterest.com"]
            for page, url in zip(pages, urls): await page.goto(url)
            
            print("--- 🔐 MODO LOGIN ---")
            print("Inicia sesión en lo que falte y CIERRA el navegador para guardar.")
            try: await pages[0].wait_for_timeout(3600000)
            except: pass
            await SessionManager.save_session(context)
            await browser.close()
        return

    # 2. Inicializar Componentes
    orchestrator = Orchestrator(headless=not args.visible, dry_run=args.dry_run)
    telegram = TelegramBot(Config.BOT_TOKEN, Config.CHAT_ID, orchestrator)
    orchestrator.telegram_bot = telegram # Vinculación bidireccional
    scheduler = Scheduler(orchestrator)

    # 3. Modo Manual (URL directa)
    if args.url:
        print(f"🚀 Ejecutando publicación manual para: {args.url}")
        await orchestrator.run_publication(args.url)
        return

    # 4. Modo Producción (Schedule + Telegram + Supervisor API)
    if args.schedule:
        print("Inyectando bot en modo PRODUCCION...")

        await asyncio.gather(
            telegram.listener(),
            scheduler.run_worker(),
            api_supervisor()
        )
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot detenido por el usuario.")
        sys.exit(0)
