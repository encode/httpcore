import contextlib
import socket
import subprocess
import tempfile
import time
from typing import List, Tuple

import sniffio


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
    Represents the server we're testing against.
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    @property
    def netloc(self) -> Tuple[bytes, int]:
        return (self._host.encode("ascii"), self._port)

    @property
    def host_header(self) -> Tuple[bytes, bytes]:
        return (b"host", self._host.encode("utf-8"))


@contextlib.contextmanager
def http_proxy_server(proxy_host: str, proxy_port: int):
    """
    This function launches pproxy process like this:
    $ pproxy -b <blocked_hosts_file> -l http://127.0.0.1:8080
    What does it mean?
    It runs HTTP proxy on 127.0.0.1:8080 and blocks access to some external hosts,
        specified in blocked_hosts_file

    Relevant pproxy docs could be found in their github repo:
        https://github.com/qwj/python-proxy
    """
    proc = None

    with create_proxy_block_file(["blockedhost.example.com"]) as block_file_name:
        try:
            command = [
                "pproxy",
                "-b",
                block_file_name,
                "-l",
                f"http://{proxy_host}:{proxy_port}/",
            ]
            proc = subprocess.Popen(command)

            _wait_can_connect(proxy_host, proxy_port)

            yield b"http", proxy_host.encode(), proxy_port, b"/"
        finally:
            if proc is not None:
                proc.kill()


@contextlib.contextmanager
def create_proxy_block_file(blocked_domains: List[str]):
    """
    The context manager yields pproxy block file.
    This file should contain line delimited hostnames. We use it in the following test:
        test_proxy_socket_does_not_leak_when_the_connection_hasnt_been_added_to_pool
    """
    with tempfile.NamedTemporaryFile(delete=True, mode="w+") as file:

        for domain in blocked_domains:
            file.write(domain)
            file.write("\n")

        file.flush()

        yield file.name
