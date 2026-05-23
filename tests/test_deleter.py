import json
from unittest.mock import Mock, call, patch

import pytest

from shopify_manager import ShopifyDeleter


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


def products_page(nodes, has_next=False):
    edges = [{"cursor": f"c{i}", "node": n} for i, n in enumerate(nodes)]
    return {"data": {"products": {"edges": edges, "pageInfo": {"hasNextPage": has_next}}}}


# ---------------------------------------------------------------------------
# _post
# ---------------------------------------------------------------------------

def test_post_raises_on_http_error(headers):
    with patch("requests.post", return_value=make_resp(500, {"error": "oops"})):
        d = ShopifyDeleter("shop.test", headers)
        with pytest.raises(RuntimeError, match="500"):
            d._post({"query": "{}"})


# ---------------------------------------------------------------------------
# _fetch_products
# ---------------------------------------------------------------------------

def test_fetch_products_single_page(headers):
    node = {"id": "gid://shopify/Product/1", "title": "Chair", "status": "DRAFT"}
    data = products_page([node], has_next=False)
    with patch("requests.post", return_value=make_resp(200, data)):
        d = ShopifyDeleter("shop.test", headers)
        products = d._fetch_products()
    assert len(products) == 1
    assert products[0]["title"] == "Chair"


def test_fetch_products_pagination(headers):
    page1 = products_page(
        [{"id": "gid://shopify/Product/1", "title": "A", "status": "DRAFT"}],
        has_next=True,
    )
    page2 = products_page(
        [{"id": "gid://shopify/Product/2", "title": "B", "status": "ACTIVE"}],
        has_next=False,
    )
    with patch("requests.post", side_effect=[make_resp(200, page1), make_resp(200, page2)]) as rp:
        d = ShopifyDeleter("shop.test", headers)
        products = d._fetch_products()
    assert len(products) == 2
    assert rp.call_count == 2


def test_fetch_products_with_query_filter(headers):
    data = products_page([], has_next=False)
    with patch("requests.post", return_value=make_resp(200, data)) as rp:
        d = ShopifyDeleter("shop.test", headers)
        d._fetch_products(query_filter="status:DRAFT")
    call_body = rp.call_args[1]["json"]
    assert call_body["variables"]["query"] == "status:DRAFT"


# ---------------------------------------------------------------------------
# _delete_product
# ---------------------------------------------------------------------------

def test_delete_product_dry_run(headers, capsys):
    d = ShopifyDeleter("shop.test", headers, dry_run=True)
    result = d._delete_product("gid://shopify/Product/99")
    assert result["mock"] is True
    assert result["id"] == "gid://shopify/Product/99"


def test_delete_product_success(headers):
    data = {"data": {"productDelete": {"deletedProductId": "gid://shopify/Product/1", "userErrors": []}}}
    with patch("requests.post", return_value=make_resp(200, data)):
        d = ShopifyDeleter("shop.test", headers)
        result = d._delete_product("gid://shopify/Product/1")
    assert result["deletedProductId"] == "gid://shopify/Product/1"


def test_delete_product_user_errors(headers):
    data = {"data": {"productDelete": {"deletedProductId": None, "userErrors": [{"field": "id", "message": "Not found"}]}}}
    with patch("requests.post", return_value=make_resp(200, data)):
        d = ShopifyDeleter("shop.test", headers)
        with pytest.raises(RuntimeError, match="userErrors"):
            d._delete_product("gid://shopify/Product/404")


# ---------------------------------------------------------------------------
# delete_by_status
# ---------------------------------------------------------------------------

def test_delete_by_status_invalid(headers):
    d = ShopifyDeleter("shop.test", headers)
    with pytest.raises(ValueError, match="Unknown status"):
        d.delete_by_status("pending")


def test_delete_by_status_dry_run(headers):
    node = {"id": "gid://shopify/Product/1", "title": "Draft Chair", "status": "DRAFT"}
    with patch("requests.post", return_value=make_resp(200, products_page([node]))):
        d = ShopifyDeleter("shop.test", headers, dry_run=True)
        deleted = d.delete_by_status("draft")
    assert len(deleted) == 1
    assert deleted[0]["title"] == "Draft Chair"


def test_delete_by_status_skips_failed(headers):
    nodes = [
        {"id": "gid://shopify/Product/1", "title": "A", "status": "DRAFT"},
        {"id": "gid://shopify/Product/2", "title": "B", "status": "DRAFT"},
    ]
    fetch_resp = make_resp(200, products_page(nodes))
    delete_ok = {"data": {"productDelete": {"deletedProductId": "gid://shopify/Product/1", "userErrors": []}}}
    delete_err = {"data": {"productDelete": {"deletedProductId": None, "userErrors": [{"field": "id", "message": "fail"}]}}}
    with patch("requests.post", side_effect=[fetch_resp, make_resp(200, delete_ok), make_resp(200, delete_err)]):
        d = ShopifyDeleter("shop.test", headers)
        deleted = d.delete_by_status("draft")
    assert len(deleted) == 1
    assert deleted[0]["title"] == "A"


# ---------------------------------------------------------------------------
# delete_by_name
# ---------------------------------------------------------------------------

def test_delete_by_name_substring(headers):
    nodes = [
        {"id": "gid://shopify/Product/1", "title": "Dining Table 48", "status": "ACTIVE"},
        {"id": "gid://shopify/Product/2", "title": "Dining Chair", "status": "ACTIVE"},
    ]
    delete_resp = {"data": {"productDelete": {"deletedProductId": "x", "userErrors": []}}}
    with patch("requests.post", side_effect=[
        make_resp(200, products_page(nodes)),
        make_resp(200, delete_resp),
        make_resp(200, delete_resp),
    ]):
        d = ShopifyDeleter("shop.test", headers)
        deleted = d.delete_by_name("dining")
    assert len(deleted) == 2


def test_delete_by_name_exact(headers):
    nodes = [
        {"id": "gid://shopify/Product/1", "title": "Chair", "status": "ACTIVE"},
        {"id": "gid://shopify/Product/2", "title": "Chair Deluxe", "status": "ACTIVE"},
    ]
    delete_resp = {"data": {"productDelete": {"deletedProductId": "x", "userErrors": []}}}
    with patch("requests.post", side_effect=[
        make_resp(200, products_page(nodes)),
        make_resp(200, delete_resp),
    ]):
        d = ShopifyDeleter("shop.test", headers)
        deleted = d.delete_by_name("Chair", exact=True)
    assert len(deleted) == 1
    assert deleted[0]["title"] == "Chair"


def test_delete_by_name_case_insensitive_exact(headers):
    nodes = [{"id": "gid://shopify/Product/1", "title": "CHAIR", "status": "ACTIVE"}]
    delete_resp = {"data": {"productDelete": {"deletedProductId": "x", "userErrors": []}}}
    with patch("requests.post", side_effect=[make_resp(200, products_page(nodes)), make_resp(200, delete_resp)]):
        d = ShopifyDeleter("shop.test", headers)
        deleted = d.delete_by_name("chair", exact=True)
    assert len(deleted) == 1


def test_delete_by_name_no_matches(headers):
    with patch("requests.post", return_value=make_resp(200, products_page([]))):
        d = ShopifyDeleter("shop.test", headers)
        deleted = d.delete_by_name("nonexistent")
    assert deleted == []
