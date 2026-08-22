import pytest
from main import build_caption


def test_build_caption_formatting():
    cfg = {
        "buffer": {
            "caption_template": "{title} - Part {index}/{total} {hashtags}",
            "hashtags": "#shorts #viral",
        }
    }
    title = "Funny Cat Moment"
    caption = build_caption(cfg, title, 1, 3)
    assert caption == "Funny Cat Moment - Part 1/3 #shorts #viral"


def test_build_caption_no_hashtags():
    cfg = {
        "buffer": {
            "caption_template": "{title} ({index}/{total})",
        }
    }
    title = "Recipe Tutorial"
    caption = build_caption(cfg, title, 2, 4)
    assert caption == "Recipe Tutorial (2/4)"


def test_build_caption_per_platform():
    cfg = {
        "buffer": {
            "caption_template": "Default {title}",
            "hashtags": "#craft",
            "per_platform_captions": {
                "facebook": "{title} - Daily Crafts! {hashtags}",
                "tiktok": "TikTok: {title} {hashtags}"
            }
        }
    }
    fb_caption = build_caption(cfg, "Wood Art", 1, 1, service="facebook")
    assert fb_caption == "Wood Art - Daily Crafts! #craft"
    tt_caption = build_caption(cfg, "Wood Art", 1, 1, service="tiktok")
    assert tt_caption == "TikTok: Wood Art #craft"
    default_caption = build_caption(cfg, "Wood Art", 1, 1, service="youtube")
    assert default_caption == "Default Wood Art"
