import socket
import ssl
import threading
import typing

import pytest
import trustme

TCP_ADDRESS: typing.Optional[typing.Tuple[str, int]] = None
TLS_ADDRESS: typing.Optional[typing.Tuple[str, int]] = None
TLS_IN_TLS_ADDRESS: typing.Optional[typing.Tuple[str, int]] = None

tcp_started = threading.Event()
tls_started = threading.Event()
tls_in_tls_started = threading.Event()

CA = trustme.CA()

SERVER_CONTEXT = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_SERVER)
server_cert = CA.issue_cert("localhost")
server_cert.configure_cert(SERVER_CONTEXT)

SOCKET_READ_WRITE_TIMEOUT = 0.5


class Address(typing.NamedTuple):
    host: str
    port: int


def handle_connection(client_sock: socket.socket) -> None:
    with client_sock:
        while True:
            try:
                buffer = client_sock.recv(1024)
                if not buffer:
                    break
                client_sock.sendall(buffer)
            except ConnectionResetError:  # pragma: no cover
                # This error can occur when the client has
                # data in the kernel buffer but closes the
                # connection, as in write tests when we
                # are writing data and closing the
                # connection without reading incoming data.
                break
            except ssl.SSLEOFError:  # pragma: no cover
                # This error is similar to `ConnectionResetError`,
                # but it only occurs in TLS connections.
                break
            except BrokenPipeError:  # pragma: no cover
                # When FIN packets were sent and we attempted to write data
                break


def handle_tunnel_connection(client_sock: socket.socket) -> None:
    remote_socket = socket.create_connection(TLS_ADDRESS)  # type: ignore
    with client_sock, remote_socket:
        while True:
            try:
                
                try:
                    client_sock.settimeout(SOCKET_READ_WRITE_TIMEOUT)
                    buffer = client_sock.recv(1024)
                    remote_socket.sendall(buffer)
                except socket.timeout:
                    pass

                try:
                    remote_socket.settimeout(SOCKET_READ_WRITE_TIMEOUT)
                    buffer = remote_socket.recv(1024)
                    client_sock.sendall(buffer)
                except socket.timeout:
                    pass
            except ssl.SSLEOFError:  # pragma: no cover
                break
            except BrokenPipeError:  # pragma: no cover
                break


def start_tcp() -> None:
    global TCP_ADDRESS
    with socket.socket() as sock:
        sock.listen()
        TCP_ADDRESS = sock.getsockname()
        tcp_started.set()

        while True:
            client_sock = sock.accept()[0]
            threading.Thread(
                target=handle_connection, daemon=True, args=(client_sock,)
            ).start()


def start_tls() -> None:
    global TLS_ADDRESS
    with socket.socket() as sock:
        sock.listen()
        TLS_ADDRESS = sock.getsockname()
        tls_started.set()

        with SERVER_CONTEXT.wrap_socket(sock, server_side=True) as tls_sock:
            while True:
                client_sock = tls_sock.accept()[0]
                threading.Thread(
                    target=handle_connection, daemon=True, args=(client_sock,)
                ).start()


def start_tls_in_tls() -> None:
    global TLS_IN_TLS_ADDRESS
    tls_started.wait()
    with socket.socket() as sock:
        sock.listen()
        TLS_IN_TLS_ADDRESS = sock.getsockname()
        tls_in_tls_started.set()

        with SERVER_CONTEXT.wrap_socket(sock, server_side=True) as tls_sock:
            while True:
                client_sock = tls_sock.accept()[0]
                threading.Thread(
                    target=handle_tunnel_connection, daemon=True, args=(client_sock,)
                ).start()


@pytest.fixture
def client_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    CA.configure_trust(context)
    return context

@pytest.fixture(scope="session")
def tls_in_tls_server(tls_server) -> Address:
    threading.Thread(target=start_tls_in_tls, daemon=True).start()
    tls_in_tls_started.wait()
    assert TLS_IN_TLS_ADDRESS
    host, port = TLS_IN_TLS_ADDRESS
    return Address(host, port)

@pytest.fixture(scope="session")
def tls_server() -> Address:
    threading.Thread(target=start_tls, daemon=True).start()
    tls_started.wait()
    assert TLS_ADDRESS
    host, port = TLS_ADDRESS
    return Address(host, port)


@pytest.fixture(scope="session")
def tcp_server() -> Address:
    threading.Thread(target=start_tcp, daemon=True).start()
    tcp_started.wait()
    assert TCP_ADDRESS
    host, port = TCP_ADDRESS
    return Address(host, port)
