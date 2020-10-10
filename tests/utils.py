import contextlib
import functools
import socket
import subprocess
import threading
import time
from typing import Callable, Iterator, Tuple

import sniffio
import trio

try:
    from hypercorn import config as hypercorn_config, trio as hypercorn_trio
except ImportError:  # pragma: no cover
    # Python 3.6.
    hypercorn_config = None  # type: ignore
    hypercorn_trio = None  # type: ignore


def lookup_async_backend():
    return sniffio.current_async_library()


def lookup_sync_backend():
    return "sync"


def _wait_can_connect(host: str, port: int):
    while True:
        try:
            sock = socket.create_connection((host, port))
        except ConnectionRefusedError:
            time.sleep(0.25)
        else:
            sock.close()
            break


class Server:
    """
    Base interface for servers we can test against.
    """

    @property
    def sends_reason(self) -> bool:
        raise NotImplementedError  # pragma: no cover

    @property
    def netloc(self) -> Tuple[bytes, int]:
        raise NotImplementedError  # pragma: no cover

    @property
    def host_header(self) -> Tuple[bytes, bytes]:
        raise NotImplementedError  # pragma: no cover


class LiveServer(Server):  # pragma: no cover
    """
    A test server running on a live location.
    """

    sends_reason = True

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    @property
    def netloc(self) -> Tuple[bytes, int]:
        return (self._host.encode("ascii"), self._port)

    @property
    def host_header(self) -> Tuple[bytes, bytes]:
        return (b"host", self._host.encode("ascii"))


class HypercornServer(Server):  # pragma: no cover
    """
    A test server running in-process, powered by Hypercorn.
    """

    sends_reason = False

    def __init__(
        self,
        app: Callable,
        host: str,
        port: int,
        bind: str = None,
        certfile: str = None,
        keyfile: str = None,
    ) -> None:
        assert hypercorn_config is not None
        self._app = app
        self._host = host
        self._port = port
        self._config = hypercorn_config.Config()
        self._config.bind = [bind or f"{host}:{port}"]
        self._config.certfile = certfile
        self._config.keyfile = keyfile
        self._config.worker_class = "asyncio"
        self._started = False
        self._should_exit = False

    @property
    def netloc(self) -> Tuple[bytes, int]:
        return (self._host.encode("ascii"), self._port)

    @property
    def host_header(self) -> Tuple[bytes, bytes]:
        return (b"host", self._host.encode("ascii"))

    def _run(self) -> None:
        async def shutdown_trigger() -> None:
            while not self._should_exit:
                await trio.sleep(0.01)

        serve = functools.partial(
            hypercorn_trio.serve, shutdown_trigger=shutdown_trigger
        )

        async def main() -> None:
            async with trio.open_nursery() as nursery:
                await nursery.start(serve, self._app, self._config)
                self._started = True

        trio.run(main)

    @contextlib.contextmanager
    def serve_in_thread(self) -> Iterator[None]:
        thread = threading.Thread(target=self._run)
        thread.start()
        try:
            while not self._started:
                time.sleep(1e-3)
            yield
        finally:
            self._should_exit = True
            thread.join()


@contextlib.contextmanager
def http_proxy_server(proxy_host: str, proxy_port: int):

    proc = None
    try:
        command = ["pproxy", "-l", f"http://{proxy_host}:{proxy_port}/"]
        proc = subprocess.Popen(command)

        _wait_can_connect(proxy_host, proxy_port)

        yield b"http", proxy_host.encode(), proxy_port, b"/"
    finally:
        if proc is not None:
            proc.kill()
