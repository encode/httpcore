import typing

import anyio
import hpack
import hyperframe
import pytest

import httpcore


class SlowWriteStream(httpcore.AsyncNetworkStream):
    """
    A stream that we can use to test cancellations during
    the request writing.
    """

    async def write(
        self, buffer: bytes, timeout: typing.Optional[float] = None
    ) -> None:
        await anyio.sleep(999)

    async def aclose(self) -> None:
        await anyio.sleep(0)


class HandshakeThenSlowWriteStream(httpcore.AsyncNetworkStream):
    """
    A stream that we can use to test cancellations during
    the HTTP/2 request writing, after allowing the initial
    handshake to complete.
    """

    def __init__(self) -> None:
        self._handshake_complete = False

    async def write(
        self, buffer: bytes, timeout: typing.Optional[float] = None
    ) -> None:
        if not self._handshake_complete:
            self._handshake_complete = True
        else:
            await anyio.sleep(999)

    async def aclose(self) -> None:
        await anyio.sleep(0)


class SlowReadStream(httpcore.AsyncNetworkStream):
    """
    A stream that we can use to test cancellations during
    the response reading.
    """

    def __init__(self, buffer: typing.List[bytes]):
        self._buffer = buffer

    async def write(self, buffer, timeout=None):
        pass

    async def read(
        self, max_bytes: int, timeout: typing.Optional[float] = None
    ) -> bytes:
        if not self._buffer:
            await anyio.sleep(999)
        return self._buffer.pop(0)

    async def aclose(self):
        await anyio.sleep(0)


class SlowWriteBackend(httpcore.AsyncNetworkBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[httpcore.SOCKET_OPTION]] = None,
    ) -> httpcore.AsyncNetworkStream:
        return SlowWriteStream()


class SlowReadBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, buffer: typing.List[bytes]):
        self._buffer = buffer

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[httpcore.SOCKET_OPTION]] = None,
    ) -> httpcore.AsyncNetworkStream:
        return SlowReadStream(self._buffer)


@pytest.mark.anyio
async def test_connection_pool_timeout_during_request():
    """
    An async timeout when writing an HTTP/1.1 response on the connection pool
    should leave the pool in a consistent state.

    In this case, that means the connection will become closed, and no
    longer remain in the pool.
    """
    network_backend = SlowWriteBackend()
    async with httpcore.AsyncConnectionPool(network_backend=network_backend) as pool:
        with anyio.move_on_after(0.01):
            await pool.request("GET", "http://example.com")
        assert not pool.connections


@pytest.mark.anyio
async def test_connection_pool_timeout_during_response():
    """
    An async timeout when reading an HTTP/1.1 response on the connection pool
    should leave the pool in a consistent state.

    In this case, that means the connection will become closed, and no
    longer remain in the pool.
    """
    network_backend = SlowReadBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 1000\r\n",
            b"\r\n",
            b"Hello, world!...",
        ]
    )
    async with httpcore.AsyncConnectionPool(network_backend=network_backend) as pool:
        with anyio.move_on_after(0.01):
            await pool.request("GET", "http://example.com")
        assert not pool.connections


@pytest.mark.anyio
async def test_h11_timeout_during_request():
    """
    An async timeout on an HTTP/1.1 during the request writing
    should leave the connection in a neatly closed state.
    """
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = SlowWriteStream()
    async with httpcore.AsyncHTTP11Connection(origin, stream) as conn:
        with anyio.move_on_after(0.01):
            await conn.request("GET", "http://example.com")
        assert conn.is_closed()


@pytest.mark.anyio
async def test_h11_timeout_during_response():
    """
    An async timeout on an HTTP/1.1 during the response reading
    should leave the connection in a neatly closed state.
    """
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = SlowReadStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 1000\r\n",
            b"\r\n",
            b"Hello, world!...",
        ]
    )
    async with httpcore.AsyncHTTP11Connection(origin, stream) as conn:
        with anyio.move_on_after(0.01):
            await conn.request("GET", "http://example.com")
        assert conn.is_closed()


@pytest.mark.xfail
@pytest.mark.anyio
async def test_h2_timeout_during_handshake():
    """
    An async timeout on an HTTP/2 during the initial handshake
    should leave the connection in a neatly closed state.
    """
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = SlowWriteStream()
    async with httpcore.AsyncHTTP2Connection(origin, stream) as conn:
        with anyio.move_on_after(0.01):
            await conn.request("GET", "http://example.com")
        assert conn.is_closed()


@pytest.mark.xfail
@pytest.mark.anyio
async def test_h2_timeout_during_request():
    """
    An async timeout on an HTTP/2 during a request
    should leave the connection in a neatly idle state.

    The connection is not closed because it is multiplexed,
    and a timeout on one request does not require the entire
    connection be closed.
    """
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = HandshakeThenSlowWriteStream()
    async with httpcore.AsyncHTTP2Connection(origin, stream) as conn:
        with anyio.move_on_after(0.01):
            await conn.request("GET", "http://example.com")

        assert not conn.is_closed()
        assert conn.is_idle()


@pytest.mark.xfail
@pytest.mark.anyio
async def test_h2_timeout_during_response():
    """
    An async timeout on an HTTP/2 during the response reading
    should leave the connection in a neatly idle state.

    The connection is not closed because it is multiplexed,
    and a timeout on one request does not require the entire
    connection be closed.
    """
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = SlowReadStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.DataFrame(
                stream_id=1, data=b"Hello, world!...", flags=[]
            ).serialize(),
        ]
    )
    async with httpcore.AsyncHTTP2Connection(origin, stream) as conn:
        with anyio.move_on_after(0.01):
            await conn.request("GET", "http://example.com")

        assert not conn.is_closed()
        assert conn.is_idle()


@pytest.mark.parametrize("cancel_during", ["state_lock", "network_close"])
def test_http11_double_cancel_releases_connection(cancel_during):
    """A second cancellation must not prevent the pool from retrying cleanup."""
    import asyncio

    async def run() -> None:
        reading = asyncio.Event()
        closing = asyncio.Event()
        never = asyncio.Event()

        class Stream(httpcore.AsyncMockStream):
            async def read(self, max_bytes, timeout=None):
                if not self._buffer:
                    reading.set()
                    await never.wait()
                return await super().read(max_bytes, timeout)

            async def aclose(self):
                if cancel_during == "network_close" and not closing.is_set():
                    closing.set()
                    await never.wait()
                await super().aclose()

        streams = []

        class Backend(httpcore.AsyncMockBackend):
            async def connect_tcp(self, *args, **kwargs):
                stream = Stream([b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nx"])
                streams.append(stream)
                return stream

        async def trace(name, info):
            if (
                cancel_during == "state_lock"
                and name == "http11.response_closed.started"
            ):
                closing.set()

        async with httpcore.AsyncConnectionPool(
            network_backend=Backend([]), max_connections=1
        ) as pool:

            async def consume() -> None:
                async with pool.stream(
                    "GET", "http://example.com", extensions={"trace": trace}
                ) as response:
                    async for _ in response.aiter_stream():
                        pass

            task = asyncio.create_task(consume())
            await asyncio.wait_for(reading.wait(), 1)
            pooled_connection = pool.connections[0]
            assert isinstance(pooled_connection, httpcore.AsyncHTTPConnection)
            connection = pooled_connection._connection
            assert isinstance(connection, httpcore.AsyncHTTP11Connection)
            lock = connection._state_lock
            if cancel_during == "state_lock":
                await lock.__aenter__()
            try:
                task.cancel()
                await asyncio.wait_for(closing.wait(), 1)
                task.cancel()
                # Deliver cancellation while cleanup is still blocked.
                await asyncio.sleep(0)
            finally:
                if cancel_during == "state_lock":
                    await lock.__aexit__(None, None, None)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)

            assert connection.is_closed()
            assert streams[0]._closed
            assert not pool.connections
            assert not pool._requests

            # A one-slot pool must still be able to service another request.
            async with pool.stream(
                "GET", "http://example.com", extensions={"timeout": {"pool": 0.1}}
            ) as response:
                assert response.status == 200
            assert not pool.connections
            assert streams[1]._closed

    asyncio.run(run())
