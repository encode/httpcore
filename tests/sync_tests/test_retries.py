import queue
import time
from typing import Any, Iterable, List, Optional

import pytest

import httpcore
from httpcore._backends.sync import SyncSocketStream, SyncBackend
from tests.utils import Server


class SyncMockBackend(SyncBackend):
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

    def open_tcp_stream(self, *args: Any, **kwargs: Any) -> SyncSocketStream:
        self._timestamps.append(time.time())
        exc = None if self._exceptions.empty() else self._exceptions.get_nowait()
        if exc is not None:
            raise exc
        return super().open_tcp_stream(*args, **kwargs)


def read_body(stream: Iterable[bytes]) -> bytes:
    return b"".join([chunk for chunk in stream])



def test_no_retries(server: Server) -> None:
    """
    By default, connection failures are not retried on.
    """
    method = b"GET"
    url = (b"http", *server.netloc, b"/")
    headers = [server.host_header]
    backend = SyncMockBackend()

    with httpcore.SyncConnectionPool(
        max_keepalive_connections=0, backend=backend
    ) as http:
        with http.request(method, url, headers) as response:
            status_code, _, stream, _ = response
            assert status_code == 200
            read_body(stream)

        backend.push(httpcore.ConnectTimeout(), httpcore.ConnectError())

        with pytest.raises(httpcore.ConnectTimeout):
            with http.request(method, url, headers) as response:
                pass  # pragma: no cover

        with pytest.raises(httpcore.ConnectError):
            with http.request(method, url, headers) as response:
                pass  # pragma: no cover



def test_retries_enabled(server: Server) -> None:
    """
    When retries are enabled, connection failures are retried on with
    a fixed exponential backoff.
    """
    method = b"GET"
    url = (b"http", *server.netloc, b"/")
    headers = [server.host_header]
    backend = SyncMockBackend()
    retries = 10  # Large enough to not run out of retries within this test.

    with httpcore.SyncConnectionPool(
        retries=retries, max_keepalive_connections=0, backend=backend
    ) as http:
        # Standard case, no failures.
        with http.request(method, url, headers) as response:
            assert backend.pop_open_tcp_stream_intervals() == []
            status_code, _, stream, _ = response
            assert status_code == 200
            read_body(stream)

        # One failure, then success.
        backend.push(httpcore.ConnectError(), None)
        with http.request(method, url, headers) as response:
            assert backend.pop_open_tcp_stream_intervals() == [
                pytest.approx(0, abs=5e-3),  # Retry immediately.
            ]
            status_code, _, stream, _ = response
            assert status_code == 200
            read_body(stream)

        # Three failures, then success.
        backend.push(
            httpcore.ConnectError(),
            httpcore.ConnectTimeout(),
            httpcore.ConnectTimeout(),
            None,
        )
        with http.request(method, url, headers) as response:
            assert backend.pop_open_tcp_stream_intervals() == [
                pytest.approx(0, abs=5e-3),  # Retry immediately.
                pytest.approx(0.5, rel=0.1),  # First backoff.
                pytest.approx(1.0, rel=0.1),  # Second (increased) backoff.
            ]
            status_code, _, stream, _ = response
            assert status_code == 200
            read_body(stream)

        # Non-connect exceptions are not retried on.
        backend.push(httpcore.ReadTimeout(), httpcore.NetworkError())
        with pytest.raises(httpcore.ReadTimeout):
            with http.request(method, url, headers) as response:
                pass  # pragma: no cover

        with pytest.raises(httpcore.NetworkError):
            with http.request(method, url, headers) as response:
                pass  # pragma: no cover



def test_retries_exceeded(server: Server) -> None:
    """
    When retries are enabled and connecting failures more than the configured number
    of retries, connect exceptions are raised.
    """
    method = b"GET"
    url = (b"http", *server.netloc, b"/")
    headers = [server.host_header]
    backend = SyncMockBackend()
    retries = 1

    with httpcore.SyncConnectionPool(
        retries=retries, max_keepalive_connections=0, backend=backend
    ) as http:
        with http.request(method, url, headers) as response:
            status_code, _, stream, _ = response
            assert status_code == 200
            read_body(stream)

        # First failure is retried on, second one isn't.
        backend.push(httpcore.ConnectError(), httpcore.ConnectTimeout())
        with pytest.raises(httpcore.ConnectTimeout):
            with http.request(method, url, headers) as response:
                pass  # pragma: no cover
