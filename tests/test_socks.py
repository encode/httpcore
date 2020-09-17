import pytest

import httpcore
from httpcore import AsyncByteStream
from httpcore._types import Socks


async def read_response(stream: AsyncByteStream) -> bytes:
    response = []
    async for chunk in stream:
        response.append(chunk)

    return b"".join(response)


@pytest.mark.parametrize(
    ["protocol", "port"],
    [
        (b"https", 443),
        (b"http", 80),
    ],
)
@pytest.mark.parametrize("proxy", [Socks(b"SOCKS5", b"localhost", 1085)])
@pytest.mark.asyncio
async def test_connection_pool_with_socks_proxy(protocol, port, proxy):
    hostname = b"example.com"
    url = (protocol, hostname, port, b"/")
    headers = [(b"host", hostname)]
    method = b"GET"

    async with httpcore.AsyncConnectionPool(socks=proxy) as pool:

        http_version, status_code, reason, headers, stream = await pool.request(
            method, url, headers
        )

        assert status_code == 200
        assert reason == b"OK"
        _ = await read_response(stream)
