from typing import Generator, List

import pytest
from sniffio import current_async_library

from httpcore import AnyIOBackend, AsyncIOBackend, AsyncNetworkBackend, TrioBackend
from httpcore._backends.auto import AutoBackend


@pytest.fixture(scope="session", autouse=True)
def check_tested_backends() -> Generator[List[AsyncNetworkBackend], None, None]:
    # Ensure tests cover all supported backend variants
    backends: List[AsyncNetworkBackend] = []
    yield backends
    assert {b.__class__ for b in backends} == {
        AsyncIOBackend,
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
@pytest.mark.no_auto_backend_patch
async def test_auto_backend_uses_expected_backend(monkeypatch):
    auto = AutoBackend()
    await auto._init_backend()
    assert auto._backend is not None

    if current_async_library() == "trio":
        assert isinstance(auto._backend, TrioBackend)
    else:
        # TODO add support for choosing the AsyncIOBackend in AutoBackend
        assert isinstance(auto._backend, AnyIOBackend)
