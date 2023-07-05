import ssl
import typing

import hpack
import hyperframe.frame
import pytest

from httpcore import (
    SOCKET_OPTION,
    AsyncHTTPConnection,
    AsyncMockBackend,
    AsyncMockStream,
    AsyncNetworkStream,
    ConnectError,
    ConnectionNotAvailable,
    Origin,
    RemoteProtocolError,
    WriteError,
)


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


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
@pytest.mark.anyio
async def test_write_error_with_response_sent():
    """
    If a server half-closes the connection while the client is sending
    the request, it may still send a response. In this case the client
    should successfully read and return the response.

    See also the `test_write_error_without_response_sent` test above.
    """

    class ErrorOnRequestTooLargeStream(AsyncMockStream):
        def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
            super().__init__(buffer, http2)
            self.count = 0

        async def write(
            self, buffer: bytes, timeout: typing.Optional[float] = None
        ) -> None:
            self.count += len(buffer)

            if self.count > 1_000_000:
                raise WriteError()

    class ErrorOnRequestTooLarge(AsyncMockBackend):
        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: typing.Optional[float] = None,
            local_address: typing.Optional[str] = None,
            socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
        ) -> AsyncMockStream:
            return ErrorOnRequestTooLargeStream(list(self._buffer), http2=self._http2)

    origin = Origin(b"https", b"example.com", 443)
    network_backend = ErrorOnRequestTooLarge(
        [
            b"HTTP/1.1 413 Payload Too Large\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 37\r\n",
            b"\r\n",
            b"Request body exceeded 1,000,000 bytes",
        ]
    )

    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        content = b"x" * 10_000_000
        response = await conn.request("POST", "https://example.com/", content=content)
        assert response.status == 413
        assert response.content == b"Request body exceeded 1,000,000 bytes"


@pytest.mark.anyio
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
async def test_write_error_without_response_sent():
    """
    If a server fully closes the connection while the client is sending
    the request, then client should raise an error.

    See also the `test_write_error_with_response_sent` test above.
    """

    class ErrorOnRequestTooLargeStream(AsyncMockStream):
        def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
            super().__init__(buffer, http2)
            self.count = 0

        async def write(
            self, buffer: bytes, timeout: typing.Optional[float] = None
        ) -> None:
            self.count += len(buffer)

            if self.count > 1_000_000:
                raise WriteError()

    class ErrorOnRequestTooLarge(AsyncMockBackend):
        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: typing.Optional[float] = None,
            local_address: typing.Optional[str] = None,
            socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
        ) -> AsyncMockStream:
            return ErrorOnRequestTooLargeStream(list(self._buffer), http2=self._http2)

    origin = Origin(b"https", b"example.com", 443)
    network_backend = ErrorOnRequestTooLarge([])

    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        content = b"x" * 10_000_000
        with pytest.raises(RemoteProtocolError) as exc_info:
            await conn.request("POST", "https://example.com/", content=content)
        assert str(exc_info.value) == "Server disconnected without sending a response."


@pytest.mark.anyio
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
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
    def __init__(
        self,
        buffer: typing.List[bytes],
        http2: bool = False,
        connect_tcp_failures: int = 2,
        start_tls_failures: int = 0,
    ) -> None:
        self._connect_tcp_failures = connect_tcp_failures
        self._start_tls_failures = start_tls_failures
        super().__init__(buffer, http2)

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:
        if self._connect_tcp_failures > 0:
            self._connect_tcp_failures -= 1
            raise ConnectError()

        stream = await super().connect_tcp(
            host, port, timeout=timeout, local_address=local_address
        )
        return self._NeedsRetryAsyncNetworkStream(self, stream)

    class _NeedsRetryAsyncNetworkStream(AsyncNetworkStream):
        def __init__(
            self, backend: "NeedsRetryBackend", stream: AsyncNetworkStream
        ) -> None:
            self._backend = backend
            self._stream = stream

        async def read(
            self, max_bytes: int, timeout: typing.Optional[float] = None
        ) -> bytes:
            return await self._stream.read(max_bytes, timeout)

        async def write(
            self, buffer: bytes, timeout: typing.Optional[float] = None
        ) -> None:
            await self._stream.write(buffer, timeout)

        async def aclose(self) -> None:
            await self._stream.aclose()

        async def start_tls(
            self,
            ssl_context: ssl.SSLContext,
            server_hostname: typing.Optional[str] = None,
            timeout: typing.Optional[float] = None,
        ) -> "AsyncNetworkStream":
            if self._backend._start_tls_failures > 0:
                self._backend._start_tls_failures -= 1
                raise ConnectError()

            stream = await self._stream.start_tls(ssl_context, server_hostname, timeout)
            return self._backend._NeedsRetryAsyncNetworkStream(self._backend, stream)

        def get_extra_info(self, info: str) -> typing.Any:
            return self._stream.get_extra_info(info)


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
async def test_connection_retries_tls():
    origin = Origin(b"https", b"example.com", 443)
    content = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: plain/text\r\n",
        b"Content-Length: 13\r\n",
        b"\r\n",
        b"Hello, world!",
    ]

    network_backend = NeedsRetryBackend(
        content, connect_tcp_failures=0, start_tls_failures=2
    )
    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, retries=3
    ) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200

    network_backend = NeedsRetryBackend(
        content, connect_tcp_failures=0, start_tls_failures=2
    )
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
