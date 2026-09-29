import unittest

from product_confidence import evaluate_confidence, parse_price, title_similarity


class ProductConfidenceTests(unittest.TestCase):
    def test_high_confidence_product_is_approved(self):
        product = {
            "title": "Tenis Adidas Duramo SL 2 Hombre Blanco",
            "affiliate_url": "https://meli.la/example",
        }
        live = {
            "title": "Tenis Adidas Duramo SL 2 para Hombre Blanco",
            "offer_price": "$899",
            "list_price": "$1,499",
            "discount": "40% OFF",
            "image_url": "https://http2.mlstatic.com/image.webp",
        }

        result = evaluate_confidence(product, live)

        self.assertTrue(result["approved"])
        self.assertGreaterEqual(result["score"], 90)

    def test_title_mismatch_requires_review(self):
        product = {
            "title": "Tenis Adidas Duramo SL 2 Hombre Blanco",
            "affiliate_url": "https://meli.la/example",
        }
        live = {
            "title": "Perfume Carolina Herrera 100 ml",
            "offer_price": "$899",
            "list_price": "$1,499",
            "discount": "40% OFF",
            "image_url": "https://http2.mlstatic.com/image.webp",
        }

        result = evaluate_confidence(product, live)

        self.assertFalse(result["approved"])

    def test_price_parser_handles_mexican_formats(self):
        self.assertEqual(parse_price("$1,499"), 1499.0)
        self.assertEqual(parse_price("$697.99"), 697.99)

    def test_title_similarity_uses_product_terms(self):
        score = title_similarity("Tenis Adidas Duramo Hombre", "Adidas Tenis Duramo para Hombre")
        self.assertGreaterEqual(score, 0.7)


if __name__ == "__main__":
    unittest.main()
