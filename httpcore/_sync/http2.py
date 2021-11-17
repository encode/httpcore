import enum
import time
import types
import typing

import h2.config
import h2.connection
import h2.events
import h2.exceptions
import h2.settings

from .._exceptions import ConnectionNotAvailable, RemoteProtocolError
from .._models import Origin, Request, Response
from .._synchronization import Lock, Semaphore
from .._trace import Trace
from ..backends.base import NetworkStream
from .interfaces import ConnectionInterface


def has_body_headers(request: Request) -> bool:
    return any(
        [
            k.lower() == b"content-length" or k.lower() == b"transfer-encoding"
            for k, v in request.headers
        ]
    )


class HTTPConnectionState(enum.IntEnum):
    ACTIVE = 1
    IDLE = 2
    CLOSED = 3


class HTTP2Connection(ConnectionInterface):
    READ_NUM_BYTES = 64 * 1024
    CONFIG = h2.config.H2Configuration(validate_inbound_headers=False)

    def __init__(
        self, origin: Origin, stream: NetworkStream, keepalive_expiry: float = None
    ):
        self._origin = origin
        self._network_stream = stream
        self._keepalive_expiry: typing.Optional[float] = keepalive_expiry
        self._h2_state = h2.connection.H2Connection(config=self.CONFIG)
        self._state = HTTPConnectionState.IDLE
        self._expire_at: typing.Optional[float] = None
        self._request_count = 0
        self._init_lock = Lock()
        self._state_lock = Lock()
        self._read_lock = Lock()
        self._write_lock = Lock()
        self._sent_connection_init = False
        self._used_all_stream_ids = False
        self._events: typing.Dict[int, h2.events.Event] = {}

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

        with self._init_lock:
            if not self._sent_connection_init:
                kwargs = {"request": request}
                with Trace("http2.send_connection_init", request, kwargs):
                    self._send_connection_init(**kwargs)
                self._sent_connection_init = True
                max_streams = self._h2_state.local_settings.max_concurrent_streams
                self._max_streams_semaphore = Semaphore(max_streams)

        self._max_streams_semaphore.acquire()

        try:
            stream_id = self._h2_state.get_next_available_stream_id()
            self._events[stream_id] = []
        except h2.exceptions.NoAvailableStreamIDError:  # pragma: nocover
            self._used_all_stream_ids = True
            raise ConnectionNotAvailable()

        try:
            kwargs = {"request": request, "stream_id": stream_id}
            with Trace("http2.send_request_headers", request, kwargs):
                self._send_request_headers(request=request, stream_id=stream_id)
            with Trace("http2.send_request_body", request, kwargs):
                self._send_request_body(request=request, stream_id=stream_id)
            with Trace(
                "http2.receive_response_headers", request, kwargs
            ) as trace:
                status, headers = self._receive_response(
                    request=request, stream_id=stream_id
                )
                trace.return_value = (status, headers)

            return Response(
                status=status,
                headers=headers,
                content=HTTP2ConnectionByteStream(self, request, stream_id=stream_id),
                extensions={"stream_id": stream_id, "http_version": b"HTTP/2"},
            )
        except Exception:  # noqa: PIE786
            kwargs = {"stream_id": stream_id}
            with Trace("http2.response_closed", request, kwargs):
                self._response_closed(stream_id=stream_id)
            raise

    def _send_connection_init(self, request: Request) -> None:
        """
        The HTTP/2 connection requires some initial setup before we can start
        using individual request/response streams on it.
        """
        # Need to set these manually here instead of manipulating via
        # __setitem__() otherwise the H2Connection will emit SettingsUpdate
        # frames in addition to sending the undesired defaults.
        self._h2_state.local_settings = h2.settings.Settings(
            client=True,
            initial_values={
                # Disable PUSH_PROMISE frames from the server since we don't do anything
                # with them for now.  Maybe when we support caching?
                h2.settings.SettingCodes.ENABLE_PUSH: 0,
                # These two are taken from h2 for safe defaults
                h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 100,
                h2.settings.SettingCodes.MAX_HEADER_LIST_SIZE: 65536,
            },
        )

        # Some websites (*cough* Yahoo *cough*) balk at this setting being
        # present in the initial handshake since it's not defined in the original
        # RFC despite the RFC mandating ignoring settings you don't know about.
        del self._h2_state.local_settings[
            h2.settings.SettingCodes.ENABLE_CONNECT_PROTOCOL
        ]

        self._h2_state.initiate_connection()
        self._h2_state.increment_flow_control_window(2 ** 24)
        self._write_outgoing_data(request)

    # Sending the request...

    def _send_request_headers(self, request: Request, stream_id: int) -> None:
        end_stream = not has_body_headers(request)

        # In HTTP/2 the ':authority' pseudo-header is used instead of 'Host'.
        # In order to gracefully handle HTTP/1.1 and HTTP/2 we always require
        # HTTP/1.1 style headers, and map them appropriately if we end up on
        # an HTTP/2 connection.
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

        self._h2_state.send_headers(stream_id, headers, end_stream=end_stream)
        self._h2_state.increment_flow_control_window(2 ** 24, stream_id=stream_id)
        self._write_outgoing_data(request)

    def _send_request_body(self, request: Request, stream_id: int) -> None:
        if not has_body_headers(request):
            return

        assert isinstance(request.stream, typing.Iterable)
        for data in request.stream:
            while data:
                max_flow = self._wait_for_outgoing_flow(request, stream_id)
                chunk_size = min(len(data), max_flow)
                chunk, data = data[:chunk_size], data[chunk_size:]
                self._h2_state.send_data(stream_id, chunk)
                self._write_outgoing_data(request)

        self._h2_state.end_stream(stream_id)
        self._write_outgoing_data(request)

    # Receiving the response...

    def _receive_response(
        self, request: Request, stream_id: int
    ) -> typing.Tuple[int, typing.List[typing.Tuple[bytes, bytes]]]:
        while True:
            event = self._receive_stream_event(request, stream_id)
            if isinstance(event, h2.events.ResponseReceived):
                break

        status_code = 200
        headers = []
        for k, v in event.headers:
            if k == b":status":
                status_code = int(v.decode("ascii", errors="ignore"))
            elif not k.startswith(b":"):
                headers.append((k, v))

        return (status_code, headers)

    def _receive_response_body(
        self, request: Request, stream_id: int
    ) -> typing.Iterator[bytes]:
        while True:
            event = self._receive_stream_event(request, stream_id)
            if isinstance(event, h2.events.DataReceived):
                amount = event.flow_controlled_length
                self._h2_state.acknowledge_received_data(amount, stream_id)
                self._write_outgoing_data(request)
                yield event.data
            elif isinstance(event, (h2.events.StreamEnded, h2.events.StreamReset)):
                break

    def _receive_stream_event(
        self, request: Request, stream_id: int
    ) -> h2.events.Event:
        while not self._events.get(stream_id):
            self._receive_events(request)
        return self._events[stream_id].pop(0)

    def _receive_events(self, request: Request) -> None:
        events = self._read_incoming_data(request)
        for event in events:
            event_stream_id = getattr(event, "stream_id", 0)

            if hasattr(event, "error_code"):
                raise RemoteProtocolError(event)

            if event_stream_id in self._events:
                self._events[event_stream_id].append(event)

        self._write_outgoing_data(request)

    def _response_closed(self, stream_id: int) -> None:
        self._max_streams_semaphore.release()
        del self._events[stream_id]
        with self._state_lock:
            if self._state == HTTPConnectionState.ACTIVE and not self._events:
                self._state = HTTPConnectionState.IDLE
                if self._keepalive_expiry is not None:
                    now = time.monotonic()
                    self._expire_at = now + self._keepalive_expiry
                if self._used_all_stream_ids:  # pragma: nocover
                    self.close()

    def close(self) -> None:
        # Note that this method unilaterally closes the connection, and does
        # not have any kind of locking in place around it.
        # For task-safe/thread-safe operations call into 'attempt_close' instead.
        self._state = HTTPConnectionState.CLOSED
        self._network_stream.close()

    # Wrappers around network read/write operations...

    def _read_incoming_data(
        self, request: Request
    ) -> typing.List[h2.events.Event]:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("read", None)

        with self._read_lock:
            data = self._network_stream.read(self.READ_NUM_BYTES, timeout)
            if data == b"":
                raise RemoteProtocolError("Server disconnected")
            return self._h2_state.receive_data(data)

    def _write_outgoing_data(self, request: Request) -> None:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("write", None)

        with self._write_lock:
            data_to_send = self._h2_state.data_to_send()
            self._network_stream.write(data_to_send, timeout)

    # Flow control...

    def _wait_for_outgoing_flow(self, request: Request, stream_id: int) -> int:
        """
        Returns the maximum allowable outgoing flow for a given stream.

        If the allowable flow is zero, then waits on the network until
        WindowUpdated frames have increased the flow rate.
        https://tools.ietf.org/html/rfc7540#section-6.9
        """
        local_flow = self._h2_state.local_flow_control_window(stream_id)
        max_frame_size = self._h2_state.max_outbound_frame_size
        flow = min(local_flow, max_frame_size)
        while flow == 0:
            self._receive_events(request)
            local_flow = self._h2_state.local_flow_control_window(stream_id)
            max_frame_size = self._h2_state.max_outbound_frame_size
            flow = min(local_flow, max_frame_size)
        return flow

    # Interface for connection pooling...

    def can_handle_request(self, origin: Origin) -> bool:
        return origin == self._origin

    def is_available(self) -> bool:
        return (
            self._state != HTTPConnectionState.CLOSED and not self._used_all_stream_ids
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
            f"{origin!r}, HTTP/2, {self._state.name}, "
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

    def __enter__(self) -> "HTTP2Connection":
        return self

    def __exit__(
        self,
        exc_type: typing.Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: types.TracebackType = None,
    ) -> None:
        self.close()


class HTTP2ConnectionByteStream:
    def __init__(
        self, connection: HTTP2Connection, request: Request, stream_id: int
    ) -> None:
        self._connection = connection
        self._request = request
        self._stream_id = stream_id

    def __iter__(self) -> typing.Iterator[bytes]:
        kwargs = {"request": self._request, "stream_id": self._stream_id}
        with Trace("http2.receive_response_body", self._request, kwargs):
            for chunk in self._connection._receive_response_body(
                request=self._request, stream_id=self._stream_id
            ):
                yield chunk

    def close(self) -> None:
        kwargs = {"stream_id": self._stream_id}
        with Trace("http2.response_closed", self._request, kwargs):
            self._connection._response_closed(stream_id=self._stream_id)
