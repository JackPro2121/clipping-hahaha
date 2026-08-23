"""audio_energy.py — per-second loudness profile + peak window detection.

Used for smart clip selection on videos WITHOUT a transcript (music/ASMR
content): loud moments usually correlate with action, impacts, and reveals.
Pure stdlib (wave/struct/math) + ffmpeg for demuxing — no new dependencies.
"""

import subprocess
from pathlib import Path


def extract_loudness_profile(video_path, sample_rate=8000):
    """Return per-second RMS loudness list (linear scale) for the first audio stream.

    Returns [] when the video has no audio stream or ffmpeg fails.
    """
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", str(video_path),
        "-map", "a:0",
        "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "pipe:1",
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=180).stdout
    except Exception:
        return []
    if not raw:
        return []

    bytes_per_sec = sample_rate * 2  # s16le mono
    profile = []
    for sec_start in range(0, len(raw) - bytes_per_sec + 1, bytes_per_sec):
        chunk = raw[sec_start:sec_start + bytes_per_sec]
        # RMS over 16-bit little-endian samples
        acc = 0
        n = len(chunk) // 2
        for i in range(0, len(chunk), 2):
            sample = chunk[i] | (chunk[i + 1] << 8)
            if sample >= 32768:
                sample -= 65536
            acc += sample * sample
        rms = (acc / max(n, 1)) ** 0.5 / 32768.0
        profile.append(rms)
    return profile


def find_energy_peaks(profile, duration, clip_len, max_clips, min_clip):
    """Pick the highest-energy non-overlapping windows of `clip_len` seconds.

    Args:
        profile: per-second loudness values from extract_loudness_profile().
        duration: video duration in seconds (windows clamped to it).
        clip_len: desired window length in seconds.
        max_clips: maximum windows to return.
        min_clip: minimum acceptable window length.

    Returns:
        list[(start, end)] sorted by start, or [] if profile too short.
    """
    if not profile or duration < min_clip:
        return []

    win_secs = min(clip_len, duration)
    # Score every candidate window start (1s granularity)
    candidates = []
    limit = max(0, int(duration - win_secs))
    for start in range(0, limit + 1):
        end = min(start + int(win_secs), len(profile))
        seg = profile[start:end]
        if seg:
            candidates.append((sum(seg) / len(seg), start))
    if not candidates:
        return []

    candidates.sort(reverse=True)
    chosen = []
    for score, start in candidates:
        if len(chosen) >= max_clips:
            break
        end = start + win_secs
        # reject overlaps with already-chosen windows
        if any(start < c_end and end > c_start for c_start, c_end in chosen):
            continue
        chosen.append((float(start), round(float(min(end, duration)), 2)))

    windows = [(round(s, 2), e) for s, e in chosen]
    windows.sort()
    # enforce minimum length
    return [(s, e) for s, e in windows if e - s >= min_clip]
