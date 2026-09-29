import json
import tempfile
import unittest
from pathlib import Path

from import_apify import import_records, normalize_record


APIFY_PRODUCT = {
    "articuloTitulo": "Tenis adidas Basketball Hoops Classic Unisex Negro Ki1113",
    "nuevoPrecio": "659",
    "precioAnterior": "1099",
    "precioDiscount": "40% OFF",
    "imgDireccion": "https://http2.mlstatic.com/D_NQ_NP_example.webp",
    "zdireccion": "https://articulo.mercadolibre.com.mx/MLM-4464029374-producto-_JM",
    "SKU": "MLM4464029374",
}


class ImportApifyTests(unittest.TestCase):
    def test_normalizes_apify_product(self):
        product, error = normalize_record(APIFY_PRODUCT)

        self.assertIsNone(error)
        self.assertEqual(product["id"], "MLM4464029374")
        self.assertEqual(product["offer_price"], "$659")
        self.assertEqual(product["list_price"], "$1099")
        self.assertEqual(product["discount"], "40% OFF")
        self.assertEqual(product["affiliate_url"], APIFY_PRODUCT["zdireccion"])

    def test_imports_once_and_skips_duplicate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "apify.json"
            queue_path = root / "queue.json"
            history_path = root / "history.json"
            input_path.write_text(json.dumps([APIFY_PRODUCT, APIFY_PRODUCT]), encoding="utf-8")
            queue_path.write_text("[]", encoding="utf-8")
            history_path.write_text("[]", encoding="utf-8")

            result = import_records(input_path, queue_path, history_path)
            queue = json.loads(queue_path.read_text(encoding="utf-8"))

            self.assertEqual(result["imported"], 1)
            self.assertEqual(len(result["skipped"]), 1)
            self.assertEqual(len(queue), 1)
            self.assertFalse((root / "queue.json.tmp").exists())

    def test_dry_run_does_not_change_queue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "apify.json"
            queue_path = root / "queue.json"
            history_path = root / "history.json"
            input_path.write_text(json.dumps(APIFY_PRODUCT), encoding="utf-8")
            queue_path.write_text("[]", encoding="utf-8")
            history_path.write_text("[]", encoding="utf-8")

            result = import_records(input_path, queue_path, history_path, dry_run=True)

            self.assertEqual(result["imported"], 1)
            self.assertEqual(queue_path.read_text(encoding="utf-8"), "[]")


if __name__ == "__main__":
    unittest.main()
