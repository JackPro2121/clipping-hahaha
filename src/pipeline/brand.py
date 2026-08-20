"""brand.py — Channel branding, watermark overlays, and platform watermarking.

Builds ffmpeg drawtext filter strings for non-intrusive brand identifiers.
"""


def get_brand_filter(cfg):
    """Generate an ffmpeg drawtext video filter string for channel watermarking.

    Args:
        cfg: Configuration dictionary with optional 'brand' section.

    Returns:
        str | None: ffmpeg filter snippet, or None if branding is disabled.
    """
    brand = cfg.get("brand") or {}
    if not brand.get("enabled"):
        return None

    handle = brand.get("handle") or brand.get("channel_name")
    if not handle:
        return None

    position = brand.get("position", "bottom_right")
    opacity = brand.get("opacity", 0.6)
    font_size = brand.get("font_size", 32)

    # Position coordinates (1080x1920 vertical canvas)
    if position == "bottom_right":
        pos_expr = "x=w-tw-40:y=h-th-180"  # above TikTok bottom UI
    elif position == "top_right":
        pos_expr = "x=w-tw-40:y=120"
    elif position == "top_left":
        pos_expr = "x=40:y=120"
    elif position == "bottom_left":
        pos_expr = "x=40:y=h-th-180"
    else:
        pos_expr = "x=w-tw-40:y=h-th-180"

    escaped_handle = str(handle).replace(":", "\\:").replace("'", "")
    alpha_hex = f"{int(opacity * 255):02X}"

    # drawtext filter with semi-transparent font and subtle shadow
    vf = (
        f"drawtext=text='{escaped_handle}':"
        f"fontsize={font_size}:fontcolor=0xFFFFFF{alpha_hex}:"
        f"shadowcolor=0x000000{alpha_hex}:shadowx=2:shadowy=2:"
        f"{pos_expr}"
    )
    return vf
