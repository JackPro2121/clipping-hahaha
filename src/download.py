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


def _bili_headers(out_dir):
    import uuid

    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    b3 = b4 = None
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/frontend/finger/spi",
            headers={"User-Agent": ua, "Referer": "https://www.bilibili.com/"},
            timeout=30,
        )
        data = (resp.json() or {}).get("data") or {}
        b3, b4 = data.get("b_3"), data.get("b_4")
    except Exception as exc:
        print(f"bilibili finger API failed, using synthetic cookies: {exc}")
    if not b3:
        b3 = str(uuid.uuid4()).upper()
    if not b4:
        b4 = str(uuid.uuid4()).upper() + str(uuid.uuid4()).upper()
    cookie = "buvid3=%s; buvid4=%s; b_nut=%d; _uuid=%s" % (
        b3,
        b4,
        int(time.time()),
        uuid.uuid4(),
    )
    headers = {
        "User-Agent": ua,
        "Referer": "https://www.bilibili.com/",
        "Cookie": cookie,
        "Origin": "https://www.bilibili.com",
    }
    lines = [
        "# Netscape HTTP Cookie File",
        f"#HttpOnly_.bilibili.com\tTRUE\t/\tTRUE\t0\tbuvid3\t{b3}",
        f"#HttpOnly_.bilibili.com\tTRUE\t/\tTRUE\t0\tbuvid4\t{b4}",
        f".bilibili.com\tTRUE\t/\tTRUE\t0\tb_nut\t{int(time.time())}",
        f".bilibili.com\tTRUE\t/\tTRUE\t0\t_uuid\t{uuid.uuid4()}",
    ]
    dest = out_dir / "bili_cookies.txt"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return headers, dest


def _bili_api_get(url, headers, retries=3):
    last = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            last = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last = str(exc)[:120]
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"bilibili API failed: {last}")


def _bili_stream_download(url, dest, headers, retries=3):
    for attempt in range(retries):
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(1024 * 1024):
                        fh.write(chunk)
            if dest.stat().st_size > 10_000:
                return
            raise RuntimeError("stream too small")
        except (requests.RequestException, RuntimeError) as exc:
            last = str(exc)[:160]
            if attempt == retries - 1:
                raise RuntimeError(f"stream download failed: {last}")
            time.sleep(3 * (attempt + 1))


def _bili_download(url, out_dir, max_duration_s):
    m = _BILI_RE.search(url)
    bvid = m.group(1)
    headers, cookies_file = _bili_headers(out_dir)

    pagelist = _bili_api_get(
        f"https://api.bilibili.com/x/player/pagelist?bvid={bvid}", headers
    )
    pages = pagelist.get("data") or []
    if not pages:
        raise RuntimeError(f"no pages for {bvid}: {pagelist.get('message')}")
    cid = pages[0]["cid"]
    print(f"bilibili {bvid}: cid={cid}")

    dash = None
    for qn in (80, 64, 48, 32):
        playurl = _bili_api_get(
            f"https://api.bilibili.com/x/player/playurl"
            f"?bvid={bvid}&cid={cid}&qn={qn}&fnval=16&fourk=1",
            headers,
        )
        if playurl.get("code") == 0:
            data = playurl.get("data") or {}
            if data.get("dash"):
                dash = data["dash"]
                break
    if not dash:
        raise RuntimeError(
            f"no playable dash for {bvid}: {playurl.get('message')}"
        )

    vids = dash["video"]
    auds = dash["audio"]
    vid = max(vids, key=lambda x: (x.get("width") or 0) * (x.get("height") or 0))
    aud = max(auds, key=lambda x: x.get("bandwidth") or 0)
    v_url = vid.get("baseUrl") or vid.get("backupUrl", [""])[0]
    a_url = aud.get("baseUrl") or aud.get("backupUrl", [""])[0]
    print(
        f"bilibili {bvid}: picking video {vid.get('width')}x{vid.get('height')} "
        f"+ audio {aud.get('bandwidth') // 1000}kbps"
    )

    v_path = out_dir / f"{bvid}_video.m4s"
    a_path = out_dir / f"{bvid}_audio.m4s"
    _bili_stream_download(v_url, v_path, headers)
    _bili_stream_download(a_url, a_path, headers)

    out = out_dir / f"{bvid}.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(v_path),
        "-i", str(a_path),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    if out.stat().st_size < 100_000:
        raise RuntimeError(f"merged file too small ({out.stat().st_size}B)")
    v_path.unlink(missing_ok=True)
    a_path.unlink(missing_ok=True)
    return out


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