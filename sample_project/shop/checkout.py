"""Checkout: turns a cart and an optional coupon into an order."""

from shop.pricing import calculate_total


def place_order(cart, coupon_percent=0):
    total = calculate_total(cart, discount_percent=coupon_percent)
    if total <= 0:
        raise ValueError("Order total must be positive.")
    return {"status": "placed", "total": total}
