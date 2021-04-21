# HTTP Core

[![Test Suite](https://github.com/encode/httpcore/workflows/Test%20Suite/badge.svg)](https://github.com/encode/httpcore/actions)
[![Package version](https://badge.fury.io/py/httpcore.svg)](https://pypi.org/project/httpcore/)

> *Do one thing, and do it well.*

The HTTP Core package provides a minimal low-level HTTP client, which does
one thing only. Sending HTTP requests.

It does not provide any high level model abstractions over the API,
does not handle redirects, multipart uploads, building authentication headers,
transparent HTTP caching, URL parsing, session cookie handling,
content or charset decoding, handling JSON, environment based configuration
defaults, or any of that Jazz.

Some things HTTP Core does do:

* Sending HTTP requests.
* Provides both sync and async interfaces.
* Supports HTTP/1.1 and HTTP/2.
* Async backend support for `asyncio`, `trio` and `curio`.
* Automatic connection pooling.
* HTTP(S) proxy support.

## Installation

For HTTP/1.1 only support, install with...

```shell
$ pip install httpcore
```

For HTTP/1.1 and HTTP/2 support, install with...

```shell
$ pip install httpcore[http2]
```

## Quickstart

Here's an example of making an HTTP GET request using `httpcore`...

```python
with httpcore.SyncConnectionPool() as http:
    status_code, headers, stream, extensions = http.handle_request(
        method=b'GET',
        url=(b'https', b'example.org', 443, b'/'),
        headers=[(b'host', b'example.org'), (b'user-agent', b'httpcore')]
        stream=httpcore.ByteStream(b''),
        extensions={}
    )
    body = stream.read()
    print(status_code, body)
```

Or, using async...

```python
async with httpcore.AsyncConnectionPool() as http:
    status_code, headers, stream, extensions = await http.handle_async_request(
        method=b'GET',
        url=(b'https', b'example.org', 443, b'/'),
        headers=[(b'host', b'example.org'), (b'user-agent', b'httpcore')],
        stream=httpcore.ByteStream(b''),
        extensions={}
    )
    body = await stream.aread()
    print(status_code, body)
```

## Motivation

You probably don't want to be using HTTP Core directly. It might make sense if
you're writing something like a proxy service in Python, and you just want
something at the lowest possible level, but more typically you'll want to use
a higher level client library, such as `httpx`.

The motivation for `httpcore` is:

* To provide a reusable low-level client library, that other packages can then build on top of.
* To provide a *really clear interface split* between the networking code and client logic,
  so that each is easier to understand and reason about in isolation.
