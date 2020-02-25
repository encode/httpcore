import contextlib
from typing import Dict, Iterator, Type


@contextlib.contextmanager
def map_exceptions(map: Dict[Type[Exception], Type[Exception]]) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        for from_exc, to_exc in map.items():
            if isinstance(exc, from_exc):
                raise to_exc(exc) from None
        raise


class ProtocolError(Exception):
    pass


class ProxyError(Exception):
    pass


# Timeout errors


class PoolTimeout(Exception):
    pass


class ConnectTimeout(Exception):
    pass


class ReadTimeout(Exception):
    pass


class WriteTimeout(Exception):
    pass


# Network errors


class NetworkError(Exception):
    pass


class ConnectError(NetworkError):
    pass


class ReadError(NetworkError):
    pass


class WriteError(NetworkError):
    pass


class CloseError(NetworkError):
    pass
