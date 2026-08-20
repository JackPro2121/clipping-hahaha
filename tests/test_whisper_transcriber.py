"""Test Faster-Whisper AI Transcriber module."""

from pathlib import Path
from captions.whisper_transcriber import transcribe_and_translate, get_whisper_model


def test_whisper_transcribe_nonexistent_file():
    result = transcribe_and_translate(Path("nonexistent_video_file.mp4"))
    assert result == []


def test_whisper_transcribe_none():
    result = transcribe_and_translate(None)
    assert result == []
