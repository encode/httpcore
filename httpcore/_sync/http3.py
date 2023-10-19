import enum
import logging
import ssl
import time
import types
import typing
from time import monotonic

from aioquic.h3 import events as h3_events, exceptions as h3_exceptions
from aioquic.h3.connection import H3Connection
from aioquic.quic import events as quic_events
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicConnectionState

from .._backends.base import NetworkStream
from .._exceptions import (
    ConnectionNotAvailable,
    LocalProtocolError,
    RemoteProtocolError,
)
from .._models import Origin, Request, Response
from .._synchronization import Lock, ShieldCancellation
from .._trace import Trace
from .interfaces import ConnectionInterface

logger = logging.getLogger("httpcore.http3")


def has_body_headers(request: Request) -> bool:
    return any(
        k.lower() == b"content-length" or k.lower() == b"transfer-encoding"
        for k, v in request.headers
    )


class HTTPConnectionState(enum.IntEnum):
    ACTIVE = 1
    IDLE = 2
    CLOSED = 3


class HTTP3Connection(ConnectionInterface):
    READ_NUM_BYTES = 64 * 1024

    def __init__(
        self,
        origin: Origin,
        stream: NetworkStream,
        keepalive_expiry: typing.Optional[float] = None,
    ):
        self._origin = origin
        self._network_stream = stream
        self._keepalive_expiry: typing.Optional[float] = keepalive_expiry
        CONFIG = QuicConfiguration(
            alpn_protocols=["h3", "h3-32", "h3-31", "h3-30", "h3-29"],
            is_client=True,
            verify_mode=ssl.CERT_NONE,
        )
        CONFIG.server_name = origin.host.decode()
        self._quic_conn = QuicConnection(configuration=CONFIG)
        self._h3_state = H3Connection(quic=self._quic_conn)
        self._state = HTTPConnectionState.IDLE
        self._expire_at: typing.Optional[float] = None
        self._request_count = 0
        self._state_lock = Lock()
        self._read_lock = Lock()
        self._write_lock = Lock()
        self._handshake_lock = Lock()
        self._handshake_done = False
        self._sent_connection_init = False
        self._used_all_stream_ids = False
        self._connection_error = False

        # Mapping from stream ID to response stream events.
        self._events: typing.Dict[
            int,
            typing.Union[
                h3_events.ResponseReceived,
                h3_events.DataReceived,
                quic_events.StreamReset,
            ],
        ] = {}

        # Connection terminated events are stored as state since
        # we need to handle them for all streams.
        self._connection_terminated: typing.Optional[
            quic_events.ConnectionTerminated
        ] = None

        self._read_exception: typing.Optional[Exception] = None
        self._write_exception: typing.Optional[Exception] = None

    def handle_request(self, request: Request) -> Response:
        if not self.can_handle_request(request.url.origin):
            # This cannot occur in normal operation, since the connection pool
            # will only send requests on connections that handle them.
            # It's in place simply for resilience as a guard against incorrect
            # usage, for anyone working directly with httpcore connections.
            raise RuntimeError(
                f"Attempted to send request to {request.url.origin} on connection "
                f"to {self._origin}"
            )

        with self._state_lock:
            if self._state in (HTTPConnectionState.ACTIVE, HTTPConnectionState.IDLE):
                self._request_count += 1
                self._expire_at = None
                self._state = HTTPConnectionState.ACTIVE
            else:
                raise ConnectionNotAvailable()

        with self._handshake_lock:
            if not self._handshake_done:
                self._do_handshake(request)

        try:
            stream_id = self._quic_conn.get_next_available_stream_id()
            self._events[stream_id] = []
        except BaseException:  # pragma: nocover
            assert False, "Unexpected exception"

        try:
            kwargs = {"request": request, "stream_id": stream_id}
            with Trace("send_request_headers", logger, request, kwargs):
                self._send_request_headers(request=request, stream_id=stream_id)
            with Trace("send_request_body", logger, request, kwargs):
                self._send_request_body(request=request, stream_id=stream_id)
            with Trace(
                "receive_response_headers", logger, request, kwargs
            ) as trace:
                status, headers, stream_ended = self._receive_response(
                    request=request, stream_id=stream_id
                )
                trace.return_value = (status, headers)

            return Response(
                status=status,
                headers=headers,
                content=HTTP3ConnectionByteStream(
                    self, request, stream_id=stream_id, is_empty=stream_ended
                ),
                extensions={
                    "http_version": b"HTTP/3",
                    "network_stream": self._network_stream,
                    "stream_id": stream_id,
                },
            )
        except BaseException as exc:  # noqa: PIE786
            with ShieldCancellation():
                kwargs = {"stream_id": stream_id}
                with Trace("response_closed", logger, request, kwargs):
                    self._response_closed(stream_id=stream_id)

            if isinstance(exc, h3_exceptions.H3Error):
                if self._connection_terminated:  # pragma: nocover
                    raise RemoteProtocolError(self._connection_terminated)
                raise LocalProtocolError(exc)  # pragma: nocover

            raise exc

    # Sending the request...

    def _do_handshake(self, request: Request) -> None:
        assert hasattr(self._network_stream, "_addr")
        self._quic_conn.connect(addr=self._network_stream._addr, now=monotonic())
        while not self._handshake_done:
            self._write_outgoing_data(request)
            self._read_incoming_data(request)

    def _send_request_headers(self, request: Request, stream_id: int) -> None:
        """
        Send the request headers to a given stream ID.
        """
        end_stream = not has_body_headers(request)

        # In HTTP/3 the ':authority' pseudo-header is used instead of 'Host'.
        # In order to gracefully handle HTTP/1.1 and HTTP/3 we always require
        # HTTP/1.1 style headers, and map them appropriately if we end up on
        # an HTTP/3 connection.
        authority = [v for k, v in request.headers if k.lower() == b"host"][0]

        headers = [
            (b":method", request.method),
            (b":authority", authority),
            (b":scheme", request.url.scheme),
            (b":path", request.url.target),
        ] + [
            (k.lower(), v)
            for k, v in request.headers
            if k.lower()
            not in (
                b"host",
                b"transfer-encoding",
            )
        ]

        self._h3_state.send_headers(stream_id, headers, end_stream=end_stream)
        self._write_outgoing_data(request)

    def _send_request_body(self, request: Request, stream_id: int) -> None:
        """
        Iterate over the request body sending it to a given stream ID.
        """
        if not has_body_headers(request):
            return

        assert isinstance(request.stream, typing.Iterable)
        for data in request.stream:
            self._send_stream_data(request, stream_id, data)
        self._send_end_stream(request, stream_id)

    def _send_stream_data(
        self, request: Request, stream_id: int, data: bytes
    ) -> None:
        """
        Send a single chunk of data in one or more data frames.
        """
        self._h3_state.send_data(stream_id=stream_id, data=data, end_stream=False)
        self._write_outgoing_data(request)

    def _send_end_stream(self, request: Request, stream_id: int) -> None:
        """
        Send an empty data frame on on a given stream ID with the END_STREAM flag set.
        """
        self._h3_state.send_data(stream_id=stream_id, data=b"", end_stream=True)
        self._write_outgoing_data(request)

    # Receiving the response...

    def _receive_response(
        self, request: Request, stream_id: int
    ) -> typing.Tuple[int, typing.List[typing.Tuple[bytes, bytes]]]:
        """
        Return the response status code and headers for a given stream ID.
        """
        while True:
            event = self._receive_stream_event(request, stream_id)
            if isinstance(event, h3_events.HeadersReceived):
                break

        status_code = 200
        headers = []
        for k, v in event.headers:
            if k == b":status":
                status_code = int(v.decode("ascii", errors="ignore"))
            elif not k.startswith(b":"):
                headers.append((k, v))

        return (status_code, headers, event.stream_ended)

    def _receive_response_body(
        self, request: Request, stream_id: int
    ) -> typing.Iterator[bytes]:
        """
        Iterator that returns the bytes of the response body for a given stream ID.
        """
        while True:
            event = self._receive_stream_event(request, stream_id)
            if isinstance(event, h3_events.DataReceived):
                if event.stream_ended:
                    break

                self._write_outgoing_data(request)
                yield event.data

    def _receive_stream_event(
        self, request: Request, stream_id: int
    ) -> typing.Union[h3_events.HeadersReceived, h3_events.DatagramReceived]:
        """
        Return the next available event for a given stream ID.

        Will read more data from the network if required.
        """
        while not self._events.get(stream_id):
            self._receive_events(request, stream_id)
        event = self._events[stream_id].pop(0)
        if isinstance(event, quic_events.StreamReset):
            raise RemoteProtocolError(event)
        return event

    def _receive_events(
        self, request: Request, stream_id: typing.Optional[int] = None
    ) -> None:
        """
        Read some data from the network until we see one or more events
        for a given stream ID.
        """

        with self._read_lock:
            if self._connection_terminated is not None:
                raise RemoteProtocolError(self._connection_terminated)

            # This conditional is a bit icky. We don't want to block reading if we've
            # actually got an event to return for a given stream. We need to do that
            # check *within* the atomic read lock. Though it also need to be optional,
            # because when we call it from `_wait_for_outgoing_flow` we *do* want to
            # block until we've available flow control, event when we have events
            # pending for the stream ID we're attempting to send on.
            if stream_id is None or not self._events.get(stream_id):
                events = self._read_incoming_data(request)
                for event in events:
                    if isinstance(
                        event,
                        (
                            h3_events.HeadersReceived,
                            h3_events.DataReceived,
                        ),
                    ):
                        if event.stream_id in self._events:
                            self._events[event.stream_id].append(event)

                    elif isinstance(event, quic_events.ConnectionTerminated):
                        self._connection_terminated = event

        self._write_outgoing_data(request)

    def _response_closed(self, stream_id: int) -> None:
        del self._events[stream_id]
        with self._state_lock:
            if self._connection_terminated and not self._events:
                self.close()

            elif self._state == HTTPConnectionState.ACTIVE and not self._events:
                self._state = HTTPConnectionState.IDLE
                if self._keepalive_expiry is not None:
                    now = time.monotonic()
                    self._expire_at = now + self._keepalive_expiry
                if self._used_all_stream_ids:  # pragma: nocover
                    self.close()

    def close(self) -> None:
        # Note that this method unilaterally closes the connection, and does
        # not have any kind of locking in place around it.
        self._quic_conn.close()
        self._state = HTTPConnectionState.CLOSED
        self._network_stream.close()

    # Wrappers around network read/write operations...

    def _read_incoming_data(
        self, request: Request
    ) -> typing.List[h3_events.H3Event]:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("read", None)

        if self._read_exception is not None:
            raise self._read_exception  # pragma: nocover

        try:
            data = self._network_stream.read(self.READ_NUM_BYTES, timeout)
            if data == b"":
                raise RemoteProtocolError("Server disconnected")
        except Exception as exc:
            # If we get a network error we should:
            #
            # 1. Save the exception and just raise it immediately on any future reads.
            #    (For example, this means that a single read timeout or disconnect will
            #    immediately close all pending streams. Without requiring multiple
            #    sequential timeouts.)
            # 2. Mark the connection as errored, so that we don't accept any other
            #    incoming requests.
            self._read_exception = exc
            self._connection_error = True
            raise exc

        self._quic_conn.receive_datagram(
            data=data, addr=self._network_stream._addr, now=time.monotonic()
        )

        events: typing.List[h3_events.H3Event] = []
        quic_event = self._quic_conn.next_event()

        while quic_event:
            if isinstance(quic_event, quic_events.HandshakeCompleted):
                self._handshake_done = True

            # elif isinstance(quic_event, quic_events.StreamDataReceived):

            events.extend(self._h3_state.handle_event(quic_event))
            quic_event = self._quic_conn.next_event()

        return events

    def _write_outgoing_data(self, request: Request) -> None:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("write", None)

        with self._write_lock:
            for data_to_send, _ in self._quic_conn.datagrams_to_send(now=monotonic()):
                if self._write_exception is not None:
                    raise self._write_exception  # pragma: nocover

                try:
                    self._network_stream.write(data_to_send, timeout)
                except Exception as exc:  # pragma: nocover
                    # If we get a network error we should:
                    #
                    # 1. Save the exception and just raise it immediately on any future write.
                    #    (For example, this means that a single write timeout or disconnect will
                    #    immediately close all pending streams. Without requiring multiple
                    #    sequential timeouts.)
                    # 2. Mark the connection as errored, so that we don't accept any other
                    #    incoming requests.
                    self._write_exception = exc
                    self._connection_error = True
                    raise exc

    # Interface for connection pooling...

    def can_handle_request(self, origin: Origin) -> bool:
        return origin == self._origin

    def is_available(self) -> bool:
        return (
            self._state != HTTPConnectionState.CLOSED
            and not self._connection_error
            and not self._used_all_stream_ids
            and not (self._quic_conn._state == QuicConnectionState.CLOSING)
        )

    def has_expired(self) -> bool:
        now = time.monotonic()
        return self._expire_at is not None and now > self._expire_at

    def is_idle(self) -> bool:
        return self._state == HTTPConnectionState.IDLE

    def is_closed(self) -> bool:
        return self._state == HTTPConnectionState.CLOSED

    def info(self) -> str:
        origin = str(self._origin)
        return (
            f"{origin!r}, HTTP/3, {self._state.name}, "
            f"Request Count: {self._request_count}"
        )

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        origin = str(self._origin)
        return (
            f"<{class_name} [{origin!r}, {self._state.name}, "
            f"Request Count: {self._request_count}]>"
        )

    # These context managers are not used in the standard flow, but are
    # useful for testing or working with connection instances directly.

    def __enter__(self) -> "HTTP3Connection":
        return self

    def __exit__(
        self,
        exc_type: typing.Optional[typing.Type[BaseException]] = None,
        exc_value: typing.Optional[BaseException] = None,
        traceback: typing.Optional[types.TracebackType] = None,
    ) -> None:
        self.close()


class HTTP3ConnectionByteStream:
    def __init__(
        self,
        connection: HTTP3Connection,
        request: Request,
        stream_id: int,
        is_empty: bool,
    ) -> None:
        self._connection = connection
        self._request = request
        self._stream_id = stream_id
        self._closed = False
        self._is_empty = is_empty

    def __iter__(self) -> typing.Iterator[bytes]:
        kwargs = {"request": self._request, "stream_id": self._stream_id}
        try:
            if not self._is_empty:
                with Trace(
                    "receive_response_body", logger, self._request, kwargs
                ):
                    for chunk in self._connection._receive_response_body(
                        request=self._request, stream_id=self._stream_id
                    ):
                        yield chunk
        except BaseException as exc:
            # If we get an exception while streaming the response,
            # we want to close the response (and possibly the connection)
            # before raising that exception.
            with ShieldCancellation():
                self.close()
            raise exc

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            kwargs = {"stream_id": self._stream_id}
            with Trace("response_closed", logger, self._request, kwargs):
                self._connection._response_closed(stream_id=self._stream_id)
