"""Page sequencing and PDF writing for the paperback interior and the home-print version."""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pymupdf
from PIL import Image, ImageDraw

from . import text
from .config import (HOME_PAPER, KDP_BLEED, POINTS_PER_INCH, PRINT_DPI, BookOptions, kdp_gutter)
from .images import PreparedImage
from .layout import Rect, fit, render_art


@dataclass(frozen=True)
class Page:
    kind: str                 # "title" | "belongs" | "art" | "blank"
    art_index: int | None = None


@dataclass
class InteriorInfo:
    page_count: int
    gutter: float
    page_size: tuple[float, float]
    native_dpi: dict[str, float] = field(default_factory=dict)


def page_sequence(opts: BookOptions, art_count: int, blank_backs: bool | None = None) -> list[Page]:
    """Order of pages. Page 1 is always a right-hand (recto) page in a printed book."""
    blank_backs = opts.blank_backs if blank_backs is None else blank_backs
    front = []
    if opts.title_page:
        front.append(Page("title"))
    if opts.belongs_to_page:
        front.append(Page("belongs"))
    body = [Page("art", i) for i in range(art_count)]

    pages: list[Page] = []
    for p in front + body:
        pages.append(p)
        if blank_backs:
            pages.append(Page("blank"))
    if blank_backs and pages and pages[-1].kind == "blank":
        pages.pop()  # avoid a trailing blank; even-page padding below re-adds it if needed
    return pages


def pad_to_even(pages: list[Page]) -> list[Page]:
    return pages + [Page("blank")] if len(pages) % 2 else pages


def render_elements(page: Page, box: Rect, prepared: list[PreparedImage], opts: BookOptions,
                    dpi: int = PRINT_DPI, upscale: bool = True) -> list[tuple[Rect, Image.Image, float | None]]:
    """What to draw on one page: list of (rect in inches, grayscale image, native dpi of art or None)."""
    if page.kind == "art":
        art = prepared[page.art_index]
        placement = fit(art.lineart.size, box, opts.auto_rotate)
        return [(placement.rect, render_art(art.lineart, placement, upscale, dpi), placement.native_dpi)]
    if page.kind == "title":
        return [(box, _title_page(box, opts, dpi), None)]
    if page.kind == "belongs":
        return [(box, _belongs_page(box, dpi), None)]
    return []


def _canvas(box: Rect, dpi: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int, int]:
    w, h = round(box.w * dpi), round(box.h * dpi)
    im = Image.new("L", (w, h), 255)
    return im, ImageDraw.Draw(im), w, h


def _title_page(box: Rect, opts: BookOptions, dpi: int) -> Image.Image:
    im, draw, w, h = _canvas(box, dpi)
    pad = w * 0.06
    y = text.draw_centered(draw, opts.title, (pad, h * 0.18, w - pad, h * 0.42), int(dpi * 0.9), 0, True, 3)
    if opts.subtitle:
        text.draw_centered(draw, opts.subtitle, (pad, y + h * 0.03, w - pad, y + h * 0.14), int(dpi * 0.35), 0,
                           False, 3, "top")
    if opts.author:
        text.draw_centered(draw, opts.author, (pad, h * 0.80, w - pad, h * 0.90), int(dpi * 0.3), 0, False, 2)
    return im


def _belongs_page(box: Rect, dpi: int) -> Image.Image:
    im, draw, w, h = _canvas(box, dpi)
    stroke = max(4, dpi // 40)
    frame = (stroke, h * 0.25, w - stroke, h * 0.65)
    draw.rounded_rectangle(frame, radius=dpi * 0.4, outline=0, width=stroke)
    inner_pad = w * 0.08
    text.draw_centered(draw, "This book belongs to:", (frame[0] + inner_pad, frame[1] + h * 0.05,
                                                       frame[2] - inner_pad, frame[1] + h * 0.15),
                       int(dpi * 0.55), 0, True, 2)
    line_y = frame[1] + (frame[3] - frame[1]) * 0.72
    draw.line((frame[0] + inner_pad, line_y, frame[2] - inner_pad, line_y), fill=0, width=stroke)
    return im


def _png(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "PNG", dpi=(PRINT_DPI, PRINT_DPI))
    return buf.getvalue()


def _add_page(doc: pymupdf.Document, size: tuple[float, float], elements) -> None:
    page = doc.new_page(width=size[0] * POINTS_PER_INCH, height=size[1] * POINTS_PER_INCH)
    for rect, image, _ in elements:
        r = pymupdf.Rect(rect.x, rect.y, rect.x1, rect.y1) * POINTS_PER_INCH
        page.insert_image(r, stream=_png(image), keep_proportion=False)


def _new_doc(opts: BookOptions) -> pymupdf.Document:
    doc = pymupdf.open()
    doc.set_metadata({"title": opts.title, "author": opts.author, "creator": "coloringbook"})
    return doc


def build_interior(prepared: list[PreparedImage], opts: BookOptions, out_path) -> InteriorInfo:
    """KDP paperback interior: trim size (+bleed), mirrored inside margins, optional blank backs."""
    pages = pad_to_even(page_sequence(opts, len(prepared)))
    trim_w, trim_h = opts.trim_size
    bleed = KDP_BLEED if opts.bleed else 0.0
    page_size = (trim_w + bleed, trim_h + 2 * bleed)
    gutter = kdp_gutter(len(pages))
    inside = max(opts.margin, gutter)
    info = InteriorInfo(len(pages), gutter, page_size)

    doc = _new_doc(opts)
    for number, page in enumerate(pages, start=1):
        recto = number % 2 == 1  # right-hand page: binding on the left
        # With bleed, the extra 0.125" is on the outside edge only (not at the spine).
        trim_x = 0.0 if recto else bleed
        left = inside if recto else opts.margin
        right = opts.margin if recto else inside
        box = Rect(trim_x + left, bleed + opts.margin, trim_w - left - right, trim_h - 2 * opts.margin)
        elements = render_elements(page, box, prepared, opts, upscale=opts.upscale_to_print_dpi)
        for _, _, native in elements:
            if native is not None:
                info.native_dpi[prepared[page.art_index].name] = native
        _add_page(doc, page_size, elements)
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return info


def build_home_print(prepared: list[PreparedImage], opts: BookOptions, out_path, margin: float = 0.4) -> int:
    """Simple PDF for a home printer: one picture per page, uniform margins, no blank pages."""
    size = HOME_PAPER[opts.home_paper]
    box = Rect(margin, margin, size[0] - 2 * margin, size[1] - 2 * margin)
    doc = _new_doc(opts)
    for i in range(len(prepared)):
        _add_page(doc, size, render_elements(Page("art", i), box, prepared, opts, upscale=opts.upscale_to_print_dpi))
    count = doc.page_count
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return count
