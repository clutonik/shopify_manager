# shopify_manager

Python package for managing a Shopify store via the Admin GraphQL API.

Provides four classes — `ShopifyUploader`, `ShopifyDeleter`, `ShopifyPublisher`, and `PriceUpdater` — that cover the full product lifecycle: create, price, publish, and delete.

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Setup

All classes share the same constructor signature:

```python
headers = {
    "Content-Type": "application/json",
    "X-Shopify-Access-Token": "<your-admin-api-token>",
}

# optional: basic auth instead of token
auth = ("api-key", "api-password")
```

---

## ShopifyUploader

Creates products in a Shopify store from scraped product data.

```python
from shopify_manager import ShopifyUploader

uploader = ShopifyUploader("your-store.myshopify.com", headers, dry_run=False)
```

### List collections

```python
collections = uploader.get_collection_ids()
# [{"node": {"id": "gid://shopify/Collection/1", "title": "Dining", "handle": "dining"}}, ...]
```

### Look up a collection ID by handle

```python
gid = uploader.get_collection_id_by_handle("dining-tables")
# "gid://shopify/Collection/123456"  or  None if not found
```

### Fetch all products (cursor-paginated)

```python
products = uploader.get_products()
# [{"id": "gid://shopify/Product/1", "title": "Dining Table"}, ...]
```

### Build a product payload

Converts a scraped item dict into a GraphQL `productCreate` body.
Applies a 1.59× retail markup on price automatically.

```python
item = {
    "title": "5302C-18",
    "description": "Solid wood dining chair with upholstered seat.",
    "dimensions": ["20 x 18 x 36H"],
    "images": ["https://example.com/chair_l1.jpg"],
    "price": 120.00,
}

payload = uploader.build_product_payload(
    item,
    collection="dining-chairs",   # collection handle (optional)
    vendor="Mazin Furniture",      # optional
    status="draft",                # "draft" | "active" | "archived"
)
```

### Create a product

```python
response = uploader.create_product(payload)
product_id = response["data"]["productCreate"]["product"]["id"]
```

Set `dry_run=True` on the uploader to log the payload without making any HTTP calls.

---

## ShopifyDeleter

Deletes products by status or by title.

```python
from shopify_manager import ShopifyDeleter

deleter = ShopifyDeleter("your-store.myshopify.com", headers, dry_run=False)
```

### List available sales channels (to preview before deletion)

```python
# Use dry_run=True to preview what would be deleted without making changes
deleter = ShopifyDeleter("your-store.myshopify.com", headers, dry_run=True)
```

### Delete by status

Deletes all products with the given status (`draft`, `active`, or `archived`).

```python
deleted = deleter.delete_by_status("draft")
# [{"id": "gid://shopify/Product/1", "title": "Old Chair", "status": "DRAFT"}, ...]
```

### Delete by name

Deletes products whose title contains the search string (case-insensitive substring match by default).

```python
# substring match — deletes any product containing "5302"
deleted = deleter.delete_by_name("5302")

# exact match — only deletes products whose title equals "5302C-18" exactly
deleted = deleter.delete_by_name("5302C-18", exact=True)
```

Each returned dict has keys `id`, `title`, and `status`.

---

## ShopifyPublisher

Publishes products to Shopify sales channels.

```python
from shopify_manager import ShopifyPublisher

publisher = ShopifyPublisher("your-store.myshopify.com", headers, dry_run=False)
```

### List available sales channels

```python
channels = publisher.get_publications()
# [{"id": "gid://shopify/Publication/1", "name": "Online Store"}, ...]
```

### Publish a single product

```python
publication_ids = ["gid://shopify/Publication/1", "gid://shopify/Publication/2"]
result = publisher.publish_product("gid://shopify/Product/123", publication_ids)
```

### Publish a batch of products

Accepts bare numeric IDs or full GIDs interchangeably.

```python
# publish to all available channels
results = publisher.publish_products([
    "gid://shopify/Product/1",
    "gid://shopify/Product/2",
    12345,          # bare int is automatically wrapped into a GID
])

# publish to specific channels only
results = publisher.publish_products(product_ids, channel_names=["Online Store"])
```

Each result dict has keys `id`, `title`, `published_to` (list of channel names), and `error` (None on success).

---

## PriceUpdater

Updates variant pricing on existing Shopify products. *(In development — the mutation body is defined but the `update_prices` method is not yet implemented.)*

---

## Common options

| Parameter | Description |
|-----------|-------------|
| `shop_base` | Store domain, e.g. `your-store.myshopify.com` |
| `headers` | Dict including `Content-Type` and auth token |
| `dry_run` | `True` to log/return mock responses without HTTP calls |
| `api_version` | Shopify API version string (default: `2024-01`) |
| `auth` | Optional `(api_key, password)` tuple for basic auth |

---

## Tests

```bash
pytest -q
```

Tests live in `tests/` and cover all three implemented classes using `unittest.mock` — no real HTTP calls are made.

| Test file | Covers |
|-----------|--------|
| `tests/test_uploader.py` | `ShopifyUploader` — collections, products, payload building, create |
| `tests/test_deleter.py` | `ShopifyDeleter` — fetch, delete by status, delete by name |
| `tests/test_publisher.py` | `ShopifyPublisher` — publications, publish single, publish batch, GID wrapping |
