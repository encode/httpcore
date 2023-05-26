from ._api import request, stream
from ._async import (
    AsyncConnectionInterface,
    AsyncConnectionPool,
    AsyncHTTP2Connection,
    AsyncHTTP11Connection,
    AsyncHTTPConnection,
    AsyncHTTPProxy,
    AsyncSOCKSProxy,
)
from ._exceptions import (
    ConnectError,
    ConnectionNotAvailable,
    ConnectTimeout,
    LocalProtocolError,
    NetworkError,
    PoolTimeout,
    ProtocolError,
    ProxyError,
    ReadError,
    ReadTimeout,
    RemoteProtocolError,
    TimeoutException,
    UnsupportedProtocol,
    WriteError,
    WriteTimeout,
)
from ._models import URL, Origin, Request, Response
from ._ssl import default_ssl_context
from ._sync import (
    ConnectionInterface,
    ConnectionPool,
    HTTP2Connection,
    HTTP11Connection,
    HTTPConnection,
    HTTPProxy,
    SOCKSProxy,
)

# The 'httpcore.AnyIONetworkBackend' class is conditional on 'anyio' being installed.
try:
    from .backends.asyncio import AnyIONetworkBackend
except ImportError:  # pragma: nocover

    class AnyIONetworkBackend:  # type: ignore
        def __init__(self, *args, **kwargs):  # type: ignore
            msg = "Attempted to use 'httpcore.AnyIONetworkBackend' but 'anyio' is not installed."
            raise RuntimeError(msg)


# The 'httpcore.TrioNetworkBackend' class is conditional on 'trio' being installed.
try:
    from .backends.trio import TrioNetworkBackend
except ImportError:  # pragma: nocover

    class TrioNetworkBackend:  # type: ignore
        def __init__(self, *args, **kwargs):  # type: ignore
            msg = "Attempted to use 'httpcore.TrioNetworkBackend' but 'trio' is not installed."
            raise RuntimeError(msg)


__all__ = [
    # top-level requests
    "request",
    "stream",
    # models
    "Origin",
    "URL",
    "Request",
    "Response",
    # async
    "AsyncHTTPConnection",
    "AsyncConnectionPool",
    "AsyncHTTPProxy",
    "AsyncHTTP11Connection",
    "AsyncHTTP2Connection",
    "AsyncConnectionInterface",
    "AsyncSOCKSProxy",
    # sync
    "HTTPConnection",
    "ConnectionPool",
    "HTTPProxy",
    "HTTP11Connection",
    "HTTP2Connection",
    "ConnectionInterface",
    "SOCKSProxy",
    # network backends
    "AnyIONetworkBackend",
    "TrioNetworkBackend",
    # util
    "default_ssl_context",
    # exceptions
    "ConnectionNotAvailable",
    "ProxyError",
    "ProtocolError",
    "LocalProtocolError",
    "RemoteProtocolError",
    "UnsupportedProtocol",
    "TimeoutException",
    "PoolTimeout",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "NetworkError",
    "ConnectError",
    "ReadError",
    "WriteError",
]

__version__ = "0.17.2"


__locals = locals()
for __name in __all__:
    if not __name.startswith("__"):
        setattr(__locals[__name], "__module__", "httpcore")  # noqa
