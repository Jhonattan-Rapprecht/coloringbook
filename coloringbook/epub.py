"""Fixed-layout (pre-paginated) EPUB 3 for Kindle. Each page is one full-page image."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone
from html import escape

from PIL import Image

from .config import BookOptions
from .cover import build_ebook_cover
from .images import PreparedImage
from .interior import page_sequence, render_elements
from .layout import Rect

EBOOK_PAGE_WIDTH = 1600


def ebook_page_size(opts: BookOptions) -> tuple[int, int]:
    trim_w, trim_h = opts.trim_size
    return EBOOK_PAGE_WIDTH, round(EBOOK_PAGE_WIDTH * trim_h / trim_w)


def render_ebook_pages(prepared: list[PreparedImage], opts: BookOptions) -> list[Image.Image]:
    w, h = ebook_page_size(opts)
    trim_w, trim_h = opts.trim_size
    dpi = w / trim_w
    margin = 0.3
    box = Rect(margin, margin, trim_w - 2 * margin, trim_h - 2 * margin)
    pages = []
    for page in page_sequence(opts, len(prepared), blank_backs=False):
        canvas = Image.new("L", (w, h), 255)
        for rect, image, _ in render_elements(page, box, prepared, opts, dpi=round(dpi), upscale=True):
            image = image.resize((round(rect.w * dpi), round(rect.h * dpi)), Image.LANCZOS)
            canvas.paste(image, (round(rect.x * dpi), round(rect.y * dpi)))
        pages.append(canvas)
    return pages


def _jpeg(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def build_epub(prepared: list[PreparedImage], opts: BookOptions, out_path, cover_jpg_path=None) -> int:
    w, h = ebook_page_size(opts)
    cover = build_ebook_cover(prepared, opts)
    if cover_jpg_path:
        cover.save(cover_jpg_path, "JPEG", quality=95)
    pages = render_ebook_pages(prepared, opts)
    book_id = f"urn:uuid:{uuid.uuid4()}"
    title, author, lang = escape(opts.title), escape(opts.author or "Unknown"), escape(opts.language)
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def xhtml(page_title: str, img_href: str, pw: int, ph: int) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">
<head>
<meta charset="UTF-8"/>
<title>{escape(page_title)}</title>
<meta name="viewport" content="width={pw}, height={ph}"/>
<link rel="stylesheet" type="text/css" href="../css/style.css"/>
</head>
<body style="width:{pw}px;height:{ph}px;">
<div class="page"><img src="{img_href}" alt="{escape(page_title)}" style="width:{pw}px;height:{ph}px;"/></div>
</body>
</html>
"""

    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="css" href="css/style.css" media-type="text/css"/>',
                '<item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>',
                '<item id="cover-page" href="xhtml/cover.xhtml" media-type="application/xhtml+xml"/>']
    spine = ['<itemref idref="cover-page" linear="yes"/>']
    files: dict[str, bytes] = {
        "OEBPS/images/cover.jpg": _jpeg(cover),
        "OEBPS/xhtml/cover.xhtml": xhtml("Cover", "../images/cover.jpg", *cover.size).encode(),
    }
    for i, page in enumerate(pages, start=1):
        name = f"page-{i:03d}"
        files[f"OEBPS/images/{name}.jpg"] = _jpeg(page)
        files[f"OEBPS/xhtml/{name}.xhtml"] = xhtml(f"Page {i}", f"../images/{name}.jpg", w, h).encode()
        manifest.append(f'<item id="img-{name}" href="images/{name}.jpg" media-type="image/jpeg"/>')
        manifest.append(f'<item id="{name}" href="xhtml/{name}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{name}"/>')

    first_page = "xhtml/page-001.xhtml" if pages else "xhtml/cover.xhtml"
    files["OEBPS/content.opf"] = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}"
         prefix="rendition: http://www.idpf.org/vocab/rendition/#">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{book_id}</dc:identifier>
<dc:title>{title}</dc:title>
<dc:creator>{author}</dc:creator>
<dc:language>{lang}</dc:language>
<meta property="dcterms:modified">{modified}</meta>
<meta property="rendition:layout">pre-paginated</meta>
<meta property="rendition:orientation">portrait</meta>
<meta property="rendition:spread">none</meta>
<meta name="cover" content="cover-image"/>
<meta name="fixed-layout" content="true"/>
<meta name="original-resolution" content="{w}x{h}"/>
<meta name="book-type" content="children"/>
<meta name="orientation-lock" content="portrait"/>
<meta name="region-mag" content="false"/>
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine toc="ncx">
{chr(10).join(spine)}
</spine>
</package>
""".encode()
    files["OEBPS/nav.xhtml"] = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">
<head><meta charset="UTF-8"/><title>{title}</title></head>
<body>
<nav epub:type="toc" id="toc"><ol><li><a href="{first_page}">{title}</a></li></ol></nav>
<nav epub:type="landmarks" hidden=""><ol>
<li><a epub:type="cover" href="xhtml/cover.xhtml">Cover</a></li>
<li><a epub:type="bodymatter" href="{first_page}">Start</a></li>
</ol></nav>
</body>
</html>
""".encode()
    files["OEBPS/toc.ncx"] = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{book_id}"/></head>
<docTitle><text>{title}</text></docTitle>
<navMap><navPoint id="start" playOrder="1"><navLabel><text>{title}</text></navLabel>
<content src="{first_page}"/></navPoint></navMap>
</ncx>
""".encode()
    files["OEBPS/css/style.css"] = b"html, body { margin: 0; padding: 0; }\n.page { position: relative; }\n" \
                                   b"img { position: absolute; top: 0; left: 0; display: block; }\n"
    files["META-INF/container.xml"] = b"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

    with zipfile.ZipFile(out_path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    return len(pages)
