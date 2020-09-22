# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## 0.11.0 (September 22nd, 2020)

The Transport API with 0.11.0 has a couple of significant changes.

Firstly we've moved changed the request interface in order to allow extensions, which will later enable us to support features
such as trailing headers, HTTP/2 server push, and CONNECT/Upgrade connections.

The interface changes from:

```python
def request(method, url, headers, stream, timeout):
    return (http_version, status_code, reason, headers, stream)
```

To instead including an optional dictionary of extensions on the request and response:

```python
def request(method, url, headers, stream, ext):
    return (status_code, headers, stream, ext)
```

Having an open-ended extensions point will allow us to add later support for various optional features, that wouldn't otherwise be supported without these API changes.

In particular:

* Trailing headers support.
* HTTP/2 Server Push
* sendfile.
* Exposing raw connection on CONNECT, Upgrade, HTTP/2 bi-di streaming.
* Exposing debug information out of the API, including template name, template context.

Currently extensions are limited to:

* request: `timeout` - Optional. Timeout dictionary.
* response: `http_version` - Optional. Include the HTTP version used on the response.
* response: `reason` - Optional. Include the reason phrase used on the response. Only valid with HTTP/1.*.

See https://github.com/encode/httpx/issues/1274#issuecomment-694884553 for the history behind this.

Secondly, the async version of `request` is now namespaced as `arequest`.

This allows concrete transports to support both sync and async implementations on the same class.

### Added

- Add curio support. (Pull #168)
- Add anyio support, with `backend="anyio"`. (Pull #169)

### Changed

- Update the Transport API to use 'ext' for optional extensions. (Pull #190)
- Update the Transport API to use `.request` and `.arequest` so implementations can support both sync and async. (Pull #189)

## 0.10.2 (August 20th, 2020)

### Added

- Added Unix Domain Socket support. (Pull #139)

### Fixed

- Always include the port on proxy CONNECT requests. (Pull #154)
- Fix `max_keepalive_connections` configuration. (Pull #153)
- Fixes behaviour in HTTP/1.1 where server disconnects can be used to signal the end of the response body. (Pull #164)

## 0.10.1 (August 7th, 2020)

- Include `max_keepalive_connections` on `AsyncHTTPProxy`/`SyncHTTPProxy` classes.

## 0.10.0 (August 7th, 2020)

The most notable change in the 0.10.0 release is that HTTP/2 support is now fully optional.

Use either `pip install httpcore` for HTTP/1.1 support only, or `pip install httpcore[http2]` for HTTP/1.1 and HTTP/2 support.

### Added

- HTTP/2 support becomes optional. (Pull #121, #130)
- Add `local_address=...` support. (Pull #100, #134)
- Add `PlainByteStream`, `IteratorByteStream`, `AsyncIteratorByteStream`. The `AsyncByteSteam` and `SyncByteStream` classes are now pure interface classes. (#133)
- Add `LocalProtocolError`, `RemoteProtocolError` exceptions. (Pull #129)
- Add `UnsupportedProtocol` exception. (Pull #128)
- Add `.get_connection_info()` method. (Pull #102, #137)
- Add better TRACE logs. (Pull #101)

### Changed

- `max_keepalive` is deprecated in favour of `max_keepalive_connections`. (Pull #140)

### Fixed

- Improve handling of server disconnects. (Pull #112)

## 0.9.1 (May 27th, 2020)

### Fixed

- Proper host resolution for sync case, including IPv6 support. (Pull #97)
- Close outstanding connections when connection pool is closed. (Pull #98)

## 0.9.0 (May 21th, 2020)

### Changed

- URL port becomes an `Optional[int]` instead of `int`. (Pull #92)

### Fixed

- Honor HTTP/2 max concurrent streams settings. (Pull #89, #90)
- Remove incorrect debug log. (Pull #83)

## 0.8.4 (May 11th, 2020)

### Added

- Logging via HTTPCORE_LOG_LEVEL and HTTPX_LOG_LEVEL environment variables
and TRACE level logging. (Pull #79)

### Fixed

- Reuse of connections on HTTP/2 in close concurrency situations. (Pull #81)

## 0.8.3 (May 6rd, 2020)

### Fixed

- Include `Host` and `Accept` headers on proxy "CONNECT" requests.
- De-duplicate any headers also contained in proxy_headers.
- HTTP/2 flag not being passed down to proxy connections.

## 0.8.2 (May 3rd, 2020)

### Fixed

- Fix connections using proxy forwarding requests not being added to the
connection pool properly. (Pull #70)

## 0.8.1 (April 30th, 2020)

### Changed

- Allow inherintance of both `httpcore.AsyncByteStream`, `httpcore.SyncByteStream` without type conflicts.

## 0.8.0 (April 30th, 2020)

### Fixed

- Fixed tunnel proxy support.

### Added

- New `TimeoutException` base class.

## 0.7.0 (March 5th, 2020)

- First integration with HTTPX.
