import typing
from typing import Optional

import anyio
import pytest

import httpcore


class SlowStream(httpcore.AsyncNetworkStream):
    async def write(
        self, buffer: bytes, timeout: typing.Optional[float] = None
    ) -> None:
        await httpcore._backends.auto.AutoBackend().sleep(2)

    async def aclose(self) -> None:
        ...


class SlowBackend(httpcore.AsyncNetworkBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[httpcore.SOCKET_OPTION]] = None,
    ) -> httpcore.AsyncNetworkStream:
        return SlowStream()


@pytest.mark.anyio
async def test_async_cancellation():
    async with httpcore.AsyncConnectionPool(network_backend=SlowBackend()) as pool:
        with anyio.move_on_after(0.001):
            await pool.request("GET", "http://example.com")
        assert not pool.connections
