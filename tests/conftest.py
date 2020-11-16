import contextlib
import os
import threading
import time
import typing

import pytest
import trustme

from httpcore._types import URL

from .utils import HypercornServer, LiveServer, Server, http_proxy_server

try:
    import hypercorn
except ImportError:  # pragma: no cover  # Python 3.6
    hypercorn = None  # type: ignore
    SERVER_HOST = "example.org"
    SERVER_HTTP_PORT = 80
    SERVER_HTTPS_PORT = 443
    HTTPS_SERVER_URL = "https://example.org"
else:
    SERVER_HOST = "localhost"
    SERVER_HTTP_PORT = 8002
    SERVER_HTTPS_PORT = 8003
    HTTPS_SERVER_URL = f"https://localhost:{SERVER_HTTPS_PORT}"


@pytest.fixture(scope="session")
def proxy_server() -> typing.Iterator[URL]:
    proxy_host = "127.0.0.1"
    proxy_port = 8080

    with http_proxy_server(proxy_host, proxy_port) as proxy_url:
        yield proxy_url


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
def uds() -> typing.Iterator[str]:
    uds = "test_server.sock"
    try:
        yield uds
    finally:
        os.remove(uds)


@pytest.fixture(scope="session")
def uds_server(uds: str) -> typing.Iterator[Server]:
    if hypercorn is not None:
        server = HypercornServer(app=app, bind=f"unix:{uds}")
        with server.serve_in_thread():
            yield server
    else:
        # On Python 3.6, use Uvicorn as a fallback.
        import uvicorn

        class UvicornServer(Server, uvicorn.Server):
            sends_reason = True

            @property
            def uds(self) -> str:
                uds = self.config.uds
                assert uds is not None
                return uds

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

        config = uvicorn.Config(app=app, lifespan="off", loop="asyncio", uds=uds)
        server = UvicornServer(config=config)
        with server.serve_in_thread():
            yield server


@pytest.fixture(scope="session")
def server() -> typing.Iterator[Server]:  # pragma: no cover
    server: Server  # Please mypy.

    if hypercorn is None:
        server = LiveServer(host=SERVER_HOST, port=SERVER_HTTP_PORT)
        yield server
        return

    server = HypercornServer(app=app, bind=f"{SERVER_HOST}:{SERVER_HTTP_PORT}")
    with server.serve_in_thread():
        yield server


@pytest.fixture(scope="session")
def cert_authority() -> trustme.CA:
    return trustme.CA()


@pytest.fixture(scope="session")
def localhost_cert(cert_authority: trustme.CA) -> trustme.LeafCert:
    return cert_authority.issue_cert("localhost")


@pytest.fixture(scope="session")
def localhost_cert_path(localhost_cert: trustme.LeafCert) -> typing.Iterator[str]:
    with localhost_cert.private_key_and_cert_chain_pem.tempfile() as tmp:
        yield tmp


@pytest.fixture(scope="session")
def localhost_cert_pem_file(localhost_cert: trustme.LeafCert) -> typing.Iterator[str]:
    with localhost_cert.cert_chain_pems[0].tempfile() as tmp:
        yield tmp


@pytest.fixture(scope="session")
def localhost_cert_private_key_file(
    localhost_cert: trustme.LeafCert,
) -> typing.Iterator[str]:
    with localhost_cert.private_key_pem.tempfile() as tmp:
        yield tmp


@pytest.fixture(scope="session")
def https_server(
    localhost_cert_pem_file: str, localhost_cert_private_key_file: str
) -> typing.Iterator[Server]:  # pragma: no cover
    server: Server  # Please mypy.

    if hypercorn is None:
        server = LiveServer(host=SERVER_HOST, port=SERVER_HTTPS_PORT)
        yield server
        return

    server = HypercornServer(
        app=app,
        bind=f"{SERVER_HOST}:{SERVER_HTTPS_PORT}",
        certfile=localhost_cert_pem_file,
        keyfile=localhost_cert_private_key_file,
    )
    with server.serve_in_thread():
        yield server


@pytest.fixture(scope="function")
def too_many_open_files_minus_one() -> typing.Iterator[None]:
    # Fixture for test regression on https://github.com/encode/httpcore/issues/182
    # Max number of descriptors chosen according to:
    # See: https://man7.org/linux/man-pages/man2/select.2.html#top_of_page
    # "To monitor file descriptors greater than 1023, use poll or epoll instead."
    max_num_descriptors = 1023

    files = []

    while True:
        f = open("/dev/null")
        # Leave one file descriptor available for a transport to perform
        # a successful request.
        if f.fileno() > max_num_descriptors - 1:
            f.close()
            break
        files.append(f)

    try:
        yield
    finally:
        for f in files:
            f.close()
