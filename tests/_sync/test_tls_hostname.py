from __future__ import annotations

import ssl

from httpcore._backends.sync import SyncStream, TLSinTLSStream


class DummySocket:
    def settimeout(self, timeout: float | None) -> None:
        self.timeout = timeout

    def sendall(self, data: bytes) -> None:
        self.data = data

    def close(self) -> None:
        pass


def test_sync_stream_start_tls_strips_trailing_dot_from_server_hostname() -> None:
    recorded: dict[str, str | None] = {}

    class DummyContext:
        def wrap_socket(self, sock: DummySocket, server_hostname: str | None = None) -> DummySocket:
            recorded["server_hostname"] = server_hostname
            return sock

    stream = SyncStream(DummySocket())

    wrapped = stream.start_tls(
        DummyContext(),
        server_hostname="localhost.",
        timeout=1,
    )

    assert recorded["server_hostname"] == "localhost"
    assert isinstance(wrapped, SyncStream)


def test_tls_in_tls_stream_strips_trailing_dot_from_server_hostname() -> None:
    recorded: dict[str, str | None] = {}

    class DummySSLObject:
        def do_handshake(self) -> None:
            return None

    class DummyContext:
        def wrap_bio(
            self,
            incoming: ssl.MemoryBIO,
            outgoing: ssl.MemoryBIO,
            server_hostname: str | None = None,
        ) -> DummySSLObject:
            recorded["server_hostname"] = server_hostname
            return DummySSLObject()

    TLSinTLSStream(
        DummySocket(),
        DummyContext(),
        server_hostname="localhost.",
        timeout=1,
    )

    assert recorded["server_hostname"] == "localhost"
