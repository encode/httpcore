# Developer Interface

## Async API Overview

The `AsyncHTTPTransport` and `AsyncByteStream` classes provide the base
interface which transport classes need to implement.

::: httpcore.AsyncHTTPTransport
    :docstring:
    :members: request close

::: httpcore.AsyncByteStream
    :docstring:
    :members: __aiter__ close

The `AsyncConnectionPool` class is a concrete implementation of `AsyncHTTPTransport`.

::: httpcore.AsyncConnectionPool
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
