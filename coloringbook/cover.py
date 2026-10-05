"""Paperback wraparound cover (PDF) and Kindle eBook cover (JPG)."""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageColor, ImageDraw

from . import text
from .config import (KDP_BLEED, KDP_SPINE_TEXT_MIN_PAGES, POINTS_PER_INCH, PRINT_DPI, BookOptions,
                     spine_width)
from .images import PreparedImage

COVER_SAFE = 0.25         # keep text/art this far inside the trim line (KDP minimum is 0.125")
SPINE_TEXT_MARGIN = 0.0625
BARCODE_SIZE = (2.0, 1.2)  # area KDP reserves for the ISBN barcode on the back cover
EBOOK_COVER_SIZE = (1600, 2560)


@dataclass
class CoverInfo:
    width: float
    height: float
    spine: float
    spine_text: bool


def _text_color(background: str) -> str:
    r, g, b = ImageColor.getrgb(background)[:3]
    return "black" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "white"


def draw_front(canvas: Image.Image, safe: tuple[float, float, float, float], art: PreparedImage,
               opts: BookOptions) -> None:
    """Front cover design inside the ``safe`` pixel box: title, framed artwork, subtitle/author."""
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = safe
    w, h = x1 - x0, y1 - y0
    ink = _text_color(opts.cover_color)

    title_bottom = text.draw_centered(draw, opts.title, (x0, y0, x1, y0 + h * 0.22), int(h * 0.09), ink, True, 3)
    footer = " · ".join(t for t in (opts.subtitle, opts.author) if t)
    footer_top = y1 - h * 0.10 if footer else y1
    if opts.subtitle:
        text.draw_centered(draw, opts.subtitle, (x0, footer_top, x1, footer_top + h * 0.05), int(h * 0.035), ink,
                           False, 2)
    if opts.author:
        text.draw_centered(draw, opts.author, (x0, footer_top + h * 0.05, x1, y1), int(h * 0.03), ink, False, 1)

    frame_pad = w * 0.03
    area = (x0, title_bottom + h * 0.03, x1, footer_top - h * 0.02)
    aw, ah = area[2] - area[0] - 2 * frame_pad, area[3] - area[1] - 2 * frame_pad
    img = art.color
    scale = min(aw / img.width, ah / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    img = img.resize(size, Image.LANCZOS)
    ix = round(area[0] + (area[2] - area[0] - size[0]) / 2)
    iy = round(area[1] + (area[3] - area[1] - size[1]) / 2)
    draw.rounded_rectangle((ix - frame_pad, iy - frame_pad, ix + size[0] + frame_pad, iy + size[1] + frame_pad),
                           radius=frame_pad, fill="white", outline=ink, width=max(2, round(frame_pad / 6)))
    canvas.paste(img, (ix, iy))


def build_paperback_cover(prepared: list[PreparedImage], opts: BookOptions, page_count: int, out_path) -> CoverInfo:
    trim_w, trim_h = opts.trim_size
    spine = spine_width(page_count, opts.paper)
    width = 2 * KDP_BLEED + 2 * trim_w + spine
    height = 2 * KDP_BLEED + trim_h
    px = lambda inches: round(inches * PRINT_DPI)  # noqa: E731

    canvas = Image.new("RGB", (px(width), px(height)), opts.cover_color)
    draw = ImageDraw.Draw(canvas)
    ink = _text_color(opts.cover_color)
    top = KDP_BLEED + COVER_SAFE
    bottom = KDP_BLEED + trim_h - COVER_SAFE

    # Front panel (right side).
    front_x = KDP_BLEED + trim_w + spine
    cover_art = prepared[min(max(opts.cover_image_index, 0), len(prepared) - 1)]
    draw_front(canvas, (px(front_x + COVER_SAFE), px(top), px(front_x + trim_w - COVER_SAFE), px(bottom)),
               cover_art, opts)

    # Back panel (left side): small preview grid of pages, keeping the barcode area free.
    back_x0, back_x1 = KDP_BLEED + COVER_SAFE, KDP_BLEED + trim_w - COVER_SAFE
    previews = [p for i, p in enumerate(prepared) if i != opts.cover_image_index][:6] or prepared[:1]
    grid_bottom = bottom - BARCODE_SIZE[1] - 0.25
    text.draw_centered(draw, "Inside you'll find:", (px(back_x0), px(top), px(back_x1), px(top + 0.6)),
                       px(0.35), ink, True, 1)
    _preview_grid(canvas, previews, (px(back_x0), px(top + 0.8), px(back_x1), px(grid_bottom)))

    # Spine text is only allowed by KDP for books with enough pages.
    spine_text = page_count >= KDP_SPINE_TEXT_MIN_PAGES
    if spine_text:
        label = " - ".join(t for t in (opts.title, opts.author) if t)
        block = text.text_block(label, px(trim_h - 2 * COVER_SAFE), px(spine - 2 * SPINE_TEXT_MARGIN),
                                px(spine * 0.6), True, ink, opts.cover_color)
        canvas.paste(block.rotate(-90, expand=True), (px(KDP_BLEED + trim_w + SPINE_TEXT_MARGIN), px(top)))

    doc = pymupdf.open()
    doc.set_metadata({"title": f"{opts.title} - cover", "author": opts.author, "creator": "coloringbook"})
    page = doc.new_page(width=width * POINTS_PER_INCH, height=height * POINTS_PER_INCH)
    page.insert_image(page.rect, stream=_jpeg(canvas), keep_proportion=False)
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return CoverInfo(width, height, spine, spine_text)


def _preview_grid(canvas: Image.Image, items: list[PreparedImage], box: tuple[int, int, int, int]) -> None:
    if not items:
        return
    cols = 3 if len(items) > 4 else 2 if len(items) > 1 else 1
    rows = -(-len(items) // cols)
    x0, y0, x1, y1 = box
    gap = round((x1 - x0) * 0.03)
    cell_w = (x1 - x0 - gap * (cols - 1)) / cols
    cell_h = min((y1 - y0 - gap * (rows - 1)) / rows, cell_w * 1.3)
    draw = ImageDraw.Draw(canvas)
    for i, item in enumerate(items):
        cx = x0 + (i % cols) * (cell_w + gap)
        cy = y0 + (i // cols) * (cell_h + gap)
        img = item.lineart.convert("RGB")
        scale = min((cell_w - 2 * gap) / img.width, (cell_h - 2 * gap) / img.height)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        ix, iy = round(cx + (cell_w - img.width) / 2), round(cy + (cell_h - img.height) / 2)
        draw.rectangle((ix - gap // 2, iy - gap // 2, ix + img.width + gap // 2, iy + img.height + gap // 2),
                       fill="white", outline="#999999", width=3)
        canvas.paste(img, (ix, iy))


def build_ebook_cover(prepared: list[PreparedImage], opts: BookOptions) -> Image.Image:
    w, h = EBOOK_COVER_SIZE
    canvas = Image.new("RGB", (w, h), opts.cover_color)
    margin = round(w * 0.06)
    cover_art = prepared[min(max(opts.cover_image_index, 0), len(prepared) - 1)]
    draw_front(canvas, (margin, margin, w - margin, h - margin), cover_art, opts)
    return canvas


def _jpeg(image: Image.Image, quality: int = 95) -> bytes:
    import io
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=quality, dpi=(PRINT_DPI, PRINT_DPI))
    return buf.getvalue()
