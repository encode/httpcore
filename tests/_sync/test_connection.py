import ssl
import typing
from typing import List, Optional

import hpack
import hyperframe.frame
import pytest

from httpcore import HTTPConnection, ConnectError, ConnectionNotAvailable, Origin
from httpcore.backends.base import NetworkStream
from httpcore.backends.mock import MockBackend



def test_http_connection():
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with HTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        assert not conn.is_idle()
        assert not conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert repr(conn) == "<HTTPConnection [CONNECTING]>"

        with conn.stream("GET", "https://example.com/") as response:
            assert (
                repr(conn)
                == "<HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            )
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"

        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<HTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        )



def test_concurrent_requests_not_available_on_http11_connections():
    """
    Attempting to issue a request against an already active HTTP/1.1 connection
    will raise a `ConnectionNotAvailable` exception.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with HTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        with conn.stream("GET", "https://example.com/"):
            with pytest.raises(ConnectionNotAvailable):
                conn.request("GET", "https://example.com/")



def test_http2_connection():
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend(
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

    with HTTPConnection(
        origin=origin, network_backend=network_backend, http2=True
    ) as conn:
        response = conn.request("GET", "https://example.com/")

        assert response.status == 200
        assert response.content == b"Hello, world!"
        assert response.extensions["http_version"] == b"HTTP/2"



def test_request_to_incorrect_origin():
    """
    A connection can only send requests whichever origin it is connected to.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend([])
    with HTTPConnection(
        origin=origin, network_backend=network_backend
    ) as conn:
        with pytest.raises(RuntimeError):
            conn.request("GET", "https://other.com/")


class NeedsRetryBackend(MockBackend):
    def __init__(
        self,
        buffer: List[bytes],
        http2: bool = False,
        connect_tcp_failures: int = 2,
        start_tls_failures: int = 0,
    ) -> None:
        self._connect_tcp_failures = connect_tcp_failures
        self._start_tls_failures = start_tls_failures
        super().__init__(buffer, http2)

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
    ) -> NetworkStream:
        if self._connect_tcp_failures > 0:
            self._connect_tcp_failures -= 1
            raise ConnectError()

        stream = super().connect_tcp(
            host, port, timeout=timeout, local_address=local_address
        )
        return self._NeedsRetryAsyncNetworkStream(self, stream)

    class _NeedsRetryAsyncNetworkStream(NetworkStream):
        def __init__(
            self, backend: "NeedsRetryBackend", stream: NetworkStream
        ) -> None:
            self._backend = backend
            self._stream = stream

        def read(
            self, max_bytes: int, timeout: typing.Optional[float] = None
        ) -> bytes:
            return self._stream.read(max_bytes, timeout)

        def write(
            self, buffer: bytes, timeout: typing.Optional[float] = None
        ) -> None:
            self._stream.write(buffer, timeout)

        def close(self) -> None:
            self._stream.close()

        def start_tls(
            self,
            ssl_context: ssl.SSLContext,
            server_hostname: typing.Optional[str] = None,
            timeout: typing.Optional[float] = None,
        ) -> "NetworkStream":
            if self._backend._start_tls_failures > 0:
                self._backend._start_tls_failures -= 1
                raise ConnectError()

            stream = self._stream.start_tls(ssl_context, server_hostname, timeout)
            return self._backend._NeedsRetryAsyncNetworkStream(self._backend, stream)

        def get_extra_info(self, info: str) -> typing.Any:
            return self._stream.get_extra_info(info)



def test_connection_retries():
    origin = Origin(b"https", b"example.com", 443)
    content = [
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: plain/text\r\n",
        b"Content-Length: 13\r\n",
        b"\r\n",
        b"Hello, world!",
    ]

    network_backend = NeedsRetryBackend(content)
    with HTTPConnection(
        origin=origin, network_backend=network_backend, retries=3
    ) as conn:
        response = conn.request("GET", "https://example.com/")
        assert response.status == 200

    network_backend = NeedsRetryBackend(content)
    with HTTPConnection(
        origin=origin,
        network_backend=network_backend,
    ) as conn:
        with pytest.raises(ConnectError):
            conn.request("GET", "https://example.com/")



def test_connection_retries_tls():
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
    with HTTPConnection(
        origin=origin, network_backend=network_backend, retries=3
    ) as conn:
        response = conn.request("GET", "https://example.com/")
        assert response.status == 200

    network_backend = NeedsRetryBackend(
        content, connect_tcp_failures=0, start_tls_failures=2
    )
    with HTTPConnection(
        origin=origin,
        network_backend=network_backend,
    ) as conn:
        with pytest.raises(ConnectError):
            conn.request("GET", "https://example.com/")



def test_uds_connections():
    # We're not actually testing Unix Domain Sockets here, because we're just
    # using a mock backend, but at least we're covering the UDS codepath
    # in `connection.py` which we may as well do.
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    with HTTPConnection(
        origin=origin, network_backend=network_backend, uds="/mock/example"
    ) as conn:
        response = conn.request("GET", "https://example.com/")
        assert response.status == 200
