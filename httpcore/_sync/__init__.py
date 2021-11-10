from .connection import HTTPConnection
from .connection_pool import ConnectionPool
from .http11 import HTTP11Connection
from .http_proxy import HTTPProxy
from .interfaces import ConnectionInterface

try:
    from .http2 import HTTP2Connection
except ImportError:  # pragma: nocover
    pass


__all__ = [
    "HTTPConnection",
    "ConnectionPool",
    "HTTPProxy",
    "HTTP11Connection",
    "HTTP2Connection",
    "ConnectionInterface",
]
