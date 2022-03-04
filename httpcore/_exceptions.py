import contextlib
from typing import Dict, Iterator, Type


@contextlib.contextmanager
def map_exceptions(map: Dict[Type, Type]) -> Iterator[None]:  # type: ignore[type-arg]
    try:
        yield
    except Exception as exc:  # noqa: PIE786
        for from_exc, to_exc in map.items():
            if isinstance(exc, from_exc):
                raise to_exc(exc)
        raise  # pragma: nocover


class ConnectionNotAvailable(Exception):
    pass


class ProxyError(Exception):
    pass


class UnsupportedProtocol(Exception):
    pass


class ProtocolError(Exception):
    pass


class RemoteProtocolError(ProtocolError):
    pass


class LocalProtocolError(ProtocolError):
    pass


# Timeout errors


class TimeoutException(Exception):
    pass


class PoolTimeout(TimeoutException):
    pass


class ConnectTimeout(TimeoutException):
    pass


class ReadTimeout(TimeoutException):
    pass


class WriteTimeout(TimeoutException):
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
