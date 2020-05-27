from ssl import SSLContext
from typing import Iterator, Callable, Dict, Optional, Set, Tuple

from .._backends.auto import SyncLock, SyncSemaphore, SyncBackend
from .._exceptions import PoolTimeout
from .._threadlock import ThreadLock
from .._types import URL, Headers, Origin, TimeoutDict
from .._utils import get_logger, url_to_origin
from .base import (
    SyncByteStream,
    SyncHTTPTransport,
    ConnectionState,
    NewConnectionRequired,
)
from .connection import SyncHTTPConnection

logger = get_logger(__name__)


class NullSemaphore(SyncSemaphore):
    def __init__(self) -> None:
        pass

    def acquire(self, timeout: float = None) -> None:
        return

    def release(self) -> None:
        return


class ResponseByteStream(SyncByteStream):
    def __init__(
        self,
        stream: SyncByteStream,
        connection: SyncHTTPConnection,
        callback: Callable,
    ) -> None:
        """
        A wrapper around the response stream that we return from `.request()`.

        Ensures that when `stream.close()` is called, the connection pool
        is notified via a callback.
        """
        self.stream = stream
        self.connection = connection
        self.callback = callback

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.stream:
            yield chunk

    def close(self) -> None:
        try:
            #  Call the underlying stream close callback.
            # This will be a call to `SyncHTTP11Connection._response_closed()`
            # or `SyncHTTP2Stream._response_closed()`.
            self.stream.close()
        finally:
            #  Call the connection pool close callback.
            # This will be a call to `SyncConnectionPool._response_closed()`.
            self.callback(self.connection)


class SyncConnectionPool(SyncHTTPTransport):
    """
    A connection pool for making HTTP requests.

    **Parameters:**

    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for
    verifying connections.
    * **max_connections** - `Optional[int]` - The maximum number of concurrent
    connections to allow.
    * **max_keepalive** - `Optional[int]` - The maximum number of connections
    to allow before closing keep-alive connections.
    * **keepalive_expiry** - `Optional[float]` - The maximum time to allow
    before closing a keep-alive connection.
    * **http2** - `bool` - Enable HTTP/2 support.
    """

    def __init__(
        self,
        ssl_context: SSLContext = None,
        max_connections: int = None,
        max_keepalive: int = None,
        keepalive_expiry: float = None,
        http2: bool = False,
    ):
        self._ssl_context = SSLContext() if ssl_context is None else ssl_context
        self._max_connections = max_connections
        self._max_keepalive = max_keepalive
        self._keepalive_expiry = keepalive_expiry
        self._http2 = http2
        self._connections: Dict[Origin, Set[SyncHTTPConnection]] = {}
        self._thread_lock = ThreadLock()
        self._backend = SyncBackend()
        self._next_keepalive_check = 0.0

    @property
    def _connection_semaphore(self) -> SyncSemaphore:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_internal_semaphore"):
            if self._max_connections is not None:
                self._internal_semaphore = self._backend.create_semaphore(
                    self._max_connections, exc_class=PoolTimeout
                )
            else:
                self._internal_semaphore = NullSemaphore()

        return self._internal_semaphore

    @property
    def _connection_acquiry_lock(self) -> SyncLock:
        if not hasattr(self, "_internal_connection_acquiry_lock"):
            self._internal_connection_acquiry_lock = self._backend.create_lock()
        return self._internal_connection_acquiry_lock

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, Headers, SyncByteStream]:
        assert url[0] in (b"http", b"https")
        origin = url_to_origin(url)

        if self._keepalive_expiry is not None:
            self._keepalive_sweep()

        connection: Optional[SyncHTTPConnection] = None
        while connection is None:
            with self._connection_acquiry_lock:
                # We get-or-create a connection as an atomic operation, to ensure
                # that HTTP/2 requests issued in close concurrency will end up
                # on the same connection.
                logger.trace("get_connection_from_pool=%r", origin)
                connection = self._get_connection_from_pool(origin)

                if connection is None:
                    connection = SyncHTTPConnection(
                        origin=origin, http2=self._http2, ssl_context=self._ssl_context,
                    )
                    logger.trace("created connection=%r", connection)
                    self._add_to_pool(connection, timeout=timeout)
                else:
                    logger.trace("reuse connection=%r", connection)

            try:
                response = connection.request(
                    method, url, headers=headers, stream=stream, timeout=timeout
                )
            except NewConnectionRequired:
                connection = None
            except Exception:
                logger.trace("remove from pool connection=%r", connection)
                self._remove_from_pool(connection)
                raise

        wrapped_stream = ResponseByteStream(
            response[4], connection=connection, callback=self._response_closed
        )
        return response[0], response[1], response[2], response[3], wrapped_stream

    def _get_connection_from_pool(
        self, origin: Origin
    ) -> Optional[SyncHTTPConnection]:
        # Determine expired keep alive connections on this origin.
        seen_http11 = False
        pending_connection = None
        reuse_connection = None
        connections_to_close = set()

        for connection in self._connections_for_origin(origin):
            if connection.is_http11:
                seen_http11 = True

            if connection.state == ConnectionState.IDLE:
                if connection.is_connection_dropped():
                    # IDLE connections that have been dropped should be
                    # removed from the pool.
                    connections_to_close.add(connection)
                    self._remove_from_pool(connection)
                else:
                    # IDLE connections that are still maintained may
                    # be reused.
                    reuse_connection = connection
            elif connection.state == ConnectionState.ACTIVE and connection.is_http2:
                # HTTP/2 connections may be reused.
                reuse_connection = connection
            elif connection.state == ConnectionState.PENDING:
                # Pending connections may potentially be reused.
                pending_connection = connection

        if reuse_connection is not None:
            # Mark the connection as READY before we return it, to indicate
            # that if it is HTTP/1.1 then it should not be re-acquired.
            reuse_connection.mark_as_ready()
            reuse_connection.expires_at = None
        elif self._http2 and pending_connection is not None and not seen_http11:
            # If we have a PENDING connection, and no HTTP/1.1 connections
            # on this origin, then we can attempt to share the connection.
            reuse_connection = pending_connection

        # Close any dropped connections.
        for connection in connections_to_close:
            connection.close()

        return reuse_connection

    def _response_closed(self, connection: SyncHTTPConnection) -> None:
        remove_from_pool = False
        close_connection = False

        if connection.state == ConnectionState.CLOSED:
            remove_from_pool = True
        elif connection.state == ConnectionState.IDLE:
            num_connections = len(self._get_all_connections())
            if (
                self._max_keepalive is not None
                and num_connections > self._max_keepalive
            ):
                remove_from_pool = True
                close_connection = True
            elif self._keepalive_expiry is not None:
                now = self._backend.time()
                connection.expires_at = now + self._keepalive_expiry

        if remove_from_pool:
            self._remove_from_pool(connection)

        if close_connection:
            connection.close()

    def _keepalive_sweep(self) -> None:
        """
        Remove any IDLE connections that have expired past their keep-alive time.
        """
        assert self._keepalive_expiry is not None

        now = self._backend.time()
        if now < self._next_keepalive_check:
            return

        self._next_keepalive_check = now + 1.0
        connections_to_close = set()

        for connection in self._get_all_connections():
            if (
                connection.state == ConnectionState.IDLE
                and connection.expires_at is not None
                and now > connection.expires_at
            ):
                connections_to_close.add(connection)
                self._remove_from_pool(connection)

        for connection in connections_to_close:
            connection.close()

    def _add_to_pool(
        self, connection: SyncHTTPConnection, timeout: TimeoutDict = None
    ) -> None:
        timeout = {} if timeout is None else timeout

        self._connection_semaphore.acquire(timeout=timeout.get("pool", None))
        with self._thread_lock:
            self._connections.setdefault(connection.origin, set())
            self._connections[connection.origin].add(connection)

    def _remove_from_pool(self, connection: SyncHTTPConnection) -> None:
        with self._thread_lock:
            if connection in self._connections.get(connection.origin, set()):
                self._connection_semaphore.release()
                self._connections[connection.origin].remove(connection)
                if not self._connections[connection.origin]:
                    del self._connections[connection.origin]

    def _connections_for_origin(self, origin: Origin) -> Set[SyncHTTPConnection]:
        return set(self._connections.get(origin, set()))

    def _get_all_connections(self) -> Set[SyncHTTPConnection]:
        connections: Set[SyncHTTPConnection] = set()
        for connection_set in self._connections.values():
            connections |= connection_set
        return connections

    def close(self) -> None:
        connections = self._get_all_connections()
        for connection in connections:
            self._remove_from_pool(connection)

        # Close all connections
        for connection in connections:
            connection.close()
