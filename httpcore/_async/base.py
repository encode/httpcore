import enum
from types import TracebackType
from typing import AsyncIterator, Tuple, Type

from .._types import URL, Headers, T


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

    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        """
        The interface for sending a single HTTP request, and returning a response.

        **Parameters:**

        * **method** - `bytes` - The HTTP method, such as `b'GET'`.
        * **url** - `Tuple[bytes, bytes, Optional[int], bytes]` - The URL as a 4-tuple
        of (scheme, host, port, path).
        * **headers** - `Optional[List[Tuple[bytes, bytes]]]` - Any HTTP headers
        to send with the request.
        * **stream** - `Optional[AsyncByteStream]` - The body of the HTTP request.
        * **ext** - `Optional[dict]` - A dictionary of optional extensions.

        ** Returns:**

        A four-tuple of:

        * **status_code** - `int` - The HTTP status code, such as `200`.
        * **headers** - `List[Tuple[bytes, bytes]]` - Any HTTP headers included
        on the response.
        * **stream** - `AsyncByteStream` - The body of the HTTP response.
        * **ext** - `dict` - A dictionary of optional extensions.
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
