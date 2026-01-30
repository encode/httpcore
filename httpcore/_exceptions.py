import contextlib
import typing

ExceptionMapping = typing.Mapping[typing.Type[Exception], typing.Type[Exception]]


@contextlib.contextmanager
def map_exceptions(map: ExceptionMapping) -> typing.Iterator[None]:
    try:
        yield
    except Exception as exc:  # noqa: PIE786
        for from_exc, to_exc in map.items():
            if isinstance(exc, from_exc):
                raise to_exc(exc) from exc
        raise  # pragma: nocover


class ConnectionNotAvailable(Exception):
    pass


class ConnectionGoingAway(ConnectionNotAvailable):
    """
    Raised when a GOAWAY frame is received during HTTP/2 request processing.

    This exception provides context for determining whether a request is safe
    to retry, based on RFC 7540 Section 6.8 semantics.

    Per RFC 7540: streams with IDs > last_stream_id are guaranteed unprocessed
    and safe to retry. Streams with IDs <= last_stream_id may have been processed.

    Attributes:
        last_stream_id: The highest stream ID the server may have processed.
        error_code: The GOAWAY error code (0 = NO_ERROR for graceful shutdown).
        request_stream_id: The stream ID assigned to this specific request.
        headers_sent: Whether request headers were transmitted before GOAWAY.
        body_sent: Whether request body was transmitted before GOAWAY.
    """

    def __init__(
        self,
        message: str,
        *,
        last_stream_id: int,
        error_code: int,
        request_stream_id: int,
        headers_sent: bool = False,
        body_sent: bool = False,
    ) -> None:
        super().__init__(message)
        self.last_stream_id = last_stream_id
        self.error_code = error_code
        self.request_stream_id = request_stream_id
        self.headers_sent = headers_sent
        self.body_sent = body_sent

    @property
    def is_safe_to_retry(self) -> bool:
        """
        Returns True if the request is guaranteed unprocessed and safe to retry.

        Per RFC 7540 Section 6.8: any stream with ID > last_stream_id was never
        seen by the server and can be safely retried.
        """
        return self.request_stream_id > self.last_stream_id

    @property
    def is_graceful_shutdown(self) -> bool:
        """
        Returns True if this is a graceful shutdown (NO_ERROR).

        NO_ERROR (0x0) indicates administrative shutdown such as server restart,
        connection limit reached, or idle timeout.
        """
        return self.error_code == 0

    @property
    def may_have_side_effects(self) -> bool:
        """
        Returns True if the request may have been processed by the server.

        If stream_id > last_stream_id: guaranteed no side effects (unprocessed).
        If stream_id <= last_stream_id AND (headers or body sent): possibly processed.
        """
        if self.request_stream_id > self.last_stream_id:
            return False  # Guaranteed unprocessed per RFC 7540
        return self.headers_sent or self.body_sent

    def __repr__(self) -> str:
        return (
            f"ConnectionGoingAway("
            f"last_stream_id={self.last_stream_id}, "
            f"error_code={self.error_code}, "
            f"request_stream_id={self.request_stream_id}, "
            f"is_safe_to_retry={self.is_safe_to_retry}, "
            f"is_graceful_shutdown={self.is_graceful_shutdown})"
        )


class ProxyError(Exception):
    pass


class UnsupportedProtocol(Exception):
    pass


class ProtocolError(Exception):
    pass


class RemoteProtocolError(ProtocolError):
    pass


class LocalProtocolError(ProtocolError):
    pass


# Timeout errors


class TimeoutException(Exception):
    pass


class PoolTimeout(TimeoutException):
    pass


class ConnectTimeout(TimeoutException):
    pass


class ReadTimeout(TimeoutException):
    pass


class WriteTimeout(TimeoutException):
    pass


# Network errors


class NetworkError(Exception):
    pass


class ConnectError(NetworkError):
    pass


class ReadError(NetworkError):
    pass


class WriteError(NetworkError):
    pass
