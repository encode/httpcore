# Developer Interface

## Async API Overview

### Base async interfaces

These classes provide the base interface which transport classes need to implement.

:::{eval-rst}
.. autoclass:: httpcore.AsyncHTTPTransport
    :members: arequest, aclose

.. autoclass:: httpcore.AsyncByteStream
    :members: __aiter__, aclose
:::

### Async connection pool

:::{eval-rst}
.. autoclass:: httpcore.AsyncConnectionPool
    :show-inheritance:
:::

### Async proxy

:::{eval-rst}
.. autoclass:: httpcore.AsyncHTTPProxy
    :show-inheritance:
:::

### Async byte streams

These classes are concrete implementations of [`AsyncByteStream`](httpcore.AsyncByteStream).

:::{eval-rst}
.. autoclass:: httpcore.PlainByteStream
    :show-inheritance:

.. autoclass:: httpcore.AsyncIteratorByteStream
    :show-inheritance:
:::

## Sync API Overview

### Base sync interfaces

These classes provide the base interface which transport classes need to implement.

:::{eval-rst}
.. autoclass:: httpcore.SyncHTTPTransport
    :members: request, close

.. autoclass:: httpcore.SyncByteStream
    :members: __iter__, close
:::

### Sync connection pool

:::{eval-rst}
.. autoclass:: httpcore.SyncConnectionPool
    :show-inheritance:
:::

### Sync proxy

:::{eval-rst}
.. autoclass:: httpcore.SyncHTTPProxy
    :show-inheritance:
:::

### Sync byte streams

These classes are concrete implementations of [`SyncByteStream`](httpcore.SyncByteStream).

:::{eval-rst}
.. autoclass:: httpcore.PlainByteStream
    :show-inheritance:
    :noindex:

.. autoclass:: httpcore.IteratorByteStream
    :show-inheritance:
:::
