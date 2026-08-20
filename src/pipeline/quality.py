"""quality.py — Source video scoring and quality filtering before processing.

Scores videos from 0 to 100 based on:
  - View counts (0 to 40 pts)
  - Video duration sweet-spot (0 to 35 pts)
  - Subtitle track availability (0 to 25 pts)
"""


def score_source(src):
    """Calculate a quality score (0-100) for a source video.

    Args:
        src: Source dictionary containing 'views', 'length', and optional 'has_subtitles'.

    Returns:
        int: Score from 0 to 100.
    """
    score = 0
    views = src.get("views") or 0
    length = src.get("length") or 0

    # 1. View Engagement (0-40)
    if views >= 1_000_000:
        score += 40
    elif views >= 500_000:
        score += 32
    elif views >= 100_000:
        score += 24
    elif views >= 20_000:
        score += 16
    elif views >= 5_000:
        score += 8

    # 2. Duration Sweet-Spot (0-35)
    # Ideal range is 60s - 300s (produces 1 to 3 solid 45s clips without excessive bloat)
    if 60 <= length <= 240:
        score += 35
    elif 40 <= length < 60:
        score += 25
    elif 240 < length <= 480:
        score += 25
    elif 480 < length <= 900:
        score += 15
    # length > 900 or < 30 gets 0 duration points

    # 3. Subtitles Available (0-25)
    if src.get("has_subtitles"):
        score += 25

    return score


def should_process(src, min_score=20):
    """Determine if a source video meets the minimum quality threshold.

    Args:
        src: Source dictionary.
        min_score: Minimum required score (default: 20).

    Returns:
        bool: True if source passes quality bar.
    """
    return score_source(src) >= min_score
