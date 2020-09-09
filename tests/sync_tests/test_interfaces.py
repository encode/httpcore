import platform
import ssl

import pytest

import httpcore
from httpcore._types import URL
from tests.conftest import Server, detect_backend


def read_body(stream: httpcore.SyncByteStream) -> bytes:
    try:
        body = []
        for chunk in stream:
            body.append(chunk)
        return b"".join(body)
    finally:
        stream.close()



def test_http_request() -> None:
    with httpcore.SyncConnectionPool(backend="sync") as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_https_request() -> None:
    with httpcore.SyncConnectionPool(backend="sync") as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_request_unsupported_protocol() -> None:
    with httpcore.SyncConnectionPool(backend="sync") as http:
        method = b"GET"
        url = (b"ftp", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        with pytest.raises(httpcore.UnsupportedProtocol):
            http.request(method, url, headers)



def test_http2_request() -> None:
    with httpcore.SyncConnectionPool(backend="sync", http2=True) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/2"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_closing_http_request() -> None:
    with httpcore.SyncConnectionPool(backend="sync") as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org"), (b"connection", b"close")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert url[:3] not in http._connections  # type: ignore



def test_http_request_reuse_connection() -> None:
    with httpcore.SyncConnectionPool(backend="sync") as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

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
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_https_request_reuse_connection() -> None:
    with httpcore.SyncConnectionPool(backend="sync") as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

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
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore



def test_http_request_cannot_reuse_dropped_connection() -> None:
    with httpcore.SyncConnectionPool(backend="sync") as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore

        # Mock the connection as having been dropped.
        connection = list(http._connections[url[:3]])[0]  # type: ignore
        connection.is_connection_dropped = lambda: True  # type: ignore

        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "FORWARD_ONLY", "TUNNEL_ONLY"])

def test_http_proxy(proxy_server: URL, proxy_mode: str) -> None:
    method = b"GET"
    url = (b"http", b"example.org", 80, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    with httpcore.SyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        max_connections=max_connections,
        backend="sync",
    ) as http:
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"



# This doesn't run with trio, since trio doesn't support local_address.
def test_http_request_local_address() -> None:
    with httpcore.SyncConnectionPool(
        backend="sync", local_address="0.0.0.0"
    ) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


# mitmproxy does not support forwarding HTTPS requests
@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "TUNNEL_ONLY"])

@pytest.mark.parametrize("http2", [False, True])
def test_proxy_https_requests(
    proxy_server: URL, ca_ssl_context: ssl.SSLContext, proxy_mode: str, http2: bool
) -> None:
    method = b"GET"
    url = (b"https", b"example.org", 443, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    with httpcore.SyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        ssl_context=ca_ssl_context,
        max_connections=max_connections,
        http2=http2,
        backend="sync",
    ) as http:
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        _ = read_body(stream)

        assert http_version == (b"HTTP/2" if http2 else b"HTTP/1.1")
        assert status_code == 200
        assert reason == b"OK"


@pytest.mark.parametrize(
    "http2,keepalive_expiry,expected_during_active,expected_during_idle",
    [
        (
            False,
            60.0,
            {"https://example.org": ["HTTP/1.1, ACTIVE", "HTTP/1.1, ACTIVE"]},
            {"https://example.org": ["HTTP/1.1, IDLE", "HTTP/1.1, IDLE"]},
        ),
        (
            True,
            60.0,
            {"https://example.org": ["HTTP/2, ACTIVE, 2 streams"]},
            {"https://example.org": ["HTTP/2, IDLE, 0 streams"]},
        ),
        (
            False,
            0.0,
            {"https://example.org": ["HTTP/1.1, ACTIVE", "HTTP/1.1, ACTIVE"]},
            {},
        ),
        (
            True,
            0.0,
            {"https://example.org": ["HTTP/2, ACTIVE, 2 streams"]},
            {},
        ),
    ],
)

def test_connection_pool_get_connection_info(
    http2: bool,
    keepalive_expiry: float,
    expected_during_active: dict,
    expected_during_idle: dict,
) -> None:
    with httpcore.SyncConnectionPool(
        backend="sync", http2=http2, keepalive_expiry=keepalive_expiry
    ) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]

        _, _, _, _, stream_1 = http.request(method, url, headers)
        _, _, _, _, stream_2 = http.request(method, url, headers)

        try:
            stats = http.get_connection_info()
            assert stats == expected_during_active
        finally:
            read_body(stream_1)
            read_body(stream_2)

        stats = http.get_connection_info()
        assert stats == expected_during_idle

    stats = http.get_connection_info()
    assert stats == {}


@pytest.mark.skipif(
    platform.system() not in ("Linux", "Darwin"),
    reason="Unix Domain Sockets only exist on Unix",
)

def test_http_request_unix_domain_socket(uds_server: Server) -> None:
    uds = uds_server.config.uds
    assert uds is not None
    with httpcore.SyncConnectionPool(backend="sync", uds=uds) as http:
        method = b"GET"
        url = (b"http", b"localhost", None, b"/")
        headers = [(b"host", b"localhost")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        body = read_body(stream)
        assert body == b"Hello, world!"



@pytest.mark.parametrize("max_keepalive", [1, 3, 5])
@pytest.mark.parametrize("connections_number", [4])
def test_max_keepalive_connections_handled_correctly(
    max_keepalive: int, connections_number: int
) -> None:
    with httpcore.SyncConnectionPool(
        backend="sync", max_keepalive_connections=max_keepalive, keepalive_expiry=60
    ) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]

        connections_streams = []
        for _ in range(connections_number):
            _, _, _, _, stream = http.request(method, url, headers)
            connections_streams.append(stream)

        try:
            for i in range(len(connections_streams)):
                read_body(connections_streams[i])
        finally:
            stats = http.get_connection_info()

            connections_in_pool = next(iter(stats.values()))
            assert len(connections_in_pool) == min(connections_number, max_keepalive)



def test_explicit_backend_name() -> None:
    with httpcore.SyncConnectionPool(backend=detect_backend()) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(
            method, url, headers
        )
        read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore
