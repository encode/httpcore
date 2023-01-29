import ssl
import time
import typing
from typing import Optional, Type

import anyio

from httpcore import ReadTimeout

from .._exceptions import ReadError
from .base import AsyncNetworkBackend, AsyncNetworkStream, NetworkBackend, NetworkStream


class MockSSLObject:
    def __init__(self, http2: bool):
        self._http2 = http2

    def selected_alpn_protocol(self) -> str:
        return "h2" if self._http2 else "http/1.1"


class MockStream(NetworkStream):
    def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
        self._buffer = buffer
        self._http2 = http2
        self._closed = False

    def read(self, max_bytes: int, timeout: Optional[float] = None) -> bytes:
        if self._closed:
            raise ReadError("Connection closed")
        if not self._buffer:
            return b""
        return self._buffer.pop(0)

    def write(self, buffer: bytes, timeout: Optional[float] = None) -> None:
        pass

    def close(self) -> None:
        self._closed = True

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> NetworkStream:
        return self

    def get_extra_info(self, info: str) -> typing.Any:
        return MockSSLObject(http2=self._http2) if info == "ssl_object" else None


class HangingStream(MockStream):
    def read(self, max_bytes: int, timeout: Optional[float] = None) -> bytes:
        time.sleep(timeout or 0.1)
        raise ReadTimeout


class MockBackend(NetworkBackend):
    def __init__(
        self,
        buffer: typing.List[bytes],
        http2: bool = False,
        resp_stream_cls: Optional[Type[MockStream]] = None,
    ) -> None:
        self._buffer = buffer
        self._http2 = http2
        self._resp_stream_cls: Type[MockStream] = resp_stream_cls or MockStream

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
    ) -> NetworkStream:
        return self._resp_stream_cls(list(self._buffer), http2=self._http2)

    def connect_unix_socket(
        self, path: str, timeout: Optional[float] = None
    ) -> NetworkStream:
        return self._resp_stream_cls(list(self._buffer), http2=self._http2)

    def sleep(self, seconds: float) -> None:
        pass


class AsyncMockStream(AsyncNetworkStream):
    def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
        self._buffer = buffer
        self._http2 = http2
        self._closed = False

    async def read(self, max_bytes: int, timeout: Optional[float] = None) -> bytes:
        if self._closed:
            raise ReadError("Connection closed")
        if not self._buffer:
            return b""
        return self._buffer.pop(0)

    async def write(self, buffer: bytes, timeout: Optional[float] = None) -> None:
        pass

    async def aclose(self) -> None:
        self._closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> AsyncNetworkStream:
        return self

    def get_extra_info(self, info: str) -> typing.Any:
        return MockSSLObject(http2=self._http2) if info == "ssl_object" else None


class AsyncHangingStream(AsyncMockStream):
    async def read(self, max_bytes: int, timeout: Optional[float] = None) -> bytes:
        await anyio.sleep(timeout or 0.1)
        raise ReadTimeout


class AsyncMockBackend(AsyncNetworkBackend):
    def __init__(
        self,
        buffer: typing.List[bytes],
        http2: bool = False,
        resp_stream_cls: Optional[Type[AsyncMockStream]] = None,
    ) -> None:
        self._buffer = buffer
        self._http2 = http2
        self._resp_stream_cls: Type[AsyncMockStream] = (
            resp_stream_cls or AsyncMockStream
        )

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
    ) -> AsyncNetworkStream:
        return self._resp_stream_cls(list(self._buffer), http2=self._http2)

    async def connect_unix_socket(
        self, path: str, timeout: Optional[float] = None
    ) -> AsyncNetworkStream:
        return self._resp_stream_cls(list(self._buffer), http2=self._http2)

    async def sleep(self, seconds: float) -> None:
        pass
