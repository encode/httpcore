from ssl import SSLContext
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

import h11

from .._backends.auto import AsyncSocketStream
from .._exceptions import ProtocolError, map_exceptions
from .base import AsyncByteStream, AsyncHTTPTransport, ConnectionState

H11Event = Union[
    h11.Request,
    h11.Response,
    h11.InformationalResponse,
    h11.Data,
    h11.EndOfMessage,
    h11.ConnectionClosed,
]


class AsyncHTTP11Connection(AsyncHTTPTransport):
    READ_NUM_BYTES = 4096

    def __init__(
        self, socket: AsyncSocketStream, ssl_context: SSLContext = None,
    ):
        self.socket = socket
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context

        self.h11_state = h11.Connection(our_role=h11.CLIENT)

        self.state = ConnectionState.ACTIVE

    def mark_as_ready(self):
        if self.state == ConnectionState.IDLE:
            self.state = ConnectionState.READY

    async def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, int, bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: AsyncByteStream = None,
        timeout: Dict[str, Optional[float]] = None,
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]], AsyncByteStream]:
        headers = [] if headers is None else headers
        stream = AsyncByteStream() if stream is None else stream
        timeout = {} if timeout is None else timeout

        self.state = ConnectionState.ACTIVE

        await self._send_request(method, url, headers, timeout)
        await self._send_request_body(stream, timeout)
        (
            http_version,
            status_code,
            reason_phrase,
            headers,
        ) = await self._receive_response(timeout)
        stream = AsyncByteStream(
            iterator=self._receive_response_data(timeout),
            close_func=self._response_closed,
        )
        return (http_version, status_code, reason_phrase, headers, stream)

    async def start_tls(
        self, hostname: bytes, timeout: Dict[str, Optional[float]] = None
    ):
        timeout = {} if timeout is None else timeout
        self.socket = await self.socket.start_tls(hostname, self.ssl_context, timeout)

    async def _send_request(
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
        await self._send_event(event, timeout)

    async def _send_request_body(
        self, stream: AsyncByteStream, timeout: Dict[str, Optional[float]]
    ) -> None:
        """
        Send the request body.
        """
        # Send the request body.
        async for chunk in stream:
            event = h11.Data(data=chunk)
            await self._send_event(event, timeout)

        # Finalize sending the request.
        event = h11.EndOfMessage()
        await self._send_event(event, timeout)

    async def _send_event(
        self, event: H11Event, timeout: Dict[str, Optional[float]]
    ) -> None:
        """
        Send a single `h11` event to the network, waiting for the data to
        drain before returning.
        """
        bytes_to_send = self.h11_state.send(event)
        await self.socket.write(bytes_to_send, timeout)

    async def _receive_response(
        self, timeout: Dict[str, Optional[float]]
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]]]:
        """
        Read the response status and headers from the network.
        """
        while True:
            event = await self._receive_event(timeout)
            if isinstance(event, h11.Response):
                break
        http_version = b"HTTP/" + event.http_version
        return http_version, event.status_code, event.reason, event.headers

    async def _receive_response_data(
        self, timeout: Dict[str, Optional[float]]
    ) -> AsyncIterator[bytes]:
        """
        Read the response data from the network.
        """
        while True:
            event = await self._receive_event(timeout)
            if isinstance(event, h11.Data):
                yield bytes(event.data)
            elif isinstance(event, h11.EndOfMessage):
                break

    async def _receive_event(self, timeout: Dict[str, Optional[float]]) -> H11Event:
        """
        Read a single `h11` event, reading more data from the network if needed.
        """
        while True:
            with map_exceptions({h11.RemoteProtocolError: ProtocolError}):
                event = self.h11_state.next_event()

            if event is h11.NEED_DATA:
                data = await self.socket.read(self.READ_NUM_BYTES, timeout)
                self.h11_state.receive_data(data)
            else:
                assert event is not h11.NEED_DATA
                break
        return event

    async def _response_closed(self) -> None:
        if self.h11_state.our_state is h11.DONE:
            self.h11_state.start_next_cycle()
            self.state = ConnectionState.IDLE
        else:
            await self.close()

    async def close(self) -> None:
        if self.state != ConnectionState.CLOSED:
            self.state = ConnectionState.CLOSED

            if self.h11_state.our_state is h11.MUST_CLOSE:
                event = h11.ConnectionClosed()
                self.h11_state.send(event)

            await self.socket.close()

    def is_connection_dropped(self) -> bool:
        return self.socket.is_connection_dropped()
