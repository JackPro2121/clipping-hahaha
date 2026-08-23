"""llm/windows.py — LLM-guided smart clip window selection.

Tier 1: transcript available -> LLM reads timestamped segments and picks the
        most engaging windows (hook / transformation / reveal).
Tier 2: no transcript (music/ASMR) -> audio-energy candidate windows are
        ranked and the LLM picks a diverse narrative spread.
Tier 3: any failure -> caller falls back to the existing heuristic windows.

The returned windows are always validated (in-range, long enough,
non-overlapping, capped); invalid LLM output never reaches the clip engine.
"""

import json
import re

from llm.client import llm_complete


def validate_windows(windows, duration, clip_len, min_clip, max_clips):
    """Sanitize raw (start, end) pairs into safe, non-overlapping windows.

    Pure function. Drops malformed/out-of-range/too-short entries, resolves
    overlaps by keeping the earlier window, and caps the count.
    """
    clean = []
    for w in windows or []:
        try:
            s, e = float(w[0]), float(w[1])
        except (TypeError, ValueError, IndexError):
            continue
        s = max(0.0, s)
        e = min(float(duration), e)
        if e - s < min_clip * 0.8:  # tolerate small LLM rounding
            continue
        clean.append((round(s, 2), round(e, 2)))

    clean.sort()
    result = []
    for s, e in clean:
        if result and s < result[-1][1]:  # overlap with previous -> clip to it
            s = result[-1][1]
            if e - s < min_clip * 0.8:
                continue
        result.append((s, round(e, 2)))
        if len(result) >= max_clips:
            break
    return result


def _prompt(transcript_block, duration, clip_len, max_clips):
    return (
        "You are a short-form video editor. From this video, pick the "
        f"{max_clips} most engaging moments for TikTok/Reels clips of ~{clip_len} "
        f"s each. Video duration: {duration:.0f}s.\n"
        "Rules: windows must not overlap, each must be 30-50s long, stay within "
        "the video, and together tell a story (hook -> action -> payoff).\n"
        "Respond with ONLY a JSON array like "
        '[{"start": 65, "end": 110}, ...] — no other text.\n\n'
        f"{transcript_block}"
    )


def _parse_json_windows(text):
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and "start" in item and "end" in item:
            out.append((item["start"], item["end"]))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((item[0], item[1]))
    return out or None


def compute_windows(duration, cfg, transcript=None, audio_candidates=None):
    """Return smart windows, or None to signal 'use the heuristic fallback'.

    Args:
        duration: source duration seconds.
        cfg: clipper config (clip_length_s, min_clip_s, max_clips_per_video).
        transcript: list of segment dicts with 'start' and 'text'/'caption'.
        audio_candidates: list[(start, end)] energy-ranked windows from
            utils.audio_energy (optional, used when there's no transcript).

    Returns:
        list[(start, end)] validated windows, or None when LLM unavailable.
    """
    clip_len = cfg.get("clip_length_s", 45)
    min_clip = cfg.get("min_clip_s", 10)
    max_clips = cfg.get("max_clips_per_video", 3)

    if transcript:
        seg_lines = []
        for seg in transcript[:80]:
            s = seg.get("start")
            txt = (seg.get("text") or seg.get("caption") or "").strip()
            if s is not None and txt:
                seg_lines.append(f"[{float(s):.0f}s] {txt[:90]}")
        if seg_lines:
            block = "Transcript (timestamped):\n" + "\n".join(seg_lines)
            raw = llm_complete(_prompt(block, duration, clip_len, max_clips), max_tokens=300)
            windows = _parse_json_windows(raw or "")
            if windows:
                validated = validate_windows(windows, duration, clip_len, min_clip, max_clips)
                if validated:
                    return validated

    if audio_candidates:
        ranked = "\n".join(
            f"- {s:.0f}s to {e:.0f}s" for s, e in audio_candidates[:6]
        )
        block = (
            "Candidate windows ranked by audio energy (loudest = most action):\n"
            + ranked
        )
        raw = llm_complete(_prompt(block, duration, clip_len, max_clips), max_tokens=300)
        windows = _parse_json_windows(raw or "")
        if windows:
            validated = validate_windows(windows, duration, clip_len, min_clip, max_clips)
            if validated:
                return validated
        # LLM unavailable -> energy peaks themselves are already a good pick
        validated = validate_windows(
            audio_candidates, duration, clip_len, min_clip, max_clips
        )
        if validated:
            return validated

    return None
