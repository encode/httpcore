import time

import anyio


def async_current_time() -> float:
    return anyio.current_time()


def sync_current_time() -> float:
    return time.monotonic()


async def async_sleep(delay: float) -> None:
    await anyio.sleep(delay)


def sync_sleep(delay: float) -> None:
    time.sleep(delay)
