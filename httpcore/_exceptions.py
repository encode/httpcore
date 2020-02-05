import contextlib
import typing


@contextlib.contextmanager
def map_exceptions(
    from_exc: typing.Type[Exception], to_exc: typing.Type[Exception]
) -> typing.Iterator[None]:
    try:
        yield
    except from_exc as exc:
        raise to_exc(exc) from exc


class ProtocolError(Exception):
    pass


class ConnectTimeout(Exception):
    pass


class ReadTimeout(Exception):
    pass


class WriteTimeout(Exception):
    pass


class NetworkError(Exception):
    pass
