"""Loading source files (images and PDFs) and preparing them for printing."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from .config import PRINT_DPI

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS

WHITE_THRESHOLD = 235  # pixels lighter than this count as "paper"

Image.MAX_IMAGE_PIXELS = 300_000_000


@dataclass
class SourceImage:
    name: str
    image: Image.Image  # RGB, original colors


@dataclass
class PreparedImage:
    name: str
    lineart: Image.Image  # "L" mode, ready for the B&W interior
    color: Image.Image    # "RGB" mode, same crop, used for covers


def list_supported(folder: Path) -> list[Path]:
    """Supported files in a folder, sorted naturally by name (2 before 10)."""
    import re

    def natural_key(p: Path):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]

    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=natural_key,
    )


def load_sources(paths: list[Path]) -> list[SourceImage]:
    sources: list[SourceImage] = []
    for path in paths:
        suffix = path.suffix.lower()
        if suffix in PDF_EXTENSIONS:
            sources.extend(_load_pdf(path))
        elif suffix in IMAGE_EXTENSIONS:
            sources.append(SourceImage(path.stem, _to_rgb(_open_image(path))))
        else:
            raise ValueError(f"Unsupported file type: {path.name}")
    return sources


def _open_image(path: Path) -> Image.Image:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        return im.copy()


def _to_rgb(im: Image.Image) -> Image.Image:
    """Flatten transparency onto white paper and convert to RGB."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        background = Image.new("RGBA", im.size, (255, 255, 255, 255))
        background.alpha_composite(im)
        return background.convert("RGB")
    return im.convert("RGB")


def _load_pdf(path: Path) -> list[SourceImage]:
    """Each PDF page becomes one picture.

    If a page is just a single embedded picture (typical for "Print to PDF" of an image),
    the picture is extracted at its native resolution. Otherwise the page is rendered at 300 DPI.
    """
    results: list[SourceImage] = []
    with pymupdf.open(path) as doc:
        for page_index, page in enumerate(doc):
            name = f"{path.stem}-p{page_index + 1}" if doc.page_count > 1 else path.stem
            image = _extract_single_image(doc, page)
            if image is None:
                pix = page.get_pixmap(dpi=PRINT_DPI, alpha=False, colorspace=pymupdf.csRGB)
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            results.append(SourceImage(name, image))
    return results


def _extract_single_image(doc: pymupdf.Document, page: pymupdf.Page) -> Image.Image | None:
    images = page.get_images(full=True)
    if len(images) != 1 or page.get_text().strip() or not _only_white_fills(page):
        return None
    xref = images[0][0]
    rects = page.get_image_rects(xref, transform=True)
    if len(rects) != 1:
        return None
    rect, matrix = rects[0]
    if abs(matrix.b) > 1e-6 or abs(matrix.c) > 1e-6 or matrix.a < 0 or matrix.d < 0:
        return None  # rotated or mirrored placement: let the renderer handle it
    try:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace is None or pix.colorspace.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        image.load()
    except Exception:
        return None
    return _to_rgb(image)


def _only_white_fills(page: pymupdf.Page) -> bool:
    """True if the page has no vector art other than white backgrounds (as "Print to PDF" adds)."""
    for d in page.get_drawings():
        if d.get("color") is not None:
            return False
        fill = d.get("fill")
        if fill is not None and min(fill) < 0.98:
            return False
    return True


def prepare(source: SourceImage, auto_trim: bool = True, clean_lineart: bool = True) -> PreparedImage:
    color = source.image
    gray = color.convert("L")
    if clean_lineart:
        gray = gray.point(_lineart_curve())
    if auto_trim:
        box = content_bbox(gray)
        if box is not None:
            gray = gray.crop(box)
            color = color.crop(box)
    return PreparedImage(source.name, gray, color)


def _lineart_curve() -> list[int]:
    """Levels adjustment: near-white -> pure white, dark gray -> black, keeps anti-aliasing."""
    low, high = 40, 225
    lut = []
    for v in range(256):
        if v <= low:
            lut.append(0)
        elif v >= high:
            lut.append(255)
        else:
            lut.append(round((v - low) * 255 / (high - low)))
    return lut


def content_bbox(gray: Image.Image, padding_ratio: float = 0.01) -> tuple[int, int, int, int] | None:
    """Bounding box of the non-white artwork, with a little breathing room."""
    mask = gray.point(lambda v: 255 if v < WHITE_THRESHOLD else 0)
    box = mask.getbbox()
    if box is None:
        return None
    pad = round(max(gray.size) * padding_ratio)
    x0, y0, x1, y1 = box
    return (max(0, x0 - pad), max(0, y0 - pad), min(gray.width, x1 + pad), min(gray.height, y1 + pad))
