"""
facebook_groups_notes.py
Gestión de notas y comentarios para grupos de Facebook.
Permite guardar notas personalizadas para cada grupo.
"""
import os
from datetime import datetime
from core.storage import json_load, json_save_atomic
from core.config import Config

NOTES_FILE = os.path.join(Config.BASE_DIR, "facebook_groups_notes.json")
MAX_NOTE_LENGTH = 1000


def get_note(group_url: str) -> dict:
    """
    Obtiene la nota de un grupo.

    Returns:
        {
            "url": "https://...",
            "note": "texto de la nota",
            "updated_at": "2026-08-29T14:30:00",
            "character_count": 150
        }
    """
    notes = json_load(NOTES_FILE, default={})

    if group_url not in notes:
        return {
            "url": group_url,
            "note": "",
            "updated_at": None,
            "character_count": 0
        }

    entry = notes[group_url]
    return {
        "url": group_url,
        "note": entry.get("note", ""),
        "updated_at": entry.get("updated_at"),
        "character_count": len(entry.get("note", ""))
    }


def get_all_notes() -> dict:
    """Obtiene todas las notas guardadas."""
    return json_load(NOTES_FILE, default={})


def save_note(group_url: str, note: str) -> bool:
    """
    Guarda o actualiza la nota de un grupo.

    Args:
        group_url: URL del grupo
        note: Texto de la nota (máx 1000 caracteres)

    Returns:
        True si se guardó, False si excede límite
    """
    print(f"\n[SAVE_NOTE] Guardando nota para: {group_url}")
    print(f"[SAVE_NOTE] Nota: '{note}' (len={len(note)})")
    print(f"[SAVE_NOTE] Archivo: {NOTES_FILE}")

    if len(note) > MAX_NOTE_LENGTH:
        print(f"[SAVE_NOTE] ERROR: Nota excede {MAX_NOTE_LENGTH} caracteres")
        return False

    print(f"[SAVE_NOTE] Cargando notas existentes...")
    notes = json_load(NOTES_FILE, default={})
    print(f"[SAVE_NOTE] Notas cargadas: {len(notes)} grupos")

    notes[group_url] = {
        "note": note.strip(),
        "updated_at": datetime.now().isoformat(),
        "character_count": len(note.strip())
    }

    try:
        print(f"[SAVE_NOTE] Guardando en archivo...")
        json_save_atomic(NOTES_FILE, notes, indent=2, ensure_ascii=False)
        print("[SAVE_NOTE] OK: Nota guardada exitosamente")
        return True
    except Exception as e:
        print(f"[SAVE_NOTE] ERROR guardando nota: {e}")
        import traceback
        traceback.print_exc()
        return False


def delete_note(group_url: str) -> bool:
    """Elimina la nota de un grupo."""
    notes = json_load(NOTES_FILE, default={})

    if group_url in notes:
        del notes[group_url]
        try:
            json_save_atomic(NOTES_FILE, notes, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ERROR] Error eliminando nota para {group_url}: {e}")
            return False

    return False


