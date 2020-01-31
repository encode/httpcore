from ssl import SSLContext
from types import TracebackType
from typing import Iterator, Dict, List, Tuple, Type


class SyncByteStream:
    """
    The base interface for request and response bodies.

    Concrete implementations should subclass this class, and implement
    the `\\__iter__` method, and optionally the `close` method.
    """

    def __iter__(self) -> Iterator[bytes]:
        """
        Yield bytes representing the request or response body.
        """
        yield b""

    def close(self) -> None:
        """
        Must be called by the client to indicate that the stream has been closed.
        """


class SyncHTTPTransport:
    """
    The base interface for sending HTTP requests.

    Concete implementations should subclass this class, and implement
    the `request` method, and optionally the `close` method.
    """

    def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: SyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        """
        The interface for sending a single HTTP request, and returning a response.

        **Parameters:**

        * **method** - `bytes` - The HTTP method, such as `b'GET'`.
        * **url** - `Tuple[bytes, bytes, int, bytes]` - The URL as a 4-tuple of (scheme, host, port, path).
        * **headers** - `Optional[List[Tuple[bytes, bytes]]]` - Any HTTP headers to send with the request.
        * **stream** - `Optional[SyncByteStream]` - The body of the HTTP request.
        * **timeout** - `Optional[Dict[str, Optional[float]]]` - A dictionary of timeout values for I/O operations.

        ** Returns:**

        A five-tuple of:

        * **http_version** - `bytes` - The HTTP version used by the server, such as `b'HTTP/1.1'`.
        * **status_code** - `int` - The HTTP status code, such as `200`.
        * **reason_phrase** - `bytes` - Any HTTP reason phrase, such as `b'OK'`.
        * **headers** - `List[Tuple[bytes, bytes]]` - Any HTTP headers included on the response.
        * **stream** - `SyncByteStream` - The body of the HTTP response.
        """
        raise NotImplementedError()

    def close(self) -> None:
        """
        Close the implementation, which should close any outstanding response streams,
        and any keep alive connections.
        """

    def __enter__(self) -> "SyncHTTPTransport":
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        self.close()


class SyncConnectionPool(SyncHTTPTransport):
    """
    A connection pool for making HTTP requests.

    **Parameters:**

    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
    * **max_keepalive** - `Optional[int]` - The maximum number of keep alive connections to maintain in the pool.
    * **max_connections** - `Optional[int]` - The maximum number of HTTP connections to allow. Attempting to establish a connection beyond this limit will block for the duration specified in the pool acquiry timeout.
    """

    def __init__(
        self,
        ssl_context: SSLContext = None,
        max_keepalive: int = None,
        max_connections: int = None,
    ):
        pass

    def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: SyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        raise NotImplementedError()

    def close(self) -> None:
        pass


class SyncHTTPProxy(SyncHTTPTransport):
    """
    A connection pool for making HTTP requests via an HTTP proxy.

    **Parameters:**

    * **proxy_url** - `Tuple[bytes, bytes, int, bytes]` - The URL of the proxy service as a 4-tuple of (scheme, host, port, path).
    * **proxy_headers** - `Optional[List[Tuple[bytes, bytes]]]` - A list of proxy headers to include.
    * **proxy_mode** - `Optional[str]` - A proxy mode to operate in. May be "DEFAULT", "FORWARD_ONLY", or "TUNNEL_ONLY".
    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
    * **max_keepalive** - `Optional[int]` - The maximum number of keep alive connections to maintain in the pool.
    * **max_connections** - `Optional[int]` - The maximum number of HTTP connections to allow. Attempting to establish a connection beyond this limit will block for the duration specified in the pool acquiry timeout.
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

    def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: SyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        raise NotImplementedError()

    def close(self) -> None:
        pass
