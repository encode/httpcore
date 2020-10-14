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

    proc = None

    with create_proxy_block_file(["example.com"]) as block_file_name:
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
    with tempfile.NamedTemporaryFile(delete=True, mode="w+") as file:

        for domain in blocked_domains:
            file.write(domain)
            file.write("\n")

        file.flush()

        yield file.name
