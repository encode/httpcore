from ssl import SSLContext
from typing import Tuple

from .._exceptions import ProxyError
from .._types import URL, Headers, Origin, TimeoutDict
from .base import SyncByteStream
from .connection import SyncHTTPConnection
from .connection_pool import SyncConnectionPool, ResponseByteStream


class SyncHTTPProxy(SyncConnectionPool):
    """
    A connection pool for making HTTP requests via an HTTP proxy.

    **Parameters:**

    * **proxy_origin** - `Tuple[bytes, bytes, int]` - The address of the proxy
    service as a 3-tuple of (scheme, host, port).
    * **proxy_headers** - `Optional[List[Tuple[bytes, bytes]]]` - A list of
    proxy headers to include.
    * **proxy_mode** - `str` - A proxy mode to operate in. May be "DEFAULT",
    "FORWARD_ONLY", or "TUNNEL_ONLY".
    * **ssl_context** - `Optional[SSLContext]` - An SSL context to use for
    verifying connections.
    * **max_connections** - `Optional[int]` - The maximum number of concurrent
    connections to allow.
    * **max_keepalive** - `Optional[int]` - The maximum number of connections
    to allow before closing keep-alive connections.
    * **http2** - `bool` - Enable HTTP/2 support.
    """

    def __init__(
        self,
        proxy_origin: Origin,
        proxy_headers: Headers = None,
        proxy_mode: str = "DEFAULT",
        ssl_context: SSLContext = None,
        max_connections: int = None,
        max_keepalive: int = None,
        keepalive_expiry: float = None,
        http2: bool = False,
    ):
        assert proxy_mode in ("DEFAULT", "FORWARD_ONLY", "TUNNEL_ONLY")

        self.proxy_origin = proxy_origin
        self.proxy_headers = [] if proxy_headers is None else proxy_headers
        self.proxy_mode = proxy_mode
        super().__init__(
            ssl_context=ssl_context,
            max_connections=max_connections,
            max_keepalive=max_keepalive,
            keepalive_expiry=keepalive_expiry,
            http2=http2,
        )

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, Headers, SyncByteStream]:
        if self._keepalive_expiry is not None:
            self._keepalive_sweep()

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
            connection = SyncHTTPConnection(
                origin=origin, http2=False, ssl_context=self._ssl_context,
            )
            with self._thread_lock:
                self._connections.setdefault(origin, set())
                self._connections[origin].add(connection)

        # Issue a forwarded proxy request...

        # GET https://www.example.org/path HTTP/1.1
        # [proxy headers]
        # [headers]
        target = b"%b://%b:%d%b" % url
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
            # First, create a connection to the proxy server
            proxy_connection = SyncHTTPConnection(
                origin=self.proxy_origin, http2=False, ssl_context=self._ssl_context,
            )

            # Issue a CONNECT request...

            # CONNECT www.example.org:80 HTTP/1.1
            # [proxy-headers]
            target = b"%b:%d" % (url[1], url[2])
            connect_url = self.proxy_origin + (target,)
            proxy_headers = self._get_tunnel_proxy_headers(headers)
            proxy_response = proxy_connection.request(
                b"CONNECT", connect_url, headers=proxy_headers, timeout=timeout
            )
            proxy_status_code = proxy_response[1]
            proxy_reason_phrase = proxy_response[2]
            proxy_stream = proxy_response[4]

            # Read the response data without closing the socket
            for _ in proxy_stream:
                pass

            # See if the tunnel was successfully established.
            if proxy_status_code < 200 or proxy_status_code > 299:
                msg = "%d %s" % (proxy_status_code, proxy_reason_phrase.decode("ascii"))
                raise ProxyError(msg)

            # The CONNECT request is successful, so we have now SWITCHED PROTOCOLS.
            # This means the proxy connection is now unusable, and we must create
            # a new one for regular requests, making sure to use the same socket to
            # retain the tunnel.
            connection = SyncHTTPConnection(
                origin=origin,
                http2=False,
                ssl_context=self._ssl_context,
                socket=proxy_connection.socket,
            )
            self._add_to_pool(connection)

        # Once the connection has been established we can send requests on
        # it as normal.
        response = connection.request(
            method, url, headers=headers, stream=stream, timeout=timeout,
        )
        wrapped_stream = ResponseByteStream(
            response[4], connection=connection, callback=self._response_closed
        )
        return response[0], response[1], response[2], response[3], wrapped_stream

    def _get_tunnel_proxy_headers(self, request_headers: Headers = None) -> Headers:
        """Returns the headers for the CONNECT request to the tunnel proxy.

        These do not include _all_ the request headers, but we make sure Host
        is present as it's required for any h11 connection. If not in the proxy
        headers we try to pull it from the request headers.

        We also attach `Accept: */*` if not present in the user's proxy headers.
        """
        proxy_headers = []
        should_add_accept_header = True
        should_add_host_header = True
        for header in self.proxy_headers:
            proxy_headers.append(header)
            if header[0] == b"accept":
                should_add_accept_header = False
            if header[0] == b"host":
                should_add_host_header = False

        if should_add_accept_header:
            proxy_headers.append((b"accept", b"*/*"))

        if should_add_host_header and request_headers:
            try:
                host_header = next(h for h in request_headers if h[0] == b"host")
                proxy_headers.append(host_header)
            except StopIteration:
                pass

        return proxy_headers
