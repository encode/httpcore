from ssl import SSLContext
from typing import Optional, Tuple, cast

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
        ext: dict = None,
    ) -> Tuple[int, Headers, SyncByteStream, dict]:
        assert url_to_origin(url) == self.origin
        ext = {} if ext is None else ext
        timeout = cast(TimeoutDict, ext.get("timeout", {}))

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
        return self.connection.request(method, url, headers, stream, ext)

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
