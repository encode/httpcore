import anyio
import pytest

import httpcore
from httpcore._models import (
    enforce_bytes,
    enforce_headers,
    enforce_url,
    include_request_headers,
)


@pytest.mark.anyio
async def test_available_connections_reassigned():
    """
    Setup: max_connections=1, start 3 requests
    Expected: 2 should be queued, 1 should be active

    After reading/closing first request:
    Expected: 1 active, 1 queued, 1 connection
    Only 1 request should be assigned to the freed-up connection
    """
    network_backend = httpcore.AsyncMockBackend(
        [
            # First response
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
            # Second response
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
            # Third response
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    async with httpcore.AsyncConnectionPool(
        network_backend=network_backend,
        max_connections=1,  # Allow a single concurrent request
        max_keepalive_connections=1,
        keepalive_expiry=10.0,  # Long timeout to avoid expiry issues
        http1=True,
        http2=False,
    ) as pool:
        method_str = "GET"
        url_str = "https://example.com/"
        headers = None

        method = enforce_bytes(method_str, name="method")
        url = enforce_url(url_str, name="url")
        headers = enforce_headers(headers, name="headers")
        headers = include_request_headers(headers, url=url, content=None)

        request1 = httpcore.Request(method, url, headers=headers)
        request2 = httpcore.Request(method, url, headers=headers)
        request3 = httpcore.Request(method, url, headers=headers)

        # Do the first request
        response1 = await pool.handle_async_request(request1)

        # Start requests 2 and 3 as tasks so they get queued but don't block
        async with anyio.create_task_group() as tg:
            tg.start_soon(pool.handle_async_request, request2)
            tg.start_soon(pool.handle_async_request, request3)

            # Give a short time for the tasks to start and for the requests to get added to the queue
            await anyio.sleep(0.01)

            # With max_connections=1, we should have:
            # - 1 active request (request1)
            # - 2 queued requests
            # - 1 connection
            assert (
                repr(pool)
                == "<AsyncConnectionPool [Requests: 1 active, 2 queued | Connections: 1 active, 0 idle]>"
            )

            # Monkey patch connection's handle_async_request to intercept ConnectionNotAvailable
            for connection in pool._connections:
                original_handle = connection.handle_async_request

                async def monitored_handle_async_request(request):
                    try:
                        return await original_handle(request)
                    except httpcore.ConnectionNotAvailable:  # pragma: nocover
                        pytest.fail(  # pragma: nocover
                            "ConnectionNotAvailable was raised on connection, "
                            "indicating that multiple requests were assigned to a single HTTP/1.1 connection"
                        )

                connection.handle_async_request = monitored_handle_async_request  # type: ignore[method-assign]

            # Read and close the first response
            await response1.aread()
            await response1.aclose()

            # Give a short time for the pool to assign the freed-up connection to the queued request
            # This will trigger the ConnectionNotAvailable if multiple requests are assigned to the same connection
            await anyio.sleep(0.05)

            # Cancel taskgroup to avoid a hanging test
            # (since request2 is never closed, and hence the task for request3 cannot start)
            tg.cancel_scope.cancel()
