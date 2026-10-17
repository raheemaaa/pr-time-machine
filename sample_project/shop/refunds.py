"""Refunds for returned items. Customers lose 10% as a restocking fee."""

from shop import pricing

RESTOCKING_FEE_PERCENT = 10


def refund_amount(items):
    return pricing.calculate_total(items, RESTOCKING_FEE_PERCENT)
