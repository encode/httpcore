# Developer Interface

## Async API Overview

The `AsyncHTTPTransport` and `AsyncByteStream` classes provide the base
interface which transport classes need to implement.

::: httpcore.AsyncHTTPTransport
    :docstring:
    :members: handle_async_request aclose

::: httpcore.AsyncByteStream
    :docstring:
    :members: __aiter__ aclose

The `AsyncConnectionPool` class is a concrete implementation of `AsyncHTTPTransport`.

::: httpcore.AsyncConnectionPool
    :docstring:


The `PlainByteStream` and `AsyncIteratorByteStream` classes are concrete implementations of `AsyncByteStream`.

::: httpcore.PlainByteStream
    :docstring:

::: httpcore.AsyncIteratorByteStream
    :docstring:

---

## Sync API Overview

The `SyncHTTPTransport` and `SyncByteStream` classes provide the base
interface which transport classes need to implement.

::: httpcore.SyncHTTPTransport
    :docstring:
    :members: request close

::: httpcore.SyncByteStream
    :docstring:
    :members: __iter__ close

The `SyncConnectionPool` class is a concrete implementation of `SyncHTTPTransport`.

::: httpcore.SyncConnectionPool
    :docstring:

The `PlainByteStream` and `IteratorByteStream` classes are concrete implementations of `SyncByteStream`.

::: httpcore.PlainByteStream
    :docstring:

::: httpcore.IteratorByteStream
    :docstring:
