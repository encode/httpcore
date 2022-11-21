from typing import List, Optional

import hpack
import hyperframe.frame
import pytest

from httpcore import AsyncHTTPConnection, ConnectError, ConnectionNotAvailable, Origin
from httpcore.backends.base import AsyncNetworkStream
from httpcore.backends.mock import AsyncMockBackend


@pytest.mark.anyio
async def test_http_connection():
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        assert not conn.is_idle()
        assert not conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert repr(conn) == "<AsyncHTTPConnection [CONNECTING]>"

        async with conn.stream("GET", "https://example.com/") as response:
            assert (
                repr(conn)
                == "<AsyncHTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            )
            await response.aread()

        assert response.status == 200
        assert response.content == b"Hello, world!"

        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        )


@pytest.mark.anyio
async def test_concurrent_requests_not_available_on_http11_connections():
    """
    Attempting to issue a request against an already active HTTP/1.1 connection
    will raise a `ConnectionNotAvailable` exception.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        async with conn.stream("GET", "https://example.com/"):
            with pytest.raises(ConnectionNotAvailable):
                await conn.request("GET", "https://example.com/")


@pytest.mark.anyio
async def test_http2_connection():
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend(
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
                stream_id=1, data=b"Hello, world!", flags=["END_STREAM"]
            ).serialize(),
        ],
        http2=True,
    )

    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, http2=True
    ) as conn:
        response = await conn.request("GET", "https://example.com/")

        assert response.status == 200
        assert response.content == b"Hello, world!"
        assert response.extensions["http_version"] == b"HTTP/2"


@pytest.mark.anyio
async def test_request_to_incorrect_origin():
    """
    A connection can only send requests whichever origin it is connected to.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend([])
    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend
    ) as conn:
        with pytest.raises(RuntimeError):
            await conn.request("GET", "https://other.com/")


class NeedsRetryBackend(AsyncMockBackend):
    def __init__(self, buffer: List[bytes], http2: bool = False) -> None:
        self._retry = 2
        super().__init__(buffer, http2)

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
    ) -> AsyncNetworkStream:
        if self._retry > 0:
            self._retry -= 1
            raise ConnectError()

        return await super().connect_tcp(
            host, port, timeout=timeout, local_address=local_address
        )


@pytest.mark.anyio
async def test_connection_retries():
    origin = Origin(b"https", b"example.com", 443)
    content = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: plain/text\r\n",
        b"Content-Length: 13\r\n",
        b"\r\n",
        b"Hello, world!",
    ]

    network_backend = NeedsRetryBackend(content)
    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, retries=3
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200

    network_backend = NeedsRetryBackend(content)
    async with AsyncHTTPConnection(
        origin=origin,
        network_backend=network_backend,
    ) as conn:
        with pytest.raises(ConnectError):
            await conn.request("GET", "https://example.com/")


@pytest.mark.anyio
async def test_uds_connections():
    # We're not actually testing Unix Domain Sockets here, because we're just
    # using a mock backend, but at least we're covering the UDS codepath
    # in `connection.py` which we may as well do.
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, uds="/mock/example"
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200
