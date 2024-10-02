import asyncio
import sys
import threading
from types import TracebackType
from typing import Any, Callable, Coroutine, Literal, Optional, Protocol, Type

from ._exceptions import ExceptionMapping, PoolTimeout, map_exceptions

# Our async synchronization primitives use either 'asyncio' or 'trio' depending
# on if they're running under asyncio or trio.

try:
    import trio
except (ImportError, NotImplementedError):  # pragma: nocover
    trio = None  # type: ignore

try:
    import anyio
except ImportError:  # pragma: nocover
    anyio = None  # type: ignore


if sys.version_info >= (3, 11):  # pragma: nocover
    import asyncio as asyncio_timeout
else:  # pragma: nocover
    import async_timeout as asyncio_timeout


AsyncBackend = Literal["asyncio", "trio"]


def current_async_backend() -> AsyncBackend:
    # Determine if we're running under trio or asyncio.
    # See https://sniffio.readthedocs.io/en/latest/
    try:
        import sniffio
    except ImportError:  # pragma: nocover
        backend: AsyncBackend = "asyncio"
    else:
        backend = sniffio.current_async_library()  # type: ignore[assignment]

    if backend not in ("asyncio", "trio"):  # pragma: nocover
        raise RuntimeError("Running under an unsupported async backend.")

    if backend == "asyncio" and anyio is None:  # pragma: nocover
        raise RuntimeError(
            "Running with asyncio requires installation of 'httpcore[asyncio]'."
        )

    if backend == "trio" and trio is None:  # pragma: nocover
        raise RuntimeError(
            "Running with trio requires installation of 'httpcore[trio]'."
        )

    return backend


class _LockProto(Protocol):
    async def acquire(self) -> Any: ...
    def release(self) -> None: ...


class _EventProto(Protocol):
    def set(self) -> None: ...
    async def wait(self) -> Any: ...


class AsyncLock:
    """
    This is a standard lock.

    In the sync case `Lock` provides thread locking.
    In the async case `AsyncLock` provides async locking.
    """

    def __init__(self) -> None:
        self._lock: Optional[_LockProto] = None

    def setup(self) -> None:
        """
        Detect if we're running under 'asyncio' or 'trio' and create
        a lock with the correct implementation.
        """
        if current_async_backend() == "trio":
            self._lock = trio.Lock()
        else:
            # Note: asyncio.Lock has better performance characteristics than anyio.Lock
            # https://github.com/encode/httpx/issues/3215
            self._lock = asyncio.Lock()

    async def __aenter__(self) -> "AsyncLock":
        if self._lock is None:
            self.setup()
        lock: _LockProto = self._lock  # type: ignore[assignment]
        await lock.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        lock: _LockProto = self._lock  # type: ignore[assignment]
        lock.release()


class AsyncThreadLock:
    """
    This is a threading-only lock for no-I/O contexts.

    In the sync case `ThreadLock` provides thread locking.
    In the async case `AsyncThreadLock` is a no-op.
    """

    def __enter__(self) -> "AsyncThreadLock":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        pass


class AsyncEvent:
    def __init__(self) -> None:
        self._backend = ""
        self._event: Optional[_EventProto] = None

    def setup(self) -> None:
        """
        Detect if we're running under 'asyncio' or 'trio' and create
        a lock with the correct implementation.
        """
        self._backend = current_async_backend()
        if self._backend == "trio":
            self._event = trio.Event()
        else:
            # Note: asyncio.Event has better performance characteristics than anyio.Event
            self._event = asyncio.Event()

    def set(self) -> None:
        if self._event is None:
            self.setup()
        event: _EventProto = self._event  # type: ignore[assignment]
        event.set()

    async def wait(self, timeout: Optional[float] = None) -> None:
        if self._event is None:
            self.setup()
        event: _EventProto = self._event  # type: ignore[assignment]

        if self._backend == "trio":
            trio_exc_map: ExceptionMapping = {trio.TooSlowError: PoolTimeout}
            timeout_or_inf = float("inf") if timeout is None else timeout
            with map_exceptions(trio_exc_map):
                with trio.fail_after(timeout_or_inf):
                    await event.wait()
        else:
            asyncio_exc_map: ExceptionMapping = {
                asyncio.exceptions.TimeoutError: PoolTimeout
            }
            with map_exceptions(asyncio_exc_map):
                async with asyncio_timeout.timeout(timeout):
                    await event.wait()


class AsyncSemaphore:
    def __init__(self, bound: int) -> None:
        self._bound = bound
        self._semaphore: Optional[_LockProto] = None

    def setup(self) -> None:
        """
        Detect if we're running under 'asyncio' or 'trio' and create
        a semaphore with the correct implementation.
        """
        if current_async_backend() == "trio":
            self._semaphore = trio.Semaphore(
                initial_value=self._bound, max_value=self._bound
            )
        else:
            # Note: asyncio.BoundedSemaphore has better performance characteristics than anyio.Semaphore
            self._semaphore = asyncio.BoundedSemaphore(self._bound)

    async def acquire(self) -> None:
        if self._semaphore is None:
            self.setup()
        semaphore: _LockProto = self._semaphore  # type: ignore[assignment]
        await semaphore.acquire()

    async def release(self) -> None:
        semaphore: _LockProto = self._semaphore  # type: ignore[assignment]
        semaphore.release()


async def async_cancel_shield(
    shielded: Callable[[], Coroutine[Any, Any, None]],
) -> None:
    if current_async_backend() == "trio":
        with trio.CancelScope(shield=True):
            await shielded()
    else:
        inner_task = asyncio.create_task(shielded())
        retry = False
        while True:
            try:
                await asyncio.shield(inner_task)
                break
            except asyncio.CancelledError:
                if inner_task.done() or retry:
                    break
                # We may get multiple cancellations.
                # Retry once to get inner_task finished here by best effort.
                retry = True
                continue


# Our thread-based synchronization primitives...


class Lock:
    """
    This is a standard lock.

    In the sync case `Lock` provides thread locking.
    In the async case `AsyncLock` provides async locking.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> "Lock":
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        self._lock.release()


class ThreadLock:
    """
    This is a threading-only lock for no-I/O contexts.

    In the sync case `ThreadLock` provides thread locking.
    In the async case `AsyncThreadLock` is a no-op.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> "ThreadLock":
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        self._lock.release()


class Event:
    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    def wait(self, timeout: Optional[float] = None) -> None:
        if timeout == float("inf"):  # pragma: no cover
            timeout = None
        if not self._event.wait(timeout=timeout):
            raise PoolTimeout()  # pragma: nocover


class Semaphore:
    def __init__(self, bound: int) -> None:
        self._semaphore = threading.Semaphore(value=bound)

    def acquire(self) -> None:
        self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()


# Thread-synchronous codebases don't support cancellation semantics.
# We have this class because we need to mirror the async and sync
# cases within our package, but it's just a no-op.
def sync_cancel_shield(fn: Callable[[], None]) -> None:
    fn()
