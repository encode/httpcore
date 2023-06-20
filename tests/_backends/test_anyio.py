import ssl

import pytest
from pytest_httpbin import certs  # type: ignore

import httpcore

READ_TIMEOUT = 2
WRITE_TIMEOUT = 2
CONNECT_TIMEOUT = 2


@pytest.mark.anyio
async def test_connect_without_tls(httpbin):
    backend = httpcore.AnyIOBackend()
    stream = await backend.connect_tcp(
        httpbin.host, httpbin.port, timeout=CONNECT_TIMEOUT
    )
    await stream.aclose()


@pytest.mark.anyio
async def test_write_without_tls(httpbin):
    backend = httpcore.AnyIOBackend()
    stream = await backend.connect_tcp(
        httpbin.host, httpbin.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
        for chunk in http_request:
            await stream.write(chunk, timeout=WRITE_TIMEOUT)


@pytest.mark.anyio
async def test_read_without_tls(httpbin):
    backend = httpcore.AnyIOBackend()
    stream = await backend.connect_tcp(
        httpbin.host, httpbin.port, timeout=CONNECT_TIMEOUT
    )
    http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
    async with stream:
        for chunk in http_request:
            await stream.write(chunk, timeout=WRITE_TIMEOUT)
        await stream.read(1024, timeout=READ_TIMEOUT)


@pytest.mark.anyio
async def test_connect_with_tls(httpbin_secure):
    backend = httpcore.AnyIOBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = await backend.connect_tcp(
        httpbin_secure.host, httpbin_secure.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=ssl_context, timeout=CONNECT_TIMEOUT
        )
        await tls_stream.aclose()


@pytest.mark.anyio
async def test_write_with_tls(httpbin_secure):
    backend = httpcore.AnyIOBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = await backend.connect_tcp(
        httpbin_secure.host, httpbin_secure.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=ssl_context, timeout=CONNECT_TIMEOUT
        )
        async with tls_stream:
            http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
            for chunk in http_request:
                await tls_stream.write(chunk, timeout=WRITE_TIMEOUT)


@pytest.mark.anyio
async def test_read_with_tls(httpbin_secure):
    backend = httpcore.AnyIOBackend()
    ssl_context = ssl.create_default_context()
    ssl_context.load_verify_locations(certs.where())
    stream = await backend.connect_tcp(
        httpbin_secure.host, httpbin_secure.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=ssl_context, timeout=CONNECT_TIMEOUT
        )
        async with tls_stream:
            http_request = [b"GET / HTTP/1.1\r\n", b"\r\n"]
            for chunk in http_request:
                await tls_stream.write(chunk, timeout=WRITE_TIMEOUT)
            await tls_stream.read(1024, timeout=READ_TIMEOUT)
