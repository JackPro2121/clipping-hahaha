import pytest
from clip import _select_windows


def test_select_windows_standard():
    cfg = {"clip_length_s": 45, "max_clips_per_video": 3, "min_clip_s": 30}
    duration = 100.0  # 45, 45, remainder 10 (< 30, dropped)
    windows = _select_windows(duration, cfg)
    assert len(windows) == 2
    assert windows[0] == (0.0, 45)
    assert windows[1] == (45.0, 45)


def test_select_windows_short_video():
    cfg = {"clip_length_s": 45, "max_clips_per_video": 3, "min_clip_s": 30}
    duration = 35.0  # single clip 35s
    windows = _select_windows(duration, cfg)
    assert len(windows) == 1
    assert windows[0] == (0.0, 35.0)


def test_select_windows_too_short():
    cfg = {"clip_length_s": 45, "max_clips_per_video": 3, "min_clip_s": 30}
    duration = 25.0  # < min_clip_s
    windows = _select_windows(duration, cfg)
    assert len(windows) == 0


def test_select_windows_max_clips_cap():
    cfg = {"clip_length_s": 30, "max_clips_per_video": 2, "min_clip_s": 10}
    duration = 300.0
    windows = _select_windows(duration, cfg)
    assert len(windows) == 2
