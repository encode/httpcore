import pytest

import httpcore


async def read_body(stream):
    try:
        body = []
        async for chunk in stream:
            body.append(chunk)
        return b''.join(body)
    finally:
        await stream.close()


@pytest.mark.asyncio
async def test_connection_pool():
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = await http.request(method, url, headers)
        body = await read_body(stream)

        assert http_version == b'HTTP/1.1'
        assert status_code == 200
        assert reason == b'OK'
