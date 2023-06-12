import typing
from functools import wraps
from typing import Optional

import anyio
import sniffio

from .base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream

_R = typing.TypeVar("_R")


class AutoBackend(AsyncNetworkBackend):
    fail_after = anyio.fail_after

    async def _init_backend(self) -> None:
        if not (hasattr(self, "_backend")):
            backend = sniffio.current_async_library()
            if backend == "trio":
                from .trio import TrioBackend

                self._backend: AsyncNetworkBackend = TrioBackend()
            else:
                from .anyio import AnyIOBackend

                self._backend = AnyIOBackend()

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

    @staticmethod
    def shield_cancellation(
        fnc: typing.Callable[..., typing.Awaitable[_R]]
    ) -> typing.Callable[..., typing.Awaitable[_R]]:
        # Makes an async function that runs in a cancellation-isolated environment.

        @wraps(fnc)
        async def inner(*args: typing.Any, **kwargs: typing.Any) -> _R:
            with anyio.CancelScope(shield=True):
                return await fnc(*args, **kwargs)

        return inner
