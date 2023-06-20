import ssl

from pytest_httpbin import certs  # type: ignore

import httpcore


def test_connect_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    stream.close()


def test_write_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    with stream:
        http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
        for chunk in http_request:
            stream.write(chunk)


def test_read_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    with stream:
        http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
        for chunk in http_request:
            stream.write(chunk)
        stream.read(1024)


def test_connect_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = backend.connect_tcp(httpbin_secure.host, httpbin_secure.port)
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=ssl_context, server_hostname="localhost"
        )
        tls_stream.close()


def test_write_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = backend.connect_tcp(httpbin_secure.host, httpbin_secure.port)
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=ssl_context, server_hostname="localhost"
        )
        with tls_stream:
            http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
            for chunk in http_request:
                tls_stream.write(chunk)


def test_read_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = backend.connect_tcp(httpbin_secure.host, httpbin_secure.port)
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=ssl_context, server_hostname="localhost"
        )
        with tls_stream:
            http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
            for chunk in http_request:
                tls_stream.write(chunk)
            tls_stream.read(1024)
