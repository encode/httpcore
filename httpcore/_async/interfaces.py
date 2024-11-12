from __future__ import annotations

import contextlib
import typing

from .._models import (
    URL,
    Extensions,
    HeaderTypes,
    Origin,
    Request,
    Response,
    enforce_bytes,
    enforce_headers,
    enforce_url,
    include_request_headers,
)


class StartResponse:
    def __init__(self, status: int, headers: HeaderTypes, extensions: Extensions):
        self.status = status
        self.headers = headers
        self.extensions = extensions


class ResponseContext:
    def __init__(
        self, status: int, headers: HeaderTypes, iterator, extensions: Extensions
    ):
        self._status = status
        self._headers = headers
        self._iterator = iterator
        self._extensions = extensions

    async def __aenter__(self):
        self._response = Response(
            status=self._status,
            headers=self._headers,
            content=self._iterator,
            extensions=self._extensions,
        )
        return self._response

    async def __aexit__(self, *args, **kwargs):
        await self._response.aclose()


class AsyncRequestInterface:
    async def request(
        self,
        method: bytes | str,
        url: URL | bytes | str,
        *,
        headers: HeaderTypes = None,
        content: bytes | typing.AsyncIterator[bytes] | None = None,
        extensions: Extensions | None = None,
    ) -> Response:
        # Strict type checking on our parameters.
        method = enforce_bytes(method, name="method")
        url = enforce_url(url, name="url")
        headers = enforce_headers(headers, name="headers")

        # Include Host header, and optionally Content-Length or Transfer-Encoding.
        headers = include_request_headers(headers, url=url, content=content)

        request = Request(
            method=method,
            url=url,
            headers=headers,
            content=content,
            extensions=extensions,
        )
        iterator = self.iterate_response(request)
        start_response = await anext(iterator)
        content = b"".join([part async for part in iterator])
        return Response(
            status=start_response.status,
            headers=start_response.headers,
            content=content,
            extensions=start_response.extensions,
        )

    @contextlib.asynccontextmanager
    async def stream(
        self,
        method: bytes | str,
        url: URL | bytes | str,
        *,
        headers: HeaderTypes = None,
        content: bytes | typing.AsyncIterator[bytes] | None = None,
        extensions: Extensions | None = None,
    ) -> ResponseContext:
        # Strict type checking on our parameters.
        method = enforce_bytes(method, name="method")
        url = enforce_url(url, name="url")
        headers = enforce_headers(headers, name="headers")

        # Include Host header, and optionally Content-Length or Transfer-Encoding.
        headers = include_request_headers(headers, url=url, content=content)

        request = Request(
            method=method,
            url=url,
            headers=headers,
            content=content,
            extensions=extensions,
        )
        iterator = self.iterate_response(request)
        start_response = await anext(iterator)
        response = Response(
            status=start_response.status,
            headers=start_response.headers,
            content=iterator,
            extensions=start_response.extensions,
        )
        try:
            yield response
        finally:
            await response.aclose()

    async def iterate_response(
        self, request: Request
    ) -> typing.AsyncIterator[StartResponse | bytes]:
        raise NotImplementedError()  # pragma: nocover
        yield b""


class AsyncConnectionInterface(AsyncRequestInterface):
    async def aclose(self) -> None:
        raise NotImplementedError()  # pragma: nocover

    def info(self) -> str:
        raise NotImplementedError()  # pragma: nocover

    def can_handle_request(self, origin: Origin) -> bool:
        raise NotImplementedError()  # pragma: nocover

    def is_available(self) -> bool:
        """
        Return `True` if the connection is currently able to accept an
        outgoing request.

        An HTTP/1.1 connection will only be available if it is currently idle.

        An HTTP/2 connection will be available so long as the stream ID space is
        not yet exhausted, and the connection is not in an error state.

        While the connection is being established we may not yet know if it is going
        to result in an HTTP/1.1 or HTTP/2 connection. The connection should be
        treated as being available, but might ultimately raise `NewConnectionRequired`
        required exceptions if multiple requests are attempted over a connection
        that ends up being established as HTTP/1.1.
        """
        raise NotImplementedError()  # pragma: nocover

    def has_expired(self) -> bool:
        """
        Return `True` if the connection is in a state where it should be closed.

        This either means that the connection is idle and it has passed the
        expiry time on its keep-alive, or that server has sent an EOF.
        """
        raise NotImplementedError()  # pragma: nocover

    def is_idle(self) -> bool:
        """
        Return `True` if the connection is currently idle.
        """
        raise NotImplementedError()  # pragma: nocover

    def is_closed(self) -> bool:
        """
        Return `True` if the connection has been closed.

        Used when a response is closed to determine if the connection may be
        returned to the connection pool or not.
        """
        raise NotImplementedError()  # pragma: nocover
