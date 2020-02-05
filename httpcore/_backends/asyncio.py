import asyncio
from ssl import SSLContext
from typing import Dict, Optional

from .._exceptions import (
    ConnectTimeout,
    NetworkError,
    ReadTimeout,
    WriteTimeout,
    map_exceptions,
)
from .base import AsyncBackend, AsyncSocketStream

SSL_MONKEY_PATCH_APPLIED = False


def ssl_monkey_patch() -> None:
    """
    Monkey-patch for https://bugs.python.org/issue36709

    This prevents console errors when outstanding HTTPS connections
    still exist at the point of exiting.

    Clients which have been opened using a `with` block, or which have
    had `close()` closed, will not exhibit this issue in the first place.
    """
    MonkeyPatch = asyncio.selector_events._SelectorSocketTransport  # type: ignore

    _write = MonkeyPatch.write

    def _fixed_write(self, data: bytes) -> None:  # type: ignore
        if self._loop and not self._loop.is_closed():
            _write(self, data)

    MonkeyPatch.write = _fixed_write


class SocketStream(AsyncSocketStream):
    def __init__(
        self, stream_reader: asyncio.StreamReader, stream_writer: asyncio.StreamWriter,
    ):
        self.stream_reader = stream_reader
        self.stream_writer = stream_writer
        self.read_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()

    async def read(self, n: int, timeout: Dict[str, Optional[float]]) -> bytes:
        try:
            async with self.read_lock:
                with map_exceptions(OSError, NetworkError):
                    return await asyncio.wait_for(
                        self.stream_reader.read(n), timeout.get("read")
                    )
        except asyncio.TimeoutError:
            raise ReadTimeout() from None

    async def write(self, data: bytes, timeout: Dict[str, Optional[float]]) -> None:
        if not data:
            return

        try:
            async with self.write_lock:
                with map_exceptions(OSError, NetworkError):
                    self.stream_writer.write(data)
                    return await asyncio.wait_for(
                        self.stream_writer.drain(), timeout.get("write")
                    )
        except asyncio.TimeoutError:
            raise WriteTimeout() from None

    def is_connection_dropped(self) -> bool:
        # Counter-intuitively, what we really want to know here is whether the socket is
        # *readable*, i.e. whether it would return immediately with empty bytes if we
        # called `.recv()` on it, indicating that the other end has closed the socket.
        # See: https://github.com/encode/httpx/pull/143#issuecomment-515181778
        #
        # As it turns out, asyncio checks for readability in the background
        # (see: https://github.com/encode/httpx/pull/276#discussion_r322000402),
        # so checking for EOF or readability here would yield the same result.
        #
        # At the cost of rigour, we check for EOF instead of readability because asyncio
        # does not expose any public API to check for readability.
        # (For a solution that uses private asyncio APIs, see:
        # https://github.com/encode/httpx/pull/143#issuecomment-515202982)

        return self.stream_reader.at_eof()

    async def close(self) -> None:
        # NOTE: StreamWriter instances expose a '.wait_closed()' coroutine function,
        # but using it has caused compatibility issues with certain sites in
        # the past (see https://github.com/encode/httpx/issues/634), which is
        # why we don't call it here.
        # This is fine, though, because '.close()' schedules the actual closing of the
        # stream, meaning that at best it will happen during the next event loop
        # iteration, and at worst asyncio will take care of it on program exit.
        async with self.write_lock:
            with map_exceptions(OSError, NetworkError):
                self.stream_writer.close()


class AsyncioBackend(AsyncBackend):
    def __init__(self) -> None:
        global SSL_MONKEY_PATCH_APPLIED

        if not SSL_MONKEY_PATCH_APPLIED:
            ssl_monkey_patch()
        SSL_MONKEY_PATCH_APPLIED = True

    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: Dict[str, Optional[float]],
    ) -> SocketStream:
        try:
            with map_exceptions(OSError, NetworkError):
                stream_reader, stream_writer = await asyncio.wait_for(  # type: ignore
                    asyncio.open_connection(
                        hostname.decode("ascii"), port, ssl=ssl_context
                    ),
                    timeout.get("connect"),
                )
        except asyncio.TimeoutError:
            raise ConnectTimeout()

        return SocketStream(stream_reader=stream_reader, stream_writer=stream_writer)
