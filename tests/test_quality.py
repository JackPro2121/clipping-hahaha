import pytest
from pipeline.quality import score_source, should_process


def test_score_source_high_views_sweet_duration():
    src = {
        "views": 1_200_000,
        "length": 120,
        "has_subtitles": True,
    }
    score = score_source(src)
    # 40 (views) + 35 (duration) + 25 (subtitles) = 100
    assert score == 100
    assert should_process(src, min_score=50) is True


def test_score_source_low_engagement():
    src = {
        "views": 200,
        "length": 1200,
        "has_subtitles": False,
    }
    score = score_source(src)
    # 0 (views) + 0 (duration) + 0 (subtitles) = 0
    assert score == 0
    assert should_process(src, min_score=20) is False


def test_score_source_mid_tier():
    src = {
        "views": 50_000,
        "length": 45,
        "has_subtitles": False,
    }
    score = score_source(src)
    # 16 (views) + 25 (duration) = 41
    assert score == 41
    assert should_process(src, min_score=40) is True
