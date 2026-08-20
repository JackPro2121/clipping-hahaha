import json
import re
import subprocess
from pathlib import Path


def _run(cmd, cwd=None):
    subprocess.run(cmd, check=True, capture_output=True, cwd=cwd)


def probe(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=index,codec_type,width,height:format=duration",
        "-of", "json",
        str(path),
    ]
    out = json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)
    stream = out["streams"][0]
    has_audio = any(s.get("codec_type") == "audio" for s in out["streams"])
    return stream["width"], stream["height"], float(out["format"]["duration"]), has_audio


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


def _center_crop(cfg, src_w, src_h):
    if cfg["aspect"] == "vertical":
        w = round(src_h * 9 / 16)
        if w % 2:
            w -= 1
        if w > src_w:
            w = src_w
            h = round(w * 16 / 9)
            if h % 2:
                h -= 1
            x, y = 0, (src_h - h) // 2
        else:
            h = src_h
            x, y = (src_w - w) // 2, 0
    else:
        w, h = src_w, src_h
        x, y = 0, 0
    return w, h, x, y


def _build_filter(cfg, src_w, src_h, duration, subtitle_name=None):
    parts = []
    w, h, x, y = _center_crop(cfg, src_w, src_h)
    motion = cfg.get("motion", {})
    pan_rl = bool(motion.get("enabled") and motion.get("type") == "pan_rl")
    if pan_rl and duration > 0 and src_w - w > 20:
        parts.append(
            f"crop={w}:{h}:x='trunc((iw-{w})*(1-t/{duration:.3f}))*2':y={y}"
        )
    else:
        parts.append(f"crop={w}:{h}:{x}:{y}")
        if motion.get("enabled") and duration > 0 and motion.get("type") != "pan_rl":
            zw = round(w / motion.get("zoom_factor", 1.1) / 2) * 2
            zh = round(h / motion.get("zoom_factor", 1.1) / 2) * 2
            zw = min(zw, w)
            zh = min(zh, h)
            parts.append(
                f"crop={zw}:{zh}:x='trunc((iw-{zw})*t/{duration:.3f}/2)*2':"
                f"y='trunc((ih-{zh})*t/{duration:.3f}/2)*2'"
            )
    parts.append(f"scale={cfg['width']}:{cfg['height']},setsar=1")
    effects = cfg.get("effects", {})
    if effects.get("enabled") and effects.get("subtle_filter"):
        parts.append(effects["subtle_filter"])
    if subtitle_name:
        parts.append(f"subtitles={subtitle_name}")
    return ",".join(parts)


def _ass_ts(seconds):
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_subtitles(segments, start, duration, out_path):
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default, DejaVu Sans, 66, &H00FFFFFF, &H000000FF, &H00000000, "
        "&H80000000, -1, 0, 0, 0, 100, 100, 0, 0, 1, 3, 0, 2, 60, 60, 140, 1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = [header]
    end = start + duration
    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_dur = seg.get("duration", 2)
        text = (seg.get("text") or seg.get("caption") or "").strip()
        if not text:
            continue
        seg_end = seg_start + seg_dur
        if seg_end <= start or seg_start >= end:
            continue
        ls = max(seg_start, start) - start
        le = min(seg_end, end) - start
        if le - ls < 0.3:
            continue
        text = text.replace("\n", " ").replace("\r", " ")
        lines.append(
            f"Dialogue: 0,{_ass_ts(ls)},{_ass_ts(le)},Default,,0,0,0,,{text}"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _select_segments(cuts, cfg):
    interval = cfg.get("cut_interval_s")
    min_clip = cfg.get("min_clip_s", 2.5)
    segments = []
    for i in range(len(cuts) - 1):
        start, end = cuts[i], cuts[i + 1]
        seg_dur = end - start
        if interval:
            t = start
            while t < end - 0.2:
                d = min(interval, end - t)
                if d >= min_clip:
                    segments.append((t, d))
                t += d
        elif cfg["min_segment_s"] <= seg_dur <= cfg["max_segment_s"]:
            segments.append((start, seg_dur))
    segments.sort(key=lambda s: s[1], reverse=True)
    return segments[: cfg["max_clips_per_video"]]


def _fallback_segments(duration, cfg):
    interval = cfg.get("cut_interval_s") or cfg["min_segment_s"]
    min_clip = cfg.get("min_clip_s", 2.5)
    chunks = []
    t = 0.0
    while t < duration - 0.2:
        d = min(interval, duration - t)
        if d >= min_clip:
            chunks.append((t, d))
        t += d
    return chunks[: cfg["max_clips_per_video"]]


def _make_bgm(path, duration):
    dur = duration - 1.0
    if dur < 1.0:
        dur = 1.0
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=164.81:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
        "-filter_complex",
        "[0:a][1:a][2:a]amix=inputs=3:normalize=0,volume=0.5,"
        f"tremolo=f=0.15:d=0.5,lowpass=f=1400,"
        f"aformat=channel_layouts=stereo,"
        f"afade=t=in:d=1.5,afade=t=out:st={dur - 1.0:.2f}:d=1.0",
        "-t", f"{duration:.3f}",
        str(path),
    ]
    _run(cmd)


def _mix_cmd(cfg, has_audio):
    bgm_vol = cfg.get("effects", {}).get("bgm_volume", 0.35)
    afmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    if has_audio:
        fc = (
            f"[0:a]{afmt},volume=1.0[orig];"
            f"[1:a]{afmt},volume={bgm_vol}[bg];"
            f"[orig][bg]amix=inputs=2:duration=first:normalize=0[aout]"
        )
    else:
        fc = f"[1:a]{afmt},volume=1.0[aout]"
    return fc


def build_clips(path, out_dir, cfg, transcript=None, captions_enabled=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src_w, src_h, duration, has_audio = probe(path)
    cuts = [0.0] + detect_scenes(path, cfg["scene_threshold"]) + [duration]
    segments = _select_segments(cuts, cfg)
    if not segments:
        segments = _fallback_segments(duration, cfg)

    clips = []
    for idx, (start, seg_dur) in enumerate(segments, 1):
        out = out_dir / f"clip_{idx:02d}.mp4"
        sub_name = None
        if captions_enabled and transcript:
            sub_path = out_dir / f"clip_{idx:02d}.ass"
            build_subtitles(transcript, start, seg_dur, sub_path)
            sub_name = sub_path.name
        vf = _build_filter(cfg, src_w, src_h, seg_dur, sub_name)

        use_bgm = cfg.get("effects", {}).get("bgm", True)
        bgm_path = None
        if use_bgm:
            bgm_path = out_dir / f"clip_{idx:02d}_bgm.wav"
            _make_bgm(bgm_path, seg_dur)

        cmd = [
            "ffmpeg",
            "-ss", f"{start:.3f}",
            "-i", str(path),
        ]
        if bgm_path is not None:
            cmd += ["-i", str(bgm_path)]
        cmd += [
            "-t", f"{seg_dur:.3f}",
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
        ]
        if bgm_path is not None:
            cmd += [
                "-filter_complex", _mix_cmd(cfg, has_audio),
                "-map", "0:v",
                "-map", "[aout]",
                "-c:a", "aac",
                "-b:a", "128k",
            ]
        else:
            cmd += ["-map", "0:v", "-map", "0:a?"]
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "128k"]
        cmd += [
            "-movflags", "+faststart",
            "-y", str(out),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, cwd=out_dir)
        except subprocess.CalledProcessError:
            if sub_name:
                print(f"Subtitle burn failed for {out.name}, retrying without captions")
                vf = _build_filter(cfg, src_w, src_h, seg_dur, None)
                cmd[cmd.index("-vf") + 1] = vf
                subprocess.run(cmd, check=True, capture_output=True, cwd=out_dir)
            else:
                raise
        clips.append(out)
    return clips