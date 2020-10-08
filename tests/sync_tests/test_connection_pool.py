from typing import Iterator, Tuple, Type
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

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: httpcore.SyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, httpcore.SyncByteStream, dict]:
        self.state = ConnectionState.ACTIVE
        self.stream_count += 1

        def on_close():
            self.stream_count -= 1
            if self.stream_count == 0:
                self.state = ConnectionState.IDLE

        def iterator() -> Iterator[bytes]:
            yield b""

        stream = httpcore.IteratorByteStream(
            iterator=iterator(), close_func=on_close
        )

        return 200, [], stream, {}

    def close(self):
        pass

    def info(self) -> str:
        return str(self.state)

    def mark_as_ready(self) -> None:
        self.state = ConnectionState.READY

    def is_connection_dropped(self) -> bool:
        return False


class AlwaysPendingConnection(MockConnection):
    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: httpcore.SyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, httpcore.SyncByteStream, dict]:
        result = super().request(method, url, headers, stream, ext)
        self.state = ConnectionState.PENDING
        return result


class BrokenConnection(MockConnection):
    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: httpcore.SyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, httpcore.SyncByteStream, dict]:
        raise ConnectionRefusedError


class ConnectionPool(httpcore.SyncConnectionPool):
    def __init__(
        self,
        http_version: str,
        connection_class: Type = MockConnection,
    ):
        super().__init__()
        self.http_version = http_version
        if http_version == "HTTP/2":
            self._http2 = True
        self.connection_class = connection_class
        assert http_version in ("HTTP/1.1", "HTTP/2")

    def _create_connection(self, **kwargs):
        return self.connection_class(self.http_version)


def read_body(stream: httpcore.SyncByteStream) -> bytes:
    try:
        body = []
        for chunk in stream:
            body.append(chunk)
        return b"".join(body)
    finally:
        stream.close()



@pytest.mark.parametrize("http_version", ["HTTP/1.1", "HTTP/2"])
def test_sequential_requests(http_version) -> None:
    with ConnectionPool(http_version=http_version) as http:
        info = http.get_connection_info()
        assert info == {}

        response = http.request(b"GET", (b"http", b"example.org", None, b"/"))
        status_code, headers, stream, ext = response
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        read_body(stream)
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}

        response = http.request(b"GET", (b"http", b"example.org", None, b"/"))
        status_code, headers, stream, ext = response
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        read_body(stream)
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}



def test_concurrent_requests_h11() -> None:
    with ConnectionPool(http_version="HTTP/1.1") as http:
        info = http.get_connection_info()
        assert info == {}

        response_1 = http.request(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_1, headers_1, stream_1, ext_1 = response_1
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        response_2 = http.request(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_2, headers_2, stream_2, ext_2 = response_2
        info = http.get_connection_info()
        assert info == {
            "http://example.org": ["ConnectionState.ACTIVE", "ConnectionState.ACTIVE"]
        }

        read_body(stream_1)
        info = http.get_connection_info()
        assert info == {
            "http://example.org": ["ConnectionState.ACTIVE", "ConnectionState.IDLE"]
        }

        read_body(stream_2)
        info = http.get_connection_info()
        assert info == {
            "http://example.org": ["ConnectionState.IDLE", "ConnectionState.IDLE"]
        }



def test_concurrent_requests_h2() -> None:
    with ConnectionPool(http_version="HTTP/2") as http:
        info = http.get_connection_info()
        assert info == {}

        response_1 = http.request(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_1, headers_1, stream_1, ext_1 = response_1
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        response_2 = http.request(b"GET", (b"http", b"example.org", None, b"/"))
        status_code_2, headers_2, stream_2, ext_2 = response_2
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        read_body(stream_1)
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.ACTIVE"]}

        read_body(stream_2)
        info = http.get_connection_info()
        assert info == {"http://example.org": ["ConnectionState.IDLE"]}



def test_connection_with_exception_has_been_removed_from_pool():
    with ConnectionPool(
        http_version="HTTP/2", connection_class=BrokenConnection
    ) as http:
        with pytest.raises(ConnectionRefusedError):
            http.request(b"GET", (b"http", b"example.org", None, b"/"))

        assert len(http.get_connection_info()) == 0


@patch("importlib.util.find_spec", autospec=True)

def test_that_we_cannot_start_http2_connection_without_h2_lib(find_spec_mock):
    find_spec_mock.return_value = None

    with pytest.raises(ImportError):
        with httpcore.SyncConnectionPool(http2=True):
            pass



def test_that_we_can_reuse_pending_http2_connection():
    with ConnectionPool(
        http_version="HTTP/2", connection_class=AlwaysPendingConnection
    ) as http:
        for _ in range(2):
            _ = http.request(b"GET", (b"http", b"example.org", None, b"/"))

        info = http.get_connection_info()

        assert info == {"http://example.org": ["ConnectionState.PENDING"]}
