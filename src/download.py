import base64
import os
import subprocess
import time
from pathlib import Path


def _download(cmd, out_dir):
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)


def download_video(url, out_dir, max_duration_s=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cookies_b64 = os.environ.get("YT_COOKIES")
    client = "web_embedded" if cookies_b64 else "android"
    base_cmd = [
        "yt-dlp",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-progress",
        "--socket-timeout", "15",
        "--retries", "5",
        "--retry-sleep", "5-10",
        "--sleep-requests", "1.0",
        "--extractor-args", f"youtube:player_client={client}",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    if cookies_b64:
        cookies_file = out_dir / "cookies.txt"
        cookies_file.write_bytes(base64.b64decode(cookies_b64))
        base_cmd += ["--cookies", str(cookies_file), "--js-runtime", "node", "--remote-components", "ejs:github"]
    if max_duration_s:
        base_cmd += [
            "--download-sections", f"*0-{max_duration_s}",
            "--force-keyframes-at-cuts",
        ]

    attempts = []
    proxy_list = os.environ.get("WEBSHARE_PROXIES") or os.environ.get("WEBSHARE_PROXY")
    if proxy_list:
        for proxy in proxy_list.split(","):
            attempts.append(("proxy", base_cmd + ["--proxy", proxy] + [url]))
    attempts.append(("direct", base_cmd + [url]))

    last_err = None
    for round_no in range(3):
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
        if round_no < 2:
            print(f"Retrying download in 30s (round {round_no + 2}/3)...")
            time.sleep(30)
    raise RuntimeError(f"yt-dlp failed for {url}: {last_err}")