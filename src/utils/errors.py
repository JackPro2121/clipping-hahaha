# Custom exceptions for the Clipping-or-posting pipeline.
# Import these instead of catching raw RuntimeError strings.


class QueueFullError(Exception):
    """Raised when Buffer's posting queue limit is reached."""


class DownloadError(Exception):
    """Raised when all download strategies for a URL fail."""


class ClipError(Exception):
    """Raised when clip encoding fails even after the no-effects retry."""


class CaptionError(Exception):
    """Non-fatal; callers should catch. Raised on unrecoverable caption fetch failure."""
