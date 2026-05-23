"""
ShopifyDeleter – delete Shopify products by status or name via the GraphQL Admin API.
"""

import json
import logging
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

API_VERSION = "2024-01"

_STATUS_MAP = {
    "draft": "DRAFT",
    "active": "ACTIVE",
    "archived": "ARCHIVED",
}


class ShopifyDeleter:
    def __init__(
        self,
        shop_base: str,
        headers: Dict[str, str],
        dry_run: bool = False,
        api_version: Optional[str] = API_VERSION,
        auth: Optional[tuple] = None,
    ) -> None:
        self.shop_base = shop_base
        self.headers = headers
        self.dry_run = dry_run
        self.api_version = api_version
        self.auth = auth

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _graphql_url(self) -> str:
        return f"https://{self.shop_base}/admin/api/{self.api_version}/graphql.json"

    def _post(self, body: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(
            self._graphql_url(),
            json=body,
            headers=self.headers,
            auth=self.auth,
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Shopify HTTP {resp.status_code}: {resp.text}")
        return resp.json()

    def _fetch_products(self, query_filter: Optional[str] = None) -> list:
        """Page through all products, optionally with a Shopify search query string."""
        all_products: list = []
        cursor: Optional[str] = None
        query = """
        query getProducts($first: Int!, $after: String, $query: String) {
          products(first: $first, after: $after, query: $query) {
            edges {
              cursor
              node {
                id
                title
                status
              }
            }
            pageInfo { hasNextPage }
          }
        }
        """
        while True:
            variables: Dict[str, Any] = {"first": 250, "after": cursor}
            if query_filter:
                variables["query"] = query_filter
            data = self._post({"query": query, "variables": variables})
            products_data = data.get("data", {}).get("products", {})
            edges = products_data.get("edges") or []
            for edge in edges:
                node = edge.get("node")
                if node:
                    all_products.append(node)
            if not products_data.get("pageInfo", {}).get("hasNextPage"):
                break
            last_cursor = edges[-1].get("cursor") if edges else None
            if not last_cursor:
                break
            cursor = last_cursor
        return all_products

    def _delete_product(self, product_id: str) -> Dict[str, Any]:
        mutation = """
        mutation productDelete($input: ProductDeleteInput!) {
          productDelete(input: $input) {
            deletedProductId
            userErrors { field message }
          }
        }
        """
        body = {"query": mutation, "variables": {"input": {"id": product_id}}}

        if self.dry_run:
            logger.info("DRY-RUN: would delete product %s", product_id)
            return {"mock": True, "id": product_id}

        data = self._post(body)
        result = (data.get("data") or {}).get("productDelete", {})
        user_errors = result.get("userErrors") or []
        if user_errors:
            raise RuntimeError(f"Shopify userErrors: {user_errors}")
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def delete_by_status(self, status: str) -> list:
        """Delete all products with the given status ('draft', 'active', or 'archived').

        Returns a list of dicts with keys ``id`` and ``title`` for every
        product that was (or would be, in dry-run mode) deleted.
        """
        canonical = _STATUS_MAP.get(status.strip().lower())
        if not canonical:
            raise ValueError(f"Unknown status '{status}'. Choose from: draft, active, archived.")

        logger.info("Fetching products with status=%s …", canonical)
        products = self._fetch_products(query_filter=f"status:{canonical}")
        logger.info("Found %d product(s) with status %s", len(products), canonical)

        deleted = []
        for product in products:
            pid = product["id"]
            title = product.get("title", "")
            try:
                self._delete_product(pid)
                logger.info("Deleted '%s' (%s)", title, pid)
                deleted.append({"id": pid, "title": title, "status": product.get("status")})
            except Exception as e:
                logger.error("Failed to delete '%s' (%s): %s", title, pid, e)
        return deleted

    def delete_by_name(self, name: str, exact: bool = False) -> list:
        """Delete products whose title matches *name*.

        Parameters
        - name: search string to match against product titles.
        - exact: when True only products whose title equals *name* exactly
          (case-insensitive) are deleted; when False any product whose title
          *contains* the string is deleted.

        Returns a list of dicts with keys ``id`` and ``title`` for every
        product that was (or would be, in dry-run mode) deleted.
        """
        logger.info("Fetching products matching title '%s' (exact=%s) …", name, exact)
        products = self._fetch_products(query_filter=f'title:"{name}"')

        if exact:
            products = [p for p in products if p.get("title", "").lower() == name.lower()]
        else:
            products = [p for p in products if name.lower() in p.get("title", "").lower()]

        logger.info("Found %d product(s) matching '%s'", len(products), name)

        deleted = []
        for product in products:
            pid = product["id"]
            title = product.get("title", "")
            try:
                self._delete_product(pid)
                logger.info("Deleted '%s' (%s)", title, pid)
                deleted.append({"id": pid, "title": title, "status": product.get("status")})
            except Exception as e:
                logger.error("Failed to delete '%s' (%s): %s", title, pid, e)
        return deleted
