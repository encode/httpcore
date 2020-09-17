import platform
import ssl

import pytest

import httpcore
from httpcore._types import URL
from tests.conftest import Server
from tests.utils import lookup_async_backend


@pytest.fixture(params=["auto", "anyio"])
def backend(request):
    return request.param


async def read_body(stream: httpcore.AsyncByteStream) -> bytes:
    try:
        body = []
        async for chunk in stream:
            body.append(chunk)
        return b"".join(body)
    finally:
        await stream.aclose()


@pytest.mark.anyio
async def test_http_request(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.anyio
async def test_https_request(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.anyio
async def test_request_unsupported_protocol(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        method = b"GET"
        url = (b"ftp", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        with pytest.raises(httpcore.UnsupportedProtocol):
            await http.request(method, url, headers)


@pytest.mark.anyio
async def test_http2_request(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend, http2=True) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/2"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.anyio
async def test_closing_http_request(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org"), (b"connection", b"close")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert url[:3] not in http._connections  # type: ignore


@pytest.mark.anyio
async def test_http_request_reuse_connection(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

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
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.anyio
async def test_https_request_reuse_connection(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

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
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.anyio
async def test_http_request_cannot_reuse_dropped_connection(backend: str) -> None:
    async with httpcore.AsyncConnectionPool(backend=backend) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

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
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "FORWARD_ONLY", "TUNNEL_ONLY"])
@pytest.mark.anyio
async def test_http_proxy(proxy_server: URL, proxy_mode: str, backend: str) -> None:
    method = b"GET"
    url = (b"http", b"example.org", 80, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    async with httpcore.AsyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        max_connections=max_connections,
        backend=backend,
    ) as http:
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"


@pytest.mark.anyio
async def test_http_request_local_address(backend: str) -> None:
    if backend == "auto" and lookup_async_backend() == "trio":
        pytest.skip("The trio backend does not support local_address")

    async with httpcore.AsyncConnectionPool(
        backend=backend, local_address="0.0.0.0"
    ) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


# mitmproxy does not support forwarding HTTPS requests
@pytest.mark.parametrize("proxy_mode", ["DEFAULT", "TUNNEL_ONLY"])
@pytest.mark.parametrize("http2", [False, True])
@pytest.mark.anyio
async def test_proxy_https_requests(
    proxy_server: URL, ca_ssl_context: ssl.SSLContext, proxy_mode: str, http2: bool
) -> None:
    method = b"GET"
    url = (b"https", b"example.org", 443, b"/")
    headers = [(b"host", b"example.org")]
    max_connections = 1
    async with httpcore.AsyncHTTPProxy(
        proxy_server,
        proxy_mode=proxy_mode,
        ssl_context=ca_ssl_context,
        max_connections=max_connections,
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
@pytest.mark.anyio
async def test_connection_pool_get_connection_info(
    http2: bool,
    keepalive_expiry: float,
    expected_during_active: dict,
    expected_during_idle: dict,
    backend: str,
) -> None:
    async with httpcore.AsyncConnectionPool(
        http2=http2, keepalive_expiry=keepalive_expiry, backend=backend
    ) as http:
        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]

        _, _, _, _, stream_1 = await http.request(method, url, headers)
        _, _, _, _, stream_2 = await http.request(method, url, headers)

        try:
            stats = await http.get_connection_info()
            assert stats == expected_during_active
        finally:
            await read_body(stream_1)
            await read_body(stream_2)

        stats = await http.get_connection_info()
        assert stats == expected_during_idle

    stats = await http.get_connection_info()
    assert stats == {}


@pytest.mark.skipif(
    platform.system() not in ("Linux", "Darwin"),
    reason="Unix Domain Sockets only exist on Unix",
)
@pytest.mark.anyio
async def test_http_request_unix_domain_socket(
    uds_server: Server, backend: str
) -> None:
    uds = uds_server.config.uds
    assert uds is not None
    async with httpcore.AsyncConnectionPool(uds=uds, backend=backend) as http:
        method = b"GET"
        url = (b"http", b"localhost", None, b"/")
        headers = [(b"host", b"localhost")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        body = await read_body(stream)
        assert body == b"Hello, world!"


@pytest.mark.parametrize("max_keepalive", [1, 3, 5])
@pytest.mark.parametrize("connections_number", [4])
@pytest.mark.anyio
async def test_max_keepalive_connections_handled_correctly(
    max_keepalive: int, connections_number: int, backend: str
) -> None:
    async with httpcore.AsyncConnectionPool(
        max_keepalive_connections=max_keepalive, keepalive_expiry=60, backend=backend
    ) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]

        connections_streams = []
        for _ in range(connections_number):
            _, _, _, _, stream = await http.request(method, url, headers)
            connections_streams.append(stream)

        try:
            for i in range(len(connections_streams)):
                await read_body(connections_streams[i])
        finally:
            stats = await http.get_connection_info()

            connections_in_pool = next(iter(stats.values()))
            assert len(connections_in_pool) == min(connections_number, max_keepalive)


@pytest.mark.anyio
async def test_explicit_backend_name() -> None:
    async with httpcore.AsyncConnectionPool(backend=lookup_async_backend()) as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        await read_body(stream)

        assert http_version == b"HTTP/1.1"
        assert status_code == 200
        assert reason == b"OK"
        assert len(http._connections[url[:3]]) == 1  # type: ignore


@pytest.mark.anyio
@pytest.mark.parametrize(
    "url",
    [
        (b"http", b"example.com", 80, b"/"),
        (b"https", b"example.com", 443, b"/"),
    ],
)
@pytest.mark.parametrize("http2", [True, False])
async def test_socks5_proxy_connection_without_auth(socks5_proxy, url, http2):
    (protocol, hostname, port, path) = url
    origin = (protocol, hostname, port)
    headers = [(b"host", hostname)]
    method = b"GET"

    async with httpcore._async.connection.AsyncSOCKSConnection(
        origin, http2=http2, proxy_origin=socks5_proxy
    ) as connection:
        http_version, status_code, reason, headers, stream = await connection.request(
            method, url, headers
        )

        assert status_code == 200
        assert reason == b"OK"
