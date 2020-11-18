from typing import AsyncIterator, Iterator


class PlainByteStream:
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
