"""Tests for llm.captions — caption generation with mocked LLM responses."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import llm.captions as captions_mod  # noqa: E402
from llm.captions import generate_caption  # noqa: E402
from llm.client import llm_complete  # noqa: E402


def test_generate_caption_uses_llm_output(monkeypatch):
    monkeypatch.setattr(
        captions_mod, "llm_complete", lambda prompt, **kw: "Hand-carved magic! #woodworking"
    )
    out = generate_caption("Some title", fallback="TEMPLATE")
    assert out == "Hand-carved magic! #woodworking"


def test_generate_caption_appends_part_suffix(monkeypatch):
    monkeypatch.setattr(
        captions_mod, "llm_complete", lambda prompt, **kw: "Watch this transformation #asmr"
    )
    out = generate_caption("Some title", index=2, total=3, fallback="TEMPLATE")
    assert out.endswith("(Part 2/3)")


def test_generate_caption_falls_back_when_llm_none(monkeypatch):
    monkeypatch.setattr(captions_mod, "llm_complete", lambda prompt, **kw: None)
    assert generate_caption("t", fallback="TEMPLATE") == "TEMPLATE"


def test_generate_caption_falls_back_on_too_short(monkeypatch):
    monkeypatch.setattr(captions_mod, "llm_complete", lambda prompt, **kw: "short")
    assert generate_caption("t", fallback="TEMPLATE") == "TEMPLATE"


def test_generate_caption_falls_back_on_exception(monkeypatch):
    def boom(prompt, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(captions_mod, "llm_complete", boom)
    assert generate_caption("t", fallback="TEMPLATE") == "TEMPLATE"


def test_llm_complete_strips_think_blocks(monkeypatch):
    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {"message": {"content": "<think>reasoning here</think>\nFinal answer!"}}
                ]
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResp()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("llm.client.requests.post", fake_post)
    assert llm_complete("prompt") == "Final answer!"
