from shop.api import checkout_endpoint
from shop.checkout import place_order


def test_place_order_with_coupon():
    assert place_order([(100, 2)], coupon_percent=10) == {"status": "placed", "total": 180.0}


def test_checkout_endpoint_returns_created():
    response = checkout_endpoint({"cart": [(50, 1)], "coupon": 20})
    assert response == {"code": 201, "body": {"status": "placed", "total": 40.0}}
