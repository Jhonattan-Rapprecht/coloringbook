"""Geometry: fitting artwork inside a box without ever cropping it."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .config import PRINT_DPI


@dataclass(frozen=True)
class Rect:
    """Rectangle in inches, origin top-left."""
    x: float
    y: float
    w: float
    h: float

    @property
    def x1(self) -> float:
        return self.x + self.w

    @property
    def y1(self) -> float:
        return self.y + self.h

    def inset(self, d: float) -> "Rect":
        return Rect(self.x + d, self.y + d, self.w - 2 * d, self.h - 2 * d)


@dataclass(frozen=True)
class Placement:
    rect: Rect            # where the artwork goes, in inches
    rotate: bool          # rotate the artwork 90 degrees to make it bigger
    native_dpi: float     # resolution the original pixels print at


def fit(image_size: tuple[int, int], box: Rect, auto_rotate: bool = True) -> Placement:
    """Largest placement of the image inside ``box`` keeping the aspect ratio ("contain")."""
    iw, ih = image_size
    scale = min(box.w / iw, box.h / ih)
    rotate = False
    if auto_rotate:
        rotated_scale = min(box.w / ih, box.h / iw)
        if rotated_scale > scale * 1.05:
            scale, rotate, (iw, ih) = rotated_scale, True, (ih, iw)
    w, h = iw * scale, ih * scale
    rect = Rect(box.x + (box.w - w) / 2, box.y + (box.h - h) / 2, w, h)
    return Placement(rect, rotate, 1 / scale)


def render_art(image: Image.Image, placement: Placement, upscale: bool, dpi: int = PRINT_DPI) -> Image.Image:
    """Rotate and resample the artwork to the exact pixel size needed at ``dpi``."""
    if placement.rotate:
        image = image.rotate(90, expand=True)  # counter-clockwise
    target = (max(1, round(placement.rect.w * dpi)), max(1, round(placement.rect.h * dpi)))
    if target[0] < image.width or upscale:
        image = image.resize(target, Image.LANCZOS)
    return image
