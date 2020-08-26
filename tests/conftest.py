import asyncio
import contextlib
import os
import ssl
import threading
import time
import typing

import pytest
import trustme
import uvicorn
from mitmproxy import options, proxy
from mitmproxy.tools.dump import DumpMaster

from httpcore._types import URL

from .marks.curio import curio_pytest_pycollect_makeitem, curio_pytest_pyfunc_call

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080


@pytest.mark.tryfirst
def pytest_pycollect_makeitem(collector, name, obj):
    curio_pytest_pycollect_makeitem(collector, name, obj)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    yield from curio_pytest_pyfunc_call(pyfuncitem)


@pytest.fixture(
    params=[
        pytest.param("asyncio", marks=pytest.mark.asyncio),
        pytest.param("trio", marks=pytest.mark.trio),
        pytest.param("curio", marks=pytest.mark.curio),
    ]
)
def async_environment(request: typing.Any) -> str:
    """
    Mark a test function to be run on asyncio, trio and curio.

    Equivalent to having three tests, each respectively marked with
    '@pytest.mark.asyncio', '@pytest.mark.trio' and '@pytest.mark.curio'.

    Intended usage:

    ```
    @pytest.mark.usefixtures("async_environment")
    async def my_async_test():
        ...
    ```
    """
    return request.param


class RunNotify:
    """A mitmproxy addon wrapping an event to notify us when the server is running."""

    def __init__(self) -> None:
        self.started = threading.Event()

    def running(self) -> None:
        self.started.set()


class ProxyWrapper(threading.Thread):
    """Runs an mitmproxy in a separate thread."""

    def __init__(self, host: str, port: int, **kwargs: typing.Any) -> None:
        self.host = host
        self.port = port
        self.options = kwargs
        super().__init__()
        self.notify = RunNotify()

    def run(self) -> None:
        # mitmproxy uses asyncio internally but the default loop policy
        # will only create event loops for the main thread, create one
        # as part of the thread startup
        asyncio.set_event_loop(asyncio.new_event_loop())
        opts = options.Options(
            listen_host=self.host, listen_port=self.port, **self.options
        )
        pconf = proxy.config.ProxyConfig(opts)

        self.master = DumpMaster(opts)
        self.master.server = proxy.server.ProxyServer(pconf)
        self.master.addons.add(self.notify)
        self.master.run()

    def join(self, timeout: float = None) -> None:
        self.master.shutdown()
        super().join()


@pytest.fixture(scope="session")
def cert_authority() -> trustme.CA:
    return trustme.CA()


@pytest.fixture()
def ca_ssl_context(cert_authority: trustme.CA) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    cert_authority.configure_trust(ctx)
    return ctx


@pytest.fixture(scope="session")
def example_org_cert(cert_authority: trustme.CA) -> trustme.LeafCert:
    return cert_authority.issue_cert("example.org")


@pytest.fixture(scope="session")
def example_org_cert_path(example_org_cert: trustme.LeafCert) -> typing.Iterator[str]:
    with example_org_cert.private_key_and_cert_chain_pem.tempfile() as tmp:
        yield tmp


@pytest.fixture()
def proxy_server(example_org_cert_path: str) -> typing.Iterator[URL]:
    """Starts a proxy server on a different thread and yields its origin tuple.

    The server is configured to use a trustme CA and key, this will allow our
    test client to make HTTPS requests when using the ca_ssl_context fixture
    above.

    Note this is only required because mitmproxy's main purpose is to analyse
    traffic. Other proxy servers do not need this but mitmproxy is easier to
    integrate in our tests.
    """
    try:
        thread = ProxyWrapper(PROXY_HOST, PROXY_PORT, certs=[example_org_cert_path])
        thread.start()
        thread.notify.started.wait()
        yield (b"http", PROXY_HOST.encode(), PROXY_PORT, b"/")
    finally:
        thread.join()


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
