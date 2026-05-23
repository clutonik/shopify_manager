"""
ShopifyPublisher – publish Shopify products to sales channels via the GraphQL Admin API.
"""

import logging
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

API_VERSION = "2024-01"


class ShopifyPublisher:
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_publications(self) -> list:
        """Return all publications (sales channels) available in the store.

        Returns a list of dicts with keys ``id`` and ``name``.
        """
        query = """
        query getPublications($first: Int!) {
          publications(first: $first) {
            edges {
              node {
                id
                name
              }
            }
          }
        }
        """
        data = self._post({"query": query, "variables": {"first": 50}})
        edges = data.get("data", {}).get("publications", {}).get("edges") or []
        publications = [edge["node"] for edge in edges if edge.get("node")]
        logger.info("Found %d publication(s): %s", len(publications), [p["name"] for p in publications])
        return publications

    def publish_product(self, product_id: str, publication_ids: list) -> Dict[str, Any]:
        """Publish a single product to the given list of publication IDs.

        Parameters
        - product_id: GraphQL GID, e.g. ``"gid://shopify/Product/12345"``.
        - publication_ids: list of publication GIDs to publish to.

        Returns the raw ``publishablePublish`` result dict.
        """
        mutation = """
        mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) {
          publishablePublish(id: $id, input: $input) {
            publishable {
              ... on Product {
                id
                title
              }
            }
            userErrors { field message }
          }
        }
        """
        pub_input = [{"publicationId": pid} for pid in publication_ids]

        if self.dry_run:
            logger.info("DRY-RUN: would publish %s to %s", product_id, publication_ids)
            return {"mock": True, "id": product_id, "publications": publication_ids}

        data = self._post({"query": mutation, "variables": {"id": product_id, "input": pub_input}})
        result = (data.get("data") or {}).get("publishablePublish", {})
        user_errors = result.get("userErrors") or []
        if user_errors:
            raise RuntimeError(f"Shopify userErrors: {user_errors}")
        return result

    def publish_products(self, product_ids: list, channel_names: Optional[list] = None) -> list:
        """Publish a list of products to sales channels.

        Parameters
        - product_ids: list of product GIDs or plain integer/string IDs.
          Plain IDs are automatically wrapped into the GID format.
        - channel_names: optional list of channel names to publish to (case-insensitive).
          When ``None`` (default) all available channels are used.

        Returns a list of result dicts, one per product, with keys
        ``id``, ``title``, ``published_to``, and ``error`` (if any).
        """
        publications = self.get_publications()

        if channel_names:
            names_lower = {n.lower() for n in channel_names}
            publications = [p for p in publications if p["name"].lower() in names_lower]
            if not publications:
                raise ValueError(
                    f"None of the requested channels {channel_names} were found. "
                    f"Available: {[p['name'] for p in self.get_publications()]}"
                )

        publication_ids = [p["id"] for p in publications]
        pub_names = [p["name"] for p in publications]
        logger.info("Publishing to %d channel(s): %s", len(pub_names), pub_names)

        results = []
        for raw_id in product_ids:
            product_id = _ensure_gid(raw_id)
            try:
                result = self.publish_product(product_id, publication_ids)
                title = (
                    (result.get("publishable") or {}).get("title", "")
                    if not self.dry_run
                    else ""
                )
                logger.info("Published %s (%s) to %s", title or product_id, product_id, pub_names)
                results.append({
                    "id": product_id,
                    "title": title,
                    "published_to": pub_names,
                    "error": None,
                })
            except Exception as e:
                logger.error("Failed to publish %s: %s", product_id, e)
                results.append({
                    "id": product_id,
                    "title": "",
                    "published_to": [],
                    "error": str(e),
                })
        return results


def _ensure_gid(product_id) -> str:
    """Wrap a bare numeric/string ID into a Shopify product GID if needed."""
    s = str(product_id).strip()
    if s.startswith("gid://"):
        return s
    return f"gid://shopify/Product/{s}"
