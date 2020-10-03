import contextlib
import os
import threading
import time
import typing

import pytest
import uvicorn

from httpcore._types import URL

from .utils import Server, http_proxy_server

SERVER_HOST = "example.org"
HTTPS_SERVER_URL = "https://example.org"


@pytest.fixture(scope="session")
def proxy_server() -> typing.Iterator[URL]:
    proxy_host = "127.0.0.1"
    proxy_port = 8080

    with http_proxy_server(proxy_host, proxy_port) as proxy_server_fixture:
        yield proxy_server_fixture


class UvicornServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        pass

    @contextlib.contextmanager
    def serve_in_thread(self) -> typing.Iterator[None]:
        thread = threading.Thread(target=self.run)
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        finally:
            self.should_exit = True
            thread.join()


async def app(scope: dict, receive: typing.Callable, send: typing.Callable) -> None:
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


@pytest.fixture(scope="session")
def uds_server() -> typing.Iterator[UvicornServer]:
    uds = "test_server.sock"
    config = uvicorn.Config(app=app, lifespan="off", loop="asyncio", uds=uds)
    server = UvicornServer(config=config)
    try:
        with server.serve_in_thread():
            yield server
    finally:
        os.remove(uds)


@pytest.fixture(scope="session")
def server() -> Server:
    return Server(SERVER_HOST, port=80)


@pytest.fixture(scope="session")
def https_server() -> Server:
    return Server(SERVER_HOST, port=443)
