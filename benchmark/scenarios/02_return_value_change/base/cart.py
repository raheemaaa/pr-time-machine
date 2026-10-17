from util import parse_price

def add(cart, text):
    return cart + parse_price(text)
