from ssl import SSLContext
from typing import Iterator, List, Tuple, Union

import h11

from .._backends.auto import SyncSocketStream
from .._bytestreams import IteratorByteStream, PlainByteStream
from .._exceptions import LocalProtocolError, RemoteProtocolError, map_exceptions
from .._types import URL, Headers, TimeoutDict
from .._utils import get_logger
from .base import SyncByteStream, ConnectionState
from .http import SyncBaseHTTPConnection

H11Event = Union[
    h11.Request,
    h11.Response,
    h11.InformationalResponse,
    h11.Data,
    h11.EndOfMessage,
    h11.ConnectionClosed,
]

logger = get_logger(__name__)


class SyncHTTP11Connection(SyncBaseHTTPConnection):
    READ_NUM_BYTES = 64 * 1024

    def __init__(
        self, socket: SyncSocketStream, ssl_context: SSLContext = None,
    ):
        self.socket = socket
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context

        self.h11_state = h11.Connection(our_role=h11.CLIENT)

        self.state = ConnectionState.ACTIVE

    def __repr__(self) -> str:
        return f"<SyncHTTP11Connection state={self.state}>"

    def info(self) -> str:
        return f"HTTP/1.1, {self.state.name}"

    def get_state(self) -> ConnectionState:
        return self.state

    def mark_as_ready(self) -> None:
        if self.state == ConnectionState.IDLE:
            self.state = ConnectionState.READY

    def request(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: SyncByteStream = None,
        timeout: TimeoutDict = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], SyncByteStream]:
        headers = [] if headers is None else headers
        stream = PlainByteStream(b"") if stream is None else stream
        timeout = {} if timeout is None else timeout

        self.state = ConnectionState.ACTIVE

        self._send_request(method, url, headers, timeout)
        self._send_request_body(stream, timeout)
        (
            http_version,
            status_code,
            reason_phrase,
            headers,
        ) = self._receive_response(timeout)
        response_stream = IteratorByteStream(
            iterator=self._receive_response_data(timeout),
            close_func=self._response_closed,
        )
        return (http_version, status_code, reason_phrase, headers, response_stream)

    def start_tls(
        self, hostname: bytes, timeout: TimeoutDict = None
    ) -> SyncSocketStream:
        timeout = {} if timeout is None else timeout
        self.socket = self.socket.start_tls(hostname, self.ssl_context, timeout)
        return self.socket

    def _send_request(
        self, method: bytes, url: URL, headers: Headers, timeout: TimeoutDict,
    ) -> None:
        """
        Send the request line and headers.
        """
        logger.trace("send_request method=%r url=%r headers=%s", method, url, headers)
        _scheme, _host, _port, target = url
        with map_exceptions({h11.LocalProtocolError: LocalProtocolError}):
            event = h11.Request(method=method, target=target, headers=headers)
        self._send_event(event, timeout)

    def _send_request_body(
        self, stream: SyncByteStream, timeout: TimeoutDict
    ) -> None:
        """
        Send the request body.
        """
        # Send the request body.
        for chunk in stream:
            logger.trace("send_data=Data(<%d bytes>)", len(chunk))
            event = h11.Data(data=chunk)
            self._send_event(event, timeout)

        # Finalize sending the request.
        event = h11.EndOfMessage()
        self._send_event(event, timeout)

    def _send_event(self, event: H11Event, timeout: TimeoutDict) -> None:
        """
        Send a single `h11` event to the network, waiting for the data to
        drain before returning.
        """
        bytes_to_send = self.h11_state.send(event)
        self.socket.write(bytes_to_send, timeout)

    def _receive_response(
        self, timeout: TimeoutDict
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
        self, timeout: TimeoutDict
    ) -> Iterator[bytes]:
        """
        Read the response data from the network.
        """
        while True:
            event = self._receive_event(timeout)
            if isinstance(event, h11.Data):
                logger.trace("receive_event=Data(<%d bytes>)", len(event.data))
                yield bytes(event.data)
            elif isinstance(event, (h11.EndOfMessage, h11.PAUSED)):
                logger.trace("receive_event=%r", event)
                break

    def _receive_event(self, timeout: TimeoutDict) -> H11Event:
        """
        Read a single `h11` event, reading more data from the network if needed.
        """
        while True:
            with map_exceptions({h11.RemoteProtocolError: RemoteProtocolError}):
                event = self.h11_state.next_event()

            if event is h11.NEED_DATA:
                data = self.socket.read(self.READ_NUM_BYTES, timeout)
                self.h11_state.receive_data(data)
            else:
                assert event is not h11.NEED_DATA
                break
        return event

    def _response_closed(self) -> None:
        logger.trace(
            "response_closed our_state=%r their_state=%r",
            self.h11_state.our_state,
            self.h11_state.their_state,
        )
        if (
            self.h11_state.our_state is h11.DONE
            and self.h11_state.their_state is h11.DONE
        ):
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

            self.socket.close()

    def is_connection_dropped(self) -> bool:
        return self.socket.is_connection_dropped()
