import json
import os
import threading

_cache = {}
_cache_lock = threading.Lock()


def _get_mtime(path: str):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def json_load(path: str, default=None, silence=True):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        if not silence:
            print(f"[STORAGE] Error cargando JSON {path}: {e}")
        return default if default is not None else {}




def json_save_atomic(path: str, data, indent=2, ensure_ascii=False):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

        with _cache_lock:
            if path in _cache:
                del _cache[path]
    except Exception as e:
        print(f"[STORAGE] Error guardando JSON {path}: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


