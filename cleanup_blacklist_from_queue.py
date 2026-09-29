#!/usr/bin/env python3
"""
Limpia la cola removiendo productos que contienen palabras en BLACKLIST.
Esto evita que se intenten publicar productos que serán rechazados por validación.
"""
import json
import os
from core.config import Config
from core.storage import json_load, json_save_atomic

QUEUE_FILES = {
    "general": Config.JSON_QUEUE_FILE,
    "baby": os.path.join(Config.BASE_DIR, "products_list_baby.json"),
    "pets": os.path.join(Config.BASE_DIR, "products_list_pets.json"),
    "tenis": os.path.join(Config.BASE_DIR, "queue_tenis.json"),
    "moda": os.path.join(Config.BASE_DIR, "queue_moda.json"),
}

def cleanup_queue(queue_name: str, queue_file: str) -> int:
    """Limpia una cola removiendo productos con palabras BLACKLIST."""
    if not os.path.exists(queue_file):
        return 0

    products = json_load(queue_file, default=[])
    if not isinstance(products, list):
        return 0

    blacklist_words = Config.BLACKLIST_WORDS
    original_count = len(products)
    cleaned = []
    removed = []

    for product in products:
        title = (product.get("title", "") or "").lower()

        # Verificar si contiene alguna palabra en BLACKLIST
        if title and any(word in title for word in blacklist_words):
            removed.append((product.get("id"), product.get("title", "")[:60]))
        else:
            cleaned.append(product)

    if removed:
        print(f"\n[CLEANUP {queue_name.upper()}] Removidos {len(removed)} productos con BLACKLIST:")
        for prod_id, title in removed:
            print(f"  ❌ {prod_id}: {title}...")

        json_save_atomic(queue_file, cleaned, indent=2, ensure_ascii=False)
        return len(removed)

    return 0

if __name__ == "__main__":
    print("=" * 70)
    print("LIMPIEZA DE COLA - Removiendo productos con BLACKLIST")
    print("=" * 70)

    print(f"\nPalabras BLACKLIST configuradas: {', '.join(Config.BLACKLIST_WORDS)}\n")

    total_removed = 0
    for queue_name, queue_file in QUEUE_FILES.items():
        removed = cleanup_queue(queue_name, queue_file)
        total_removed += removed

    print(f"\n{'=' * 70}")
    print(f"✅ LIMPIEZA COMPLETADA")
    print(f"📊 Total removidos: {total_removed} productos")
    print(f"{'=' * 70}\n")
