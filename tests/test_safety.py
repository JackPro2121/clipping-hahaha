"""test_safety.py — Meta-moderation safety gate (keyword tier + LLM tier)."""
from llm.safety import _keyword_verdict, classify_content_safety


def test_blood_accident_title_rejected():
    """The exact video class that got the FB page restricted."""
    unsafe, hits = _keyword_verdict("血的教训:角磨机装木工锯片")
    assert unsafe is True
    assert "血" in hits


def test_safety_psa_title_rejected():
    unsafe, _ = _keyword_verdict("快一点就没事？拒绝侥幸伸手，别拿生命赌瞬间！")
    assert unsafe is True


def test_normal_craft_titles_safe():
    for title in [
        "三十三道中华榫卯，匠心传承",
        "修复一把50年前的古董级双刃刀",
        "Restoring a 50-year-old antique knife",
        "木工雕刻一只屑狐狸",
    ]:
        unsafe, _ = _keyword_verdict(title)
        assert unsafe is False, title


def test_whitelist_weakens_ambiguous_hits():
    """锋利/打磨 context alone must not reject craft content."""
    unsafe, _ = _keyword_verdict("打磨抛光一把锋利的刀，手工制作")
    assert unsafe is False


def test_classify_keyword_mode_unsafe():
    v = classify_content_safety("工地事故实录，工人受伤", use_llm=False)
    assert v["safe"] is False
    assert v["source"] == "keyword"


def test_classify_keyword_mode_safe():
    v = classify_content_safety("传统木工书桌制作", use_llm=False)
    assert v["safe"] is True


def test_classify_llm_unsafe_verdict(monkeypatch):
    import llm.safety as s

    monkeypatch.setattr(
        s, "llm_complete",
        lambda *a, **k: '{"safe": false, "reason": "shows injury", "severity": "high"}',
    )
    v = classify_content_safety("一些看起来普通的标题", use_llm=True)
    assert v["safe"] is False
    assert v["source"] == "llm"


def test_classify_llm_safe_verdict(monkeypatch):
    import llm.safety as s

    monkeypatch.setattr(
        s, "llm_complete",
        lambda *a, **k: '{"safe": true, "reason": "woodworking", "severity": "none"}',
    )
    v = classify_content_safety("木工制作", use_llm=True)
    assert v["safe"] is True


def test_classify_llm_garbage_falls_open(monkeypatch):
    """LLM unavailable/garbage -> fail-open to keyword verdict."""
    import llm.safety as s

    monkeypatch.setattr(s, "llm_complete", lambda *a, **k: "not json at all")
    v = classify_content_safety("木工制作", use_llm=True)
    assert v["safe"] is True
    assert v["source"] == "keyword"


def test_classify_empty_title_safe():
    assert classify_content_safety("", use_llm=False)["safe"] is True
