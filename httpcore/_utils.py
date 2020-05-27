import logging
import os
import sys
import typing

from ._types import URL, Origin

_LOGGER_INITIALIZED = False
TRACE_LOG_LEVEL = 5


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
    default_port = {b"http": 80, b"https": 443}[scheme]
    port = default_port if explicit_port is None else explicit_port
    return scheme, host, port
