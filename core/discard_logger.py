"""
discard_logger.py
Sistema de logging para productos descartados en el scraper.
Mantiene un registro atómico y persistente de por qué cada producto fue rechazado.
"""
import os
import json
from datetime import datetime, timedelta
from core.storage import json_load, json_save_atomic

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISCARDED_FILE = os.path.join(BASE_DIR, "discarded_products.json")


def log_discarded_product(
    product_id: str,
    title: str,
    reason: str,
    details: dict = None,
    url: str = "",
    offer_price: str = "",
    list_price: str = "",
    discount: str = "",
    scraper_source: str = "unknown"
) -> None:
    """
    Registra un producto descartado con toda la información relevante.

    Args:
        product_id: ID único del producto (ej: MLM123456)
        title: Título del producto
        reason: Motivo del descarte (ej: "Blacklist: suplemento")
        details: Dict adicional con detalles técnicos del descarte
        url: URL del producto
        offer_price: Precio con oferta (ej: "$1200")
        list_price: Precio original (ej: "$2400")
        discount: Descuento (ej: "50% OFF")
        scraper_source: Fuente del scraper (ej: "ml_offers_scraper", "orchestrator")
    """
    try:
        # Cargar historial existente
        history = json_load(DISCARDED_FILE, default=[])
        if not isinstance(history, list):
            history = []

        # Crear entrada
        entry = {
            "id": product_id,
            "title": title,
            "reason": reason,
            "details": details or {},
            "url": url,
            "offer_price": offer_price,
            "list_price": list_price,
            "discount": discount,
            "timestamp": datetime.now().isoformat(),
            "scraper_source": scraper_source
        }

        # Agregar al principio (más reciente primero)
        history.insert(0, entry)

        # Mantener un máximo de 10,000 registros para no ocupar demasiado espacio
        if len(history) > 10000:
            history = history[:10000]

        # Guardar de forma atómica
        json_save_atomic(DISCARDED_FILE, history, indent=2, ensure_ascii=False)

    except Exception as e:
        print(f"[DISCARD_LOGGER] Error registrando producto descartado {product_id}: {e}")


def get_discard_summary() -> dict:
    """
    Retorna un resumen del historial de descartados agrupado por razón.
    """
    try:
        history = json_load(DISCARDED_FILE, default=[])
        if not isinstance(history, list):
            return {"total": 0, "summary": {}}

        summary = {}
        for entry in history:
            reason = entry.get("reason", "Unknown")
            summary[reason] = summary.get(reason, 0) + 1

        return {
            "total": len(history),
            "summary": summary
        }
    except Exception as e:
        print(f"[DISCARD_LOGGER] Error calculando resumen: {e}")
        return {"total": 0, "summary": {}}


def get_discarded_products(
    days: int = 7,
    reason: str = None,
    limit: int = 100,
    offset: int = 0
) -> dict:
    """
    Obtiene productos descartados con filtros opcionales.

    Args:
        days: Últimos N días (None para todos)
        reason: Filtrar por razón específica
        limit: Máximo número de registros
        offset: Desplazamiento para paginación

    Returns:
        Dict con total, registros paginados y resumen
    """
    try:
        history = json_load(DISCARDED_FILE, default=[])
        if not isinstance(history, list):
            history = []

        # Filtrar por días si es necesario
        if days:
            cutoff = datetime.now() - timedelta(days=days)
            def _is_recent(h):
                ts = h.get("timestamp", "")
                if not ts:
                    return False
                try:
                    return datetime.fromisoformat(ts) >= cutoff
                except Exception:
                    return False
            history = [h for h in history if _is_recent(h)]

        # Filtrar por razón si es necesario
        if reason:
            history = [h for h in history if h.get("reason") == reason]

        # Calcular resumen
        summary = {}
        for entry in history:
            r = entry.get("reason", "Unknown")
            summary[r] = summary.get(r, 0) + 1

        # Paginación
        total = len(history)
        paginated = history[offset:offset + limit]

        return {
            "total": total,
            "discarded": paginated,
            "summary": summary,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        print(f"[DISCARD_LOGGER] Error obteniendo descartados: {e}")
        return {
            "total": 0,
            "discarded": [],
            "summary": {},
            "limit": limit,
            "offset": offset
        }


def clear_old_discarded(days: int = 30) -> int:
    """
    Limpia descartados más antiguos de N días. Retorna cantidad eliminada.
    """
    try:
        from datetime import timedelta
        history = json_load(DISCARDED_FILE, default=[])
        if not isinstance(history, list):
            return 0

        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(history)
        def _is_recent(h):
            ts = h.get("timestamp", "")
            if not ts:
                return False
            try:
                return datetime.fromisoformat(ts) >= cutoff
            except Exception:
                return False
        history = [h for h in history if _is_recent(h)]

        removed = original_count - len(history)
        if removed > 0:
            json_save_atomic(DISCARDED_FILE, history, indent=2, ensure_ascii=False)

        return removed
    except Exception as e:
        print(f"[DISCARD_LOGGER] Error limpiando descartados: {e}")
        return 0


def delete_discarded_product(product_id: str, timestamp: str = None) -> bool:
    """Elimina un producto específico del historial de descartados (opcionalmente por timestamp)."""
    try:
        history = json_load(DISCARDED_FILE, default=[])
        if not isinstance(history, list):
            return False

        if timestamp:
            filtered = [h for h in history if not (str(h.get("id")) == str(product_id) and h.get("timestamp") == timestamp)]
        else:
            filtered = [h for h in history if str(h.get("id")) != str(product_id)]

        if len(filtered) < len(history):
            json_save_atomic(DISCARDED_FILE, filtered, indent=2, ensure_ascii=False)
            return True
        return False
    except Exception as e:
        print(f"[DISCARD_LOGGER] Error eliminando producto descartado {product_id}: {e}")
        return False


def clear_all_discarded_records() -> int:
    """Vacía completamente el historial de descartados."""
    try:
        history = json_load(DISCARDED_FILE, default=[])
        count = len(history) if isinstance(history, list) else 0
        json_save_atomic(DISCARDED_FILE, [], indent=2, ensure_ascii=False)
        return count
    except Exception as e:
        print(f"[DISCARD_LOGGER] Error vaciando descartados: {e}")
        return 0

