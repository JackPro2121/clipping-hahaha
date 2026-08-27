import pytest
from pathlib import Path
from pipeline.brand import get_brand_filter, get_logo_path, get_logo_overlay


def test_brand_disabled():
    cfg = {"brand": {"enabled": False, "handle": "@ZenCut"}}
    assert get_brand_filter(cfg) is None
    assert get_logo_path(cfg) is None


def test_brand_enabled_bottom_right():
    cfg = {
        "brand": {
            "enabled": True,
            "handle": "@ZenCut",
            "position": "bottom_right",
            "opacity": 0.5,
            "font_size": 28,
        }
    }
    vf = get_brand_filter(cfg)
    assert vf is not None
    assert "drawtext=" in vf
    assert "@ZenCut" in vf
    assert "fontsize=28" in vf
    assert "x=w-tw-50" in vf


def test_brand_enabled_top_left():
    cfg = {
        "brand": {
            "enabled": True,
            "handle": "@ZenCut",
            "position": "top_left",
        }
    }
    vf = get_brand_filter(cfg)
    assert vf is not None
    assert "@ZenCut" in vf
    assert "x=50:y=140" in vf


def test_get_logo_path_exists(tmp_path):
    logo = tmp_path / "test_logo.png"
    logo.write_bytes(b"fake_png_data")
    cfg = {"brand": {"enabled": True, "logo_path": str(logo)}}
    p = get_logo_path(cfg)
    assert p == logo


def test_get_logo_overlay():
    cfg = {
        "brand": {
            "enabled": True,
            "handle": "@ZenCut",
            "logo_width": 135,
            "opacity": 0.9,
            "position": "top_left",
        }
    }
    parts, out_name = get_logo_overlay(cfg, logo_input_idx=2, base_stream="vscaled", out_stream="vout")
    assert out_name == "vout"
    assert len(parts) == 3
    assert "[2:v]scale=135:-1" in parts[0]
    assert "[vscaled][logo_scaled]overlay=50:130[v_with_logo]" in parts[1]
    assert "drawtext=text='@ZenCut'" in parts[2]


def test_get_hook_banner_filter_valid():
    from pipeline.brand import get_hook_banner_filter
    vf = get_hook_banner_filter({}, "Satisfying 100-Year Antique Restoration", duration_s=3.8)
    assert vf is not None
    assert "drawtext=" in vf
    assert "Satisfying 100-Year Antique Restoration" in vf
    assert "enable='between(t,0,3.8)'" in vf
    assert "box=1" in vf
    assert "x=(w-text_w)/2:y=230" in vf


def test_get_hook_banner_filter_empty():
    from pipeline.brand import get_hook_banner_filter
    assert get_hook_banner_filter({}, "") is None
    assert get_hook_banner_filter({}, None) is None


def test_get_hook_banner_filter_escapes_and_caps():
    from pipeline.brand import get_hook_banner_filter
    long_text = "This is an extremely long title with quotes 'and' colons: that needs safe escaping and length truncation"
    vf = get_hook_banner_filter({}, long_text)
    assert vf is not None
    assert "\\:" in vf or ":" not in vf.split("text=")[1].split(":")[0]
    assert "'" not in vf.split("text=")[1].split("'")[0]  # text quotes removed from inner text

