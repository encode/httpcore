from ._async.base import AsyncHTTPTransport
from ._async.connection_pool import AsyncConnectionPool
from ._async.http_proxy import AsyncHTTPProxy
from ._bytestreams import PlainByteStream
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
from ._sync.base import SyncHTTPTransport
from ._sync.connection_pool import SyncConnectionPool
from ._sync.http_proxy import SyncHTTPProxy

__all__ = [
    "AsyncConnectionPool",
    "AsyncHTTPProxy",
    "AsyncHTTPTransport",
    "CloseError",
    "ConnectError",
    "ConnectTimeout",
    "LocalProtocolError",
    "NetworkError",
    "PlainByteStream",
    "PoolTimeout",
    "ProtocolError",
    "ProxyError",
    "ReadError",
    "ReadTimeout",
    "RemoteProtocolError",
    "SyncConnectionPool",
    "SyncHTTPProxy",
    "SyncHTTPTransport",
    "TimeoutException",
    "UnsupportedProtocol",
    "WriteError",
    "WriteTimeout",
]
__version__ = "0.12.2"

__locals = locals()

for _name in __all__:
    if not _name.startswith("__"):
        setattr(__locals[_name], "__module__", "httpcore")  # noqa
