import ssl
import time
import typing

SOCKET_OPTION = typing.Union[
    typing.Tuple[int, int, int],
    typing.Tuple[int, int, typing.Union[bytes, bytearray]],
    typing.Tuple[int, int, None, int],
]


class NetworkStream:
    def read(self, max_bytes: int, timeout: typing.Optional[float] = None) -> bytes:
        raise NotImplementedError()

    def write(self, buffer: bytes, timeout: typing.Optional[float] = None) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        raise NotImplementedError()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: typing.Optional[str] = None,
        timeout: typing.Optional[float] = None,
    ) -> "NetworkStream":
        raise NotImplementedError()

    def get_extra_info(self, info: str) -> typing.Any:
        return None


class NetworkBackend:
    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> NetworkStream:
        raise NotImplementedError()

    def connect_unix_socket(
        self,
        path: str,
        timeout: typing.Optional[float] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> NetworkStream:
        raise NotImplementedError()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class AsyncNetworkStream:
    async def read(
        self, max_bytes: int, timeout: typing.Optional[float] = None
    ) -> bytes:
        raise NotImplementedError()

    async def write(
        self, buffer: bytes, timeout: typing.Optional[float] = None
    ) -> None:
        raise NotImplementedError()

    async def aclose(self) -> None:
        raise NotImplementedError()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: typing.Optional[str] = None,
        timeout: typing.Optional[float] = None,
    ) -> "AsyncNetworkStream":
        raise NotImplementedError()

    def get_extra_info(self, info: str) -> typing.Any:
        return None


class AsyncNetworkBackend:
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: typing.Optional[float] = None,
        local_address: typing.Optional[str] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:
        raise NotImplementedError()

    async def connect_unix_socket(
        self,
        path: str,
        timeout: typing.Optional[float] = None,
        socket_options: typing.Optional[typing.Iterable[SOCKET_OPTION]] = None,
    ) -> AsyncNetworkStream:
        raise NotImplementedError()

    async def sleep(self, seconds: float) -> None:
        raise NotImplementedError()
