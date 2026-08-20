import pytest
from clip import _filter_path


def test_filter_path_windows():
    # On Windows: C:\path\file.ass -> C\:/path/file.ass
    # Backslashes are converted to forward slashes, but the colon is escaped with a backslash (\:)
    win_path = r"C:\Users\test\clips\clip_01.ass"
    escaped = _filter_path(win_path)
    assert "C\\:" in escaped
    assert "/Users/test/clips/clip_01.ass" in escaped
    # Ensure all path separators are forward slashes
    path_without_colon = escaped.replace("C\\:", "")
    assert "\\" not in path_without_colon


def test_filter_path_posix():
    posix_path = "/tmp/clips/clip_01.ass"
    escaped = _filter_path(posix_path)
    assert escaped == "/tmp/clips/clip_01.ass"
