# `contextlib.asynccontextmanager` exists from Python 3.7 onwards.
# For 3.6 we require the `async_generator` package for a backported version.
try:
    from contextlib import asynccontextmanager
except ImportError:
    from async_generator import asynccontextmanager  # type: ignore[no-redef]  # noqa
