from ssl import SSLContext
from typing import Tuple, cast

from socksio import socks5

from .._backends.base import AsyncSocketStream
from .._exceptions import ProxyError
from .._types import URL, Headers, Origin, SocksProxyCredentials, TimeoutDict
from .base import AsyncByteStream
from .connection import AsyncHTTPConnection
from .connection_pool import AsyncConnectionPool


class AsyncSocksProxyProtocol:
    async def connect(
        self,
        socket: AsyncSocketStream,
        hostname: bytes,
        port: int,
        timeout: TimeoutDict,
    ) -> None:
        raise NotImplementedError


class AsyncSocks5ProxyProtocol(AsyncSocksProxyProtocol):
    def __init__(self, proxy_credentials: SocksProxyCredentials = None):
        self.proxy_connection = socks5.SOCKS5Connection()
        self.proxy_credentials = proxy_credentials

    async def connect(
        self,
        socket: AsyncSocketStream,
        hostname: bytes,
        port: int,
        timeout: TimeoutDict,
    ) -> None:
        await self._auth_if_required(socket, timeout)

        is_connected = await self._connect_to_remote_host(
            socket, hostname, port, timeout
        )

        if not is_connected:
            raise ProxyError("Cannot connect through the proxy.")

    async def _auth_if_required(
        self, socket: AsyncSocketStream, timeout: TimeoutDict
    ) -> None:
        is_auth_required = await self._check_for_authentication(socket, timeout)

        if is_auth_required:
            if self.proxy_credentials is None:
                raise ProxyError(
                    "This proxy requires auth, but you didn't set user/password"
                )

            user, password = (
                self.proxy_credentials.username,
                self.proxy_credentials.password,
            )

            await self._auth_using_login_and_password(socket, user, password, timeout)

    async def _check_for_authentication(
        self, socket: AsyncSocketStream, timeout: TimeoutDict
    ) -> bool:
        auth_request = socks5.SOCKS5AuthMethodsRequest(
            [
                socks5.SOCKS5AuthMethod.NO_AUTH_REQUIRED,
                socks5.SOCKS5AuthMethod.USERNAME_PASSWORD,
            ]
        )

        self.proxy_connection.send(auth_request)

        bytes_to_send = self.proxy_connection.data_to_send()
        await socket.write(bytes_to_send, timeout)

        data = await socket.read(1024, timeout)
        auth_ev = self.proxy_connection.receive_data(data)

        return (
            auth_ev.method == socks5.SOCKS5AuthMethod.USERNAME_PASSWORD  # type: ignore
        )

    async def _auth_using_login_and_password(
        self,
        socket: AsyncSocketStream,
        user: bytes,
        password: bytes,
        timeout: TimeoutDict,
    ) -> None:
        user_password_request = socks5.SOCKS5UsernamePasswordRequest(user, password)
        self.proxy_connection.send(user_password_request)

        await socket.write(self.proxy_connection.data_to_send(), timeout)
        user_password_response = await socket.read(2048, timeout)

        user_password_event = self.proxy_connection.receive_data(user_password_response)

        if not user_password_event.success:  # type: ignore
            raise ProxyError("Invalid user/password provided to proxy auth")

    async def _connect_to_remote_host(
        self,
        socket: AsyncSocketStream,
        hostname: bytes,
        port: int,
        timeout: TimeoutDict,
    ) -> bool:
        connect_request = socks5.SOCKS5CommandRequest.from_address(
            socks5.SOCKS5Command.CONNECT, (hostname, port)
        )

        self.proxy_connection.send(connect_request)
        bytes_to_send = self.proxy_connection.data_to_send()

        await socket.write(bytes_to_send, timeout)
        data = await socket.read(1024, timeout)
        event = self.proxy_connection.receive_data(data)

        return event.reply_code == socks5.SOCKS5ReplyCode.SUCCEEDED  # type: ignore


class AsyncSocksProxy(AsyncConnectionPool):
    def __init__(
        self,
        proxy_origin: Origin,
        proxy_mode: str = "socks5",
        proxy_credentials: SocksProxyCredentials = None,
        ssl_context: SSLContext = None,
        max_connections: int = None,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        http2: bool = False,
        uds: str = None,
        local_address: str = None,
        max_keepalive: int = None,
        backend: str = "auto",
    ):
        assert proxy_mode in ("socks5",)

        super().__init__(
            ssl_context=ssl_context,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
            http2=http2,
            uds=uds,
            local_address=local_address,
            max_keepalive=max_keepalive,
            backend=backend,
        )

        self._proxy_mode = proxy_mode
        self._proxy_origin = proxy_origin
        self._proxy_protocol = AsyncSocks5ProxyProtocol(proxy_credentials)

    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        if self._keepalive_expiry is not None:
            await self._keepalive_sweep()

        if self._proxy_mode == "socks5":
            return await self._socks5_arequest(method, url, headers, stream, ext)

        raise NotImplementedError

    async def _socks5_arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:

        ext = {} if ext is None else ext
        timeout = cast(TimeoutDict, ext.get("timeout", {}))
        scheme, remote_host, remote_port, path = url
        remote_origin = (scheme, remote_host, remote_port)
        connection = await self._get_connection_from_pool(remote_origin)

        if connection is None:
            _, proxy_hostname, proxy_port = self._proxy_origin
            socket = await self._backend.open_tcp_stream(
                proxy_hostname,
                proxy_port,
                None,
                timeout,
                local_address=None,
            )

            await self._proxy_protocol.connect(
                socket, remote_host, remote_port, timeout
            )

            connection = AsyncHTTPConnection(
                remote_origin,
                http2=self._http2,
                ssl_context=self._ssl_context,
                socket=socket,
            )

            await self._add_to_pool(connection, timeout)

        return await connection.arequest(method, url, headers, stream, ext)
