# Developer Interface

## Async API Overview

### Base interfaces

The `AsyncHTTPTransport` and `AsyncByteStream` classes provide the base
interface which transport classes need to implement.

<!-- See: https://myst-parser.readthedocs.io/en/latest/using/howto.html#use-sphinx-ext-autodoc-in-markdown-files -->

```{eval-rst}
.. autoclass:: httpcore.AsyncHTTPTransport
    :members: arequest, aclose

.. autoclass:: httpcore.AsyncByteStream
    :members: __aiter__, aclose
```

### Connection pool

The {class}`AsyncConnectionPool <httpcore.AsyncConnectionPool>` class is a concrete implementation of {class}`AsyncHTTPTransport <httpcore.AsyncHTTPTransport>`.

```{eval-rst}
.. autoclass:: httpcore.AsyncConnectionPool
```

### Byte streams

The {class}`PlainByteStream <httpcore.PlainByteStream>` and {class}`AsyncIteratorByteStream <httpcore.AsyncIteratorByteStream>` classes are concrete implementations of `AsyncByteStream`.

```{eval-rst}
.. autoclass:: httpcore.PlainByteStream

.. autoclass:: httpcore.AsyncIteratorByteStream
```

## Sync API Overview

### Base interfaces

The {class}`SyncHTTPTransport <httpcore.SyncHTTPTransport>` and {class}`SyncByteStream <httpcore.SyncByteStream>` classes provide the base interface which transport classes need to implement.

```{eval-rst}
.. autoclass:: httpcore.SyncHTTPTransport
    :members: request, close

.. autoclass:: httpcore.SyncByteStream
    :members: __iter__, close
```

### Connection pool

The {class}`SyncConnectionPool <httpcore.SyncConnectionPool>` class is a concrete implementation of {class}`SyncHTTPTransport <httpcore.SyncHTTPTransport>`.

```{eval-rst}
.. autoclass:: httpcore.SyncConnectionPool
```

### Byte streams

The {class}`PlainByteStream <httpcore.PlainByteStream>` and {class}`IteratorByteStream <httpcore.IteratorByteStream>` classes are concrete implementations of `SyncByteStream`.

```{eval-rst}
.. autoclass:: httpcore.PlainByteStream
    :noindex:

.. autoclass:: httpcore.IteratorByteStream
```
