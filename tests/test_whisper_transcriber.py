"""Test Faster-Whisper AI Transcriber module."""

from pathlib import Path
from captions.whisper_transcriber import transcribe_and_translate, get_whisper_model


def test_whisper_transcribe_nonexistent_file():
    result = transcribe_and_translate(Path("nonexistent_video_file.mp4"))
    assert result == []


def test_whisper_transcribe_none():
    result = transcribe_and_translate(None)
    assert result == []


def test_gemini_transcribe_missing_key(monkeypatch):
    from captions.whisper_transcriber import _transcribe_with_gemini
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert _transcribe_with_gemini("nonexistent.wav") == []


def test_gemini_transcribe_mocked_success(monkeypatch, tmp_path):
    from captions.whisper_transcriber import _transcribe_with_gemini
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key")
    dummy_wav = tmp_path / "test.wav"
    dummy_wav.write_bytes(b"RIFFdummywavdata")

    class MockResp:
        status_code = 200
        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '[{"start": 0.5, "duration": 2.0, "text": "Restoring an antique teapot"}]'
                                }
                            ]
                        }
                    }
                ]
            }

    monkeypatch.setattr("requests.post", lambda *a, **kw: MockResp())
    result = _transcribe_with_gemini(str(dummy_wav))
    assert len(result) == 1
    assert result[0]["text"] == "Restoring an antique teapot"
    assert result[0]["start"] == 0.5
