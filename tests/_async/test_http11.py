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
async def test_http11_expect_continue():
    """
    HTTP "100 Continue" is an interim response.
    We simply ignore it and return the final response.

    https://httpwg.org/specs/rfc9110.html#status.100
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/100
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 100 Continue\r\n",
            b"\r\n",
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
        response = await conn.request(
            "GET",
            "https://example.com/",
            headers={"Expect": "continue"},
        )
        assert response.status == 200
        assert response.content == b"Hello, world!"


@pytest.mark.anyio
async def test_http11_upgrade_connection():
    """
    HTTP "101 Switching Protocols" indicates an upgraded connection.

    We should return the response, so that the network stream
    may be used for the upgraded connection.

    https://httpwg.org/specs/rfc9110.html#status.101
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/101
    """
    origin = Origin(b"wss", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 101 Switching Protocols\r\n",
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
            "wss://example.com/",
            headers={"Connection": "upgrade", "Upgrade": "custom"},
        ) as response:
            assert response.status == 101
            network_stream = response.extensions["network_stream"]
            content = await network_stream.read(max_bytes=1024)
            assert content == b"..."


@pytest.mark.anyio
async def test_http11_early_hints():
    """
    HTTP "103 Early Hints" is an interim response.
    We simply ignore it and return the final response.

    https://datatracker.ietf.org/doc/rfc8297/
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 103 Early Hints\r\n",
            b"Link: </style.css>; rel=preload; as=style\r\n",
            b"Link: </script.js.css>; rel=preload; as=style\r\n",
            b"\r\n",
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: text/html; charset=utf-8\r\n",
            b"Content-Length: 30\r\n",
            b"Link: </style.css>; rel=preload; as=style\r\n",
            b"Link: </script.js>; rel=preload; as=script\r\n",
            b"\r\n",
            b"<html>Hello, world! ...</html>",
        ]
    )
    async with AsyncHTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        response = await conn.request(
            "GET",
            "https://example.com/",
            headers={"Expect": "continue"},
        )
        assert response.status == 200
        assert response.content == b"<html>Hello, world! ...</html>"


@pytest.mark.anyio
async def test_http11_header_sub_100kb():
    """
    A connection should be able to handle a http header size up to 100kB.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            b"HTTP/1.1 200 OK\r\n",  # 17
            b"Content-Type: plain/text\r\n",  # 43
            b"Cookie: " + b"x" * (100 * 1024 - 72) + b"\r\n",  # 102381
            b"Content-Length: 0\r\n",  # 102400
            b"\r\n",
            b"",
        ]
    )
    async with AsyncHTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b""
