from rules import is_adult

def register(age):
    if not is_adult(age):
        raise ValueError('too young')
    return 'ok'
