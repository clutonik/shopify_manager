import json
import sys
from unittest.mock import MagicMock, Mock, patch

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


# ---------------------------------------------------------------------------
# get_metafield_id_by_key
# ---------------------------------------------------------------------------

def test_get_metafield_id_by_key_found(headers):
    data = {"data": {"metafields": {"edges": [{"node": {"id": "gid://m1"}}]}}}
    with patch("requests.post", return_value=make_resp(200, data)):
        up = ShopifyUploader("shop.test", headers)
        assert up.get_metafield_id_by_key("length") == "gid://m1"


def test_get_metafield_id_by_key_not_found(headers):
    data = {"data": {"metafields": {"edges": []}}}
    with patch("requests.post", return_value=make_resp(200, data)):
        up = ShopifyUploader("shop.test", headers)
        assert up.get_metafield_id_by_key("nonexistent") is None


def test_get_metafield_id_by_key_http_error(headers):
    with patch("requests.post", return_value=make_resp(500, {"error": "fail"})):
        up = ShopifyUploader("shop.test", headers)
        assert up.get_metafield_id_by_key("length") is None


# ---------------------------------------------------------------------------
# get_collection_ids error path
# ---------------------------------------------------------------------------

def test_get_collection_ids_error(headers):
    with patch("requests.post", return_value=make_resp(500, {})):
        up = ShopifyUploader("shop.test", headers)
        assert up.get_collection_ids() == []


# ---------------------------------------------------------------------------
# get_products edge cases
# ---------------------------------------------------------------------------

def test_get_products_http_error(headers):
    with patch("requests.post", return_value=make_resp(500, {})):
        up = ShopifyUploader("shop.test", headers)
        assert up.get_products() == []


def test_get_products_empty_edges_with_next_page(headers):
    # hasNextPage True but edges empty — last_cursor will be None, should break
    page = {"data": {"products": {"edges": [], "pageInfo": {"hasNextPage": True}}}}
    with patch("requests.post", return_value=make_resp(200, page)):
        up = ShopifyUploader("shop.test", headers)
        assert up.get_products() == []


# ---------------------------------------------------------------------------
# build_product_payload — dimension parsing, price exception, status branches
# ---------------------------------------------------------------------------

def test_build_product_payload_with_dimensions(headers):
    up = ShopifyUploader("shop.test", headers)
    up.get_collection_id_by_handle = Mock(return_value=None)
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Table", "dimensions": ["48 x 24 x 30H"], "price": "100"}
    body = up.build_product_payload(item)
    metas = {m["key"]: m["value"] for m in body["variables"]["input"]["metafields"]}
    assert metas["length"] == "48"
    assert metas["width"] == "24"
    assert metas["height"] == "30"


def test_build_product_payload_price_invalid(headers):
    up = ShopifyUploader("shop.test", headers)
    up.get_collection_id_by_handle = Mock(return_value=None)
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Table", "price": "not_a_price"}
    body = up.build_product_payload(item)
    assert body is not None


def test_build_product_payload_status_active(headers):
    up = ShopifyUploader("shop.test", headers)
    up.get_collection_id_by_handle = Mock(return_value=None)
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Table", "price": "100"}
    body = up.build_product_payload(item, status="active")
    assert body["variables"]["input"]["status"] == "ACTIVE"


def test_build_product_payload_status_archived(headers):
    up = ShopifyUploader("shop.test", headers)
    up.get_collection_id_by_handle = Mock(return_value=None)
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Table", "price": "100"}
    body = up.build_product_payload(item, status="archived")
    assert body["variables"]["input"]["status"] == "ARCHIVED"


# ---------------------------------------------------------------------------
# build_product_payload — OpenAI subtitle generation
# ---------------------------------------------------------------------------

def _make_openai_mock(content: str) -> MagicMock:
    mock_message = Mock()
    mock_message.content = content
    mock_choice = Mock()
    mock_choice.message = mock_message
    mock_response = Mock()
    mock_response.choices = [mock_choice]
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    return mock_openai


def test_build_product_payload_openai_subtitle(headers):
    up = ShopifyUploader("shop.test", headers)
    up.get_collection_id_by_handle = Mock(return_value=None)
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Chair", "description": "A nice chair", "price": "50"}

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), \
         patch.dict("sys.modules", {"openai": _make_openai_mock("Comfortable dining chair")}):
        body = up.build_product_payload(item)

    metas = {m["key"]: m["value"] for m in body["variables"]["input"]["metafields"]}
    assert metas["subtitle"] == "Comfortable dining chair"


def test_build_product_payload_openai_subtitle_truncated(headers):
    up = ShopifyUploader("shop.test", headers)
    up.get_collection_id_by_handle = Mock(return_value=None)
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Chair", "description": "A nice chair", "price": "50"}
    long_subtitle = "A" * 60

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), \
         patch.dict("sys.modules", {"openai": _make_openai_mock(long_subtitle)}):
        body = up.build_product_payload(item)

    metas = {m["key"]: m["value"] for m in body["variables"]["input"]["metafields"]}
    assert len(metas["subtitle"]) <= 50
    assert metas["subtitle"].endswith("...")


def test_build_product_payload_openai_exception(headers):
    up = ShopifyUploader("shop.test", headers)
    up.get_collection_id_by_handle = Mock(return_value=None)
    up.get_metafield_id_by_key = Mock(return_value=None)
    item = {"title": "Chair", "description": "A nice chair", "price": "50"}

    mock_openai = MagicMock()
    mock_openai.OpenAI.side_effect = Exception("API error")

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), \
         patch.dict("sys.modules", {"openai": mock_openai}):
        body = up.build_product_payload(item)

    metas = {m["key"]: m["value"] for m in body["variables"]["input"]["metafields"]}
    assert metas["subtitle"] == ""


# ---------------------------------------------------------------------------
# create_product — REST-style payload (backwards-compat branch)
# ---------------------------------------------------------------------------

def test_create_product_rest_style_draft_string_tags(headers):
    up = ShopifyUploader("shop.test", headers, dry_run=True)
    payload = {"product": {"title": "Chair", "body_html": "<p>desc</p>", "vendor": "V", "status": "draft", "tags": "a, b"}}
    result = up.create_product(payload)
    assert result["mock"] is True


def test_create_product_rest_style_active_list_tags(headers):
    up = ShopifyUploader("shop.test", headers, dry_run=True)
    payload = {"product": {"title": "Chair", "status": "active", "tags": ["a", "b"]}}
    result = up.create_product(payload)
    assert result["mock"] is True


def test_create_product_rest_style_archived(headers):
    up = ShopifyUploader("shop.test", headers, dry_run=True)
    payload = {"product": {"title": "Chair", "status": "archived"}}
    result = up.create_product(payload)
    assert result["mock"] is True


# ---------------------------------------------------------------------------
# create_product — HTTP error and JSON decode error paths
# ---------------------------------------------------------------------------

def test_create_product_json_decode_error(headers):
    mock_resp = Mock()
    mock_resp.status_code = 500
    mock_resp.json.side_effect = ValueError("No JSON")
    mock_resp.raise_for_status.side_effect = RuntimeError("HTTP 500")
    with patch("requests.post", return_value=mock_resp):
        up = ShopifyUploader("shop.test", headers, dry_run=False)
        with pytest.raises(RuntimeError):
            up.create_product({"query": "query {}"})


def test_create_product_http_error_status(headers):
    mock_resp = Mock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"errors": "Bad Request"}
    with patch("requests.post", return_value=mock_resp):
        up = ShopifyUploader("shop.test", headers, dry_run=False)
        with pytest.raises(RuntimeError, match="400"):
            up.create_product({"query": "query {}"})


def test_create_product_user_errors(headers):
    data = {"data": {"productCreate": {"product": None, "userErrors": [{"field": "title", "message": "is blank"}]}}}
    with patch("requests.post", return_value=make_resp(200, data)):
        up = ShopifyUploader("shop.test", headers, dry_run=False)
        with pytest.raises(RuntimeError, match="userErrors"):
            up.create_product({"query": "query {}"})
