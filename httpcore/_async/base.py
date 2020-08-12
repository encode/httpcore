import enum
from types import TracebackType
from typing import AsyncIterator, List, Tuple, Type

from .._types import URL, Headers, T, TimeoutDict


class NewConnectionRequired(Exception):
    pass


class ConnectionState(enum.IntEnum):
    """
    PENDING  READY
        |    |   ^
        v    V   |
        ACTIVE   |
         |  |    |
         |  V    |
         V  IDLE-+
       FULL   |
         |    |
         V    V
         CLOSED
    """

    PENDING = 0  # Connection not yet acquired.
    READY = 1  # Re-acquired from pool, about to send a request.
    ACTIVE = 2  # Active requests.
    FULL = 3  # Active requests, no more stream IDs available.
    IDLE = 4  # No active requests.
    CLOSED = 5  # Connection closed.


class AsyncByteStream:
    """
    The base interface for request and response bodies.

    Concrete implementations should subclass this class, and implement
    the `\\__aiter__` method, and optionally the `aclose` method.
    """

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """
        Yield bytes representing the request or response body.
        """
        yield b""  # pragma: nocover

    async def aclose(self) -> None:
        """
        Must be called by the client to indicate that the stream has been closed.
        """
        pass  # pragma: nocover


class AsyncHTTPTransport:
    """
    The base interface for sending HTTP requests.

    Concete implementations should subclass this class, and implement
    the `request` method, and optionally the `close` method.
    """

    async def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream]:
        """
        The interface for sending a single HTTP request, and returning a response.

        **Parameters:**

        * **method** - `bytes` - The HTTP method, such as `b'GET'`.
        * **url** - `Tuple[bytes, bytes, Optional[int], bytes]` - The URL as a 4-tuple
        of (scheme, host, port, path).
        * **headers** - `Optional[List[Tuple[bytes, bytes]]]` - Any HTTP headers
        to send with the request.
        * **stream** - `Optional[AsyncByteStream]` - The body of the HTTP request.
        * **timeout** - `Optional[Dict[str, Optional[float]]]` - A dictionary of
        timeout values for I/O operations. Supported keys are "pool" for acquiring a
        connection from the connection pool, "read" for reading from the connection,
        "write" for writing to the connection and "connect" for opening the connection.
        Values are floating point seconds.

        ** Returns:**

        A five-tuple of:

        * **http_version** - `bytes` - The HTTP version used by the server,
        such as `b'HTTP/1.1'`.
        * **status_code** - `int` - The HTTP status code, such as `200`.
        * **reason_phrase** - `bytes` - Any HTTP reason phrase, such as `b'OK'`.
        * **headers** - `List[Tuple[bytes, bytes]]` - Any HTTP headers included
        on the response.
        * **stream** - `AsyncByteStream` - The body of the HTTP response.
        """
        raise NotImplementedError()  # pragma: nocover

    async def aclose(self) -> None:
        """
        Close the implementation, which should close any outstanding response streams,
        and any keep alive connections.
        """

    async def __aenter__(self: T) -> T:
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.aclose()
