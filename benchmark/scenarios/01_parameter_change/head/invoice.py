from pricing import total

def make_invoice(items):
    return {'due': total(items)}
