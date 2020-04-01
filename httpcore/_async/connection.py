from ssl import SSLContext
from typing import List, Optional, Tuple, Union

from socksio import socks4

from .._backends.auto import AsyncLock, AutoBackend
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
        self, origin: Origin, http2: bool = False, ssl_context: SSLContext = None,
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
        headers: Optional[Headers] = None,
        stream: AsyncByteStream = None,
        timeout: Optional[TimeoutDict] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream]:
        assert url[:3] == self.origin

        async with self.request_lock:
            if self.state == ConnectionState.PENDING:
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
        socket = await self.backend.open_tcp_stream(
            hostname, port, ssl_context, timeout
        )
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

    async def start_tls(
        self, hostname: bytes, timeout: Optional[TimeoutDict] = None
    ) -> None:
        if self.connection is not None:
            await self.connection.start_tls(hostname, timeout)


class AsyncSOCKSConnection(AsyncHTTPConnection):
    """An HTTP/1.1 connection with SOCKS proxy negotiation."""

    def __init__(
        self,
        origin: Origin,
        proxy_origin: Origin,
        socks_version: str,
        user_id: bytes = b"httpcore",
        ssl_context: Optional[SSLContext] = None,
    ) -> None:
        self.origin = origin
        self.proxy_origin = proxy_origin
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context
        self.connection: Union[None, AsyncHTTP11Connection] = None
        self.is_http11 = True
        self.is_http2 = False
        self.connect_failed = False
        self.expires_at: Optional[float] = None
        self.backend = AutoBackend()

        self.user_id = user_id
        self.socks_connection = self._get_socks_connection(socks_version)

    def _get_socks_connection(self, socks_version: str) -> socks4.SOCKS4Connection:
        if socks_version == "SOCKS4":
            return socks4.SOCKS4Connection(user_id=self.user_id)
        else:
            raise NotImplementedError

    async def _connect(self, timeout: Optional[TimeoutDict] = None,) -> None:
        """SOCKS4 negotiation prior to creating an HTTP/1.1 connection."""
        # First setup the socket to talk to the proxy server
        _, hostname, port = self.proxy_origin
        timeout = {} if timeout is None else timeout
        ssl_context = None
        socket = await self.backend.open_tcp_stream(
            hostname, port, ssl_context, timeout
        )

        # Use socksio to negotiate the connection with the remote host
        request = socks4.SOCKS4Request.from_address(
            socks4.SOCKS4Command.CONNECT, (self.origin[1].decode(), self.origin[2])
        )
        self.socks_connection.send(request)
        bytes_to_send = self.socks_connection.data_to_send()
        await socket.write(bytes_to_send, timeout)

        # Read the response from the proxy
        data = await socket.read(1024, timeout)
        event = self.socks_connection.receive_data(data)

        # Bail if rejected
        if event.reply_code != socks4.SOCKS4ReplyCode.REQUEST_GRANTED:
            raise Exception(
                "Proxy server could not connect to remote host: {}".format(
                    event.reply_code
                )
            )

        # Otherwise use the socket as usual
        self.connection = AsyncHTTP11Connection(
            socket=socket, ssl_context=self.ssl_context
        )
