"""
core/storage_manager.py

Gestor centralizado de persistencia de datos.
Abstrae todas las operaciones de carga/guardado de JSON para:
- Consistencia de operaciones atómicas
- Validación de esquema básica
- Caché en memoria (opcional)
- Auditoría de cambios

Reemplaza:
- Cargas/guardados dispersos en Orchestrator, Scheduler, TelegramBot, etc.
- Uso directo de json_load/json_save_atomic
"""

import os
import json
from typing import Any, Dict, Optional, List
from core.config import Config
from core.storage import json_load, json_save_atomic


class StorageManager:
    """
    Gestor centralizado de persistencia.

    Todos los datos se definen en un único lugar con schemas opcionales.
    Facilita refactoring, validación y caché.
    """

    # Definición de almacenamientos disponibles
    STORAGE_SPECS = {
        "queue": {
            "file": "products_list.json",
            "default": [],
            "description": "Cola de productos general para publicar",
        },
        "queue_baby": {
            "file": "products_list_baby.json",
            "default": [],
            "description": "Cola de productos categoría bebés",
        },
        "queue_pets": {
            "file": "products_list_pets.json",
            "default": [],
            "description": "Cola de productos categoría mascotas",
        },
        "queue_tenis": {
            "file": "queue_tenis.json",
            "default": [],
            "description": "Cola de productos categoría tenis",
        },
        "queue_moda": {
            "file": "queue_moda.json",
            "default": [],
            "description": "Cola de productos categoría moda",
        },
        "queue_draft": {
            "file": "products_draft.json",
            "default": [],
            "description": "Borrador de productos para curación manual",
        },
        "published_history": {
            "file": "published_history.json",
            "default": [],
            "description": "Set de IDs/URLs ya publicados",
        },
        "last_published": {
            "file": "last_published.json",
            "default": {},
            "description": "Último producto publicado",
        },
        "website_db": {
            "file": "website_db.json",
            "default": [],
            "description": "Base de datos de landing page (máx 100 productos)",
        },
        "user_state": {
            "file": "user_state.json",
            "default": {
                "paused": False,
                "fb_paused": False,
                "mode": "both",
                "queue_mode": False,
                "active_networks": {
                    "facebook": True,
                    "facebook_bebes": True,
                    "fb_page": True,
                    "telegram": True,
                    "pinterest": True,
                    "tiktok": True,
                    "youtube": True,
                    "web": True,
                },
                "video_niches": {
                    "general": True,
                    "baby": False,
                    "pets": True,
                    "moda": True,
                    "tenis": True,
                },
                "video_mode": "normal",
            },
            "description": "Estado del bot y configuración de usuario",
        },
        "fb_failed_queue": {
            "file": "fb_failed_queue.json",
            "default": [],
            "description": "Cola de grupos FB fallidos para reintentar",
        },
    }

    def __init__(self, cache_enabled=False):
        """
        Args:
            cache_enabled: Si True, cachea datos en memoria (use con cuidado para datos compartidos)
        """
        self.cache_enabled = cache_enabled
        self._cache = {}

    @staticmethod
    def get_path(key: str) -> str:
        """Retorna la ruta completa de un almacenamiento."""
        spec = StorageManager.STORAGE_SPECS.get(key)
        if not spec:
            raise ValueError(f"Almacenamiento desconocido: {key}")
        return os.path.join(Config.BASE_DIR, spec["file"])

    def load(self, key: str, default: Optional[Any] = None) -> Any:
        """
        Carga datos desde archivo JSON.

        Args:
            key: Identificador del almacenamiento (ej: "queue", "user_state")
            default: Valor por defecto si no existe o está vacío

        Returns:
            Datos cargados o default
        """
        spec = self.STORAGE_SPECS.get(key)
        if not spec:
            raise ValueError(f"Almacenamiento desconocido: {key}")

        # Retornar del caché si está disponible
        if self.cache_enabled and key in self._cache:
            return self._cache[key]

        # Cargar desde disco
        path = self.get_path(key)
        data = json_load(path, default=default or spec.get("default"))

        # Cachear si está habilitado
        if self.cache_enabled:
            self._cache[key] = data

        return data

    def save(self, key: str, data: Any, use_atomic=True) -> bool:
        """
        Guarda datos en archivo JSON.

        Args:
            key: Identificador del almacenamiento
            data: Datos a guardar
            use_atomic: Si True, usa guardado atómico (.tmp)

        Returns:
            True si fue exitoso
        """
        spec = self.STORAGE_SPECS.get(key)
        if not spec:
            raise ValueError(f"Almacenamiento desconocido: {key}")

        path = self.get_path(key)

        try:
            if use_atomic:
                json_save_atomic(path, data, indent=2, ensure_ascii=False)
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

            # Actualizar caché si está habilitado
            if self.cache_enabled:
                self._cache[key] = data

            return True
        except Exception as e:
            print(f"[STORAGE] Error guardando {key}: {e}")
            return False

    def invalidate_cache(self, key: Optional[str] = None):
        """Invalida el caché (completo o para una clave específica)."""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    @staticmethod
    def describe() -> Dict[str, str]:
        """Retorna descripciones de todos los almacenamientos."""
        return {
            k: v["description"] for k, v in StorageManager.STORAGE_SPECS.items()
        }
