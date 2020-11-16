import itertools
from typing import List

import pytest

from httpcore._utils import exponential_backoff


@pytest.mark.parametrize(
    "factor, expected",
    [
        (0.1, [0, 0.1, 0.2, 0.4, 0.8]),
        (0.2, [0, 0.2, 0.4, 0.8, 1.6]),
        (0.5, [0, 0.5, 1.0, 2.0, 4.0]),
    ],
)
def test_exponential_backoff(factor: float, expected: List[int]) -> None:
    delays = list(itertools.islice(exponential_backoff(factor), 5))
    assert delays == expected
