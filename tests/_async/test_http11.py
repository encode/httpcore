import pytest

from httpcore import (
    AsyncHTTP11Connection,
    ConnectionNotAvailable,
    LocalProtocolError,
    Origin,
    RemoteProtocolError,
)
from httpcore.backends.mock import AsyncMockStream


@pytest.mark.anyio
async def test_http11_connection():
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    async with AsyncHTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"

        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTP11Connection ['https://example.com:443', IDLE, Request Count: 1]>"
        )


@pytest.mark.anyio
async def test_http11_connection_chunked_response():
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Transfer-Encoding: chunked\r\n",
            b"\r\n",
            b"3\r\n",
            b"Hel\r\n",
            b"4\r\n",
            b"lo, \r\n",
            b"6\r\n",
            b"world!\r\n",
            b"0\r\n",
            b"\r\n",
        ]
    )
    async with AsyncHTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"

        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTP11Connection ['https://example.com:443', IDLE, Request Count: 1]>"
        )


@pytest.mark.anyio
async def test_http11_connection_trailing_headers_response():
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Transfer-Encoding: chunked\r\n",
            b"Trailer: Surprise\r\n",
            b"\r\n",
            b"3\r\n",
            b"Hel\r\n",
            b"4\r\n",
            b"lo, \r\n",
            b"6\r\n",
            b"world!\r\n",
            b"0\r\n",
            b"Surprise: You thought we were done here?\r\n",
            b"\r\n",
        ]
    )
    async with AsyncHTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        response = await conn.request(
            "GET", "https://example.com/", headers={"TE": "trailers"}
        )
        assert response.status == 200
        assert response.content == b"Hello, world!"
        assert response.headers == [
            (b"Content-Type", b"plain/text"),
            (b"Transfer-Encoding", b"chunked"),
            (b"Trailer", b"Surprise"),
        ]
        trailing_headers = response.extensions["trailing_headers"]
        assert trailing_headers == [(b"Surprise", b"You thought we were done here?")]


@pytest.mark.anyio
async def test_http11_connection_unread_response():
    """
    If the client releases the response without reading it to termination,
    then the connection will not be reusable.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    async with AsyncHTTP11Connection(origin=origin, stream=stream) as conn:
        async with conn.stream("GET", "https://example.com/") as response:
            assert response.status == 200

        assert not conn.is_idle()
        assert conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTP11Connection ['https://example.com:443', CLOSED, Request Count: 1]>"
        )


@pytest.mark.anyio
async def test_http11_connection_with_remote_protocol_error():
    """
    If a remote protocol error occurs, then no response will be returned,
    and the connection will not be reusable.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream([b"Wait, this isn't valid HTTP!", b""])
    async with AsyncHTTP11Connection(origin=origin, stream=stream) as conn:
        with pytest.raises(RemoteProtocolError):
            await conn.request("GET", "https://example.com/")

        assert not conn.is_idle()
        assert conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTP11Connection ['https://example.com:443', CLOSED, Request Count: 1]>"
        )


@pytest.mark.anyio
async def test_http11_connection_with_incomplete_response():
    """
    We should be gracefully handling the case where the connection ends prematurely.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, wor",
        ]
    )
    async with AsyncHTTP11Connection(origin=origin, stream=stream) as conn:
        with pytest.raises(RemoteProtocolError):
            await conn.request("GET", "https://example.com/")

        assert not conn.is_idle()
        assert conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTP11Connection ['https://example.com:443', CLOSED, Request Count: 1]>"
        )


@pytest.mark.anyio
async def test_http11_connection_with_local_protocol_error():
    """
    If a local protocol error occurs, then no response will be returned,
    and the connection will not be reusable.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    async with AsyncHTTP11Connection(origin=origin, stream=stream) as conn:
        with pytest.raises(LocalProtocolError) as exc_info:
            await conn.request("GET", "https://example.com/", headers={"Host": "\0"})

        assert str(exc_info.value) == "Illegal header value b'\\x00'"

        assert not conn.is_idle()
        assert conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTP11Connection ['https://example.com:443', CLOSED, Request Count: 1]>"
        )


@pytest.mark.anyio
async def test_http11_connection_handles_one_active_request():
    """
    Attempting to send a request while one is already in-flight will raise
    a ConnectionNotAvailable exception.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    async with AsyncHTTP11Connection(origin=origin, stream=stream) as conn:
        async with conn.stream("GET", "https://example.com/"):
            with pytest.raises(ConnectionNotAvailable):
                await conn.request("GET", "https://example.com/")


@pytest.mark.anyio
async def test_http11_connection_attempt_close():
    """
    A connection can only be closed when it is idle.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    async with AsyncHTTP11Connection(origin=origin, stream=stream) as conn:
        async with conn.stream("GET", "https://example.com/") as response:
            await response.aread()
            assert response.status == 200
            assert response.content == b"Hello, world!"


@pytest.mark.anyio
async def test_http11_request_to_incorrect_origin():
    """
    A connection can only send requests to whichever origin it is connected to.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream([])
    async with AsyncHTTP11Connection(origin=origin, stream=stream) as conn:
        with pytest.raises(RuntimeError):
            await conn.request("GET", "https://other.com/")


@pytest.mark.anyio
async def test_http11_upgrade_connection():
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 101 OK\r\n",
            b"Connection: upgrade\r\n",
            b"Upgrade: custom\r\n",
            b"\r\n",
            b"...",
        ]
    )
    async with AsyncHTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        async with conn.stream(
            "GET",
            "https://example.com/",
            headers={"Connection": "upgrade", "Upgrade": "custom"},
        ) as response:
            assert response.status == 101
            network_stream = response.extensions["network_stream"]
            content = await network_stream.read(max_bytes=1024)
            assert content == b"..."
