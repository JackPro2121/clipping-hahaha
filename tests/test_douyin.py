"""Test Douyin No-Watermark Extractor module."""

import pytest
from douyin import extract_douyin_video_id, get_no_watermark_url


def test_extract_douyin_video_id_standard_url():
    url = "https://www.douyin.com/video/7234567890123456789"
    assert extract_douyin_video_id(url) == "7234567890123456789"


def test_extract_douyin_video_id_note_url():
    url = "https://www.douyin.com/note/7198765432109876543"
    assert extract_douyin_video_id(url) == "7198765432109876543"


def test_extract_douyin_video_id_invalid():
    assert extract_douyin_video_id("") is None
    assert extract_douyin_video_id(None) is None
    assert extract_douyin_video_id("https://youtube.com/watch?v=123") is None


def test_get_no_watermark_url_replaces_playwm():
    wm_url = "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v0200fg10000ch32...&ratio=720p"
    clean_url = get_no_watermark_url(wm_url)
    assert "/play/" in clean_url
    assert "/playwm/" not in clean_url


def test_get_no_watermark_url_passthrough():
    clean_url = "https://aweme.snssdk.com/aweme/v1/play/?video_id=v0200fg10000ch32..."
    assert get_no_watermark_url(clean_url) == clean_url
    assert get_no_watermark_url("") == ""
    assert get_no_watermark_url(None) == ""


def test_douyin_discover_empty():
    from douyin import discover
    cfg = {"discovery": {}}
    res = discover(cfg)
    assert isinstance(res, list)
