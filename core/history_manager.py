"""
core/history_manager.py
=======================
Gestor centralizado de historial de publicaciones con expiración por tiempo (TTL).
Permite que ofertas publicadas hace más de N días (por defecto 21 días / 3 semanas)
puedan volver a ser aprobadas y publicadas si vuelven a tener un buen descuento.
"""

import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from core.config import Config
from core.storage import json_load, json_save_atomic

DEFAULT_TTL_DAYS = 21


def get_history_ttl_days() -> int:
    """Obtiene los días de expiración del historial desde scraping_config.json."""
    try:
        dyn = Config.get_dynamic_config()
        return int(dyn.get("history_ttl_days", DEFAULT_TTL_DAYS))
    except Exception:
        return DEFAULT_TTL_DAYS


def _rescue_timestamps_from_website_db() -> Dict[str, str]:
    """Rescata timestamps reales de website_db.json y last_published.json."""
    rescued = {}
    try:
        wdb_file = os.path.join(Config.BASE_DIR, "website_db.json")
        if os.path.exists(wdb_file):
            wdb = json_load(wdb_file, default=[])
            if isinstance(wdb, list):
                for p in wdb:
                    pub_at = p.get("published_at")
                    if pub_at:
                        for k in [p.get("id"), p.get("url"), p.get("affiliate_url"), p.get("affiliate_link")]:
                            if k:
                                key = str(k).strip()
                                rescued[key] = str(pub_at)
                                asin_m = re.search(r"/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})", key)
                                if asin_m:
                                    asin = asin_m.group(1) or asin_m.group(2)
                                    rescued[asin] = str(pub_at)
                                mlm_m = re.search(r"MLM-?(\d+)", key)
                                if mlm_m:
                                    rescued[f"MLM{mlm_m.group(1)}"] = str(pub_at)

        last_file = os.path.join(Config.BASE_DIR, "last_published.json")
        if os.path.exists(last_file):
            last = json_load(last_file, default={})
            if isinstance(last, dict) and last.get("timestamp"):
                ts = str(last["timestamp"])
                for k in [last.get("id"), last.get("url")]:
                    if k:
                        key = str(k).strip()
                        rescued[key] = ts
                        asin_m = re.search(r"/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})", key)
                        if asin_m:
                            asin = asin_m.group(1) or asin_m.group(2)
                            rescued[asin] = ts
                        mlm_m = re.search(r"MLM-?(\d+)", key)
                        if mlm_m:
                            rescued[f"MLM{mlm_m.group(1)}"] = ts
    except Exception as e:
        print(f"[HISTORY] Error rescatando timestamps: {e}")
    return rescued


def load_history_map() -> Dict[str, str]:
    """
    Carga el historial completo como diccionario {identificador: iso_timestamp}.
    Si el archivo está en formato legacy (lista plana de strings), lo migra automáticamente.
    """
    history_file = Config.HISTORY_FILE
    data = json_load(history_file, default={})

    # Si ya es un diccionario, normalizarlo y retornarlo
    if isinstance(data, dict):
        return {str(k).strip(): str(v) if v else "" for k, v in data.items() if str(k).strip()}

    # Si es lista legacy, migrar automáticamente
    history_map = {}
    if isinstance(data, list):
        rescued = _rescue_timestamps_from_website_db()
        # Fecha base para registros antiguos sin fecha rescatable (más de 30 días en el pasado)
        fallback_old_date = (datetime.now() - timedelta(days=45)).isoformat()

        for item in data:
            if not item:
                continue
            key = str(item).strip()
            # Si tiene timestamp real de website_db/last_published, asignarlo; sino, fecha vieja
            history_map[key] = rescued.get(key, fallback_old_date)

        # Guardar la versión migrada en disco
        try:
            json_save_atomic(history_file, history_map, indent=2, ensure_ascii=False)
            print(f"[HISTORY] Migrado published_history.json a formato con fecha ({len(history_map)} registros).")
        except Exception as e:
            print(f"[HISTORY] Error guardando historial migrado: {e}")

    return history_map


def load_recent_history(ttl_days: Optional[int] = None) -> Set[str]:
    """
    Retorna un set con los identificadores (IDs, URLs, ASINs) publicados recientemente
    (dentro de la ventana de ttl_days, por defecto 21 días).
    Los productos publicados hace más de ttl_days NO se incluyen aquí, por lo que quedan
    libres para ser reaprobados y republicados.
    """
    if ttl_days is None:
        ttl_days = get_history_ttl_days()

    cutoff = datetime.now() - timedelta(days=ttl_days)
    history_map = load_history_map()
    recent = set()

    for key, ts_str in history_map.items():
        if not key or not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str)
            if dt >= cutoff:
                recent.add(key)
        except Exception:
            # Si la fecha no es parseable, tratar como no reciente para no bloquear de por vida
            pass

    return recent


def is_in_recent_history(
    prod_id: Optional[str] = None,
    url: Optional[str] = None,
    affiliate_url: Optional[str] = None,
    ttl_days: Optional[int] = None,
) -> bool:
    """Verifica si un producto específico está en la ventana de historial reciente."""
    recent = load_recent_history(ttl_days=ttl_days)
    candidates = [prod_id, url, affiliate_url]
    for c in candidates:
        if c and str(c).strip() in recent:
            return True
    return False


def register_in_history(url: str, details: dict, timestamp: Optional[str] = None) -> None:
    """
    Registra de forma atómica un producto en published_history.json con su fecha y hora actual.
    Registra por URL original, enlace de afiliado, ID directo de Mercado Libre y ASIN de Amazon.
    """
    history_file = Config.HISTORY_FILE
    now_iso = timestamp or datetime.now().isoformat()
    history_map = load_history_map()

    keys_to_add = set()

    # 1. Registrar URL original y de afiliado
    if url:
        keys_to_add.add(str(url).strip())
    aff_url = details.get("affiliate_url")
    if aff_url:
        keys_to_add.add(str(aff_url).strip())

    # 2. Registrar ID directo si existe
    direct_id = details.get("id")
    if direct_id:
        keys_to_add.add(str(direct_id).strip())

    # 3. Extraer y registrar ID de Mercado Libre desde URL / título
    match = re.search(r"MLM-?(\d+)", url or "")
    if match:
        keys_to_add.add(f"MLM{match.group(1)}")
    else:
        for field in [aff_url, details.get("title", "")]:
            if field:
                match_alt = re.search(r"MLM-?(\d+)", str(field))
                if match_alt:
                    keys_to_add.add(f"MLM{match_alt.group(1)}")
                    break

    # 4. Extraer y registrar ASIN de Amazon
    asin_match = re.search(r"/dp/([A-Z0-9]{10})|/gp/product/([A-Z0-9]{10})", url or "")
    if asin_match:
        asin = asin_match.group(1) or asin_match.group(2)
        if asin:
            keys_to_add.add(asin)

    # Actualizar timestamps
    keys_to_add.discard("")
    keys_to_add.discard(None)

    for k in keys_to_add:
        history_map[k] = now_iso

    try:
        json_save_atomic(history_file, history_map, indent=2, ensure_ascii=False)
        print(f"[HISTORIAL ATOMICO] Registrado(s) {len(keys_to_add)} identificador(es) con fecha {now_iso[:19]}.")
    except Exception as e:
        print(f"[HISTORIAL ATOMICO] Error guardando historial: {e}")


def get_history_stats(ttl_days: Optional[int] = None) -> dict:
    """Devuelve estadísticas del historial: total, recientes (bloqueados) y expirados (elegibles)."""
    if ttl_days is None:
        ttl_days = get_history_ttl_days()

    history_map = load_history_map()
    recent = load_recent_history(ttl_days=ttl_days)
    total = len(history_map)
    recent_count = len(recent)
    expired_count = total - recent_count

    return {
        "ttl_days": ttl_days,
        "total_entries": total,
        "active_recent": recent_count,
        "expired_eligible": expired_count,
    }
