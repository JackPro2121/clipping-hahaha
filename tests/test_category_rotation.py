import pytest
from find_sources import _get_next_target


def test_get_next_target_keywords():
    cfg = {"discovery": {"keywords": ["木工", "修复", "解压"]}}
    state = {"_meta": {}}
    ttype, val = _get_next_target(cfg, state)
    assert ttype == "keyword"
    assert val == "木工"

    state["_meta"]["last_keyword"] = "木工"
    ttype, val = _get_next_target(cfg, state)
    assert ttype == "keyword"
    assert val == "修复"

    state["_meta"]["last_keyword"] = "修复"
    ttype, val = _get_next_target(cfg, state)
    assert ttype == "keyword"
    assert val == "解压"

    state["_meta"]["last_keyword"] = "解压"
    ttype, val = _get_next_target(cfg, state)
    assert ttype == "keyword"
    assert val == "木工"


def test_get_next_target_categories():
    cfg = {"discovery": {"categories": ["food", "tech"]}}
    state = {"_meta": {}}
    ttype, val = _get_next_target(cfg, state)
    assert ttype == "category"
    assert val == "food"

    state["_meta"]["last_category"] = "food"
    ttype, val = _get_next_target(cfg, state)
    assert ttype == "category"
    assert val == "tech"
