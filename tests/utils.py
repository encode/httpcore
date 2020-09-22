import contextlib
import functools
import threading
import time
from typing import Callable, Iterator, Tuple

import hypercorn.config
import hypercorn.trio
import sniffio
import trio


def lookup_async_backend():
    return sniffio.current_async_library()


def lookup_sync_backend():
    return "sync"


class Server:
    """
    A local ASGI server, using Hypercorn.
    """

    def __init__(
        self,
        app: Callable,
        host: str,
        port: int,
        bind: str = None,
        certfile: str = None,
        keyfile: str = None,
    ) -> None:
        if bind is None:
            bind = f"{host}:{port}"

        self.app = app
        self.host = host
        self.port = port
        self.config = hypercorn.config.Config()
        self.config.bind = [bind]
        self.config.certfile = certfile
        self.config.keyfile = keyfile
        self.config.worker_class = "trio"
        self.started = False
        self.should_exit = False

    @property
    def netloc(self) -> Tuple[bytes, int]:
        return (self.host.encode("utf-8"), self.port)

    def host_header(self) -> Tuple[bytes, bytes]:
        return (b"host", self.host.encode("utf-8"))

    def run(self) -> None:
        async def shutdown_trigger() -> None:
            while not self.should_exit:
                await trio.sleep(0.01)

        serve = functools.partial(
            hypercorn.trio.serve, shutdown_trigger=shutdown_trigger
        )

        async def main() -> None:
            async with trio.open_nursery() as nursery:
                await nursery.start(serve, self.app, self.config)
                self.started = True

        trio.run(main)

    @contextlib.contextmanager
    def serve_in_thread(self) -> Iterator[None]:
        thread = threading.Thread(target=self.run)
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        finally:
            self.should_exit = True
            thread.join()
