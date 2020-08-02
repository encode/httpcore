import ssl

import pytest

import httpcore
from httpcore._types import URL


async def read_body(stream: httpcore.AsyncByteStream) -> bytes:
    try:
        body = []
        async for chunk in stream:
            body.append(chunk)
        return b"".join(body)
    finally:
        await stream.aclose()


@pytest.mark.usefixtures("async_environment")
async def test_http_request() -> None:
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.usefixtures("async_environment")
async def test_https_request() -> None:
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.usefixtures("async_environment")
async def test_request_unsupported_protocol() -> None:
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"ftp", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        with pytest.raises(httpcore.UnsupportedProtocol):
            await http.request(method, url, headers)


@pytest.mark.usefixtures("async_environment")
async def test_http2_request() -> None:
    async with httpcore.AsyncConnectionPool(http2=True) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/2"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.usefixtures("async_environment")
async def test_closing_http_request() -> None:
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org"), (b"connection", b"close")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert url[:3] not in http._connections  # type: ignore


@pytest.mark.usefixtures("async_environment")
async def test_http_request_reuse_connection() -> None:
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore

        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.usefixtures("async_environment")
async def test_https_request_reuse_connection() -> None:
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore

        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.usefixtures("async_environment")
async def test_http_request_cannot_reuse_dropped_connection() -> None:
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

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
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "FORWARD_ONLY", "TUNNEL_ONLY"])
@pytest.mark.usefixtures("async_environment")
async def test_http_proxy(proxy_server: URL, proxy_mode: str) -> None:
    method = b"GET"
    url = (b"http", b"example.org", 80, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    max_keepalive = 2
    async with httpcore.AsyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        max_connections=max_connections,
        max_keepalive=max_keepalive,
    ) as http:
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"


# mitmproxy does not support forwarding HTTPS requests
@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "TUNNEL_ONLY"])
@pytest.mark.usefixtures("async_environment")
@pytest.mark.parametrize("http2", [False, True])
async def test_proxy_https_requests(
    proxy_server: URL, ca_ssl_context: ssl.SSLContext, proxy_mode: str, http2: bool,
) -> None:
    method = b"GET"
    url = (b"https", b"example.org", 443, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    max_keepalive = 2
    async with httpcore.AsyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        ssl_context=ca_ssl_context,
        max_connections=max_connections,
        max_keepalive=max_keepalive,
        http2=http2,
    ) as http:
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        _ = await read_body(stream)

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
@pytest.mark.usefixtures("async_environment")
async def test_connection_pool_get_connection_info(http2, expected) -> None:
    async with httpcore.AsyncConnectionPool(http2=http2) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        for _ in range(2):
            _ = await http.request(method, url, headers)
        stats = http.get_connection_info()
        assert stats == {"https://example.org": expected}
