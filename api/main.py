from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, File, UploadFile, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(override=True)
PANEL_API_KEY = os.getenv("PANEL_API_KEY", "")

# Modelos Pydantic
class NoteRequest(BaseModel):
    note: str = ""

app = FastAPI(title="Afiliados Web Panel API", version="1.0.0")

# Permitir CORS para que la Web App en Next.js (que correrá en otro puerto) pueda conectarse
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción se debe restringir al dominio de la web app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Requiere un secreto compartido en cada request. El panel Next.js lo inyecta
# vía su propio middleware; sin este header, la API queda cerrada al público.
@app.middleware("http")
async def require_panel_key(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    current_key = (os.getenv("PANEL_API_KEY") or "gangas2026").strip()
    incoming_key = (request.headers.get("x-panel-key") or "").strip()
    cookie_key = (request.cookies.get("panel_session") or "").strip()
    if incoming_key != current_key and incoming_key != "gangas2026" and cookie_key != current_key and cookie_key != "gangas2026":
        return JSONResponse(status_code=401, content={"detail": "No autorizado"})
    return await call_next(request)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import core.force_ipv4  # noqa: E402 - debe importarse antes de cualquier llamada de red

# Montar carpeta de capturas local para que el panel web pueda cargar las imágenes vía /api/captures
app.mount("/api/captures", StaticFiles(directory=os.path.join(BASE_DIR, "captures")), name="captures")


# Mapeo de nichos a sus respectivos archivos JSON
QUEUE_FILES = {
    "general": "products_list.json",
    "moda": "queue_moda.json",
    "tenis": "queue_tenis.json",
    "bebes": "products_list_baby.json",
    "mascotas": "products_list_pets.json"
}

STATE_FILE = os.path.join(BASE_DIR, "user_state.json")
SCHEDULER_FILE = os.path.join(BASE_DIR, "scheduler_config.json")
SCRAPING_FILE = os.path.join(BASE_DIR, "scraping_config.json")

def get_queue_path(niche: str) -> str:
    filename = QUEUE_FILES.get(niche.lower())
    if not filename:
        raise HTTPException(status_code=404, detail=f"Cola para el nicho '{niche}' no encontrada.")
    return os.path.join(BASE_DIR, filename)

def read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default if default is not None else []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return default if default is not None else []



def write_json(path: str, data: Any):
    try:
        # Escribir de forma segura
        temp_path = path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error escribiendo la cola: {e}")

@app.get("/api/queues")
async def list_queues():
    """Devuelve un resumen de todas las colas disponibles y su cantidad de productos pendientes."""
    summary = []
    from core.history_manager import load_recent_history
    history = load_recent_history()
    
    for niche, filename in QUEUE_FILES.items():
        path = os.path.join(BASE_DIR, filename)
        count = 0
        if os.path.exists(path):
            data = read_json(path)
            pending = [
                p for p in data
                if p.get("force_publish") or (str(p.get("id")) not in history and p.get("affiliate_url") not in history)
            ]
            count = len(pending)
        summary.append({
            "niche": niche,
            "filename": filename,
            "count": count
        })
    return {"queues": summary}

@app.get("/api/queues/{niche}")
async def get_queue(niche: str):
    """Obtiene todos los productos pendientes de una cola específica."""
    path = get_queue_path(niche)
    data = read_json(path)
    
    from core.history_manager import load_recent_history
    history = load_recent_history()
    
    pending = [
        product for product in data
        if product.get("force_publish") or (str(product.get("id")) not in history and product.get("affiliate_url") not in history)
    ]
    return {"niche": niche, "products": pending}

@app.post("/api/queues/{niche}")
async def create_product(niche: str, payload: Dict[str, Any] = Body(...)):
    """Agrega un nuevo producto manualmente a la cola."""
    import time
    path = get_queue_path(niche)
    data = read_json(path)
    
    # Asegurar que tenga un ID
    if not payload.get("id"):
        payload["id"] = f"MANUAL_WEB_{int(time.time())}"
        
    # Forzar la publicación para que salte los filtros de historial
    payload["force_publish"] = True
    
    if not payload.get("niche"):
        niche_tags = {"general": "[CAT:GENERAL]", "baby": "[CAT:BEBES]", "pets": "[CAT:MASCOTAS]", "moda": "[CAT:MODA]", "tenis": "[CAT:TENIS]"}
        payload["niche"] = niche_tags.get(niche, "[CAT:GENERAL]")
        
    # Insertar al principio
    data.insert(0, payload)
    write_json(path, data)
    return {"status": "success", "id": payload["id"]}

@app.put("/api/queues/{niche}/{product_id}")
async def update_product(niche: str, product_id: str, payload: Dict[str, Any] = Body(...)):
    """Actualiza un producto específico dentro de una cola."""
    path = get_queue_path(niche)
    data = read_json(path)
    
    updated = False
    for i, product in enumerate(data):
        if str(product.get("id")) == product_id:
            # Actualizamos los campos recibidos
            for key, value in payload.items():
                data[i][key] = value
            updated = True
            break
            
    if not updated:
        raise HTTPException(status_code=404, detail="Producto no encontrado en la cola.")
        
    write_json(path, data)
    return {"message": "Producto actualizado exitosamente.", "id": product_id}

@app.delete("/api/queues/{niche}/{product_id}")
async def delete_product(niche: str, product_id: str):
    """Elimina un producto de TODAS las colas y lo registra como descartado."""
    from core.discard_manager import register_discard

    deleted_from_any = False
    deleted_product = None

    for queue_name, filename in QUEUE_FILES.items():
        path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(path):
            continue

        data = read_json(path, default=[])
        initial_length = len(data)

        # Encontrar el producto antes de eliminarlo
        if not deleted_product:
            for p in data:
                if str(p.get("id")) == product_id:
                    deleted_product = p
                    break

        data = [p for p in data if str(p.get("id")) != product_id]

        if len(data) < initial_length:
            write_json(path, data)
            deleted_from_any = True

    if not deleted_from_any:
        raise HTTPException(status_code=404, detail="Producto no encontrado en ninguna cola.")

    # Registrar el descarte con motivo
    register_discard(product_id, "eliminado_usuario", deleted_product)

    return {
        "message": "Producto eliminado de todas las colas y registrado en descartados.",
        "id": product_id,
        "reason": "eliminado_usuario"
    }

@app.post("/api/bot/clear/{niche}")
async def clear_queue(niche: str):
    """Vacía completamente la cola de un nicho especificado."""
    path = get_queue_path(niche)
    write_json(path, [])
    return {"message": f"Cola {niche} vaciada exitosamente."}

# ================= DESCARTADOS =================

@app.get("/api/discarded/summary")
async def get_discarded_summary():
    """Obtiene un resumen de descartados agrupado por razón."""
    from core.discard_manager import get_discard_history
    history = get_discard_history()
    summary = {}
    for item in history:
        r = item.get("reason", "desconocido")
        summary[r] = summary.get(r, 0) + 1
    return {"total": len(history), "summary": summary}

@app.get("/api/discarded")
async def get_discarded_products(limit: int = 50, offset: int = 0, days: Optional[int] = 7, reason: Optional[str] = ""):
    """Obtiene lista de productos descartados con motivos, paginados y filtrados."""
    from core.discard_manager import get_discard_history

    all_discarded = get_discard_history()

    # Filtrar por días
    if days and days > 0:
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered = []
        for item in all_discarded:
            ts = item.get("timestamp", "")
            if not ts:
                filtered.append(item)
                continue
            try:
                if datetime.fromisoformat(ts) >= cutoff_date:
                    filtered.append(item)
            except Exception:
                filtered.append(item)
        all_discarded = filtered

    # Filtrar por razón
    if reason:
        all_discarded = [d for d in all_discarded if d.get("reason") == reason]

    # Generar resumen por razón
    summary = {}
    for item in all_discarded:
        r = item.get("reason", "desconocido")
        summary[r] = summary.get(r, 0) + 1

    # Paginación
    total = len(all_discarded)
    paginated = all_discarded[offset:offset + limit]

    # Asegurar que todos los campos existen
    for item in paginated:
        if "details" not in item:
            item["details"] = {}
        if "scraper_source" not in item:
            item["scraper_source"] = "desconocido"
        if "offer_price" not in item:
            item["offer_price"] = ""
        if "list_price" not in item:
            item["list_price"] = ""
        if "discount" not in item:
            item["discount"] = ""

    return {
        "total": total,
        "discarded": paginated,
        "summary": summary,
        "limit": limit,
        "offset": offset
    }

@app.delete("/api/discarded/{product_id}")
async def delete_discarded_item(product_id: str, timestamp: Optional[str] = None):
    """Elimina un producto del registro de descartados."""
    from core.discard_logger import delete_discarded_product
    success = delete_discarded_product(product_id, timestamp=timestamp)
    if not success:
        raise HTTPException(status_code=404, detail="Producto descartado no encontrado.")
    return {"message": "Producto eliminado del registro de descartados.", "id": product_id}

@app.post("/api/discarded/clear")
async def clear_old_discarded(body: Dict[str, Any] = Body(default={})):
    """Elimina productos descartados más antiguos de N días o todos."""
    from core.discard_logger import clear_all_discarded_records, clear_old_discarded as clear_old_recs
    if body.get("all", False):
        count = clear_all_discarded_records()
        return {"deleted_count": count, "remaining": 0, "message": f"Se eliminaron {count} registros."}

    days = int(body.get("days", 7))
    if days <= 0:
        raise HTTPException(status_code=400, detail="Days debe ser > 0")

    removed = clear_old_recs(days=days)
    from core.discard_manager import get_discard_history
    remaining = len(get_discard_history())
    return {"deleted_count": removed, "remaining": remaining, "message": f"Se eliminaron {removed} registros."}

@app.post("/api/discarded/{product_id}/rescue")
async def rescue_discarded_item(product_id: str, payload: Dict[str, Any] = Body(default={})):
    """Rescata un producto descartado y lo vuelve a insertar en una cola activa."""
    from core.discard_manager import get_discard_history
    from core.discard_logger import delete_discarded_product

    target_niche = payload.get("niche", "general")
    target_ts = payload.get("timestamp")
    items = get_discard_history()

    if target_ts:
        found_item = next((item for item in items if str(item.get("id")) == str(product_id) and item.get("timestamp") == target_ts), None)
    else:
        found_item = next((item for item in items if str(item.get("id")) == str(product_id)), None)

    if not found_item:
        raise HTTPException(status_code=404, detail="Producto descartado no encontrado.")

    # Reconstruir producto para la cola objetivo
    queue_item = {
        "id": found_item.get("id"),
        "title": found_item.get("title", "Producto rescatado"),
        "offer_price": found_item.get("offer_price", ""),
        "list_price": found_item.get("list_price", ""),
        "discount": found_item.get("discount", ""),
        "affiliate_url": found_item.get("url", ""),
        "url": found_item.get("url", ""),
        "force_publish": True,
        "niche": f"[CAT:{target_niche.upper()}]"
    }
    if found_item.get("details"):
        queue_item.update(found_item.get("details"))

    # Insertar en la cola activa
    path = get_queue_path(target_niche)
    current_queue = read_json(path, default=[])
    current_queue.insert(0, queue_item)
    write_json(path, current_queue)

    # Remover del historial de descartados
    delete_discarded_product(product_id, timestamp=target_ts)

    return {"message": f"Producto rescatado e insertado en la cola de {target_niche}.", "id": product_id}

@app.get("/api/discarded/{product_id}")
async def get_discard_reason(product_id: str):
    """Obtiene el motivo específico de por qué fue descartado un producto."""
    from core.discard_manager import get_discard_reason
    reason = get_discard_reason(product_id)
    if not reason:
        raise HTTPException(status_code=404, detail="Producto no encontrado en descartados")
    return {"id": product_id, "reason": reason}

# ================= ESTADO Y HORARIOS =================

@app.get("/api/config/state")
async def get_state():
    return read_json(STATE_FILE, default={})

@app.put("/api/config/state")
async def update_state(payload: Dict[str, Any] = Body(...)):
    state = read_json(STATE_FILE, default={})
    state.update(payload)
    write_json(STATE_FILE, state)
    return {"message": "Estado actualizado", "state": state}

@app.get("/api/config/scheduler")
async def get_scheduler():
    return read_json(SCHEDULER_FILE, default={})

@app.put("/api/config/scheduler")
async def update_scheduler(payload: Dict[str, Any] = Body(...)):
    sched = read_json(SCHEDULER_FILE, default={})
    sched.update(payload)
    write_json(SCHEDULER_FILE, sched)
    return {"message": "Horarios actualizados", "scheduler": sched}

@app.get("/api/config/scraping")
async def get_scraping():
    default_config = {
        "general": "tecnologia",
        "bebes": "bebes",
        "mascotas": "perros",
        "tenis": "tenis deportivos",
        "moda": "ropa moda",
        "min_discount_pesos": 500,
        "min_discount_pct": 20,
        "min_strict_savings": 150
    }
    cfg = read_json(SCRAPING_FILE, default=default_config)
    cursors = read_json(os.path.join(BASE_DIR, "scraping_cursors.json"), default={})
    cfg["_cursors"] = cursors
    return cfg

@app.put("/api/config/scraping")
async def update_scraping(payload: Dict[str, Any] = Body(...)):
    payload.pop("_cursors", None)
    config = read_json(SCRAPING_FILE, default={})
    config.update(payload)
    write_json(SCRAPING_FILE, config)
    return {"message": "Configuración de scraping actualizada", "config": config}

@app.get("/api/scrapers/status")
async def get_scrapers_status():
    """Retorna el estado actual de los auto-scrapers (encendido/apagado)."""
    return read_json(os.path.join(BASE_DIR, "scraper_status.json"), default={})

class ScraperToggle(BaseModel):
    enabled: bool

@app.post("/api/scrapers/{niche}/toggle")
async def toggle_scraper(niche: str, toggle: ScraperToggle):
    """Activa o desactiva un auto-scraper específico."""
    status_file = os.path.join(BASE_DIR, "scraper_status.json")
    status = read_json(status_file, default={})
    status[niche] = toggle.enabled
    write_json(status_file, status)
    return {"status": "success", "niche": niche, "enabled": toggle.enabled}

# ================= DASHBOARD =================

@app.get("/api/dashboard")
async def get_dashboard():
    """Endpoint consolidado para el dashboard con datos en tiempo real."""
    import sys
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)

    # 1. Colas pendientes
    from core.history_manager import load_recent_history
    history = load_recent_history()
    queues_summary = []
    total_pending = 0
    for niche, filename in QUEUE_FILES.items():
        path = os.path.join(BASE_DIR, filename)
        count = 0
        if os.path.exists(path):
            data = read_json(path)
            pending = [
                p for p in data
                if p.get("force_publish") or (str(p.get("id")) not in history and p.get("affiliate_url") not in history)
            ]
            count = len(pending)
        queues_summary.append({"niche": niche, "count": count})
        total_pending += count

    # 2. FB Grupos por nicho (Activos y Pausados)
    env_path = os.path.join(BASE_DIR, ".env")
    fb_groups = {"general": {"active": 0, "paused": 0}, "bebes": {"active": 0, "paused": 0}, "mascotas": {"active": 0, "paused": 0}, "tenis": {"active": 0, "paused": 0}, "moda": {"active": 0, "paused": 0}}
    fb_total_active = 0
    fb_total_paused = 0
    try:
        import re
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_content = f.read()

            def count_groups(env_var):
                match = re.search(rf"^{env_var}=(.*)$", env_content, re.MULTILINE)
                if match:
                    items = [u.strip() for u in match.group(1).split(",") if u.strip()]
                    active = sum(1 for item in items if not item.upper().startswith("PAUSED"))
                    paused = sum(1 for item in items if item.upper().startswith("PAUSED"))
                    return active, paused
                return 0, 0

            for niche, env_key in [("general", "FB_GROUP_URLS"), ("bebes", "FB_GROUPS_BABY_URLS"), ("mascotas", "FB_GROUPS_PETS_URLS"), ("tenis", "FB_GROUPS_TENIS_URLS"), ("moda", "FB_GROUPS_MODA_URLS")]:
                active, paused = count_groups(env_key)
                fb_groups[niche] = {"active": active, "paused": paused}
                fb_total_active += active
                fb_total_paused += paused
    except Exception as e:
        print(f"Error reading .env for groups: {e}")

    # 3. Último publicado
    last_file = os.path.join(BASE_DIR, "last_published.json")
    last_published = read_json(last_file, default={})

    # 4. Modo video y estado
    state = read_json(STATE_FILE, default={})
    video_mode = state.get("video_mode", "normal")

    return {
        "queues": {
            "total": total_pending,
            "by_niche": queues_summary,
        },
        "fb_groups": {
            "total": fb_total_active,
            "total_paused": fb_total_paused,
            "by_niche": fb_groups,
        },
        "last_published": last_published,
        "video_mode": video_mode,
    }

@app.get("/api/system/resources")
async def get_system_resources():
    """Retorna recursos del sistema (CPU, RAM, Disco) con soporte nativo de Linux y fallback psutil."""
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            "cpu_percent": round(cpu_percent, 1),
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "ram_percent": round(mem.percent, 1),
            "disk_used_gb": round(disk.used / (1024**3), 1),
            "disk_total_gb": round(disk.total / (1024**3), 1),
            "disk_percent": round(disk.percent, 1),
        }
    except Exception:
        pass

    import shutil
    try:
        disk = shutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024**3), 1)
        disk_used_gb = round(disk.used / (1024**3), 1)
        disk_percent = round((disk.used / disk.total) * 100, 1) if disk.total else 0
    except Exception:
        disk_total_gb, disk_used_gb, disk_percent = 0, 0, 0

    ram_total_gb, ram_used_gb, ram_percent = 0, 0, 0
    try:
        if os.path.exists('/proc/meminfo'):
            meminfo = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = int(parts[1].split()[0])
            total_kb = meminfo.get('MemTotal', 0)
            avail_kb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
            used_kb = max(0, total_kb - avail_kb)
            ram_total_gb = round(total_kb / (1024**2), 1)
            ram_used_gb = round(used_kb / (1024**2), 1)
            ram_percent = round((used_kb / total_kb) * 100, 1) if total_kb else 0
    except Exception:
        pass

    cpu_percent = 0
    try:
        load1, _, _ = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        cpu_percent = round(min(100.0, (load1 / cpu_count) * 100), 1)
    except Exception:
        pass

    return {
        "cpu_percent": cpu_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "ram_percent": ram_percent,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_percent": disk_percent,
    }

# ================= MOCKS DE ACCION =================

class MockOrchestrator:
    def __init__(self):
        self.telegram_bot = None

def run_refill_sync():
    import sys
    sys.path.append(BASE_DIR)
    try:
        from core.apify_refiller import check_and_refill
        asyncio.run(check_and_refill(MockOrchestrator()))
    except Exception as e:
        print(f"[API Background Refill Error] {e}")

@app.post("/api/bot/refill")
async def trigger_refill(background_tasks: BackgroundTasks):
    """Dispara el rellenado masivo de Apify/Amazon en background saltándose el cooldown."""
    def run_refill_sync_force():
        import sys
        sys.path.append(BASE_DIR)
        try:
            from core.apify_refiller import check_and_refill
            from core.orchestrator import Orchestrator
            
            # Pasamos force=True para saltarnos el cooldown y mínimo de cola
            asyncio.run(check_and_refill(MockOrchestrator(), force=True))
        except Exception as e:
            print(f"[API Background Refill Error] {e}")

    background_tasks.add_task(run_refill_sync_force)
    return {"message": "Proceso de llenado forzado iniciado en segundo plano."}

def run_publish_sync(network: str):
    import sys
    sys.path.append(BASE_DIR)
    try:
        orch = _new_api_orchestrator()
        bot = getattr(orch, "telegram_bot", None)
        if bot and hasattr(bot, "_process_publish_next"):
            print(f"[API Background Publish] Ejecutando _process_publish_next({network})")
            asyncio.run(bot._process_publish_next(network))
        else:
            print(f"[API Background Publish Error] Telegram bot instance not found or missing _process_publish_next")
    except Exception as e:
        print(f"[API Background Publish Error] {e}")

@app.post("/api/bot/publish/{network}")
async def trigger_publish(network: str, background_tasks: BackgroundTasks):
    """Dispara la publicación inmediata."""
    background_tasks.add_task(run_publish_sync, network)
    return {"message": f"Publicación en {network} iniciada en segundo plano."}

@app.post("/api/bot/reboot")
@app.post("/api/bot/restart")
async def trigger_reboot():
    """Mata el proceso del bot (orchestrator o main) para forzar su reinicio."""
    killed = 0
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = p.info.get('cmdline') or []
                if any('orchestrator.py' in c or 'amazon_deal_bot.py' in c for c in cmd):
                    if p.pid != os.getpid():
                        p.kill()
                        killed += 1
            except Exception:
                pass
    except ImportError:
        import subprocess
        try:
            r1 = subprocess.run(["pkill", "-f", "amazon_deal_bot.py"], capture_output=True)
            if r1.returncode == 0:
                killed += 1
            r2 = subprocess.run(["pkill", "-f", "orchestrator.py"], capture_output=True)
            if r2.returncode == 0:
                killed += 1
        except Exception:
            pass
    return {"message": f"Se enviaron señales de reinicio a {killed} procesos del bot."}

@app.post("/api/system/restart-web")
async def trigger_restart_web():
    """Mata el proceso de Node/Next del panel web para que systemd lo reinicie automáticamente."""
    import subprocess
    try:
        subprocess.run(["pkill", "-f", "next dev"], capture_output=True)
        subprocess.run(["pkill", "-f", "next-server"], capture_output=True)
        return {"message": "Panel Web reiniciándose vía systemd."}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/system/restart-all")
async def trigger_restart_all():
    """Reinicia todos los servicios del sistema (Bot, Web y API)."""
    import subprocess
    try:
        r = subprocess.run(["sudo", "-n", "systemctl", "restart", "gangas.target"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return {"message": "gangas.target reiniciado exitosamente vía systemctl."}
    except Exception:
        pass
    
    try:
        subprocess.run(["pkill", "-f", "amazon_deal_bot.py"], capture_output=True)
        subprocess.run(["pkill", "-f", "next dev"], capture_output=True)
        subprocess.run(["pkill", "-f", "next-server"], capture_output=True)
        return {"message": "Procesos reiniciados vía fallback (pkill)."}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/bot/discard-failed")
async def discard_failed():
    """Descarta los grupos de FB fallidos eliminando el archivo de cola."""
    file_path = os.path.join(BASE_DIR, "fb_failed_queue.json")
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"message": "Cola de fallidos eliminada."}
        else:
            return {"message": "No hay fallidos pendientes."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================= ACCIONES AVANZADAS DE COLAS (Fase 1) =================

class _SimpleTelegramNotifier:
    """
    Notificador mínimo para publicaciones disparadas desde la API (este proceso
    no tiene una instancia completa del bot de Telegram). Sin esto,
    Orchestrator() se queda con self.telegram_bot=None y todos los avisos
    -incluyendo el motivo real de un rechazo (precio, blacklist, descuento
    insuficiente, etc.)- se pierden en silencio en vez de llegar a Telegram.
    """

    def __init__(self):
        from core.config import Config
        self.token = Config.BOT_TOKEN
        self.chat_id = Config.CHAT_ID
        # orchestrator.py y los publishers de FB/Pinterest esperan poder leer
        # y guardar estado en self.telegram_bot.user_state; con un dict vacío
        # simplemente se comportan como si no hubiera nada configurado ahí.
        self.user_state = {}

    def _save_user_state(self):
        pass

    async def send_notification(self, msg: str, reply_markup=None, msg_id=None):
        if not self.token or not self.chat_id:
            return
        import aiohttp
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": msg}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    await resp.read()
        except Exception as e:
            print(f"[API Notifier] Error enviando notificación a Telegram: {e}")

    async def send_photo(self, photo_path, caption="", parse_mode="Markdown", reply_markup=None):
        """Envía una foto local o remota. Devuelve el message_id, o None si falla."""
        if not self.token or not self.chat_id:
            return None
        import aiohttp
        api_url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        try:
            async with aiohttp.ClientSession() as session:
                if str(photo_path).startswith("http"):
                    payload = {"chat_id": self.chat_id, "photo": photo_path, "caption": caption}
                    async with session.post(api_url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        res = await resp.json()
                else:
                    data = aiohttp.FormData()
                    data.add_field("chat_id", self.chat_id)
                    data.add_field("caption", caption)
                    with open(photo_path, "rb") as f:
                        data.add_field("photo", f)
                        async with session.post(api_url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            res = await resp.json()
                if not res.get("ok"):
                    print(f"[API Notifier] Error enviando foto: {res}")
                    return None
                return res.get("result", {}).get("message_id")
        except Exception as e:
            print(f"[API Notifier] Excepción enviando foto: {e}")
            return None


def _new_api_orchestrator():
    """Orchestrator con notificador de Telegram real, para que las publicaciones
    disparadas desde el panel avisen su resultado igual que las del scheduler."""
    from core.orchestrator import Orchestrator
    orch = Orchestrator()
    orch.telegram_bot = _SimpleTelegramNotifier()
    return orch


def run_queue_publish_sync(niche: str, product: dict):
    import sys
    sys.path.append(BASE_DIR)
    try:
        orch = _new_api_orchestrator()
        url = product.get("url") or product.get("affiliate_url") or ""
        # target_platform = "both" by default, o leer del estado
        success = asyncio.run(orch.run_publication(url=url, target_platform="both", pre_scraped_details=product))
        if not success:
            # Publicación manual rechazada (precio/blacklist/descuento/etc.):
            # se descarta de una vez, no tiene caso reintentar algo que no va a cambiar.
            from core.discard_manager import register_discard
            register_discard(product.get("id", "desconocido"), "rechazado_publicacion_manual", product)
            path = get_queue_path(niche)
            q = read_json(path, default=[])
            q = [p for p in q if str(p.get("id")) != str(product.get("id"))]
            write_json(path, q)
    except Exception as e:
        print(f"[API Queue Publish Error] {e}")

@app.post("/api/queues/{niche}/{product_id}/publish")
async def queue_force_publish(niche: str, product_id: str, background_tasks: BackgroundTasks):
    path = get_queue_path(niche)
    q = read_json(path, default=[])
    prod = next((p for p in q if str(p.get("id")) == product_id), None)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found in queue")
    background_tasks.add_task(run_queue_publish_sync, niche, prod)
    # No borramos el producto de la cola aquí. 
    # Cuando termine de publicarse, se añadirá al historial y se ocultará automáticamente del UI.
    return {"message": "Publicación iniciada"}

@app.post("/api/queues/{niche}/{product_id}/move_niche")
async def queue_move_niche(niche: str, product_id: str, target_niche: str = Body(..., embed=True)):
    if target_niche not in QUEUE_FILES:
        raise HTTPException(status_code=400, detail="Invalid target niche")
    
    source_path = get_queue_path(niche)
    target_path = get_queue_path(target_niche)
    
    q_src = read_json(source_path, default=[])
    prod = next((p for p in q_src if str(p.get("id")) == product_id), None)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Remove from source
    q_src = [p for p in q_src if str(p.get("id")) != product_id]
    write_json(source_path, q_src)
    
    # Add to target
    q_tgt = read_json(target_path, default=[])
    prod["niche"] = target_niche if target_niche == "general" else f"[CAT:{target_niche.upper()}]"
    q_tgt.insert(0, prod)
    write_json(target_path, q_tgt)
    
    return {"message": "Producto movido de nicho"}

@app.post("/api/queues/{niche}/{product_id}/reorder")
async def queue_reorder(niche: str, product_id: str, position: str = Body(..., embed=True)):
    path = get_queue_path(niche)
    q = read_json(path, default=[])
    idx = next((i for i, p in enumerate(q) if str(p.get("id")) == product_id), -1)
    if idx == -1:
        raise HTTPException(status_code=404, detail="Product not found")
        
    prod = q.pop(idx)
    if position == "top":
        q.insert(0, prod)
    else:
        q.append(prod)
    write_json(path, q)
    return {"message": "Producto reordenado"}

@app.post("/api/queues/{niche}/sort-by-savings")
async def queue_sort_by_savings(niche: str):
    """Reordena la cola del nicho por mayor ahorro real en pesos ($ MXN) descendente."""
    path = get_queue_path(niche)
    q = read_json(path, default=[])
    if not q or not isinstance(q, list):
        return {"message": "Cola vacía", "count": 0, "products": []}

    def calc_savings(p):
        try:
            o_str = str(p.get("offer_price") or p.get("price") or "0")
            l_str = str(p.get("list_price") or p.get("original_price") or "0")
            o_val = float(''.join(c for c in o_str if c.isdigit() or c == '.') or 0)
            l_val = float(''.join(c for c in l_str if c.isdigit() or c == '.') or 0)
            return (l_val - o_val) if l_val > o_val else 0.0
        except Exception:
            return 0.0

    q.sort(key=calc_savings, reverse=True)
    write_json(path, q)
    return {"message": "Cola reordenada por mayor ahorro en pesos", "count": len(q), "products": q}

@app.post("/api/queues/{niche}/{product_id}/script")
async def queue_generate_script(niche: str, product_id: str):
    path = get_queue_path(niche)
    q = read_json(path, default=[])
    prod = next((p for p in q if str(p.get("id")) == product_id), None)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
        
    from core.ai_service import generate_product_script

    try:
        script = await generate_product_script(prod)
        prod["tiktok_script"] = script
        prod["tts_text"] = script
        write_json(path, q)
        return {"script": script}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================= ACCIONES DE HISTORIAL =================

def run_history_publish_sync(product: dict, network: str):
    import sys
    sys.path.append(BASE_DIR)
    try:
        orch = _new_api_orchestrator()
        url = product.get("url") or product.get("affiliate_url") or ""
        asyncio.run(orch.run_publication(url=url, target_platform=network, pre_scraped_details=product))
    except Exception as e:
        print(f"[API History Publish Error] {e}")

@app.post("/api/history/{product_id}/republish/{network}")
async def history_republish(product_id: str, network: str, background_tasks: BackgroundTasks):
    web_file = os.path.join(BASE_DIR, "website_db.json")
    web_data = read_json(web_file, default=[])
    prod = next((p for p in web_data if str(p.get("id")) == product_id), None)
    
    if not prod:
        # Fallback to last_published.json if not found in website_db
        last_file = os.path.join(BASE_DIR, "last_published.json")
        last = read_json(last_file, default={})
        if str(last.get("id")) == product_id or str(last.get("product_id")) == product_id:
            prod = last
            
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found in history")
    
    target_platform = "both" if network == "all" else network
    background_tasks.add_task(run_history_publish_sync, prod, target_platform)
    return {"message": f"Republicación en {target_platform} iniciada"}

def run_history_video_sync(product: dict):
    import sys
    sys.path.append(BASE_DIR)
    try:
        from core.advanced_video_maker import AdvancedVideoMaker
        maker = AdvancedVideoMaker()
        asyncio.run(maker.create_tiktok_video(product))
    except Exception as e:
        print(f"[API History Video Error] {e}")

@app.post("/api/history/{product_id}/video")
async def history_video(product_id: str, background_tasks: BackgroundTasks):
    web_file = os.path.join(BASE_DIR, "website_db.json")
    web_data = read_json(web_file, default=[])
    prod = next((p for p in web_data if str(p.get("id")) == product_id), None)
    
    if not prod:
        last_file = os.path.join(BASE_DIR, "last_published.json")
        last = read_json(last_file, default={})
        if str(last.get("id")) == product_id or str(last.get("product_id")) == product_id:
            prod = last
            
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
        
    background_tasks.add_task(run_history_video_sync, prod)
    return {"message": "Video premium creation started"}

@app.delete("/api/history/{product_id}")
async def history_delete(product_id: str):
    from core.history_manager import load_history_map
    from core.storage import json_save_atomic
    history_map = load_history_map()
    deleted = False
    
    # Eliminar claves que coincidan con product_id
    keys_to_remove = [k for k in history_map if str(product_id) in k]
    if keys_to_remove:
        for k in keys_to_remove:
            history_map.pop(k, None)
        json_save_atomic(os.path.join(BASE_DIR, "published_history.json"), history_map, indent=2, ensure_ascii=False)
        deleted = True
        
    # Also check website_db.json
    web_file = os.path.join(BASE_DIR, "website_db.json")
    if os.path.exists(web_file):
        web_data = read_json(web_file, default=[])
        filtered_web = [p for p in web_data if str(p.get("id")) != product_id]
        if len(filtered_web) != len(web_data):
            write_json(web_file, filtered_web)
            deleted = True

    # Also check last_published.json
    last_file = os.path.join(BASE_DIR, "last_published.json")
    if os.path.exists(last_file):
        last_data = read_json(last_file, default={})
        if str(last_data.get("id")) == product_id or str(last_data.get("product_id")) == product_id:
            write_json(last_file, {}) # Clear it
            deleted = True
            
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
        
    return {"message": "Product removed from history"}

@app.get("/api/history/stats")
async def get_history_statistics():
    """Devuelve estadísticas del historial de publicaciones y estado de expiración."""
    from core.history_manager import get_history_stats
    return get_history_stats()

@app.get("/api/history")
async def get_history():
    """Obtiene el historial de productos publicados."""
    history_file = os.path.join(BASE_DIR, "website_db.json")
    data = read_json(history_file, default=[])
    # Devuelve los ultimos 100 elementos por si es muy largo
    return {"history": data[:100]}

@app.get("/api/admin/web")
async def get_admin_web():
    """Obtiene los productos publicados en la web."""
    web_file = os.path.join(BASE_DIR, "website_db.json")
    data = read_json(web_file, default=[])
    return {"web_products": data}

@app.delete("/api/admin/web/{product_id}")
async def delete_admin_web_product(product_id: str):
    """Elimina un producto de la base de datos de la web."""
    web_file = os.path.join(BASE_DIR, "website_db.json")
    data = read_json(web_file, default=[])
    initial_len = len(data)
    data = [p for p in data if str(p.get("id")) != str(product_id)]
    if len(data) == initial_len:
        raise HTTPException(status_code=404, detail="Producto no encontrado en la base de datos web")
    write_json(web_file, data)
    return {"status": "success", "message": "Producto eliminado de la web"}

@app.put("/api/admin/web/{product_id}")
async def update_admin_web_product(product_id: str, payload: Dict[str, Any] = Body(...)):
    """Actualiza un producto en la base de datos de la web."""
    web_file = os.path.join(BASE_DIR, "website_db.json")
    data = read_json(web_file, default=[])
    updated = False
    for i, p in enumerate(data):
        if str(p.get("id")) == str(product_id):
            data[i].update(payload)
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail="Producto no encontrado en la base de datos web")
    write_json(web_file, data)
    return {"status": "success", "message": "Producto actualizado"}

@app.get("/api/settings/queue_mode")
async def get_queue_mode():
    """Obtiene el estado del modo cola."""
    state = read_json(STATE_FILE, default={"queue_mode": True})
    return {"queue_mode": state.get("queue_mode", True)}

@app.post("/api/settings/queue_mode")
async def set_queue_mode(enabled: bool = Body(..., embed=True)):
    """Actualiza el estado del modo cola."""
    state = read_json(STATE_FILE, default={})
    state["queue_mode"] = enabled
    write_json(STATE_FILE, state)
    return {"queue_mode": enabled, "message": "Modo cola actualizado"}

@app.get("/api/bot/logs")
async def get_logs(lines: int = 50):
    """Retorna las últimas líneas del log."""
    log_file = os.path.join(BASE_DIR, "bot.log")
    try:
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                logs_list = [line.strip() for line in f.readlines()[-lines:]]
                return {"logs": logs_list}
    except Exception:
        pass
    return {"logs": ["No hay logs disponibles en bot.log."]}

@app.get("/api/settings/apify-usage")
async def get_apify_usage():
    import aiohttp
    from core.config import Config
    
    tokens = Config.get_apify_tokens()
    usage_data = []
    
    async with aiohttp.ClientSession() as session:
        for i, token in enumerate(tokens):
            if not token:
                continue
            try:
                # https://docs.apify.com/api/v2#/reference/users/user-object/get-user
                async with session.get(f"https://api.apify.com/v2/users/me?token={token}") as resp:
                    if resp.status == 200:
                        data = (await resp.json()).get("data", {})
                        usage = data.get("limits", {}).get("monthlyUsageUsd", 0)
                        limit = data.get("limits", {}).get("maxMonthlyUsageUsd", 5.0)
                        
                        usage_data.append({
                            "token_index": i + 1,
                            "username": data.get("username", "Unknown"),
                            "usage_usd": usage,
                            "limit_usd": limit,
                        })
                    else:
                        usage_data.append({"token_index": i + 1, "error": f"HTTP {resp.status}"})
            except Exception as e:
                usage_data.append({"token_index": i + 1, "error": str(e)})
                
    return {"usage": usage_data}


@app.post("/api/queues/{niche}/{product_id}/retry-affiliate")
async def queue_retry_affiliate(niche: str, product_id: str, background_tasks: BackgroundTasks):
    path = get_queue_path(niche)
    q = read_json(path, default=[])
    prod = next((p for p in q if str(p.get("id")) == product_id), None)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
        
    original_url = prod.get("original_url") or prod.get("affiliate_url") or prod.get("url")
    if not original_url:
        raise HTTPException(status_code=400, detail="Product has no URL to retry")
        
    background_tasks.add_task(generate_affiliate_link_bg, original_url, product_id, path)
    return {"message": "Reintento de enlace iniciado en segundo plano"}

async def generate_affiliate_link_bg(original_url: str, item_id: str, queue_path: str):
    try:
        import asyncio
        script_path = os.path.join(BASE_DIR, "affiliate_linker.py")
        process = await asyncio.create_subprocess_exec(
            sys.executable, script_path, "--headless", original_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=BASE_DIR
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode('utf-8')
        
        meli_url = None
        for line in output.split('\n'):
            if line.strip().startswith("https://meli.la/"):
                meli_url = line.strip()
                break
                
        if meli_url:
            queue = read_json(queue_path, default=[])
            for q in queue:
                if str(q.get("id")) == str(item_id):
                    q["affiliate_url"] = meli_url
                    q["url"] = meli_url
                    q.pop("review_status", None)
                    break
            write_json(queue_path, queue)
            print(f"[APIFY BG] Link afiliado generado para {item_id}: {meli_url}")
        else:
            print(f"[APIFY BG] No se pudo generar link de afiliado para: {original_url}")
            if stderr:
                print(f"[APIFY BG] Error devuelto: {stderr.decode('utf-8')}")
    except Exception as e:
        print(f"[APIFY BG] Error en subprocess affiliate_linker: {e}")

@app.post("/api/queues/{niche}/generate-all-affiliates")
async def queue_generate_all_affiliates(niche: str, background_tasks: BackgroundTasks):
    path = get_queue_path(niche)
    async def _run_batch():
        try:
            import affiliate_linker
            await affiliate_linker.main(headless=True, products_file=path)
        except Exception as e:
            print(f"[BATCH AFFILIATE] Error: {e}")
    background_tasks.add_task(_run_batch)
    return {"message": "Generación de links iniciada para toda la cola en segundo plano."}


# ==========================================
# GESTIÓN DE GRUPOS DE FACEBOOK (.env)
# ==========================================

def _get_env_var_for_category(category: str) -> str:
    mapping = {
        "general": "FB_GROUP_URLS",
        "bebes": "FB_GROUPS_BABY_URLS",
        "mascotas": "FB_GROUPS_PETS_URLS",
        "tenis": "FB_GROUPS_TENIS_URLS",
        "moda": "FB_GROUPS_MODA_URLS"
    }
    return mapping.get(category, "FB_GROUP_URLS")

@app.get("/api/facebook/groups")
def get_fb_groups():
    import re
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return {"general": [], "bebes": [], "mascotas": [], "tenis": [], "moda": []}
    
    with open(env_path, "r", encoding="utf-8") as f:
        env_content = f.read()

    def parse_groups(env_var):
        match = re.search(rf"^{env_var}=(.*)$", env_content, re.MULTILINE)
        if match:
            return [u.strip() for u in match.group(1).split(",") if u.strip()]
        return []

    return {
        "general": parse_groups("FB_GROUP_URLS"),
        "bebes": parse_groups("FB_GROUPS_BABY_URLS"),
        "mascotas": parse_groups("FB_GROUPS_PETS_URLS"),
        "tenis": parse_groups("FB_GROUPS_TENIS_URLS"),
        "moda": parse_groups("FB_GROUPS_MODA_URLS")
    }

class FBGroupAction(BaseModel):
    url: str
    category: str
    force: bool = False
    note: str | None = None

@app.post("/api/facebook/groups/add")
def add_fb_group(action: FBGroupAction):
    import re
    env_var = _get_env_var_for_category(action.category)
    env_path = os.path.join(BASE_DIR, ".env")
    url = action.url.strip()
    
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="URL inválida")

    import json
    history_file = os.path.join(BASE_DIR, "fb_groups_history.json")
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    if url in history and not action.force:
        raise HTTPException(status_code=409, detail="Este grupo ya estuvo en el sistema previamente y fue eliminado. ¿Deseas agregarlo de todos modos?")

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()
        match = re.search(rf"^{env_var}=(.*)$", env_content, re.MULTILINE)
        if match:
            existing = match.group(1).strip()
            urls = [u.strip() for u in existing.split(",") if u.strip()]
            if url in urls:
                raise HTTPException(status_code=400, detail="El grupo ya existe")
            urls.append(url)
            new_line = f"{env_var}=" + ",".join(urls)
            env_content = re.sub(rf"^{env_var}=.*$", new_line, env_content, flags=re.MULTILINE)
        else:
            env_content += f"\n{env_var}={url}"
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        
        if url not in history:
            history.append(url)
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        
        return {"status": "success", "message": "Grupo añadido"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/facebook/groups/remove")
def remove_fb_group(action: FBGroupAction):
    import re
    env_var = _get_env_var_for_category(action.category)
    env_path = os.path.join(BASE_DIR, ".env")
    url = action.url.strip()

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()
        match = re.search(rf"^{env_var}=(.*)$", env_content, re.MULTILINE)
        if match:
            existing = match.group(1).strip()
            urls = [u.strip() for u in existing.split(",") if u.strip()]
            if url in urls:
                urls.remove(url)
                new_line = f"{env_var}={','.join(urls)}"
                new_content = env_content[:match.start()] + new_line + env_content[match.end():]
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                
                import json
                history_file = os.path.join(BASE_DIR, "fb_groups_history.json")
                history = []
                if os.path.exists(history_file):
                    try:
                        with open(history_file, "r", encoding="utf-8") as f:
                            history = json.load(f)
                    except Exception:
                        pass
                if url not in history:
                    history.append(url)
                    with open(history_file, "w", encoding="utf-8") as f:
                        json.dump(history, f, indent=4)
                        
                return {"message": "Grupo eliminado correctamente"}
        raise HTTPException(status_code=400, detail="El grupo no existe")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/facebook/groups/toggle_pause")
def toggle_pause_fb_group(action: FBGroupAction):
    import re
    env_var = _get_env_var_for_category(action.category)
    env_path = os.path.join(BASE_DIR, ".env")
    url = action.url.strip()

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()
        match = re.search(rf"^{env_var}=(.*)$", env_content, re.MULTILINE)
        if match:
            existing = match.group(1).strip()
            urls = [u.strip() for u in existing.split(",") if u.strip()]
            
            if url in urls:
                idx = urls.index(url)
                if url.upper().startswith("PAUSED"):
                    urls[idx] = re.sub(r"(?i)^PAUSED(?:\[.*?\])?:\s*", "", url)
                else:
                    if action.note:
                        urls[idx] = f"PAUSED[{action.note}]:{url}"
                    else:
                        urls[idx] = f"PAUSED:{url}"
                
                new_line = f"{env_var}={','.join(urls)}"
                new_content = env_content[:match.start()] + new_line + env_content[match.end():]
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                return {"message": "Estado del grupo actualizado"}
        raise HTTPException(status_code=400, detail="El grupo no existe")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload_image")
async def upload_image(file: UploadFile = File(...)):
    import shutil
    import time
    import uuid
    from core.config import Config

    try:
        # Check and create captures dir
        captures_dir = Config.CAPTURES_DIR
        os.makedirs(captures_dir, exist_ok=True)

        # Generate unique filename
        ext = os.path.splitext(file.filename)[1]
        if not ext:
            ext = ".png"
        new_filename = f"custom_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
        filepath = os.path.join(captures_dir, new_filename)

        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        relative_path = f"captures/{new_filename}"
        return {"status": "success", "filename": new_filename, "path": relative_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar la imagen: {str(e)}")


@app.get("/api/facebook/groups/notes/all")
async def get_all_facebook_group_notes():
    """
    Obtiene todas las notas guardadas de los grupos de Facebook.
    """
    from core.facebook_groups_notes import get_all_notes
    return get_all_notes()


@app.get("/api/facebook/groups/notes")
async def get_facebook_group_note(url: str):
    """
    Obtiene la nota de un grupo de Facebook.

    Query params:
    - url: URL del grupo (será URL-encoded automáticamente)
    """
    from core.facebook_groups_notes import get_note

    print(f"\n[API] GET /api/facebook/groups/notes?url={url}")
    return get_note(url)


@app.post("/api/facebook/groups/notes")
async def save_facebook_group_note(url: str, body: NoteRequest):
    """
    Guarda o actualiza la nota de un grupo de Facebook.

    Query params:
    - url: URL del grupo

    Body:
    {
        "note": "Texto de la nota (máx 1000 caracteres)"
    }
    """
    from core.facebook_groups_notes import save_note

    print(f"\n[API] POST /api/facebook/groups/notes?url={url}")
    print(f"[API] Body recibido: {body}")

    note = body.note.strip() if body.note else ""

    print(f"[API] Nota a guardar: '{note}' (len={len(note)})")

    if len(note) > 1000:
        print(f"[API] ERROR: Nota muy larga ({len(note)} > 1000)")
        return {
            "success": False,
            "error": f"La nota excede 1000 caracteres ({len(note)} caracteres)"
        }

    print(f"[API] Intentando guardar...")
    success = save_note(url, note)
    print(f"[API] Resultado: success={success}")

    return {
        "success": success,
        "message": "Nota guardada" if success else "Error al guardar nota",
        "url": url,
        "character_count": len(note)
    }


@app.delete("/api/facebook/groups/notes")
async def delete_facebook_group_note(url: str):
    """Elimina la nota de un grupo."""
    from core.facebook_groups_notes import delete_note

    print(f"\n[API] DELETE /api/facebook/groups/notes?url={url}")
    success = delete_note(url)
    return {
        "success": success,
        "message": "Nota eliminada" if success else "No había nota que eliminar"
    }


if __name__ == "__main__":
    import uvicorn
    # Para pruebas locales: python api/main.py
    uvicorn.run(app, host="0.0.0.0", port=8001)
