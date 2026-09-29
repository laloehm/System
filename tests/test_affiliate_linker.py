import unittest

from affiliate_linker import map_result_lines, needs_affiliate


class AffiliateLinkerTests(unittest.TestCase):
    def test_partial_results_keep_original_positions(self):
        urls = [f"https://mercadolibre.com.mx/product-{index}" for index in range(4)]
        lines = [
            "Esta URL no esta permitida en el Programa.",
            "https://meli.la/first",
            "Esta URL no es de Mercado Libre Mexico.",
            "https://meli.la/second",
        ]

        mapping = map_result_lines(urls, lines)

        self.assertIsNone(mapping[urls[0]])
        self.assertEqual(mapping[urls[1]], "https://meli.la/first")
        self.assertIsNone(mapping[urls[2]])
        self.assertEqual(mapping[urls[3]], "https://meli.la/second")

    def test_rejected_product_is_not_retried(self):
        product = {
            "affiliate_url": "https://articulo.mercadolibre.com.mx/MLM-1-_JM",
            "affiliate_status": "rejected",
        }

        self.assertFalse(needs_affiliate(product))


if __name__ == "__main__":
    unittest.main()
