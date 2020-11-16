import warnings
from ssl import SSLContext
from typing import (
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
    cast,
)

from .._backends.auto import AsyncBackend, AsyncLock, AsyncSemaphore
from .._backends.base import lookup_async_backend
from .._exceptions import LocalProtocolError, PoolTimeout, UnsupportedProtocol
from .._threadlock import ThreadLock
from .._types import URL, Headers, Origin, TimeoutDict
from .._utils import get_logger, origin_to_url_string, url_to_origin
from .base import (
    AsyncByteStream,
    AsyncHTTPTransport,
    ConnectionState,
    NewConnectionRequired,
)
from .connection import AsyncHTTPConnection

logger = get_logger(__name__)


class NullSemaphore(AsyncSemaphore):
    def __init__(self) -> None:
        pass

    async def acquire(self, timeout: float = None) -> None:
        return

    async def release(self) -> None:
        return


class ResponseByteStream(AsyncByteStream):
    def __init__(
        self,
        stream: AsyncByteStream,
        connection: AsyncHTTPConnection,
        callback: Callable,
    ) -> None:
        """
        A wrapper around the response stream that we return from `.arequest()`.

        Ensures that when `stream.aclose()` is called, the connection pool
        is notified via a callback.
        """
        self.stream = stream
        self.connection = connection
        self.callback = callback

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        try:
            # Call the underlying stream close callback.
            # This will be a call to `AsyncHTTP11Connection._response_closed()`
            # or `AsyncHTTP2Stream._response_closed()`.
            await self.stream.aclose()
        finally:
            # Call the connection pool close callback.
            # This will be a call to `AsyncConnectionPool._response_closed()`.
            await self.callback(self.connection)


class AsyncConnectionPool(AsyncHTTPTransport):
    """
    A connection pool for making HTTP requests.

    **Parameters:**

    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for
    verifying connections.
    * **max_connections** - `Optional[int]` - The maximum number of concurrent
    connections to allow.
    * **max_keepalive_connections** - `Optional[int]` - The maximum number of
    connections to allow before closing keep-alive connections.
    * **keepalive_expiry** - `Optional[float]` - The maximum time to allow
    before closing a keep-alive connection.
    * **http2** - `bool` - Enable HTTP/2 support.
    * **uds** - `str` - Path to a Unix Domain Socket to use instead of TCP sockets.
    * **local_address** - `Optional[str]` - Local address to connect from. Can
    also be used to connect using a particular address family. Using
    `local_address="0.0.0.0"` will connect using an `AF_INET` address (IPv4),
    while using `local_address="::"` will connect using an `AF_INET6` address
    (IPv6).
    * **retries** - `int` - The maximum number of retries when trying to establish a
    connection.
    * **backend** - `str` - A name indicating which concurrency backend to use.
    """

    def __init__(
        self,
        ssl_context: SSLContext = None,
        max_connections: int = None,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        http2: bool = False,
        uds: str = None,
        local_address: str = None,
        retries: int = 0,
        max_keepalive: int = None,
        backend: Union[AsyncBackend, str] = "auto",
    ):
        if max_keepalive is not None:
            warnings.warn(
                "'max_keepalive' is deprecated. Use 'max_keepalive_connections'.",
                DeprecationWarning,
            )
            max_keepalive_connections = max_keepalive

        if isinstance(backend, str):
            backend = lookup_async_backend(backend)

        self._ssl_context = SSLContext() if ssl_context is None else ssl_context
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._keepalive_expiry = keepalive_expiry
        self._http2 = http2
        self._uds = uds
        self._local_address = local_address
        self._retries = retries
        self._connections: Dict[Origin, Set[AsyncHTTPConnection]] = {}
        self._thread_lock = ThreadLock()
        self._backend = backend
        self._next_keepalive_check = 0.0

        if http2:
            try:
                import h2  # noqa: F401
            except ImportError:
                raise ImportError(
                    "Attempted to use http2=True, but the 'h2' "
                    "package is not installed. Use 'pip install httpcore[http2]'."
                )

    @property
    def _connection_semaphore(self) -> AsyncSemaphore:
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
    def _connection_acquiry_lock(self) -> AsyncLock:
        if not hasattr(self, "_internal_connection_acquiry_lock"):
            self._internal_connection_acquiry_lock = self._backend.create_lock()
        return self._internal_connection_acquiry_lock

    def _create_connection(
        self,
        origin: Tuple[bytes, bytes, int],
    ) -> AsyncHTTPConnection:
        return AsyncHTTPConnection(
            origin=origin,
            http2=self._http2,
            uds=self._uds,
            ssl_context=self._ssl_context,
            local_address=self._local_address,
            retries=self._retries,
            backend=self._backend,
        )

    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        if url[0] not in (b"http", b"https"):
            scheme = url[0].decode("latin-1")
            raise UnsupportedProtocol(f"Unsupported URL protocol {scheme!r}")
        if not url[1]:
            raise LocalProtocolError("Missing hostname in URL.")

        origin = url_to_origin(url)
        ext = {} if ext is None else ext
        timeout = cast(TimeoutDict, ext.get("timeout", {}))

        await self._keepalive_sweep()

        connection: Optional[AsyncHTTPConnection] = None
        while connection is None:
            async with self._connection_acquiry_lock:
                # We get-or-create a connection as an atomic operation, to ensure
                # that HTTP/2 requests issued in close concurrency will end up
                # on the same connection.
                logger.trace("get_connection_from_pool=%r", origin)
                connection = await self._get_connection_from_pool(origin)

                if connection is None:
                    connection = self._create_connection(origin=origin)
                    logger.trace("created connection=%r", connection)
                    await self._add_to_pool(connection, timeout=timeout)
                else:
                    logger.trace("reuse connection=%r", connection)

            try:
                response = await connection.arequest(
                    method, url, headers=headers, stream=stream, ext=ext
                )
            except NewConnectionRequired:
                connection = None
            except Exception:  # noqa: PIE786
                logger.trace("remove from pool connection=%r", connection)
                await self._remove_from_pool(connection)
                raise

        status_code, headers, stream, ext = response
        wrapped_stream = ResponseByteStream(
            stream, connection=connection, callback=self._response_closed
        )
        return status_code, headers, wrapped_stream, ext

    async def _get_connection_from_pool(
        self, origin: Origin
    ) -> Optional[AsyncHTTPConnection]:
        # Determine expired keep alive connections on this origin.
        seen_http11 = False
        pending_connection = None
        reuse_connection = None
        connections_to_close = set()

        for connection in self._connections_for_origin(origin):
            if connection.is_http11:
                seen_http11 = True

            if connection.state == ConnectionState.IDLE:
                if connection.is_socket_readable():
                    # If the socket is readable while the connection is idle (meaning
                    # we don't expect the server to send any data), then the only valid
                    # reason is that the other end has disconnected, which means we
                    # should drop the connection too.
                    # (For a detailed run-through of what a "readable" socket is, and
                    # why this is the best thing for us to do here, see:
                    # https://github.com/encode/httpx/pull/143#issuecomment-515181778)
                    logger.trace("removing dropped idle connection=%r", connection)
                    # IDLE connections that have been dropped should be
                    # removed from the pool.
                    connections_to_close.add(connection)
                    await self._remove_from_pool(connection)
                else:
                    # IDLE connections that are still maintained may
                    # be reused.
                    logger.trace("reusing idle http11 connection=%r", connection)
                    reuse_connection = connection
            elif connection.state == ConnectionState.ACTIVE and connection.is_http2:
                # HTTP/2 connections may be reused.
                logger.trace("reusing active http2 connection=%r", connection)
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
            logger.trace("reusing pending connection=%r", connection)
            reuse_connection = pending_connection

        # Close any dropped connections.
        for connection in connections_to_close:
            await connection.aclose()

        return reuse_connection

    async def _response_closed(self, connection: AsyncHTTPConnection) -> None:
        remove_from_pool = False
        close_connection = False

        if connection.state == ConnectionState.CLOSED:
            remove_from_pool = True
        elif connection.state == ConnectionState.IDLE:
            num_connections = len(self._get_all_connections())
            if (
                self._max_keepalive_connections is not None
                and num_connections > self._max_keepalive_connections
            ):
                remove_from_pool = True
                close_connection = True
            elif self._keepalive_expiry is not None:
                now = await self._backend.time()
                connection.expires_at = now + self._keepalive_expiry

        if remove_from_pool:
            await self._remove_from_pool(connection)

        if close_connection:
            await connection.aclose()

    async def _keepalive_sweep(self) -> None:
        """
        Remove any IDLE connections that have expired past their keep-alive time.
        """
        if self._keepalive_expiry is None:
            return

        now = await self._backend.time()
        if now < self._next_keepalive_check:
            return

        self._next_keepalive_check = now + min(1.0, self._keepalive_expiry)
        connections_to_close = set()

        for connection in self._get_all_connections():
            if (
                connection.state == ConnectionState.IDLE
                and connection.expires_at is not None
                and now >= connection.expires_at
            ):
                connections_to_close.add(connection)
                await self._remove_from_pool(connection)

        for connection in connections_to_close:
            await connection.aclose()

    async def _add_to_pool(
        self, connection: AsyncHTTPConnection, timeout: TimeoutDict
    ) -> None:
        logger.trace("adding connection to pool=%r", connection)
        await self._connection_semaphore.acquire(timeout=timeout.get("pool", None))
        async with self._thread_lock:
            self._connections.setdefault(connection.origin, set())
            self._connections[connection.origin].add(connection)

    async def _remove_from_pool(self, connection: AsyncHTTPConnection) -> None:
        logger.trace("removing connection from pool=%r", connection)
        async with self._thread_lock:
            if connection in self._connections.get(connection.origin, set()):
                await self._connection_semaphore.release()
                self._connections[connection.origin].remove(connection)
                if not self._connections[connection.origin]:
                    del self._connections[connection.origin]

    def _connections_for_origin(self, origin: Origin) -> Set[AsyncHTTPConnection]:
        return set(self._connections.get(origin, set()))

    def _get_all_connections(self) -> Set[AsyncHTTPConnection]:
        connections: Set[AsyncHTTPConnection] = set()
        for connection_set in self._connections.values():
            connections |= connection_set
        return connections

    async def aclose(self) -> None:
        connections = self._get_all_connections()
        for connection in connections:
            await self._remove_from_pool(connection)

        # Close all connections
        for connection in connections:
            await connection.aclose()

    async def get_connection_info(self) -> Dict[str, List[str]]:
        """
        Returns a dict of origin URLs to a list of summary strings for each connection.
        """
        await self._keepalive_sweep()

        stats = {}
        for origin, connections in self._connections.items():
            stats[origin_to_url_string(origin)] = sorted(
                [connection.info() for connection in connections]
            )
        return stats
