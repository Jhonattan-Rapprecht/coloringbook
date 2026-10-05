import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

from coloringbook import BookOptions, build_book
from coloringbook.config import KDP_BLEED, kdp_gutter, spine_width
from coloringbook.images import load_sources, prepare
from coloringbook.interior import page_sequence
from coloringbook.layout import Rect, fit

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def make_art(path: Path, size=(1200, 800), border=40) -> Path:
    """Line drawing whose outermost black frame touches the artwork edges, so any crop is detectable."""
    im = Image.new("RGB", (size[0] + 2 * border, size[1] + 2 * border), "white")
    d = ImageDraw.Draw(im)
    d.rectangle((border, border, border + size[0] - 1, border + size[1] - 1), outline="black", width=6)
    d.ellipse((border + 100, border + 100, border + size[0] - 100, border + size[1] - 100), outline="black", width=6)
    im.save(path)
    return path


@pytest.mark.parametrize("img", [(1200, 800), (800, 1200), (1000, 1000), (3000, 500)])
@pytest.mark.parametrize("rotate", [True, False])
def test_fit_never_crops_and_keeps_aspect(img, rotate):
    box = Rect(0.5, 0.5, 7.5, 10)
    p = fit(img, box, rotate)
    assert p.rect.x >= box.x - 1e-9 and p.rect.y >= box.y - 1e-9
    assert p.rect.x1 <= box.x1 + 1e-9 and p.rect.y1 <= box.y1 + 1e-9
    iw, ih = (img[1], img[0]) if p.rotate else img
    assert p.rect.w / p.rect.h == pytest.approx(iw / ih)
    assert p.rect.w == pytest.approx(box.w) or p.rect.h == pytest.approx(box.h)  # as big as possible


def test_landscape_is_rotated_on_portrait_page():
    assert fit((1600, 900), Rect(0, 0, 7.5, 10)).rotate
    assert not fit((900, 1600), Rect(0, 0, 7.5, 10)).rotate
    assert not fit((1600, 900), Rect(0, 0, 7.5, 10), auto_rotate=False).rotate


def test_kdp_tables():
    assert kdp_gutter(24) == 0.375
    assert kdp_gutter(151) == 0.5
    assert kdp_gutter(828) == 0.875
    assert spine_width(100, "white") == pytest.approx(0.2252)


def test_page_sequence_blank_backs():
    seq = page_sequence(BookOptions(), 2)
    assert [p.kind for p in seq] == ["title", "blank", "belongs", "blank", "art", "blank", "art"]
    seq = page_sequence(BookOptions(title_page=False, belongs_to_page=False, blank_backs=False), 3)
    assert [p.kind for p in seq] == ["art"] * 3


def test_auto_trim_removes_whitespace(tmp_path):
    src = load_sources([make_art(tmp_path / "a.png", (1000, 600), border=300)])[0]
    prepared = prepare(src)
    assert prepared.lineart.width < 1100 and prepared.lineart.height < 700
    assert prepared.lineart.mode == "L" and prepared.color.size == prepared.lineart.size


def _image_rects(page):
    return [page.get_image_rects(x[0])[0] for x in page.get_images(full=True)]


@pytest.mark.parametrize("bleed", [False, True])
def test_full_build_is_kdp_compliant(tmp_path, bleed):
    files = [make_art(tmp_path / f"{i:02d}.png", (2400, 1600) if i % 2 else (1600, 2400)) for i in range(12)]
    opts = BookOptions(title="Test Book", author="Me", bleed=bleed, margin=0.5)
    result = build_book(files, tmp_path / "out", opts)

    assert result.page_count == 28 and result.page_count % 2 == 0
    assert not [w for w in result.warnings if "at least 24 pages" in w]

    interior = pymupdf.open(result.files["Paperback interior (KDP)"])
    b = KDP_BLEED if bleed else 0
    inside = max(opts.margin, kdp_gutter(result.page_count))
    for number, page in enumerate(interior, start=1):
        assert page.rect.width / 72 == pytest.approx(8.5 + b)
        assert page.rect.height / 72 == pytest.approx(11 + 2 * b)
        assert not page.get_fonts(), "fonts must not be needed (KDP requires embedded fonts)"
        recto = number % 2 == 1
        trim_left = 0 if recto else b
        safe = Rect(trim_left + (inside if recto else opts.margin), b + opts.margin,
                    8.5 - inside - opts.margin, 11 - 2 * opts.margin)
        for r in _image_rects(page):
            r = r / 72
            assert r.x0 >= safe.x - 1e-3 and r.x1 <= safe.x1 + 1e-3
            assert r.y0 >= safe.y - 1e-3 and r.y1 <= safe.y1 + 1e-3
        for info in page.get_images(full=True):
            width_px = info[2]
            rect = page.get_image_rects(info[0])[0]
            assert width_px / (rect.width / 72) >= 299  # 300 DPI

    cover = pymupdf.open(result.files["Paperback cover (KDP)"])[0]
    expected_w = 2 * 0.125 + 2 * 8.5 + spine_width(result.page_count, "white")
    assert cover.rect.width / 72 == pytest.approx(expected_w, abs=1e-3)
    assert cover.rect.height / 72 == pytest.approx(11.25)

    home = pymupdf.open(result.files["Print at home (Letter)"])
    assert home.page_count == 12

    with Image.open(result.files["Kindle eBook cover (1600x2560 JPG)"]) as im:
        assert im.size == (1600, 2560)
    assert result.files["Build report"].read_text(encoding="utf-8").startswith("COLORING BOOK BUILD REPORT")


def test_artwork_is_not_cropped_in_pdf(tmp_path):
    """Render the printed page and check the art's outer frame is fully present on all four sides."""
    src = make_art(tmp_path / "wide.png", (2000, 1000))
    result = build_book([src], tmp_path / "out", BookOptions(title_page=False, belongs_to_page=False,
                                                             make_cover=False, make_ebook=False))
    page = pymupdf.open(result.files["Print at home (Letter)"])[0]
    rect = _image_rects(page)[0]
    pix = page.get_pixmap(dpi=100, clip=rect, colorspace=pymupdf.csGRAY)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    w, h = im.size
    inset = 8
    for x, y in [(w // 2, inset), (w // 2, h - inset), (inset, h // 2), (w - inset, h // 2)]:
        column_or_row = [im.getpixel((x, yy)) for yy in range(max(0, y - inset), min(h, y + inset))] if x == w // 2 \
            else [im.getpixel((xx, y)) for xx in range(max(0, x - inset), min(w, x + inset))]
        assert min(column_or_row) < 100, f"frame missing near ({x},{y}) - artwork was cut off"


def test_epub_structure(tmp_path):
    files = [make_art(tmp_path / f"{i}.png") for i in range(3)]
    result = build_book(files, tmp_path / "out", BookOptions(title="E & B <Book>", make_cover=False,
                                                             make_home_print=False))
    with zipfile.ZipFile(result.files["Kindle eBook (fixed-layout EPUB)"]) as zf:
        first = zf.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"
        opf = ET.fromstring(zf.read("OEBPS/content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        metas = {m.get("property"): m.text for m in opf.iterfind(".//opf:meta[@property]", ns)}
        assert metas["rendition:layout"] == "pre-paginated"
        hrefs = [i.get("href") for i in opf.iterfind(".//opf:item", ns)]
        for href in hrefs:
            zf.getinfo(f"OEBPS/{href}")
        for name in zf.namelist():
            if name.endswith((".xhtml", ".ncx", ".opf", ".xml")):
                ET.fromstring(zf.read(name))  # well-formed XML
        spine = opf.findall(".//opf:itemref", ns)
        assert len(spine) == 1 + 2 + 3  # cover + title + belongs + 3 pictures


@pytest.mark.skipif(not (ASSETS / "2 - Girls" / "Pony-1.pdf").exists(), reason="sample assets not present")
def test_pdf_input_extracts_native_image():
    src = load_sources([ASSETS / "2 - Girls" / "Pony-1.pdf"])
    assert len(src) == 1 and src[0].image.size == (1024, 1536)


def test_web_upload(tmp_path, monkeypatch):
    import app as webapp
    monkeypatch.setattr(webapp, "JOBS", tmp_path / "jobs")
    client = webapp.app.test_client()
    assert client.get("/").status_code == 200

    buf = io.BytesIO()
    Image.open(make_art(tmp_path / "x.png")).save(buf, "PNG")
    form = {"title": "Web Book", "trim": "8.5x11", "paper": "white", "margin": "0.5", "home_paper": "a4",
            "cover_image": "1", "cover_color": "#ffffff", "blank_backs": "on", "make_cover": "on",
            "make_home_print": "on", "images": (io.BytesIO(buf.getvalue()), "x.png")}
    resp = client.post("/build", data=form, content_type="multipart/form-data")
    assert resp.status_code == 200, resp.data
    html = resp.get_data(as_text=True)
    assert "Your book is ready" in html and "at least 24 pages" in html
    job = next((tmp_path / "jobs").iterdir()).name
    assert client.get(f"/download/{job}/web-book-interior.pdf").status_code == 200
    assert client.get(f"/download/{job}/web-book-print-at-home-a4.pdf").status_code == 200
    assert client.get(f"/download/{job}.zip").status_code == 200
    assert client.get("/download/../../etc/passwd").status_code == 404
    assert client.get(f"/download/{job}/..%2F..%2Fapp.py").status_code == 404
