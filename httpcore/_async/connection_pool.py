from ssl import SSLContext
from typing import Dict, List, Optional, Set, Tuple

from .base import AsyncByteStream, AsyncHTTPTransport
from .http11 import AsyncHTTP11Connection


class AsyncConnectionPool(AsyncHTTPTransport):
    """
    A connection pool for making HTTP requests.

    **Parameters:**

    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
    * **max_keepalive** - `Optional[int]` - The maximum number of keep alive connections to maintain in the pool.
    * **max_connections** - `Optional[int]` - The maximum number of HTTP connections to allow. Attempting to establish a connection beyond this limit will block for the duration specified in the pool acquiry timeout.
    """

    def __init__(
        self,
        ssl_context: SSLContext = None,
        max_keepalive: int = None,
        max_connections: int = None,
    ):
        self.ssl_context = ssl_context
        self.max_keepalive = max_keepalive
        self.max_connections = max_connections
        self.connections = {}  # type: Dict[Tuple[bytes, bytes, int], Set[AsyncHTTP11Connection]]

    async def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: AsyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream]:
        origin = url[:3]
        connection = AsyncHTTP11Connection(origin=origin, ssl_context=self.ssl_context, request_finished=self.request_finished)
        self.connections.setdefault(origin, set())
        self.connections[origin].add(connection)
        return await connection.request(
            method, url, headers=headers, stream=stream, timeout=timeout
        )

    async def request_finished(self, connection: AsyncHTTP11Connection):
        if connection.socket is None:
            self.connections[connection.origin].remove(connection)
            if not self.connections[connection.origin]:
                self.connections.pop(connection.origin)

    async def close(self) -> None:
        for connections in list(self.connections.values()):
            for connection in list(connections):
                connection.request_finished = None
                await connection.close()
        self.connections.clear()


class AsyncHTTPProxy(AsyncHTTPTransport):
    """
    A connection pool for making HTTP requests via an HTTP proxy.

    **Parameters:**

    * **proxy_url** - `Tuple[bytes, bytes, int, bytes]` - The URL of the proxy service as a 4-tuple of (scheme, host, port, path).
    * **proxy_headers** - `Optional[List[Tuple[bytes, bytes]]]` - A list of proxy headers to include.
    * **proxy_mode** - `Optional[str]` - A proxy mode to operate in. May be "DEFAULT", "FORWARD_ONLY", or "TUNNEL_ONLY".
    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
    * **max_keepalive** - `Optional[int]` - The maximum number of keep alive connections to maintain in the pool.
    * **max_connections** - `Optional[int]` - The maximum number of HTTP connections to allow. Attempting to establish a connection beyond this limit will block for the duration specified in the pool acquiry timeout.
    """

    def __init__(
        self,
        proxy_url: Tuple[bytes, bytes, int, bytes],
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        proxy_mode: str = None,
        ssl_context: SSLContext = None,
        max_keepalive: int = None,
        max_connections: int = None,
    ):
        pass

    async def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: AsyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream]:
        raise NotImplementedError()

    async def close(self) -> None:
        pass
