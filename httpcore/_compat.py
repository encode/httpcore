# `contextlib.asynccontextmanager` exists from Python 3.7 onwards.
# For 3.6 we require the `async_generator` package for a backported version.
import sys

if sys.version_info >= (3, 7):
    from contextlib import asynccontextmanager as asynccontextmanager
else:
    from async_generator import asynccontextmanager  # noqa: F401
