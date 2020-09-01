import select
import socket
from ssl import SSLContext, SSLSocket
from typing import Dict, Optional, Type, Union

import curio
import curio.io

from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    TimeoutException,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._types import TimeoutDict
from .._utils import get_logger
from .base import AsyncBackend, AsyncLock, AsyncSemaphore, AsyncSocketStream

logger = get_logger("curio_backend")

one_day_in_seconds = 60 * 60 * 24


async def wrap_ssl_client(
    sock: curio.io.Socket,
    ssl_context: SSLContext,
    server_hostname: bytes,
) -> curio.io.Socket:
    kwargs = {
        "server_hostname": server_hostname,
        "do_handshake_on_connect": sock._socket.gettimeout() != 0.0,
    }

    socket = curio.io.Socket(ssl_context.wrap_socket(sock._socket, **kwargs))
    await socket.do_handshake()

    return socket


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
        exc_map: Dict[Type[Exception], Type[Exception]] = {
            curio.TaskTimeout: TimeoutException,
        }
        acquire_timeout: int = convert_timeout(timeout)

        with map_exceptions(exc_map):
            return await curio.timeout_after(acquire_timeout, self.semaphore.acquire())

    async def release(self) -> None:
        await self.semaphore.release()


class SocketStream(AsyncSocketStream):
    def __init__(self, socket: curio.io.Socket) -> None:
        self.read_lock = curio.Lock()
        self.write_lock = curio.Lock()
        self.socket = socket
        self.stream = socket.as_stream()

    def get_http_version(self) -> str:
        ident: Optional[str] = "http/1.1"

        if hasattr(self.socket, "_socket"):
            raw_socket: Union[SSLSocket, socket.socket] = self.socket._socket

            if isinstance(raw_socket, SSLSocket):
                ident = raw_socket.selected_alpn_protocol()

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
                wrap_ssl_client(self.socket, ssl_context, hostname),
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
        await self.stream.close()
        await self.socket.close()

    def is_connection_dropped(self) -> bool:
        rready, _, _ = select.select([self.socket.fileno()], [], [], 0)

        return bool(rready)


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
                connect_timeout,
                curio.open_connection(hostname, port, **kwargs),
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
