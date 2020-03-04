import pytest

import httpcore


async def read_body(stream):
    try:
        body = []
        async for chunk in stream:
            body.append(chunk)
        return b"".join(body)
    finally:
        await stream.aclose()


@pytest.mark.usefixtures("async_environment")
async def test_http_request():
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
        assert len(http._connections[url[:3]]) == 1


@pytest.mark.usefixtures("async_environment")
async def test_https_request():
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
        assert len(http._connections[url[:3]]) == 1


@pytest.mark.usefixtures("async_environment")
async def test_http2_request():
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
        assert len(http._connections[url[:3]]) == 1


@pytest.mark.usefixtures("async_environment")
async def test_closing_http_request():
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
        assert url[:3] not in http._connections


@pytest.mark.usefixtures("async_environment")
async def test_http_request_reuse_connection():
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
        assert len(http._connections[url[:3]]) == 1

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
        assert len(http._connections[url[:3]]) == 1


@pytest.mark.usefixtures("async_environment")
async def test_https_request_reuse_connection():
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
        assert len(http._connections[url[:3]]) == 1

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
        assert len(http._connections[url[:3]]) == 1


@pytest.mark.usefixtures("async_environment")
async def test_http_request_cannot_reuse_dropped_connection():
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
        assert len(http._connections[url[:3]]) == 1

        # Mock the connection as having been dropped.
        connection = list(http._connections[url[:3]])[0]
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
        assert len(http._connections[url[:3]]) == 1


@pytest.mark.usefixtures("async_environment")
async def test_http_get_connection_stats():
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert status_code == 200
        assert reason == b"OK"

        stats = http.get_connection_stats()
        key = url[:3] + (b"HTTP/1.1",)
        assert stats.get(key, None) is not None
        assert len(stats[key]) == 1
        assert sum(stats[key].values()) == 1

        method = b"GET"
        url = (b"https", b"example.org", 443, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(
            method, url, headers
        )
        body = await read_body(stream)

        assert status_code == 200
        assert reason == b"OK"

        stats = http.get_connection_stats()
        key = url[:3] + (b"HTTP/1.1",)
        assert stats.get(key, None) is not None
        assert len(stats[key]) == 1
        assert sum(stats[key].values()) == 1

        assert len(stats.keys()) == 2
        assert sum([sum(k.values()) for k in stats.values()]) == 2
