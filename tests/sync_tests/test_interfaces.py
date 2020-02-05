import pytest

import httpcore


def read_body(stream):
    try:
        body = []
        for chunk in stream:
            body.append(chunk)
        return b''.join(body)
    finally:
        stream.close()



def test_connection_pool():
    with httpcore.SyncConnectionPool() as http:
        method = b"GET"
        url = (b"http", b"example.org", 80, b"/")
        headers = [(b"host", b"example.org")]
        http_version, status_code, reason, headers, stream = http.request(method, url, headers)
        body = read_body(stream)

        assert http_version == b'HTTP/1.1'
        assert status_code == 200
        assert reason == b'OK'
