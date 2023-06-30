import socket
import ssl
import threading
from typing import NamedTuple

import pytest
import trustme


class Address(NamedTuple):
    host: str
    port: int


TCP_ADDRESS = None
TLS_ADDRESS = None

CA = trustme.CA()

SERVER_CONTEXT = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_SERVER)
server_cert = CA.issue_cert("localhost")
server_cert.configure_cert(SERVER_CONTEXT)


def handle_connection(client_sock: socket.socket) -> None:
    with client_sock:
        while True:
            try:
                buffer = client_sock.recv(1024)
                if not buffer:
                    break
                client_sock.sendall(buffer)
            except ConnectionResetError:  # pragma: no cover
                break
            except ssl.SSLEOFError:  # pragma: no cover
                break


def start_tcp(event: threading.Event) -> None:
    global TCP_ADDRESS
    with socket.socket() as sock:
        sock.listen()
        TCP_ADDRESS = sock.getsockname()
        event.set()

        while True:
            client_sock = sock.accept()[0]
            threading.Thread(
                target=handle_connection, daemon=True, args=(client_sock,)
            ).start()


def start_tls(event: threading.Event) -> None:
    global TLS_ADDRESS
    with socket.socket() as sock:
        sock.listen()
        TLS_ADDRESS = sock.getsockname()
        event.set()

        with SERVER_CONTEXT.wrap_socket(sock, server_side=True) as tls_sock:
            while True:
                client_sock = tls_sock.accept()[0]
                threading.Thread(
                    target=handle_connection, daemon=True, args=(client_sock,)
                ).start()


@pytest.fixture
def client_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    CA.configure_trust(context)
    return context


@pytest.fixture(scope="session")
def tls_server() -> Address:
    event = threading.Event()
    threading.Thread(target=start_tls, daemon=True, args=(event,)).start()
    event.wait()
    assert TLS_ADDRESS
    host, port = TLS_ADDRESS
    return Address(host, port)


@pytest.fixture(scope="session")
def tcp_server() -> Address:
    event = threading.Event()
    threading.Thread(target=start_tcp, daemon=True, args=(event,)).start()
    event.wait()
    assert TCP_ADDRESS
    host, port = TCP_ADDRESS
    return Address(host, port)
