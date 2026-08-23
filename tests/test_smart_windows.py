"""Tests for smart window selection: validation, JSON parsing, audio peaks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from llm.windows import _parse_json_windows, validate_windows  # noqa: E402
from utils.audio_energy import find_energy_peaks  # noqa: E402


def test_validate_keeps_good_windows():
    out = validate_windows([(10, 55), (120, 165)], 300, 45, 10, 3)
    assert out == [(10.0, 55.0), (120.0, 165.0)]


def test_validate_clamps_out_of_range():
    out = validate_windows([(-5, 50), (280, 400)], 300, 45, 10, 3)
    assert out[0][0] == 0.0
    assert out[-1][1] <= 300.0


def test_validate_drops_too_short():
    out = validate_windows([(10, 15)], 300, 45, 10, 3)
    assert out == []


def test_validate_resolves_overlap():
    out = validate_windows([(10, 55), (30, 80), (200, 245)], 300, 45, 3, 3)
    assert out[0] == (10.0, 55.0)
    # second window clipped to start after first, kept because still long enough
    assert all(b[0] >= a[1] for a, b in zip(out, out[1:]))


def test_validate_caps_count():
    out = validate_windows([(i * 100, i * 100 + 45) for i in range(6)], 700, 45, 10, 3)
    assert len(out) == 3


def test_validate_rejects_garbage():
    assert validate_windows([("a", "b"), None, (1,)], 300, 45, 10, 3) == []


def test_parse_json_windows_from_prose():
    text = 'Here you go: [{"start": 30, "end": 75}, {"start": 120, "end": 160}] done'
    assert _parse_json_windows(text) == [(30, 75), (120, 160)]


def test_parse_json_windows_list_form():
    assert _parse_json_windows("[[10, 50], [90, 130]]") == [(10, 50), (90, 130)]


def test_parse_json_windows_invalid():
    assert _parse_json_windows("no json here") is None
    assert _parse_json_windows('{"start": 1}') is None


def test_energy_peaks_pick_loudest_region():
    # 100s profile: quiet everywhere except a loud burst at 60-80s
    profile = [0.01] * 100
    for i in range(60, 80):
        profile[i] = 0.9
    out = find_energy_peaks(profile, 100, 20, 2, 10)
    assert out, "should return at least one window"
    # the loudest window must cover the burst
    top = out[0]
    assert top[0] <= 65 and top[1] >= 75


def test_energy_peaks_no_overlap():
    profile = [0.5] * 200
    out = find_energy_peaks(profile, 200, 45, 3, 10)
    assert len(out) == 3
    assert all(b[0] >= a[1] for a, b in zip(out, out[1:]))


def test_energy_peaks_empty_profile():
    assert find_energy_peaks([], 100, 45, 3, 10) == []
