from .._backends.sync import SyncSocketStream
from .._types import TimeoutDict
from .base import SyncHTTPTransport, ConnectionState


class SyncBaseHTTPConnection(SyncHTTPTransport):
    def info(self) -> str:
        raise NotImplementedError()  # pragma: nocover

    def get_state(self) -> ConnectionState:
        """
        Return the current state.
        """
        raise NotImplementedError()  # pragma: nocover

    def mark_as_ready(self) -> None:
        """
        The connection has been acquired from the pool, and the state
        should reflect that.
        """
        raise NotImplementedError()  # pragma: nocover

    def is_socket_readable(self) -> bool:
        """
        Return 'True' if the underlying network socket is readable.
        """
        raise NotImplementedError()  # pragma: nocover

    def start_tls(
        self, hostname: bytes, timeout: TimeoutDict = None
    ) -> SyncSocketStream:
        """
        Upgrade the underlying socket to TLS.
        """
        raise NotImplementedError()  # pragma: nocover
