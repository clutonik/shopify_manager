"""
This module provides the ShopifyUploader class, which facilitates uploading product data
to a Shopify store using the GraphQL Admin API. It includes functionality for fetching
collections, retrieving existing products, building product payloads with media and
metadata, and executing the product creation mutations.
"""

import json
import logging
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)


API_VERSION = "2024-01"


class ShopifyUploader:
    def __init__(
        self,
        shop_base: str,
        headers: Dict[str, str],
        dry_run: bool = False,
        api_version: Optional[str] = API_VERSION,
        auth: Optional[tuple] = None,
    ) -> None:
        """Create a ShopifyUploader.

        Parameters
        - shop_base: shop domain (e.g. "your-store.myshopify.com").
        - headers: request headers to include (must include Content-Type and auth token when used).
        - dry_run: if True, HTTP requests are not performed and payloads are returned or logged.
        - api_version: Shopify Admin API version string.
        - auth: optional (api_key, password) tuple for basic auth.
        """
        self.shop_base = shop_base
        self.headers = headers
        self.api_version = api_version
        self.dry_run = dry_run
        self.auth = auth

    def get_collection_ids(self):
        """Return a list of collection edge objects from the store.

        The method queries the Admin GraphQL API for up to 100 collections
        and returns the raw `edges` list as returned by Shopify. Each entry
        is a dict with a `node` containing `id`, `title`, and `handle`.

        Returns
        - list: collection edges on success, empty list on error.
        """
        url = f"https://{self.shop_base}/admin/api/{self.api_version}/graphql.json"
        query = """
        {
        collections(first: 100) {
            edges {
            node {
                id
                title
                handle
            }
            }
        }
        }
        """
        response = requests.post(url, json={"query": query}, headers=self.headers)

        if response.status_code == 200:
            collections = response.json()["data"]["collections"]["edges"]
            logger.info("%s | %s", "Collection Title", "Global ID")
            logger.info("%s", "-" * 70)
            return collections
        else:
            logger.error("Error: %s", response.text)
            return []

    def get_collection_id_by_handle(self, handle: str) -> Optional[str]:
        """Lookup a collection global ID by its handle.

        Parameters
        - handle: collection handle string.

        Returns
        - str or None: the GraphQL global id for the collection if found.
        """
        all_collections = self.get_collection_ids()
        for col in all_collections:
            node = col["node"]
            if node.get("handle") == handle:
                return node.get("id")
        return None

    def get_products(self) -> list:
        """Fetch all products from the store using cursor pagination.

        This method pages through the GraphQL `products` connection using
        the `after` cursor until `pageInfo.hasNextPage` is False. It
        returns a flat list of product `node` dicts (each contains `id`
        and `title` for the current query).

        Returns
        - list: list of product nodes collected from all pages.
        """
        url = f"https://{self.shop_base}/admin/api/{self.api_version}/graphql.json"
        all_products: list = []
        cursor: Optional[str] = None
        while True:
            query = """
            query getProducts($first: Int!, $after: String) {
              products(first: $first, after: $after) {
                edges {
                  cursor
                  node {
                    id
                    title
                  }
                }
                pageInfo {
                  hasNextPage
                }
              }
            }
            """
            variables = {"first": 250, "after": cursor}
            resp = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=self.headers,
                auth=self.auth,
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error("Error fetching products: %s", resp.text)
                break
            data = resp.json().get("data", {}).get("products", {})
            edges = data.get("edges") or []
            for edge in edges:
                node = edge.get("node")
                if node:
                    all_products.append(node)
            page_info = data.get("pageInfo", {})
            has_next = page_info.get("hasNextPage")
            if not has_next:
                break
            # set cursor to last edge's cursor for next page
            last_cursor = edges[-1].get("cursor") if edges else None
            if not last_cursor:
                break
            cursor = last_cursor
        return all_products

    def build_product_payload(
        self,
        item: Dict[str, Any],
        collection: Optional[str] = None,
        vendor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a GraphQL productCreate mutation payload.

        Parameters
        - item: product data from the scraper (expects keys like `title`,
          `description`, `dimensions`, `images`, `price`).
        - collection: optional collection handle or id to join the product to.
        - vendor: optional vendor string to set on the product.
        - status: optional product status ('draft', 'active', 'archived').

        Returns
        - dict: a GraphQL body with `query` and `variables` suitable for POSTing
          to the Admin GraphQL endpoint.
        """
        title = item.get("title") or ""
        description = item.get("description") or ""
        dims = item.get("dimensions") or []
        dims_str = "; ".join(dims) if dims else ""
        body_html = description
        if dims_str:
            body_html = (body_html + "<br><br>Dimensions: " + dims_str) if body_html else (
                "Dimensions: " + dims_str
            )

        imgs = []
        for url in item.get("images", [])[:10]:
            imgs.append({"src": url})

        media_variables = []
        for i, img in enumerate(imgs):
            media_obj = {
                "originalSource": img["src"],
                "alt": f"{title}-image-{i+1}",
                "mediaContentType": "IMAGE",
            }
            media_variables.append(media_obj)

        price = item.get("price")
        price_str = None
        if price is not None:
            try:
                p = float(price)
                p = round(p * 1.59, 2)
                price_str = f"{p:.2f}"
            except Exception:
                price_str = str(price)

        tags: list = []
        collection_gid = None
        if collection:
            # accept either a handle or a more explicit id; try handle lookup
            collection_gid = self.get_collection_id_by_handle(collection)

        input_obj: Dict[str, Any] = {}
        input_obj["collectionsToJoin"] = [collection_gid] if collection_gid else []
        if title:
            input_obj["title"] = title
        if body_html:
            input_obj["descriptionHtml"] = body_html
        if vendor:
            input_obj["vendor"] = vendor
        if status:
            s = str(status).strip().lower()
            if s == "draft":
                input_obj["status"] = "DRAFT"
            elif s == "active":
                input_obj["status"] = "ACTIVE"
            elif s == "archived":
                input_obj["status"] = "ARCHIVED"

        if tags:
            input_obj["tags"] = tags

        graphql_mutation = """
        mutation productCreate($input: ProductInput!, $media: [CreateMediaInput!]) {
            productCreate(input: $input, media: $media) {
                product { id title }
                userErrors { field message }
        }
        }
        """

        body = {"query": graphql_mutation, "variables": {"input": input_obj, "media": media_variables}}
        return body

    def create_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a product using the Shopify Admin GraphQL API.

        Parameters
        - payload: either a GraphQL body (contains `query`/`variables`) or
          a REST-style product dict under the `product` key. When `dry_run`
          was set on the uploader, the function logs and returns a mock
          response dict instead of performing HTTP.

        Returns
        - dict: parsed JSON response from Shopify on success; a mock dict
          when `dry_run` is True.

        Raises
        - RuntimeError on HTTP error status or when Shopify returns `userErrors`.
        """
        url = f"https://{self.shop_base}/admin/api/{self.api_version}/graphql.json"

        # If caller already provided a GraphQL body (query/variables), use it directly.
        if isinstance(payload, dict) and ("query" in payload or "variables" in payload):
            body = payload
        else:
            # Build GraphQL input from REST-style payload (backwards compatible)
            prod = payload.get("product", {})
            input_obj: Dict[str, Any] = {}
            if "title" in prod:
                input_obj["title"] = prod["title"]
            if "body_html" in prod:
                input_obj["descriptionHtml"] = prod["body_html"]
            if "vendor" in prod:
                input_obj["vendor"] = prod["vendor"]
            if "status" in prod:
                s = str(prod["status"]).strip().lower()
                if s == "draft":
                    input_obj["status"] = "DRAFT"
                elif s == "active":
                    input_obj["status"] = "ACTIVE"
                elif s == "archived":
                    input_obj["status"] = "ARCHIVED"
            tags = prod.get("tags")
            if isinstance(tags, str):
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                if tag_list:
                    input_obj["tags"] = tag_list
            elif isinstance(tags, list):
                input_obj["tags"] = tags

            graphql_mutation = """
        mutation productCreate($input: ProductInput!) {
        productCreate(input: $input) {
            product { id handle title }
            userErrors { field message }
        }
        }
        """

            body = {"query": graphql_mutation, "variables": {"input": input_obj}}

        if self.dry_run:
            logger.info("DRY-RUN: would POST GraphQL to %s", url)
            logger.info("%s", json.dumps(body, indent=2, ensure_ascii=False))
            return {"mock": True, "body": body}

        resp = requests.post(url, json=body, headers=self.headers, auth=self.auth, timeout=30)
        try:
            data = resp.json()
        except Exception:
            resp.raise_for_status()

        # check for top-level errors
        if resp.status_code >= 400:
            raise RuntimeError(f"Shopify GraphQL error {resp.status_code}: {data}") # type: ignore

        # check userErrors
        pd = data.get("data") or {} # type: ignore
        create_result = pd.get("productCreate") if pd else None
        if create_result:
            user_errors = create_result.get("userErrors") or []
            if user_errors:
                raise RuntimeError(f"Shopify userErrors: {user_errors}")

        return data # type: ignore
