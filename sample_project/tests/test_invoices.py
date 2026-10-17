from shop.invoices import build_invoice


def test_invoice_shows_full_price():
    assert build_invoice("INV-1", [(25, 4)])["amount_due"] == 100.0
