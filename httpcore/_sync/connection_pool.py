from ssl import SSLContext
from typing import Callable, Dict, List, Optional, Set, Tuple

from .._threadlock import ThreadLock
from .base import SyncByteStream, SyncHTTPTransport
from .http11 import SyncHTTP11Connection, ConnectionState

Origin = Tuple[bytes, bytes, int]
URL = Tuple[bytes, bytes, int, bytes]
Headers = List[Tuple[bytes, bytes]]


class ResponseByteStream(SyncByteStream):
    def __init__(
        self,
        stream: SyncByteStream,
        connection: SyncHTTP11Connection,
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
            # This will be a call to `SyncHTTP11Connection._response_closed()``.
            self.stream.close()
        finally:
            #  Call the connection pool close callback.
            # This will be a call to `SyncConnectionPool._response_closed()``.
            self.callback(self.connection)


class SyncConnectionPool(SyncHTTPTransport):
    """
    A connection pool for making HTTP requests.

    **Parameters:**

    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
    """

    def __init__(
        self, ssl_context: SSLContext = None,
    ):
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context
        self.connections: Dict[Origin, Set[SyncHTTP11Connection]] = {}
        self.thread_lock = ThreadLock()

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, Headers, SyncByteStream]:
        origin = url[:3]

        # Determine expired keep alive connections on this origin.
        reuse_connection = None
        connections_to_close = set()

        with self.thread_lock:
            if origin in self.connections:
                connections = self.connections[origin]
                for connection in list(connections):
                    if connection.state == ConnectionState.IDLE:
                        if connection.is_connection_dropped():
                            connections_to_close.add(connection)
                            connections.remove(connection)
                        else:
                            reuse_connection = connection

                if not connections:
                    del self.connections[origin]

            if reuse_connection is not None:
                reuse_connection.state = ConnectionState.ACTIVE

        # Close any expired keep alive connections.
        for connection in connections_to_close:
            connection.close()

        # Either reuse an unexpired keep alive connection, or create a new one.
        if reuse_connection is not None:
            connection = reuse_connection
        else:
            connection = SyncHTTP11Connection(
                origin=origin, ssl_context=self.ssl_context,
            )
            with self.thread_lock:
                self.connections.setdefault(origin, set())
                self.connections[origin].add(connection)

        response = connection.request(
            method, url, headers=headers, stream=stream, timeout=timeout
        )
        (http_version, status_code, reason_phrase, headers, stream,) = response
        stream = ResponseByteStream(
            stream, connection=connection, callback=self._response_closed
        )
        return http_version, status_code, reason_phrase, headers, stream

    def _response_closed(self, connection: SyncHTTP11Connection):
        with self.thread_lock:
            if connection.state == ConnectionState.CLOSED:
                self.connections[connection.origin].remove(connection)
                if not self.connections[connection.origin]:
                    del self.connections[connection.origin]

    def close(self) -> None:
        connections_to_close = set()

        with self.thread_lock:
            for connection_set in self.connections.values():
                connections_to_close.update(connection_set)
            self.connections.clear()

        # Close all connections
        for connection in connections_to_close:
            connection.close()


# class SyncHTTPProxy(SyncHTTPTransport):
#     """
#     A connection pool for making HTTP requests via an HTTP proxy.
#
#     **Parameters:**
#
#     * **proxy_url** - `Tuple[bytes, bytes, int, bytes]` - The URL of the proxy service as a 4-tuple of (scheme, host, port, path).
#     * **proxy_headers** - `Optional[List[Tuple[bytes, bytes]]]` - A list of proxy headers to include.
#     * **proxy_mode** - `Optional[str]` - A proxy mode to operate in. May be "DEFAULT", "FORWARD_ONLY", or "TUNNEL_ONLY".
#     * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
#     * **max_keepalive** - `Optional[int]` - The maximum number of keep alive connections to maintain in the pool.
#     * **max_connections** - `Optional[int]` - The maximum number of HTTP connections to allow. Attempting to establish a connection beyond this limit will block for the duration specified in the pool acquiry timeout.
#     """
#
#     def __init__(
#         self,
#         proxy_url: Tuple[bytes, bytes, int, bytes],
#         proxy_headers: List[Tuple[bytes, bytes]] = None,
#         proxy_mode: str = None,
#         ssl_context: SSLContext = None,
#         max_keepalive: int = None,
#         max_connections: int = None,
#     ):
#         pass
#
#     def request(
#         self,
#         method: bytes,
#         url: Tuple[bytes, bytes, int, bytes],
#         headers: List[Tuple[bytes, bytes]] = None,
#         stream: SyncByteStream = None,
#         timeout: Dict[str, Optional[float]] = None,
#     ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
#         raise NotImplementedError()
#
#     def close(self) -> None:
#         pass
