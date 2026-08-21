"""tests/test_creator_discovery.py — Unit tests for creator discovery on Bilibili and Douyin."""

from unittest.mock import patch, MagicMock
from pipeline.creator_discovery import (
    _fetch_bilibili_creator_videos,
    discover_bilibili_creators,
    discover_douyin_creators,
)


def test_fetch_bilibili_creator_videos_empty():
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 404
        videos = _fetch_bilibili_creator_videos("999999")
        assert videos == []


def test_fetch_bilibili_creator_videos_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "result": [
                {
                    "bvid": "BV1test123",
                    "title": "Master Woodworker Chair Restoration",
                    "play": 125000,
                    "duration": "02:45",
                }
            ]
        }
    }
    with patch("requests.get", return_value=mock_resp):
        videos = _fetch_bilibili_creator_videos("12345", max_count=2)
        assert len(videos) == 1
        assert videos[0]["url"] == "https://www.bilibili.com/video/BV1test123"
        assert videos[0]["views"] == 125000
        assert videos[0]["length"] == 165
        assert "creator_12345" in videos[0]["category"]


def test_discover_bilibili_creators_with_configured_uids():
    cfg = {
        "discovery": {
            "bilibili_creator_uids": ["12345"],
            "min_source_duration_s": 30,
            "max_duration_s": 600,
        }
    }
    with patch(
        "pipeline.creator_discovery._fetch_bilibili_creator_videos"
    ) as mock_fetch:
        mock_fetch.return_value = [
            {
                "url": "https://www.bilibili.com/video/BV1xyz",
                "title": "Test Video",
                "views": 80000,
                "length": 60,
                "category": "bilibili_creator_12345",
            }
        ]
        results = discover_bilibili_creators(cfg)
        assert len(results) == 1
        assert results[0]["url"] == "https://www.bilibili.com/video/BV1xyz"
        mock_fetch.assert_called_once_with(
            "12345", max_count=2, min_duration_s=30, max_duration_s=600, order="pubdate"
        )


def test_discover_douyin_creators_empty_profiles():
    cfg = {"discovery": {"douyin_creator_profiles": []}}
    results = discover_douyin_creators(cfg)
    assert results == []
