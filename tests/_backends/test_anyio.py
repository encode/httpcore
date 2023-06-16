import pytest

import httpcore


@pytest.mark.anyio
async def test_connect_tcp(httpbin):
    backend = httpcore.AnyIOBackend()
    stream = await backend.connect_tcp(httpbin.host, httpbin.port)
    try:
        ssl_object = stream.get_extra_info("ssl_object")
        assert ssl_object is None
    finally:
        await stream.aclose()
