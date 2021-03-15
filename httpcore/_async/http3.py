from ssl import SSLContext
from typing import AsyncIterator, Dict, List, Tuple, cast

from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, H3Event, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection

from .._backends.auto import (
    AsyncBackend,
    AsyncDatagramSocket,
    AsyncLock,
    AsyncSocketStream,
)
from .._bytestreams import AsyncIteratorByteStream, PlainByteStream
from .._exceptions import RemoteProtocolError
from .._types import URL, Headers, TimeoutDict
from .._utils import get_logger
from .base import AsyncByteStream, ConnectionState
from .http import AsyncBaseHTTPConnection

logger = get_logger(__name__)


class AsyncHTTP3Connection(AsyncBaseHTTPConnection):
    def __init__(
        self,
        socket: AsyncDatagramSocket,
        backend: AsyncBackend,
        ssl_context: SSLContext = None,
    ):
        self.socket = socket
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context

        self.backend = backend
        self._quic = QuicConnection(
            configuration=QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN)
        )
        self._http = H3Connection(self._quic)

        self.sent_connection_init = False
        self.streams = {}  # type: Dict[int, AsyncHTTP3Stream]
        self.events = {}  # type: Dict[int, List[H3Event]]

        self.state = ConnectionState.ACTIVE

    def __repr__(self) -> str:
        return f"<AsyncHTTP3Connection state={self.state}>"

    def info(self) -> str:
        return f"HTTP/3, {self.state.name}, {len(self.streams)} streams"

    @property
    def init_lock(self) -> AsyncLock:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_initialization_lock"):
            self._initialization_lock = self.backend.create_lock()
        return self._initialization_lock

    @property
    def read_lock(self) -> AsyncLock:
        # We do this lazily, to make sure backend autodetection always
        # runs within an async context.
        if not hasattr(self, "_read_lock"):
            self._read_lock = self.backend.create_lock()
        return self._read_lock

    async def start_tls(
        self, hostname: bytes, timeout: TimeoutDict = None
    ) -> AsyncSocketStream:
        raise NotImplementedError("TLS upgrade not supported on HTTP/3 connections.")

    def get_state(self) -> ConnectionState:
        return self.state

    def mark_as_ready(self) -> None:
        if self.state == ConnectionState.IDLE:
            self.state = ConnectionState.READY

    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        ext = {} if ext is None else ext
        timeout = cast(TimeoutDict, ext.get("timeout", {}))

        async with self.init_lock:
            if not self.sent_connection_init:
                # The very first stream is responsible for initiating the connection.
                self.state = ConnectionState.ACTIVE
                await self.send_connection_init(timeout)
                self.sent_connection_init = True

        # await self.max_streams_semaphore.acquire()
        try:
            stream_id = self._quic.get_next_available_stream_id()

            h3_stream = AsyncHTTP3Stream(stream_id=stream_id, connection=self)
            self.streams[stream_id] = h3_stream
            self.events[stream_id] = []
            return await h3_stream.arequest(method, url, headers, stream, ext)
        except Exception:  # noqa: PIE786
            # await self.max_streams_semaphore.release()
            raise

    async def send_connection_init(self, timeout: TimeoutDict) -> None:
        """
        The HTTP/3 connection requires some initial setup before we can start
        using individual request/response streams on it.
        """

        logger.trace("initiate_connection=%r", self)

        now = await self.backend.time()
        self._quic.connect(self.socket.remote_addr, now=now)
        await self._transmit()

    @property
    def is_closed(self) -> bool:
        return False

    def is_socket_readable(self) -> bool:
        return True

    async def aclose(self) -> None:
        logger.trace("close_connection=%r", self)
        if self.state != ConnectionState.CLOSED:
            self.state = ConnectionState.CLOSED

            await self.socket.aclose()

    async def wait_for_event(self, stream_id: int, timeout: TimeoutDict) -> H3Event:
        """
        Returns the next event for a given stream.
        If no events are available yet, then waits on the network until
        an event is available.
        """
        async with self.read_lock:
            while not self.events[stream_id]:
                await self.receive_events(timeout)
        return self.events[stream_id].pop(0)

    async def receive_events(self, timeout: TimeoutDict) -> None:
        """
        Read some data from the network, and update the H2 state.
        """
        data, addr = await self.socket.receive()
        if data == b"":
            raise RemoteProtocolError("Server disconnected")

        now = await self.backend.time()
        self._quic.receive_datagram(data, addr, now=now)

        quic_event = self._quic.next_event()
        while quic_event is not None:
            for http_event in self._http.handle_event(quic_event):
                event_stream_id = getattr(http_event, "stream_id", 0)
                logger.trace(
                    "receive_event stream_id=%r event=%s", event_stream_id, http_event
                )

                if event_stream_id in self.events:
                    self.events[event_stream_id].append(http_event)
            quic_event = self._quic.next_event()
        await self._transmit()

    async def send_headers(
        self, stream_id: int, headers: Headers, end_stream: bool, timeout: TimeoutDict
    ) -> None:
        logger.trace("send_headers stream_id=%r headers=%r", stream_id, headers)
        self._http.send_headers(
            stream_id=stream_id, headers=headers, end_stream=end_stream
        )
        await self._transmit()

    async def send_data(
        self, stream_id: int, chunk: bytes, timeout: TimeoutDict
    ) -> None:
        logger.trace("send_data stream_id=%r chunk=%r", stream_id, chunk)
        self._http.send_data(stream_id, chunk, end_stream=False)
        await self._transmit()

    async def end_stream(self, stream_id: int, timeout: TimeoutDict) -> None:
        logger.trace("end_stream stream_id=%r", stream_id)
        self._http.send_data(stream_id, b"", end_stream=True)
        await self._transmit()

    async def close_stream(self, stream_id: int) -> None:
        try:
            logger.trace("close_stream stream_id=%r", stream_id)
            del self.streams[stream_id]
            del self.events[stream_id]

            if not self.streams:
                if self.state == ConnectionState.ACTIVE:
                    self.state = ConnectionState.IDLE
                elif self.state == ConnectionState.FULL:
                    await self.aclose()
        finally:
            # await self.max_streams_semaphore.release()
            pass

    async def _transmit(self) -> None:
        """
        Send pending datagrams to the peer and arm the timer if needed.
        """
        self._transmit_task = None

        # send datagrams
        now = await self.backend.time()
        for data, addr in self._quic.datagrams_to_send(now=now):
            await self.socket.send(data, addr)

        """
        # re-arm timer
        timer_at = self._quic.get_timer()
        if self._timer is not None and self._timer_at != timer_at:
            self._timer.cancel()
            self._timer = None
        if self._timer is None and timer_at is not None:
            self._timer = self._loop.call_at(timer_at, self._handle_timer)
        self._timer_at = timer_at
        """


class AsyncHTTP3Stream:
    def __init__(self, stream_id: int, connection: AsyncHTTP3Connection) -> None:
        self.stream_ended = False
        self.stream_id = stream_id
        self.connection = connection

    async def arequest(
        self,
        method: bytes,
        url: URL,
        headers: Headers = None,
        stream: AsyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, Headers, AsyncByteStream, dict]:
        headers = [] if headers is None else [(k.lower(), v) for (k, v) in headers]
        stream = PlainByteStream(b"") if stream is None else stream
        ext = {} if ext is None else ext
        timeout = cast(TimeoutDict, ext.get("timeout", {}))

        # Send the request.
        seen_headers = set(key for key, value in headers)
        has_body = (
            b"content-length" in seen_headers or b"transfer-encoding" in seen_headers
        )

        await self.send_headers(method, url, headers, has_body, timeout)
        if has_body:
            await self.send_body(stream, timeout)

        # Receive the response.
        status_code, headers = await self.receive_response(timeout)
        response_stream = AsyncIteratorByteStream(
            aiterator=self.body_iter(timeout), aclose_func=self._response_closed
        )

        ext = {
            "http_version": "HTTP/3",
        }
        return (status_code, headers, response_stream, ext)

    async def send_headers(
        self,
        method: bytes,
        url: URL,
        headers: Headers,
        has_body: bool,
        timeout: TimeoutDict,
    ) -> None:
        scheme, hostname, port, path = url

        # In HTTP/3 the ':authority' pseudo-header is used instead of 'Host'.
        # In order to gracefully handle HTTP/1.1 and HTTP/3 we always require
        # HTTP/1.1 style headers, and map them appropriately if we end up on
        # an HTTP/3 connection.
        authority = None
        for k, v in headers:
            if k == b"host":
                authority = v
                break

        if authority is None:
            default_port = {b"http": 80, b"https": 443}.get(scheme)
            if port is not None and port != default_port:
                authority = b"%s:%d" % (authority, port)
            else:
                authority = hostname

        headers = [
            (b":method", method),
            (b":authority", authority),
            (b":scheme", scheme),
            (b":path", path),
        ] + [
            (k, v)
            for k, v in headers
            if k
            not in (
                b"host",
                b"transfer-encoding",
            )
        ]
        end_stream = not has_body

        await self.connection.send_headers(self.stream_id, headers, end_stream, timeout)

    async def send_body(self, stream: AsyncByteStream, timeout: TimeoutDict) -> None:
        async for data in stream:
            await self.connection.send_data(self.stream_id, data, timeout)

        await self.connection.end_stream(self.stream_id, timeout)

    async def receive_response(
        self, timeout: TimeoutDict
    ) -> Tuple[int, List[Tuple[bytes, bytes]]]:
        """
        Read the response status and headers from the network.
        """
        while True:
            event = await self.connection.wait_for_event(self.stream_id, timeout)
            if isinstance(event, HeadersReceived):
                self.stream_ended = event.stream_ended
                break

        status_code = 200
        headers = []
        for k, v in event.headers:
            if k == b":status":
                status_code = int(v.decode("ascii", errors="ignore"))
            elif not k.startswith(b":"):
                headers.append((k, v))

        return (status_code, headers)

    async def body_iter(self, timeout: TimeoutDict) -> AsyncIterator[bytes]:
        while not self.stream_ended:
            event = await self.connection.wait_for_event(self.stream_id, timeout)
            if isinstance(event, DataReceived):
                self.stream_ended = event.stream_ended
                yield event.data
            elif isinstance(event, HeadersReceived):
                self.stream_ended = event.stream_ended

    async def _response_closed(self) -> None:
        await self.connection.close_stream(self.stream_id)
