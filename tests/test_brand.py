import pytest
from pipeline.brand import get_brand_filter


def test_brand_disabled():
    cfg = {"brand": {"enabled": False, "handle": "@test"}}
    assert get_brand_filter(cfg) is None


def test_brand_enabled_bottom_right():
    cfg = {
        "brand": {
            "enabled": True,
            "handle": "@JackOscar",
            "position": "bottom_right",
            "opacity": 0.5,
            "font_size": 28,
        }
    }
    vf = get_brand_filter(cfg)
    assert vf is not None
    assert "drawtext=" in vf
    assert "@JackOscar" in vf
    assert "fontsize=28" in vf
    assert "x=w-tw-40" in vf


def test_brand_enabled_top_left():
    cfg = {
        "brand": {
            "enabled": True,
            "handle": "@ClipChannel",
            "position": "top_left",
        }
    }
    vf = get_brand_filter(cfg)
    assert vf is not None
    assert "@ClipChannel" in vf
    assert "x=40:y=120" in vf
