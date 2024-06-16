from typing import Generator, List

import pytest

import httpcore
from httpcore import (
    AnyIOBackend,
    AsyncioBackend,
    AsyncNetworkBackend,
    AutoBackend,
    TrioBackend,
)
from httpcore._synchronization import current_async_backend


@pytest.fixture(scope="session", autouse=True)
def check_tested_backends() -> Generator[List[AsyncNetworkBackend], None, None]:
    # Ensure tests cover all supported backend variants
    backends: List[AsyncNetworkBackend] = []
    yield backends
    assert {b.__class__ for b in backends} == {
        AsyncioBackend,
        AnyIOBackend,
        TrioBackend,
    }


@pytest.mark.anyio
async def test_init_backend(check_tested_backends: List[AsyncNetworkBackend]) -> None:
    auto = AutoBackend()
    await auto._init_backend()
    assert auto._backend is not None
    check_tested_backends.append(auto._backend)


@pytest.mark.anyio
@pytest.mark.parametrize("has_anyio", [False, True])
async def test_auto_backend_asyncio(monkeypatch, has_anyio):
    if current_async_backend() == "trio":
        return

    AutoBackend.set_default_backend(None)

    monkeypatch.setattr(httpcore._backends.auto, "HAS_ANYIO", has_anyio)

    auto = AutoBackend()
    await auto._init_backend()
    assert auto._backend is not None
    assert isinstance(auto._backend, AnyIOBackend if has_anyio else AsyncioBackend)
