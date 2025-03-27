import asyncio
import socket
import ssl
from typing import Any, Dict, Iterable, Optional, Type

from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._utils import is_socket_readable
from .base import SOCKET_OPTION, AsyncNetworkBackend, AsyncNetworkStream


class AsyncIOStream(AsyncNetworkStream):
    def __init__(
        self, stream_reader: asyncio.StreamReader, stream_writer: asyncio.StreamWriter
    ):
        self._stream_reader = stream_reader
        self._stream_writer = stream_writer
        self._inner: Optional[AsyncIOStream] = None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> AsyncNetworkStream:
        loop = asyncio.get_event_loop()

        stream_reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(stream_reader)

        exc_map: Dict[Type[Exception], Type[Exception]] = {
            asyncio.TimeoutError: ConnectTimeout,
            OSError: ConnectError,
        }
        with map_exceptions(exc_map):
            transport_ssl = await asyncio.wait_for(
                loop.start_tls(
                    self._stream_writer.transport,
                    protocol,
                    ssl_context,
                    server_hostname=server_hostname,
                ),
                timeout,
            )
        if transport_ssl is None:
            # https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.start_tls
            raise ConnectError("Transport closed while starting TLS")  # pragma: nocover

        # Initialize the protocol, so it is made aware of being tied to
        # a TLS connection.
        # See: https://github.com/encode/httpx/issues/859
        protocol.connection_made(transport_ssl)

        stream_writer = asyncio.StreamWriter(
            transport=transport_ssl, protocol=protocol, reader=stream_reader, loop=loop
        )

        ssl_stream = AsyncIOStream(stream_reader, stream_writer)
        # When we return a new SocketStream with new StreamReader/StreamWriter instances
        # we need to keep references to the old StreamReader/StreamWriter so that they
        # are not garbage collected and closed while we're still using them.
        ssl_stream._inner = self
        return ssl_stream

    async def read(self, max_bytes: int, timeout: Optional[float] = None) -> bytes:
        exc_map: Dict[Type[Exception], Type[Exception]] = {
            asyncio.TimeoutError: ReadTimeout,
            OSError: ReadError,
        }
        with map_exceptions(exc_map):
            try:
                return await asyncio.wait_for(
                    self._stream_reader.read(max_bytes), timeout
                )
            except AttributeError as exc:  # pragma: nocover
                if "resume_reading" in str(exc):
                    # Python's asyncio has a bug that can occur when a
                    # connection has been closed, while it is paused.
                    # See: https://github.com/encode/httpx/issues/1213
                    #
                    # Returning an empty byte-string to indicate connection
                    # close will eventually raise an httpcore.RemoteProtocolError
                    # to the user when this goes through our HTTP parsing layer.
                    return b""
                raise

    async def write(self, data: bytes, timeout: Optional[float] = None) -> None:
        if not data:
            return

        exc_map: Dict[Type[Exception], Type[Exception]] = {
            asyncio.TimeoutError: WriteTimeout,
            OSError: WriteError,
        }
        with map_exceptions(exc_map):
            self._stream_writer.write(data)
            return await asyncio.wait_for(self._stream_writer.drain(), timeout)

    async def aclose(self) -> None:
        # SSL connections should issue the close and then abort, rather than
        # waiting for the remote end of the connection to signal the EOF.
        #
        # See:
        #
        # * https://bugs.python.org/issue39758
        # * https://github.com/python-trio/trio/blob/
        #             31e2ae866ad549f1927d45ce073d4f0ea9f12419/trio/_ssl.py#L779-L829
        #
        # And related issues caused if we simply omit the 'wait_closed' call,
        # without first using `.abort()`
        #
        # * https://github.com/encode/httpx/issues/825
        # * https://github.com/encode/httpx/issues/914
        is_ssl = self._sslobj is not None

        try:
            self._stream_writer.close()
            if is_ssl:
                # Give the connection a chance to write any data in the buffer,
                # and then forcibly tear down the SSL connection.
                await asyncio.sleep(0)
                self._stream_writer.transport.abort()
            await self._stream_writer.wait_closed()
        except OSError:  # pragma: nocover
            pass

    def get_extra_info(self, info: str) -> Any:
        if info == "is_readable":
            return is_socket_readable(self._raw_socket)
        if info == "ssl_object":
            return self._sslobj
        if info in ("client_addr", "server_addr"):
            sock = self._raw_socket
            if sock is None:  # pragma: nocover
                # TODO replace with an explicit error such as BrokenSocketError
                raise ConnectError()
            return sock.getsockname() if info == "client_addr" else sock.getpeername()
        if info == "socket":
            return self._raw_socket
        return None

    @property
    def _raw_socket(self) -> Optional[socket.socket]:
        transport = self._stream_writer.transport
        sock: Optional[socket.socket] = transport.get_extra_info("socket")
        return sock

    @property
    def _sslobj(self) -> Optional[ssl.SSLObject]:
        transport = self._stream_writer.transport
        sslobj: Optional[ssl.SSLObject] = transport.get_extra_info("ssl_object")
        return sslobj


class AsyncIOBackend(AsyncNetworkBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:
        local_addr = None if local_address is None else (local_address, 0)

        exc_map: Dict[Type[Exception], Type[Exception]] = {
            asyncio.TimeoutError: ConnectTimeout,
            OSError: ConnectError,
        }
        with map_exceptions(exc_map):
            stream_reader, stream_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, local_addr=local_addr),
                timeout,
            )
            self._set_socket_options(stream_writer, socket_options)
            return AsyncIOStream(
                stream_reader=stream_reader, stream_writer=stream_writer
            )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: Optional[Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:
        exc_map: Dict[Type[Exception], Type[Exception]] = {
            asyncio.TimeoutError: ConnectTimeout,
            OSError: ConnectError,
        }
        with map_exceptions(exc_map):
            stream_reader, stream_writer = await asyncio.wait_for(
                asyncio.open_unix_connection(path), timeout
            )
            self._set_socket_options(stream_writer, socket_options)
            return AsyncIOStream(
                stream_reader=stream_reader, stream_writer=stream_writer
            )

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)  # pragma: nocover

    def _set_socket_options(
        self,
        stream: asyncio.StreamWriter,
        socket_options: Optional[Iterable[SOCKET_OPTION]] = None,
    ) -> None:
        if not socket_options:
            return

        sock = stream.get_extra_info("socket")
        if sock is None:  # pragma: nocover
            # TODO replace with an explicit error such as BrokenSocketError
            raise ConnectError()

        for option in socket_options:
            sock.setsockopt(*option)
