from typing import AsyncIterator, Tuple, Type
from unittest.mock import patch

import pytest

import httpcore
from httpcore._async.base import ConnectionState
from httpcore._types import URL, Headers


class MockConnection(object):
    def __init__(self, http_version):
        self.origin = (b"http", b"example.org", 80)
        self.state = ConnectionState.PENDING
        self.is_http11 = http_version == "HTTP/1.1"
        self.is_http2 = http_version == "HTTP/2"
        self.stream_count = 0

    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: httpcore.AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, httpcore.AsyncByteStream, dict]:
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

        return 200, [], stream, {}

    async def aclose(self):
        pass

    def info(self) -> str:
        return str(self.state)

    def mark_as_ready(self) -> None:
        self.state = ConnectionState.READY

    def is_connection_dropped(self) -> bool:
        return False


class BrokenConnection(MockConnection):
    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: httpcore.AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, httpcore.AsyncByteStream, dict]:
        raise ConnectionRefusedError


class ConnectionPool(httpcore.AsyncConnectionPool):
    def __init__(
        self,
        http_version: str,
        connection_class: Type = MockConnection,
    ):
        super().__init__()
        self.http_version = http_version
        self.connection_class = connection_class
        assert http_version in ("HTTP/1.1", "HTTP/2")

    def _create_connection(self, **kwargs):
        return self.connection_class(self.http_version)


async def read_body(stream: httpcore.AsyncByteStream) -> bytes:
    try:
        body = []
        async for chunk in stream:
            body.append(chunk)
        return b"".join(body)
    finally:
        await stream.aclose()


@pytest.mark.trio
@pytest.mark.parametrize("http_version", ["HTTP/1.1", "HTTP/2"])
async def test_sequential_requests(http_version) -> None:
    async with ConnectionPool(http_version=http_version) as http:
        info = await http.get_connection_info()
        assert info == {}

        response = await http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
        status_code, headers, stream, ext = response
        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        await read_body(stream)
        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}

        response = await http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
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

        response_1 = await http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_1, headers_1, stream_1, ext_1 = response_1
        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        response_2 = await http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_2, headers_2, stream_2, ext_2 = response_2
        info = await http.get_connection_info()
        assert info == {
            "http://example.org": ["ConnectionState.ACTIVE", "ConnectionState.ACTIVE"]
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

        response_1 = await http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_1, headers_1, stream_1, ext_1 = response_1
        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        response_2 = await http.arequest(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_2, headers_2, stream_2, ext_2 = response_2
        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        await read_body(stream_1)
        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        await read_body(stream_2)
        info = await http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}


@pytest.mark.trio
async def test_connection_with_exception_has_been_removed_from_pool():
    async with ConnectionPool(
        http_version="HTTP/2", connection_class=BrokenConnection
    ) as http:
        with pytest.raises(ConnectionRefusedError):
            await http.arequest(b"GET", (b"http", b"example.org", None, b"/"))

        assert len(await http.get_connection_info()) == 0


@patch("importlib.util.find_spec", autospec=True)
@pytest.mark.trio
async def test_that_we_cannot_start_http2_connection_without_h2_lib(find_spec_mock):
    find_spec_mock.return_value = None

    with pytest.raises(ImportError):
        async with httpcore.AsyncConnectionPool(http2=True):
            pass
