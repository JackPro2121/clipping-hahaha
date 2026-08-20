# Operations — Setup, Secrets, Troubleshooting

How to get this running locally and on GitHub Actions, plus a troubleshooting matrix.
Companion to `AGENTS.md`, `ARCHITECTURE.md`, `PIPELINE.md`.

---

## 1. Prerequisites

- Python **3.12** (local)
- `ffmpeg` / `ffprobe` on PATH.
  - Local Windows: gyan.dev build (8.1.2) is fine **except `xfade`** (broken — see AGENTS.md §10.3).
  - Runner: installed by the workflow (apt → static fallback), ffmpeg 6.1.1.
- A GitHub repo `JackPro2121/clipping-hahaha` with the workflow file present.

## 2. Secrets setup (GitHub → repo → Settings → Secrets and variables → Actions)

| Secret | Value source | Notes |
|---|---|---|
| `BUFFER_API_KEY` | Buffer account → settings; 43-char token | The one tied to org `6a85a8289189f6da59a63fb7` (has the TikTok channel). A stale token points at a Twitter-only org. |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Cloudinary dashboard | Needed by `media.py` |
| `CHOCODATA_API_KEY` | chocodata.com | Only needed for YouTube discovery/transcripts |
| `YT_COOKIES` | base64 of a Netscape `cookies.txt` | Only for YouTube fallback; YouTube is mostly dead on the runner |
| `APIFY_TOKEN` | Apify account | Only for the YouTube Apify fallback |

**Security:** this repo is public. Never store cookie/token values in any committed file. If a secret is
ever pushed in plaintext, rotate it immediately (see §5).

## 3. Local `.env` (gitignored) — key naming gotcha

The Python code reads plain env vars, it does **not** read `.env`. When running locally, export them.
The local `.env` uses **spaced / hyphenated** key names that are NOT what the code reads:

| `.env` key | Code expects | Action |
|---|---|---|
| `Buffer api key` | `BUFFER_API_KEY` | Use the `Buffer api key` VALUE (it is the correct Buffer org); export it as `BUFFER_API_KEY` |
| `CHOCODATA-API-KEY` | `CHOCODATA_API_KEY` | Export the value as `CHOCODATA_API_KEY` |
| `CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET` | same | fine |

PowerShell snippet to load and export:
```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^([^=]+)=(.*)$') {
    [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
  }
}
# then map the spaced keys explicitly if needed:
$env:BUFFER_API_KEY = $env:'Buffer api key'
```

## 4. Local run

```powershell
pip install -r requirements.txt          # python 3.12
# ensure ffmpeg/ffprobe on PATH
# export env vars (see §3)

python src/find_sources.py               # optional discovery
python src/main.py                       # processes pending sources.json
```

Run a single source end-to-end for testing: put exactly one URL in `sources.json` with
`"status": "pending"`, run `main.py`, watch the logs.

## 5. Triggering the GitHub Action manually

Without `gh` auth, use the REST API (see AGENTS.md §9). Token must have `repo`/`workflow` scope.

```powershell
$t = "GITHUB_TOKEN"
$body = '{"ref":"main"}' | ConvertTo-Json
Invoke-RestMethod -Uri "https://api.github.com/repos/JackPro2121/clipping-hahaha/actions/workflows/clip-and-post.yml/dispatches" `
  -Method Post -Headers @{ Authorization="Bearer $t"; "X-GitHub-Api-Version"="2022-11-28" } -ContentType "application/json" -Body $body
```

Monitor:
```powershell
Invoke-RestMethod -Uri "https://api.github.com/repos/JackPro2121/clipping-hahaha/actions/runs" `
  -Headers @{ Authorization="Bearer $t"; "X-GitHub-Api-Version"="2022-11-28" }
# logs: /actions/runs/{run_id}/jobs → /actions/jobs/{job_id}/logs
```

## 6. Posting policy & the Buffer queue

- Every run queues up to `3 sources × 3 clips = 9` posts on the TikTok channel, **scheduled** (Buffer
  `mode: addToQueue`, `schedulingType: automatic`).
- TikTok does not allow third-party auto-publish → the operator confirms each post in the Buffer app.
- The 6-hourly cron keeps adding to the queue. **Check the queue regularly**; old/undesired posts can
  be removed in the Buffer app (or via the Buffer GraphQL `postDelete` mutation).
- To inspect the queue (Python):
  ```python
  from buffer_api import get_org_id
  # query: posts(input:{organizationId, filter:{channelIds}}){edges{node{id status text dueAt}}}
  ```

## 7. Troubleshooting matrix

| Symptom | Likely cause | Fix |
|---|---|---|
| `Discovery disabled in config` | `discovery.enabled` false | Set `"enabled": true` |
| `Discovery failed: …` | bilibili popular API unreachable / 5xx | Transient; retry. Check network on runner. |
| `bilibili download failed: … HTTP 412` | Hit a `www`/`view` endpoint somewhere | Shouldn't happen — API path only. Update yt-dlp only if you later rely on it. |
| `bilibili API failed` | pagelist/playurl 5xx or rate limit | `_bili_api_get` retries 3×; usually transient. |
| `yt-dlp exited 1` on bilibili URL | yt-dlp touched www (regression) | Confirm URL goes through `_bili_download`, not the yt-dlp ladder. |
| `Impersonate target "chrome" is not available` | curl_cffi 0.16+ installed | Pin `curl_cffi>=0.10,<0.16` and reinstall. |
| YouTube `Sign in to confirm you're not a bot` | Runner datacenter IP flagged | Expected. bilibili is the source. If YouTube required, refresh cookies + use Apify. |
| Clips missing / `No clips generated` | Source shorter than `min_clip_s`, or encode failed twice | Shorten `clip_length_s`/`min_clip_s`; check per-clip ffmpeg errors. |
| `invalid DTS: PTS is less than DTS` / video ~4s | `xfade` reintroduced on gyan.dev ffmpeg | Remove `xfade`; use concat + fades. |
| Concat SAR warnings / broken output | Missing `setsar=1` per chunk | Keep `setsar=1` after every crop/scale. |
| Subtitles filter error on Windows | Drive-letter colon in path | Use `_filter_path()` + `subtitles=filename='…'`. |
| `UnicodeEncodeError` printing Chinese titles | Windows cp1252 console | Use `json.dumps(..., ensure_ascii=True)` for debugging. |
| Buffer `FORBIDDEN` / wrong channel | Wrong API key (Twitter-only org) | Use the `Buffer api key` value from `.env` (org `6a85a828…`). |
| Buffer queue full | Many scheduled posts | Confirm/clear posts in Buffer app, or lower `max_posts_per_channel`. |
| Run stuck / concurrency | Previous run not finished | `concurrency: clip-post` serializes; wait for it to finish. |

## 8. Security checklist (public repo)

- [ ] **Rotate** the exposed GitHub token (`ghp_31Ack…`, used in plaintext earlier). Revoke at GitHub →
  Settings → Developer settings → Personal access tokens; add a fresh one as a secret if needed.
- [ ] Never commit `cookies.txt`, `bili_cookies.txt`, `.env`, or any token/API-key value.
- [ ] After rotating a YouTube session, re-export cookies and re-set `YT_COOKIES` secret.
- [ ] The Apify token and ChocoData key are secrets — if ever exposed in logs/commits, rotate them too.

## 9. Operational tips

- **Testing the bilibili runner path**: put ONE pending URL in `sources.json`, set
  `discovery.enabled=false` temporarily, run the workflow, then re-enable.
- **Quality knob**: source resolution is capped at 480p on many free bilibili videos. To attempt
  720p/1080p, a logged-in bilibili account's cookies would be needed (untested; likely flaky from the
  datacenter IP — treat as optional).
- **Changing cadence**: edit the `schedule` cron in the workflow (e.g. `0 */12 * * *` for twice a day)
  and/or `discovery.max_new_sources`.
- **Captions**: bilibili has no transcript API here, so clips post without burned captions. For English
  sources via YouTube (if ever restored), captions come from ChocoData transcripts.