import typing

import anyio
import pytest

import httpcore


class SlowConnectionBackend(httpcore.AsyncNetworkBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[httpcore.SOCKET_OPTION]] = None,
    ) -> httpcore.AsyncNetworkStream:
        await anyio.sleep(0.5)
        return httpcore.AsyncMockStream(
            buffer=[b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"],
        )


@pytest.mark.anyio
async def test_total_timeout():
    async with httpcore.AsyncConnectionPool(
        network_backend=SlowConnectionBackend(),
    ) as pool:
        with pytest.raises(Exception):
            await pool.request(
                "GET", "http://example.org/", extensions={"timeout": {"total": 0.1}}
            )
