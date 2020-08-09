from typing import AsyncIterator, Callable, Iterator

from ._async.base import AsyncByteStream
from ._sync.base import SyncByteStream


class PlainByteStream(AsyncByteStream, SyncByteStream):
    """
    A concrete implementation for either sync or async byte streams.
    Just handles a plain byte string as the content of the stream.

    ```
    stream = httpcore.PlainByteStream(b"123")
    ```
    """

    def __init__(self, content: bytes) -> None:
        self._content = content

    def __iter__(self) -> Iterator[bytes]:
        yield self._content

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content


class IteratorByteStream(SyncByteStream):
    """
    A concrete implementation for sync byte streams.
    Handles a byte iterator as the content of the stream.

    ```
    def generate_content():
        ...

    stream = httpcore.IteratorByteStream(generate_content())
    ```
    """

    def __init__(self, iterator: Iterator[bytes], close_func: Callable = None) -> None:
        self._iterator = iterator
        self._close_func = close_func

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._iterator:
            yield chunk

    def close(self) -> None:
        if self._close_func is not None:
            self._close_func()


class AsyncIteratorByteStream(AsyncByteStream):
    """
    A concrete implementation for async byte streams.
    Handles an async byte iterator as the content of the stream.

    ```
    async def generate_content():
        ...

    stream = httpcore.AsyncIteratorByteStream(generate_content())
    ```
    """

    def __init__(
        self, aiterator: AsyncIterator[bytes], aclose_func: Callable = None
    ) -> None:
        self._aiterator = aiterator
        self._aclose_func = aclose_func

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._aiterator:
            yield chunk

    async def aclose(self) -> None:
        if self._aclose_func is not None:
            await self._aclose_func()
