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
