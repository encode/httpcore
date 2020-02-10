from typing import Tuple


def normalize_url(
    url: Tuple[bytes, bytes, int, bytes]
) -> Tuple[bytes, bytes, int, bytes]:
    scheme, hostname, port, target = url
    scheme = scheme.lower()
    hostname = hostname.lower()

    if not scheme:
        raise ValueError(r"URL missing scheme. {url!r}")
    if not hostname:
        raise ValueError(r"URL missing hostname. {url!r}")

    if not isinstance(scheme, bytes):
        raise TypeError(r"URL scheme must be bytes, got {type(scheme)}.")
    if not isinstance(hostname, bytes):
        raise TypeError(r"URL hostname must be bytes, got {type(hostname)}.")
    if not isinstance(port, int):
        raise TypeError(r"URL port must be int, got {type(port)}.")
    if not isinstance(target, bytes):
        raise TypeError(r"URL target must be bytes, got {type(target)}.")

    if scheme not in (b"http", b"https"):
        raise ValueError(r"Unsupported scheme in URL. {scheme!r}")
    if any([code > 127 for code in hostname]):
        raise ValueError(r"URL hostname must be 7-bit ASCII. {hostname!r}")

    return (scheme, hostname, port, target)


def url_as_bytes(url: Tuple[bytes, bytes, int, bytes]) -> bytes:
    scheme, hostname, port, target = url
    default_port = {b"http": 80, b"https": 443}.get(scheme)
    if port == default_port:
        return b"%b://%b%b" % (scheme, hostname, target)
    return b"%b://%b:%d%b" % (scheme, hostname, port, target)
