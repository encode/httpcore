import enum
from ssl import SSLContext
from typing import (
    Iterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

import h11

from .._backends.auto import SyncSocketStream, SyncBackend
from .._exceptions import ProtocolError, map_exceptions
from .base import SyncByteStream, SyncHTTPTransport

H11Event = Union[
    h11.Request,
    h11.Response,
    h11.InformationalResponse,
    h11.Data,
    h11.EndOfMessage,
    h11.ConnectionClosed,
]


class ConnectionState(enum.IntEnum):
    PENDING = 0
    ACTIVE = 1
    IDLE = 2
    CLOSED = 3


class SyncHTTP11Connection(SyncHTTPTransport):
    READ_NUM_BYTES = 4096

    def __init__(
        self,
        origin: Tuple[bytes, bytes, int],
        socket: SyncSocketStream = None,
        ssl_context: SSLContext = None,
    ):
        self.origin = origin
        self.socket = socket
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context

        self.backend = SyncBackend()
        self.h11_state = h11.Connection(our_role=h11.CLIENT)

        self.state = ConnectionState.PENDING

    def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: SyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        headers = [] if headers is None else headers
        stream = SyncByteStream() if stream is None else stream
        timeout = {} if timeout is None else timeout

        assert url[:3] == self.origin

        if self.state == ConnectionState.PENDING:
            self.socket = self._connect(timeout)
        self.state = ConnectionState.ACTIVE

        self._send_request(method, url, headers, timeout)
        self._send_request_body(stream, timeout)
        (
            http_version,
            status_code,
            reason_phrase,
            headers,
        ) = self._receive_response(timeout)
        stream = SyncByteStream(
            iterator=self._receive_response_data(timeout),
            close_func=self._response_closed,
        )
        return (http_version, status_code, reason_phrase, headers, stream)

    def _start_tls(
        self, hostname: bytes, timeout: Dict[str, Optional[float]] = None
    ):
        assert self.socket is not None
        timeout = {} if timeout is None else timeout
        self.socket = self.socket.start_tls(hostname, self.ssl_context, timeout)

    def _connect(self, timeout: Dict[str, Optional[float]]) -> SyncSocketStream:
        scheme, hostname, port = self.origin
        ssl_context = self.ssl_context if scheme == b"https" else None
        return self.backend.open_tcp_stream(hostname, port, ssl_context, timeout)

    def _send_request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]],
        timeout: Dict[str, Optional[float]],
    ) -> None:
        """
        Send the request line and headers.
        """
        _scheme, _host, _port, target = url
        event = h11.Request(method=method, target=target, headers=headers)
        self._send_event(event, timeout)

    def _send_request_body(
        self, stream: SyncByteStream, timeout: Dict[str, Optional[float]]
    ) -> None:
        """
        Send the request body.
        """
        # Send the request body.
        for chunk in stream:
            event = h11.Data(data=chunk)
            self._send_event(event, timeout)

        # Finalize sending the request.
        event = h11.EndOfMessage()
        self._send_event(event, timeout)

    def _send_event(
        self, event: H11Event, timeout: Dict[str, Optional[float]]
    ) -> None:
        """
        Send a single `h11` event to the network, waiting for the data to
        drain before returning.
        """
        assert self.socket is not None

        bytes_to_send = self.h11_state.send(event)
        self.socket.write(bytes_to_send, timeout)

    def _receive_response(
        self, timeout: Dict[str, Optional[float]]
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]]]:
        """
        Read the response status and headers from the network.
        """
        while True:
            event = self._receive_event(timeout)
            if isinstance(event, h11.Response):
                break
        http_version = b"HTTP/" + event.http_version
        return http_version, event.status_code, event.reason, event.headers

    def _receive_response_data(
        self, timeout: Dict[str, Optional[float]]
    ) -> Iterator[bytes]:
        """
        Read the response data from the network.
        """
        while True:
            event = self._receive_event(timeout)
            if isinstance(event, h11.Data):
                yield bytes(event.data)
            elif isinstance(event, h11.EndOfMessage):
                break

    def _receive_event(self, timeout: Dict[str, Optional[float]]) -> H11Event:
        """
        Read a single `h11` event, reading more data from the network if needed.
        """
        assert self.socket is not None

        while True:
            with map_exceptions({h11.RemoteProtocolError: ProtocolError}):
                event = self.h11_state.next_event()

            if event is h11.NEED_DATA:
                data = self.socket.read(self.READ_NUM_BYTES, timeout)
                self.h11_state.receive_data(data)
            else:
                assert event is not h11.NEED_DATA
                break
        return event

    def _response_closed(self) -> None:
        if self.h11_state.our_state is h11.DONE:
            self.h11_state.start_next_cycle()
            self.state = ConnectionState.IDLE
        else:
            self.close()

    def close(self) -> None:
        if self.state != ConnectionState.CLOSED:
            self.state = ConnectionState.CLOSED

            if self.h11_state.our_state is h11.MUST_CLOSE:
                event = h11.ConnectionClosed()
                self.h11_state.send(event)

            if self.socket is not None:
                self.socket.close()

    def is_connection_dropped(self) -> bool:
        return self.socket is not None and self.socket.is_connection_dropped()
