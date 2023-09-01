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

## Proxy SSL

The `httpcore` package also supports HTTPS proxies for http and https destinations.

HTTPS proxies can be used in the same way that HTTP proxies are.

```python
proxy = httpcore.HTTPProxy(proxy_url="https://127.0.0.1:8080/")
```

Also, when using HTTPS proxies, you may need to configure the SSL context, which you can do with the `proxy_ssl_context` argument.

```python
import ssl
import httpcore

proxy_ssl_context = ssl.create_default_context()
proxy_ssl_context.check_hostname = False

proxy = httpcore.HTTPProxy('https://127.0.0.1:8080/', proxy_ssl_context=proxy_ssl_context)
```

It is important to note that the `ssl_context` argument is always used for the remote connection, and the `proxy_ssl_context` argument is always used for the proxy connection.

## HTTP Versions

If you use proxies, keep in mind that the `httpcore` package only supports proxies to HTTP/1.1 servers.

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
