from ssl import SSLContext
from typing import Optional

import curio
import curio.io
from curio.network import _wrap_ssl_client

from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._types import TimeoutDict
from .._utils import get_logger
from .base import AsyncBackend, AsyncLock, AsyncSemaphore, AsyncSocketStream

logger = get_logger("curio_backend")

one_day_in_seconds = 60 * 60 * 24


def convert_timeout(value: Optional[float]) -> int:
    return int(value) if value is not None else one_day_in_seconds


class Lock(AsyncLock):
    def __init__(self) -> None:
        self._lock = curio.Lock()

    async def acquire(self) -> None:
        await self._lock.acquire()

    async def release(self) -> None:
        await self._lock.release()


class Semaphore(AsyncSemaphore):
    def __init__(self, max_value: int, exc_class: type) -> None:
        self.max_value = max_value
        self.exc_class = exc_class

    @property
    def semaphore(self) -> curio.Semaphore:
        if not hasattr(self, "_semaphore"):
            self._semaphore = curio.Semaphore(value=self.max_value)
        return self._semaphore

    async def acquire(self, timeout: float = None) -> None:
        await self.semaphore.acquire()

    async def release(self) -> None:
        await self.semaphore.release()


class SocketStream(AsyncSocketStream):
    def __init__(self, socket: curio.io.Socket) -> None:
        self.read_lock = curio.Lock()
        self.write_lock = curio.Lock()
        self.socket = socket
        self.stream = socket.as_stream()

    def get_http_version(self) -> str:
        if hasattr(self.socket, "_socket") and hasattr(self.socket._socket, "_sslobj"):
            ident = self.socket._socket._sslobj.selected_alpn_protocol()
        else:
            ident = "http/1.1"
        return "HTTP/2" if ident == "h2" else "HTTP/1.1"

    async def start_tls(
        self, hostname: bytes, ssl_context: SSLContext, timeout: TimeoutDict
    ) -> "AsyncSocketStream":
        connect_timeout = convert_timeout(timeout.get("connect"))
        exc_map = {
            curio.TaskTimeout: ConnectTimeout,
            curio.CurioError: ConnectError,
            OSError: ConnectError,
        }

        with map_exceptions(exc_map):
            wrapped_sock = await curio.timeout_after(
                connect_timeout,
                _wrap_ssl_client(
                    self.socket,
                    ssl=ssl_context,
                    server_hostname=hostname,
                    alpn_protocols=["h2", "http/1.1"],
                ),
            )

            return SocketStream(wrapped_sock)

    async def read(self, n: int, timeout: TimeoutDict) -> bytes:
        read_timeout = convert_timeout(timeout.get("read"))
        exc_map = {
            curio.TaskTimeout: ReadTimeout,
            curio.CurioError: ReadError,
            OSError: ReadError,
        }

        with map_exceptions(exc_map):
            async with self.read_lock:
                return await curio.timeout_after(read_timeout, self.stream.read(n))

    async def write(self, data: bytes, timeout: TimeoutDict) -> None:
        write_timeout = convert_timeout(timeout.get("write"))
        exc_map = {
            curio.TaskTimeout: WriteTimeout,
            curio.CurioError: WriteError,
            OSError: WriteError,
        }

        with map_exceptions(exc_map):
            async with self.write_lock:
                await curio.timeout_after(write_timeout, self.stream.write(data))

    async def aclose(self) -> None:
        # we dont need to close the self.socket, since it's closed by stream closing
        await self.stream.close()

    def is_connection_dropped(self) -> bool:
        return self.socket._closed


class CurioBackend(AsyncBackend):
    async def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
        *,
        local_address: Optional[str],
    ) -> AsyncSocketStream:
        connect_timeout = convert_timeout(timeout.get("connect"))
        exc_map = {
            curio.TaskTimeout: ConnectTimeout,
            curio.CurioError: ConnectError,
            OSError: ConnectError,
        }
        host = hostname.decode("ascii")
        kwargs = (
            {} if not ssl_context else {"ssl": ssl_context, "server_hostname": host}
        )

        with map_exceptions(exc_map):
            sock: curio.io.Socket = await curio.timeout_after(
                connect_timeout, curio.open_connection(hostname, port, **kwargs)
            )

            return SocketStream(sock)

    async def open_uds_stream(
        self,
        path: str,
        hostname: bytes,
        ssl_context: Optional[SSLContext],
        timeout: TimeoutDict,
    ) -> AsyncSocketStream:
        connect_timeout = convert_timeout(timeout.get("connect"))
        exc_map = {
            curio.TaskTimeout: ConnectTimeout,
            curio.CurioError: ConnectError,
            OSError: ConnectError,
        }
        host = hostname.decode("ascii")
        kwargs = (
            {} if not ssl_context else {"ssl": ssl_context, "server_hostname": host}
        )

        with map_exceptions(exc_map):
            sock: curio.io.Socket = await curio.timeout_after(
                connect_timeout, curio.open_unix_connection(path, **kwargs)
            )

            return SocketStream(sock)

    def create_lock(self) -> AsyncLock:
        return Lock()

    def create_semaphore(self, max_value: int, exc_class: type) -> AsyncSemaphore:
        return Semaphore(max_value, exc_class)

    async def time(self) -> float:
        return float(await curio.clock())
