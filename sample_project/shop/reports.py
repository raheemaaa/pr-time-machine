"""Daily revenue report."""

from shop.pricing import calculate_total


def daily_revenue(orders):
    return round(sum(calculate_total(order) for order in orders), 2)
