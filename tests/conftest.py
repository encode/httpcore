import asyncio
import ssl
import threading
import typing

import pytest
import trustme
from mitmproxy import options, proxy
from mitmproxy.tools.dump import DumpMaster

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080


@pytest.fixture(
    params=[
        pytest.param("asyncio", marks=pytest.mark.asyncio),
        pytest.param("trio", marks=pytest.mark.trio),
    ]
)
def async_environment(request: typing.Any) -> str:
    """
    Mark a test function to be run on both asyncio and trio.

    Equivalent to having a pair of tests, each respectively marked with
    '@pytest.mark.asyncio' and '@pytest.mark.trio'.

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


@pytest.fixture(scope="session")
def ca_ssl_context(cert_authority: trustme.CA) -> ssl.SSLContext:
    ctx = ssl.SSLContext()
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
def proxy_server(
    example_org_cert_path: str,
) -> typing.Iterator[typing.Tuple[bytes, bytes, int]]:
    """Starts a proxy server on a different thread and yields its origin tuple.

    The server is configured to use a trustme CA and key, this will allow our
    test client to make HTTPS requests when using the ca_ssl_context fixture
    above.

    Note this is only required because mitmproxy's main purpose is to analyse
    traffic. Other proxy server do not need this but mitmproxy is easier to
    intregrate in our tests.
    """
    try:
        # TODO: the ssl_insecure flag prevents an error raised from mitmproxy:
        # TlsException("Cannot validate certificate hostname without SNI")
        thread = ProxyWrapper(
            PROXY_HOST, PROXY_PORT, ssl_insecure=True, certs=[example_org_cert_path]
        )
        thread.start()
        thread.notify.started.wait()
        yield (b"http", PROXY_HOST.encode(), PROXY_PORT)
    finally:
        thread.join()
