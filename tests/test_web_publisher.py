import unittest

from publishers.web_publisher import WebPublisher


class WebPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_zero_remote_changes_is_success(self):
        publisher = WebPublisher()
        publisher.add_product_to_db = lambda details: False
        publisher.build = lambda: True
        publisher.push_to_github = lambda message: 0

        result = await publisher.publish({"id": "MLM1", "affiliate_url": "https://meli.la/test"})

        self.assertTrue(result)

    async def test_remote_failure_is_not_reported_as_success(self):
        publisher = WebPublisher()
        publisher.add_product_to_db = lambda details: False
        publisher.build = lambda: True

        def fail_push(message):
            raise RuntimeError("GitHub unavailable")

        publisher.push_to_github = fail_push

        result = await publisher.publish({"id": "MLM1", "affiliate_url": "https://meli.la/test"})

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
