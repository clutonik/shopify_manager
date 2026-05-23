import pytest
from shopify_manager.price_updater import PriceUpdater
from shopify_manager.uploader import API_VERSION


@pytest.fixture
def headers():
    return {"Content-Type": "application/json", "X-Shopify-Access-Token": "fake"}


def test_init_defaults(headers):
    pu = PriceUpdater("shop.test", headers)
    assert pu.shop_base == "shop.test"
    assert pu.headers == headers
    assert pu.dry_run is False
    assert pu.auth is None
    assert pu.api_version == API_VERSION


def test_init_custom_params(headers):
    pu = PriceUpdater("shop.test", headers, auth=("u", "p"), dry_run=True, api_version="2023-01")
    assert pu.dry_run is True
    assert pu.auth == ("u", "p")
    assert pu.api_version == "2023-01"


def test_update_prices_returns_none(headers):
    pu = PriceUpdater("shop.test", headers)
    result = pu.update_prices([{"id": "gid://shopify/ProductVariant/1", "price": "10.00"}])
    assert result is None


def test_update_prices_empty_list(headers):
    pu = PriceUpdater("shop.test", headers)
    result = pu.update_prices([])
    assert result is None
