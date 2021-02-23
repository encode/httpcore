from ssl import SSLContext
from typing import Optional, Tuple

from .._backends.sync import SyncBackend, SyncSocketStream, SyncBackend
from .._types import URL, Headers, Origin, TimeoutDict
from .._utils import get_logger, url_to_origin
from .base import SyncByteStream, SyncHTTPTransport, ConnectionState
from .http import SyncBaseHTTPConnection
from .http11 import SyncHTTP11Connection

logger = get_logger(__name__)


class SyncHTTPConnection(SyncHTTPTransport):
    def __init__(
        self,
        origin: Origin,
        socket: SyncSocketStream,
        ssl_context: SSLContext = None,
        backend: SyncBackend = None,
    ):
        self.origin = origin
        self.socket = socket
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context

        self.is_http11 = False
        self.is_http2 = False
        self.expires_at: Optional[float] = None
        self.backend = SyncBackend() if backend is None else backend

        self.connection: SyncBaseHTTPConnection
        http_version = self.socket.get_http_version()
        logger.trace(
            "create_connection socket=%r http_version=%r", self.socket, http_version
        )
        if http_version == "HTTP/2":
            from .http2 import SyncHTTP2Connection

            self.is_http2 = True
            self.connection = SyncHTTP2Connection(
                socket=self.socket, backend=self.backend, ssl_context=self.ssl_context
            )
        else:
            self.is_http11 = True
            self.connection = SyncHTTP11Connection(
                socket=self.socket, ssl_context=self.ssl_context
            )

    def __repr__(self) -> str:
        http_version = "UNKNOWN"
        if self.is_http11:
            http_version = "HTTP/1.1"
        elif self.is_http2:
            http_version = "HTTP/2"
        return f"<SyncHTTPConnection http_version={http_version} state={self.state}>"

    def info(self) -> str:
        if self.state == ConnectionState.PENDING:
            return "Connecting"
        return self.connection.info()

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, SyncByteStream, dict]:
        assert url_to_origin(url) == self.origin
        logger.trace(
            "connection.request method=%r url=%r headers=%r", method, url, headers
        )
        return self.connection.request(method, url, headers, stream, ext)

    @property
    def state(self) -> ConnectionState:
        return self.connection.get_state()

    def is_socket_readable(self) -> bool:
        return self.connection.is_socket_readable()

    def mark_as_ready(self) -> None:
        self.connection.mark_as_ready()

    def start_tls(self, hostname: bytes, timeout: TimeoutDict = None) -> None:
        logger.trace("start_tls hostname=%r timeout=%r", hostname, timeout)
        self.socket = self.connection.start_tls(hostname, timeout)
        logger.trace("start_tls complete hostname=%r timeout=%r", hostname, timeout)

    def close(self) -> None:
        self.connection.close()
