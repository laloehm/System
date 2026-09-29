"""Importa productos de Apify a products_list.json.

El enlace original se guarda temporalmente en ``affiliate_url`` para que
``affiliate_linker.py`` lo convierta posteriormente a un enlace meli.la.
"""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from core.storage import json_save_atomic, json_load
from core.config import Config


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "apify_products.json"
DEFAULT_DRAFTS = BASE_DIR / "products_draft.json"
PUBLISHED_QUEUE = BASE_DIR / "products_list.json"
DEFAULT_HISTORY = BASE_DIR / "published_history.json"


FIELD_MAP = {
    "id": "SKU",
    "title": "articuloTitulo",
    "offer_price": "nuevoPrecio",
    "list_price": "precioAnterior",
    "discount": "precioDiscount",
    "image_url": "imgDireccion",
    "affiliate_url": "zProductoLink",
}


def load_records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        records = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON invalido en la linea {line_number}: {exc.msg}") from exc
        data = records

    if isinstance(data, dict):
        for key in ("items", "data", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        raise ValueError("El archivo debe contener un producto o una lista de productos.")
    return [record for record in data if isinstance(record, dict)]


def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    data = json_load(path, default=[])
    if not isinstance(data, list):
        raise ValueError(f"{path.name} debe contener una lista JSON.")
    return data


def clean_text(value) -> str:
    return " ".join(str(value or "").split())


def normalize_product_id(value, url: str) -> str:
    for candidate in (clean_text(value).upper(), url.upper()):
        match = re.search(r"MLM(U)?-?(\d+)", candidate)
        if match:
            prefix = "MLMU" if match.group(1) else "MLM"
            return f"{prefix}{match.group(2)}"
    return ""


def normalize_price(value) -> str:
    price = clean_text(value)
    if not price:
        return ""
    price = re.sub(r"\s*(MXN|M\.N\.)\s*", "", price, flags=re.IGNORECASE).strip()
    return price if price.startswith("$") else f"${price}"


def normalize_discount(value) -> str:
    discount = clean_text(value).upper()
    match = re.search(r"\d+(?:[.,]\d+)?\s*%", discount)
    return f"{match.group(0).replace(' ', '')} OFF" if match else discount


def valid_url(value: str, required_host: str | None = None) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return not required_host or required_host in parsed.netloc.lower()


def normalize_record(record: dict) -> tuple[dict | None, str | None]:
    product_url = clean_text(record.get(FIELD_MAP["affiliate_url"]))
    image_url = clean_text(record.get(FIELD_MAP["image_url"]))
    product = {
        "id": normalize_product_id(record.get(FIELD_MAP["id"]), product_url),
        "title": clean_text(record.get(FIELD_MAP["title"])),
        "offer_price": normalize_price(record.get(FIELD_MAP["offer_price"])),
        "list_price": normalize_price(record.get(FIELD_MAP["list_price"])),
        "discount": normalize_discount(record.get(FIELD_MAP["discount"])),
        "image_url": image_url,
        "affiliate_url": product_url,
        "source": "apify",
        "review_status": "pending_affiliate",
    }

    missing = [name for name in ("id", "title", "offer_price", "image_url", "affiliate_url") if not product[name]]
    if missing:
        return None, f"faltan campos: {', '.join(missing)}"
    if not valid_url(product_url, "mercadolibre.com.mx"):
        return None, "zdireccion no es una URL valida de Mercado Libre"
    if not valid_url(image_url):
        return None, "imgDireccion no es una URL valida"

    # Validar que el ahorro en pesos cumpla con la regla estricta del sistema
    has_min_pesos = False
    ahorro_pesos = 0
    min_exigido = Config.MIN_AHORRO_ESTRICTO_PESOS
    try:
        from core.utils import parse_price_pesos
        o_val = parse_price_pesos(product["offer_price"])
        l_val = parse_price_pesos(product["list_price"])
        ahorro_pesos = l_val - o_val
        dyn_config = Config.get_dynamic_config()
        min_exigido = dyn_config.get('min_strict', dyn_config.get('min_strict_savings', Config.MIN_AHORRO_ESTRICTO_PESOS))
        min_p = float(getattr(Config, 'MIN_PRICE', 100.0))
        if ahorro_pesos >= min_exigido and o_val >= min_p:
            has_min_pesos = True
    except Exception:
        pass

    if not has_min_pesos:
        return None, f"descuento insuficiente (ahorro de ${ahorro_pesos:.0f} es menor al mínimo exigido de ${min_exigido})"

    return product, None


def import_records(
    input_path: Path,
    queue_path: Path,
    history_path: Path,
    dry_run: bool = False,
    other_product_paths=None,
) -> dict:
    records = load_records(input_path)
    queue = load_json_list(queue_path)
    history = {str(value) for value in load_json_list(history_path)}

    known_ids = {clean_text(item.get("id")) for item in queue if isinstance(item, dict)}
    known_urls = {clean_text(item.get("affiliate_url")) for item in queue if isinstance(item, dict)}
    for other_path in other_product_paths or []:
        for item in load_json_list(Path(other_path)):
            if isinstance(item, dict):
                known_ids.add(clean_text(item.get("id")))
                known_urls.add(clean_text(item.get("affiliate_url")))
    imported = []
    skipped = []

    for index, record in enumerate(records, start=1):
        product, error = normalize_record(record)
        if error:
            skipped.append({"record": index, "reason": error})
            continue

        if product["id"] in known_ids or product["affiliate_url"] in known_urls:
            skipped.append({"record": index, "id": product["id"], "reason": "duplicado en la cola"})
            continue
        if product["id"] in history or product["affiliate_url"] in history:
            skipped.append({"record": index, "id": product["id"], "reason": "ya publicado"})
            continue

        queue.append(product)
        imported.append(product)
        known_ids.add(product["id"])
        known_urls.add(product["affiliate_url"])

    if imported and not dry_run:
        json_save_atomic(str(queue_path), queue, indent=2, ensure_ascii=False)

    return {
        "input_records": len(records),
        "imported": len(imported),
        "skipped": skipped,
        "dry_run": dry_run,
        "products": imported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte un JSON de Apify al formato de products_list.json")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="JSON exportado por Apify")
    parser.add_argument("--draft", default=str(DEFAULT_DRAFTS), help="Archivo de staging y revision")
    parser.add_argument("--history", default=str(DEFAULT_HISTORY), help="Historial de publicaciones")
    parser.add_argument("--dry-run", action="store_true", help="Valida y muestra el resultado sin escribir la cola")
    args = parser.parse_args()

    result = import_records(
        Path(args.input).resolve(),
        Path(args.draft).resolve(),
        Path(args.history).resolve(),
        dry_run=args.dry_run,
        other_product_paths=[PUBLISHED_QUEUE],
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
