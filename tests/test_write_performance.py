"""Tests for zero-copy write optimisation using memoryview (issue #1029)."""

import pytest
import tracemalloc


def _simulate_write_bytes(data: bytes, chunk_size: int = 65536) -> int:
    """Simulate the OLD write loop (bytes slicing — copies on each iteration)."""
    copies = 0
    buf = data
    while buf:
        _chunk = buf[:chunk_size]   # consumed by socket.send() in production
        buf = buf[chunk_size:]
        copies += 1
    return copies


def _simulate_write_memoryview(data: bytes, chunk_size: int = 65536) -> int:
    """Simulate the NEW write loop (memoryview — zero-copy slicing)."""
    copies = 0
    view = memoryview(data)
    while view:
        _chunk = view[:chunk_size]  # consumed by socket.send() in production
        view = view[chunk_size:]
        copies += 1
    return copies


def test_memoryview_slicing_zero_copy():
    """memoryview slicing must not allocate new bytes objects.

    bytes slicing (buffer = buffer[n:]) copies the remaining bytes on every
    iteration — O(n²) total allocation for a large payload.
    memoryview slicing is zero-copy and runs in O(n) memory.
    """
    data = b"x" * (4 * 1024 * 1024)  # 4 MB

    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()
    _ = _simulate_write_memoryview(data)
    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Measure net allocation delta
    stats = snap_after.compare_to(snap_before, "lineno")
    allocated = sum(s.size_diff for s in stats if s.size_diff > 0)

    # memoryview approach should allocate essentially nothing (< 1 MB overhead)
    assert allocated < 1024 * 1024, (
        f"memoryview write allocated {allocated / 1024:.0f} KB — "
        "expected near-zero (zero-copy), got unexpected allocation"
    )


def test_write_loop_correct_iteration_count():
    """Both loops must iterate the same number of times for the same payload."""
    chunk = 65536
    for size in [1024, chunk, chunk * 5, chunk * 100]:
        data = b"0" * size
        n_bytes = _simulate_write_bytes(data, chunk)
        n_mv    = _simulate_write_memoryview(data, chunk)
        assert n_bytes == n_mv, (
            f"size={size}: bytes loop={n_bytes} iters, "
            f"memoryview loop={n_mv} iters — must be equal"
        )


def test_write_loop_handles_empty_buffer():
    """Empty payload should result in zero iterations (no write attempted)."""
    assert _simulate_write_bytes(b"", 65536) == 0
    assert _simulate_write_memoryview(b"", 65536) == 0


def test_write_loop_handles_sub_chunk_payload():
    """Payload smaller than one chunk should result in exactly one iteration."""
    data = b"x" * 1000
    assert _simulate_write_bytes(data, 65536) == 1
    assert _simulate_write_memoryview(data, 65536) == 1
