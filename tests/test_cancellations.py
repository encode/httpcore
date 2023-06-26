import typing

import anyio
import pytest

import httpcore


class SlowWriteStream(httpcore.AsyncNetworkStream):
    async def write(
        self, buffer: bytes, timeout: typing.Optional[float] = None
    ) -> None:
        await anyio.sleep(2)

    async def aclose(self) -> None:
        pass


@pytest.mark.anyio
async def test_h11_response_closed():
    """
    An async timeout on an HTTP/1.1 connection should leave the connection
    in a neatly closed state.
    """
    origin = httpcore.Origin(b"http", b"example.com", 80)
    stream = SlowWriteStream()
    async with httpcore.AsyncHTTP11Connection(origin, stream) as conn:
        with anyio.move_on_after(0.001):
            await conn.request("GET", "http://example.com")
        assert conn.is_closed()
