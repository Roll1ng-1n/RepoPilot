from transport import fetch


def collect(url, timeout=5):
    return fetch(url, timeout)
