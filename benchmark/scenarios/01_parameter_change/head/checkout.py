from pricing import total

def checkout(items):
    return total(items, discount_percent=10)
