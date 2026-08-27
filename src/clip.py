import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.errors import ClipError  # noqa: E402
from pipeline.brand import (  # noqa: E402
    get_brand_filter,
    get_logo_path,
    get_logo_overlay,
    get_hook_banner_filter,
)

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
    streams = out.get("streams") or []
    # Some containers (e.g. Douyin mp4s) list an audio or cover-image stream
    # first — always pick the first real video stream, not streams[0].
    vstream = _pick_video_stream(streams)
    if vstream is None:
        raise ClipError(f"no video stream found for {path}")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return vstream["width"], vstream["height"], float(out["format"]["duration"]), has_audio


def _pick_video_stream(streams):
    """Return the first stream that carries video dimensions, else None."""
    for s in streams:
        if s.get("codec_type") == "video" and s.get("width"):
            return s
    return None



def _center_crop(cfg, src_w, src_h):
    if cfg["aspect"] == "vertical":
        target_w = round(src_h * 9 / 16)
        if target_w % 2:
            target_w -= 1
        if target_w > src_w:
            # Source is portrait/vertical.
            # 10% overscan (was 6%) — eliminates corner logos, Bilibili watermarks, creator UIDs.
            # 5% cropped from each edge: top-right and top-left watermarks fall outside frame.
            w = round(src_w * 0.90)
            if w % 2:
                w -= 1
            h = round(w * 16 / 9)
            if h % 2:
                h -= 1
            x = (src_w - w) // 2
            y = (src_h - h) // 2
        else:
            # Source is landscape/horizontal → 9:16 vertical crop.
            # Bilibili & Douyin watermarks sit at top-right corner (y: 0-6% of src_h).
            # Crop height with 6% margin and shift window DOWNWARD so the top watermark zone is excluded.
            h = round(src_h * 0.94)
            if h % 2:
                h -= 1
            w = round(h * 9 / 16)
            if w % 2:
                w -= 1
            x = (src_w - w) // 2
            # Drop top watermark zone (y starts below top 6% margin)
            top_margin = round(src_h * 0.06)
            y = min(src_h - h, max(0, (src_h - h) // 2 + top_margin))
    else:
        w, h = src_w, src_h
        x, y = 0, 0
    return w, h, x, y


def _filter_path(p):
    return str(p).replace("\\", "/").replace(":", "\\:")


def _chunk_vf(cfg, src_w, src_h, dur, motion):
    w, h, x, y = _center_crop(cfg, src_w, src_h)
    center_x = (src_w - w) // 2
    # Keep pan within center +/- 20% margin to strictly exclude corner Bilibili/Douyin watermarks
    max_pan_offset = round((src_w - w) * 0.20)
    x_min = max(0, center_x - max_pan_offset)
    x_max = min(src_w - w, center_x + max_pan_offset)

    if motion == "pan_rl" and src_w - w > 40 and x_max > x_min:
        vf = f"crop={w}:{h}:x='trunc({x_max}-({x_max}-{x_min})*t/{dur:.3f})':y={y}"
    elif motion == "pan_lr" and src_w - w > 40 and x_max > x_min:
        vf = f"crop={w}:{h}:x='trunc({x_min}+({x_max}-{x_min})*t/{dur:.3f})':y={y}"
    else:
        vf = f"crop={w}:{h}:{x}:{y}"
        if motion in ("zoom_in", "slow_zoom"):
            factor = cfg["motion"].get("zoom_factor", 1.15) if motion == "zoom_in" else 1.08
            zw = round(w / factor / 2) * 2
            zh = round(h / factor / 2) * 2
            zw = min(zw, w)
            zh = min(zh, h)
            vf += (
                f",crop={zw}:{zh}:x='trunc(({w}-{zw})*t/{dur:.3f}/2)*2':"
                f"y='trunc(({h}-{zh})*t/{dur:.3f}/2)*2',scale={w}:{h}:flags=lanczos"
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
    min_clip = cfg.get("min_clip_s", 10)
    narrative = cfg.get("narrative_arc", True)

    if duration < min_clip:
        return []

    # If single clip configured or short video (< 1.8x clip_len) -> 1 single complete highlight
    if max_clips <= 1 or duration < clip_len * 1.8:
        d = min(clip_len, duration)
        return [(0.0, round(d, 2))] if d >= min_clip else []

    # Adaptive duration scaling:
    # 70s - 180s (1.2m - 3m) -> 2 clips (Start Hook + Climax/Finish)
    # >= 180s (3m - 10m) -> 3 clips (Start Hook + Middle Craft + Grand Finish)
    effective_max = max_clips
    if duration < 180.0 and effective_max > 2:
        effective_max = 2

    if narrative:
        if effective_max == 2 and duration >= clip_len * 1.6:
            w1_dur = min(clip_len, duration)
            w2_start = max(w1_dur, round(duration - clip_len - 1.0, 2))
            w2_dur = min(clip_len, round(duration - w2_start, 2))
            windows = [(0.0, round(w1_dur, 2))]
            if w2_dur >= min_clip and w2_start >= w1_dur:
                windows.append((round(w2_start, 2), round(w2_dur, 2)))
            return windows

        if effective_max >= 3 and duration >= clip_len * 2.5:
            # 3-clip distributed narrative arc:
            # Part 1: Initial Hook / Project Start (0.0 to clip_len)
            # Part 2: Middle Transformation / Craft Action (centered around mid)
            # Part 3: Grand Climax / Final Reveal (ending at duration - 1.0)
            w1_dur = min(clip_len, duration)
            mid_target = duration / 2.0
            w2_start = max(w1_dur + 1.0, round(mid_target - clip_len / 2.0, 2))
            w2_dur = min(clip_len, round(duration - w2_start, 2))

            w3_start = max(w2_start + w2_dur + 1.0, round(duration - clip_len - 1.0, 2))
            w3_dur = min(clip_len, round(duration - w3_start, 2))

            windows = [(0.0, round(w1_dur, 2))]
            if w2_dur >= min_clip and w2_start > w1_dur:
                windows.append((round(w2_start, 2), round(w2_dur, 2)))
            if w3_dur >= min_clip and w3_start > (w2_start + w2_dur if len(windows) > 1 else w1_dur):
                windows.append((round(w3_start, 2), round(w3_dur, 2)))
            return windows

    # Standard sequential slicing for fallback or narrative=False
    windows = []
    t = 0.0
    while t < duration - 2 and len(windows) < effective_max:
        d = min(clip_len, duration - t)
        if d >= min_clip:
            windows.append((round(t, 2), round(d, 2)))
        t += clip_len
    return windows


def _chunks(start, duration, chunk_s, variable_pacing=False):
    out = []
    t = 0.0
    pacing_pattern = [0.85, 1.15, 0.95, 1.05]
    step_idx = 0
    while t < duration - 0.05:
        target_s = (
            chunk_s * pacing_pattern[step_idx % len(pacing_pattern)]
            if variable_pacing
            else chunk_s
        )
        d = min(target_s, duration - t)
        if d >= 1.0:
            out.append((round(start + t, 3), round(d, 3)))
        t += d
        step_idx += 1
    return out


def _audio_pitch_filter(shift_pct):
    """Build an ffmpeg pitch-shift filter chain preserving duration.

    asetrate raises pitch+speed by the factor, aresample restores the sample
    rate, and atempo slows playback back so total duration is unchanged.
    Returns "" when shift_pct is 0 (no shifting desired).
    """
    try:
        pct = float(shift_pct)
    except (TypeError, ValueError):
        return ""
    if pct <= 0:
        return ""
    factor = 1.0 + pct / 100.0
    return (
        f"asetrate=44100*{factor:.4f},aresample=44100,"
        f"atempo={1.0 / factor:.6f}"
    )


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
        f"tremolo=f=0.5:d=0.35,lowpass=f=950,"
        f"aformat=channel_layouts=stereo,"
        f"afade=t=in:d=2.0,afade=t=out:st={dur - 1.0:.2f}:d=1.5",
        "-t", f"{duration:.3f}",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _clip_cmd(cfg, path, out_dir, idx, start, duration, transcript, has_audio, hook_text=None):
    src_w, src_h = cfg["_src"]
    fps = cfg.get("fps", 30)
    chunk_s = cfg.get("transition_every_s", 4)
    xd = cfg.get("transition_duration_s", 0.15)
    chunks = _chunks(
        start, duration, chunk_s, variable_pacing=cfg.get("variable_pacing", True)
    )

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
    scale_eff += f"scale={cfg['width']}:{cfg['height']}:flags=lanczos,setsar=1"
    effects = cfg.get("effects", {})
    if effects.get("enabled") and effects.get("subtle_filter"):
        scale_eff += "," + effects["subtle_filter"]
    if not logo_path:
        brand_vf = get_brand_filter(cfg)
        if brand_vf:
            scale_eff += "," + brand_vf
    # Curiosity Hook banner overlay (0-3.8s) for Tier-1 engagement
    curiosity_hook = hook_text or cfg.get("hook_text")
    if curiosity_hook:
        hook_vf = get_hook_banner_filter(cfg, curiosity_hook, duration_s=3.8)
        if hook_vf:
            scale_eff += "," + hook_vf
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
    # Studio-grade ASMR compressor: boosts subtle carving/slicing acoustics, tames harsh peaks.
    # Micro pitch-shift (default +4%) breaks Meta Rights Manager / Content ID audio
    # fingerprints — licensed music in source audio was getting videos muted in
    # certain countries. 1.2% was not enough; >=3% reliably defeats matching and is
    # imperceptible for speech/ASMR content. Duration is preserved via atempo.
    shift_pct = float(effects.get("audio_pitch_shift_pct", 4.0))
    audio_enhancer = (
        "highpass=f=55,"
        "compand=attacks=0.05:decays=0.2:points=-80/-80|-45/-30|-20/-12|0/-3:gain=3,"
        "equalizer=f=220:t=q:w=1.2:g=1.2,"
        "equalizer=f=4500:t=q:w=1.0:g=1.5"
    )
    pitch = _audio_pitch_filter(shift_pct)
    if pitch:
        audio_enhancer += "," + pitch
    if has_audio:
        aacc = "[acat]"
        # EBU R128 loudness normalization — TikTok/Instagram/Facebook all
        # normalize to ~-14 LUFS; delivering pre-normalized audio prevents
        # the platforms' re-normalization from crushing dynamics or leaving
        # clips too quiet relative to native content.
        loudnorm = ""
        if effects.get("loudnorm", True):
            loudnorm = ",loudnorm=I=-14:TP=-1.5:LRA=11"
        if bgm_input_idx is not None:
            bgm_vol = effects.get("bgm_volume", 0.18)
            # amix(normalize=0) can sum above full-scale; loudnorm's TP=-1.5
            # ceiling catches that, so no manual make-up gain is needed.
            parts.append(
                f"{aacc}{afmt},{audio_enhancer},volume=1.0[orig];"
                f"[{bgm_input_idx}:a]{afmt},volume={bgm_vol}[bg];"
                f"[orig][bg]amix=inputs=2:duration=first:normalize=0{loudnorm}[aout]"
            )
        else:
            parts.append(f"{aacc}{afmt},{audio_enhancer}{loudnorm}[aout]")
    else:
        if bgm_input_idx is not None:
            parts.append(f"[{bgm_input_idx}:a]{afmt},volume=1.0[aout]")
        else:
            parts.append(f"anullsrc=channel_layout=stereo[aout]")

    crf_val = str(cfg.get("crf", 18))
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", crf_val,
        "-maxrate", "8500k",
        "-bufsize", "17000k",
        "-pix_fmt", "yuv420p",
        "-force_key_frames", "expr:gte(t,n_forced*1)",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_dir / f"clip_{idx:02d}.mp4"),
    ]
    return cmd


def build_clips(path, out_dir, cfg, transcript=None, captions_enabled=False, windows=None, hook_text=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src_w, src_h, duration, has_audio = probe(path)
    cfg = {**cfg, "_src": (src_w, src_h)}
    windows = windows or _select_windows(duration, cfg)
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
            hook_text=hook_text,
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
                hook_text=None,
            )
            subprocess.run(nofrill, check=True, capture_output=True, cwd=out_dir)
        clips.append(out)
    return clips