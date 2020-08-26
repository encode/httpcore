import functools
import inspect

import curio
import curio.debug
import curio.meta
import curio.monitor
import pytest


def _is_coroutine(obj):
    """Check to see if an object is really a coroutine."""
    return curio.meta.iscoroutinefunction(obj) or inspect.isgeneratorfunction(obj)


@pytest.mark.tryfirst
def curio_pytest_pycollect_makeitem(collector, name, obj):
    """A pytest hook to collect coroutines in a test module."""
    if collector.funcnamefilter(name) and _is_coroutine(obj):
        item = pytest.Function.from_parent(collector, name=name)
        if "curio" in item.keywords:
            return list(collector._genfunctions(name, obj))


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def curio_pytest_pyfunc_call(pyfuncitem):
    """Run curio marked test functions in a Curio kernel
    instead of a normal function call."""
    if pyfuncitem.get_closest_marker("curio"):
        pyfuncitem.obj = wrap_in_sync(pyfuncitem.obj)
    yield


def wrap_in_sync(func):
    """Return a sync wrapper around an async function executing it in a Kernel."""

    @functools.wraps(func)
    def inner(**kwargs):
        coro = func(**kwargs)
        curio.Kernel().run(coro, shutdown=True)

    return inner
