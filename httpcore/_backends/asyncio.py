import asyncio
from ssl import SSLContext
from typing import Optional

from .._exceptions import (
    CloseError,
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._types import TimeoutDict
from .base import AsyncBackend, AsyncLock, AsyncSemaphore, AsyncSocketStream

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


async def backport_start_tls(
    transport: asyncio.BaseTransport,
    protocol: asyncio.BaseProtocol,
    ssl_context: SSLContext,
    *,
    server_side: bool = False,
    server_hostname: str = None,
    ssl_handshake_timeout: float = None,
) -> asyncio.Transport:  # pragma: nocover (Since it's not used on all Python versions.)
    """
    Python 3.6 asyncio doesn't have a start_tls() method on the loop
    so we use this function in place of the loop's start_tls() method.
    Adapted from this comment:
    https://github.com/urllib3/urllib3/issues/1323#issuecomment-362494839
    """
    import asyncio.sslproto

    loop = asyncio.get_event_loop()
    waiter = loop.create_future()
    ssl_protocol = asyncio.sslproto.SSLProtocol(
        loop,
        protocol,
        ssl_context,
        waiter,
        server_side=False,
        server_hostname=server_hostname,
        call_connection_made=False,
    )

    transport.set_protocol(ssl_protocol)
    loop.call_soon(ssl_protocol.connection_made, transport)
    loop.call_soon(transport.resume_reading)  # type: ignore

    await waiter
    return ssl_protocol._app_transport


class SocketStream(AsyncSocketStream):
    def __init__(
        self, stream_reader: asyncio.StreamReader, stream_writer: asyncio.StreamWriter
    ):
        self.stream_reader = stream_reader
        self.stream_writer = stream_writer
        self.read_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()

    def get_http_version(self) -> str:
        ssl_object = self.stream_writer.get_extra_info("ssl_object")

        if ssl_object is None:
            return "HTTP/1.1"

        ident = ssl_object.selected_alpn_protocol()
        return "HTTP/2" if ident == "h2" else "HTTP/1.1"

    async def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict
    ) -> "SocketStream":
        loop = asyncio.get_event_loop()

        stream_reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(stream_reader)
        transport = self.stream_writer.transport

        loop_start_tls = getattr(loop, "start_tls", backport_start_tls)

        transport = await asyncio.wait_for(
            loop_start_tls(
                transport,
                protocol,
                ssl_context,
                server_hostname=hostname.decode("ascii"),
            ),
            timeout=timeout.get("connect"),
        )

        stream_reader.set_transport(transport)
        stream_writer = asyncio.StreamWriter(
            transport=transport, protocol=protocol, reader=stream_reader, loop=loop
        )

        ssl_stream = SocketStream(stream_reader, stream_writer)
        # When we return a new SocketStream with new StreamReader/StreamWriter instances
        # we need to keep references to the old StreamReader/StreamWriter so that they
        # are not garbage collected and closed while we're still using them.
        ssl_stream._inner = self  # type: ignore
        return ssl_stream

    async def read(self, n: int, timeout: TimeoutDict) -> bytes:
        exc_map = {asyncio.TimeoutError: ReadTimeout, OSError: ReadError}
        async with self.read_lock:
            with map_exceptions(exc_map):
                return await asyncio.wait_for(
                    self.stream_reader.read(n), timeout.get("read")
                )

    async def write(self, data: bytes, timeout: TimeoutDict) -> None:
        if not data:
            return

        exc_map = {asyncio.TimeoutError: WriteTimeout, OSError: WriteError}
        async with self.write_lock:
            with map_exceptions(exc_map):
                self.stream_writer.write(data)
                return await asyncio.wait_for(
                    self.stream_writer.drain(), timeout.get("write")
                )

    async def aclose(self) -> None:
        # NOTE: StreamWriter instances expose a '.wait_closed()' coroutine function,
        # but using it has caused compatibility issues with certain sites in
        # the past (see https://github.com/encode/httpx/issues/634), which is
        # why we don't call it here.
        # This is fine, though, because '.aclose()' schedules the actual closing of the
        # stream, meaning that at best it will happen during the next event loop
        # iteration, and at worst asyncio will take care of it on program exit.
        async with self.write_lock:
            with map_exceptions({OSError: CloseError}):
                self.stream_writer.close()

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


class Lock(AsyncLock):
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def release(self) -> None:
        self._lock.release()

    async def acquire(self) -> None:
        await self._lock.acquire()


class Semaphore(AsyncSemaphore):
    def __init__(self, max_value: int, exc_class: type) -> None:
        self.max_value = max_value
        self.exc_class = exc_class

    @property
    def semaphore(self) -> asyncio.BoundedSemaphore:
        if not hasattr(self, "_semaphore"):
            self._semaphore = asyncio.BoundedSemaphore(value=self.max_value)
        return self._semaphore

    async def acquire(self, timeout: float = None) -> None:
        try:
            await asyncio.wait_for(self.semaphore.acquire(), timeout)
        except asyncio.TimeoutError:
            raise self.exc_class()

    async def release(self) -> None:
        self.semaphore.release()


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
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> SocketStream:
        host = hostname.decode("ascii")
        connect_timeout = timeout.get("connect")
        local_addr = None if local_address is None else (local_address, 0)

        exc_map = {asyncio.TimeoutError: ConnectTimeout, OSError: ConnectError}
        with map_exceptions(exc_map):
            stream_reader, stream_writer = await asyncio.wait_for(
                asyncio.open_connection(
                    host, port, ssl=ssl_context, local_addr=local_addr
                ),
                connect_timeout,
            )
            return SocketStream(
                stream_reader=stream_reader, stream_writer=stream_writer
            )

    async def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> AsyncSocketStream:
        host = hostname.decode("ascii")
        connect_timeout = timeout.get("connect")
        kwargs: dict = {"server_hostname": host} if ssl_context is not None else {}
        exc_map = {asyncio.TimeoutError: ConnectTimeout, OSError: ConnectError}
        with map_exceptions(exc_map):
            stream_reader, stream_writer = await asyncio.wait_for(
                asyncio.open_unix_connection(path, ssl=ssl_context, **kwargs),
                connect_timeout,
            )
            return SocketStream(
                stream_reader=stream_reader, stream_writer=stream_writer
            )

    def create_lock(self) -> AsyncLock:
        return Lock()

    def create_semaphore(self, max_value: int, exc_class: type) -> AsyncSemaphore:
        return Semaphore(max_value, exc_class=exc_class)

    async def time(self) -> float:
        loop = asyncio.get_event_loop()
        return loop.time()
