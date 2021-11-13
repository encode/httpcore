from typing import AsyncIterator, Iterator, List

import pytest

import httpcore

# URL


def test_url():
    url = httpcore.URL("https://www.example.com/")
    assert url == httpcore.URL(
        scheme="https", host="www.example.com", port=None, target="/"
    )
    assert bytes(url) == b"https://www.example.com/"


def test_url_with_port():
    url = httpcore.URL("https://www.example.com:443/")
    assert url == httpcore.URL(
        scheme="https", host="www.example.com", port=443, target="/"
    )
    assert bytes(url) == b"https://www.example.com:443/"


def test_url_with_invalid_argument():
    with pytest.raises(TypeError) as exc_info:
        httpcore.URL(123)  # type: ignore
    assert str(exc_info.value) == "url must be bytes or str, but got int."


def test_url_cannot_include_unicode_strings():
    """
    URLs instantiated with strings outside of the plain ASCII range are disallowed,
    but the explicit style allows for these ambiguous cases to be precisely expressed.
    """
    with pytest.raises(TypeError) as exc_info:
        httpcore.URL("https://www.example.com/☺")
    assert str(exc_info.value) == "url strings may not include unicode characters."

    httpcore.URL(scheme=b"https", host=b"www.example.com", target="/☺".encode("utf-8"))


# Request


def test_request():
    request = httpcore.Request("GET", "https://www.example.com/")
    assert request.method == b"GET"
    assert request.url == httpcore.URL("https://www.example.com/")
    assert request.headers == []
    assert request.extensions == {}
    assert repr(request) == "<Request [b'GET']>"
    assert (
        repr(request.url)
        == "URL(scheme=b'https', host=b'www.example.com', port=None, target=b'/')"
    )
    assert repr(request.stream) == "<ByteStream [0 bytes]>"


def test_request_with_invalid_method():
    with pytest.raises(TypeError) as exc_info:
        httpcore.Request(123, "https://www.example.com/")  # type: ignore
    assert str(exc_info.value) == "method must be bytes or str, but got int."


def test_request_with_invalid_url():
    with pytest.raises(TypeError) as exc_info:
        httpcore.Request("GET", 123)  # type: ignore
    assert str(exc_info.value) == "url must be a URL, bytes, or str, but got int."


def test_request_with_invalid_headers():
    with pytest.raises(TypeError) as exc_info:
        httpcore.Request("GET", "https://www.example.com/", headers=123)  # type: ignore
    assert (
        str(exc_info.value)
        == "headers must be a mapping or sequence of two-tuples, but got int."
    )


# Response


def test_response():
    response = httpcore.Response(200)
    assert response.status == 200
    assert response.headers == []
    assert response.extensions == {}
    assert repr(response) == "<Response [200]>"
    assert repr(response.stream) == "<ByteStream [0 bytes]>"


# Tests for reading and streaming sync byte streams...


class ByteIterator:
    def __init__(self, chunks: List[bytes]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def test_response_sync_read():
    stream = ByteIterator([b"Hello, ", b"world!"])
    response = httpcore.Response(200, content=stream)
    assert response.read() == b"Hello, world!"
    assert response.content == b"Hello, world!"


def test_response_sync_streaming():
    stream = ByteIterator([b"Hello, ", b"world!"])
    response = httpcore.Response(200, content=stream)
    content = b"".join([chunk for chunk in response.iter_stream()])
    assert content == b"Hello, world!"

    # We streamed the response rather than reading it, so .content is not available.
    with pytest.raises(RuntimeError):
        response.content

    # Once we've streamed the response, we can't access the stream again.
    with pytest.raises(RuntimeError):
        for _chunk in response.iter_stream():
            pass  # pragma: nocover


# Tests for reading and streaming async byte streams...


class AsyncByteIterator:
    def __init__(self, chunks: List[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@pytest.mark.trio
async def test_response_async_read():
    stream = AsyncByteIterator([b"Hello, ", b"world!"])
    response = httpcore.Response(200, content=stream)
    assert await response.aread() == b"Hello, world!"
    assert response.content == b"Hello, world!"


@pytest.mark.trio
async def test_response_async_streaming():
    stream = AsyncByteIterator([b"Hello, ", b"world!"])
    response = httpcore.Response(200, content=stream)
    content = b"".join([chunk async for chunk in response.aiter_stream()])
    assert content == b"Hello, world!"

    # We streamed the response rather than reading it, so .content is not available.
    with pytest.raises(RuntimeError):
        response.content

    # Once we've streamed the response, we can't access the stream again.
    with pytest.raises(RuntimeError):
        async for chunk in response.aiter_stream():
            pass  # pragma: nocover
