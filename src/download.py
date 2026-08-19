import subprocess
from pathlib import Path


def download_video(url, out_dir, max_duration_s=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-progress",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    if max_duration_s:
        cmd += [
            "--download-sections", f"*0-{max_duration_s}",
            "--force-keyframes-at-cuts",
        ]
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    candidates = [p for p in out_dir.iterdir() if p.is_file()]
    if not candidates:
        raise RuntimeError(f"Download produced no files for {url}")
    return max(candidates, key=lambda p: p.stat().st_size)