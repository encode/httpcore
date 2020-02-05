import pytest

import httpcore


@pytest.mark.asyncio
async def test_connection_pool():
    async with httpcore.AsyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        await http.request(method, url, headers)
