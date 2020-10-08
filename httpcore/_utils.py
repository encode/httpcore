import logging
import os
import selectors
import sys
import typing

from ._types import URL, Origin

_LOGGER_INITIALIZED = False
TRACE_LOG_LEVEL = 5
DEFAULT_PORTS = {b"http": 80, b"https": 443}


class Logger(logging.Logger):
    # Stub for type checkers.
    def trace(self, message: str, *args: typing.Any, **kwargs: typing.Any) -> None:
        ...  # pragma: nocover


def get_logger(name: str) -> Logger:
    """
    Get a `logging.Logger` instance, and optionally
    set up debug logging based on the HTTPCORE_LOG_LEVEL or HTTPX_LOG_LEVEL
    environment variables.
    """
    global _LOGGER_INITIALIZED
    if not _LOGGER_INITIALIZED:
        _LOGGER_INITIALIZED = True
        logging.addLevelName(TRACE_LOG_LEVEL, "TRACE")

        log_level = os.environ.get(
            "HTTPCORE_LOG_LEVEL", os.environ.get("HTTPX_LOG_LEVEL", "")
        ).upper()
        if log_level in ("DEBUG", "TRACE"):
            logger = logging.getLogger("httpcore")
            logger.setLevel(logging.DEBUG if log_level == "DEBUG" else TRACE_LOG_LEVEL)
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(levelname)s [%(asctime)s] %(name)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(handler)

    logger = logging.getLogger(name)

    def trace(message: str, *args: typing.Any, **kwargs: typing.Any) -> None:
        logger.log(TRACE_LOG_LEVEL, message, *args, **kwargs)

    logger.trace = trace  # type: ignore

    return typing.cast(Logger, logger)


def url_to_origin(url: URL) -> Origin:
    scheme, host, explicit_port = url[:3]
    default_port = DEFAULT_PORTS[scheme]
    port = default_port if explicit_port is None else explicit_port
    return scheme, host, port


def origin_to_url_string(origin: Origin) -> str:
    scheme, host, explicit_port = origin
    port = f":{explicit_port}" if explicit_port != DEFAULT_PORTS[scheme] else ""
    return f"{scheme.decode('ascii')}://{host.decode('ascii')}{port}"


def is_socket_readable(sock_fd: int) -> bool:
    """
    Return whether a socket, as identifed by its file descriptor, is readable.

    "A socket is readable" means that it would return immediately with b"" if we
    called .recv() on it.

    This is also equivalent to "the connection has been closed on the other end".

    See: https://github.com/encode/httpx/pull/143#issuecomment-515181778
    """
    # NOTE: We prefer the `selectors` module to `select`, because of known limitations
    # of `select` on Linux when dealing with many open file descriptors.
    # See: https://github.com/encode/httpcore/issues/182
    # On Windows `select` is just fine, but that's also what `DefaultSelector` uses
    # there, so `selectors` is really the generally-appropriate solution.
    # See: https://github.com/encode/httpcore/pull/193#issuecomment-703129316
    sel = selectors.DefaultSelector()
    event = selectors.EVENT_READ
    sel.register(sock_fd, event)
    read_ready = [key.fileobj for key, mask in sel.select(0) if mask & event]
    return len(read_ready) > 0
