import pytest
from find_sources import _get_next_category


def test_get_next_category_initial():
    cfg = {"discovery": {"categories": ["popular", "food", "tech"]}}
    state = {"_meta": {}}
    cat = _get_next_category(cfg, state)
    assert cat == "popular"


def test_get_next_category_round_robin():
    cfg = {"discovery": {"categories": ["popular", "food", "tech"]}}
    state = {"_meta": {"last_category": "popular"}}
    assert _get_next_category(cfg, state) == "food"

    state["_meta"]["last_category"] = "food"
    assert _get_next_category(cfg, state) == "tech"

    state["_meta"]["last_category"] = "tech"
    assert _get_next_category(cfg, state) == "popular"
