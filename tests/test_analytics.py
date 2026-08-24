"""test_analytics.py — performance feedback loop aggregation."""
from pipeline.analytics import _post_likes, _post_views, build_digest


def test_post_views_prefers_views_metric():
    assert _post_views({"Views": 100}) == 100
    assert _post_views({"Impressions": 250}) == 250
    # Views wins when both present (never happens per-service, but be safe)
    assert _post_views({"Views": 100, "Impressions": 250}) == 350


def test_post_likes_sums_variants():
    assert _post_likes({"Reactions": 5}) == 5
    assert _post_likes({"Likes": 3, "Reactions": 5}) == 8
    assert _post_likes({}) == 0


def test_build_digest_totals_and_top():
    channels_posts = {
        "instagram": [
            {"sent_at": "2026-08-24T11:00:00+00:00", "text": "clip A", "views": 500, "reach": 400, "likes": 10},
            {"sent_at": "2026-08-23T11:00:00+00:00", "text": "clip B", "views": 100, "reach": 90, "likes": 2},
        ],
        "facebook": [
            {"sent_at": "2026-08-22T11:00:00+00:00", "text": "clip C", "views": 300, "reach": 0, "likes": 1},
        ],
    }
    d = build_digest(channels_posts, days=30)
    assert d["total_posts"] == 3
    assert d["total_views"] == 900
    assert d["channels"]["instagram"]["avg_views"] == 300.0
    assert d["channels"]["facebook"]["best_views"] == 300
    assert d["top_posts"][0]["views"] == 500
    assert d["top_posts"][0]["service"] == "instagram"


def test_build_digest_empty_channels():
    d = build_digest({"tiktok": []}, days=7)
    assert d["total_posts"] == 0
    assert d["channels"]["tiktok"]["avg_views"] == 0
    assert d["top_posts"] == []
