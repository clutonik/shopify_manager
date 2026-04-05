# shopify_manager

Python helper for uploading products to a Shopify store via the Admin GraphQL API.

## Features

- `ShopifyUploader` class to interact with the Shopify Admin GraphQL API
  - List collections (`get_collection_ids`)
  - Lookup collection global ID by handle (`get_collection_id_by_handle`)
  - Page through products (`get_products`)
  - Build a GraphQL productCreate payload from scraped data (`build_product_payload`)
  - Create products via GraphQL (`create_product`) with optional `dry_run`

## Installation

Install requirements from `requirements.txt` (this project uses `requests`):

```
pip install -r requirements.txt
```

## Quick usage

```python
from shopify_manager import ShopifyUploader

headers = {
		"Content-Type": "application/json",
		"X-Shopify-Access-Token": "your-access-token",
}

uploader = ShopifyUploader("your-store.myshopify.com", headers, dry_run=True)

# list collections
collections = uploader.get_collection_ids()

# lookup a collection global id by handle
gid = uploader.get_collection_id_by_handle("chairs")

# fetch all products (uses cursor pagination)
products = uploader.get_products()

# build a GraphQL payload from a scraped item
item = {
		"title": "Example Chair",
		"description": "Nice chair",
		"dimensions": ["10x10"],
		"images": ["https://example.com/img1.jpg"],
		"price": "19.99",
}
payload = uploader.build_product_payload(item, collection="chairs", vendor="MyVendor", status="draft")

# create product (when dry_run=False this will POST to Shopify)
result = uploader.create_product(payload)
```

## Notes

- The class defaults to Shopify API version `2024-01` but accepts a custom `api_version`.
- Set `dry_run=True` to prevent HTTP calls (useful for testing and inspecting payloads).
- `create_product` accepts either a GraphQL body (with `query`/`variables`) or
  a REST-style `product` dict and will translate it to the GraphQL mutation.
- `build_product_payload` prepares media entries (up to 10 images) and will attempt
  to convert a provided `price` to a numeric string (it applies a fixed multiplier in
  the helper code; inspect the implementation if you need different behavior).

## Tests

Run the unit tests shipped in `tests/` with `pytest`:

```
pytest -q
```

## License

See the `LICENSE` file.
