from shop.reports import daily_revenue


def test_daily_revenue_sums_orders():
    assert daily_revenue([[(10, 1)], [(5, 2)]]) == 20.0
