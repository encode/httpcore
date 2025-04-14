import socket
import time
from contextlib import contextmanager
from threading import Thread
from typing import Any, Awaitable, Callable, Generator, Iterator, List, Optional

import pytest
import uvicorn

from httpcore import AnyIOBackend, AsyncIOBackend
from httpcore._backends.auto import AutoBackend


@pytest.fixture(
    params=[
        pytest.param(("asyncio", {"httpcore_use_anyio": False}), id="asyncio"),
        pytest.param(("asyncio", {"httpcore_use_anyio": True}), id="asyncio+anyio"),
        pytest.param(("trio", {}), id="trio"),
    ]
)
def anyio_backend(request, monkeypatch):
    backend_name, options = request.param
    options = {**options}
    use_anyio = options.pop("httpcore_use_anyio", False)

    # TODO remove this marker once we have a way to define the asyncio backend in AutoBackend
    no_auto_backend_patch = bool(
        request.node.get_closest_marker("no_auto_backend_patch")
    )

    if backend_name != "trio" and not no_auto_backend_patch:
        # TODO replace with a proper interface in AutoBackend to setup either the AnyIO or asyncio backend
        async def patch_init_backend(auto_backend: AutoBackend) -> None:
            if hasattr(auto_backend, "_backend"):
                return
            auto_backend._backend = AnyIOBackend() if use_anyio else AsyncIOBackend()

        monkeypatch.setattr(AutoBackend, "_init_backend", patch_init_backend)

    return backend_name, options


class Server(uvicorn.Server):
    @contextmanager
    def run_in_thread(
        self, sockets: Optional[List[socket.socket]] = None
    ) -> Generator[None, None, None]:
        thread = Thread(target=lambda: self.run(sockets))
        thread.start()
        start_time = time.monotonic()
        try:
            while not self.started:
                time.sleep(0.01)
                if (time.monotonic() - start_time) > 5:
                    raise TimeoutError()  # pragma: nocover
            yield
        finally:
            self.should_exit = True
            thread.join()


@pytest.fixture
def server_port() -> int:
    return 1111


@pytest.fixture
def server_url(server_port: int) -> str:
    return f"http://127.0.0.1:{server_port}"


@pytest.fixture
def server_app() -> Callable[[Any, Any, Any], Awaitable[None]]:
    async def app(scope, receive, send):
        assert scope["type"] == "http"
        assert not (await receive()).get("more_body", False)

        start = {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
        body = {"type": "http.response.body", "body": b"Hello World"}
        await send(start)
        await send(body)

    return app


@pytest.fixture
def server_config(
    server_port: int, server_app: Callable[[Any, Any, Any], Awaitable[None]]
) -> uvicorn.Config:
    return uvicorn.Config(server_app, port=server_port, log_level="error")


@pytest.fixture
def server(server_config: uvicorn.Config) -> Iterator[None]:
    with Server(server_config).run_in_thread():
        yield
