from main import build_caption, sanitize_caption_title


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


def test_sanitize_caption_title():
    # Craft titles should pass through
    assert sanitize_caption_title("Making a Japanese Wood Chisel") == "Making a Japanese Wood Chisel"
    assert sanitize_caption_title("Ancient Sword Restoration Process") == "Ancient Sword Restoration Process"
    assert sanitize_caption_title("Satisfying lathe machining") == "Satisfying lathe machining"

    # Off-niche titles should be replaced with generic on-brand fallback
    off_niche = "The immune system fight against viral infections in humans"
    assert sanitize_caption_title(off_niche) == "Incredible Craft Mastery You Have to See"
    assert sanitize_caption_title("") == "Incredible Craft Mastery You Have to See"
    assert sanitize_caption_title(None) == "Incredible Craft Mastery You Have to See"
