"""Command line: python -m coloringbook <images or folders...> --title "..." --out output/"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .builder import build_book
from .config import HOME_PAPER, TRIM_SIZES, BookOptions
from .images import SUPPORTED_EXTENSIONS, list_supported


def collect(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            paths.extend(list_supported(p))
        elif p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            paths.append(p)
        else:
            raise SystemExit(f"Not a supported image, PDF or folder: {item}")
    return paths


def main(argv: list[str] | None = None) -> int:
    d = BookOptions()
    ap = argparse.ArgumentParser(prog="coloringbook", description="Build a KDP-ready coloring book from images.")
    ap.add_argument("inputs", nargs="+", help="image/PDF files or folders (folders are sorted by name)")
    ap.add_argument("-o", "--out", default="output", help="output folder (default: output)")
    ap.add_argument("--title", default=d.title)
    ap.add_argument("--subtitle", default=d.subtitle)
    ap.add_argument("--author", default=d.author)
    ap.add_argument("--trim", default=d.trim, choices=list(TRIM_SIZES))
    ap.add_argument("--paper", default=d.paper, choices=["white", "cream"])
    ap.add_argument("--margin", type=float, default=d.margin, help="outside margin in inches")
    ap.add_argument("--bleed", action="store_true", help="add 0.125in bleed (not needed for white-border pages)")
    ap.add_argument("--double-sided", action="store_true", help="print on both sides (no blank backs)")
    ap.add_argument("--no-title-page", action="store_true")
    ap.add_argument("--no-belongs-page", action="store_true")
    ap.add_argument("--no-rotate", action="store_true", help="never rotate landscape pictures")
    ap.add_argument("--no-trim", action="store_true", help="keep white borders around pictures")
    ap.add_argument("--no-clean", action="store_true", help="keep original grays (no line-art cleanup)")
    ap.add_argument("--no-upscale", action="store_true")
    ap.add_argument("--cover-image", type=int, default=1, help="1-based index of picture used on the cover")
    ap.add_argument("--cover-color", default=d.cover_color, help="cover background, e.g. '#FFE066'")
    ap.add_argument("--home-paper", default=d.home_paper, choices=list(HOME_PAPER))
    ap.add_argument("--no-cover", action="store_true")
    ap.add_argument("--no-ebook", action="store_true")
    ap.add_argument("--no-home-print", action="store_true")
    args = ap.parse_args(argv)

    opts = BookOptions(
        title=args.title, subtitle=args.subtitle, author=args.author, trim=args.trim, paper=args.paper,
        margin=args.margin, bleed=args.bleed, blank_backs=not args.double_sided,
        title_page=not args.no_title_page, belongs_to_page=not args.no_belongs_page,
        auto_rotate=not args.no_rotate, auto_trim=not args.no_trim, clean_lineart=not args.no_clean,
        upscale_to_print_dpi=not args.no_upscale, cover_image_index=args.cover_image - 1,
        cover_color=args.cover_color, home_paper=args.home_paper, make_cover=not args.no_cover,
        make_ebook=not args.no_ebook, make_home_print=not args.no_home_print,
    )
    paths = collect(args.inputs)
    try:
        result = build_book(paths, Path(args.out), opts, progress=lambda m: print(f"... {m}", file=sys.stderr))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    print(result.report)
    print(f"Output folder: {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
