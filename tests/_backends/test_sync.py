import ssl

import httpcore


def test_connect_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    stream.close()


def test_write_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    try:
        for chunk in http_request:
            stream.write(chunk)
    finally:
        stream.close()


def test_read_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    try:
        for chunk in http_request:
            stream.write(chunk)
        stream.read(1024)
    finally:
        stream.close()


def test_connect_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    stream = backend.connect_tcp(httpbin_secure.host, httpbin_secure.port)
    tls_stream = stream.start_tls(ssl_context=ssl_context)
    tls_stream.close()


def test_write_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    stream = backend.connect_tcp(httpbin_secure.host, httpbin_secure.port)
    tls_stream = stream.start_tls(ssl_context=ssl_context)
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    try:
        for chunk in http_request:
            tls_stream.write(chunk)
    finally:
        tls_stream.close()


def test_read_with_tls(httpbin_secure):
    backend = httpcore.SyncBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    stream = backend.connect_tcp(httpbin_secure.host, httpbin_secure.port)
    tls_stream = stream.start_tls(ssl_context=ssl_context)
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    try:
        for chunk in http_request:
            tls_stream.write(chunk)
        tls_stream.read(1024)
    finally:
        tls_stream.close()
