# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
