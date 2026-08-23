"""Tests for clip._pick_video_stream — stream selection robustness."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clip import _pick_video_stream  # noqa: E402


def test_picks_video_stream_when_audio_first():
    # Douyin-style container: audio stream listed first, no width on it
    streams = [
        {"index": 0, "codec_type": "audio", "channels": 2},
        {"index": 1, "codec_type": "video", "width": 1080, "height": 1920},
    ]
    s = _pick_video_stream(streams)
    assert s is not None and s["width"] == 1080


def test_skips_video_stream_without_dimensions():
    # Cover-image/mjpeg pseudo-streams may carry codec_type video but no width
    streams = [
        {"codec_type": "video"},
        {"codec_type": "audio"},
        {"codec_type": "video", "width": 1920, "height": 1080},
    ]
    assert _pick_video_stream(streams)["width"] == 1920


def test_returns_none_without_any_video():
    streams = [{"codec_type": "audio"}, {"codec_type": "data"}]
    assert _pick_video_stream(streams) is None


def test_returns_none_for_empty_list():
    assert _pick_video_stream([]) is None
