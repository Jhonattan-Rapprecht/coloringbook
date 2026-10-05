"""Web UI: upload pictures, pick options, download the finished coloring book."""

from __future__ import annotations

import io
import re
import shutil
import uuid
import zipfile
from pathlib import Path

from flask import Flask, abort, render_template, request, send_file
from werkzeug.utils import secure_filename

from coloringbook import TRIM_SIZES, BookOptions, build_book
from coloringbook.config import HOME_PAPER
from coloringbook.images import SUPPORTED_EXTENSIONS

BASE = Path(__file__).parent
JOBS = BASE / "output" / "jobs"
JOB_ID = re.compile(r"^[0-9a-f]{32}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB of uploads


def _flag(name: str) -> bool:
    return request.form.get(name) == "on"


def _options() -> BookOptions:
    f = request.form
    return BookOptions(
        title=f.get("title", "").strip() or "My Coloring Book",
        subtitle=f.get("subtitle", "").strip(),
        author=f.get("author", "").strip(),
        trim=f.get("trim", "8.5x11"),
        paper=f.get("paper", "white"),
        margin=float(f.get("margin", 0.5)),
        bleed=_flag("bleed"),
        blank_backs=_flag("blank_backs"),
        title_page=_flag("title_page"),
        belongs_to_page=_flag("belongs_to_page"),
        auto_rotate=_flag("auto_rotate"),
        auto_trim=_flag("auto_trim"),
        clean_lineart=_flag("clean_lineart"),
        upscale_to_print_dpi=_flag("upscale"),
        cover_image_index=max(0, int(f.get("cover_image", 1)) - 1),
        cover_color=f.get("cover_color", "#FFFFFF"),
        home_paper=f.get("home_paper", "letter"),
        make_cover=_flag("make_cover"),
        make_ebook=_flag("make_ebook"),
        make_home_print=_flag("make_home_print"),
    )


@app.get("/")
def index():
    return render_template("index.html", trims=TRIM_SIZES, home_papers=HOME_PAPER, defaults=BookOptions(),
                           accept=",".join(sorted(SUPPORTED_EXTENSIONS)))


@app.post("/build")
def build():
    files = [f for f in request.files.getlist("images") if f and f.filename]
    if not files:
        return render_template("result.html", error="Please choose at least one image."), 400
    try:
        opts = _options()
        opts.validate()
    except ValueError as e:
        return render_template("result.html", error=str(e)), 400

    job = uuid.uuid4().hex
    upload_dir, out_dir = JOBS / job / "uploads", JOBS / job / "book"
    upload_dir.mkdir(parents=True)
    paths = []
    for i, f in enumerate(files):
        name = secure_filename(f.filename) or f"image-{i}"
        if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        path = upload_dir / f"{i:04d}" / name  # numbered folders keep the browser order and allow duplicate names
        path.parent.mkdir()
        f.save(path)
        paths.append(path)
    try:
        result = build_book(paths, out_dir, opts)
    except Exception as e:  # show a friendly message instead of a 500 page
        shutil.rmtree(JOBS / job, ignore_errors=True)
        return render_template("result.html", error=f"Could not build the book: {e}"), 400
    files_out = {label: p.name for label, p in result.files.items()}
    return render_template("result.html", job=job, result=result, files=files_out)


def _job_dir(job: str) -> Path:
    if not JOB_ID.match(job):
        abort(404)
    path = JOBS / job / "book"
    if not path.is_dir():
        abort(404)
    return path


@app.get("/download/<job>/<name>")
def download(job: str, name: str):
    folder = _job_dir(job)
    path = folder / secure_filename(name)
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=request.args.get("inline") != "1")


@app.get("/download/<job>.zip")
def download_zip(job: str):
    folder = _job_dir(job)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.iterdir()):
            zf.write(p, p.name)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="coloring-book.zip", mimetype="application/zip")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
