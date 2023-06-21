# Proxies

The `httpcore` package provides support for HTTP proxies, using either "HTTP Forwarding" or "HTTP Tunnelling". Forwarding is a proxy mechanism for sending requests to `http` URLs via an intermediate proxy. Tunnelling is a proxy mechanism for sending requests to `https` URLs via an intermediate proxy.

Sending requests via a proxy is very similar to sending requests using a standard connection pool:

```python
import httpcore

proxy = httpcore.HTTPProxy(proxy_url="http://127.0.0.1:8080/")
r = proxy.request("GET", "https://www.example.com/")

print(r)
# <Response [200]>
```

You can test the `httpcore` proxy support, using the Python [`proxy.py`](https://pypi.org/project/proxy.py/) tool:

```shell
$ pip install proxy.py
$ proxy --hostname 127.0.0.1 --port 8080
```

Requests will automatically use either forwarding or tunnelling, depending on if the scheme is `http` or `https`.

## Authentication

Proxy authentication can be included in the initial configuration:

```python
import httpcore

# A `Proxy-Authorization` header will be included on the initial proxy connection.
proxy = httpcore.HTTPProxy(
    proxy_url="http://127.0.0.1:8080/",
    proxy_auth=("<username>", "<password>")
)
```

Custom headers can also be included:

```python
import httpcore
import base64

# Construct and include a `Proxy-Authorization` header.
auth = base64.b64encode(b"<username>:<password>")
proxy = httpcore.HTTPProxy(
    proxy_url="http://127.0.0.1:8080/",
    proxy_headers={"Proxy-Authorization": b"Basic " + auth}
)
```

## Proxy Connection mode

There are two types of HTTP proxy:

1. Forwading (HTTP [absolute-url](https://tools.ietf.org/html/rfc7230#section-5.3.2))
2. Tunneling (HTTP [`CONNECT` method](https://tools.ietf.org/html/rfc7231#section-4.3.6))

By default we forwarding plain http requests and tunneling https requests.
You can change this behavior with `mode: httpcore.ProxyMode` parameter:
```py
import httpcore
import base64

proxy = httpcore.HTTPProxy(
    proxy_url="http://127.0.0.1:8080/",
    mode=httpcore.ProxyMode.HTTP_TUNNEL,  # Forces HTTP requests also use Tunneling
)
```
Also you should make sure your proxy server supports http tunneling or https forwarding.

`ProxyMode` is a flag parameter, you can reverse current default behavior:
```py
import httpcore
import base64

proxy = httpcore.HTTPProxy(
    proxy_url="http://127.0.0.1:8080/",
    mode=httpcore.ProxyMode.HTTP_TUNNEL | httpcore.ProxyMode.HTTPS_FORWARD,
)
```
Note that `ProxyMode.HTTPS_FORWARD` could be unsafe:
1. proxy will handle TLS stuffs like certificate validation, etc.
2. your requests will be visible for proxy server.
## Proxy SSL and HTTP Versions

Proxy support currently only allows for HTTP/1.1 connections to the proxy,
and does not currently support SSL proxy connections, which require HTTPS-in-HTTPS,

## SOCKS proxy support

The `httpcore` package also supports proxies using the SOCKS5 protocol.

Make sure to install the optional dependancy using `pip install httpcore[socks]`.

The `SOCKSProxy` class should be using instead of a standard connection pool:

```python
import httpcore

# Note that the SOCKS port is 1080.
proxy = httpcore.SOCKSProxy(proxy_url="socks5://127.0.0.1:1080/")
r = proxy.request("GET", "https://www.example.com/")
```

Authentication via SOCKS is also supported:

```python
import httpcore

proxy = httpcore.SOCKSProxy(
    proxy_url="socks5://127.0.0.1:8080/",
    proxy_auth=("<username>", "<password>")
)
r = proxy.request("GET", "https://www.example.com/")
```

---

# Reference

## `httpcore.HTTPProxy`

::: httpcore.HTTPProxy
    handler: python
    rendering:
        show_source: False
