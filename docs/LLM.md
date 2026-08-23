# LLM Subsystem — Providers, Fallback Chains & Smart Selection

Companion to `AGENTS.md` and `docs/ARCHITECTURE.md`. Documents everything about
how Large Language Models are wired into the pipeline, what they cost, and how
the system behaves when they fail (they must never break the pipeline).

---

## 1. Design Contract

1. **LLM is always optional.** Every LLM call has a rule-based fallback. A dead
   API key, rate limit, or timeout degrades quality — it never crashes a run.
2. **Provider chain, not single provider.** Groq → Gemini → OpenRouter, tried
   in order. First provider that answers wins.
3. **Keys are secrets.** `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`
   live in GitHub Actions secrets and the gitignored local `.env`. Never commit.
4. **All providers are free-tier.** Pipeline cash cost stays $0.

---

## 2. Provider Chain (`src/llm/client.py`)

| Order | Provider | Model (2026-08) | Notes |
|---|---|---|---|
| 1 | Groq | `openai/gpt-oss-120b` | `reasoning_effort: low` — fastest, primary |
| 2 | Gemini | `gemini-flash-latest` | stable alias; survives model deprecations |
| 3 | OpenRouter | `z-ai/glm-5.2:free` | backup; sometimes 429 (busy) upstream |

Hard-won notes:
- Model names rotate fast. `gemini-2.0-flash` retired mid-August 2026; the
  `-latest` aliases are the safe choice.
- Reasoning models (e.g. `qwen3.6`) emit `<think>...</think>` blocks that eat
  the token budget — `llm_complete()` strips them, but prefer non-reasoning
  models for short outputs.
- `llm_complete(prompt, max_tokens, temperature)` returns `str` or `None`.
  It never raises.

---

## 3. LLM Captions (`src/llm/captions.py`)

**What:** one unique hook caption per clip, generated from the translated
title + transcript excerpt. Replaces the old fixed template
("Incredible Craft Mastery You Have to See") that every post shared.

**Flow (in `main.py`, per clip, before the channel loop):**
```
template_caption = build_caption(...)          # always computed
llm_caption      = generate_caption(title, transcript_text, index, total)
caption          = llm_caption or build_caption(..., service=service)  # per-service fallback
```

**Output rules baked into the prompt:** one hook sentence ≤120 chars,
2–3 hashtags, ≤1 emoji, no preamble. Multi-part clips keep the
`(Part i/total)` suffix. Output is sanitized (whitespace collapse, quote
strip) and length-checked (15–240 chars) — anything odd falls back.

**Token budget:** `max_tokens=400` (reasoning models need headroom; 200 caused
mid-sentence truncation).

---

## 4. Smart Clip Windows (`src/llm/windows.py`)

**What:** replaces fixed window math (0s / mid / end) with content-aware
selection. Three tiers:

| Tier | Condition | Mechanism |
|---|---|---|
| 1 | Transcript present | LLM reads timestamped segments → picks hook/action/payoff windows |
| 2 | No transcript (music/ASMR) | Audio-energy peaks → LLM picks diverse spread from ranked candidates |
| 3 | Any failure | Existing `_select_windows()` heuristic (unchanged) |

**Tier 2 — audio energy (`src/utils/audio_energy.py`):**
ffmpeg demuxes audio to 8 kHz mono s16le PCM (piped, no temp files) → stdlib
RMS per second → sliding-window scoring → top non-overlapping candidates.
Loud moments correlate with action, impacts, and reveals in craft videos.
Pure stdlib — no numpy/scipy dependency on the runner.

**Validation (`validate_windows`)** — LLM output is never trusted:
- clamped to `[0, duration]`
- min length enforced (0.8 × `min_clip_s`, tolerating LLM rounding)
- overlaps resolved (earlier window wins, later clipped)
- count capped at `max_clips_per_video`

**LLM output format:** strict JSON array `[{"start": 65, "end": 110}, ...]`,
parsed leniently (dict or list forms) via regex extraction.

---

## 5. Config & Cost

`config.json → clipper.smart_windows: true` (per-profile too) — set `false`
to revert to heuristic windows.

| Item | Cost |
|---|---|
| Groq free tier | ~30 req/min — captions (≤6/run) + windows (≤2/run) fit easily |
| Gemini / OpenRouter free tiers | unused unless Groq fails |
| Expected monthly cost | **$0** |

---

## 6. Testing

`tests/test_llm_captions.py` — mocked LLM: fallback on None/short/exception,
part-suffix logic, `<think>` stripping.
`tests/test_smart_windows.py` — validation edge cases, JSON parsing, energy
peak selection (synthetic loudness profiles).

Both suites mock the network — CI never calls real providers.
