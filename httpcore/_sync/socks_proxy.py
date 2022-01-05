import typing

from socksio import socks5

from .._exceptions import ProxyError
from ..backends.base import NetworkStream

AUTH_METHODS = {
    b"\x00": "NO AUTHENTICATION REQUIRED",
    b"\x01": "GSSAPI",
    b"\x02": "USERNAME/PASSWORD",
    b"\xff": "NO ACCEPTABLE METHODS",
}

REPLY_CODES = {
    b"\x00": "Succeeded",
    b"\x01": "General SOCKS server failure",
    b"\x02": "Connection not allowed by ruleset",
    b"\x03": "Network unreachable",
    b"\x04": "Host unreachable",
    b"\x05": "Connection refused",
    b"\x06": "TTL expired",
    b"\x07": "Command not supported",
    b"\x08": "Address type not supported",
}


def _init_socks5_connection(
    stream: NetworkStream,
    *,
    host: bytes,
    port: int,
    auth: typing.Tuple[bytes, bytes] = None,
) -> None:
    conn = socks5.SOCKS5Connection()

    # Auth method request
    auth_method = (
        socks5.SOCKS5AuthMethod.NO_AUTH_REQUIRED
        if auth is None
        else socks5.SOCKS5AuthMethod.USERNAME_PASSWORD
    )
    conn.send(socks5.SOCKS5AuthMethodsRequest([auth_method]))
    outgoing_bytes = conn.data_to_send()
    stream.write(outgoing_bytes)

    # Auth method response
    incoming_bytes = stream.read(max_bytes=4096)
    response = conn.receive_data(incoming_bytes)
    assert isinstance(response, socks5.SOCKS5AuthReply)
    if response.method != auth_method:
        requested = AUTH_METHODS.get(auth_method, "UNKNOWN")
        responded = AUTH_METHODS.get(response.method, "UNKNOWN")
        raise ProxyError(
            f"Requested {requested} from proxy server, but got {responded}."
        )

    if response.method == socks5.SOCKS5AuthMethod.USERNAME_PASSWORD:
        # Username/password request
        assert auth is not None
        username, password = auth
        conn.send(socks5.SOCKS5UsernamePasswordRequest(username, password))
        outgoing_bytes = conn.data_to_send()
        stream.write(outgoing_bytes)

        # Username/password response
        incoming_bytes = stream.read(max_bytes=4096)
        response = conn.receive_data(incoming_bytes)
        assert isinstance(response, socks5.SOCKS5UsernamePasswordReply)
        if not response.success:
            raise ProxyError("Invalid username/password")

    # Connect request
    conn.send(
        socks5.SOCKS5CommandRequest.from_address(
            socks5.SOCKS5Command.CONNECT, (host, port)
        )
    )
    outgoing_bytes = conn.data_to_send()
    stream.write(outgoing_bytes)

    # Connect response
    incoming_bytes = stream.read(max_bytes=4096)
    response = conn.receive_data(incoming_bytes)
    assert isinstance(response, socks5.SOCKS5Reply)
    if response.reply_code != socks5.SOCKS5ReplyCode.SUCCEEDED:
        reply_code = REPLY_CODES.get(response.reply_code, "UNKOWN")
        raise ProxyError(f"Proxy Server could not connect: {reply_code}.")
