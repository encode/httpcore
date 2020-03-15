import asyncio
import threading
import time
import typing

import pytest
from mitmproxy import master, options, proxy
from mitmproxy.tools.dump import DumpMaster


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


@pytest.fixture
def proxy_server():
    host, port = "127.0.0.1", 8080

    class ProxyWrapper(threading.Thread):
        def run(self):
            # mitmproxy uses asyncio internally but the default loop policy
            # will only create event loops for the main thread, create one
            # as part of the thread startup
            asyncio.set_event_loop(asyncio.new_event_loop())
            opts = options.Options(listen_host=host, listen_port=port)
            pconf = proxy.config.ProxyConfig(opts)

            self.master = DumpMaster(opts)
            self.master.server = proxy.server.ProxyServer(pconf)
            self.master.run()

        def join(self):
            self.master.shutdown()
            super().join()

    try:
        thread = ProxyWrapper()
        thread.start()
        time.sleep(2)  # TODO: there's probably a better way to do this
        yield (host, port)
    finally:
        thread.join()
