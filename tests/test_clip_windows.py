import pytest
from clip import _select_windows


def test_select_windows_sequential():
    cfg = {"clip_length_s": 45, "max_clips_per_video": 3, "min_clip_s": 30, "narrative_arc": False}
    duration = 100.0  # 45, 45, remainder 10 (< 30, dropped)
    windows = _select_windows(duration, cfg)
    assert len(windows) == 2
    assert windows[0] == (0.0, 45)
    assert windows[1] == (45.0, 45)


def test_select_windows_short_video():
    cfg = {"clip_length_s": 36, "max_clips_per_video": 3, "min_clip_s": 24}
    duration = 50.0  # < 1.8 * 36s (64.8s) -> single complete highlight clip
    windows = _select_windows(duration, cfg)
    assert len(windows) == 1
    assert windows[0] == (0.0, 36.0)


def test_select_windows_too_short():
    cfg = {"clip_length_s": 45, "max_clips_per_video": 3, "min_clip_s": 30}
    duration = 25.0  # < min_clip_s
    windows = _select_windows(duration, cfg)
    assert len(windows) == 0


def test_select_windows_medium_video_2clips():
    cfg = {"clip_length_s": 36, "max_clips_per_video": 3, "min_clip_s": 24, "narrative_arc": True}
    duration = 120.0  # 70s - 180s range -> exactly 2 clips (Start + Climax)
    windows = _select_windows(duration, cfg)
    assert len(windows) == 2
    assert windows[0] == (0.0, 36.0)
    assert windows[1][0] >= 36.0  # Starts after Part 1
    assert windows[1][1] == 36.0  # Full 36s clip length


def test_select_windows_long_video_3clips():
    cfg = {"clip_length_s": 36, "max_clips_per_video": 3, "min_clip_s": 24, "narrative_arc": True}
    duration = 300.0  # 5 minutes -> exactly 3 clips (Start, Mid, Climax)
    windows = _select_windows(duration, cfg)
    assert len(windows) == 3
    # Part 1: Start
    assert windows[0] == (0.0, 36.0)
    # Part 2: Middle transformation (centered around 150s)
    assert 120.0 <= windows[1][0] <= 160.0
    assert windows[1][1] == 36.0
    # Part 3: Grand Climax / Final finish (ending around 299s)
    assert windows[2][0] >= 250.0
    assert windows[2][1] == 36.0

