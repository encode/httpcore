import contextlib
import os
import shlex
import socket
import ssl
import subprocess
import threading
import time
import typing

import pytest
import trustme
import uvicorn

from httpcore._types import Origin, SocksProxyCredentials, URL


@pytest.fixture(scope="session")
def cert_authority() -> trustme.CA:
    return trustme.CA()


@pytest.fixture()
def ca_ssl_context(cert_authority: trustme.CA) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    cert_authority.configure_trust(ctx)
    return ctx


def wait_until_pproxy_serve_on_port(host: str, port: int):
    while True:
        try:
            sock = socket.create_connection((host, port))
        except ConnectionRefusedError:
            time.sleep(0.25)
        else:
            sock.close()
            break


@pytest.fixture(scope="session")
def proxy_server() -> typing.Iterator[URL]:
    http_proxy_host = "127.0.0.1"
    http_proxy_port = 8080

    proc = None
    try:
        command_str = f"pproxy -l http://{http_proxy_host}:{http_proxy_port}/"
        command = shlex.split(command_str)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        wait_until_pproxy_serve_on_port(http_proxy_host, http_proxy_port)

        print(f"HTTP proxy started on http://{http_proxy_host}:{http_proxy_port}/")

        yield b"http", http_proxy_host.encode(), http_proxy_port, b"/"
    finally:
        if proc is not None:
            proc.kill()


SocksFixture = typing.NamedTuple(
    "SocksFixture",
    [
        ("with_auth", typing.Tuple[Origin, SocksProxyCredentials]),
        ("without_auth", Origin),
    ],
)


@pytest.fixture(scope="session")
def socks_proxy() -> typing.Iterator[SocksFixture]:
    no_auth_host = "127.0.01"
    no_auth_port = 1085

    auth_host = "127.0.0.1"
    auth_port = 1086
    auth_user = "username"
    auth_pwd = "password"

    proc = None
    try:
        command_str = (
            f"pproxy -l socks5://{no_auth_host}:{no_auth_port} "
            f"--auth 0 -l 'socks5://{auth_host}:{auth_port}#{auth_user}:{auth_pwd}'"
        )

        command = shlex.split(command_str)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        wait_until_pproxy_serve_on_port(auth_host, auth_port)
        wait_until_pproxy_serve_on_port(no_auth_host, no_auth_port)

        yield SocksFixture(
            with_auth=(
                (
                    b"socks5",
                    auth_host.encode(),
                    auth_port,
                ),
                SocksProxyCredentials(auth_user.encode(), auth_pwd.encode()),
            ),
            without_auth=(b"socks5", no_auth_host.encode(), no_auth_port),
        )
    finally:
        if proc is not None:
            proc.kill()


class Server(uvicorn.Server):
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
def uds_server() -> typing.Iterator[Server]:
    uds = "test_server.sock"
    config = uvicorn.Config(app=app, lifespan="off", loop="asyncio", uds=uds)
    server = Server(config=config)
    try:
        with server.serve_in_thread():
            yield server
    finally:
        os.remove(uds)
