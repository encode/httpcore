import enum
from types import TracebackType
from typing import Iterator, Callable, List, Tuple, Type

from .._types import URL, Headers, TimeoutDict


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


class SyncByteStream:
    """
    The base interface for request and response bodies.

    Concrete implementations should subclass this class, and implement
    the `\\__iter__` method, and optionally the `close` method.
    """

    def __init__(
        self,
        content: bytes = b"",
        iterator: Iterator[bytes] = None,
        close_func: Callable = None,
    ) -> None:
        #  We're doing a bit of a funny dance here to ensure that type checkers
        # don't make any assumptions about the attribute interfaces that
        # SyncByteStream subclasses should support.

        # This allows us to include a simple base-case implementation on the
        # class itself, wile still treating subclasses as plain
        # "implement this interface" cases.
        assert iterator is None or not content
        setattr(self, "content", content)
        setattr(self, "iterator", iterator)
        setattr(self, "close_func", close_func)

    def __iter__(self) -> Iterator[bytes]:
        """
        Yield bytes representing the request or response body.
        """
        content = getattr(self, "content", b"")
        iterator = getattr(self, "iterator", None)

        if iterator is None:
            yield content
        else:
            for chunk in iterator:
                yield chunk

    def close(self) -> None:
        """
        Must be called by the client to indicate that the stream has been closed.
        """
        close_func = getattr(self, "close_func")

        if close_func is not None:
            close_func()


class SyncHTTPTransport:
    """
    The base interface for sending HTTP requests.

    Concete implementations should subclass this class, and implement
    the `request` method, and optionally the `close` method.
    """

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        """
        The interface for sending a single HTTP request, and returning a response.

        **Parameters:**

        * **method** - `bytes` - The HTTP method, such as `b'GET'`.
        * **url** - `Tuple[bytes, bytes, Optional[int], bytes]` - The URL as a 4-tuple of
        (scheme, host, port, path).
        * **headers** - `Optional[List[Tuple[bytes, bytes]]]` - Any HTTP headers
        to send with the request.
        * **stream** - `Optional[SyncByteStream]` - The body of the HTTP request.
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
        * **stream** - `SyncByteStream` - The body of the HTTP response.
        """
        raise NotImplementedError()  # pragma: nocover

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
