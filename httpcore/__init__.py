from ._async.base import AsyncByteStream, AsyncHTTPTransport
from ._async.connection_pool import AsyncConnectionPool
from ._async.http_proxy import AsyncHTTPProxy
from ._bytestreams import AsyncIteratorByteStream, IteratorByteStream, PlainByteStream
from ._exceptions import (
    CloseError,
    ConnectError,
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
from ._sync.base import SyncByteStream, SyncHTTPTransport
from ._sync.connection_pool import SyncConnectionPool
from ._sync.http_proxy import SyncHTTPProxy

__all__ = [
    "AsyncHTTPTransport",
    "AsyncByteStream",
    "AsyncConnectionPool",
    "AsyncHTTPProxy",
    "SyncHTTPTransport",
    "SyncByteStream",
    "SyncConnectionPool",
    "SyncHTTPProxy",
    "TimeoutException",
    "PoolTimeout",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "NetworkError",
    "ConnectError",
    "ReadError",
    "WriteError",
    "CloseError",
    "LocalProtocolError",
    "RemoteProtocolError",
    "UnsupportedProtocol",
    "AsyncIteratorByteStream",
    "IteratorByteStream",
    "PlainByteStream",
]
__version__ = "0.10.1"

__locals = locals()

for name in __all__:
    if not name.startswith("__"):
        setattr(__locals[name], "__module__", "httpcore")  # noqa
