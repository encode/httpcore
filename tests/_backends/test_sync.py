import httpcore


def test_connect_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    try:
        ssl_object = stream.get_extra_info("ssl_object")
        assert ssl_object is None
    finally:
        stream.close()


def test_write_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    try:
        for chunk in http_request:
            stream.write(chunk)
        assert True
    finally:
        stream.close()


def test_read_without_tls(httpbin):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(httpbin.host, httpbin.port)
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    try:
        for chunk in http_request:
            stream.write(chunk)
        response = stream.read(1024)
        assert response
    finally:
        stream.close()
