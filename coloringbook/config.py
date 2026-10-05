"""Page geometry and Amazon KDP print specifications.

All lengths are in inches unless stated otherwise.
Source: KDP "Set Trim Size, Bleed, and Margins" and "Create a Paperback Cover".
"""

from __future__ import annotations

from dataclasses import dataclass

POINTS_PER_INCH = 72
PRINT_DPI = 300

TRIM_SIZES: dict[str, tuple[float, float]] = {
    "8.5x11": (8.5, 11.0),     # most popular coloring book size
    "8.27x11.69 (A4)": (8.27, 11.69),
    "8.25x11": (8.25, 11.0),
    "8x10": (8.0, 10.0),
    "8.5x8.5": (8.5, 8.5),
    "7.5x9.25": (7.5, 9.25),
    "6x9": (6.0, 9.0),
}

HOME_PAPER: dict[str, tuple[float, float]] = {"letter": (8.5, 11.0), "a4": (8.27, 11.69)}

KDP_BLEED = 0.125
KDP_MIN_PAGES = 24
KDP_MAX_PAGES = 828
KDP_MIN_OUTSIDE_MARGIN_NO_BLEED = 0.25
KDP_MIN_OUTSIDE_MARGIN_BLEED = 0.375
KDP_SPINE_TEXT_MIN_PAGES = 79

# Spine width per page for black & white interiors.
SPINE_PER_PAGE = {"white": 0.002252, "cream": 0.0025}

# (max page count, inside/gutter margin)
_GUTTER_TABLE = [(150, 0.375), (300, 0.5), (500, 0.625), (700, 0.75), (828, 0.875)]


def kdp_gutter(page_count: int) -> float:
    for max_pages, gutter in _GUTTER_TABLE:
        if page_count <= max_pages:
            return gutter
    return _GUTTER_TABLE[-1][1]


def spine_width(page_count: int, paper: str = "white") -> float:
    return page_count * SPINE_PER_PAGE[paper]


@dataclass
class BookOptions:
    title: str = "My Coloring Book"
    subtitle: str = ""
    author: str = ""
    trim: str = "8.5x11"
    paper: str = "white"                 # "white" or "cream"
    margin: float = 0.5                  # outside/top/bottom margin, inches
    bleed: bool = False                  # coloring pages have white borders: no bleed needed
    blank_backs: bool = True             # one picture per sheet, so markers don't bleed through
    title_page: bool = True
    belongs_to_page: bool = True         # "This book belongs to: ____"
    auto_rotate: bool = True             # rotate landscape art onto portrait pages if it gets bigger
    auto_trim: bool = True               # remove empty white borders around the artwork
    clean_lineart: bool = True           # grayscale + push near-white to pure white
    upscale_to_print_dpi: bool = True    # resample low-res images to 300 DPI
    cover_image_index: int = 0           # which image to use on the front cover
    make_cover: bool = True
    make_ebook: bool = True
    make_home_print: bool = True
    home_paper: str = "letter"           # "letter" or "a4" for printing at home
    cover_color: str = "#FFFFFF"         # background color of the paperback / eBook cover
    language: str = "en"

    @property
    def trim_size(self) -> tuple[float, float]:
        if self.trim not in TRIM_SIZES:
            raise ValueError(f"Unknown trim size {self.trim!r}. Choose from: {', '.join(TRIM_SIZES)}")
        return TRIM_SIZES[self.trim]

    def validate(self) -> None:
        _ = self.trim_size
        if self.paper not in SPINE_PER_PAGE:
            raise ValueError("paper must be 'white' or 'cream'")
        if self.home_paper not in HOME_PAPER:
            raise ValueError("home_paper must be 'letter' or 'a4'")
        min_margin = KDP_MIN_OUTSIDE_MARGIN_BLEED if self.bleed else KDP_MIN_OUTSIDE_MARGIN_NO_BLEED
        if self.margin < min_margin:
            raise ValueError(f"margin must be at least {min_margin} in for KDP")
        w, h = self.trim_size
        if self.margin * 2 + 0.875 >= min(w, h):
            raise ValueError("margin is too large for this trim size")
