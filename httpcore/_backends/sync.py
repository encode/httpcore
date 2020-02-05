from ssl import SSLContext
from typing import Dict, Optional
import socket
from .._exceptions import NetworkError, ConnectTimeout


class SyncSocketStream:
    """
    A socket stream with read/write operations. Abstracts away any asyncio-specific
    interfaces into a more generic base class, that we can use with alternate
    backends, or for stand-alone test cases.
    """
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock

    def read(self, n: int, timeout: Dict[str, Optional[float]]) -> bytes:
        return self.sock.recv(n)

    def write(self, data: bytes, timeout: Dict[str, Optional[float]]) -> None:
        while data:
            n = self.sock.send(data)
            data = data[n:]

    def close(self) -> None:
        self.sock.close()


class SyncBackend:
    def open_tcp_stream(
        self,
        hostname: bytes,
        port: int,
        ssl_context: Optional[SSLContext],
        timeout: Dict[str, Optional[float]],
    ) -> SyncSocketStream:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout.get('connect'))
            sock.connect((hostname.decode('ascii'), port))
            if ssl_context is not None:
                sock = ssl_context.wrap_socket(sock, server_hostname=hostname.decode('ascii'))
        except socket.timeout:
            raise ConnectTimeout()
        except socket.error:
            raise NetworkError()

        return SyncSocketStream(sock=sock)
