import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.errors import ClipError  # noqa: E402
from pipeline.brand import get_brand_filter, get_logo_path, get_logo_overlay  # noqa: E402

MOTIONS = ["pan_rl", "pan_lr", "zoom_in", "slow_zoom"]


def probe(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=index,codec_type,width,height:format=duration",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise ClipError(
            f"ffprobe failed on {path}:\n{result.stderr[:400]}"
        )
    out = json.loads(result.stdout)
    if not out.get("streams"):
        raise ClipError(f"ffprobe returned no streams for {path}")
    stream = out["streams"][0]
    has_audio = any(s.get("codec_type") == "audio" for s in out["streams"])
    return stream["width"], stream["height"], float(out["format"]["duration"]), has_audio



def _center_crop(cfg, src_w, src_h):
    if cfg["aspect"] == "vertical":
        target_w = round(src_h * 9 / 16)
        if target_w % 2:
            target_w -= 1
        if target_w > src_w:
            # Source is portrait/vertical -> apply 6% overscan margin to eliminate corner logos/UIDs
            w = round(src_w * 0.94)
            if w % 2:
                w -= 1
            h = round(w * 16 / 9)
            if h % 2:
                h -= 1
            x = (src_w - w) // 2
            y = (src_h - h) // 2
        else:
            # Source is landscape/horizontal -> center 9:16 crop + subtle top/bottom safe margin
            h = round(src_h * 0.97)
            if h % 2:
                h -= 1
            w = round(h * 9 / 16)
            if w % 2:
                w -= 1
            x = (src_w - w) // 2
            y = (src_h - h) // 2
    else:
        w, h = src_w, src_h
        x, y = 0, 0
    return w, h, x, y


def _filter_path(p):
    return str(p).replace("\\", "/").replace(":", "\\:")


def _chunk_vf(cfg, src_w, src_h, dur, motion):
    w, h, x, y = _center_crop(cfg, src_w, src_h)
    if motion == "pan_rl" and src_w - w > 20:
        vf = f"crop={w}:{h}:x='trunc((iw-{w})*(1-t/{dur:.3f}))*2':y={y}"
    elif motion == "pan_lr" and src_w - w > 20:
        vf = f"crop={w}:{h}:x='trunc((iw-{w})*t/{dur:.3f})*2':y={y}"
    else:
        vf = f"crop={w}:{h}:{x}:{y}"
        if motion in ("zoom_in", "slow_zoom"):
            factor = cfg["motion"].get("zoom_factor", 1.15) if motion == "zoom_in" else 1.08
            zw = round(w / factor / 2) * 2
            zh = round(h / factor / 2) * 2
            zw = min(zw, w)
            zh = min(zh, h)
            vf += (
                f",crop={zw}:{zh}:x='trunc((iw-{zw})*t/{dur:.3f}/2)*2':"
                f"y='trunc((ih-{zh})*t/{dur:.3f}/2)*2',scale={w}:{h}"
            )
    return vf


def _ass_ts(seconds):
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _wrap(text, width=18):
    words = text.split()
    lines = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if len(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return "\\N".join(lines[:3])


def build_subtitles(segments, start, duration, out_path, timeline=None):
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
        "Style: Default, Arial Black, 76, &H0000FFFF, &H00FFFFFF, &H00000000, "
        "&H80000000, -1, 0, 0, 0, 100, 100, 0, 0, 1, 5, 2, 2, 70, 70, 260, 1\n"
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
        if timeline:
            ls = le = None
            for cs, cd, os_ in timeline:
                ov = max(seg_start, cs)
                ov_end = min(seg_end, cs + cd)
                if ov_end > ov + 0.05:
                    l1 = os_ + (ov - cs)
                    l2 = os_ + (ov_end - cs)
                    ls = l1 if ls is None else min(ls, l1)
                    le = l2 if le is None else max(le, l2)
            if ls is None:
                continue
        else:
            ls = max(seg_start, start) - start
            le = min(seg_end, end) - start
        if le - ls < 0.3:
            continue
        text = _wrap(text.replace("\n", " ").replace("\r", " "))
        lines.append(
            f"Dialogue: 0,{_ass_ts(ls)},{_ass_ts(le)},Default,,0,0,0,,{text}"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _select_windows(duration, cfg):
    clip_len = cfg.get("clip_length_s", 45)
    max_clips = cfg.get("max_clips_per_video", 3)
    windows = []
    t = 0.0
    while t < duration - 2 and len(windows) < max_clips:
        d = min(clip_len, duration - t)
        if d >= cfg.get("min_clip_s", 10):
            windows.append((t, d))
        t += clip_len
    return windows


def _chunks(start, duration, chunk_s):
    out = []
    t = 0.0
    while t < duration - 0.05:
        d = min(chunk_s, duration - t)
        if d >= 1.0:
            out.append((start + t, d))
        t += d
    return out


def _make_bgm(path, duration):
    """Synthesize a calming, slow copyright-free ambient soundscape."""
    dur = duration - 1.0
    if dur < 1.0:
        dur = 1.0
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=130.81:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=164.81:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=196.00:sample_rate=44100",
        "-filter_complex",
        "[0:a][1:a][2:a]amix=inputs=3:normalize=0,volume=0.35,"
        f"tremolo=f=0.08:d=0.35,lowpass=f=950,"
        f"aformat=channel_layouts=stereo,"
        f"afade=t=in:d=2.0,afade=t=out:st={dur - 1.0:.2f}:d=1.5",
        "-t", f"{duration:.3f}",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _clip_cmd(cfg, path, out_dir, idx, start, duration, transcript, has_audio):
    src_w, src_h = cfg["_src"]
    fps = cfg.get("fps", 25)
    chunk_s = cfg.get("transition_every_s", 4)
    xd = cfg.get("transition_duration_s", 0.15)
    chunks = _chunks(start, duration, chunk_s)

    parts = []
    for i, (cs, cd) in enumerate(chunks):
        vf = _chunk_vf(cfg, src_w, src_h, cd, MOTIONS[i % len(MOTIONS)])
        vf = f"setpts=PTS-STARTPTS,{vf},setsar=1"
        if i > 0:
            vf += f",fade=t=in:st=0:d={xd}"
        if i < len(chunks) - 1:
            vf += f",fade=t=out:st={max(0.0, cd - xd):.3f}:d={xd}"
        vf += f",fps={fps}"
        parts.append(
            f"[0:v]trim=start={cs:.3f}:end={cs + cd:.3f},{vf}[c{i}]"
        )
        if has_audio:
            parts.append(
                f"[0:a]atrim=start={cs:.3f}:end={cs + cd:.3f},"
                f"asetpts=PTS-STARTPTS[ac{i}]"
            )

    n = len(chunks)
    v_in = "".join(f"[c{i}]" for i in range(n))
    parts.append(f"{v_in}concat=n={n}:v=1:a=0[vcat]")
    if has_audio:
        a_in = "".join(f"[ac{i}]" for i in range(n))
        parts.append(f"{a_in}concat=n={n}:v=0:a=1[acat]")

    sub_name = None
    if transcript:
        shifted = []
        for seg in transcript:
            s = seg.get("start", 0) - start
            d = seg.get("duration", 2)
            shifted.append({"start": s, "duration": d, "text": seg.get("text")})
        timeline = []
        out_t = 0.0
        for cs, cd in chunks:
            timeline.append((cs - start, cd, out_t))
            out_t += cd
        sub_path = out_dir / f"clip_{idx:02d}.ass"
        build_subtitles(shifted, 0.0, duration, sub_path, timeline=timeline)
        sub_name = sub_path.name

    logo_path = get_logo_path(cfg)
    scale_out = "[vscaled]" if logo_path else "[vout]"

    scale_eff = f"settb=AVTB,setpts=PTS-STARTPTS,"
    scale_eff += f"scale={cfg['width']}:{cfg['height']},setsar=1"
    effects = cfg.get("effects", {})
    if effects.get("enabled") and effects.get("subtle_filter"):
        scale_eff += "," + effects["subtle_filter"]
    if not logo_path:
        brand_vf = get_brand_filter(cfg)
        if brand_vf:
            scale_eff += "," + brand_vf
    if sub_name:
        scale_eff += f",subtitles=filename='{_filter_path(out_dir / sub_name)}'"
    parts.append(f"[vcat]{scale_eff}{scale_out}")

    use_bgm = effects.get("bgm", True)
    bgm_path = None
    if use_bgm:
        bgm_path = out_dir / f"clip_{idx:02d}_bgm.wav"
        _make_bgm(bgm_path, duration)

    inputs = ["-i", str(path)]
    current_input_idx = 1

    if bgm_path is not None:
        inputs += ["-i", str(bgm_path)]
        bgm_input_idx = current_input_idx
        current_input_idx += 1
    else:
        bgm_input_idx = None

    if logo_path is not None:
        inputs += ["-i", str(logo_path)]
        logo_input_idx = current_input_idx
        current_input_idx += 1
        logo_parts, _ = get_logo_overlay(
            cfg, logo_input_idx, base_stream="vscaled", out_stream="vout"
        )
        parts.extend(logo_parts)

    afmt = "aformat=sample_rates=44100:channel_layouts=stereo"
    # Subtle acoustic variation (bypasses direct match fingerprint while remaining natural & clear)
    audio_enhancer = (
        "equalizer=f=280:t=q:w=1.2:g=1.0,"
        "equalizer=f=3200:t=q:w=1.0:g=-0.5,"
        "asetrate=44100*1.015,aresample=44100,atempo=1/1.015"
    )
    if has_audio:
        aacc = "[acat]"
        if bgm_input_idx is not None:
            bgm_vol = effects.get("bgm_volume", 0.18)
            parts.append(
                f"{aacc}{afmt},{audio_enhancer},volume=1.0[orig];"
                f"[{bgm_input_idx}:a]{afmt},volume={bgm_vol}[bg];"
                f"[orig][bg]amix=inputs=2:duration=first:normalize=0[aout]"
            )
        else:
            parts.append(f"{aacc}{afmt},{audio_enhancer}[aout]")
    else:
        if bgm_input_idx is not None:
            parts.append(f"[{bgm_input_idx}:a]{afmt},volume=1.0[aout]")
        else:
            parts.append(f"anullsrc=channel_layout=stereo[aout]")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-force_key_frames", "expr:gte(t,n_forced*1)",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_dir / f"clip_{idx:02d}.mp4"),
    ]
    return cmd


def build_clips(path, out_dir, cfg, transcript=None, captions_enabled=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src_w, src_h, duration, has_audio = probe(path)
    cfg = {**cfg, "_src": (src_w, src_h)}
    windows = _select_windows(duration, cfg)
    if not windows:
        windows = [(0.0, duration)]

    clips = []
    for idx, (start, seg_dur) in enumerate(windows, 1):
        out = out_dir / f"clip_{idx:02d}.mp4"
        cmd = _clip_cmd(
            cfg,
            path,
            out_dir,
            idx,
            start,
            seg_dur,
            transcript if captions_enabled else None,
            has_audio,
        )
        try:
            subprocess.run(cmd, check=True, capture_output=True, cwd=out_dir)
        except subprocess.CalledProcessError:
            print(f"Clip {idx} failed, retrying without subtitles/bgm")
            nofrill = _clip_cmd(
                {**cfg, "effects": {"enabled": False, "bgm": False}},
                path,
                out_dir,
                idx,
                start,
                seg_dur,
                None,
                has_audio,
            )
            subprocess.run(nofrill, check=True, capture_output=True, cwd=out_dir)
        clips.append(out)
    return clips