import ssl

from pytest_httpbin import certs  # type: ignore

import httpcore

READ_TIMEOUT = 2
WRITE_TIMEOUT = 2
CONNECT_TIMEOUT = 2


def test_connect_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port, timeout=CONNECT_TIMEOUT)
    stream.close()


def test_write_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port, timeout=CONNECT_TIMEOUT)
    with stream:
        http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
        for chunk in http_request:
            stream.write(chunk, timeout=WRITE_TIMEOUT)


def test_read_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port, timeout=CONNECT_TIMEOUT)
    with stream:
        http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
        for chunk in http_request:
            stream.write(chunk, timeout=WRITE_TIMEOUT)
        stream.read(1024, timeout=READ_TIMEOUT)


def test_connect_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = backend.connect_tcp(
        httpbin_secure.host, httpbin_secure.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=ssl_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT,
        )
        tls_stream.close()


def test_write_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = backend.connect_tcp(
        httpbin_secure.host, httpbin_secure.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=ssl_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT,
        )
        with tls_stream:
            http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
            for chunk in http_request:
                tls_stream.write(chunk, timeout=WRITE_TIMEOUT)


def test_read_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = backend.connect_tcp(
        httpbin_secure.host, httpbin_secure.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=ssl_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT,
        )
        with tls_stream:
            http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
            for chunk in http_request:
                tls_stream.write(chunk, timeout=WRITE_TIMEOUT)
            tls_stream.read(1024, timeout=READ_TIMEOUT)
