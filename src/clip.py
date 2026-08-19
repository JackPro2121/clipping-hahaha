import json
import re
import subprocess
from pathlib import Path


def _run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def probe_duration(path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def detect_scenes(path, threshold):
    cmd = [
        "ffmpeg", "-i", str(path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    pts = []
    for line in res.stderr.splitlines():
        if "showinfo" not in line or "pts_time:" not in line:
            continue
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            pts.append(float(m.group(1)))
    return sorted(set(pts))


def _aspect_filter(cfg):
    if cfg["aspect"] == "vertical":
        return (
            f"crop=trunc(ih*9/16/2)*2:ih,"
            f"scale={cfg['width']}:{cfg['height']},setsar=1"
        )
    return f"scale={cfg['width']}:{cfg['height']},setsar=1"


def build_clips(path, out_dir, cfg):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(path)
    cuts = [0.0] + detect_scenes(path, cfg["scene_threshold"]) + [duration]
    segments = []
    for i in range(len(cuts) - 1):
        start, end = cuts[i], cuts[i + 1]
        seg_dur = end - start
        if cfg["min_segment_s"] <= seg_dur <= cfg["max_segment_s"]:
            segments.append((start, seg_dur))
    segments.sort(key=lambda s: s[1], reverse=True)
    segments = segments[: cfg["max_clips_per_video"]]

    clips = []
    for idx, (start, seg_dur) in enumerate(segments, 1):
        out = out_dir / f"clip_{idx:02d}.mp4"
        vf = _aspect_filter(cfg)
        cmd = [
            "ffmpeg",
            "-ss", f"{start:.3f}",
            "-i", str(path),
            "-t", f"{seg_dur:.3f}",
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y", str(out),
        ]
        _run(cmd)
        clips.append(out)
    return clips