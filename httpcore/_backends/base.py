from ssl import SSLContext
from types import TracebackType
from typing import Optional, Type

from .._types import TimeoutDict


class AsyncSocketStream:
    """
    A socket stream with read/write operations. Abstracts away any asyncio-specific
    interfaces into a more generic base class, that we can use with alternate
    backends, or for stand-alone test cases.
    """

    def get_http_version(self) -> str:
        raise NotImplementedError()  # pragma: no cover

    async def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict
    ) -> "AsyncSocketStream":
        raise NotImplementedError()  # pragma: no cover

    async def read(self, n: int, timeout: TimeoutDict) -> bytes:
        raise NotImplementedError()  # pragma: no cover

    async def write(self, data: bytes, timeout: TimeoutDict) -> None:
        raise NotImplementedError()  # pragma: no cover

    async def aclose(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    def is_connection_dropped(self) -> bool:
        raise NotImplementedError()  # pragma: no cover


class AsyncLock:
    """
    An abstract interface for Lock classes.
    """

    async def __aenter__(self) -> None:
        await self.acquire()

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        self.release()

    def release(self) -> None:
        raise NotImplementedError()  # pragma: no cover

    async def acquire(self) -> None:
        raise NotImplementedError()  # pragma: no cover


class AsyncSemaphore:
    """
    An abstract interface for Semaphore classes.
    Abstracts away any asyncio-specific interfaces.
    """

    async def acquire(self, timeout: float = None) -> None:
        raise NotImplementedError()  # pragma: no cover

    def release(self) -> None:
        raise NotImplementedError()  # pragma: no cover


class AsyncBackend:
    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> AsyncSocketStream:
        raise NotImplementedError()  # pragma: no cover

    async def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> AsyncSocketStream:
        raise NotImplementedError()  # pragma: no cover

    def create_lock(self) -> AsyncLock:
        raise NotImplementedError()  # pragma: no cover

    def create_semaphore(self, max_value: int, exc_class: type) -> AsyncSemaphore:
        raise NotImplementedError()  # pragma: no cover

    def time(self) -> float:
        raise NotImplementedError()  # pragma: no cover
