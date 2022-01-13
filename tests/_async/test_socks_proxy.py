import pytest

from httpcore import Origin, ProxyError
from httpcore._async.socks_proxy import AsyncSOCKSProxy, _init_socks5_connection
from httpcore.backends.mock import AsyncMockBackend, AsyncMockStream


@pytest.mark.anyio
async def test_init_socks5_proxy():
    stream = AsyncMockStream(
        [
            #   v5 NOAUTH
            b"\x05\x00",
            #   v5 SUC RSV IP4 127  .0  .0  .1     :80
            b"\x05\x00\x00\x01\xff\x00\x00\x01\x00\x50",
        ]
    )
    await _init_socks5_connection(stream, host=b"google.com", port=80)


@pytest.mark.anyio
async def test_init_socks5_proxy_failed():
    stream = AsyncMockStream(
        [
            #   v5 NOAUTH
            b"\x05\x00",
            #   v5  NO RSV IP4   0  .0  .0  .0     :00
            b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00",
        ]
    )
    with pytest.raises(ProxyError) as exc_info:
        await _init_socks5_connection(stream, host=b"google.com", port=80)
    assert str(exc_info.value) == "Proxy Server could not connect: Connection refused."


@pytest.mark.anyio
async def test_init_socks5_proxy_invalid_auth_method():
    stream = AsyncMockStream(
        [
            #   v5 USERNAME/PASSWORD
            b"\x05\x02",
        ]
    )
    with pytest.raises(ProxyError) as exc_info:
        await _init_socks5_connection(stream, host=b"google.com", port=80)
    assert (
        str(exc_info.value)
        == "Requested NO AUTHENTICATION REQUIRED from proxy server, but got USERNAME/PASSWORD."
    )


@pytest.mark.anyio
async def test_init_socks5_proxy_invalid_username_password():
    stream = AsyncMockStream(
        [
            #   v5 USERNAME/PASSWORD
            b"\x05\x02",
            #   v5 INVALID USERNAME/PASSWORD
            b"\x05\x01",
        ]
    )
    with pytest.raises(ProxyError) as exc_info:
        await _init_socks5_connection(
            stream, host=b"google.com", port=80, auth=(b"invalid", b"invalid")
        )
    assert str(exc_info.value) == "Invalid username/password"


@pytest.mark.anyio
async def test_init_socks5_proxy_valid_username_password():
    stream = AsyncMockStream(
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
        await _init_socks5_connection(
            stream, host=b"google.com", port=80, auth=(b"invalid", b"invalid")
        )
    assert str(exc_info.value) == "Invalid username/password"


@pytest.mark.anyio
async def test_socks5_proxy_request():
    """
    Send an HTTPS request via a proxy.
    """
    network_backend = AsyncMockBackend(
        [
            # The initial socks CONNECT
            #   v5 NOAUTH
            b"\x05\x00",
            #   v5 SUC RSV IP4 127  .0  .0  .1     :80
            b"\x05\x00\x00\x01\xff\x00\x00\x01\x00\x50",
            # The actual response from the remote server
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    async with AsyncSOCKSProxy(
        proxy_url="socks5://localhost:8080/",
        max_connections=10,
        network_backend=network_backend,
    ) as proxy:
        # Sending an intial request, which once complete will return to the pool, IDLE.
        async with proxy.stream("GET", "https://example.com/") as response:
            info = [repr(c) for c in proxy.connections]
            assert info == [
                "<AsyncSocks5Connection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            await response.aread()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in proxy.connections]
        assert info == [
            "<AsyncSocks5Connection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        ]
        assert proxy.connections[0].is_idle()
        assert proxy.connections[0].is_available()
        assert not proxy.connections[0].is_closed()

        # A connection on a tunneled proxy can only handle HTTPS requests to the same origin.
        assert not proxy.connections[0].can_handle_request(
            Origin(b"http", b"example.com", 80)
        )
        assert not proxy.connections[0].can_handle_request(
            Origin(b"http", b"other.com", 80)
        )
        assert proxy.connections[0].can_handle_request(
            Origin(b"https", b"example.com", 443)
        )
        assert not proxy.connections[0].can_handle_request(
            Origin(b"https", b"other.com", 443)
        )


@pytest.mark.anyio
async def test_socks5_proxy_request_failed():
    """
    Send an HTTPS request via a proxy.
    """
    network_backend = AsyncMockBackend(
        [
            # The initial socks CONNECT
            #   v5 NOAUTH
            b"\x05\x00",
            #   v5  NO RSV IP4   0  .0  .0  .0     :00
            b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00",
        ]
    )

    async with AsyncSOCKSProxy(
        proxy_url="socks5://localhost:8080/",
        max_connections=10,
        network_backend=network_backend,
    ) as proxy:
        # Sending a request, which the proxy rejects
        with pytest.raises(ProxyError) as exc_info:
            await proxy.request("GET", "https://example.com/")
        assert (
            str(exc_info.value) == "Proxy Server could not connect: Connection refused."
        )

        assert not proxy.connections
