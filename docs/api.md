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

The `AsyncConnectionPool` and `AsyncHTTPProxy` classes are concrete
implementations of the `AsyncHTTPTransport` class.

::: httpcore.AsyncConnectionPool
    :docstring:

::: httpcore.AsyncHTTPProxy
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

The `SyncConnectionPool` and `SyncHTTPProxy` classes are concrete
implementations of the `SyncHTTPTransport` class.

::: httpcore.SyncConnectionPool
    :docstring:

::: httpcore.SyncHTTPProxy
    :docstring:
