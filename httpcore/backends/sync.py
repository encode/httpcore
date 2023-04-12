import socket
import ssl
import sys
import typing

from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ExceptionMapping,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._utils import is_socket_readable
from .base import NetworkBackend, NetworkStream

SOCKET_OPTIONS = typing.Union[
    typing.Tuple[int, int, int],
    typing.Tuple[int, int, typing.Union[bytes, bytearray]],
    typing.Tuple[int, int, None, int],
]


def create_connection(
    address: typing.Tuple[str, int],
    timeout: typing.Optional[float],
    source_address: typing.Optional[typing.Tuple[str, int]],
    socket_options: typing.Iterable[SOCKET_OPTIONS],
) -> typing.Any:  # pragma: no cover
    host, port = address
    err = None
    for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            for option in socket_options:
                sock.setsockopt(*option)
            sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            err = None
            return sock
        except socket.error as _:
            err = _
            if sock is not None:
                sock.close()

    if err is not None:
        try:
            raise err
        finally:
            err = None
    else:
        raise socket.error("getaddrinfo returns an empty list")


class SyncStream(NetworkStream):
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def read(self, max_bytes: int, timeout: typing.Optional[float] = None) -> bytes:
        exc_map: ExceptionMapping = {socket.timeout: ReadTimeout, OSError: ReadError}
        with map_exceptions(exc_map):
            self._sock.settimeout(timeout)
            return self._sock.recv(max_bytes)

    def write(self, buffer: bytes, timeout: typing.Optional[float] = None) -> None:
        if not buffer:
            return

        exc_map: ExceptionMapping = {socket.timeout: WriteTimeout, OSError: WriteError}
        with map_exceptions(exc_map):
            while buffer:
                self._sock.settimeout(timeout)
                n = self._sock.send(buffer)
                buffer = buffer[n:]

    def close(self) -> None:
        self._sock.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: typing.Optional[str] = None,
        timeout: typing.Optional[float] = None,
    ) -> NetworkStream:
        exc_map: ExceptionMapping = {
            socket.timeout: ConnectTimeout,
            OSError: ConnectError,
        }
        with map_exceptions(exc_map):
            try:
                self._sock.settimeout(timeout)
                sock = ssl_context.wrap_socket(
                    self._sock, server_hostname=server_hostname
                )
            except Exception as exc:  # pragma: nocover
                self.close()
                raise exc
        return SyncStream(sock)

    def get_extra_info(self, info: str) -> typing.Any:
        if info == "ssl_object" and isinstance(self._sock, ssl.SSLSocket):
            return self._sock._sslobj  # type: ignore
        if info == "client_addr":
            return self._sock.getsockname()
        if info == "server_addr":
            return self._sock.getpeername()
        if info == "socket":
            return self._sock
        if info == "is_readable":
            return is_socket_readable(self._sock)
        return None


class SyncBackend(NetworkBackend):
    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTIONS]] = None,
    ) -> NetworkStream:
        if socket_options is None:
            socket_options = []
        address = (host, port)
        source_address = None if local_address is None else (local_address, 0)
        exc_map: ExceptionMapping = {
            socket.timeout: ConnectTimeout,
            OSError: ConnectError,
        }

        with map_exceptions(exc_map):
            sock = create_connection(
                address,
                timeout,
                socket_options=socket_options,
                source_address=source_address,
            )
        return SyncStream(sock)

    def connect_unix_socket(
        self,
        path: str,
        timeout: typing.Optional[float] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTIONS]] = None,
    ) -> NetworkStream:  # pragma: nocover
        if sys.platform == "win32":
            raise RuntimeError(
                "Attempted to connect to a UNIX socket on a Windows system."
            )
        if socket_options is None:
            socket_options = []

        exc_map: ExceptionMapping = {
            socket.timeout: ConnectTimeout,
            OSError: ConnectError,
        }
        with map_exceptions(exc_map):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            for option in socket_options:
                sock.setsockopt(*option)
            sock.settimeout(timeout)
            sock.connect(path)
        return SyncStream(sock)
