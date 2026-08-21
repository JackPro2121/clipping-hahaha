import pytest
from clip import _chunks


def test_chunks_exact_split():
    start = 0.0
    duration = 12.0
    chunk_s = 4.0
    chunks = _chunks(start, duration, chunk_s)
    assert len(chunks) == 3
    assert chunks[0] == (0.0, 4.0)
    assert chunks[1] == (4.0, 4.0)
    assert chunks[2] == (8.0, 4.0)


def test_chunks_with_remainder():
    start = 10.0
    duration = 9.5
    chunk_s = 4.0
    chunks = _chunks(start, duration, chunk_s)
    # 4.0, 4.0, 1.5
    assert len(chunks) == 3
    assert chunks[0] == (10.0, 4.0)
    assert chunks[1] == (14.0, 4.0)
    assert chunks[2] == (18.0, 1.5)


def test_chunks_drop_tiny_trailing_chunk():
    start = 0.0
    duration = 4.04  # remainder 0.04 < 0.05 / 1.0 threshold
    chunk_s = 4.0
    chunks = _chunks(start, duration, chunk_s)
    assert len(chunks) == 1
    assert chunks[0] == (0.0, 4.0)


def test_chunks_variable_pacing():
    start = 0.0
    duration = 20.0
    chunk_s = 4.0
    chunks = _chunks(start, duration, chunk_s, variable_pacing=True)
    assert len(chunks) > 0
    # First chunk should be scaled by 0.85 (3.4s)
    assert chunks[0] == (0.0, 3.4)
    # Second chunk should be scaled by 1.15 (4.6s)
    assert chunks[1] == (3.4, 4.6)
