import base64
import os
import subprocess
from pathlib import Path


def _download(cmd, out_dir):
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)


def download_video(url, out_dir, max_duration_s=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_cmd = [
        "yt-dlp",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-progress",
        "--extractor-args", "youtube:player_client=android",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    cookies_b64 = os.environ.get("YT_COOKIES")
    if cookies_b64:
        cookies_file = out_dir / "cookies.txt"
        cookies_file.write_bytes(base64.b64decode(cookies_b64))
        base_cmd += ["--cookies", str(cookies_file)]
    if max_duration_s:
        base_cmd += [
            "--download-sections", f"*0-{max_duration_s}",
            "--force-keyframes-at-cuts",
        ]

    attempts = []
    proxy = os.environ.get("WEBSHARE_PROXY")
    if proxy:
        attempts.append(("proxy", base_cmd + ["--proxy", proxy] + [url]))
    attempts.append(("direct", base_cmd + [url]))

    last_err = None
    for name, cmd in attempts:
        try:
            _download(cmd, out_dir)
            candidates = [p for p in out_dir.iterdir() if p.is_file() and p.suffix != ".txt"]
            if not candidates:
                raise RuntimeError(f"Download produced no files for {url}")
            return max(candidates, key=lambda p: p.stat().st_size)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            stderr = getattr(exc, "stderr", None)
            if stderr:
                stderr = stderr.decode("utf-8", "replace")
            last_err = f"{name}: {stderr or exc}"
            print(f"Download via {name} failed: {str(exc)[:200]}")
    raise RuntimeError(f"yt-dlp failed for {url}: {last_err}")