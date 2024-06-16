import os
import socket
import ssl
from tempfile import gettempdir

import pytest
import uvicorn

import httpcore
from tests.conftest import Server



def test_request(httpbin):
    with httpcore.ConnectionPool() as pool:
        response = pool.request("GET", httpbin.url)
        assert response.status == 200



def test_ssl_request(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    with httpcore.ConnectionPool(ssl_context=ssl_context) as pool:
        response = pool.request("GET", httpbin_secure.url)
        assert response.status == 200



def test_extra_info(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    with httpcore.ConnectionPool(ssl_context=ssl_context) as pool:
        with pool.stream("GET", httpbin_secure.url) as response:
            assert response.status == 200
            stream = response.extensions["network_stream"]

            ssl_object = stream.get_extra_info("ssl_object")
            assert ssl_object.version() == "TLSv1.3"

            local_addr = stream.get_extra_info("client_addr")
            assert local_addr[0] == "127.0.0.1"

            remote_addr = stream.get_extra_info("server_addr")
            assert "https://%s:%d" % remote_addr == httpbin_secure.url

            sock = stream.get_extra_info("socket")
            assert hasattr(sock, "family")
            assert hasattr(sock, "type")

            invalid = stream.get_extra_info("invalid")
            assert invalid is None

            stream.get_extra_info("is_readable")



@pytest.mark.parametrize("keep_alive_enabled", [True, False])
def test_socket_options(
    server: Server, server_url: str, keep_alive_enabled: bool
) -> None:
    socket_options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, int(keep_alive_enabled))]
    with httpcore.ConnectionPool(socket_options=socket_options) as pool:
        response = pool.request("GET", server_url)
        assert response.status == 200

        stream = response.extensions["network_stream"]
        sock = stream.get_extra_info("socket")
        opt = sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
        assert bool(opt) is keep_alive_enabled



def test_socket_no_nagle(server: Server, server_url: str) -> None:
    with httpcore.ConnectionPool() as pool:
        response = pool.request("GET", server_url)
        assert response.status == 200

        stream = response.extensions["network_stream"]
        sock = stream.get_extra_info("socket")
        opt = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        assert bool(opt) is True



def test_pool_recovers_from_connection_breakage(
    server_config: uvicorn.Config, server_url: str
) -> None:
    with httpcore.ConnectionPool(
        max_connections=1, max_keepalive_connections=1, keepalive_expiry=10
    ) as pool:
        with Server(server_config).run_in_thread():
            response = pool.request("GET", server_url)
            assert response.status == 200

            assert len(pool.connections) == 1
            conn = pool.connections[0]

            stream = response.extensions["network_stream"]
            assert stream.get_extra_info("is_readable") is False

        assert (
            stream.get_extra_info("is_readable") is True
        ), "Should break by coming readable"

        with Server(server_config).run_in_thread():
            assert len(pool.connections) == 1
            assert pool.connections[0] is conn, "Should be the broken connection"

            response = pool.request("GET", server_url)
            assert response.status == 200

            assert len(pool.connections) == 1
            assert pool.connections[0] is not conn, "Should be a new connection"



def test_unix_domain_socket(server_port, server_config, server_url):
    uds = f"{gettempdir()}/test_httpcore_app.sock"
    if os.path.exists(uds):
        os.remove(uds)  # pragma: nocover

    uds_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        uds_sock.bind(uds)

        with Server(server_config).run_in_thread(sockets=[uds_sock]):
            with httpcore.ConnectionPool(uds=uds) as pool:
                response = pool.request("GET", server_url)
                assert response.status == 200
    finally:
        uds_sock.close()
        os.remove(uds)
