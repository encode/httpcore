import typing
from typing import Optional

import anyio
import pytest

import httpcore
from httpcore._async.http2 import HTTPConnectionState as HTTP2ConnectionState
from httpcore._async.http11 import HTTPConnectionState as HTTP11ConnectionState
from httpcore._synchronization import AsyncSemaphore


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


@pytest.mark.anyio
async def test_h11_response_closed():
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.AsyncMockStream([])
    async with httpcore.AsyncHTTP11Connection(origin, stream) as conn:
        # mock
        with anyio.CancelScope() as cancel_scope:
            cancel_scope.cancel()
            await conn.request("GET", "https://example.com")
        assert conn._state == HTTP11ConnectionState.CLOSED


@pytest.mark.anyio
async def test_h2_response_closed():
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.AsyncMockStream([])
    events = {0: None}
    async with httpcore.AsyncHTTP2Connection(origin, stream) as conn:
        # mock
        conn._state = HTTP2ConnectionState.ACTIVE
        conn._max_streams_semaphore = AsyncSemaphore(1)
        conn._events = events
        await conn._max_streams_semaphore.acquire()

        with anyio.CancelScope() as cancel_scope:
            cancel_scope.cancel()
            await conn._response_closed(0)
        assert conn._state == HTTP2ConnectionState.CLOSED
