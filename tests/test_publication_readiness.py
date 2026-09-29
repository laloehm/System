import unittest

from core.utils import is_product_ready_for_publication


class PublicationReadinessTests(unittest.TestCase):
    def test_ml_raw_url_is_not_ready(self):
        product = {"id": "MLM123", "affiliate_url": "https://articulo.mercadolibre.com.mx/MLM-123-_JM"}
        self.assertFalse(is_product_ready_for_publication(product))

    def test_ml_affiliate_url_is_ready(self):
        product = {"id": "MLM123", "affiliate_url": "https://meli.la/example"}
        self.assertTrue(is_product_ready_for_publication(product))

    def test_rejected_product_is_not_ready(self):
        product = {
            "id": "MLM123",
            "affiliate_url": "https://meli.la/example",
            "affiliate_status": "rejected",
        }
        self.assertFalse(is_product_ready_for_publication(product))

    def test_amazon_url_is_ready(self):
        product = {"id": "B012345678", "affiliate_url": "https://www.amazon.com.mx/dp/B012345678?tag=test-20"}
        self.assertTrue(is_product_ready_for_publication(product))


if __name__ == "__main__":
    unittest.main()
