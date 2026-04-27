from __future__ import annotations

import ssl

import anyio
import pytest
import trio

from httpcore._backends.anyio import AnyIOStream
from httpcore._backends.trio import TrioStream


class DummyAsyncStream:
    async def aclose(self) -> None:
        pass


@pytest.mark.anyio
async def test_anyio_stream_start_tls_strips_trailing_dot_from_server_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, str | None] = {}

    class DummyTLSStream:
        async def aclose(self) -> None:
            pass

        def extra(self, attribute: object, default: object = None) -> object:
            return default

    async def wrap(
        stream: DummyAsyncStream,
        *,
        ssl_context: ssl.SSLContext,
        hostname: str | None,
        standard_compatible: bool,
        server_side: bool,
    ) -> DummyTLSStream:
        recorded["server_hostname"] = hostname
        return DummyTLSStream()

    monkeypatch.setattr(anyio.streams.tls.TLSStream, "wrap", wrap)

    stream = AnyIOStream(DummyAsyncStream())
    wrapped = await stream.start_tls(
        ssl.create_default_context(),
        server_hostname="localhost.",
        timeout=1,
    )

    assert recorded["server_hostname"] == "localhost"
    assert isinstance(wrapped, AnyIOStream)


@pytest.mark.trio
async def test_trio_stream_start_tls_strips_trailing_dot_from_server_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, str | None] = {}

    class DummySSLStream:
        def __init__(
            self,
            stream: DummyAsyncStream,
            *,
            ssl_context: ssl.SSLContext,
            server_hostname: str | None,
            https_compatible: bool,
            server_side: bool,
        ) -> None:
            self.transport_stream = stream
            recorded["server_hostname"] = server_hostname

        async def do_handshake(self) -> None:
            return None

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(trio, "SSLStream", DummySSLStream)

    stream = TrioStream(DummyAsyncStream())
    wrapped = await stream.start_tls(
        ssl.create_default_context(),
        server_hostname="localhost.",
        timeout=1,
    )

    assert recorded["server_hostname"] == "localhost"
    assert isinstance(wrapped, TrioStream)
