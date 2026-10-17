"""A small HTTP-style handler that calls checkout."""

from shop.checkout import place_order


def checkout_endpoint(payload):
    order = place_order(payload["cart"], payload.get("coupon", 0))
    return {"code": 201, "body": order}
