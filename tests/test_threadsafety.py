import concurrent.futures
from typing import Iterable

import pytest

import httpcore

from .utils import Server


def read_body(stream: Iterable[bytes]) -> bytes:
    return b"".join(chunk for chunk in stream)


@pytest.mark.parametrize(
    "http2", [pytest.param(False, id="h11"), pytest.param(True, id="h2")]
)
def test_threadsafe_basic(server: Server, http2: bool) -> None:
    """
    The sync connection pool can be used to perform requests concurrently using
    threads.

    Also a regression test for: https://github.com/encode/httpx/issues/1393
    """
    with httpcore.SyncConnectionPool(http2=http2) as http:

        def request(http: httpcore.SyncHTTPTransport) -> int:
            method = b"GET"
            url = (b"http", *server.netloc, b"/")
            headers = [server.host_header]
            with http.request(method, url, headers) as response:
                status_code, _, stream, _ = response
                read_body(stream)
            return status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(request, http) for _ in range(10)]
            num_results = 0

            for future in concurrent.futures.as_completed(futures):
                status_code = future.result()
                assert status_code == 200
                num_results += 1

            assert num_results == 10
