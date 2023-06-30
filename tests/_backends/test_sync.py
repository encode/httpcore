import httpcore

READ_TIMEOUT = 2
WRITE_TIMEOUT = 2
CONNECT_TIMEOUT = 2


def test_connect_without_tls(tcp_server):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(
        tcp_server.host, tcp_server.port, timeout=CONNECT_TIMEOUT
    )
    stream.close()


def test_write_without_tls(tcp_server):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(
        tcp_server.host, tcp_server.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        stream.write(b"ping", timeout=WRITE_TIMEOUT)


def test_read_without_tls(tcp_server):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(
        tcp_server.host, tcp_server.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        stream.write(b"ping", timeout=WRITE_TIMEOUT)
        stream.read(1024, timeout=READ_TIMEOUT)


def test_connect_with_tls(tls_server, client_context):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(
        tls_server.host, tls_server.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=client_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT,
        )
        tls_stream.close()


def test_write_with_tls(tls_server, client_context):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(
        tls_server.host, tls_server.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=client_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT,
        )
        with tls_stream:
            tls_stream.write(b"ping", timeout=WRITE_TIMEOUT)


def test_read_with_tls(tls_server, client_context):
    backend = httpcore.SyncBackend()
    stream = backend.connect_tcp(
        tls_server.host, tls_server.port, timeout=CONNECT_TIMEOUT
    )
    with stream:
        tls_stream = stream.start_tls(
            ssl_context=client_context,
            server_hostname="localhost",
            timeout=CONNECT_TIMEOUT,
        )
        with tls_stream:
            tls_stream.write(b"ping", timeout=WRITE_TIMEOUT)
            tls_stream.read(1024, timeout=READ_TIMEOUT)
