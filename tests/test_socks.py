import pytest

from httpcore._async.connection import AsyncSOCKSConnection


@pytest.mark.parametrize(
    "url",
    [
        (b"http", b"example.com", 80, b"/"),
        (b"https", b"example.com", 443, b"/"),
    ],
)
@pytest.mark.parametrize("http2", [True, False])
@pytest.mark.asyncio
async def test_smoke(socks5_proxy, url, http2):
    (protocol, hostname, port, path) = url
    origin = (protocol, hostname, port)
    headers = [(b"host", hostname)]
    method = b"GET"

    async with AsyncSOCKSConnection(
        origin, http2=http2, proxy_origin=socks5_proxy
    ) as connection:
        http_version, status_code, reason, headers, stream = await connection.request(
            method, url, headers
        )

        assert status_code == 200
        assert reason == b"OK"
