import threading
from types import TracebackType
from typing import Optional, Type


class ThreadLock:
    """
    Provides thread safety when used as a sync context manager, or a
    no-op when used as an async context manager.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()

    def __enter__(self) -> None:
        self.lock.acquire()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        self.lock.release()

    async def __aenter__(self) -> None:
        pass

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        pass
