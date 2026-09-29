import argparse
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SDK_DIR = BASE_DIR / "vendor" / "creatorsapi-python-sdk"
if str(SDK_DIR) not in sys.path:
    sys.path.insert(0, str(SDK_DIR))


def _load_environment():
    try:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
        return
    except ImportError:
        pass

    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


_load_environment()

try:
    from creatorsapi_python_sdk.api.default_api import DefaultApi
    from creatorsapi_python_sdk.api_client import ApiClient
    from creatorsapi_python_sdk.models.get_items_request_content import GetItemsRequestContent
except ImportError as exc:
    raise RuntimeError(
        "Amazon Creators API SDK dependencies are missing. "
        "Run: pip install -r requirements.txt"
    ) from exc


DEFAULT_RESOURCES = [
    "images.primary.medium",
    "itemInfo.title",
    "itemInfo.features",
    "offersV2.listings.price",
    "offersV2.listings.availability",
    "offersV2.listings.condition",
    "offersV2.listings.dealDetails",
    "offersV2.listings.merchantInfo",
]


class AmazonCreatorsApi:
    def __init__(self):
        settings = {
            "AMAZON_CREATORS_CREDENTIAL_ID": os.getenv("AMAZON_CREATORS_CREDENTIAL_ID"),
            "AMAZON_CREATORS_CREDENTIAL_SECRET": os.getenv("AMAZON_CREATORS_CREDENTIAL_SECRET"),
            "AMAZON_CREATORS_CREDENTIAL_VERSION": os.getenv("AMAZON_CREATORS_CREDENTIAL_VERSION"),
            "AMAZON_CREATORS_MARKETPLACE": os.getenv("AMAZON_CREATORS_MARKETPLACE", "www.amazon.com.mx"),
            "AMAZON_PARTNER_TAG": os.getenv("AMAZON_PARTNER_TAG"),
        }
        missing = [name for name, value in settings.items() if not value]
        if missing:
            raise ValueError(f"Missing Amazon Creators API settings: {', '.join(missing)}")

        api_client = ApiClient(
            credential_id=settings["AMAZON_CREATORS_CREDENTIAL_ID"],
            credential_secret=settings["AMAZON_CREATORS_CREDENTIAL_SECRET"],
            version=settings["AMAZON_CREATORS_CREDENTIAL_VERSION"].lstrip("vV"),
        )
        self.api = DefaultApi(api_client)
        self.marketplace = settings["AMAZON_CREATORS_MARKETPLACE"]
        self.partner_tag = settings["AMAZON_PARTNER_TAG"]

    def get_items(self, item_ids):
        asins = [item_id.strip().upper() for item_id in item_ids]
        invalid = [asin for asin in asins if not re.fullmatch(r"[A-Z0-9]{10}", asin)]
        if invalid:
            raise ValueError(f"Invalid ASIN: {', '.join(invalid)}")

        request = GetItemsRequestContent(
            partner_tag=self.partner_tag,
            item_ids=asins,
            resources=DEFAULT_RESOURCES,
        )
        response = self.api.get_items(
            x_marketplace=self.marketplace,
            get_items_request_content=request,
        )
        return response.to_dict()


def summarize_response(response):
    summaries = []
    items = response.get("itemsResult", {}).get("items", [])
    for item in items:
        title = item.get("itemInfo", {}).get("title", {}).get("displayValue", "")
        image = item.get("images", {}).get("primary", {}).get("medium", {}).get("url", "")
        listings = item.get("offersV2", {}).get("listings", [])
        price = listings[0].get("price", {}).get("money", {}) if listings else {}
        summaries.append(
            {
                "asin": item.get("asin", ""),
                "title": title,
                "detail_page_url": item.get("detailPageURL", ""),
                "image_url": image,
                "price": price,
            }
        )
    return summaries


def main():
    parser = argparse.ArgumentParser(description="Test Amazon Creators API with one or more ASINs")
    parser.add_argument("asin", nargs="+", help="Amazon ASIN, for example B0CZ7R8CGX")
    args = parser.parse_args()

    response = AmazonCreatorsApi().get_items(args.asin)
    print(json.dumps(summarize_response(response), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
