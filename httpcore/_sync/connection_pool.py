from ssl import SSLContext
from typing import Callable, Dict, List, Optional, Set, Tuple

from .._backends.auto import SyncSemaphore, SyncBackend
from .._exceptions import PoolTimeout
from .._threadlock import ThreadLock
from .base import (
    SyncByteStream,
    SyncHTTPTransport,
    ConnectionState,
    NewConnectionRequired,
)
from .connection import SyncHTTPConnection

Origin = Tuple[bytes, bytes, int]
URL = Tuple[bytes, bytes, int, bytes]
Headers = List[Tuple[bytes, bytes]]
TimeoutDict = Dict[str, Optional[float]]


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

    def __iter__(self):
        for chunk in self.stream:
            yield chunk

    def close(self):
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

    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
    * **max_connections** - `Optional[int]` - The maximum number of concurrent connections to allow.
    * **max_keepalive** - `Optional[int]` - The maximum number of connections to allow before closing keep-alive connections.
    * **keepalive_expiry** - `Optional[float]` - The maximum time to allow before closing a keep-alive connection.
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
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context
        self.max_connections = max_connections
        self.max_keepalive = max_keepalive
        self.keepalive_expiry = keepalive_expiry
        self.http2 = http2
        self.connections: Dict[Origin, Set[SyncHTTPConnection]] = {}
        self.thread_lock = ThreadLock()
        self.backend = SyncBackend()
        self.next_keepalive_check = 0.0

    @property
    def connection_semaphore(self) -> SyncSemaphore:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_connection_semaphore"):
            if self.max_connections is not None:
                self._connection_semaphore = self.backend.create_semaphore(
                    self.max_connections, exc_class=PoolTimeout
                )
            else:
                self._connection_semaphore = NullSemaphore()

        return self._connection_semaphore

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, Headers, SyncByteStream]:
        timeout = {} if timeout is None else timeout
        origin = url[:3]

        if self.keepalive_expiry is not None:
            self._keepalive_sweep()

        connection: Optional[SyncHTTPConnection] = None
        while connection is None:
            connection = self._get_connection_from_pool(origin)
            is_new_connection = False

            if connection is None:
                self.connection_semaphore.acquire(
                    timeout=timeout.get("pool", None)
                )
                connection = SyncHTTPConnection(
                    origin=origin, http2=self.http2, ssl_context=self.ssl_context,
                )
                with self.thread_lock:
                    self.connections.setdefault(origin, set())
                    self.connections[origin].add(connection)

            try:
                response = connection.request(
                    method, url, headers=headers, stream=stream, timeout=timeout
                )
            except NewConnectionRequired:
                connection = None
            except:
                with self.thread_lock:
                    self.connection_semaphore.release()
                    self.connections[connection.origin].remove(connection)
                    if not self.connections[connection.origin]:
                        del self.connections[connection.origin]
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

        with self.thread_lock:
            if origin in self.connections:
                connections = self.connections[origin]
                for connection in list(connections):
                    if connection.is_http11:
                        seen_http11 = True

                    if connection.state == ConnectionState.IDLE:
                        if connection.is_connection_dropped():
                            # IDLE connections that have been dropped should be
                            # removed from the pool.
                            connections_to_close.add(connection)
                            connections.remove(connection)
                        else:
                            # IDLE connections that are still maintained may
                            # be reused.
                            reuse_connection = connection
                    elif (
                        connection.state == ConnectionState.ACTIVE
                        and connection.is_http2
                    ):
                        # HTTP/2 connections may be reused.
                        reuse_connection = connection
                    elif connection.state == ConnectionState.PENDING:
                        # Pending connections may potentially be reused.
                        pending_connection = connection

                # Clean up the connections mapping if we've no connections
                # remaining for this origin.
                if not connections:
                    del self.connections[origin]

            if reuse_connection is not None:
                # Mark the connection as READY before we return it, to indicate
                # that if it is HTTP/1.1 then it should not be re-acquired.
                reuse_connection.mark_as_ready()
                reuse_connection.expires_at = None
            elif self.http2 and pending_connection is not None and not seen_http11:
                # If we have a PENDING connection, and no HTTP/1.1 connections
                # on this origin, then we can attempt to share the connection.
                reuse_connection = pending_connection

        # Close any dropped connections.
        for connection in connections_to_close:
            connection.close()

        return reuse_connection

    def _response_closed(self, connection: SyncHTTPConnection):
        remove_from_pool = False
        close_connection = False

        with self.thread_lock:
            if connection.state == ConnectionState.CLOSED:
                remove_from_pool = True
            elif connection.state == ConnectionState.IDLE:
                num_connections = sum(
                    [len(conns) for conns in self.connections.values()]
                )
                if (
                    self.max_keepalive is not None
                    and num_connections > self.max_keepalive
                ):
                    remove_from_pool = True
                    close_connection = True
                elif self.keepalive_expiry is not None:
                    now = self.backend.time()
                    connection.expires_at = now + self.keepalive_expiry

            if remove_from_pool:
                if connection in self.connections.get(connection.origin, set()):
                    self.connection_semaphore.release()
                    self.connections[connection.origin].remove(connection)
                    if not self.connections[connection.origin]:
                        del self.connections[connection.origin]

        if close_connection:
            connection.close()

    def _keepalive_sweep(self):
        assert self.keepalive_expiry is not None

        now = self.backend.time()
        if now < self.next_keepalive_check:
            return

        self.next_keepalive_check = now + 1.0
        connections_to_close = set()

        with self.thread_lock:
            for connection_set in list(self.connections.values()):
                for connection in list(connection_set):
                    if (
                        connection.state == ConnectionState.IDLE
                        and connection.expires_at is not None
                        and now > connection.expires_at
                    ):
                        connections_to_close.add(connection)
                        self.connection_semaphore.release()
                        self.connections[connection.origin].remove(connection)
                        if not self.connections[connection.origin]:
                            del self.connections[connection.origin]

        for connection in connections_to_close:
            connection.close()

    def close(self) -> None:
        connections_to_close = set()

        with self.thread_lock:
            for connection_set in self.connections.values():
                connections_to_close.update(connection_set)
            self.connections.clear()

        # Close all connections
        for connection in connections_to_close:
            connection.close()
