import handlers

def dispatch(event, doc):
    return getattr(handlers, 'on_' + event)(doc)
