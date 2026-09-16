"""
Test for issue #1110: Connection pool can close a connection it has already
assigned to a queued request. (Async version)
"""

import typing

import anyio
import pytest

import httpcore
import httpcore._async.connection_pool
from httpcore._async.connection_pool import AsyncPoolRequest

RESPONSE_BYTES = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 13\r\n"
    b"\r\n"
    b"Hello, world!"
)


@pytest.mark.anyio
async def test_async_connection_pool_does_not_close_assigned_connection():
    """
    Regression test for issue #1110.
    """
    network_backend = httpcore.AsyncMockBackend([RESPONSE_BYTES] * 50)

    async def fetch(pool: httpcore.AsyncConnectionPool, results: list) -> None:
        try:
            response = await pool.request("GET", "http://example.com/")
            await response.aread()
            results.append("success")
        except Exception as e:
            results.append(f"error: {type(e).__name__}: {e}")

    results: list[str] = []

    async with httpcore.AsyncConnectionPool(
        max_connections=1,
        max_keepalive_connections=1,
        network_backend=network_backend,
    ) as pool:
        async with anyio.create_task_group() as tg:
            for _ in range(10):
                tg.start_soon(fetch, pool, results)

    assert all(r == "success" for r in results), f"Some requests failed: {results}"
    assert len(results) == 10


@pytest.mark.anyio
async def test_async_connection_pool_no_hang_on_reuse_after_max_keepalive():
    """
    Regression test for issue #1110.
    """
    network_backend = httpcore.AsyncMockBackend([RESPONSE_BYTES] * 200)

    async def fetch(pool: httpcore.AsyncConnectionPool, results: list) -> None:
        try:
            response = await pool.request("GET", "http://example.com/")
            await response.aread()
            results.append("success")
        except Exception as e:
            results.append(f"error: {type(e).__name__}: {e}")

    results: list[str] = []

    async with httpcore.AsyncConnectionPool(
        max_connections=20,
        max_keepalive_connections=5,
        network_backend=network_backend,
    ) as pool:
        async with anyio.create_task_group() as tg:
            for _ in range(40):
                tg.start_soon(fetch, pool, results)

    assert all(r == "success" for r in results), f"Some requests failed: {results}"
    assert len(results) == 40


@pytest.mark.anyio
async def test_async_assign_requests_does_not_close_assigned_idle_connections():
    """
    Directly test the bug: _assign_requests_to_connections should not close
    an idle connection that has already been assigned to a queued request.
    """
    network_backend = httpcore.AsyncMockBackend([RESPONSE_BYTES] * 10)
    pool = httpcore.AsyncConnectionPool(
        max_connections=10,
        max_keepalive_connections=0,
        network_backend=network_backend,
    )

    origin = httpcore.Origin(b"http", b"example.com", 80)
    connection = pool.create_connection(origin)

    request = httpcore.Request("GET", "http://example.com/", headers=[(b"host", b"example.com")])
    response = await connection.handle_async_request(request)
    await response.aread()
    await response.aclose()
    assert connection.is_idle(), f"Connection should be IDLE, got {connection.info()}"

    pool._connections.append(connection)

    pool_request = AsyncPoolRequest(request)
    pool_request.assign_to_connection(connection)

    assert not pool_request.is_queued()

    pool._requests.append(pool_request)

    closing = pool._assign_requests_to_connections()

    assert connection not in closing, (
        "Connection assigned to a request should NOT be in closing list"
    )
    assert connection in pool._connections, (
        "Connection should still be in the pool"
    )

    await pool.aclose()


@pytest.mark.anyio
async def test_async_surplus_idle_not_closed_when_assigned():
    """
    When there are more idle connections than max_keepalive_connections,
    connections that have been assigned to requests should not be closed.
    """
    network_backend = httpcore.AsyncMockBackend([RESPONSE_BYTES] * 20)
    pool = httpcore.AsyncConnectionPool(
        max_connections=10,
        max_keepalive_connections=0,
        network_backend=network_backend,
    )

    origin = httpcore.Origin(b"http", b"example.com", 80)

    conn1 = pool.create_connection(origin)
    conn2 = pool.create_connection(origin)

    req1 = httpcore.Request("GET", "http://example.com/", headers=[(b"host", b"example.com")])
    req2 = httpcore.Request("GET", "http://example.com/", headers=[(b"host", b"example.com")])

    resp1 = await conn1.handle_async_request(req1)
    await resp1.aread()
    await resp1.aclose()
    resp2 = await conn2.handle_async_request(req2)
    await resp2.aread()
    await resp2.aclose()

    assert conn1.is_idle()
    assert conn2.is_idle()

    pool._connections.extend([conn1, conn2])

    pool_request = AsyncPoolRequest(req1)
    pool_request.assign_to_connection(conn1)
    pool._requests.append(pool_request)

    closing = pool._assign_requests_to_connections()

    assert conn1 not in closing, "Assigned connection should not be closed"
    assert conn2 in closing, "Unassigned surplus idle connection should be closed"
    assert conn1 in pool._connections, "Assigned connection should remain in pool"

    await pool.aclose()
