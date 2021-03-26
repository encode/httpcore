import queue
import time
from typing import Any, List, Optional

import pytest

import httpcore
from httpcore._backends.auto import AsyncSocketStream, AutoBackend
from tests.utils import Server


class AsyncMockBackend(AutoBackend):
    def __init__(self) -> None:
        super().__init__()
        self._exceptions: queue.Queue[Optional[Exception]] = queue.Queue()
        self._timestamps: List[float] = []

    def push(self, *exceptions: Optional[Exception]) -> None:
        for exc in exceptions:
            self._exceptions.put(exc)

    def pop_open_tcp_stream_intervals(self) -> list:
        intervals = [b - a for a, b in zip(self._timestamps, self._timestamps[1:])]
        self._timestamps.clear()
        return intervals

    async def open_tcp_stream(self, *args: Any, **kwargs: Any) -> AsyncSocketStream:
        self._timestamps.append(time.time())
        exc = None if self._exceptions.empty() else self._exceptions.get_nowait()
        if exc is not None:
            raise exc
        return await super().open_tcp_stream(*args, **kwargs)


async def read_body(stream: httpcore.AsyncByteStream) -> bytes:
    try:
        return b"".join([chunk async for chunk in stream])
    finally:
        await stream.aclose()


@pytest.mark.anyio
async def test_no_retries(server: Server) -> None:
    """
    By default, connection failures are not retried on.
    """
    backend = AsyncMockBackend()

    async with httpcore.AsyncConnectionPool(
        max_keepalive_connections=0, backend=backend
    ) as http:
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", *server.netloc, b"/"),
            headers=[server.host_header],
        )
        status_code, _, stream, _ = response
        assert status_code == 200
        await read_body(stream)

        backend.push(httpcore.ConnectTimeout(), httpcore.ConnectError())

        with pytest.raises(httpcore.ConnectTimeout):
            await http.handle_async_request(
                method=b"GET",
                url=(b"http", *server.netloc, b"/"),
                headers=[server.host_header],
            )

        with pytest.raises(httpcore.ConnectError):
            await http.handle_async_request(
                method=b"GET",
                url=(b"http", *server.netloc, b"/"),
                headers=[server.host_header],
            )


@pytest.mark.anyio
async def test_retries_enabled(server: Server) -> None:
    """
    When retries are enabled, connection failures are retried on with
    a fixed exponential backoff.
    """
    backend = AsyncMockBackend()
    retries = 10  # Large enough to not run out of retries within this test.

    async with httpcore.AsyncConnectionPool(
        retries=retries, max_keepalive_connections=0, backend=backend
    ) as http:
        # Standard case, no failures.
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", *server.netloc, b"/"),
            headers=[server.host_header],
        )
        assert backend.pop_open_tcp_stream_intervals() == []
        status_code, _, stream, _ = response
        assert status_code == 200
        await read_body(stream)

        # One failure, then success.
        backend.push(httpcore.ConnectError(), None)
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", *server.netloc, b"/"),
            headers=[server.host_header],
        )
        assert backend.pop_open_tcp_stream_intervals() == [
            pytest.approx(0, abs=5e-3),  # Retry immediately.
        ]
        status_code, _, stream, _ = response
        assert status_code == 200
        await read_body(stream)

        # Three failures, then success.
        backend.push(
            httpcore.ConnectError(),
            httpcore.ConnectTimeout(),
            httpcore.ConnectTimeout(),
            None,
        )
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", *server.netloc, b"/"),
            headers=[server.host_header],
        )
        assert backend.pop_open_tcp_stream_intervals() == [
            pytest.approx(0, abs=5e-3),  # Retry immediately.
            pytest.approx(0.5, rel=0.1),  # First backoff.
            pytest.approx(1.0, rel=0.1),  # Second (increased) backoff.
        ]
        status_code, _, stream, _ = response
        assert status_code == 200
        await read_body(stream)

        # Non-connect exceptions are not retried on.
        backend.push(httpcore.ReadTimeout(), httpcore.NetworkError())
        with pytest.raises(httpcore.ReadTimeout):
            await http.handle_async_request(
                method=b"GET",
                url=(b"http", *server.netloc, b"/"),
                headers=[server.host_header],
            )
        with pytest.raises(httpcore.NetworkError):
            await http.handle_async_request(
                method=b"GET",
                url=(b"http", *server.netloc, b"/"),
                headers=[server.host_header],
            )


@pytest.mark.anyio
async def test_retries_exceeded(server: Server) -> None:
    """
    When retries are enabled and connecting failures more than the configured number
    of retries, connect exceptions are raised.
    """
    backend = AsyncMockBackend()
    retries = 1

    async with httpcore.AsyncConnectionPool(
        retries=retries, max_keepalive_connections=0, backend=backend
    ) as http:
        response = await http.handle_async_request(
            method=b"GET",
            url=(b"http", *server.netloc, b"/"),
            headers=[server.host_header],
        )
        status_code, _, stream, _ = response
        assert status_code == 200
        await read_body(stream)

        # First failure is retried on, second one isn't.
        backend.push(httpcore.ConnectError(), httpcore.ConnectTimeout())
        with pytest.raises(httpcore.ConnectTimeout):
            await http.handle_async_request(
                method=b"GET",
                url=(b"http", *server.netloc, b"/"),
                headers=[server.host_header],
            )
