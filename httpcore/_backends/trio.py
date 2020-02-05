from ssl import SSLContext
from typing import Dict, Optional, Union

import trio

from .._exceptions import (
    ConnectTimeout,
    NetworkError,
    ReadTimeout,
    WriteTimeout,
    map_exceptions,
)
from .base import AsyncBackend, AsyncSocketStream


def none_as_inf(value: Optional[float]) -> float:
    return value if value is not None else float("inf")


class SocketStream(AsyncSocketStream):
    def __init__(self, stream: Union[trio.SocketStream, trio.SSLStream],) -> None:
        self.stream = stream
        self.read_lock = trio.Lock()
        self.write_lock = trio.Lock()

    async def read(self, n: int, timeout: Dict[str, Optional[float]]) -> bytes:
        read_timeout = none_as_inf(timeout.get("read"))

        with trio.move_on_after(read_timeout):
            async with self.read_lock:
                with map_exceptions(trio.BrokenResourceError, NetworkError):
                    return await self.stream.receive_some(max_bytes=n)

        raise ReadTimeout()

    async def write(self, data: bytes, timeout: Dict[str, Optional[float]]) -> None:
        if not data:
            return

        write_timeout = none_as_inf(timeout.get("write"))

        with trio.move_on_after(write_timeout):
            async with self.write_lock:
                with map_exceptions(trio.BrokenResourceError, NetworkError):
                    return await self.stream.send_all(data)

        raise WriteTimeout()

    def is_connection_dropped(self) -> bool:
        # Adapted from: https://github.com/encode/httpx/pull/143#issuecomment-515202982
        stream = self.stream

        # Peek through any SSLStream wrappers to get the underlying SocketStream.
        while hasattr(stream, "transport_stream"):
            stream = stream.transport_stream
        assert isinstance(stream, trio.SocketStream)

        # Counter-intuitively, what we really want to know here is whether the socket is
        # *readable*, i.e. whether it would return immediately with empty bytes if we
        # called `.recv()` on it, indicating that the other end has closed the socket.
        # See: https://github.com/encode/httpx/pull/143#issuecomment-515181778
        return stream.socket.is_readable()

    async def close(self) -> None:
        async with self.write_lock:
            await self.stream.aclose()


class TrioBackend(AsyncBackend):
    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: Dict[str, Optional[float]],
    ) -> AsyncSocketStream:
        connect_timeout = none_as_inf(timeout.get("connect"))

        with trio.move_on_after(connect_timeout):
            with map_exceptions(OSError, NetworkError):
                stream: trio.SocketStream = await trio.open_tcp_stream(hostname, port)

            if ssl_context is not None:
                stream = trio.SSLStream(stream, ssl_context, server_hostname=hostname)
                with map_exceptions(trio.BrokenResourceError, NetworkError):
                    await stream.do_handshake()

            return SocketStream(stream=stream)

        raise ConnectTimeout()
