"""whisper_transcriber.py — $0 AI Speech-to-Text & Translation Engine.

Uses Faster-Whisper (CTranslate2) on CPU to detect spoken Chinese in videos
and directly translate speech into English subtitle timestamps.
If a video is pure ASMR (no speech detected), it returns an empty transcript
so the video remains 100% clean and immersion-focused.
"""

import subprocess
from pathlib import Path

_MODEL = None


def get_whisper_model(model_size="tiny"):
    """Lazy load Faster-Whisper model in int8 CPU mode."""
    global _MODEL
    if _MODEL is None:
        try:
            from faster_whisper import WhisperModel
            # 'tiny' or 'base' are ultra fast on 2-core CPU (~3-5s for 45s audio)
            _MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
        except ImportError:
            print("faster-whisper not installed; skipping audio AI transcription.")
            return None
        except Exception as exc:
            print(f"Failed to initialize Faster-Whisper model: {exc}")
            return None
    return _MODEL


def extract_audio_wav(video_path, out_wav):
    """Extract mono 16kHz WAV audio from video for Whisper processing."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(out_wav),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return res.returncode == 0 and Path(out_wav).exists()
    except Exception as exc:
        print(f"Audio extraction failed: {exc}")
        return False


def _transcribe_with_gemini(wav_path):
    """Use Gemini Flash free multimodal API to transcribe and translate audio speech into English segments."""
    import base64
    import json
    import os
    import re
    import requests

    key = os.environ.get("GEMINI_API_KEY")
    if not key or not Path(wav_path).exists():
        return []

    try:
        audio_bytes = Path(wav_path).read_bytes()
        # Cap size to 10MB to stay well within free request limits
        if len(audio_bytes) > 10 * 1024 * 1024:
            return []
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

        prompt = (
            "Listen to this audio track from a craftsmanship / woodworking / restoration video. "
            "If there is spoken dialogue (in Chinese or any language), transcribe and translate it into concise, fluent English subtitle segments. "
            "If the audio is pure ambient sound, background music, or ASMR tool noises with NO spoken words, respond with an empty list []. "
            "Format your response ONLY as a JSON array of objects: "
            '[{"start": 1.2, "duration": 2.5, "text": "English subtitle"}]'
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "audio/wav",
                                "data": b64_audio,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 600,
                "temperature": 0.1,
            },
        }
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            return []

        data = resp.json()
        raw_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        m = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not m:
            return []

        parsed = json.loads(m.group(0))
        segments = []
        for seg in parsed if isinstance(parsed, list) else []:
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            s = float(seg.get("start", 0))
            d = max(0.5, float(seg.get("duration", 2.0)))
            segments.append({"start": round(s, 2), "duration": round(d, 2), "text": text})

        if segments:
            print(f"Gemini Cloud AI transcribed {len(segments)} spoken lines to English.")
        return segments
    except Exception as exc:
        print(f"Gemini audio transcription skipped: {str(exc)[:80]}")
        return []


def transcribe_and_translate(video_path, max_duration_s=120):
    """Transcribe and translate spoken speech from video into English segments.

    Dual-engine:
      1. Local Faster-Whisper CPU (if installed)
      2. Cloud Gemini Multimodal API ($0 free tier)

    Returns:
        list[dict]: List of segments [{"start": 0.5, "duration": 2.3, "text": "English text"}]
                    or empty list [] if no speech is present (pure ASMR).
    """
    if not video_path:
        return []

    video_path = Path(video_path)
    if not video_path.exists():
        return []

    wav_path = video_path.with_suffix(".temp_audio.wav")
    if not extract_audio_wav(video_path, wav_path):
        return []

    try:
        model = get_whisper_model()
        if model is not None:
            # 1. Faster-Whisper path
            segments_gen, info = model.transcribe(
                str(wav_path),
                task="translate",
                language="zh",
                beam_size=1,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            if info.language_probability >= 0.35 or "zh" in [p[0] for p in (info.all_language_probs or [])[:2]]:
                segments = []
                for s in segments_gen:
                    text = s.text.strip()
                    if not text or text in ["...", "。", "！", "？", "[Music]", "[Applause]"]:
                        continue
                    dur = max(0.5, round(s.end - s.start, 2))
                    segments.append({
                        "start": round(s.start, 2),
                        "duration": dur,
                        "text": text,
                    })
                if segments:
                    print(f"Whisper AI transcribed & translated {len(segments)} spoken Chinese lines to English.")
                    return segments

        # 2. Gemini Cloud Multimodal Audio path (zero CPU load, $0 free tier)
        gemini_segs = _transcribe_with_gemini(wav_path)
        if gemini_segs:
            return gemini_segs

        print("Audio AI detected pure ASMR/silence — no speech subtitles needed.")
        return []
    except Exception as exc:
        print(f"Audio transcription error: {exc}")
        return []
    finally:
        if wav_path.exists():
            try:
                wav_path.unlink()
            except OSError:
                pass
