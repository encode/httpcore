import pytest

from httpcore import ProxyError
from httpcore._sync.socks_proxy import _init_socks5_connection
from httpcore.backends.mock import MockStream



def test_init_socks5_proxy():
    stream = MockStream(
        [
            #   v5 NOAUTH
            b"\x05\x00",
            #   v5 SUC RSV IP4 127  .0  .0  .1     :80
            b"\x05\x00\x00\x01\xff\x00\x00\x01\x00\x50",
        ]
    )
    _init_socks5_connection(stream, host=b"google.com", port=80)



def test_init_socks5_proxy_failed():
    stream = MockStream(
        [
            #   v5 NOAUTH
            b"\x05\x00",
            #   v5  NO RSV IP4   0  .0  .0  .0     :00
            b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00",
        ]
    )
    with pytest.raises(ProxyError) as exc_info:
        _init_socks5_connection(stream, host=b"google.com", port=80)
    assert str(exc_info.value) == "Proxy Server could not connect: Connection refused."



def test_init_socks5_proxy_invalid_auth_method():
    stream = MockStream(
        [
            #   v5 USERNAME/PASSWORD
            b"\x05\x02",
        ]
    )
    with pytest.raises(ProxyError) as exc_info:
        _init_socks5_connection(stream, host=b"google.com", port=80)
    assert (
        str(exc_info.value)
        == "Requested NO AUTHENTICATION REQUIRED from proxy server, but got USERNAME/PASSWORD."
    )



def test_init_socks5_proxy_invalid_username_password():
    stream = MockStream(
        [
            #   v5 USERNAME/PASSWORD
            b"\x05\x02",
            #   v5 INVALID USERNAME/PASSWORD
            b"\x05\x01",
        ]
    )
    with pytest.raises(ProxyError) as exc_info:
        _init_socks5_connection(
            stream, host=b"google.com", port=80, auth=(b"invalid", b"invalid")
        )
    assert str(exc_info.value) == "Invalid username/password"



def test_init_socks5_proxy_valid_username_password():
    stream = MockStream(
        [
            #   v5 USERNAME/PASSWORD
            b"\x05\x02",
            #   v5 VALID USERNAME/PASSWORD
            b"\x05\x00",
            #   v5 SUC RSV IP4 127  .0  .0  .1     :80
            b"\x05\x00\x00\x01\xff\x00\x00\x01\x00\x50",
        ]
    )
    with pytest.raises(ProxyError) as exc_info:
        _init_socks5_connection(
            stream, host=b"google.com", port=80, auth=(b"invalid", b"invalid")
        )
    assert str(exc_info.value) == "Invalid username/password"
