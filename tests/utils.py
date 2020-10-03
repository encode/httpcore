from typing import Tuple

import sniffio


def lookup_async_backend():
    return sniffio.current_async_library()


def lookup_sync_backend():
    return "sync"


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
