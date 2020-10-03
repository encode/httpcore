from typing import AsyncIterator, Tuple

import pytest

import httpcore
from httpcore._async.base import ConnectionState
from httpcore._compat import AsyncExitStack, asynccontextmanager
from httpcore._types import URL, Headers


class MockConnection(httpcore.AsyncHTTPTransport):
    def __init__(self, http_version):
        self.origin = (b"http", b"example.org", 80)
        self.state = ConnectionState.PENDING
        self.is_http11 = http_version == "HTTP/1.1"
        self.is_http2 = http_version == "HTTP/2"
        self.stream_count = 0

    @asynccontextmanager
    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: httpcore.AsyncByteStream = None,
        ext: dict = None,
    ) -> AsyncIterator[Tuple[int, Headers, httpcore.AsyncByteStream, dict]]:
        self.state = ConnectionState.ACTIVE
        self.stream_count += 1

        async def on_close():
            self.stream_count -= 1
            if self.stream_count == 0:
                self.state = ConnectionState.IDLE

        async def aiterator() -> AsyncIterator[bytes]:
            yield b""

        stream = httpcore.AsyncIteratorByteStream(
            aiterator=aiterator(), aclose_func=on_close
        )

        try:
            yield 200, [], stream, {}
        finally:
            await stream.aclose()

    async def aclose(self):
        pass

    def info(self) -> str:
        return str(self.state)

    def mark_as_ready(self) -> None:
        self.state = ConnectionState.READY

    def is_connection_dropped(self) -> bool:
        return False


class ConnectionPool(httpcore.AsyncConnectionPool):
    def __init__(self, http_version: str):
        super().__init__()
        self.http_version = http_version
        assert http_version in ("HTTP/1.1", "HTTP/2")

    def _create_connection(self, **kwargs):
        return MockConnection(self.http_version)


async def read_body(stream: httpcore.AsyncByteStream) -> bytes:
    return b"".join([chunk async for chunk in stream])


@pytest.mark.trio
@pytest.mark.parametrize("http_version", ["HTTP/1.1", "HTTP/2"])
async def test_sequential_requests(http_version) -> None:
    async with ConnectionPool(http_version=http_version) as http:
        info = await http.get_connection_info()
        assert info == {}

        async with http.arequest(
            b"GET", (b"http", b"example.org", None, b"/")
        ) as response:
            status_code, headers, stream, ext = response
            info = await http.get_connection_info()
            assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}
            await read_body(stream)

        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}

        async with http.arequest(
            b"GET", (b"http", b"example.org", None, b"/")
        ) as response:
            status_code, headers, stream, ext = response
            info = await http.get_connection_info()
            assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}
            await read_body(stream)

        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}


@pytest.mark.trio
async def test_concurrent_requests_h11() -> None:
    async with ConnectionPool(http_version="HTTP/1.1") as http:
        info = await http.get_connection_info()
        assert info == {}

        async with AsyncExitStack() as exit_stack2:
            async with AsyncExitStack() as exit_stack1:
                response_1 = await exit_stack1.enter_async_context(
                    http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
                )
                status_code_1, headers_1, stream_1, ext_1 = response_1
                info = await http.get_connection_info()
                assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

                response_2 = await exit_stack2.enter_async_context(
                    http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
                )
                status_code_2, headers_2, stream_2, ext_2 = response_2
                info = await http.get_connection_info()
                assert info == {
                    "http://example.org": [
                        "ConnectionState.ACTIVE",
                        "ConnectionState.ACTIVE",
                    ]
                }

                await read_body(stream_1)

            info = await http.get_connection_info()
            assert info == {
                "http://example.org": ["ConnectionState.ACTIVE", "ConnectionState.IDLE"]
            }

            await read_body(stream_2)

        info = await http.get_connection_info()
        assert info == {
            "http://example.org": ["ConnectionState.IDLE", "ConnectionState.IDLE"]
        }


@pytest.mark.trio
async def test_concurrent_requests_h2() -> None:
    async with ConnectionPool(http_version="HTTP/2") as http:
        info = await http.get_connection_info()
        assert info == {}

        async with AsyncExitStack() as exit_stack2:
            async with AsyncExitStack() as exit_stack1:
                response_1 = await exit_stack1.enter_async_context(
                    http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
                )
                status_code_1, headers_1, stream_1, ext_1 = response_1
                info = await http.get_connection_info()
                assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

                response_2 = await exit_stack2.enter_async_context(
                    http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
                )
                status_code_2, headers_2, stream_2, ext_2 = response_2

                info = await http.get_connection_info()
                assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

                await read_body(stream_1)

            info = await http.get_connection_info()
            assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

            await read_body(stream_2)

        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}
