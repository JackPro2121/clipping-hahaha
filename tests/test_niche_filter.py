"""test_niche_filter.py — niche keyword gate + LLM relevance tier.

Regression: the palace-park workout video "今天是年轻人专场，作为宫廷盘杠传承人，
我带领大家用传统技艺强身健体，非遗正青春！" passed the positive-keyword gate via
非遗/传承/传统技艺 and reached the Buffer queue as "craft".
"""
from find_sources import _NEGATIVE_KW, _NICHE_KW


def _relevant(title):
    """Mirror of find_sources' gate logic: negatives win, then positives."""
    t = title.lower()
    if any(neg.lower() in t for neg in _NEGATIVE_KW):
        return False
    return any(kw.lower() in t for kw in _NICHE_KW)


def test_park_workout_title_vetoed():
    """The exact off-topic video that reached the Buffer queue."""
    assert not _relevant("今天是年轻人专场，作为宫廷盘杠传承人，我带领大家用传统技艺强身健体，非遗正青春！")


def test_fitness_keywords_veto():
    for t in ["公园单杠高手表演", "街头健身大佬", "每天锻炼身体的年轻人", "street workout beast"]:
        assert not _relevant(t), t


def test_food_title_vetoed():
    assert not _relevant("东北的孩子打小就爱这一口")


def test_craft_titles_still_pass():
    for t in [
        "三十三道中华榫卯，匠心传承",
        "修复一把50年前的古董级双刃刀",
        "木工雕刻一只小狐狸",
        "320个小时，我把大英博物馆的中国文物做成了一盏灯！",
    ]:
        assert _relevant(t), t


# ── LLM relevance tier (llm/safety.py classify_relevance) ───────────────────

def test_relevance_llm_rejects_workout(monkeypatch):
    import llm.safety as s

    monkeypatch.setattr(
        s, "llm_complete",
        lambda *a, **k: '{"relevant": false, "reason": "park calisthenics, not a craft"}',
    )
    v = s.classify_relevance("宫廷盘杠传承人非遗正青春")
    assert v["relevant"] is False
    assert v["source"] == "llm"


def test_relevance_llm_accepts_craft(monkeypatch):
    import llm.safety as s

    monkeypatch.setattr(
        s, "llm_complete",
        lambda *a, **k: '{"relevant": true, "reason": "wood carving"}',
    )
    v = s.classify_relevance("榫卯木工制作")
    assert v["relevant"] is True


def test_relevance_fails_open_on_garbage(monkeypatch):
    import llm.safety as s

    monkeypatch.setattr(s, "llm_complete", lambda *a, **k: "total garbage")
    v = s.classify_relevance("榫卯木工制作")
    assert v["relevant"] is True
    assert v["source"] == "failopen"


def test_relevance_disabled_is_fail_open():
    import llm.safety as s

    v = s.classify_relevance("随便什么标题", use_llm=False)
    assert v["relevant"] is True
    assert v["source"] == "disabled"


def test_blocked_creator_terms():
    from find_sources import _BLOCKED_CREATOR_TERMS

    blocked_samples = [
        "木可雕real",
        "土木工程洪工",
        "土木白工",
        "国粹非遗正骨传人老张",
        "非遗中医刺血高晓尚",
        "青木动漫工坊",
        "沙雕木其",
    ]
    for creator in blocked_samples:
        assert any(b.lower() in creator.lower() for b in _BLOCKED_CREATOR_TERMS), f"Expected {creator} to be blocked"