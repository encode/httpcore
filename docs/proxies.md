# Proxies

The `httpcore` package currently provides support for HTTP proxies, using either "HTTP Forwarding" and "HTTP Tunnelling". Forwarding is a proxy mechanism for sending requests to `http` URLs via an intermediate proxy. Tunnelling is a proxy mechanism for sending requests to `https` URLs via an intermediate proxy.

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

Proxy headers can be included in the initial configuration:

```python
import httpcore
import base64

auth = base64.b64encode(b"Basic <username>:<password>")
proxy = httpcore.HTTPProxy(
    proxy_url="http://127.0.0.1:8080/",
    proxy_headers={"Proxy-Authorization": auth}
)
```

## HTTP Versions

Proxy support currently only allows for HTTP/1.1 connections to the proxy.

---

# Reference

## `httpcore.HTTPProxy`

::: httpcore.HTTPProxy
    handler: python
    rendering:
        show_source: False
