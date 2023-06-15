import typing

import anyio
import pytest

import httpcore


class SlowStream(httpcore.AsyncNetworkStream):
    async def write(
        self, buffer: bytes, timeout: typing.Optional[float] = None
    ) -> None:
        await anyio.sleep(2)

    async def aclose(self) -> None:
        ...


class SlowBackend(httpcore.AsyncNetworkBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[httpcore.SOCKET_OPTION]] = None,
    ) -> httpcore.AsyncNetworkStream:
        return SlowStream()


@pytest.mark.anyio
async def test_async_cancellation():
    async with httpcore.AsyncConnectionPool(network_backend=SlowBackend()) as pool:
        with anyio.move_on_after(0.001):
            await pool.request("GET", "http://example.com")
        assert not pool.connections


@pytest.mark.anyio
async def test_h11_response_closed():
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = SlowStream()
    async with httpcore.AsyncHTTP11Connection(origin, stream) as conn:
        with anyio.move_on_after(0.001):
            await conn.request("GET", "http://example.com")
        assert conn.is_closed()


@pytest.mark.anyio
async def test_h2_response_closed():
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = SlowStream()
    async with httpcore.AsyncHTTP2Connection(origin, stream) as conn:
        with anyio.move_on_after(0.001):
            await conn.request("GET", "http://example.com")
        assert conn.is_closed()
