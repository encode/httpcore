import pytest

from httpcore._exceptions import map_exceptions


def test_map_single_exception() -> None:
    with pytest.raises(TypeError):
        with map_exceptions({ValueError: TypeError}):
            raise ValueError("nope")


def test_map_multiple_exceptions() -> None:
    with pytest.raises(ValueError):
        with map_exceptions({IndexError: ValueError, KeyError: ValueError}):
            raise KeyError("nope")


def test_unhandled_map_exception() -> None:
    with pytest.raises(TypeError):
        with map_exceptions({IndexError: ValueError, KeyError: ValueError}):
            raise TypeError("nope")
