"""Text rendered to images with Pillow, so PDFs never contain un-embedded fonts (a KDP rejection reason)."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

_BOLD_FONTS = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
_REGULAR_FONTS = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]


@lru_cache(maxsize=256)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for name in _BOLD_FONTS if bold else _REGULAR_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def wrap(text: str, fnt: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if fnt.getlength(candidate) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def fit_text(text: str, max_width: float, max_height: float, start_size: int, bold: bool = False,
             max_lines: int = 3, line_spacing: float = 1.15):
    """Largest font size where wrapped ``text`` fits; returns (font, lines, line_height)."""
    size = start_size
    while True:
        fnt = font(size, bold)
        lines = wrap(text, fnt, max_width)
        line_height = size * line_spacing
        fits_width = all(fnt.getlength(line) <= max_width for line in lines)
        if (fits_width and len(lines) <= max_lines and line_height * len(lines) <= max_height) or size <= 8:
            return fnt, lines, line_height
        size = max(8, int(size * 0.92))


def draw_centered(draw: ImageDraw.ImageDraw, text: str, box: tuple[float, float, float, float],
                  start_size: int, fill="black", bold: bool = False, max_lines: int = 3,
                  valign: str = "middle") -> float:
    """Draw wrapped, horizontally centered text inside box. Returns the bottom y of the text."""
    x0, y0, x1, y1 = box
    if not text.strip():
        return y0
    fnt, lines, lh = fit_text(text, x1 - x0, y1 - y0, start_size, bold, max_lines)
    total = lh * len(lines)
    y = {"top": y0, "bottom": y1 - total}.get(valign, y0 + (y1 - y0 - total) / 2)
    for line in lines:
        w = fnt.getlength(line)
        draw.text((x0 + (x1 - x0 - w) / 2, y), line, font=fnt, fill=fill)
        y += lh
    return y


def text_block(text: str, width_px: int, height_px: int, start_size: int, bold: bool = True,
               fill="black", background="white", max_lines: int = 1) -> Image.Image:
    im = Image.new("RGB", (width_px, height_px), background)
    draw_centered(ImageDraw.Draw(im), text, (0, 0, width_px, height_px), start_size, fill, bold, max_lines)
    return im
