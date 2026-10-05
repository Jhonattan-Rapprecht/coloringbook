"""Turn images into print-ready, Amazon KDP friendly coloring books."""

from .config import BookOptions, TRIM_SIZES
from .builder import build_book, BuildResult

__all__ = ["BookOptions", "TRIM_SIZES", "build_book", "BuildResult"]
