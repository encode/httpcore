from typing import AsyncIterator, Iterator

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

    def __init__(self, iterator: Iterator[bytes]) -> None:
        self._iterator = iterator

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._iterator:
            yield chunk


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

    def __init__(self, aiterator: AsyncIterator[bytes]) -> None:
        self._aiterator = aiterator

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._aiterator:
            yield chunk
