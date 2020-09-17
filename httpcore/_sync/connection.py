from ssl import SSLContext
from typing import List, Optional, Tuple

from socksio import socks5

from .._backends.sync import SyncBackend, SyncLock, SyncSocketStream, SyncBackend
from .._types import URL, Headers, Origin, TimeoutDict
from .._utils import get_logger, url_to_origin
from .base import (
    SyncByteStream,
    SyncHTTPTransport,
    ConnectionState,
    NewConnectionRequired,
)
from .http import SyncBaseHTTPConnection

logger = get_logger(__name__)


class SyncHTTPConnection(SyncHTTPTransport):
    def __init__(
        self,
        origin: Origin,
        http2: bool = False,
        uds: str = None,
        ssl_context: SSLContext = None,
        socket: SyncSocketStream = None,
        local_address: str = None,
        backend: SyncBackend = None,
    ):
        self.origin = origin
        self.http2 = http2
        self.uds = uds
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context
        self.socket = socket
        self.local_address = local_address

        if self.http2:
            self.ssl_context.set_alpn_protocols(["http/1.1", "h2"])

        self.connection: Optional[SyncBaseHTTPConnection] = None
        self.is_http11 = False
        self.is_http2 = False
        self.connect_failed = False
        self.expires_at: Optional[float] = None
        self.backend = SyncBackend() if backend is None else backend

    def __repr__(self) -> str:
        http_version = "UNKNOWN"
        if self.is_http11:
            http_version = "HTTP/1.1"
        elif self.is_http2:
            http_version = "HTTP/2"
        return f"<SyncHTTPConnection http_version={http_version} state={self.state}>"

    def info(self) -> str:
        if self.connection is None:
            return "Not connected"
        elif self.state == ConnectionState.PENDING:
            return "Connecting"
        return self.connection.info()

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
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        assert url_to_origin(url) == self.origin
        with self.request_lock:
            if self.state == ConnectionState.PENDING:
                if not self.socket:
                    logger.trace(
                        "open_socket origin=%r timeout=%r", self.origin, timeout
                    )
                    self.socket = self._open_socket(timeout)
                self._create_connection(self.socket)
            elif self.state in (ConnectionState.READY, ConnectionState.IDLE):
                pass
            elif self.state == ConnectionState.ACTIVE and self.is_http2:
                pass
            else:
                raise NewConnectionRequired()

        assert self.connection is not None
        logger.trace(
            "connection.request method=%r url=%r headers=%r", method, url, headers
        )
        return self.connection.request(method, url, headers, stream, timeout)

    def _open_socket(self, timeout: TimeoutDict = None) -> SyncSocketStream:
        scheme, hostname, port = self.origin
        timeout = {} if timeout is None else timeout
        ssl_context = self.ssl_context if scheme == b"https" else None
        try:
            if self.uds is None:
                return self.backend.open_tcp_stream(
                    hostname,
                    port,
                    ssl_context,
                    timeout,
                    local_address=self.local_address,
                )
            else:
                return self.backend.open_uds_stream(
                    self.uds, hostname, ssl_context, timeout
                )
        except Exception:  # noqa: PIE786
            self.connect_failed = True
            raise

    def _create_connection(self, socket: SyncSocketStream) -> None:
        http_version = socket.get_http_version()
        logger.trace(
            "create_connection socket=%r http_version=%r", socket, http_version
        )
        if http_version == "HTTP/2":
            from .http2 import SyncHTTP2Connection

            self.is_http2 = True
            self.connection = SyncHTTP2Connection(
                socket=socket, backend=self.backend, ssl_context=self.ssl_context
            )
        else:
            from .http11 import SyncHTTP11Connection

            self.is_http11 = True
            self.connection = SyncHTTP11Connection(
                socket=socket, ssl_context=self.ssl_context
            )

    @property
    def state(self) -> ConnectionState:
        if self.connect_failed:
            return ConnectionState.CLOSED
        elif self.connection is None:
            return ConnectionState.PENDING
        return self.connection.get_state()

    def is_connection_dropped(self) -> bool:
        return self.connection is not None and self.connection.is_connection_dropped()

    def mark_as_ready(self) -> None:
        if self.connection is not None:
            self.connection.mark_as_ready()

    def start_tls(self, hostname: bytes, timeout: TimeoutDict = None) -> None:
        if self.connection is not None:
            logger.trace("start_tls hostname=%r timeout=%r", hostname, timeout)
            self.socket = self.connection.start_tls(hostname, timeout)
            logger.trace("start_tls complete hostname=%r timeout=%r", hostname, timeout)

    def close(self) -> None:
        with self.request_lock:
            if self.connection is not None:
                self.connection.close()


class SyncSOCKSConnection(SyncHTTPConnection):
    def __init__(
        self,
        origin: Origin,
        http2: bool = False,
        uds: str = None,
        ssl_context: SSLContext = None,
        socket: SyncSocketStream = None,
        local_address: str = None,
        backend: SyncBackend = None,
        *,
        proxy_origin: Origin,
    ):
        assert proxy_origin[0] in (b"socks5",)

        super().__init__(
            origin, http2, uds, ssl_context, socket, local_address, backend
        )
        self.proxy_origin = proxy_origin
        self.proxy_connection = socks5.SOCKS5Connection()

    def _open_socket(self, timeout: TimeoutDict = None) -> SyncSocketStream:
        _, proxy_hostname, proxy_port = self.proxy_origin
        scheme, hostname, port = self.origin
        ssl_context = self.ssl_context if scheme == b"https" else None
        timeout = timeout or {}

        proxy_socket = self.backend.open_tcp_stream(
            proxy_hostname,
            proxy_port,
            None,
            timeout,
            local_address=self.local_address,
        )

        request = socks5.SOCKS5AuthMethodsRequest(
            [
                socks5.SOCKS5AuthMethod.NO_AUTH_REQUIRED,
                socks5.SOCKS5AuthMethod.USERNAME_PASSWORD,
            ]
        )

        self.proxy_connection.send(request)

        bytes_to_send = self.proxy_connection.data_to_send()
        proxy_socket.write(bytes_to_send, timeout)

        data = proxy_socket.read(1024, timeout)
        event = self.proxy_connection.receive_data(data)

        assert event.method == socks5.SOCKS5AuthMethod.NO_AUTH_REQUIRED

        request = socks5.SOCKS5CommandRequest.from_address(
            socks5.SOCKS5Command.CONNECT, (hostname, port)
        )

        self.proxy_connection.send(request)
        bytes_to_send = self.proxy_connection.data_to_send()

        proxy_socket.write(bytes_to_send, timeout)
        data = proxy_socket.read(1024, timeout)
        event = self.proxy_connection.receive_data(data)

        assert event.reply_code == socks5.SOCKS5ReplyCode.SUCCEEDED

        if ssl_context:
            proxy_socket = proxy_socket.start_tls(hostname, ssl_context, timeout)

        return proxy_socket
