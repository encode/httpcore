from ssl import SSLContext
from typing import Optional

import sniffio

from .._types import TimeoutDict
from .base import AsyncBackend, AsyncLock, AsyncSemaphore, AsyncSocketStream

# The following line is imported from the _sync modules
from .sync import SyncBackend, SyncLock, SyncSemaphore, SyncSocketStream  # noqa


class AutoBackend(AsyncBackend):
    @property
    def backend(self) -> AsyncBackend:
        if not hasattr(self, "_backend_implementation"):
            backend = sniffio.current_async_library()

            if backend == "asyncio":
                from .asyncio import AsyncioBackend

                self._backend_implementation: AsyncBackend = AsyncioBackend()
            elif backend == "trio":
                from .trio import TrioBackend

                self._backend_implementation = TrioBackend()
            else:  # pragma: nocover
                raise RuntimeError(f"Unsupported concurrency backend {backend!r}")
        return self._backend_implementation

    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> AsyncSocketStream:
        return await self.backend.open_tcp_stream(
            hostname, port, ssl_context, timeout, local_address=local_address
        )

    async def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> AsyncSocketStream:
        return await self.backend.open_uds_stream(path, hostname, ssl_context, timeout)

    def create_lock(self) -> AsyncLock:
        return self.backend.create_lock()

    def create_semaphore(self, max_value: int, exc_class: type) -> AsyncSemaphore:
        return self.backend.create_semaphore(max_value, exc_class=exc_class)

    def time(self) -> float:
        return self.backend.time()
