"""conftest.py — Add src/ to sys.path so tests can import pipeline modules directly."""
import sys
from pathlib import Path

# Allow: from clip import _select_windows
# Allow: from captions.bilibili_subtitles import make_title_captions
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
