import os
from datetime import datetime
from core.storage import json_load, json_save_atomic
from core.config import Config

DISCARDED_FILE = os.path.join(Config.BASE_DIR, "discarded_products.json")

def register_discard(product_id: str, reason: str, product_details: dict = None):
    """
    Registra un producto como descartado con el motivo específico.

    Args:
        product_id: ID del producto
        reason: Motivo del descarte (ej: "duplicado", "usuario", "validación", etc)
        product_details: Datos del producto (opcional)
    """
    discarded = json_load(DISCARDED_FILE, default=[])

    discard_entry = {
        "id": product_id,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
        "title": product_details.get("title", "") if product_details else "",
        "url": product_details.get("affiliate_url") or product_details.get("url", "") if product_details else ""
    }

    discarded.insert(0, discard_entry)
    json_save_atomic(DISCARDED_FILE, discarded, indent=2, ensure_ascii=False)
    print(f"[DISCARD] Producto {product_id} registrado como descartado: {reason}")


def is_already_discarded(product_id: str) -> bool:
    """Verifica si un producto ya fue descartado."""
    discarded = json_load(DISCARDED_FILE, default=[])
    return any(str(d.get("id")) == str(product_id) for d in discarded)


def get_discard_history():
    """Obtiene el historial completo de descartados."""
    return json_load(DISCARDED_FILE, default=[])


def get_discard_reason(product_id: str) -> str:
    """Obtiene el motivo de descarte de un producto."""
    discarded = json_load(DISCARDED_FILE, default=[])
    for entry in discarded:
        if str(entry.get("id")) == str(product_id):
            return entry.get("reason", "desconocido")
    return None
