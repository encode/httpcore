from ._async.base import AsyncByteStream, AsyncHTTPTransport
from ._async.connection_pool import AsyncConnectionPool
from ._async.http_proxy import AsyncHTTPProxy
from ._async.socks_proxy import AsyncSocksProxy
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
from ._sync.socks_proxy import SyncSocksProxy

__all__ = [
    "AsyncByteStream",
    "AsyncConnectionPool",
    "AsyncHTTPProxy",
    "AsyncSocksProxy",
    "AsyncHTTPTransport",
    "AsyncIteratorByteStream",
    "CloseError",
    "ConnectError",
    "ConnectTimeout",
    "IteratorByteStream",
    "LocalProtocolError",
    "NetworkError",
    "PlainByteStream",
    "PoolTimeout",
    "ProtocolError",
    "ProxyError",
    "ReadError",
    "ReadTimeout",
    "RemoteProtocolError",
    "SyncByteStream",
    "SyncConnectionPool",
    "SyncHTTPProxy",
    "SyncSocksProxy",
    "SyncHTTPTransport",
    "TimeoutException",
    "UnsupportedProtocol",
    "WriteError",
    "WriteTimeout",
]
__version__ = "0.11.1"

__locals = locals()

for _name in __all__:
    if not _name.startswith("__"):
        setattr(__locals[_name], "__module__", "httpcore")  # noqa
