# Connections

Typically when you're using `httpcore` you'll be sending requests through a connection pool.

You can also work directly with individual HTTP connection instances. This might be useful for debugging issues,
developing a better understanding of the layered architecture of `httpcore` and the functioning of HTTP, or advanced requirements such as developing an alternative connection pooling system.

[...]

```python
import httpcore

with httpcore.HTTPConnection(origin="https://www.example.com") as connection:
    print(connection)  # <HTTPConnection ['https://www.example.com', NOT CONNECTED]>
    response = connection.request("GET", "https://www.example.com/")
    print(connection)  # <HTTPConnection ['https://www.example.com:443', HTTP/1.1, IDLE, Request Count: 1]>
    response = connection.request("GET", "https://www.example.com/")
    print(connection)  # <HTTPConnection ['https://www.example.com:443', HTTP/1.1, IDLE, Request Count: 2]>

print(connection)  # <HTTPConnection ['https://www.example.com:443', HTTP/1.1, CLOSED, Request Count: 2]>
```

**TODO**: Also supports the `.stream(...)` method.

**TODO**: Both the `.request` and the `.stream` methods are wrappers onto the underlying `.handle_request()`...

### Connection origin

An HTTP connection can only be connected to a single origin. The underlying TCP connection will be to a fixed host and port, and may optionally be working over SSL. The origin of the connection can be expressed using a URL form, without any path or query parameter components:

```python
connection = httpcore.HTTPConnection(origin="https://www.example.com")
print(connection)  # <HTTPConnection ['https://www.example.com', NOT CONNECTED]>
```

Attempting to send a request on a connection with a different origin will result in an exception:

```python
connection = httpcore.HTTPConnection(origin="https://www.example.com")

# We can't send a request to `www.encode.io` on a connection to `www.example.com`.
connection.request("GET", "https://www.encode.io/")
# ...
```

For a connection to be able to handle a request, the origin host, port, and ssl must all match:

```python
connection = httpcore.HTTPConnection(origin="https://www.example.com")

# The host is correct here, but we're attempting to send an HTTP request on an HTTPS connection.
connection.request("GET", "http://www.example.com/")
# ...
```

...

`connection.can_handle_request()`

### Connection lifespans

`connection.is_closed()`

The connection has been closed, and can no longer handle any new requests.

`connection.is_idle()`

The connection is not currently handling any requests. It may safely be closed if required.

`connection.has_expired()`

Indicates that the connection has been idle for a duration exceeding the configured keep-alive time, or the connection is idle and the server has sent a disconnect.

### Connections and concurrency

...

`connection.is_available()`

...

`ConnectionNotAvailable`

---

# Reference

## `httpcore.HTTPConnection`

::: httpcore.HTTPConnection
    handler: python
    rendering:
        show_source: False

## `httpcore.HTTP11Connection`

::: httpcore.HTTP11Connection
    handler: python
    rendering:
        show_source: False

## `httpcore.HTTP2Connection`

::: httpcore.HTTP2Connection
    handler: python
    rendering:
        show_source: False
