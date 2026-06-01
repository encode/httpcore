from __future__ import annotations

import socket
import typing

from httpcore._backends.sync import SyncStream
from httpcore._ssl import _normalize_server_hostname


class CapturingSSLContext:
    def __init__(self) -> None:
        self.server_hostname: str | None = None

    def wrap_socket(
        self, sock: socket.socket, server_hostname: str | None = None
    ) -> socket.socket:
        self.server_hostname = server_hostname
        return sock


def test_normalize_server_hostname() -> None:
    assert _normalize_server_hostname(None) is None
    assert _normalize_server_hostname("example.com") == "example.com"
    assert _normalize_server_hostname("example.com.") == "example.com"


def test_sync_start_tls_normalizes_trailing_dot_hostname() -> None:
    local, remote = socket.socketpair()
    ssl_context = CapturingSSLContext()

    try:
        stream = SyncStream(local)
        tls_stream = stream.start_tls(
            typing.cast(typing.Any, ssl_context), server_hostname="example.com."
        )

        assert ssl_context.server_hostname == "example.com"
        tls_stream.close()
    finally:
        local.close()
        remote.close()
