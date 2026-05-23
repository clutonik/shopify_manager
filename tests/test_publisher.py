import json
from unittest.mock import Mock, patch

import pytest

from shopify_manager import ShopifyPublisher
from shopify_manager.publisher import _ensure_gid


@pytest.fixture
def headers():
    return {"Content-Type": "application/json", "X-Shopify-Access-Token": "fake"}


def make_resp(status=200, data=None):
    m = Mock()
    m.status_code = status
    data = data or {}
    m.json = Mock(return_value=data)
    m.text = json.dumps(data)
    return m


def publications_resp(pubs):
    edges = [{"node": p} for p in pubs]
    return {"data": {"publications": {"edges": edges}}}


# ---------------------------------------------------------------------------
# _ensure_gid
# ---------------------------------------------------------------------------

def test_ensure_gid_already_gid():
    assert _ensure_gid("gid://shopify/Product/123") == "gid://shopify/Product/123"


def test_ensure_gid_numeric():
    assert _ensure_gid(123) == "gid://shopify/Product/123"


def test_ensure_gid_string_id():
    assert _ensure_gid("456") == "gid://shopify/Product/456"


def test_ensure_gid_strips_whitespace():
    assert _ensure_gid("  789  ") == "gid://shopify/Product/789"


# ---------------------------------------------------------------------------
# _post
# ---------------------------------------------------------------------------

def test_post_raises_on_http_error(headers):
    with patch("requests.post", return_value=make_resp(500)):
        p = ShopifyPublisher("shop.test", headers)
        with pytest.raises(RuntimeError, match="500"):
            p._post({"query": "{}"})


# ---------------------------------------------------------------------------
# get_publications
# ---------------------------------------------------------------------------

def test_get_publications_returns_list(headers):
    pubs = [
        {"id": "gid://shopify/Publication/1", "name": "Online Store"},
        {"id": "gid://shopify/Publication/2", "name": "Point of Sale"},
    ]
    with patch("requests.post", return_value=make_resp(200, publications_resp(pubs))):
        pub = ShopifyPublisher("shop.test", headers)
        result = pub.get_publications()
    assert len(result) == 2
    assert result[0]["name"] == "Online Store"


def test_get_publications_empty(headers):
    with patch("requests.post", return_value=make_resp(200, publications_resp([]))):
        p = ShopifyPublisher("shop.test", headers)
        assert p.get_publications() == []


# ---------------------------------------------------------------------------
# publish_product
# ---------------------------------------------------------------------------

def test_publish_product_dry_run(headers):
    p = ShopifyPublisher("shop.test", headers, dry_run=True)
    result = p.publish_product("gid://shopify/Product/1", ["gid://shopify/Publication/1"])
    assert result["mock"] is True
    assert result["id"] == "gid://shopify/Product/1"


def test_publish_product_success(headers):
    data = {
        "data": {
            "publishablePublish": {
                "publishable": {"id": "gid://shopify/Product/1", "title": "Chair"},
                "userErrors": [],
            }
        }
    }
    with patch("requests.post", return_value=make_resp(200, data)):
        p = ShopifyPublisher("shop.test", headers)
        result = p.publish_product("gid://shopify/Product/1", ["gid://shopify/Publication/1"])
    assert result["publishable"]["title"] == "Chair"


def test_publish_product_user_errors(headers):
    data = {
        "data": {
            "publishablePublish": {
                "publishable": None,
                "userErrors": [{"field": "id", "message": "Product not found"}],
            }
        }
    }
    with patch("requests.post", return_value=make_resp(200, data)):
        p = ShopifyPublisher("shop.test", headers)
        with pytest.raises(RuntimeError, match="userErrors"):
            p.publish_product("gid://shopify/Product/999", ["gid://shopify/Publication/1"])


def test_publish_product_sends_all_publication_ids(headers):
    data = {"data": {"publishablePublish": {"publishable": {"id": "x", "title": "T"}, "userErrors": []}}}
    with patch("requests.post", return_value=make_resp(200, data)) as rp:
        p = ShopifyPublisher("shop.test", headers)
        pub_ids = ["gid://shopify/Publication/1", "gid://shopify/Publication/2"]
        p.publish_product("gid://shopify/Product/1", pub_ids)
    sent = rp.call_args[1]["json"]["variables"]["input"]
    assert len(sent) == 2
    assert sent[0]["publicationId"] == "gid://shopify/Publication/1"


# ---------------------------------------------------------------------------
# publish_products
# ---------------------------------------------------------------------------

def test_publish_products_all_channels(headers):
    pubs = [{"id": "gid://shopify/Publication/1", "name": "Online Store"}]
    pub_resp = make_resp(200, publications_resp(pubs))
    publish_resp = make_resp(200, {"data": {"publishablePublish": {
        "publishable": {"id": "gid://shopify/Product/1", "title": "Chair"},
        "userErrors": [],
    }}})
    with patch("requests.post", side_effect=[pub_resp, publish_resp]):
        p = ShopifyPublisher("shop.test", headers)
        results = p.publish_products(["gid://shopify/Product/1"])
    assert len(results) == 1
    assert results[0]["error"] is None
    assert "Online Store" in results[0]["published_to"]


def test_publish_products_filters_by_channel_name(headers):
    pubs = [
        {"id": "gid://shopify/Publication/1", "name": "Online Store"},
        {"id": "gid://shopify/Publication/2", "name": "Point of Sale"},
    ]
    pub_resp = make_resp(200, publications_resp(pubs))
    publish_resp = make_resp(200, {"data": {"publishablePublish": {
        "publishable": {"id": "gid://shopify/Product/1", "title": "Chair"},
        "userErrors": [],
    }}})
    with patch("requests.post", side_effect=[pub_resp, publish_resp]) as rp:
        p = ShopifyPublisher("shop.test", headers)
        results = p.publish_products(["gid://shopify/Product/1"], channel_names=["Online Store"])
    # only one publicationId should be sent
    publish_call_body = rp.call_args_list[1][1]["json"]
    assert len(publish_call_body["variables"]["input"]) == 1


def test_publish_products_unknown_channel_raises(headers):
    pubs = [{"id": "gid://shopify/Publication/1", "name": "Online Store"}]
    with patch("requests.post", return_value=make_resp(200, publications_resp(pubs))):
        p = ShopifyPublisher("shop.test", headers)
        with pytest.raises(ValueError, match="None of the requested channels"):
            p.publish_products(["gid://shopify/Product/1"], channel_names=["TikTok Shop"])


def test_publish_products_wraps_bare_ids(headers):
    pubs = [{"id": "gid://shopify/Publication/1", "name": "Online Store"}]
    pub_resp = make_resp(200, publications_resp(pubs))
    publish_resp = make_resp(200, {"data": {"publishablePublish": {
        "publishable": {"id": "gid://shopify/Product/42", "title": "T"},
        "userErrors": [],
    }}})
    with patch("requests.post", side_effect=[pub_resp, publish_resp]) as rp:
        p = ShopifyPublisher("shop.test", headers)
        p.publish_products([42])
    sent_id = rp.call_args_list[1][1]["json"]["variables"]["id"]
    assert sent_id == "gid://shopify/Product/42"


def test_publish_products_records_error_on_failure(headers):
    pubs = [{"id": "gid://shopify/Publication/1", "name": "Online Store"}]
    pub_resp = make_resp(200, publications_resp(pubs))
    err_resp = make_resp(200, {"data": {"publishablePublish": {
        "publishable": None,
        "userErrors": [{"field": "id", "message": "Not found"}],
    }}})
    with patch("requests.post", side_effect=[pub_resp, err_resp]):
        p = ShopifyPublisher("shop.test", headers)
        results = p.publish_products(["gid://shopify/Product/999"])
    assert results[0]["error"] is not None
    assert results[0]["published_to"] == []


def test_publish_products_dry_run(headers):
    pubs = [{"id": "gid://shopify/Publication/1", "name": "Online Store"}]
    with patch("requests.post", return_value=make_resp(200, publications_resp(pubs))):
        p = ShopifyPublisher("shop.test", headers, dry_run=True)
        results = p.publish_products(["gid://shopify/Product/1", "gid://shopify/Product/2"])
    assert len(results) == 2
    assert all(r["error"] is None for r in results)
