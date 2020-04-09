from ssl import SSLContext
from typing import List, Optional, Tuple, Union

from .._backends.auto import AsyncLock, AsyncSocketStream, AutoBackend
from .._types import URL, Headers, Origin, TimeoutDict
from .base import (
    AsyncByteStream,
    AsyncHTTPTransport,
    ConnectionState,
    NewConnectionRequired,
)
from .http2 import AsyncHTTP2Connection
from .http11 import AsyncHTTP11Connection


class AsyncHTTPConnection(AsyncHTTPTransport):
    def __init__(
        self,
        origin: Origin,
        http2: bool = False,
        ssl_context: SSLContext = None,
        socket: AsyncSocketStream = None,
    ):
        self.origin = origin
        self.http2 = http2
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context

        if self.http2:
            self.ssl_context.set_alpn_protocols(["http/1.1", "h2"])

        self.connection: Union[None, AsyncHTTP11Connection, AsyncHTTP2Connection] = None
        self.is_http11 = False
        self.is_http2 = False
        self.connect_failed = False
        self.expires_at: Optional[float] = None
        self.backend = AutoBackend()
        self.socket = socket

    @property
    def request_lock(self) -> AsyncLock:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_request_lock"):
            self._request_lock = self.backend.create_lock()
        return self._request_lock

    async def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream]:
        assert url[:3] == self.origin
        async with self.request_lock:
            if self.state == ConnectionState.PENDING:
                if self.socket:
                    self._create_connection(self.socket)
                else:
                    try:
                        await self._connect(timeout)
                    except Exception:
                        self.connect_failed = True
                        raise
            elif self.state in (ConnectionState.READY, ConnectionState.IDLE):
                pass
            elif self.state == ConnectionState.ACTIVE and self.is_http2:
                pass
            else:
                raise NewConnectionRequired()

        assert self.connection is not None
        return await self.connection.request(method, url, headers, stream, timeout)

    async def _connect(self, timeout: TimeoutDict = None) -> None:
        scheme, hostname, port = self.origin
        timeout = {} if timeout is None else timeout
        ssl_context = self.ssl_context if scheme == b"https" else None
        self.socket = await self.backend.open_tcp_stream(
            hostname, port, ssl_context, timeout
        )
        self._create_connection(self.socket)

    def _create_connection(self, socket: AsyncSocketStream) -> None:
        http_version = socket.get_http_version()
        if http_version == "HTTP/2":
            self.is_http2 = True
            self.connection = AsyncHTTP2Connection(socket=socket, backend=self.backend)
        else:
            self.is_http11 = True
            self.connection = AsyncHTTP11Connection(socket=socket)

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

    async def start_tls(self, hostname: bytes, timeout: TimeoutDict = None) -> None:
        if self.connection is not None:
            await self.connection.start_tls(hostname, timeout)
            self.socket = self.connection.socket
