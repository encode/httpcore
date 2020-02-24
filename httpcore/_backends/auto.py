from ssl import SSLContext
from typing import Dict, Optional

import sniffio

from .base import AsyncBackend, AsyncLock, AsyncSocketStream
from .sync import SyncBackend, SyncLock, SyncSocketStream


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
        timeout: Dict[str, Optional[float]],
    ) -> AsyncSocketStream:
        return await self.backend.open_tcp_stream(hostname, port, ssl_context, timeout)

    def create_lock(self) -> AsyncLock:
        return self.backend.create_lock()
