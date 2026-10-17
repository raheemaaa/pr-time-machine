import a

def pong(n):
    return 0 if n <= 0 else a.ping(n - 1) + 2
