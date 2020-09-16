import asyncio
from typing import cast

import pytest
import socks

import httpcore
from httpcore import AsyncByteStream, ReadTimeout
from httpcore._backends.asyncio import AsyncioBackend


async def get_body_lines(stream: AsyncByteStream, timeout: float = 0.25):
    async for chunk in stream:
        yield chunk.decode()


@pytest.mark.asyncio
async def test_connection():
    host = "ifconfig.me"
    port = 80

    proxy_host, proxy_port = "localhost", 1085

    sock = socks.socksocket()
    sock.setblocking(False)
    sock.set_proxy(socks.SOCKS5, proxy_host, proxy_port)
    stream_writer = None

    try:
        sock.connect((host, port))

        stream_reader, stream_writer = await asyncio.open_connection(sock=sock)

        stream_writer.write(b"GET / HTTP/1.1\r\n")
        stream_writer.write(b"Host: " + host.encode("ascii") + b"\r\n")
        stream_writer.write(b"User-Agent: curl/7.72.0\r\n")
        stream_writer.write(b"\r\n")

        assert not stream_reader.at_eof()
        await stream_writer.drain()
        assert not stream_reader.at_eof()

        async for line in get_body_lines(stream_reader):
            print(line)
    finally:
        if stream_writer and stream_writer:
            stream_writer.close()


@pytest.mark.asyncio
async def test_connection_2():
    host = b"example.com"
    port = 80

    proxy_host, proxy_port = b"localhost", 1085
    proxy_type = b"SOCKS5"

    backend = AsyncioBackend()

    socket_stream = await backend.open_socks_stream(
        host, port, proxy_host, proxy_port, proxy_type, {}
    )

    try:
        assert not socket_stream.is_connection_dropped()

        await socket_stream.write(b"GET / HTTP/1.1\r\n", {})
        await socket_stream.write(b"Host: " + host + b"\r\n", {})
        await socket_stream.write(b"User-Agent: curl/7.72.0\r\n", {})

        await socket_stream.write(b"\r\n", {})

        assert not socket_stream.is_connection_dropped()

        data = []
        while True:
            try:
                chunk = await socket_stream.read(1024, {"read": 0.25})
                if not chunk:
                    break
            except ReadTimeout:
                break
            data.append(chunk)
        data = b"".join(data)

        data_lines = data.split(b"\r\n")

        for line in data_lines:
            print(line.decode())
    finally:
        await socket_stream.aclose()


@pytest.mark.asyncio
async def test_connection_3():
    async with httpcore.AsyncConnectionPool(backend="asyncio") as pool:
        pool = cast(httpcore.AsyncConnectionPool, pool)
        url = (b"http", b"example.com", 80, b"/")
        headers = [(b"host", b"example.com")]
        method = b"GET"
        http_version, status_code, reason, headers, stream = await pool.request(
            method, url, headers
        )

        assert status_code == 200
        async for line in get_body_lines(stream):
            print(line)
