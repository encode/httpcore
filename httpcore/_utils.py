import logging
import os
import socket
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


def is_socket_at_eof(sock_fd: int, family: int, type: int) -> bool:
    """
    Return whether a socket, as identified by its file descriptor, has reached
    EOF, i.e. whether its read buffer is empty.

    If we're still expecting data, then the socket being at EOF most likely means
    that the server has disconnected.
    """
    # Duplicate the socket, so we get a distinct throw-away copy.
    # (We do this instead of accepting a `socket` object from the backend-specific
    # implementation, because those may not actually be *real* `socket` objects.
    # We can't use `socket.socket(sock_fd)` either, although it auto-populates family
    # and type, because it would *replace* the existing socket, making the previous
    # file descriptor obsolete.)
    sock = socket.fromfd(sock_fd, family, type)

    # Put the copy into non-blocking mode. We need this so that the `.recv()` call
    # does not block.
    sock.setblocking(False)

    # Then peek a byte of data, to see if there's someone still sending data on the
    # other end, or if they disconnected.
    try:
        data = sock.recv(1, socket.MSG_PEEK)
    except BlockingIOError:
        return False
    else:
        return data == b""
    finally:
        # Dispose the copy.
        sock.close()
