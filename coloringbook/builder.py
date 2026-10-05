"""High level entry point: sources in, complete coloring book package out."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import (KDP_MAX_PAGES, KDP_MIN_PAGES, KDP_SPINE_TEXT_MIN_PAGES, PRINT_DPI, BookOptions)
from .cover import build_paperback_cover
from .epub import build_epub
from .images import load_sources, prepare
from .interior import build_home_print, build_interior

LOW_DPI_WARNING = 200  # below this, upscaled line art starts to look soft in print


@dataclass
class BuildResult:
    files: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    page_count: int = 0
    image_count: int = 0

    @property
    def report(self) -> str:
        lines = ["COLORING BOOK BUILD REPORT", "=" * 26, ""]
        lines += [f"Pictures: {self.image_count}", f"Paperback interior pages: {self.page_count}", ""]
        lines += ["Files:"] + [f"  {label}: {path.name}" for label, path in self.files.items()] + [""]
        lines += ["Notes:"] + [f"  - {n}" for n in self.notes] + [""]
        lines += ["Warnings:"] + ([f"  ! {w}" for w in self.warnings] or ["  none - ready for KDP upload"])
        return "\n".join(lines) + "\n"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "coloring-book"


def build_book(paths: list[Path], out_dir: Path, opts: BookOptions, progress=None) -> BuildResult:
    opts.validate()
    say = progress or (lambda msg: None)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = BuildResult()
    slug = slugify(opts.title)

    say("Loading images")
    sources = load_sources([Path(p) for p in paths])
    if not sources:
        raise ValueError("No images found. Supported: PNG, JPG, WEBP, BMP, GIF, TIFF and PDF.")
    say(f"Preparing {len(sources)} pictures")
    prepared = [prepare(s, opts.auto_trim, opts.clean_lineart) for s in sources]
    result.image_count = len(prepared)

    say("Building paperback interior")
    interior_path = out_dir / f"{slug}-interior.pdf"
    info = build_interior(prepared, opts, interior_path)
    result.files["Paperback interior (KDP)"] = interior_path
    result.page_count = info.page_count
    trim_w, trim_h = opts.trim_size
    result.notes.append(
        f"KDP setup: trim {trim_w}\" x {trim_h}\", {'bleed' if opts.bleed else 'no bleed'}, "
        f"black & white interior, {opts.paper} paper. PDF page size {info.page_size[0]}\" x {info.page_size[1]}\".")
    result.notes.append(f"Margins: {opts.margin}\" outside/top/bottom, "
                        f"{max(opts.margin, info.gutter)}\" inside (KDP gutter minimum {info.gutter}\").")
    if opts.blank_backs:
        result.notes.append("Every picture is on its own sheet (blank back) so markers don't bleed through.")

    if info.page_count < KDP_MIN_PAGES:
        missing = KDP_MIN_PAGES - info.page_count
        per_image = 2 if opts.blank_backs else 1
        result.warnings.append(
            f"KDP paperbacks need at least {KDP_MIN_PAGES} pages; this book has {info.page_count}. "
            f"Add about {-(-missing // per_image)} more picture(s).")
    if info.page_count > KDP_MAX_PAGES:
        result.warnings.append(f"KDP paperbacks allow at most {KDP_MAX_PAGES} pages; this book has {info.page_count}.")

    for name, dpi in info.native_dpi.items():
        if dpi < LOW_DPI_WARNING:
            action = "upscaled to 300 DPI" if opts.upscale_to_print_dpi else "left as is"
            result.warnings.append(
                f"'{name}' is low resolution ({dpi:.0f} DPI at print size, {action}); lines may look soft. "
                f"Use an image of at least {PRINT_DPI} DPI at print size if you have one.")

    if opts.make_cover:
        say("Building paperback cover")
        cover_path = out_dir / f"{slug}-cover.pdf"
        cover = build_paperback_cover(prepared, opts, info.page_count, cover_path)
        result.files["Paperback cover (KDP)"] = cover_path
        result.notes.append(f"Cover: {cover.width:.3f}\" x {cover.height:.3f}\" incl. bleed, "
                            f"spine {cover.spine:.3f}\". Barcode area on the back cover kept free.")
        if not cover.spine_text:
            result.notes.append(f"No spine text (KDP only allows it from {KDP_SPINE_TEXT_MIN_PAGES} pages).")

    if opts.make_ebook:
        say("Building Kindle eBook")
        epub_path = out_dir / f"{slug}-kindle.epub"
        cover_jpg = out_dir / f"{slug}-kindle-cover.jpg"
        build_epub(prepared, opts, epub_path, cover_jpg)
        result.files["Kindle eBook (fixed-layout EPUB)"] = epub_path
        result.files["Kindle eBook cover (1600x2560 JPG)"] = cover_jpg

    if opts.make_home_print:
        say("Building home-print PDF")
        home_path = out_dir / f"{slug}-print-at-home-{opts.home_paper}.pdf"
        build_home_print(prepared, opts, home_path)
        result.files[f"Print at home ({opts.home_paper.title()})"] = home_path

    report_path = out_dir / f"{slug}-report.txt"
    result.files["Build report"] = report_path
    report_path.write_text(result.report, encoding="utf-8")
    say("Done")
    return result
