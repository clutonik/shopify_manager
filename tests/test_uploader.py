import json
from unittest.mock import Mock, patch

import pytest

from shopify_manager import ShopifyUploader


@pytest.fixture
def headers():
    return {"Content-Type": "application/json", "X-Shopify-Access-Token": "fake"}


def make_resp(status=200, data=None):
    m = Mock()
    m.status_code = status
    if data is None:
        data = {}
    m.json = Mock(return_value=data)
    m.text = json.dumps(data)
    return m


def test_get_collection_ids_success(headers):
    data = {"data": {"collections": {"edges": [{"node": {"id": "gid://c1", "title": "C", "handle": "c"}}]}}}
    with patch("requests.post", return_value=make_resp(200, data)) as rp:
        up = ShopifyUploader("shop.test", headers, dry_run=True)
        cols = up.get_collection_ids()
        assert isinstance(cols, list)
        assert cols[0]["node"]["id"] == "gid://c1"
        rp.assert_called_once()


def test_get_collection_id_by_handle_found(headers):
    up = ShopifyUploader("shop.test", headers, dry_run=True)
    # patch instance method to avoid HTTP
    up.get_collection_ids = Mock(return_value=[{"node": {"id": "gid://c2", "handle": "h1"}}])
    assert up.get_collection_id_by_handle("h1") == "gid://c2"
    assert up.get_collection_id_by_handle("nope") is None


def test_get_products_pagination(headers):
    # first page hasNextPage True with one product
    page1 = {"data": {"products": {"edges": [{"cursor": "c1", "node": {"id": "1", "title": "A"}}], "pageInfo": {"hasNextPage": True}}}}
    # second page hasNextPage False
    page2 = {"data": {"products": {"edges": [{"cursor": "c2", "node": {"id": "2", "title": "B"}}], "pageInfo": {"hasNextPage": False}}}}

    resp1 = make_resp(200, page1)
    resp2 = make_resp(200, page2)

    with patch("requests.post", side_effect=[resp1, resp2]) as rp:
        up = ShopifyUploader("shop.test", headers, dry_run=False)
        prods = up.get_products()
        assert len(prods) == 2
        assert prods[0]["title"] == "A"
        assert prods[1]["title"] == "B"
        assert rp.call_count == 2


def test_build_product_payload_includes_collection_and_media(headers):
    up = ShopifyUploader("shop.test", headers, dry_run=True)
    up.get_collection_id_by_handle = Mock(return_value="gid://col123")
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Chair", "description": "Nice", "dimensions": ["10x10"], "images": ["https://img/1.jpg"], "price": "10"}
    body = up.build_product_payload(item, collection="chairs", vendor="V", status="draft")
    assert "query" in body and "variables" in body
    vars = body["variables"]["input"]
    assert vars["title"] == "Chair"
    assert vars["vendor"] == "V"
    assert vars["collectionsToJoin"] == ["gid://col123"]
    media = body["variables"]["media"]
    assert len(media) == 1


def test_create_product_dry_run(headers):
    up = ShopifyUploader("shop.test", headers, dry_run=True)
    body = {"query": "query {}"}
    result = up.create_product(body)
    assert result.get("mock") is True


def test_create_product_success(headers):
    data = {"data": {"productCreate": {"product": {"id": "gid://p1", "title": "X"}, "userErrors": []}}}
    with patch("requests.post", return_value=make_resp(200, data)) as rp:
        up = ShopifyUploader("shop.test", headers, dry_run=False)
        body = {"query": "query {}"}
        resp = up.create_product(body)
        assert resp["data"]["productCreate"]["product"]["id"] == "gid://p1"
        rp.assert_called_once()
