"""tests/test_creator_discovery.py — Unit tests for creator discovery on Bilibili and Douyin."""

from unittest.mock import patch, MagicMock
from pipeline.creator_discovery import (
    _fetch_bilibili_creator_videos,
    discover_bilibili_creators,
    discover_bilibili_creator_accounts,
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
            "12345", max_count=1, min_duration_s=30, max_duration_s=600, order="pubdate"
        )


def test_discover_douyin_creators_empty_profiles():
    cfg = {"discovery": {"douyin_creator_profiles": []}}
    results = discover_douyin_creators(cfg)
    assert results == []


# ---------------------------------------------------------------------------
# discover_bilibili_creator_accounts tests
# ---------------------------------------------------------------------------

def _make_bili_user_resp(users):
    """Build a mock Bilibili bili_user search response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"result": users}}
    return mock_resp


def test_discover_bilibili_creator_accounts_empty_response():
    """Returns empty list when Bilibili returns 404 or empty results."""
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 404
        result = discover_bilibili_creator_accounts(["木工"])
        assert result == []


def test_discover_bilibili_creator_accounts_filters_by_threshold():
    """Creators below min_fans or min_videos are excluded."""
    users = [
        {"uname": "GoodCreator", "fans": 50000, "videos": 10, "mid": 1},
        {"uname": "TooFewFans",  "fans": 100,   "videos": 10, "mid": 2},
        {"uname": "TooFewVids",  "fans": 50000, "videos": 1,  "mid": 3},
    ]
    mock_resp = _make_bili_user_resp(users)
    with patch("requests.get", return_value=mock_resp):
        result = discover_bilibili_creator_accounts(
            ["木工"], min_fans=3000, min_videos=3
        )
    assert result == ["GoodCreator"]


def test_discover_bilibili_creator_accounts_deduplicates_across_keywords():
    """Same creator found under two keywords is returned only once, sorted by fans desc."""
    shared_creator = {"uname": "MasterCarver", "fans": 80000, "videos": 20, "mid": 1}
    other_creator  = {"uname": "SmithForge",   "fans": 30000, "videos": 8,  "mid": 2}

    _SPI_RESP = MagicMock()
    _SPI_RESP.status_code = 200
    _SPI_RESP.json.return_value = {"data": {"b_3": "x", "b_4": "y"}}

    def fake_get(url, **kwargs):
        # _bili_headers calls the fingerprint SPI endpoint first
        if "finger/spi" in url:
            return _SPI_RESP
        # bili_user search — return both creators for keyword 木工, only shared for 修复
        if "bili_user" in url:
            if "%E6%9C%A8%E5%B7%A5" in url:  # 木工 URL-encoded
                return _make_bili_user_resp([shared_creator, other_creator])
            return _make_bili_user_resp([shared_creator])  # 修复: duplicate
        return MagicMock(status_code=404)

    with patch("requests.get", side_effect=fake_get):
        result = discover_bilibili_creator_accounts(
            ["木工", "修复"], min_fans=3000, min_videos=3
        )
    # MasterCarver (80k fans) first, SmithForge (30k fans) second, no duplicates
    assert "MasterCarver" in result
    assert "SmithForge" in result
    assert result.index("MasterCarver") < result.index("SmithForge")
    assert len(result) == 2
