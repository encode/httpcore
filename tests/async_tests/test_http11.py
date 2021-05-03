import collections

import pytest

import httpcore
from httpcore._backends.auto import AsyncBackend, AsyncLock, AsyncSocketStream


class MockStream(AsyncSocketStream):
    def __init__(self, http_buffer, disconnect):
        self.read_buffer = collections.deque(http_buffer)
        self.disconnect = disconnect

    def get_http_version(self) -> str:
        return "HTTP/1.1"

    async def write(self, data, timeout):
        pass

    async def read(self, n, timeout):
        return self.read_buffer.popleft()

    async def aclose(self):
        pass

    def is_readable(self):
        return self.disconnect


class MockLock(AsyncLock):
    async def release(self) -> None:
        pass

    async def acquire(self) -> None:
        pass


class MockBackend(AsyncBackend):
    def __init__(self, http_buffer, disconnect=False):
        self.http_buffer = http_buffer
        self.disconnect = disconnect

    async def open_tcp_stream(
        self, hostname, port, ssl_context, timeout, *, local_address
    ):
        return MockStream(self.http_buffer, self.disconnect)

    def create_lock(self):
        return MockLock()


@pytest.mark.trio
async def test_get_request_with_connection_keepalive() -> None:
    backend = MockBackend(
        http_buffer=[
            b"HTTP/1.1 200 OK\r\n",
            b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
            b"Server: Apache\r\n",
            b"Content-Length: 13\r\n",
            b"Content-Type: text/plain\r\n",
            b"\r\n",
            b"Hello, world.",
            b"HTTP/1.1 200 OK\r\n",
            b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
            b"Server: Apache\r\n",
            b"Content-Length: 13\r\n",
            b"Content-Type: text/plain\r\n",
            b"\r\n",
            b"Hello, world.",
        ]
    )

    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        # We're sending a request with a standard keep-alive connection, so
        # it will remain in the pool once we've sent the request.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = await stream.aread()
        assert status_code == 200
        assert body == b"Hello, world."
        assert await http.get_connection_info() == {
            "http://example.org": ["HTTP/1.1, IDLE"]
        }

        # This second request will go out over the same connection.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = await stream.aread()
        assert status_code == 200
        assert body == b"Hello, world."
        assert await http.get_connection_info() == {
            "http://example.org": ["HTTP/1.1, IDLE"]
        }


@pytest.mark.trio
async def test_get_request_with_connection_close_header() -> None:
    backend = MockBackend(
        http_buffer=[
            b"HTTP/1.1 200 OK\r\n",
            b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
            b"Server: Apache\r\n",
            b"Content-Length: 13\r\n",
            b"Content-Type: text/plain\r\n",
            b"\r\n",
            b"Hello, world.",
            b"",  # Terminate the connection.
        ]
    )

    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        # We're sending a request with 'Connection: close', so the connection
        # does not remain in the pool once we've sent the request.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org"), (b"Connection", b"close")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = await stream.aread()
        assert status_code == 200
        assert body == b"Hello, world."
        assert await http.get_connection_info() == {}

        # The second request will go out over a new connection.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org"), (b"Connection", b"close")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = await stream.aread()
        assert status_code == 200
        assert body == b"Hello, world."
        assert await http.get_connection_info() == {}


@pytest.mark.trio
async def test_get_request_with_socket_disconnect_between_requests() -> None:
    backend = MockBackend(
        http_buffer=[
            b"HTTP/1.1 200 OK\r\n",
            b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
            b"Server: Apache\r\n",
            b"Content-Length: 13\r\n",
            b"Content-Type: text/plain\r\n",
            b"\r\n",
            b"Hello, world.",
        ],
        disconnect=True,
    )

    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        # Send an initial request. We're using a standard keep-alive
        # connection, so the connection remains in the pool after completion.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = await stream.aread()
        assert status_code == 200
        assert body == b"Hello, world."
        assert await http.get_connection_info() == {
            "http://example.org": ["HTTP/1.1, IDLE"]
        }

        # On sending this second request, at the point of pool re-acquiry the
        # socket indicates that it has disconnected, and we'll send the request
        # over a new connection.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = await stream.aread()
        assert status_code == 200
        assert body == b"Hello, world."
        assert await http.get_connection_info() == {
            "http://example.org": ["HTTP/1.1, IDLE"]
        }


@pytest.mark.trio
async def test_get_request_with_unclean_close_after_first_request() -> None:
    backend = MockBackend(
        http_buffer=[
            b"HTTP/1.1 200 OK\r\n",
            b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
            b"Server: Apache\r\n",
            b"Content-Length: 13\r\n",
            b"Content-Type: text/plain\r\n",
            b"\r\n",
            b"Hello, world.",
            b"",  # Terminate the connection.
        ],
    )

    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        # Send an initial request. We're using a standard keep-alive
        # connection, so the connection remains in the pool after completion.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = await stream.aread()
        assert status_code == 200
        assert body == b"Hello, world."
        assert await http.get_connection_info() == {
            "http://example.org": ["HTTP/1.1, IDLE"]
        }

        # At this point we successfully write another request, but the socket
        # read returns `b""`, indicating a premature close.
        with pytest.raises(httpcore.RemoteProtocolError) as excinfo:
            await http.handle_async_request(
                method=b"GET",
                url=(b"http", b"example.org", None, b"/"),
                headers=[(b"Host", b"example.org")],
                stream=httpcore.ByteStream(b""),
                extensions={},
            )
        assert excinfo.value == "Server disconnected without sending a response."
