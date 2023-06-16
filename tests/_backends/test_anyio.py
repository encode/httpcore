import pytest

import httpcore


@pytest.mark.anyio
async def test_connect_without_tls(httpbin):
    backend = httpcore.AnyIOBackend()
    stream = await backend.connect_tcp(httpbin.host, httpbin.port)
    try:
        ssl_object = stream.get_extra_info("ssl_object")
        assert ssl_object is None
    finally:
        await stream.aclose()


@pytest.mark.anyio
async def test_write_without_tls(httpbin):
    backend = httpcore.AnyIOBackend()
    stream = await backend.connect_tcp(httpbin.host, httpbin.port)
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    try:
        for chunk in http_request:
            await stream.write(chunk)
        assert True
    finally:
        await stream.aclose()
