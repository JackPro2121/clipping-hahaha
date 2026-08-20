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
    """Build ffmpeg filter_complex parts for image logo watermark overlay.

    Args:
        cfg: Config dictionary.
        logo_input_idx: Integer index of the logo input file (e.g. 1 or 2).
        base_stream: Name of input video stream (e.g. 'vcat' or 'vscaled').
        out_stream: Name of output video stream (e.g. 'vout').

    Returns:
        tuple[list[str], str]: (filter_parts_list, final_stream_name)
    """
    brand = cfg.get("brand") or {}
    logo_w = brand.get("logo_width", 130)
    opacity = brand.get("opacity", 0.85)
    position = brand.get("position", "top_left")

    # Safe zone coordinates for 1080x1920 canvas (clears TikTok/Reels UI)
    if position == "top_left":
        pos_expr = "50:140"
    elif position == "top_right":
        pos_expr = f"W-w-50:140"
    elif position == "bottom_right":
        pos_expr = f"W-w-50:H-h-200"
    elif position == "bottom_left":
        pos_expr = f"50:H-h-200"
    else:
        pos_expr = "50:140"

    parts = [
        f"[{logo_input_idx}:v]scale={logo_w}:-1,format=rgba,colorchannelmixer=aa={opacity}[logo_scaled]",
        f"[{base_stream}][logo_scaled]overlay={pos_expr}[{out_stream}]",
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
