import typing
from typing import Optional

import anyio
import pytest

import httpcore
from httpcore.backends.auto import AutoBackend
from httpcore.backends.base import SOCKET_OPTION, AsyncNetworkBackend
from httpcore.backends.mock import AsyncNetworkStream


class SlowStream(AsyncNetworkStream):
    async def write(
        self, buffer: bytes, timeout: typing.Optional[float] = None
    ) -> None:
        await AutoBackend().sleep(2)

    async def aclose(self) -> None:
        ...


class SlowBackend(AsyncNetworkBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:
        return SlowStream()


@pytest.mark.anyio
async def test_async_cancellation():
    pool = httpcore.AsyncConnectionPool(network_backend=SlowBackend())
    with anyio.move_on_after(1):
        await pool.request(
            "GET", "http://example.com"
        )
    assert not pool.connections
