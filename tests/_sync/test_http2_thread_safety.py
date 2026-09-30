"""Regression test for encode/httpx#3566.

`httpx.Client(http2=True)` shares a single connection across threads (HTTP/2
multiplexing). That connection is `httpcore.HTTP2Connection`, which wraps one
`h2.H2Connection` state machine. The send path — stream-ID allocation, the
`_events` mapping, and the HPACK encoding in `send_headers` — used to be
completely unserialized, so concurrent threads could corrupt the state
machine ("deque mutated during iteration", "dictionary changed size during
iteration", `StreamIDTooLowError`).

This test drives one shared `HTTP2Connection` from multiple threads over a
fully in-memory fake HTTP/2 server (a real server-side `h2` connection
guarded by its own lock, so only the *client-side* httpcore code is under
test) and asserts every request succeeds.
"""

import threading
import time
import typing

import h2.config
import h2.connection
import h2.events

import httpcore


class FakeStream(httpcore.NetworkStream):
    """In-memory full-duplex socket backed by a real server-side h2 connection."""

    def __init__(self) -> None:
        self._server = h2.connection.H2Connection(
            config=h2.config.H2Configuration(client_side=False)
        )
        self._server.initiate_connection()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._closed = False
        self._responded: typing.Set[int] = set()

    def _respond(self, stream_id: int) -> None:
        self._server.send_headers(
            stream_id,
            [(":status", "200"), ("content-length", "2")],
            end_stream=False,
        )
        self._server.send_data(stream_id, b"ok", end_stream=True)

    # -- NetworkStream interface --
    def write(self, buffer: bytes, timeout: typing.Optional[float] = None) -> None:
        with self._lock:
            if buffer:
                for event in self._server.receive_data(buffer):
                    if isinstance(event, h2.events.RequestReceived):
                        if event.stream_ended is not None:
                            self._responded.add(event.stream_id)
                            self._respond(event.stream_id)
                    elif isinstance(event, h2.events.DataReceived):
                        # Replenish the server's inbound flow-control window,
                        # like any real HTTP/2 server does.
                        self._server.acknowledge_received_data(
                            event.flow_controlled_length, event.stream_id
                        )
                    elif isinstance(event, h2.events.StreamEnded):
                        if event.stream_id not in self._responded:
                            self._responded.add(event.stream_id)
                            self._respond(event.stream_id)
            self._cond.notify_all()

    def read(self, max_bytes: int, timeout: typing.Optional[float] = None) -> bytes:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            while True:
                data: bytes = self._server.data_to_send(max_bytes)
                if data:
                    return data
                if self._closed:  # pragma: no cover
                    return b""
                remaining = None if deadline is None else deadline - time.monotonic()  # pragma: no cover
                if remaining is not None and remaining <= 0:  # pragma: no cover
                    return b""
                self._cond.wait(timeout=1.0)  # pragma: no cover

    def close(self) -> None:  # pragma: no cover
        with self._lock:
            self._closed = True
            self._cond.notify_all()

    def get_extra_info(self, info: str) -> typing.Any:  # pragma: no cover
        return None


def test_http2_connection_is_thread_safe():
    """
    One shared HTTP2Connection must survive N threads racing the send path.

    Without the `_send_lock` fix, this fails with errors such as
    "deque mutated during iteration", "dictionary changed size during
    iteration", `StreamIDTooLowError`, or `KeyError`.
    """
    n_threads = 8
    n_requests = 50

    origin = httpcore.Origin(b"https", b"example.org", 443)
    connection = httpcore.HTTP2Connection(origin=origin, stream=FakeStream())

    errors = []
    errors_lock = threading.Lock()

    def worker(worker_id):
        for i in range(n_requests):
            body = b"x" * 64 if i % 2 else b""
            headers = [
                (b"host", b"example.org"),
                (b"user-agent", b"thread-safety-test"),
                (b"x-request", f"{worker_id}-{i}".encode()),
            ]
            if body:
                headers.append((b"content-length", str(len(body)).encode()))
            request = httpcore.Request(
                "POST" if body else "GET",
                f"https://example.org/{worker_id}/{i}",
                headers=headers,
                content=body,
                extensions={"timeout": {"read": 10, "write": 10}},
            )
            try:
                response = connection.handle_request(request)
                content = response.read()
                response.close()
                assert response.status == 200
                assert content == b"ok"
            except Exception as exc:  # noqa: BLE001  # pragma: no cover
                with errors_lock:
                    errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(w,), name=f"h2-worker-{w}")
        for w in range(n_threads)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert not any(thread.is_alive() for thread in threads), "worker threads hung"
    assert errors == [], (
        f"{len(errors)} request(s) failed out of {n_threads * n_requests}: "
        f"{sorted({type(e).__name__ for e in errors})}"
    )
