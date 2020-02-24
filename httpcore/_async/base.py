import enum
from types import TracebackType
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Type


async def empty():
    yield b""


class ConnectionState(enum.IntEnum):
    PENDING = 0
    ACTIVE = 1
    ACTIVE_NON_REUSABLE = 2
    IDLE = 3
    CLOSED = 4


class HTTPVersion(enum.IntEnum):
    HTTP_11 = 1
    HTTP_2 = 2


class AsyncByteStream:
    """
    The base interface for request and response bodies.

    Concrete implementations should subclass this class, and implement
    the `\\__aiter__` method, and optionally the `close` method.
    """

    def __init__(
        self, iterator: AsyncIterator[bytes] = None, close_func: Any = None
    ) -> None:
        self.iterator = empty() if iterator is None else iterator
        self.close_func = close_func

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """
        Yield bytes representing the request or response body.
        """
        async for chunk in self.iterator:
            yield chunk

    async def close(self) -> None:
        """
        Must be called by the client to indicate that the stream has been closed.
        """
        if self.close_func is not None:
            await self.close_func()


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
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream]:
        """
        The interface for sending a single HTTP request, and returning a response.

        **Parameters:**

        * **method** - `bytes` - The HTTP method, such as `b'GET'`.
        * **url** - `Tuple[bytes, bytes, int, bytes]` - The URL as a 4-tuple of (scheme, host, port, path).
        * **headers** - `Optional[List[Tuple[bytes, bytes]]]` - Any HTTP headers to send with the request.
        * **stream** - `Optional[AsyncByteStream]` - The body of the HTTP request.
        * **timeout** - `Optional[Dict[str, Optional[float]]]` - A dictionary of timeout values for I/O operations.

        ** Returns:**

        A five-tuple of:

        * **http_version** - `bytes` - The HTTP version used by the server, such as `b'HTTP/1.1'`.
        * **status_code** - `int` - The HTTP status code, such as `200`.
        * **reason_phrase** - `bytes` - Any HTTP reason phrase, such as `b'OK'`.
        * **headers** - `List[Tuple[bytes, bytes]]` - Any HTTP headers included on the response.
        * **stream** - `AsyncByteStream` - The body of the HTTP response.
        """
        raise NotImplementedError()  # pragma: nocover

    async def close(self) -> None:
        """
        Close the implementation, which should close any outstanding response streams,
        and any keep alive connections.
        """

    async def __aenter__(self) -> "AsyncHTTPTransport":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.close()
