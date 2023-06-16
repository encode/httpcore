import pytest

import httpcore


@pytest.mark.trio
async def test_connect_without_tls(httpbin):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(httpbin.host, httpbin.port)
    try:
        ssl_object = stream.get_extra_info("ssl_object")
        assert ssl_object is None
    finally:
        await stream.aclose()
