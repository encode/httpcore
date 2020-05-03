# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Unreleased

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
