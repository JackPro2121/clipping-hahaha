"""Test the translator module for Chinese-to-English translation."""

import pytest
from captions.translator import _has_chinese, translate_to_english, translate_segments


def test_has_chinese_detects_chinese():
    assert _has_chinese("这是一个测试") is True
    assert _has_chinese("Hello world") is False
    assert _has_chinese("Mix 中文 and English") is True
    assert _has_chinese("") is False
    assert _has_chinese(None) is False


def test_translate_to_english_passthrough_english():
    """English text should pass through unchanged (no API call)."""
    assert translate_to_english("Hello world") == "Hello world"
    assert translate_to_english("") == ""
    assert translate_to_english("  ") == ""


def test_translate_segments_preserves_structure():
    """translate_segments should keep start/duration and only transform text."""
    segments = [
        {"start": 0.0, "duration": 3.0, "text": "Hello"},
        {"start": 3.0, "duration": 2.0, "text": "World"},
    ]
    result = translate_segments(segments)
    assert len(result) == 2
    assert result[0]["start"] == 0.0
    assert result[0]["duration"] == 3.0
    assert result[0]["text"] == "Hello"  # English passes through
    assert result[1]["text"] == "World"


def test_translate_segments_empty():
    assert translate_segments(None) is None
    assert translate_segments([]) == []
