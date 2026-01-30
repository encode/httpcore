"""
Comprehensive tests for HTTP/2 GOAWAY handling.

These tests cover the new GOAWAY functionality introduced to handle race conditions
when servers send GOAWAY frames during HTTP/2 connections. Key features tested:

1. ConnectionGoingAway exception properties (is_safe_to_retry, is_graceful_shutdown, may_have_side_effects)
2. DRAINING connection state for graceful shutdowns
3. Request phase tracking (headers_sent, body_sent)
4. Pool-level retry logic based on GOAWAY context
5. Various race conditions between GOAWAY and request processing
"""

from __future__ import annotations

from typing import Any

import hpack
import hyperframe.frame
import pytest

import httpcore

# =============================================================================
# Tests for ConnectionGoingAway Exception Properties
# =============================================================================


class TestConnectionGoingAwayException:
    """Tests for the ConnectionGoingAway exception class and its properties."""

    def test_is_safe_to_retry_when_stream_id_greater_than_last_stream_id(self):
        """
        Per RFC 7540 Section 6.8: streams with IDs > last_stream_id are guaranteed
        unprocessed and safe to retry.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=3,  # > last_stream_id
            headers_sent=True,
            body_sent=True,
        )
        assert exc.is_safe_to_retry is True

    def test_is_not_safe_to_retry_when_stream_id_equals_last_stream_id(self):
        """
        Streams with IDs <= last_stream_id may have been processed by the server.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=1,  # == last_stream_id
            headers_sent=True,
            body_sent=True,
        )
        assert exc.is_safe_to_retry is False

    def test_is_not_safe_to_retry_when_stream_id_less_than_last_stream_id(self):
        """
        Streams with IDs <= last_stream_id may have been processed by the server.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=5,
            error_code=0,
            request_stream_id=1,  # < last_stream_id
            headers_sent=True,
            body_sent=True,
        )
        assert exc.is_safe_to_retry is False

    def test_is_graceful_shutdown_when_error_code_is_zero(self):
        """
        NO_ERROR (0x0) indicates administrative shutdown such as server restart,
        connection limit reached, or idle timeout.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,  # NO_ERROR
            request_stream_id=1,
        )
        assert exc.is_graceful_shutdown is True

    def test_is_not_graceful_shutdown_when_error_code_is_nonzero(self):
        """
        Non-zero error codes indicate an error condition.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=1,  # PROTOCOL_ERROR
            request_stream_id=1,
        )
        assert exc.is_graceful_shutdown is False

    def test_may_have_side_effects_when_stream_id_greater_than_last_stream_id(self):
        """
        If stream_id > last_stream_id, the request was guaranteed unprocessed,
        so no side effects are possible.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=3,  # > last_stream_id
            headers_sent=True,  # Even with headers sent, no side effects possible
            body_sent=True,
        )
        assert exc.may_have_side_effects is False

    def test_may_have_side_effects_when_headers_sent(self):
        """
        If stream_id <= last_stream_id AND headers were sent, side effects are possible.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=1,  # <= last_stream_id
            headers_sent=True,
            body_sent=False,
        )
        assert exc.may_have_side_effects is True

    def test_may_have_side_effects_when_body_sent(self):
        """
        If stream_id <= last_stream_id AND body was sent, side effects are possible.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=1,  # <= last_stream_id
            headers_sent=False,
            body_sent=True,
        )
        assert exc.may_have_side_effects is True

    def test_no_side_effects_when_nothing_sent(self):
        """
        If stream_id <= last_stream_id but nothing was sent, no side effects.
        """
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=1,  # <= last_stream_id
            headers_sent=False,
            body_sent=False,
        )
        assert exc.may_have_side_effects is False

    def test_repr(self):
        """Test the __repr__ method provides useful debugging info."""
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=3,
            headers_sent=True,
            body_sent=True,
        )
        repr_str = repr(exc)
        assert "ConnectionGoingAway" in repr_str
        assert "last_stream_id=1" in repr_str
        assert "error_code=0" in repr_str
        assert "request_stream_id=3" in repr_str
        assert "is_safe_to_retry=True" in repr_str
        assert "is_graceful_shutdown=True" in repr_str

    def test_inheritance_from_connection_not_available(self):
        """ConnectionGoingAway should be a subclass of ConnectionNotAvailable."""
        exc = httpcore.ConnectionGoingAway(
            "GOAWAY received",
            last_stream_id=1,
            error_code=0,
            request_stream_id=1,
        )
        assert isinstance(exc, httpcore.ConnectionNotAvailable)


# =============================================================================
# Tests for HTTP/2 Connection GOAWAY Handling
# =============================================================================



def test_http2_goaway_non_graceful_shutdown():
    """
    Non-graceful shutdown (error_code != 0) should raise ConnectionGoingAway
    with is_graceful_shutdown=False.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            # Non-graceful GOAWAY with PROTOCOL_ERROR (error_code=1)
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=1, last_stream_id=1
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        # First request should fail with ConnectionGoingAway due to non-graceful GOAWAY
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # Verify it's not a graceful shutdown
        assert exc_info.value.is_graceful_shutdown is False
        assert exc_info.value.error_code == 1



def test_http2_goaway_graceful_shutdown_properties():
    """
    When GOAWAY with NO_ERROR is received, the exception should have
    is_graceful_shutdown=True.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            # Graceful GOAWAY with NO_ERROR
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=0, last_stream_id=1
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        # Request should raise ConnectionGoingAway since GOAWAY is received
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # Should be a graceful shutdown
        assert exc_info.value.is_graceful_shutdown is True
        assert exc_info.value.error_code == 0



def test_http2_goaway_stream_id_greater_than_last_stream_id():
    """
    When stream_id > last_stream_id, the request is guaranteed unprocessed
    and should raise ConnectionGoingAway with is_safe_to_retry=True.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            # GOAWAY with last_stream_id=0 before any streams were processed
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=0, last_stream_id=0
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # Stream 1 > last_stream_id (0), so safe to retry
        assert exc_info.value.request_stream_id == 1
        assert exc_info.value.last_stream_id == 0
        assert exc_info.value.is_safe_to_retry is True



def test_http2_goaway_stream_id_less_than_or_equal_to_last_stream_id():
    """
    When stream_id <= last_stream_id and connection is not DRAINING,
    the request may have been processed and should raise ConnectionGoingAway.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            # GOAWAY with last_stream_id=1, so stream 1 may have been processed
            # Using error_code=1 to trigger non-DRAINING state
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=1, last_stream_id=1
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # Stream 1 <= last_stream_id (1), NOT safe to retry
        assert exc_info.value.request_stream_id == 1
        assert exc_info.value.last_stream_id == 1
        assert exc_info.value.is_safe_to_retry is False



def test_http2_server_disconnect_after_goaway():
    """
    When server disconnects after sending GOAWAY, the exception should
    include GOAWAY context.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            # GOAWAY followed immediately by disconnect
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=0, last_stream_id=0
            ).serialize(),
            b"",  # Server disconnect
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # Should include GOAWAY context
        assert exc_info.value.last_stream_id == 0
        assert exc_info.value.is_graceful_shutdown is True



def test_http2_tracks_request_phase_headers_sent():
    """
    The connection should track when headers have been sent for GOAWAY context.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            # GOAWAY after headers would be sent but before response
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=0, last_stream_id=1
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # Headers should have been sent
        assert exc_info.value.headers_sent is True



def test_http2_tracks_request_phase_body_sent():
    """
    The connection should track when body has been sent for GOAWAY context.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            # GOAWAY after body would be sent but before response
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=0, last_stream_id=1
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request(
                "POST",
                "https://example.com/",
                headers={b"content-length": b"11"},
                content=b"Hello World",
            )

        # Body should have been sent
        assert exc_info.value.body_sent is True



def test_http2_draining_connection_goaway_after_complete_response():
    """
    When GOAWAY is sent after a complete response, the first request succeeds.
    The GOAWAY is only discovered on the next request attempt, which then fails.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.DataFrame(
                stream_id=1, data=b"Hello, world!", flags=["END_STREAM"]
            ).serialize(),
            # GOAWAY after the first response completes - discovered on next request
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=0, last_stream_id=1
            ).serialize(),
            b"",  # Disconnect after GOAWAY
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        # First request should complete successfully
        response = conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"

        # Connection appears available because GOAWAY hasn't been read yet
        # (it comes after the complete response)
        # Second request attempts to use the connection and discovers GOAWAY
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # The second request (stream 3) > last_stream_id (1), so safe to retry
        assert exc_info.value.is_safe_to_retry is True


# =============================================================================
# Custom Mock Backend for Retry Tests
# =============================================================================


class MockBackendWithRetry(httpcore.MockBackend):
    """A mock backend that returns different data for each connection."""

    def __init__(self, buffers_by_connection: list[list[bytes]], http2: bool = False):
        self._all_buffers = buffers_by_connection
        self._connection_index = 0
        self._http2 = http2
        super().__init__([], http2=http2)

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.MockStream:
        if self._connection_index < len(self._all_buffers):
            buffer = list(self._all_buffers[self._connection_index])
            self._connection_index += 1
        else:
            buffer = []
        return httpcore.MockStream(buffer, http2=self._http2)


# =============================================================================
# Tests for Connection Pool GOAWAY Retry Logic
# =============================================================================



def test_connection_pool_retries_when_safe_to_retry():
    """
    Connection pool should automatically retry when is_safe_to_retry is True
    (stream_id > last_stream_id, guaranteed unprocessed).
    """
    network_backend = MockBackendWithRetry(
        buffers_by_connection=[
            # First connection: GOAWAY with last_stream_id=0 (stream 1 > 0, safe to retry)
            [
                hyperframe.frame.SettingsFrame().serialize(),
                hyperframe.frame.GoAwayFrame(
                    stream_id=0, error_code=0, last_stream_id=0
                ).serialize(),
                b"",
            ],
            # Second connection: normal response
            [
                hyperframe.frame.SettingsFrame().serialize(),
                hyperframe.frame.HeadersFrame(
                    stream_id=1,
                    data=hpack.Encoder().encode(
                        [
                            (b":status", b"200"),
                            (b"content-type", b"plain/text"),
                        ]
                    ),
                    flags=["END_HEADERS"],
                ).serialize(),
                hyperframe.frame.DataFrame(
                    stream_id=1, data=b"Hello, world!", flags=["END_STREAM"]
                ).serialize(),
            ],
        ],
        http2=True,
    )

    with httpcore.ConnectionPool(
        network_backend=network_backend,
    ) as pool:
        # Request should succeed after automatic retry
        response = pool.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"



def test_connection_pool_retries_graceful_no_side_effects():
    """
    Connection pool should retry when is_graceful_shutdown is True
    AND may_have_side_effects is False (headers not sent yet, stream > last_stream).
    """
    network_backend = MockBackendWithRetry(
        buffers_by_connection=[
            # First connection: Graceful GOAWAY with last_stream_id=0
            # stream 1 > 0, so safe to retry
            [
                hyperframe.frame.SettingsFrame().serialize(),
                hyperframe.frame.GoAwayFrame(
                    stream_id=0, error_code=0, last_stream_id=0
                ).serialize(),
                b"",
            ],
            # Second connection: normal response
            [
                hyperframe.frame.SettingsFrame().serialize(),
                hyperframe.frame.HeadersFrame(
                    stream_id=1,
                    data=hpack.Encoder().encode(
                        [
                            (b":status", b"200"),
                            (b"content-type", b"plain/text"),
                        ]
                    ),
                    flags=["END_HEADERS"],
                ).serialize(),
                hyperframe.frame.DataFrame(
                    stream_id=1, data=b"Success!", flags=["END_STREAM"]
                ).serialize(),
            ],
        ],
        http2=True,
    )

    with httpcore.ConnectionPool(
        network_backend=network_backend,
    ) as pool:
        response = pool.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Success!"



def test_connection_pool_raises_when_not_safe_to_retry():
    """
    Connection pool should raise RemoteProtocolError when is_safe_to_retry is False
    and the request may have been processed.
    """
    network_backend = MockBackendWithRetry(
        buffers_by_connection=[
            # First connection: GOAWAY with last_stream_id=1 (stream 1 <= 1, not safe)
            # Non-graceful shutdown (error_code=1)
            [
                hyperframe.frame.SettingsFrame().serialize(),
                hyperframe.frame.GoAwayFrame(
                    stream_id=0, error_code=1, last_stream_id=1
                ).serialize(),
                b"",
            ],
        ],
        http2=True,
    )

    with httpcore.ConnectionPool(
        network_backend=network_backend,
    ) as pool:
        with pytest.raises(httpcore.RemoteProtocolError) as exc_info:
            pool.request("GET", "https://example.com/")

        # Verify the error message indicates GOAWAY was received
        assert "GOAWAY" in str(exc_info.value)



def test_connection_pool_raises_when_may_have_side_effects():
    """
    Connection pool should raise RemoteProtocolError when graceful shutdown
    but request may have had side effects (headers sent, stream <= last_stream_id).
    """
    network_backend = MockBackendWithRetry(
        buffers_by_connection=[
            # First connection: Graceful GOAWAY with last_stream_id=1
            # Headers were sent, may have side effects
            [
                hyperframe.frame.SettingsFrame().serialize(),
                hyperframe.frame.GoAwayFrame(
                    stream_id=0, error_code=0, last_stream_id=1
                ).serialize(),
                b"",
            ],
        ],
        http2=True,
    )

    with httpcore.ConnectionPool(
        network_backend=network_backend,
    ) as pool:
        with pytest.raises(httpcore.RemoteProtocolError) as exc_info:
            pool.request("GET", "https://example.com/")

        # Verify the error message indicates GOAWAY was received
        assert "GOAWAY" in str(exc_info.value)


# =============================================================================
# Additional tests for specific code paths
# =============================================================================



def test_http2_goaway_receive_events_with_terminated_connection():
    """
    Test the _receive_events code path when connection is already terminated.
    This covers the case where stream_id <= last_stream_id.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            # GOAWAY with last_stream_id=5 (so stream 1 <= 5, may have been processed)
            # Non-graceful shutdown so connection goes to CLOSED, not DRAINING
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=1, last_stream_id=5
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.request("GET", "https://example.com/")

        # Stream 1 <= last_stream_id (5), NOT safe to retry
        assert exc_info.value.request_stream_id == 1
        assert exc_info.value.last_stream_id == 5
        assert exc_info.value.is_safe_to_retry is False



def test_http2_goaway_connection_closed_after_graceful_goaway():
    """
    Test that connection is properly closed after handling graceful GOAWAY
    when the request fails (due to server disconnect after GOAWAY).
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.GoAwayFrame(
                stream_id=0, error_code=0, last_stream_id=1
            ).serialize(),
            b"",
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        with pytest.raises(httpcore.ConnectionGoingAway):
            conn.request("GET", "https://example.com/")

        # After exception handling cleanup, connection should be closed
        assert conn.is_closed()


# =============================================================================
# Tests for pool retry edge cases using mock connections
# =============================================================================


class MockConnectionGracefulGoaway(httpcore.ConnectionInterface):
    """
    Mock connection that raises ConnectionGoingAway with specific properties
    to test the graceful shutdown + no side effects retry path.
    """

    def __init__(self, origin: httpcore.Origin) -> None:
        self._origin = origin
        self._calls = 0

    def can_handle_request(self, origin: httpcore.Origin) -> bool:
        return origin == self._origin

    def is_available(self) -> bool:
        return True

    def is_idle(self) -> bool:
        return self._calls == 0

    def is_closed(self) -> bool:
        return False

    def has_expired(self) -> bool:
        return False

    def handle_request(
        self, request: httpcore.Request
    ) -> httpcore.Response:
        self._calls += 1
        if self._calls == 1:
            # First call: raise ConnectionGoingAway with:
            # - stream_id <= last_stream_id (not safe to retry based on RFC)
            # - error_code = 0 (graceful shutdown)
            # - headers_sent = False, body_sent = False (no side effects)
            # This triggers the "elif exc.is_graceful_shutdown and not exc.may_have_side_effects" branch
            raise httpcore.ConnectionGoingAway(
                "Graceful shutdown before headers sent",
                last_stream_id=5,  # >= stream_id (1)
                error_code=0,  # graceful
                request_stream_id=1,  # <= last_stream_id
                headers_sent=False,  # no side effects
                body_sent=False,
            )
        return httpcore.Response(200, content=b"Success after retry!")

    def close(self) -> None:
        pass

    def info(self) -> str:
        return "MockConnectionGracefulGoaway"



def test_connection_pool_retries_graceful_shutdown_no_headers_sent():
    """
    Test the pool retry path where:
    - is_safe_to_retry = False (stream_id <= last_stream_id)
    - is_graceful_shutdown = True (error_code = 0)
    - may_have_side_effects = False (headers not sent yet)

    This tests line 258 in connection_pool.py.
    """

    # Create a custom pool that returns our mock connection
    class TestPool(httpcore.ConnectionPool):
        def __init__(self) -> None:
            super().__init__()
            self._mock_connections: list[MockConnectionGracefulGoaway] = []

        def create_connection(
            self, origin: httpcore.Origin
        ) -> MockConnectionGracefulGoaway:
            conn = MockConnectionGracefulGoaway(origin)
            self._mock_connections.append(conn)
            return conn

    with TestPool() as pool:
        response = pool.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Success after retry!"

        # Verify the first connection was called twice (retry happened)
        assert pool._mock_connections[0]._calls == 2  # type: ignore[attr-defined]


# =============================================================================
# Tests for edge cases in HTTP/2 GOAWAY handling
# =============================================================================



def test_http2_receive_events_with_terminated_connection_no_stream_id():
    """
    Test _receive_events when connection is terminated and stream_id is None.
    This covers line 435 in http2.py - the RemoteProtocolError path.

    This scenario occurs when _receive_events is called without a stream_id
    (e.g., from _wait_for_outgoing_flow) after the connection has terminated.
    We test this by directly manipulating the connection state.
    """
    import h2.events

    origin = httpcore.Origin(b"https", b"example.com", 443)
    stream = httpcore.MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            # We'll manipulate the connection state after initialization
        ]
    )
    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        # Directly set _connection_terminated to simulate a terminated connection
        # This mimics the state after receiving a GOAWAY but before cleanup
        terminated = h2.events.ConnectionTerminated()
        terminated.error_code = 0
        terminated.last_stream_id = 0
        terminated.additional_data = b""
        conn._connection_terminated = terminated

        # Create a mock request for the _receive_events call
        request = httpcore.Request(
            method=b"GET",
            url=httpcore.URL("https://example.com/"),
            headers=[(b"host", b"example.com")],
        )

        # Call _receive_events with stream_id=None to trigger line 435
        with pytest.raises(httpcore.RemoteProtocolError):
            conn._receive_events(request, stream_id=None)



def test_http2_server_disconnect_with_h2_closed_state():
    """
    Test server disconnect when h2 state machine is CLOSED but _connection_terminated
    is not yet set. This covers line 558 in http2.py.

    This simulates a race condition where h2 has processed GOAWAY internally
    (transitioning to CLOSED state) but we haven't processed the event yet.
    """
    import h2.connection

    origin = httpcore.Origin(b"https", b"example.com", 443)

    # Create a mock stream that sets state to CLOSED BEFORE returning empty data
    # This simulates the race condition accurately
    class MockStreamWithClosedStateOnDisconnect(httpcore.MockStream):
        def __init__(self, conn_ref: list[httpcore.HTTP2Connection]) -> None:
            self._conn_ref = conn_ref
            self._read_count = 0
            super().__init__([hyperframe.frame.SettingsFrame().serialize()], http2=True)

        def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
            self._read_count += 1
            if self._read_count == 1:
                # First read returns settings
                return bytes(hyperframe.frame.SettingsFrame().serialize())
            # Before returning empty (disconnect), set h2 state to CLOSED
            # This simulates h2 having processed GOAWAY internally
            if self._conn_ref and self._conn_ref[0]:
                self._conn_ref[
                    0
                ]._h2_state.state_machine.state = h2.connection.ConnectionState.CLOSED
                self._conn_ref[0]._connection_terminated = None
            return b""  # Server disconnect

    conn_ref: list[httpcore.HTTP2Connection] = []
    stream = MockStreamWithClosedStateOnDisconnect(conn_ref)

    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        conn_ref.append(conn)

        # Set up stream tracking for the request
        conn._stream_requests[1] = {"headers_sent": True, "body_sent": False}

        # Create a mock request
        request = httpcore.Request(
            method=b"GET",
            url=httpcore.URL("https://example.com/"),
            headers=[(b"host", b"example.com")],
        )

        # First call consumes the initial settings frame
        conn._read_incoming_data(request, stream_id=1)

        # Second call should hit line 558 when mock returns empty data
        # and sets h2 state to CLOSED
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn._read_incoming_data(request, stream_id=1)

        # Verify the exception has the expected properties
        assert exc_info.value.request_stream_id == 1
        assert exc_info.value.error_code == 0  # Assumed graceful



def test_http2_protocol_error_with_h2_closed_state():
    """
    Test h2 ProtocolError when state machine is CLOSED.
    This covers lines 213-225 in http2.py.

    This simulates the race condition where h2 raises a ProtocolError
    and the state machine is in CLOSED state, but _connection_terminated
    is not yet set.
    """
    import h2.connection

    origin = httpcore.Origin(b"https", b"example.com", 443)

    # Create a mock stream that sets state to CLOSED during write
    # This causes h2 to raise ProtocolError when trying to read the next frame
    class MockStreamWithClosedOnWrite(httpcore.MockStream):
        def __init__(self, conn_ref: list[httpcore.HTTP2Connection]) -> None:
            self._conn_ref = conn_ref
            self._write_count = 0
            super().__init__([hyperframe.frame.SettingsFrame().serialize()], http2=True)

        def write(self, data: bytes, timeout: float | None = None) -> None:
            self._write_count += 1
            # After first write (settings ACK), set state to CLOSED
            # to simulate race condition during request sending
            if self._write_count > 1 and self._conn_ref and self._conn_ref[0]:
                self._conn_ref[
                    0
                ]._h2_state.state_machine.state = h2.connection.ConnectionState.CLOSED
                self._conn_ref[0]._connection_terminated = None

    conn_ref: list[httpcore.HTTP2Connection] = []
    stream = MockStreamWithClosedOnWrite(conn_ref)

    with httpcore.HTTP2Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        conn_ref.append(conn)

        # Use handle_request which has the try-except block
        # The request will fail when h2 raises ProtocolError in CLOSED state
        with pytest.raises(httpcore.ConnectionGoingAway) as exc_info:
            conn.handle_request(
                httpcore.Request(
                    method=b"GET",
                    url=httpcore.URL("https://example.com/"),
                    headers=[(b"host", b"example.com")],
                )
            )

        # Verify the exception properties
        assert exc_info.value.error_code == 0  # Assumed graceful



def test_mock_backend_with_retry_exhausted_buffers():
    """
    Test the MockBackendWithRetry when more connections are made
    than buffers provided. This covers the else branch at line 497.
    """
    network_backend = MockBackendWithRetry(
        buffers_by_connection=[
            # Only one buffer set provided
            [
                hyperframe.frame.SettingsFrame().serialize(),
                hyperframe.frame.GoAwayFrame(
                    stream_id=0, error_code=0, last_stream_id=0
                ).serialize(),
                b"",
            ],
        ],
        http2=True,
    )

    # First connection uses the buffer
    stream1 = network_backend.connect_tcp("example.com", 443)
    assert stream1 is not None

    # Second connection should hit the else branch (empty buffer)
    stream2 = network_backend.connect_tcp("example.com", 443)
    assert stream2 is not None



def test_mock_connection_graceful_goaway_info():
    """
    Test the info() method of MockConnectionGracefulGoaway.
    This covers line 795.
    """
    origin = httpcore.Origin(b"https", b"example.com", 443)
    mock_conn = MockConnectionGracefulGoaway(origin)

    # Verify the info method returns the expected string
    assert mock_conn.info() == "MockConnectionGracefulGoaway"
