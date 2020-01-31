from ssl import SSLContext
from typing import AsyncIterator, Tuple, List, Optional, Type
from types import TracebackType


class AsyncByteStream:
    """
    The base interface for request and response bodies.

    Concrete implementations should subclass this class, and implement
    the `\\__aiter__` method, and optionally the `close` method.
    """

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """
        Yield bytes representing the request or response body.
        """
        yield b''

    async def close(self) -> None:
        """
        Must be called by the client to indicate that the stream has been closed.
        """
        pass


class AsyncHTTPTransport:
    """
    The base interface for sending HTTP requests.

    Concete implementations should subclass this class, and implement
    the `request` method, and optionally the `close` method.
    """

    async def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: AsyncByteStream = None,
        timeout: Tuple[
            Optional[float], Optional[float], Optional[float], Optional[float]
        ] = None,
    ) -> Tuple[
        bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream
    ]:
        """
        The interface for sending a single HTTP request, and returning a response.

        **Parameters:**

        * **method** - *bytes* - The HTTP method, such as `b'GET'`.
        * **url** - *(bytes, bytes, int, bytes)* - The URL as a 4-tuple of (scheme, host, port, path).
        * **headers** - *list of (bytes, bytes), optional* - Any HTTP headers to send with the request.
        * **stream** - *bytes async iterator, optional* - The body of the HTTP request.
        * **timeout** - *(float, float, float, float), all optional.* - A tuple of timeout values for (read, write, connect, pool acquiry) operations.

        ** Returns:**

        A five-tuple of:

        * **http_version** - *bytes* - The HTTP version used by the server, such as `b'HTTP/1.1'`.
        * **status_code** - *int* - The HTTP status code, such as `200`.
        * **reason_phrase** - *bytes* - Any HTTP reason phrase, such as `b'OK'`.
        * **headers** - *list of (bytes, bytes)* - Any HTTP headers included on the response.
        * **stream** - *bytes async iterator* - The body of the HTTP response.
        """
        raise NotImplementedError()

    async def close(self) -> None:
        """
        Close the implementation, which should close any outstanding response streams,
        and any keep alive connections.
        """
        pass

    async def __aenter__(self) -> "AsyncDispatchInterface":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.close()


class AsyncConnectionPool(AsyncHTTPTransport):
    """
    A connection pool for making HTTP requests.

    **Parameters:**

    * **ssl_context** - *SSLContext, optional* - An SSL context to use for verifying connections.
    * **max_keepalive** - *int, optional* - The maximum number of keep alive connections to maintain in the pool.
    * **max_connections** - *int, optional* - The maximum number of HTTP connections to allow. Attempting to establish a connection beyond this limit will block for the duration specified in the pool acquiry timeout.
    """

    def __init__(
        self,
        ssl_context: SSLContext = None,
        max_keepalive: int = None,
        max_connections: int = None,
    ):
        pass

    async def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: AsyncByteStream = None,
        timeout: Tuple[float, float, float, float] = None,
    ) -> Tuple[
        bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream
    ]:
        pass

    async def close(self) -> None:
        pass


class AsyncHTTPProxy(AsyncHTTPTransport):
    """
    A connection pool for making HTTP requests via an HTTP proxy.

    **Parameters:**

    * **proxy_url** - *(bytes, bytes, int, bytes)* - The URL of the proxy service as a 4-tuple of (scheme, host, port, path).
    * **proxy_headers** - *list of (bytes, bytes), optional* - An SSL context to use for verifying connections.
    * **proxy_mode** - *str, optional* - A proxy mode to operate in. May be "DEFAULT", "FORWARD_ONLY", or "TUNNEL_ONLY".
    * **ssl_context** - *SSLContext, optional* - An SSL context to use for verifying connections.
    * **max_keepalive** - *int, optional* - The maximum number of keep alive connections to maintain in the pool.
    * **max_connections** - *int, optional* - The maximum number of HTTP connections to allow. Attempting to establish a connection beyond this limit will block for the duration specified in the pool acquiry timeout.
    """

    def __init__(
        self,
        proxy_url: Tuple[bytes, bytes, int, bytes],
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        proxy_mode: str = None,
        ssl_context: SSLContext = None,
        max_keepalive: int = None,
        max_connections: int = None,
    ):
        pass

    async def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: AsyncByteStream = None,
        timeout: Tuple[float, float, float, float] = None,
    ) -> Tuple[
        bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream
    ]:
        pass

    async def close(self) -> None:
        pass
