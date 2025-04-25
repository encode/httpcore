import contextlib
import logging
import socket
import threading
import time

import h2.config
import h2.connection
import h2.events


def send_response(sock, conn, event):
    start = time.time()
    logging.info("Starting %s.", event)

    time.sleep(1)

    stream_id = event.stream_id
    conn.send_headers(
        stream_id=stream_id,
        headers=[(":status", "200"), ("server", "basic-h2-server/1.0")],
    )
    data_to_send = conn.data_to_send()
    if data_to_send:
        sock.sendall(data_to_send)

    conn.send_data(stream_id=stream_id, data=b"it works!", end_stream=True)
    data_to_send = conn.data_to_send()
    if data_to_send:
        sock.sendall(data_to_send)

    end = time.time()
    logging.info("Finished %s in %.03fs.", event, end - start)


def handle(sock: socket.socket) -> None:
    config = h2.config.H2Configuration(client_side=False)
    conn = h2.connection.H2Connection(config=config)
    conn.initiate_connection()
    sock.sendall(conn.data_to_send())

    while True:
        data = sock.recv(65535)
        if not data:
            sock.close()
            break

        events = conn.receive_data(data)
        for event in events:
            if isinstance(event, h2.events.RequestReceived):
                threading.Thread(target=send_response, args=(sock, conn, event)).start()


class HTTP2Server:
    def __init__(
        self, *, host: str = "127.0.0.1", port: int = 0, timeout: float = 0.2
    ) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(timeout)
        self.sock.bind((host, port))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(5)

    def run(self) -> None:
        while True:
            try:
                handle(self.sock.accept()[0])
            except socket.timeout:  # pragma: no cover
                pass
            except OSError:
                break


@contextlib.contextmanager
def run(**kwargs):
    server = HTTP2Server(**kwargs)
    thr = threading.Thread(target=server.run)
    thr.start()
    try:
        yield server
    finally:
        server.sock.close()
        thr.join()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        format="%(relativeCreated)5i <%(threadName)s> %(filename)s:%(lineno)s] %(message)s",
        level=logging.INFO,
    )

    HTTP2Server(port=8100).run()
