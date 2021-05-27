from ssl import SSLContext
from typing import List, Optional, Tuple, cast

from .._backends.auto import AsyncBackend, AsyncLock, AsyncSocketStream, AutoBackend
from .._exceptions import ConnectError, ConnectTimeout
from .._types import URL, Headers, Origin, TimeoutDict
from .._utils import exponential_backoff, get_logger, url_to_origin
from .base import AsyncByteStream, AsyncHTTPTransport, NewConnectionRequired
from .http import AsyncBaseHTTPConnection
from .http11 import AsyncHTTP11Connection

logger = get_logger(__name__)

RETRIES_BACKOFF_FACTOR = 0.5  # 0s, 0.5s, 1s, 2s, 4s, etc.


class AsyncHTTPConnection(AsyncHTTPTransport):
    def __init__(
        self,
        origin: Origin,
        http1: bool = True,
        http2: bool = False,
        uds: str = None,
        ssl_context: SSLContext = None,
        socket: AsyncSocketStream = None,
        local_address: str = None,
        retries: int = 0,
        backend: AsyncBackend = None,
    ):
        self.origin = origin
        self.http1 = http1
        self.http2 = http2
        self.uds = uds
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context
        self.socket = socket
        self.local_address = local_address
        self.retries = retries

        alpn_protocols: List[str] = []
        if http1:
            alpn_protocols.append("http/1.1")
        if http2:
            alpn_protocols.append("h2")

        self.ssl_context.set_alpn_protocols(alpn_protocols)

        self.connection: Optional[AsyncBaseHTTPConnection] = None
        self.is_http11 = False
        self.is_http2 = False
        self.connect_failed = False
        self.expires_at: Optional[float] = None
        self.backend = AutoBackend() if backend is None else backend

    def __repr__(self) -> str:
        return f"<AsyncHTTPConnection [{self.info()}]>"

    def info(self) -> str:
        if self.connection is None:
            return "Connection failed" if self.connect_failed else "Connecting"
        return self.connection.info()

    def should_close(self) -> bool:
        """
        Return `True` if the connection is in a state where it should be closed.
        This occurs when any of the following occur:

        * There are no active requests on an HTTP/1.1 connection, and the underlying
          socket is readable. The only valid state the socket can be readable in
          if this occurs is when the b"" EOF marker is about to be returned,
          indicating a server disconnect.
        * There are no active requests being made and the keepalive timeout has passed.
        """
        if self.connection is None:
            return False
        return self.connection.should_close()

    def may_close(self) -> bool:
        """
        Return `True` if the connection is in a state where it can be closed.
        This occurs when:

        * The connection is open, but is currently idle.
        """
        if self.connection is None:
            return False
        return self.connection.may_close()

    def is_closed(self) -> bool:
        if self.connection is None:
            return self.connect_failed
        return self.connection.is_closed()

    def is_available(self) -> bool:
        """
        Return `True` if the connection is currently able to accept an outgoing request.
        This occurs when any of the following occur:

        * The connection has not yet been opened, and HTTP/2 support is enabled.
          We don't *know* at this point if we'll end up on an HTTP/2 connection or
          not, but we *might* do, so we indicate availability.
        * The connection has been opened, and is currently idle.
        * The connection is open, and is an HTTP/2 connection. The connection must
          also not currently be exceeding the maximum number of allowable concurrent
          streams and must not have exhausted the maximum total number of stream IDs.
        """
        if self.connection is None:
            return self.http2 and not self.is_closed
        return self.connection.is_available()

    @property
    def request_lock(self) -> AsyncLock:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_request_lock"):
            self._request_lock = self.backend.create_lock()
        return self._request_lock

    async def handle_async_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        stream: AsyncByteStream,
        extensions: dict,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        assert url_to_origin(url) == self.origin
        timeout = cast(TimeoutDict, extensions.get("timeout", {}))

        async with self.request_lock:
            if self.connection is None:
                if self.connect_failed:
                    raise NewConnectionRequired()
                if not self.socket:
                    logger.trace(
                        "open_socket origin=%r timeout=%r", self.origin, timeout
                    )
                    self.socket = await self._open_socket(timeout)
                self._create_connection(self.socket)
            elif not self.connection.is_available():
                raise NewConnectionRequired()

        assert self.connection is not None
        logger.trace(
            "connection.handle_async_request method=%r url=%r headers=%r",
            method,
            url,
            headers,
        )
        return await self.connection.handle_async_request(
            method, url, headers, stream, extensions
        )

    async def _open_socket(self, timeout: TimeoutDict = None) -> AsyncSocketStream:
        scheme, hostname, port = self.origin
        timeout = {} if timeout is None else timeout
        ssl_context = self.ssl_context if scheme == b"https" else None

        retries_left = self.retries
        delays = exponential_backoff(factor=RETRIES_BACKOFF_FACTOR)

        while True:
            try:
                if self.uds is None:
                    return await self.backend.open_tcp_stream(
                        hostname,
                        port,
                        ssl_context,
                        timeout,
                        local_address=self.local_address,
                    )
                else:
                    return await self.backend.open_uds_stream(
                        self.uds, hostname, ssl_context, timeout
                    )
            except (ConnectError, ConnectTimeout):
                if retries_left <= 0:
                    self.connect_failed = True
                    raise
                retries_left -= 1
                delay = next(delays)
                await self.backend.sleep(delay)
            except Exception:  # noqa: PIE786
                self.connect_failed = True
                raise

    def _create_connection(self, socket: AsyncSocketStream) -> None:
        http_version = socket.get_http_version()
        logger.trace(
            "create_connection socket=%r http_version=%r", socket, http_version
        )
        if http_version == "HTTP/2" or (self.http2 and not self.http1):
            from .http2 import AsyncHTTP2Connection

            self.is_http2 = True
            self.connection = AsyncHTTP2Connection(
                socket=socket, backend=self.backend, ssl_context=self.ssl_context
            )
        else:
            self.is_http11 = True
            self.connection = AsyncHTTP11Connection(
                socket=socket, ssl_context=self.ssl_context
            )

    async def start_tls(self, hostname: bytes, timeout: TimeoutDict = None) -> None:
        if self.connection is not None:
            logger.trace("start_tls hostname=%r timeout=%r", hostname, timeout)
            self.socket = await self.connection.start_tls(hostname, timeout)
            logger.trace("start_tls complete hostname=%r timeout=%r", hostname, timeout)

    async def aclose(self) -> None:
        async with self.request_lock:
            if self.connection is not None:
                await self.connection.aclose()
