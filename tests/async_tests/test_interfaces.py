import httpcore
import pytest


@pytest.mark.asyncio
async def test_connection_pool():
    async with httpcore.AsyncConnectionPool() as http:
        with pytest.raises(NotImplementedError):
            await http.request(b'GET', (b'https', b'example.org', 443, b'/'))


@pytest.mark.asyncio
async def test_http_proxy():
    proxy_url = (b'https', b'localhost', 443, b'/')
    async with httpcore.AsyncHTTPProxy(proxy_url) as http:
        with pytest.raises(NotImplementedError):
            await http.request(b'GET', (b'https', b'example.org', 443, b'/'))
