from shop.refunds import refund_amount


def test_refund_keeps_restocking_fee():
    assert refund_amount([(100, 1)]) == 90.0
