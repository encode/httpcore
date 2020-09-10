import sniffio


def lookup_async_backend():
    return sniffio.current_async_library()


def lookup_sync_backend():
    return "sync"
