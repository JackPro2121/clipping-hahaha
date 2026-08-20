import base64
import os
import re
import subprocess
import time
from pathlib import Path

import requests

STRATEGIES = [
    {"name": "embedded", "client": "web_embedded", "cookies": False},
    {"name": "cookies-default", "client": "default", "cookies": True},
    {"name": "cookies-safari", "client": "web_safari", "cookies": True},
    {"name": "apify", "apify": True},
]

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})")
_BILI_RE = re.compile(r"bilibili\.com/video/(BV[\w]+)", re.IGNORECASE)
_VIDEO_EXTS = (".mp4", ".webm", ".mkv")
_APIFY_API = "https://api.apify.com/v2"


def _video_id(url):
    m = _BILI_RE.search(url)
    if m:
        return m.group(1)
    m = _VIDEO_ID_RE.search(url)
    if not m:
        raise ValueError(f"Cannot extract video id from {url}")
    return m.group(1)


def _bili_download(url, out_dir, max_duration_s):
    cmd = [
        "yt-dlp",
        "-f", "bv*[height<=720]+ba/b[height<=720]/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-progress",
        "--socket-timeout", "15",
        "--retries", "3",
        "--retry-sleep", "5",
        "--sleep-requests", "1.0",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    if max_duration_s:
        cmd += ["--download-sections", f"*0-{max_duration_s}"]
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)


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
        "--js-runtime", "node",
        "--remote-components", "ejs:github",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    if cookies_file is not None:
        cmd += ["--cookies", str(cookies_file)]
    if max_duration_s:
        cmd += ["--download-sections", f"*0-{max_duration_s}"]
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)


def _apify_download(url, out_dir, video_id):
    token = os.environ["APIFY_TOKEN"]
    actor = os.environ.get("APIFY_ACTOR_ID", "scraperoka/youtube-video-downloader")
    actor_path = actor.replace("/", "~")
    run_resp = requests.post(
        f"{_APIFY_API}/acts/{actor_path}/runs",
        params={"token": token},
        json={
            "video_urls": [{"url": url}],
            "desired_resolution": "720p",
            "upload_video_to_apify": True,
        },
        timeout=60,
    )
    run_resp.raise_for_status()
    run_id = run_resp.json().get("data", {}).get("id")
    if not run_id:
        raise RuntimeError(f"Apify actor did not start: {run_resp.text[:200]}")

    status = "RUNNING"
    for _ in range(60):
        time.sleep(4)
        try:
            st = requests.get(
                f"{_APIFY_API}/actor-runs/{run_id}",
                params={"token": token},
                timeout=30,
            ).json().get("data", {})
            status = st.get("status", "RUNNING")
        except requests.RequestException:
            continue
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED_OUT"):
            break
    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run ended with status {status}")

    items = requests.get(
        f"{_APIFY_API}/actor-runs/{run_id}/dataset/items",
        params={"token": token},
        timeout=30,
    ).json()
    direct = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("apify_storage_url"):
            direct = item["apify_storage_url"]
            break
    if not direct:
        for item in items:
            if not isinstance(item, dict):
                continue
            direct = (
                (item.get("prog_downloadable_link") or {}).get("url")
                or (item.get("downloadable_video_link") or {}).get("mp4")
                or item.get("direct_url")
            )
            if direct:
                break
    if not direct:
        raise RuntimeError("Apify returned no downloadable URL")

    dest = out_dir / f"{video_id}.mp4"
    with requests.get(direct, stream=True, timeout=900) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(1024 * 1024):
                fh.write(chunk)
    if dest.stat().st_size < 100_000:
        raise RuntimeError(
            f"Apify download suspiciously small ({dest.stat().st_size}B)"
        )
    return dest


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

    if _BILI_RE.search(url):
        attempt_dir = out_dir / "attempt-0-bilibili"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        try:
            _bili_download(url, attempt_dir, max_duration_s)
            result = _locate_output(attempt_dir, video_id)
            if result.stat().st_size < 100_000:
                raise RuntimeError(
                    f"suspiciously small file ({result.stat().st_size}B)"
                )
            print(
                f"Download OK via 'bilibili' -> "
                f"{result.name} ({result.stat().st_size // 1024 // 1024}MB)"
            )
            return result
        except (subprocess.CalledProcessError, RuntimeError, TimeoutError) as exc:
            raise RuntimeError(f"bilibili download failed: {str(exc)[:200]}") from exc

    cookies_b64 = os.environ.get("YT_COOKIES")
    cookies_file = None
    if cookies_b64:
        cookies_file = out_dir / "cookies.txt"
        cookies_file.write_bytes(base64.b64decode(cookies_b64))

    last_err = None
    for idx, strat in enumerate(STRATEGIES):
        if strat.get("apify") and not os.environ.get("APIFY_TOKEN"):
            continue
        if strat.get("cookies") and cookies_file is None:
            continue
        attempt_dir = out_dir / f"attempt-{idx}-{strat['name']}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        try:
            if strat.get("apify"):
                result = _apify_download(url, attempt_dir, video_id)
            else:
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
            last_err = f"{strat['name']}: {str(exc)[:200]}"
            print(f"Attempt '{strat['name']}' failed: {str(exc)[:160]}")
            for f in attempt_dir.iterdir():
                try:
                    f.unlink()
                except OSError:
                    pass
        time.sleep(5)

    raise RuntimeError(f"All download strategies failed for {video_id}: {last_err}")