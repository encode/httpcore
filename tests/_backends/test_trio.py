import pytest

import httpcore

READ_TIMEOUT = 2
WRITE_TIMEOUT = 2
CONNECT_TIMEOUT = 2


@pytest.mark.trio
async def test_connect_without_tls(tcp_server):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tcp_server.host, tcp_server.port, timeout=CONNECT_TIMEOUT
    )
    await stream.aclose()


@pytest.mark.trio
async def test_write_without_tls(tcp_server):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tcp_server.host, tcp_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        await stream.write(b"ping", timeout=WRITE_TIMEOUT)


@pytest.mark.trio
async def test_read_without_tls(tcp_server):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tcp_server.host, tcp_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        await stream.write(b"ping", timeout=WRITE_TIMEOUT)
        await stream.read(1024, timeout=READ_TIMEOUT)


@pytest.mark.trio
async def test_connect_with_tls(tls_server, client_context):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tls_server.host, tls_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=client_context, timeout=CONNECT_TIMEOUT
        )
        await tls_stream.aclose()


@pytest.mark.trio
async def test_write_with_tls(tls_server, client_context):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tls_server.host, tls_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=client_context, timeout=CONNECT_TIMEOUT
        )
        async with tls_stream:
            await tls_stream.write(b"ping", timeout=WRITE_TIMEOUT)


@pytest.mark.trio
async def test_read_with_tls(tls_server, client_context):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tls_server.host, tls_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=client_context, timeout=CONNECT_TIMEOUT
        )
        async with tls_stream:
            await tls_stream.write(b"ping", timeout=WRITE_TIMEOUT)
            await tls_stream.read(1024, timeout=READ_TIMEOUT)

@pytest.mark.trio
async def test_connect_with_tls_in_tls(tls_in_tls_server, client_context):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tls_in_tls_server.host, tls_in_tls_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=client_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT
        )
        async with tls_stream:
            tls_in_tls_stream = await tls_stream.start_tls(
                ssl_context=client_context,
                server_hostname="localhost",
                timeout=CONNECT_TIMEOUT
            )
            await tls_in_tls_stream.aclose()


@pytest.mark.trio
async def test_write_with_tls_in_tls(tls_in_tls_server, client_context):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tls_in_tls_server.host, tls_in_tls_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=client_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT
        )
        async with tls_stream:
            tls_in_tls_stream = await tls_stream.start_tls(
                ssl_context=client_context,
                server_hostname="localhost",
                timeout=CONNECT_TIMEOUT
            )
            async with tls_in_tls_stream:
                await tls_in_tls_stream.write(b'ping', timeout=WRITE_TIMEOUT)

@pytest.mark.trio
async def test_read_with_tls_in_tls(tls_in_tls_server, client_context):
    backend = httpcore.TrioBackend()
    stream = await backend.connect_tcp(
        tls_in_tls_server.host, tls_in_tls_server.port, timeout=CONNECT_TIMEOUT
    )
    async with stream:
        tls_stream = await stream.start_tls(
            ssl_context=client_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT
        )
        async with tls_stream:
            tls_in_tls_stream = await tls_stream.start_tls(
                ssl_context=client_context,
                server_hostname="localhost",
                timeout=CONNECT_TIMEOUT
            )
            async with tls_in_tls_stream:
                await tls_in_tls_stream.write(b'ping', timeout=WRITE_TIMEOUT)
                await tls_in_tls_stream.read(1024, timeout=READ_TIMEOUT)