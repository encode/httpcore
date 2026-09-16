"""
Test for issue #1110: Connection pool can close a connection it has already
assigned to a queued request.
"""

import threading
import time
import typing

import httpcore
from httpcore._sync.connection import HTTPConnection
from httpcore._sync.connection_pool import PoolRequest

from ..concurrency import open_nursery

RESPONSE_BYTES = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 13\r\n"
    b"\r\n"
    b"Hello, world!"
)


def test_connection_pool_does_not_close_assigned_connection_concurrent():
    """
    Regression test for issue #1110.

    With low max_keepalive_connections, concurrent requests should not fail
    because the pool closes a connection that was already assigned to a request.
    """
    network_backend = httpcore.MockBackend([RESPONSE_BYTES] * 50)

    def fetch(pool: httpcore.ConnectionPool, results: list) -> None:
        try:
            response = pool.request("GET", "http://example.com/")
            response.read()
            results.append("success")
        except Exception as e:
            results.append(f"error: {type(e).__name__}: {e}")

    results: list[str] = []

    with httpcore.ConnectionPool(
        max_connections=1,
        max_keepalive_connections=1,
        network_backend=network_backend,
    ) as pool:
        with open_nursery() as nursery:
            for _ in range(10):
                nursery.start_soon(fetch, pool, results)

    assert all(r == "success" for r in results), f"Some requests failed: {results}"
    assert len(results) == 10


def test_connection_pool_no_hang_on_reuse_after_max_keepalive():
    """
    Regression test for issue #1110.

    When max_keepalive_connections is low and max_connections is high,
    the pool should not close connections that are assigned to queued requests.
    """
    network_backend = httpcore.MockBackend([RESPONSE_BYTES] * 200)

    def fetch(pool: httpcore.ConnectionPool, results: list) -> None:
        try:
            response = pool.request("GET", "http://example.com/")
            response.read()
            results.append("success")
        except Exception as e:
            results.append(f"error: {type(e).__name__}: {e}")

    results: list[str] = []

    with httpcore.ConnectionPool(
        max_connections=20,
        max_keepalive_connections=5,
        network_backend=network_backend,
    ) as pool:
        with open_nursery() as nursery:
            for _ in range(40):
                nursery.start_soon(fetch, pool, results)

    assert all(r == "success" for r in results), f"Some requests failed: {results}"
    assert len(results) == 40


def test_assign_requests_does_not_close_assigned_idle_connections():
    """
    Directly test the bug: _assign_requests_to_connections should not close
    an idle connection that has already been assigned to a queued request.

    Setup:
    - An idle connection in the pool (already used for a prior request)
    - A PoolRequest that references this connection (assigned but not yet used)
    - max_keepalive_connections=0 so any idle connection triggers surplus closing

    Before fix: the connection gets closed even though it's assigned to a request.
    After fix: the connection is preserved.
    """
    network_backend = httpcore.MockBackend([RESPONSE_BYTES] * 10)
    pool = httpcore.ConnectionPool(
        max_connections=10,
        max_keepalive_connections=0,
        network_backend=network_backend,
    )

    # Create a connection and simulate it being IDLE (completed a prior request)
    origin = httpcore.Origin(b"http", b"example.com", 80)
    connection = pool.create_connection(origin)

    # Force the inner connection to be created and idle
    # We need to make a request first, then let it complete
    request = httpcore.Request("GET", "http://example.com/", headers=[(b"host", b"example.com")])
    response = connection.handle_request(request)
    response.read()
    response.close()
    # Now the connection should be IDLE
    assert connection.is_idle(), f"Connection should be IDLE, got {connection.info()}"

    # Add the connection to the pool
    pool._connections.append(connection)

    # Create a pool_request and assign it to this connection
    pool_request = PoolRequest(request)
    pool_request.assign_to_connection(connection)

    # The request is no longer queued (it has a connection)
    assert not pool_request.is_queued()

    # Also add it to the pool's request list (as if it was just assigned)
    pool._requests.append(pool_request)

    # Now call _assign_requests_to_connections
    # It should NOT close the connection because it's assigned to a request
    closing = pool._assign_requests_to_connections()

    assert connection not in closing, (
        "Connection assigned to a request should NOT be in closing list"
    )
    assert connection in pool._connections, (
        "Connection should still be in the pool"
    )

    pool.close()


def test_surplus_idle_not_closed_when_assigned():
    """
    When there are more idle connections than max_keepalive_connections,
    connections that have been assigned to requests should not be closed.
    """
    network_backend = httpcore.MockBackend([RESPONSE_BYTES] * 20)
    pool = httpcore.ConnectionPool(
        max_connections=10,
        max_keepalive_connections=0,
        network_backend=network_backend,
    )

    origin = httpcore.Origin(b"http", b"example.com", 80)

    # Create 2 connections and make them IDLE
    conn1 = pool.create_connection(origin)
    conn2 = pool.create_connection(origin)

    req1 = httpcore.Request("GET", "http://example.com/", headers=[(b"host", b"example.com")])
    req2 = httpcore.Request("GET", "http://example.com/", headers=[(b"host", b"example.com")])

    resp1 = conn1.handle_request(req1)
    resp1.read()
    resp1.close()
    resp2 = conn2.handle_request(req2)
    resp2.read()
    resp2.close()

    assert conn1.is_idle()
    assert conn2.is_idle()

    pool._connections.extend([conn1, conn2])

    # Assign conn1 to a pool_request (it's been given to a waiting thread)
    pool_request = PoolRequest(req1)
    pool_request.assign_to_connection(conn1)
    pool._requests.append(pool_request)

    # With max_keepalive_connections=0, any free idle connection is surplus.
    # conn2 should be closed (surplus), but conn1 should NOT because it's assigned.
    closing = pool._assign_requests_to_connections()

    assert conn1 not in closing, "Assigned connection should not be closed"
    assert conn2 in closing, "Unassigned surplus idle connection should be closed"
    assert conn1 in pool._connections, "Assigned connection should remain in pool"

    pool.close()
