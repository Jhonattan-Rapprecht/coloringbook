# Coloring Book Maker

Turn a folder of pictures (PNG, JPG, WEBP, TIFF… or PDFs) into a complete, print-ready coloring book:

| Output | Use it for |
|---|---|
| `*-interior.pdf` | **KDP paperback** manuscript (upload as the interior) |
| `*-cover.pdf` | **KDP paperback** full wraparound cover (back + spine + front, with bleed) |
| `*-kindle.epub` | **Kindle eBook** (fixed-layout EPUB, one picture per screen) |
| `*-kindle-cover.jpg` | Kindle eBook cover (1600 × 2560 px) |
| `*-print-at-home-letter.pdf` / `-a4.pdf` | Printing on your own printer, one picture per page |
| `*-report.txt` | Preflight report: page count, margins, spine width, low-resolution warnings |

## Why pictures are never cut off

"Print to PDF" usually *fills* the page and crops the edges (or the printer's hardware margin clips them).
This tool does the opposite: every picture is scaled to **fit inside** the printable safe area while keeping its
aspect ratio ("contain"), then centered. On top of that it:

- **Auto-rotates** landscape pictures onto portrait pages when that makes them bigger.
- **Trims empty white borders** so the drawing itself uses as much of the page as possible.
- **Cleans line art**: grayscale, pure-white paper, crisp black lines (KDP black & white interior).
- **Resamples to 300 DPI** (KDP's recommended print resolution) and warns when a source is low-resolution.
- Keeps KDP's **margins and gutter** (inside margin grows with page count) and mirrors them on left/right pages.
- Puts every picture on its **own sheet with a blank back**, so markers don't bleed through to the next picture.
- Renders all text as images, so the PDFs contain **no un-embedded fonts** (a common KDP rejection reason).
- PDFs that are just one embedded picture (e.g. from "Print to PDF") are unpacked at their native resolution.

## Install

```powershell
pip install -r requirements.txt
```

## Web app

```powershell
python app.py
```

Open <http://127.0.0.1:5000>, drop your pictures, drag thumbnails to set the page order, click ★ on the picture
to use on the cover, fill in title/author, and click **Build**.

## Command line (feed a whole folder)

```powershell
python -m coloringbook "assets\2 - Girls" --title "Unicorns & Dinos" --subtitle "For Kids Ages 4-8" `
    --author "Your Name" --cover-color "#FFE066" -o output\unicorns
```

Folders are sorted naturally by file name (`2.png` before `10.png`), so name files to control the order.
Run `python -m coloringbook --help` for all options (trim size, paper, margin, bleed, double-sided, …).

## Publishing on Amazon KDP

**Paperback**
1. Interior: *Black & white interior*, *White* (or *Cream*, matching `--paper`) paper, the trim size you chose
   (default 8.5" × 11"), **No bleed** (unless you used `--bleed`). Upload `*-interior.pdf`.
2. Cover: choose *Upload a cover you already have* and upload `*-cover.pdf`. The spine width is calculated from
   the page count and paper, so **rebuild the cover whenever you add/remove pictures**.
3. KDP needs **at least 24 pages**. With blank backs, each picture uses 2 pages (≈ 10+ pictures minimum);
   most coloring books have 25–50 pictures. Spine text is added automatically from 79 pages.

**Kindle eBook**
- Upload `*-kindle.epub` as the manuscript and `*-kindle-cover.jpg` as the cover. Check it in
  [Kindle Previewer](https://kdp.amazon.com/en_US/help/topic/G202131170) before publishing.
- Kindle readers can't color on screen, so position the eBook as a printable / preview edition, and check KDP's
  current content guidelines for activity books.

## Tips for best quality

- Use images that are at least **2250 × 3000 px** for an 8.5" × 11" page (300 DPI). The report flags anything
  under 200 DPI.
- Black line art on white background works best; colored pictures are converted to grayscale for the interior,
  but the original colors are used on the cover.

## Tests

```powershell
python -m pytest
```
