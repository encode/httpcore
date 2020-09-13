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


def _wait_for_io_events(socks: list, events: int, timeout: float = None) -> list:
    # Prefer the `selectors` module rather than the lower-level `select` module to
    # improve cross-platform support.
    # See: https://github.com/encode/httpcore/issues/182
    sel = selectors.DefaultSelector()
    for sock in socks:
        sel.register(sock, events)
    return [key.fileobj for key, mask in sel.select(timeout) if mask & events]


def wait_for_read(socks: list, timeout: float = None) -> list:
    return _wait_for_io_events(socks, events=selectors.EVENT_READ, timeout=timeout)
