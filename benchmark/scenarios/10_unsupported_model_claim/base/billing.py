from tax import rate

def bill(x):
    return x * (1 + rate())
