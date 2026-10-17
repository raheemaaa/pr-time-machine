"""Invoices list the full price before any discounts."""

from shop.pricing import calculate_total


def build_invoice(order_id, items):
    return {"order_id": order_id, "lines": len(items), "amount_due": calculate_total(items)}
