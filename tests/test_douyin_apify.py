"""Tests for douyin_apify.map_apify_item — Apify dataset item -> source mapping."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from douyin_apify import map_apify_item  # noqa: E402


def _sample_item(**overrides):
    item = {
        "id": "7617856244463766824",
        "groupId": "7617856244463766824",
        "type": "video",
        "mediaTypeLabel": "video",
        "text": "传统榫卯工艺打造胡桃木会议桌 #木工",
        "statistics": {"playCount": 12345, "commentCount": 100},
        "videoMeta": {
            "duration": 76200,
            "width": 1080,
            "height": 1920,
            "ratio": "720p",
            "format": "mp4",
            "playUrl": "https://api-play.amemv.com/aweme/v1/play/?video_id=abc",
            "downloadUrl": "https://v9-v2-mps-cdn.douyinvod.com/x/main.mp4",
        },
    }
    item.update(overrides)
    return item


def test_maps_basic_item():
    src = map_apify_item(_sample_item())
    assert src is not None
    assert src["url"] == "https://www.douyin.com/video/7617856244463766824"
    assert src["origin"] == "douyin_apify"
    assert src["length"] == 76
    assert src["views"] == 12345
    assert "amemv" in src["play_url"]
    assert src["resolution"] == "1080x1920"


def test_prefers_playurl_over_downloadurl():
    src = map_apify_item(_sample_item())
    assert "amemv" in src["play_url"]


def test_falls_back_to_downloadurl_when_no_playurl():
    item = _sample_item()
    item["videoMeta"] = {**item["videoMeta"], "playUrl": None}
    src = map_apify_item(item)
    assert src is not None and "douyinvod" in src["play_url"]


def test_rejects_missing_play_urls():
    item = _sample_item()
    item["videoMeta"] = {**item["videoMeta"], "playUrl": None, "downloadUrl": None}
    assert map_apify_item(item) is None


def test_rejects_non_video_types():
    assert map_apify_item(_sample_item(type="image")) is None


def test_rejects_missing_id():
    assert map_apify_item(_sample_item(id=None, groupId=None)) is None


def test_duration_converted_from_ms():
    src = map_apify_item(_sample_item())
    assert src["length"] == 76  # 76200ms -> 76s


def test_title_from_caption_when_text_missing():
    src = map_apify_item(_sample_item(text="", caption="手工锻造菜刀"))
    assert src["title"] == "手工锻造菜刀"
