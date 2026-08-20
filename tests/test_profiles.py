"""Test pipeline profile loading and configuration merging."""

import pytest
from utils.config import load_config


def test_load_config_default_profile():
    cfg = load_config()
    assert "_active_profile_key" in cfg
    assert cfg["_active_profile_key"] == "satisfying_crafts"
    assert "木工" in cfg["discovery"]["keywords"]
    assert "#woodworking" in cfg["buffer"]["hashtags"]
    assert "tiktok" in cfg["buffer"]["services"]
    assert "instagram" in cfg["buffer"]["services"]


def test_load_config_profile_override():
    cfg = load_config(profile_override="future_tech_gadgets")
    assert cfg["_active_profile_key"] == "future_tech_gadgets"
    assert "黑科技" in cfg["discovery"]["keywords"]
    assert "#tech" in cfg["buffer"]["hashtags"]


def test_load_config_street_food_profile():
    cfg = load_config(profile_override="street_food_asmr")
    assert cfg["_active_profile_key"] == "street_food_asmr"
    assert "街头美食" in cfg["discovery"]["keywords"]
    assert "#streetfood" in cfg["buffer"]["hashtags"]
