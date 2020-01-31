import httpcore
import pytest



def test_connection_pool():
    with httpcore.SyncConnectionPool() as http:
        with pytest.raises(NotImplementedError):
            http.request(b'GET', (b'https', b'example.org', 443, b'/'))



def test_http_proxy():
    proxy_url = (b'https', b'localhost', 443, b'/')
    with httpcore.SyncHTTPProxy(proxy_url) as http:
        with pytest.raises(NotImplementedError):
            http.request(b'GET', (b'https', b'example.org', 443, b'/'))
