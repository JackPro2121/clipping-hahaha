"""brand.py — Channel branding, logo watermark overlays, and platform watermarking.

Supports:
  1. Image Logo Overlay (e.g. zencut-logo.png) with customizable scale, opacity, and safe-zone positioning.
  2. Text Watermark (@ZenCut) with drop shadow fallback.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def get_logo_path(cfg):
    """Resolve and return Path to the brand logo image if configured and exists."""
    brand = cfg.get("brand") or {}
    if not brand.get("enabled"):
        return None

    logo_file = brand.get("logo_path") or "zencut-logo.png"
    p = Path(logo_file)
    if not p.is_absolute():
        p = ROOT / logo_file

    if p.exists():
        return p
    return None


def get_logo_overlay(cfg, logo_input_idx, base_stream="vcat", out_stream="vout"):
    """Build ffmpeg filter_complex parts for image logo + text watermark overlay.

    Args:
        cfg: Config dictionary.
        logo_input_idx: Integer index of the logo input file (e.g. 1 or 2).
        base_stream: Name of input video stream (e.g. 'vcat' or 'vscaled').
        out_stream: Name of output video stream (e.g. 'vout').

    Returns:
        tuple[list[str], str]: (filter_parts_list, final_stream_name)
    """
    brand = cfg.get("brand") or {}
    logo_w = brand.get("logo_width", 135)
    opacity = brand.get("opacity", 0.92)
    position = brand.get("position", "top_left")
    handle = brand.get("handle") or "@ZenCut"
    alpha_hex = f"{int(opacity * 255):02X}"

    # Safe zone coordinates for 1080x1920 canvas (clears TikTok/Reels UI)
    if position == "top_left":
        logo_pos = "50:130"
        text_pos = f"x=50:y=130+{int(logo_w * 0.95)}:fontsize=32"
    elif position == "top_right":
        logo_pos = "W-w-50:130"
        text_pos = f"x=w-tw-50:y=130+{int(logo_w * 0.95)}:fontsize=32"
    elif position == "bottom_right":
        logo_pos = "W-w-50:H-h-220"
        text_pos = "x=w-tw-50:y=h-th-200:fontsize=28"
    else:
        logo_pos = "50:130"
        text_pos = f"x=50:y=130+{int(logo_w * 0.95)}:fontsize=32"

    parts = [
        f"[{logo_input_idx}:v]scale={logo_w}:-1,format=rgba,colorchannelmixer=aa={opacity}[logo_scaled]",
        f"[{base_stream}][logo_scaled]overlay={logo_pos}[v_with_logo]",
        f"[v_with_logo]drawtext=text='{handle}':{text_pos}:fontcolor=0xFFFFFF{alpha_hex}:shadowcolor=0x000000{alpha_hex}:shadowx=2:shadowy=2[{out_stream}]",
    ]
    return parts, out_stream


def get_brand_filter(cfg):
    """Generate an ffmpeg drawtext video filter string for channel handle watermarking.

    Args:
        cfg: Configuration dictionary with optional 'brand' section.

    Returns:
        str | None: ffmpeg filter snippet, or None if branding is disabled.
    """
    brand = cfg.get("brand") or {}
    if not brand.get("enabled"):
        return None

    handle = brand.get("handle") or brand.get("name")
    if not handle:
        return None

    position = brand.get("position", "top_left")
    opacity = brand.get("opacity", 0.75)
    font_size = brand.get("font_size", 28)

    # Position coordinates (1080x1920 vertical canvas)
    if position == "bottom_right":
        pos_expr = "x=w-tw-50:y=h-th-200"
    elif position == "top_right":
        pos_expr = "x=w-tw-50:y=140"
    elif position == "top_left":
        pos_expr = "x=50:y=140"
    elif position == "bottom_left":
        pos_expr = "x=50:y=h-th-200"
    else:
        pos_expr = "x=50:y=140"

    escaped_handle = str(handle).replace(":", "\\:").replace("'", "")
    alpha_hex = f"{int(opacity * 255):02X}"

    vf = (
        f"drawtext=text='{escaped_handle}':"
        f"fontsize={font_size}:fontcolor=0xFFFFFF{alpha_hex}:"
        f"shadowcolor=0x000000{alpha_hex}:shadowx=2:shadowy=2:"
        f"{pos_expr}"
    )
    return vf


def get_hook_banner_filter(cfg, hook_text, duration_s=3.8):
    """Generate an ffmpeg drawtext filter for a high-converting curiosity hook banner.

    Displays at upper center for the first `duration_s` seconds (e.g. 0-3.8s)
    to boost 3-second hold rate and retention in Tier-1 countries.

    Args:
        cfg: Configuration dictionary with optional 'brand' / 'effects' section.
        hook_text: Text string to display as the curiosity hook.
        duration_s: Duration in seconds to show the banner (default 3.8s).

    Returns:
        str | None: ffmpeg filter snippet, or None if hook text is empty.
    """
    if not hook_text or not str(hook_text).strip():
        return None

    # Sanitize text for ffmpeg drawtext
    clean_text = str(hook_text).strip().replace(":", "\\:").replace("'", "").replace('"', "")
    # Cap length to fit nicely on vertical screen (1080px) without overflow
    if len(clean_text) > 48:
        clean_text = clean_text[:45].rstrip() + "..."

    font_size = 40
    # Position: top-center below safe-zone (y=240), box with 75% opacity dark background
    vf = (
        f"drawtext=text='{clean_text}':"
        f"fontsize={font_size}:fontcolor=0xFFFFFFFF:"
        f"box=1:boxcolor=0x000000C0:boxborderw=16:"
        f"x=(w-text_w)/2:y=230:"
        f"enable='between(t,0,{duration_s:.1f})'"
    )
    return vf

