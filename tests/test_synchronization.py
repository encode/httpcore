import threading

from httpcore._synchronization import ThreadLock


def test_thread_lock_is_reentrant():
    """
    `ThreadLock` guards `ConnectionPool`'s internal bookkeeping
    (`_assign_requests_to_connections`), which calls out to connection and
    stream methods. If the *last* reference to an unclosed `PoolByteStream`
    is dropped while that bookkeeping is running (for example, because it is
    garbage collected), `PoolByteStream.close()` re-enters this same lock on
    the same thread that is already holding it.

    A plain, non-reentrant lock deadlocks permanently in that case. See
    https://github.com/encode/httpcore/discussions/990 for real-world reports
    of this happening in multithreaded servers.

    This test only checks the primitive's contract in isolation: that the
    same thread can acquire the lock more than once without blocking.
    """
    lock = ThreadLock()

    acquired_nested = threading.Event()

    with lock:
        with lock:
            acquired_nested.set()

    assert acquired_nested.is_set()


def test_thread_lock_still_blocks_other_threads():
    """
    Re-entrancy must not come at the cost of mutual exclusion between
    *different* threads: a second thread must still block until the first
    thread has released the lock completely.
    """
    lock = ThreadLock()
    other_thread_acquired = threading.Event()
    release_first_thread = threading.Event()

    def other_thread_body() -> None:
        with lock:
            other_thread_acquired.set()

    with lock:
        thread = threading.Thread(target=other_thread_body, daemon=True)
        thread.start()
        # The other thread should not be able to acquire the lock while
        # we're still holding it.
        assert not other_thread_acquired.wait(timeout=0.2)
        release_first_thread.set()

    # Once we've released it, the other thread should be able to proceed.
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert other_thread_acquired.is_set()
