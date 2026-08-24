"""test_audio_pitch.py — pitch-shift filter generation (Meta fingerprint evasion)."""
from clip import _audio_pitch_filter


def test_pitch_filter_default_factor():
    f = _audio_pitch_filter(4.0)
    assert f == "asetrate=44100*1.0400,aresample=44100,atempo=0.961538"


def test_pitch_filter_zero_returns_empty():
    assert _audio_pitch_filter(0) == ""
    assert _audio_pitch_filter(0.0) == ""


def test_pitch_filter_negative_returns_empty():
    assert _audio_pitch_filter(-2.5) == ""


def test_pitch_filter_invalid_returns_empty():
    assert _audio_pitch_filter(None) == ""
    assert _audio_pitch_filter("abc") == ""


def test_pitch_filter_preserves_duration_math():
    """asetrate factor and atempo divisor must be exact inverses."""
    for pct in (1.2, 3.0, 4.0, 6.5):
        f = _audio_pitch_filter(pct)
        factor_str = f.split("asetrate=44100*")[1].split(",")[0]
        tempo_str = f.split("atempo=")[1]
        assert abs(float(factor_str) * float(tempo_str) - 1.0) < 1e-4


def test_pitch_filter_old_default_was_insufficient():
    """Guard: shift must be >= 3% — 1.2% let Meta Rights Manager match audio."""
    f = _audio_pitch_filter(1.2)
    assert f != ""
    # documented weakness — kept only as regression context
    assert "1.0120" in f
