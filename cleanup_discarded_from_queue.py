#!/usr/bin/env python3
"""
Limpia las colas (products_list.json, etc) removiendo productos que ya fueron descartados.
Esto previene que se intenten publicar productos que ya fallaron 3 veces.
"""
import json
import os
from core.storage import json_load, json_save_atomic
from core.config import Config
from core.discard_manager import is_already_discarded

QUEUE_FILES = [
    Config.JSON_QUEUE_FILE,
    os.path.join(Config.BASE_DIR, "products_list_baby.json"),
    os.path.join(Config.BASE_DIR, "products_list_pets.json"),
    os.path.join(Config.BASE_DIR, "queue_tenis.json"),
    os.path.join(Config.BASE_DIR, "queue_moda.json"),
]

def cleanup_queue(queue_file: str) -> int:
    """Elimina productos descartados de una cola. Retorna cantidad removida."""
    if not os.path.exists(queue_file):
        return 0

    products = json_load(queue_file, default=[])
    if not isinstance(products, list):
        return 0

    original_count = len(products)
    cleaned = []
    removed = []

    for product in products:
        product_id = product.get("id", "")
        if product_id and is_already_discarded(product_id):
            removed.append(product_id)
        else:
            cleaned.append(product)

    if removed:
        print(f"[CLEANUP] {os.path.basename(queue_file)}: Removidos {len(removed)} productos descartados")
        for pid in removed:
            print(f"  - {pid}")
        json_save_atomic(queue_file, cleaned, indent=2, ensure_ascii=False)

    return len(removed)

if __name__ == "__main__":
    print("[CLEANUP] Iniciando limpieza de colas...")
    total_removed = 0

    for queue_file in QUEUE_FILES:
        if os.path.exists(queue_file):
            removed = cleanup_queue(queue_file)
            total_removed += removed

    print(f"\n[CLEANUP] ✅ Limpieza completada. Total removidos: {total_removed}")
