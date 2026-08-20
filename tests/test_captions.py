import pytest
from clip import _ass_ts, _wrap
from captions.bilibili_subtitles import make_title_captions, bvid_from_url


def test_ass_ts():
    assert _ass_ts(0.0) == "0:00:00.00"
    assert _ass_ts(65.432) == "0:01:05.43"
    assert _ass_ts(3661.5) == "1:01:01.50"


def test_wrap_short_text():
    text = "Hello world"
    wrapped = _wrap(text, width=20)
    assert wrapped == "Hello world"


def test_wrap_long_text():
    text = "This is a longer line of text that needs to be wrapped nicely"
    wrapped = _wrap(text, width=20)
    assert "\\N" in wrapped
    lines = wrapped.split("\\N")
    for line in lines:
        assert len(line) <= 30  # word boundaries allow slight variation


def test_make_title_captions():
    title = "Awesome viral clip from trending feed"
    caps = make_title_captions(title, total_duration=30.0)
    assert caps is not None
    assert len(caps) > 0
    assert caps[0]["start"] == 0.0
    assert caps[0]["text"] == title


def test_make_title_captions_empty():
    assert make_title_captions("") is None
    assert make_title_captions("   ") is None


def test_bvid_from_url():
    assert bvid_from_url("https://www.bilibili.com/video/BV1bM8E6yEYd") == "BV1bM8E6yEYd"
    assert bvid_from_url("https://bilibili.com/video/BV1BS876oEwP?p=1") == "BV1BS876oEwP"
    assert bvid_from_url("https://www.youtube.com/watch?v=12345678901") is None
