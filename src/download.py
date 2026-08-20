import base64
import os
import re
import subprocess
import time
from pathlib import Path

STRATEGIES = [
    {"name": "embedded", "client": "web_embedded", "cookies": False},
    {"name": "cookies-default", "client": "default", "cookies": True},
    {"name": "cookies-safari", "client": "web_safari", "cookies": True},
]

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})")
_VIDEO_EXTS = (".mp4", ".webm", ".mkv")


def _video_id(url):
    m = _VIDEO_ID_RE.search(url)
    if not m:
        raise ValueError(f"Cannot extract video id from {url}")
    return m.group(1)


def _ytdlp(url, out_dir, client, cookies_file, max_duration_s):
    cmd = [
        "yt-dlp",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-progress",
        "--socket-timeout", "15",
        "--retries", "3",
        "--retry-sleep", "5",
        "--sleep-requests", "1.0",
        "--extractor-args", f"youtube:player_client={client}",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    cmd += ["--js-runtime", "node", "--remote-components", "ejs:github"]
    if cookies_file is not None:
        cmd += ["--cookies", str(cookies_file)]
    if max_duration_s:
        cmd += ["--download-sections", f"*0-{max_duration_s}"]
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)


def _locate_output(attempt_dir, video_id):
    expected = attempt_dir / f"{video_id}.mp4"
    if expected.exists():
        return expected
    candidates = [
        p
        for p in attempt_dir.iterdir()
        if p.suffix.lower() in _VIDEO_EXTS and ".f" not in p.stem
    ]
    if not candidates:
        raise RuntimeError(f"no video file found for {video_id}")
    return max(candidates, key=lambda p: p.stat().st_size)


def download_video(url, out_dir, max_duration_s=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video_id = _video_id(url)

    cookies_b64 = os.environ.get("YT_COOKIES")
    cookies_file = None
    if cookies_b64:
        cookies_file = out_dir / "cookies.txt"
        cookies_file.write_bytes(base64.b64decode(cookies_b64))

    last_err = None
    for idx, strat in enumerate(STRATEGIES):
        if strat["cookies"] and cookies_file is None:
            continue
        attempt_dir = out_dir / f"attempt-{idx}-{strat['name']}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        try:
            _ytdlp(
                url,
                attempt_dir,
                strat["client"],
                cookies_file if strat["cookies"] else None,
                max_duration_s,
            )
            result = _locate_output(attempt_dir, video_id)
            if result.stat().st_size < 100_000:
                raise RuntimeError(
                    f"suspiciously small file ({result.stat().st_size}B)"
                )
            print(
                f"Download OK via '{strat['name']}' -> "
                f"{result.name} ({result.stat().st_size // 1024 // 1024}MB)"
            )
            return result
        except (subprocess.CalledProcessError, RuntimeError, TimeoutError) as exc:
            stderr = getattr(exc, "stderr", None)
            if stderr:
                stderr = stderr.decode("utf-8", "replace")[:400]
            last_err = f"{strat['name']}: {stderr or exc}"
            print(f"Attempt '{strat['name']}' failed: {str(exc)[:160]}")
            for f in attempt_dir.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass
        time.sleep(5)

    raise RuntimeError(f"All download strategies failed for {video_id}: {last_err}")