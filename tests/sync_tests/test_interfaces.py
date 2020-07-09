import ssl
import typing

import pytest

import httpcore


def read_body(stream: httpcore.SyncByteStream) -> bytes:
    try:
        body = []
        for chunk in stream:
            body.append(chunk)
        return b"".join(body)
    finally:
        stream.close()



def test_http_request() -> None:
    with httpcore.SyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_https_request() -> None:
    with httpcore.SyncConnectionPool() as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_http2_request() -> None:
    with httpcore.SyncConnectionPool(http2=True) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/2"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_closing_http_request() -> None:
    with httpcore.SyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org"), (b"connection", b"close")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert url[:3] not in http._connections  # type: ignore



def test_http_request_reuse_connection() -> None:
    with httpcore.SyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore

        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_https_request_reuse_connection() -> None:
    with httpcore.SyncConnectionPool() as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore

        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_http_request_cannot_reuse_dropped_connection() -> None:
    with httpcore.SyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore

        # Mock the connection as having been dropped.
        connection = list(http._connections[url[:3]])[0]  # type: ignore
        connection.is_connection_dropped = lambda: True

        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "FORWARD_ONLY", "TUNNEL_ONLY"])

def test_http_proxy(
    proxy_server: typing.Tuple[bytes, bytes, int], proxy_mode: str
) -> None:
    method = b"GET"
    url = (b"http", b"example.org", 80, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    max_keepalive = 2
    with httpcore.SyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        max_connections=max_connections,
        max_keepalive=max_keepalive,
    ) as http:
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"


@pytest.mark.parametrize("local_addr", ["0.0.0.0"])

# This doesn't run with trio, since trio doesn't support local_addr.
def test_http_request_local_addr(local_addr: str) -> None:
    with httpcore.SyncConnectionPool(local_addr=local_addr) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        body = read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


# mitmproxy does not support forwarding HTTPS requests
@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "TUNNEL_ONLY"])

@pytest.mark.parametrize("http2", [False, True])
def test_proxy_https_requests(
    proxy_server: typing.Tuple[bytes, bytes, int],
    ca_ssl_context: ssl.SSLContext,
    proxy_mode: str,
    http2: bool,
) -> None:
    method = b"GET"
    url = (b"https", b"example.org", 443, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    max_keepalive = 2
    with httpcore.SyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        ssl_context=ca_ssl_context,
        max_connections=max_connections,
        max_keepalive=max_keepalive,
        http2=http2,
    ) as http:
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        _ = read_body(stream)

        assert http_version == (b"HTTP/2" if http2 else b"HTTP/1.1")
        assert status_code == 200
        assert reason == b"OK"


@pytest.mark.parametrize(
    "http2,expected",
    [
        (False, ["HTTP/1.1, ACTIVE", "HTTP/1.1, ACTIVE"]),
        (True, ["HTTP/2, ACTIVE, 2 streams"]),
    ],
)

def test_connection_pool_get_connection_info(http2, expected) -> None:
    with httpcore.SyncConnectionPool(http2=http2) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        for _ in range(2):
            _ = http.request(method, url, headers)
        stats = http.get_connection_info()
        assert stats == {"https://example.org": expected}
