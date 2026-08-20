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


def transcribe_and_translate(video_path, max_duration_s=120):
    """Transcribe and translate Chinese speech from video into English segments.

    Returns:
        list[dict]: List of segments [{"start": 0.5, "duration": 2.3, "text": "English text"}]
                    or empty list [] if no speech is present (pure ASMR).
    """
    model = get_whisper_model()
    if model is None:
        return []

    video_path = Path(video_path)
    if not video_path.exists():
        return []

    wav_path = video_path.with_suffix(".temp_audio.wav")
    if not extract_audio_wav(video_path, wav_path):
        return []

    try:
        # task="translate" directly converts Chinese speech to English
        segments_gen, info = model.transcribe(
            str(wav_path),
            task="translate",
            language="zh",
            beam_size=1,
            vad_filter=True,  # Voice Activity Detection filters out pure silence/ASMR noise
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        # Check if actual speech was detected
        if info.language_probability < 0.35 and info.all_language_probs and "zh" not in [p[0] for p in info.all_language_probs[:2]]:
            # Not Chinese speech (likely background ASMR noise)
            return []

        segments = []
        for s in segments_gen:
            text = s.text.strip()
            # Filter out hallucinations / empty brackets / pure punctuation
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
        else:
            print("Whisper AI detected pure ASMR/silence — no speech subtitles needed.")

        return segments
    except Exception as exc:
        print(f"Whisper transcription error: {exc}")
        return []
    finally:
        if wav_path.exists():
            try:
                wav_path.unlink()
            except OSError:
                pass
