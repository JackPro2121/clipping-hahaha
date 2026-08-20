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
