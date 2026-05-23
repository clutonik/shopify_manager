from shopify_manager import ShopifyUploader as uploader

class PriceUpdater:
    def __init__(self, shop_base: str, headers: dict, auth=None, dry_run=False, api_version=uploader.API_VERSION):
        self.shop_base = shop_base
        self.headers = headers
        self.auth = auth
        self.dry_run = dry_run
        self.api_version = api_version  # Update to latest stable version as needed

    def update_prices(self, price_updates):
        mutation = """
        productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
        productVariantsBulkUpdate(productId: $productId, variants: $variants) {
            productVariants {
            id
            price
            }
            userErrors {
            field
            message
            }
        }
        }
        """
        pass