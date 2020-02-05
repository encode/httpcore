from ssl import SSLContext
from typing import AsyncIterator, Dict, List, Optional, Tuple, Union

import h11

from .._backends.auto import AsyncSocketStream, AutoBackend
from .._exceptions import ProtocolError
from .base import AsyncByteStream, AsyncHTTPTransport

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
        self,
        origin: Tuple[bytes, bytes, int],
        socket: AsyncSocketStream = None,
        ssl_context: SSLContext = None,
    ):
        self.origin = origin
        self.socket = socket
        self.ssl_context = SSLContext() if ssl_context is None else ssl_context
        self.backend = AutoBackend()
        self.h11_state = h11.Connection(our_role=h11.CLIENT)

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

        assert url[:3] == self.origin

        if self.socket is None:
            self.socket = await self._connect(timeout)

        await self._send_request(method, url, headers, timeout)
        await self._send_request_body(stream, timeout)
        (
            http_version,
            status_code,
            reason_phrase,
            headers,
        ) = await self._receive_response(timeout)
        stream = AsyncByteStream(iterator=self._receive_response_data(timeout),)
        return (http_version, status_code, reason_phrase, headers, stream)

    async def _connect(self, timeout: Dict[str, Optional[float]]) -> AsyncSocketStream:
        scheme, hostname, port = self.origin
        ssl_context = self.ssl_context if scheme == b"https" else None
        return await self.backend.open_tcp_stream(hostname, port, ssl_context, timeout)

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
        assert self.socket is not None

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
        assert self.socket is not None

        while True:
            try:
                event = self.h11_state.next_event()
            except h11.RemoteProtocolError as exc:
                raise ProtocolError(exc)

            if event is h11.NEED_DATA:
                try:
                    data = await self.socket.read(self.READ_NUM_BYTES, timeout)
                except OSError:  # pragma: nocover
                    data = b""
                self.h11_state.receive_data(data)
            else:
                assert event is not h11.NEED_DATA
                break  # pragma: no cover
        return event

    async def response_closed(self) -> None:
        if (
            self.h11_state.our_state is h11.DONE
            and self.h11_state.their_state is h11.DONE
        ):
            # Get ready for another request/response cycle.
            self.h11_state.start_next_cycle()
        else:
            await self.close()

    async def close(self) -> None:
        assert self.socket is not None

        event = h11.ConnectionClosed()
        try:
            self.h11_state.send(event)
        except h11.LocalProtocolError:  # pragma: no cover
            # Premature client disconnect
            pass
        await self.socket.close()
