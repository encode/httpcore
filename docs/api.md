# Developer Interface

## Async API Overview

The `AsyncHTTPTransport` class provides the base interface which transport classes need to implement.

::: httpcore.AsyncHTTPTransport
    :docstring:
    :members: arequest aclose

The `AsyncConnectionPool` class is a concrete implementation of `AsyncHTTPTransport`.

::: httpcore.AsyncConnectionPool
    :docstring:

---

## Sync API Overview

The `SyncHTTPTransport` class provides the base interface which transport classes need to implement.

::: httpcore.SyncHTTPTransport
    :docstring:
    :members: request close

The `SyncConnectionPool` class is a concrete implementation of `SyncHTTPTransport`.

::: httpcore.SyncConnectionPool
    :docstring:

---

## Utilities

The `PlainByteStream` can be used to return a bytestring with both bytes iterable
and async bytes iterable iterfaces.

::: httpcore.PlainByteStream
    :docstring:
