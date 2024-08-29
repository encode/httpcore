import socket

import h2.connection
import h2.events
import h2.config

def send_response(conn, event):
    stream_id = event.stream_id
    conn.send_headers(
        stream_id=stream_id,
        headers=[
            (':status', '200'),
            ('server', 'basic-h2-server/1.0')
        ],
    )
    conn.send_data(
        stream_id=stream_id,
        data=b'it works!',
        end_stream=True
    )

def handle(sock):
    config = h2.config.H2Configuration(client_side=False)
    conn = h2.connection.H2Connection(config=config)
    conn.initiate_connection()
    sock.sendall(conn.data_to_send())

    while True:
        data = sock.recv(65535)
        if not data:
            break

        events = conn.receive_data(data)
        for event in events:
            if isinstance(event, h2.events.RequestReceived):
                send_response(conn, event)

        data_to_send = conn.data_to_send()
        if data_to_send:
            sock.sendall(data_to_send)


sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('0.0.0.0', 8080))
sock.listen(5)

while True:
    handle(sock.accept()[0])
