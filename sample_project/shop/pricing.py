"""Pricing rules shared by the whole shop."""


def subtotal(items):
    """Sum of price * quantity for (price, quantity) pairs."""
    return sum(price * quantity for price, quantity in items)


def calculate_total(items, discount_percent=0):
    """Total after a percentage discount, e.g. discount_percent=10 means 10% off."""
    total = subtotal(items) * (1 - discount_percent / 100)
    return round(total, 2)
