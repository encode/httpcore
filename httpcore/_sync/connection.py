from ssl import SSLContext
from typing import Dict, List, Optional, Tuple, Union

from .._backends.auto import SyncLock, SyncSocketStream, SyncBackend
from .base import (
    SyncByteStream,
    SyncHTTPTransport,
    ConnectionState,
    NewConnectionRequired,
)
from .http2 import SyncHTTP2Connection
from .http11 import SyncHTTP11Connection


class SyncHTTPConnection(SyncHTTPTransport):
    def __init__(
        self,
        origin: Tuple[bytes, bytes, int],
        http2: bool = False,
        ssl_context: SSLContext = None,
    ):
        self.origin = origin
        self.http2 = http2
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context

        if self.http2:
            self.ssl_context.set_alpn_protocols(["http/1.1", "h2"])

        self.connection: Union[None, SyncHTTP11Connection, SyncHTTP2Connection] = None
        self.is_http11 = False
        self.is_http2 = False
        self.connect_failed = False
        self.expires_at: Optional[float] = None
        self.backend = SyncBackend()

    @property
    def request_lock(self) -> SyncLock:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_request_lock"):
            self._request_lock = self.backend.create_lock()
        return self._request_lock

    def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: SyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        assert url[:3] == self.origin

        with self.request_lock:
            if self.state == ConnectionState.PENDING:
                try:
                    self._connect(timeout)
                except:
                    self.connect_failed = True
                    raise
            elif self.state in (ConnectionState.READY, ConnectionState.IDLE):
                pass
            elif self.state == ConnectionState.ACTIVE and self.is_http2:
                pass
            else:
                raise NewConnectionRequired()

        assert self.connection is not None
        return self.connection.request(method, url, headers, stream, timeout)

    def _connect(
        self, timeout: Dict[str, Optional[float]] = None,
    ):
        scheme, hostname, port = self.origin
        timeout = {} if timeout is None else timeout
        ssl_context = self.ssl_context if scheme == b"https" else None
        socket = self.backend.open_tcp_stream(
            hostname, port, ssl_context, timeout
        )
        http_version = socket.get_http_version()
        if http_version == "HTTP/2":
            self.is_http2 = True
            self.connection = SyncHTTP2Connection(socket=socket, backend=self.backend)
        else:
            self.is_http11 = True
            self.connection = SyncHTTP11Connection(socket=socket)

    @property
    def state(self) -> ConnectionState:
        if self.connect_failed:
            return ConnectionState.CLOSED
        elif self.connection is None:
            return ConnectionState.PENDING
        return self.connection.state

    def is_connection_dropped(self) -> bool:
        return self.connection is not None and self.connection.is_connection_dropped()

    def mark_as_ready(self) -> None:
        if self.connection is not None:
            self.connection.mark_as_ready()

    def start_tls(
        self, hostname: bytes, timeout: Dict[str, Optional[float]] = None
    ):
        if self.connection is not None:
            self.connection.start_tls(hostname, timeout)
