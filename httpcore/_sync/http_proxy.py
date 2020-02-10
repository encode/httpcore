from ssl import SSLContext
from typing import Dict, List, Optional, Tuple

from .._exceptions import ProxyError
from .._url import normalize_url, url_as_bytes
from .base import SyncByteStream, SyncHTTPTransport
from .connection_pool import SyncConnectionPool, ResponseByteStream
from .http11 import SyncHTTP11Connection

Origin = Tuple[bytes, bytes, int]
URL = Tuple[bytes, bytes, int, bytes]
Headers = List[Tuple[bytes, bytes]]
TimeoutDict = Dict[str, Optional[float]]


def read_body(stream: SyncByteStream) -> bytes:
    try:
        return b"".join([chunk for chunk in stream])
    finally:
        stream.close()


class SyncHTTPProxy(SyncConnectionPool):
    """
    A connection pool for making HTTP requests via an HTTP proxy.

    **Parameters:**

    * **proxy_origin** - `Tuple[bytes, bytes, int]` - The address of the proxy service as a 3-tuple of (scheme, host, port).
    * **proxy_headers** - `Optional[List[Tuple[bytes, bytes]]]` - A list of proxy headers to include.
    * **proxy_mode** - `Optional[str]` - A proxy mode to operate in. May be "DEFAULT", "FORWARD_ONLY", or "TUNNEL_ONLY".
    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for verifying connections.
    """

    def __init__(
        self,
        proxy_origin: Origin,
        proxy_headers: Headers = None,
        proxy_mode: str = "DEFAULT",
        ssl_context: SSLContext = None,
    ):
        assert proxy_mode in ("DEFAULT", "FORWARD_ONLY", "TUNNEL_ONLY")

        self.proxy_origin = normalize_url(proxy_origin + (b"/",))[:3]
        self.proxy_headers = [] if proxy_headers is None else proxy_headers
        self.proxy_mode = proxy_mode
        super().__init__(ssl_context=ssl_context)

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, Headers, SyncByteStream]:
        url = normalize_url(url)

        if (
            self.proxy_mode == "DEFAULT" and url[0] == b"http"
        ) or self.proxy_mode == "FORWARD_ONLY":
            # By default HTTP requests should be forwarded.
            return self._forward_request(
                method, url, headers=headers, stream=stream, timeout=timeout
            )
        else:
            # By default HTTPS should be tunnelled.
            return self._tunnel_request(
                method, url, headers=headers, stream=stream, timeout=timeout
            )

    def _forward_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, Headers, SyncByteStream]:
        """
        Forwarded proxy requests include the entire URL as the HTTP target,
        rather than just the path.
        """
        origin = self.proxy_origin
        connection = self._get_connection_from_pool(origin)

        if connection is None:
            connection = SyncHTTP11Connection(
                origin=origin, ssl_context=self.ssl_context,
            )
            with self.thread_lock:
                self.connections.setdefault(origin, set())
                self.connections[origin].add(connection)

        # Issue a forwarded proxy request...

        # GET https://www.example.org/path HTTP/1.1
        # [proxy headers]
        # [headers]
        target = url_as_bytes(url)
        url = self.proxy_origin + (target,)
        headers = self.proxy_headers + ([] if headers is None else headers)

        response = connection.request(
            method, url, headers=headers, stream=stream, timeout=timeout
        )
        wrapped_stream = ResponseByteStream(
            response[4], connection=connection, callback=self._response_closed
        )
        return response[0], response[1], response[2], response[3], wrapped_stream

    def _tunnel_request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, Headers, SyncByteStream]:
        """
        Tunnelled proxy requests require an initial CONNECT request to
        establish the connection, and then send regular requests.
        """
        origin = url[:3]
        connection = self._get_connection_from_pool(origin)

        if connection is None:
            connection = SyncHTTP11Connection(
                origin=origin, ssl_context=self.ssl_context,
            )
            with self.thread_lock:
                self.connections.setdefault(origin, set())
                self.connections[origin].add(connection)

            # Establish the connection by issuing a CONNECT request...

            # CONNECT www.example.org:80 HTTP/1.1
            # [proxy-headers]
            target = b"%b:%d" % (url[1], url[2])
            connect_url = self.proxy_origin + (target,)
            connect_headers = self.proxy_headers
            proxy_response = connection.request(
                b"CONNECT", connect_url, headers=connect_headers, timeout=timeout
            )
            proxy_status_code = proxy_response[1]
            proxy_reason_phrase = proxy_response[2]
            proxy_stream = proxy_response[4]

            # Ingest any request body.
            read_body(proxy_stream)

            # If the proxy responds with an error, then drop the connection
            # from the pool, and raise an exception.
            if proxy_status_code < 200 or proxy_status_code > 299:
                with self.thread_lock:
                    self.connections[connection.origin].remove(connection)
                    if not self.connections[connection.origin]:
                        del self.connections[connection.origin]
                msg = "%d %s" % (
                    proxy_status_code,
                    proxy_reason_phrase.decode("latin-1"),
                )
                raise ProxyError(msg)

            # Upgrade to TLS.
            connection._start_tls(target, timeout)

        # Once the connection has been established we can send requests on
        # it as normal.
        response = connection.request(
            method, url, headers=headers, stream=stream, timeout=timeout
        )
        wrapped_stream = ResponseByteStream(
            response[4], connection=connection, callback=self._response_closed
        )
        return response[0], response[1], response[2], response[3], wrapped_stream
