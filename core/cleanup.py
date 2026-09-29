import os
import time
from core.config import Config
from core.storage import json_load, json_save_atomic

# -----------------------------------------------------------------------
# Utilidades internas
# -----------------------------------------------------------------------

def _load_cursors():
    path = os.path.join(Config.BASE_DIR, "cursors.json")
    return json_load(path, default={})


def _save_cursors(cursors):
    path = os.path.join(Config.BASE_DIR, "cursors.json")
    try:
        json_save_atomic(path, cursors, indent=2)
    except Exception as e:
        print(f"⚠️ Error guardando cursores: {e}")


def _get_active_networks():
    state_file = os.path.join(Config.BASE_DIR, "user_state.json")
    if os.path.exists(state_file):
        state = json_load(state_file, default={})
        return [k for k, v in state.get("active_networks", {}).items() if v]
    return []


def _delete_file_safe(path):
    """Borra un archivo sin lanzar excepción si falla. Devuelve bytes liberados."""
    try:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            os.remove(path)
            return size
    except Exception as e:
        print(f"⚠️ No se pudo borrar {path}: {e}")
    return 0


# -----------------------------------------------------------------------
# FASE 1: Limpieza por Cursores — borrar assets de productos ya publicados
# -----------------------------------------------------------------------

def _cleanup_assets_by_cursor(products_to_retire):
    """
    Borra los screenshots y videos de productos que ya fueron publicados
    por TODAS las redes activas. Los archivos se identifican por el ID del producto.
    """
    deleted_count = 0
    bytes_freed = 0

    captures_dir = Config.CAPTURES_DIR
    videos_dir = os.path.join(Config.BASE_DIR, "tiktok_videos")

    for p in products_to_retire:
        p_id = str(p.get("id", "")).strip()
        if not p_id:
            continue

        # Buscar cualquier archivo cuyo nombre empiece con el ID del producto
        for directory in [captures_dir, videos_dir]:
            if not os.path.exists(directory):
                continue
            for filename in os.listdir(directory):
                if filename.startswith(p_id):
                    freed = _delete_file_safe(os.path.join(directory, filename))
                    if freed:
                        deleted_count += 1
                        bytes_freed += freed
                        print(f"🗑️ Asset retirado: {filename} ({freed / 1024 / 1024:.2f} MB)")

        # Borrar también el screenshot si está guardado como ruta absoluta
        screenshot = p.get("screenshot", "")
        if screenshot and os.path.isfile(screenshot):
            freed = _delete_file_safe(screenshot)
            if freed:
                deleted_count += 1
                bytes_freed += freed

    return deleted_count, bytes_freed


# -----------------------------------------------------------------------
# FASE 2: Red de seguridad — archivos huérfanos de más de 30 días
# -----------------------------------------------------------------------

def _cleanup_orphan_assets(days=30):
    """
    Último recurso: borra archivos que superen los 30 días de antigüedad
    en caso de que el mecanismo de cursores haya fallado silenciosamente.
    """
    now = time.time()
    cutoff = now - (days * 86400)
    deleted = 0
    freed = 0

    for directory in [Config.CAPTURES_DIR, os.path.join(Config.BASE_DIR, "tiktok_videos")]:
        if not os.path.exists(directory):
            continue
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff:
                size = _delete_file_safe(file_path)
                if size:
                    deleted += 1
                    freed += size
                    print(f"🗑️ Huérfano (+30d): {filename} ({size / 1024 / 1024:.2f} MB)")
    return deleted, freed


# -----------------------------------------------------------------------
# Función pública principal
# -----------------------------------------------------------------------

def run_cleanup(days_to_keep=7):
    """
    Limpieza principal del sistema. Opera en dos fases:

    FASE 1 — Modo Cursor (principal):
        Borra assets de los productos que YA fueron publicados por TODAS las
        redes activas. No usa fechas; usa el cursor más bajo entre todas las
        redes. Recorta la cola y re-balancea cursors.json.

    FASE 2 — Modo Seguridad (30 días):
        Borra archivos huérfanos que hayan quedado por algún error no previsto.

    `days_to_keep` se mantiene por compatibilidad con llamadas existentes
    pero ya no controla la lógica principal.
    """
    print("🧹 Iniciando rutina de limpieza inteligente (Arquitectura de Cursores)...")
    total_deleted = 0
    total_freed = 0

    queue_file = Config.JSON_QUEUE_FILE
    cursors_file = os.path.join(Config.BASE_DIR, "cursors.json")

    # ── FASE 1: Limpieza por cursor ──────────────────────────────────────
    if os.path.exists(cursors_file) and os.path.exists(queue_file):
        try:
            cursors = _load_cursors()
            active_nets = _get_active_networks()

            if active_nets and cursors:
                # Filtrar redes de video para que no bloqueen la limpieza
                primary_nets = [net for net in active_nets if net not in ["tiktok", "youtube"]]
                
                # Si no hay redes primarias activas, usar todas (fallback seguro)
                nets_to_evaluate = primary_nets if primary_nets else active_nets
                
                min_cursor = min([cursors.get(net, 0) for net in nets_to_evaluate])

                if min_cursor > 0:
                    products = json_load(queue_file, default=[])
                    if not isinstance(products, list):
                        products = []

                    products_to_retire = products[:min_cursor]
                    remaining_products = products[min_cursor:]

                    print(f"🔖 Cursor mínimo: {min_cursor} — Retirando {len(products_to_retire)} productos totalmente publicados.")

                    # 1a. Borrar sus assets
                    d, b = _cleanup_assets_by_cursor(products_to_retire)
                    total_deleted += d
                    total_freed += b

                    # 1b. Recortar la cola (escritura atómica)
                    json_save_atomic(queue_file, remaining_products, indent=2, ensure_ascii=False)

                    # 1c. Re-balancear cursores
                    for net in cursors:
                        cursors[net] = max(0, cursors[net] - min_cursor)
                    _save_cursors(cursors)

                    print(f"✅ Cola recortada ({len(remaining_products)} productos restantes). Cursores re-balanceados.")

                else:
                    print("ℹ️ Cursor mínimo en 0 — ningún producto publicado en todas las redes aún. Sin limpieza de cola hoy.")
            else:
                print("ℹ️ Sin redes activas o sin cursores — omitiendo limpieza de cola.")

        except Exception as e:
            print(f"⚠️ Error en limpieza por cursor: {e}")
    else:
        print("ℹ️ No existe cursors.json o la cola está vacía — omitiendo limpieza de cola.")

    # ── FASE 2: Red de seguridad — huérfanos de +30 días ─────────────────
    print("🛡️ Verificando archivos huérfanos (más de 30 días)...")
    d, b = _cleanup_orphan_assets(days=30)
    total_deleted += d
    total_freed += b

    # ── Resumen ───────────────────────────────────────────────────────────
    if total_deleted > 0:
        print(f"✅ Limpieza finalizada. {total_deleted} archivos eliminados — {total_freed / 1024 / 1024:.2f} MB liberados.")
    else:
        print("✅ Limpieza finalizada. Todo en orden, sin archivos que eliminar hoy.")


if __name__ == "__main__":
    run_cleanup()
