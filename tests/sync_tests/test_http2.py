import collections

import h2.config
import h2.connection
import pytest

import httpcore
from httpcore._backends.sync import (
    SyncBackend,
    SyncLock,
    SyncSemaphore,
    SyncSocketStream,
)


class MockStream(SyncSocketStream):
    def __init__(self, http_buffer, disconnect):
        self.read_buffer = collections.deque(http_buffer)
        self.disconnect = disconnect

    def get_http_version(self) -> str:
        return "HTTP/2"

    def write(self, data, timeout):
        pass

    def read(self, n, timeout):
        return self.read_buffer.popleft()

    def close(self):
        pass

    def is_readable(self):
        return self.disconnect


class MockLock(SyncLock):
    def release(self):
        pass

    def acquire(self):
        pass


class MockSemaphore(SyncSemaphore):
    def __init__(self):
        pass

    def acquire(self, timeout=None):
        pass

    def release(self):
        pass


class MockBackend(SyncBackend):
    def __init__(self, http_buffer, disconnect=False):
        self.http_buffer = http_buffer
        self.disconnect = disconnect

    def open_tcp_stream(
        self, hostname, port, ssl_context, timeout, *, local_address
    ):
        return MockStream(self.http_buffer, self.disconnect)

    def create_lock(self):
        return MockLock()

    def create_semaphore(self, max_value, exc_class):
        return MockSemaphore()


class HTTP2BytesGenerator:
    def __init__(self):
        self.client_config = h2.config.H2Configuration(client_side=True)
        self.client_conn = h2.connection.H2Connection(config=self.client_config)
        self.server_config = h2.config.H2Configuration(client_side=False)
        self.server_conn = h2.connection.H2Connection(config=self.server_config)
        self.initialized = False

    def get_server_bytes(
        self, request_headers, request_data, response_headers, response_data
    ):
        if not self.initialized:
            self.client_conn.initiate_connection()
            self.server_conn.initiate_connection()
            self.initialized = True

        # Feed the request events to the client-side state machine
        client_stream_id = self.client_conn.get_next_available_stream_id()
        self.client_conn.send_headers(client_stream_id, headers=request_headers)
        self.client_conn.send_data(client_stream_id, data=request_data, end_stream=True)

        # Determine the bytes that're sent out the client side, and feed them
        # into the server-side state machine to get it into the correct state.
        client_bytes = self.client_conn.data_to_send()
        events = self.server_conn.receive_data(client_bytes)
        server_stream_id = [
            event.stream_id
            for event in events
            if isinstance(event, h2.events.RequestReceived)
        ][0]

        # Feed the response events to the server-side state machine
        self.server_conn.send_headers(server_stream_id, headers=response_headers)
        self.server_conn.send_data(
            server_stream_id, data=response_data, end_stream=True
        )

        return self.server_conn.data_to_send()



def test_get_request() -> None:
    bytes_generator = HTTP2BytesGenerator()
    http_buffer = [
        bytes_generator.get_server_bytes(
            request_headers=[
                (b":method", b"GET"),
                (b":authority", b"www.example.com"),
                (b":scheme", b"https"),
                (b":path", "/"),
            ],
            request_data=b"",
            response_headers=[
                (b":status", b"200"),
                (b"date", b"Sat, 06 Oct 2049 12:34:56 GMT"),
                (b"server", b"Apache"),
                (b"content-length", b"13"),
                (b"content-type", b"text/plain"),
            ],
            response_data=b"Hello, world.",
        ),
        bytes_generator.get_server_bytes(
            request_headers=[
                (b":method", b"GET"),
                (b":authority", b"www.example.com"),
                (b":scheme", b"https"),
                (b":path", "/"),
            ],
            request_data=b"",
            response_headers=[
                (b":status", b"200"),
                (b"date", b"Sat, 06 Oct 2049 12:34:56 GMT"),
                (b"server", b"Apache"),
                (b"content-length", b"13"),
                (b"content-type", b"text/plain"),
            ],
            response_data=b"Hello, world.",
        ),
    ]
    backend = MockBackend(http_buffer=http_buffer)

    with httpcore.SyncConnectionPool(http2=True, backend=backend) as http:
        # We're sending a request with a standard keep-alive connection, so
        # it will remain in the pool once we've sent the request.
        response = http.handle_request(
            method=b"GET",
            url=(b"https", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = stream.read()
        assert status_code == 200
        assert body == b"Hello, world."
        assert http.get_connection_info() == {
            "https://example.org": ["HTTP/2, IDLE, 0 streams"]
        }

        # The second HTTP request will go out over the same connection.
        response = http.handle_request(
            method=b"GET",
            url=(b"https", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org")],
            stream=httpcore.ByteStream(b""),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = stream.read()
        assert status_code == 200
        assert body == b"Hello, world."
        assert http.get_connection_info() == {
            "https://example.org": ["HTTP/2, IDLE, 0 streams"]
        }



def test_post_request() -> None:
    bytes_generator = HTTP2BytesGenerator()
    bytes_to_send = bytes_generator.get_server_bytes(
        request_headers=[
            (b":method", b"POST"),
            (b":authority", b"www.example.com"),
            (b":scheme", b"https"),
            (b":path", "/"),
            (b"content-length", b"13"),
        ],
        request_data=b"Hello, world.",
        response_headers=[
            (b":status", b"200"),
            (b"date", b"Sat, 06 Oct 2049 12:34:56 GMT"),
            (b"server", b"Apache"),
            (b"content-length", b"13"),
            (b"content-type", b"text/plain"),
        ],
        response_data=b"Hello, world.",
    )
    backend = MockBackend(http_buffer=[bytes_to_send])

    with httpcore.SyncConnectionPool(http2=True, backend=backend) as http:
        # We're sending a request with a standard keep-alive connection, so
        # it will remain in the pool once we've sent the request.
        response = http.handle_request(
            method=b"POST",
            url=(b"https", b"example.org", None, b"/"),
            headers=[(b"Host", b"example.org"), (b"Content-length", b"13")],
            stream=httpcore.ByteStream(b"Hello, world."),
            extensions={},
        )
        status_code, headers, stream, extensions = response
        body = stream.read()
        assert status_code == 200
        assert body == b"Hello, world."
        assert http.get_connection_info() == {
            "https://example.org": ["HTTP/2, IDLE, 0 streams"]
        }



def test_request_with_missing_host_header() -> None:
    backend = MockBackend(http_buffer=[])

    server_config = h2.config.H2Configuration(client_side=False)
    server_conn = h2.connection.H2Connection(config=server_config)
    server_conn.initiate_connection()
    backend = MockBackend(http_buffer=[server_conn.data_to_send()])

    with httpcore.SyncConnectionPool(backend=backend) as http:
        with pytest.raises(httpcore.LocalProtocolError) as excinfo:
            http.handle_request(
                method=b"GET",
                url=(b"http", b"example.org", None, b"/"),
                headers=[],
                stream=httpcore.ByteStream(b""),
                extensions={},
            )
        assert str(excinfo.value) == "Missing mandatory Host: header"


#         # This second request will go out over the same connection.
#         response = http.handle_request(
#             method=b"GET",
#             url=(b"http", b"example.org", None, b"/"),
#             headers=[(b"Host", b"example.org")],
#             stream=httpcore.ByteStream(b""),
#             extensions={},
#         )
#         status_code, headers, stream, extensions = response
#         body = stream.read()
#         assert status_code == 200
#         assert body == b"Hello, world."
#         assert http.get_connection_info() == {
#             "http://example.org": ["HTTP/1.1, IDLE"]
#         }
#
#
# @pytest.mark.trio
# def test_get_request_with_connection_close_header() -> None:
#     backend = MockBackend(
#         http_buffer=[
#             b"HTTP/1.1 200 OK\r\n",
#             b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
#             b"Server: Apache\r\n",
#             b"Content-Length: 13\r\n",
#             b"Content-Type: text/plain\r\n",
#             b"\r\n",
#             b"Hello, world.",
#             b"",  # Terminate the connection.
#         ]
#     )
#
#     with httpcore.SyncConnectionPool(backend=backend) as http:
#         # We're sending a request with 'Connection: close', so the connection
#         # does not remain in the pool once we've sent the request.
#         response = http.handle_request(
#             method=b"GET",
#             url=(b"http", b"example.org", None, b"/"),
#             headers=[(b"Host", b"example.org"), (b"Connection", b"close")],
#             stream=httpcore.ByteStream(b""),
#             extensions={},
#         )
#         status_code, headers, stream, extensions = response
#         body = stream.read()
#         assert status_code == 200
#         assert body == b"Hello, world."
#         assert http.get_connection_info() == {}
#
#         # The second request will go out over a new connection.
#         response = http.handle_request(
#             method=b"GET",
#             url=(b"http", b"example.org", None, b"/"),
#             headers=[(b"Host", b"example.org"), (b"Connection", b"close")],
#             stream=httpcore.ByteStream(b""),
#             extensions={},
#         )
#         status_code, headers, stream, extensions = response
#         body = stream.read()
#         assert status_code == 200
#         assert body == b"Hello, world."
#         assert http.get_connection_info() == {}
#
#
# @pytest.mark.trio
# def test_get_request_with_socket_disconnect_between_requests() -> None:
#     backend = MockBackend(
#         http_buffer=[
#             b"HTTP/1.1 200 OK\r\n",
#             b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
#             b"Server: Apache\r\n",
#             b"Content-Length: 13\r\n",
#             b"Content-Type: text/plain\r\n",
#             b"\r\n",
#             b"Hello, world.",
#         ],
#         disconnect=True,
#     )
#
#     with httpcore.SyncConnectionPool(backend=backend) as http:
#         # Send an initial request. We're using a standard keep-alive
#         # connection, so the connection remains in the pool after completion.
#         response = http.handle_request(
#             method=b"GET",
#             url=(b"http", b"example.org", None, b"/"),
#             headers=[(b"Host", b"example.org")],
#             stream=httpcore.ByteStream(b""),
#             extensions={},
#         )
#         status_code, headers, stream, extensions = response
#         body = stream.read()
#         assert status_code == 200
#         assert body == b"Hello, world."
#         assert http.get_connection_info() == {
#             "http://example.org": ["HTTP/1.1, IDLE"]
#         }
#
#         # On sending this second request, at the point of pool re-acquiry the
#         # socket indicates that it has disconnected, and we'll send the request
#         # over a new connection.
#         response = http.handle_request(
#             method=b"GET",
#             url=(b"http", b"example.org", None, b"/"),
#             headers=[(b"Host", b"example.org")],
#             stream=httpcore.ByteStream(b""),
#             extensions={},
#         )
#         status_code, headers, stream, extensions = response
#         body = stream.read()
#         assert status_code == 200
#         assert body == b"Hello, world."
#         assert http.get_connection_info() == {
#             "http://example.org": ["HTTP/1.1, IDLE"]
#         }
#
#
# @pytest.mark.trio
# def test_get_request_with_unclean_close_after_first_request() -> None:
#     backend = MockBackend(
#         http_buffer=[
#             b"HTTP/1.1 200 OK\r\n",
#             b"Date: Sat, 06 Oct 2049 12:34:56 GMT\r\n",
#             b"Server: Apache\r\n",
#             b"Content-Length: 13\r\n",
#             b"Content-Type: text/plain\r\n",
#             b"\r\n",
#             b"Hello, world.",
#             b"",  # Terminate the connection.
#         ],
#     )
#
#     with httpcore.SyncConnectionPool(backend=backend) as http:
#         # Send an initial request. We're using a standard keep-alive
#         # connection, so the connection remains in the pool after completion.
#         response = http.handle_request(
#             method=b"GET",
#             url=(b"http", b"example.org", None, b"/"),
#             headers=[(b"Host", b"example.org")],
#             stream=httpcore.ByteStream(b""),
#             extensions={},
#         )
#         status_code, headers, stream, extensions = response
#         body = stream.read()
#         assert status_code == 200
#         assert body == b"Hello, world."
#         assert http.get_connection_info() == {
#             "http://example.org": ["HTTP/1.1, IDLE"]
#         }
#
#         # At this point we successfully write another request, but the socket
#         # read returns `b""`, indicating a premature close.
#         with pytest.raises(httpcore.RemoteProtocolError) as excinfo:
#             http.handle_request(
#                 method=b"GET",
#                 url=(b"http", b"example.org", None, b"/"),
#                 headers=[(b"Host", b"example.org")],
#                 stream=httpcore.ByteStream(b""),
#                 extensions={},
#             )
#         assert str(excinfo.value) == "Server disconnected without sending a response."
