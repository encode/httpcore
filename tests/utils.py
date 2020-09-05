import socket
from typing import Any, Tuple

from httpcore._backends.asyncio import SocketStream as AsyncIOSocketStream
from httpcore._backends.curio import SocketStream as CurioSocketStream
from httpcore._backends.sync import SyncSocketStream


def get_local_ip_address() -> str:
    return socket.gethostbyname(socket.gethostname())


def getsockname(stream: Any) -> Tuple[str, int]:
    if isinstance(stream, AsyncIOSocketStream):
        sock = stream.stream_reader._transport.get_extra_info("socket")  # type: ignore
    elif isinstance(stream, CurioSocketStream):
        sock = stream.socket._socket
    elif isinstance(stream, SyncSocketStream):
        sock = stream.sock
    else:  # pragma: no cover
        raise NotImplementedError(stream)

    return sock.getsockname()
