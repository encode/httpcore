import typing
from importlib.util import find_spec
from typing import Optional, Type

from .._synchronization import current_async_backend
from .base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream

HAS_ANYIO = find_spec("anyio") is not None


class AutoBackend(AsyncNetworkBackend):
    @staticmethod
    def set_default_backend(backend_class: Optional[Type[AsyncNetworkBackend]]) -> None:
        setattr(AutoBackend, "_default_backend_class", backend_class)

    async def _init_backend(self) -> None:
        if hasattr(self, "_backend"):
            return

        default_backend_class: Optional[Type[AsyncNetworkBackend]] = getattr(
            AutoBackend, "_default_backend_class", None
        )
        if default_backend_class is not None:
            self._backend = default_backend_class()
            return

        if current_async_backend() == "trio":
            from .trio import TrioBackend

            self._backend = TrioBackend()
        elif HAS_ANYIO:
            from .anyio import AnyIOBackend

            self._backend = AnyIOBackend()
        else:
            from .asyncio import AsyncioBackend

            self._backend = AsyncioBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:
        await self._init_backend()
        return await self._backend.connect_tcp(
            host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:  # pragma: nocover
        await self._init_backend()
        return await self._backend.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    async def sleep(self, seconds: float) -> None:  # pragma: nocover
        await self._init_backend()
        return await self._backend.sleep(seconds)
