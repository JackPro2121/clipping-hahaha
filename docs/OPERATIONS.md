# Operations — Setup, Profiles, Secrets & Troubleshooting

How to operate, configure, and maintain the ZenCut automation pipeline locally and on GitHub Actions.
Companion to `AGENTS.md`, `ARCHITECTURE.md`, and `PIPELINE.md`.

---

## 1. Prerequisites

- Python **3.12** or **3.14** (local)
- `ffmpeg` / `ffprobe` on system PATH.
- GitHub Repository `JackPro2121/clipping-hahaha` with GitHub Actions enabled.

---

## 2. Secrets Configuration (GitHub ➔ Repo ➔ Settings ➔ Secrets ➔ Actions)

| Secret | Service | Purpose |
|---|---|---|
| `BUFFER_API_KEY` | Buffer GraphQL API | Authenticates scheduling to TikTok (`jackoscar287`) and Instagram (`zencutofficials`). |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary | Video storage bucket name (`bu7wxgwh`). |
| `CLOUDINARY_API_KEY` | Cloudinary | Cloudinary API Key. |
| `CLOUDINARY_API_SECRET` | Cloudinary | Cloudinary API Secret. |
| `SLACK_WEBHOOK_URL` | Slack *(Optional)* | Sends automated run summaries and queue alerts. |

---

## 3. Switching Pipeline Profiles

To switch the content niche (e.g. from Woodworking to Tech Gadgets or Street Food), simply change `active_profile` in `config.json`:

```json
{
  "active_profile": "satisfying_crafts"
}
```

Available Profiles:
- `"satisfying_crafts"` (V1): Woodworking, antique restoration, satisfying craft, precision machine art.
- `"future_tech_gadgets"` (V2): Smart home gadgets, future tech, novel inventions.
- `"street_food_asmr"` (V3): High-speed street food cooking, ASMR food.

---

## 4. Local Execution & Testing

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the 49-test verification suite
python -m pytest tests/ -v

# 3. Run source discovery
python src/find_sources.py

# 4. Run the pipeline locally
python src/main.py
```

---

## 5. Troubleshooting Matrix

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `Buffer queue limit reached` | Free tier 10-post queue is full | Open Buffer app and publish or delete scheduled posts. |
| `Instagram posts require a type` | Missing Reels metadata | Handled automatically in `src/buffer_api.py` with `metadata.instagram.type: "reel"`. |
| `UnicodeEncodeError on Windows` | Console cp1252 printing Chinese | All scripts enforce `sys.stdout.reconfigure(encoding='utf-8')`. |
| `Watermark on video corners` | Creator-stamped UID in vertical video | 6% safe overscan margin in `src/clip.py` automatically crops out corner areas. |
| `No pending sources ready` | All URLs processed or in retry backoff | Run `python src/find_sources.py` to discover fresh sources. |