from .._backends.auto import AsyncSocketStream
from .._types import TimeoutDict
from .base import AsyncHTTPTransport


class AsyncBaseHTTPConnection(AsyncHTTPTransport):
    def info(self) -> str:
        raise NotImplementedError()  # pragma: nocover

    def should_close(self) -> bool:
        """
        Return `True` if the connection is in a state where it should be closed.
        """
        raise NotImplementedError()  # pragma: nocover

    def may_close(self) -> bool:
        """
        Return `True` if the connection is in a state where it can be closed.
        """
        raise NotImplementedError()  # pragma: nocover

    def is_closed(self) -> bool:
        raise NotImplementedError()  # pragma: nocover

    def is_available(self) -> bool:
        """
        Return `True` if the connection is currently able to accept an outgoing request.
        """
        raise NotImplementedError()  # pragma: nocover

    async def start_tls(
        self, hostname: bytes, timeout: TimeoutDict = None
    ) -> AsyncSocketStream:
        """
        Upgrade the underlying socket to TLS.
        """
        raise NotImplementedError()  # pragma: nocover
