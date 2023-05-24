# Network Backends

The API layer at which `httpcore` interacts with the network is described as the network backend. Various backend implementations are provided, allowing `httpcore` to handle networking in different runtime contexts.

## Working with network backends

### The default network backend

Typically you won't need to specify a network backend, as a default will automatically be selected. However, understanding how the network backends fit in may be useful if you want to better understand the underlying architecture. Let's start by seeing how we can explicitly select the network backend.

First we're making a standard HTTP request, using a connection pool:

```python
import httpcore

with httpcore.ConnectionPool() as http:
    response = http.request('GET', 'https://www.example.com')
```

We can also have the same behavior, but be explicit with our selection of the network backend:

```python
import httpcore

network_backend = httpcore.NetworkBackend()
with httpcore.ConnectionPool(network_backend=network_backend) as http:
    response = http.request('GET', 'https://www.example.com')
```

The `httpcore.NetworkBackend()` implementation handles the opening of TCP connections, and operations on the socket stream, such as reading, writing, and closing the connection.

We can get a better understanding of this by using the network backend to send a basic HTTP/1.1 request directly:

**TODO**

```python
network_backend = httpcore.NetworkBackend()
network_stream = network_backend.open_tcp_connection("www.example.com")
network_stream = network_stream.start_tls(...)
network_stream.write(...)
while True:
    content = network_stream.read()
    if not content:
        break
    print(content)
network_stream.close()
```

### Async network backends

If we're working with an `async` codebase, then we need to select a different backend. Which backend we want to choose will depend on if we're running under `asyncio`, or under `trio`:

```python
import httpcore
import asyncio

async def main():
    network_backend = httpcore.AnyIONetworkBackend()
    async with httpcore.AsyncConnectionPool(network_backend=network_backend) as http:
        response = await http.request('GET', 'https://www.example.com')

asyncio.run(main())
```

...

```python
import httpcore
import trio

async def main():
    network_backend = httpcore.TrioIONetworkBackend()
    async with httpcore.AsyncConnectionPool(network_backend=network_backend) as http:
        response = await http.request('GET', 'https://www.example.com')

trio.run(main)
```

### Mock network backends

...

### Custom network backends

The base interface for network backends is provided as public API, allowing you to implement custom networking behavior.

You can use this to provide advanced networking functionality such as:

* Network recording / replay.
* In-depth debug tooling.
* Handling non-standard SSL or DNS requirements.

Here's an example that records the network response to a file on disk:

```python
import httpcore


class RecordingNetworkStream(httpcore.BaseNetworkStream):
    def __init__(self, record_file, stream):
        self.record_file = record_file
        self.stream = stream

    def read(self, max_bytes, timeout=None):
        data = self.stream.read(max_bytes, timeout=timeout)
        self.record_file.write(data)
        return data

    def write(self, buffer, timeout=None):
        self.stream.write(buffer, timeout=timeout)

    def close(self) -> None:
        self.stream.close()

    def start_tls(
        self,
        ssl_context,
        server_hostname=None,
        timeout=None,
    ):
        self.stream = self.stream.start_tls(
            ssl_context, server_hostname=server_hostname, timeout=timeout
        )
        return self

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)


class RecordingNetworkBackend(httpcore.BaseNetworkBackend):
    """
    A custom network backend that records network responses.
    """
    def __init__(self, record_file):
        self.record_file = record_file
        self.backend = httpcore.NetworkBackend()

    def connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ) -> NetworkStream:
        # Note that we're only using a single record file here,
        # so even if multiple connections are opened the network
        # traffic will all write to the same file.

        # An alternative implementation might automatically use
        # a new file for each opened connection.
        stream = self.backend.connect_tcp(
            host,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options
        )
        return RecordingNetworkStream(self.record_file, stream)


# Once you make the request, the raw HTTP/1.1 response will be available
# in the 'network-recording' file.
#
# Try switching to `http2=True` to see the difference when recording HTTP/2 binary network traffic,
# or add `headers={'Accept-Encoding': 'gzip'}` to see HTTP content compression.
with open("network-recording", "wb") as record_file:
    network_backend = RecordingNetworkBackend(record_file)
    with httpcore.ConnectionPool(network_backend=network_backend) as http:
        response = http.request("GET", "https://www.example.com/")
```

## Reference

### Networking Backends

* `httpcore.NetworkBackend`
* `httpcore.AnyIONetworkBackend`
* `httpcore.TrioNetworkBackend`

### Mock Backends

* `httpcore.MockNetworkBackend`
* `httpcore.MockAsyncNetworkBackend`

### Base Interface

* `httpcore.BaseNetworkBackend`
* `httpcore.BaseAsyncNetworkBackend`
