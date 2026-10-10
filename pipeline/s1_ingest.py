"""Stage 1 - classify the file, render it, guess the customer template. Code only.

classify() is the skill's inspect_pdf.py. The template guess comes from text and
file-name patterns in config/customers.json, so it is the same every run and two
readers can be checked against it instead of against each other.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pymupdf
from PIL import Image

from . import CONFIG


def classify(path: str | Path) -> dict:
    doc = pymupdf.open(path)
    page = doc[0]
    text = page.get_text()
    chars = len(text.strip())
    paths = len(page.get_drawings())
    raster = []
    for im in page.get_images(full=True):
        try:
            info = doc.extract_image(im[0])
            raster.append({"w": info["width"], "h": info["height"], "ext": info["ext"],
                           "dpi_approx": round(info["width"] / (page.rect.width / 72))})
        except Exception:
            pass

    big = [r for r in raster if r["w"] > 1200]
    if chars > 40 and paths > 20:
        verdict = "VECTOR"
    elif chars < 20 and big:
        verdict = "SCAN"
    elif chars > 40 and big:
        verdict = "MIXED"
    else:
        verdict = "UNKNOWN"
    rot_hint = None
    if verdict == "SCAN" and page.rect.height > page.rect.width:
        rot_hint = "page is portrait; scanned frame drawings are usually rotated 90 deg"
    return {"file": Path(path).name, "pages": len(doc),
            "page_pt": [round(page.rect.width), round(page.rect.height)],
            "page_rotation": page.rotation, "text_chars": chars, "vector_paths": paths,
            "raster_images": raster, "verdict": verdict, "rotation_hint": rot_hint,
            "text": text}


def load_customers(path: Path | None = None) -> dict:
    with open(path or CONFIG / "customers.json", encoding="utf-8") as f:
        return json.load(f)["templates"]


def detect_template(text: str, filename: str, templates: dict | None = None) -> dict:
    """Return {"template": name|None, "hits": {...}}. Ties or no hits -> None (human picks)."""
    templates = templates or load_customers()
    scores = {}
    for name, rule in templates.items():
        hits = [p for p in rule.get("text_patterns", []) if re.search(p, text)]
        hits += [f"file:{p}" for p in rule.get("filename_patterns", []) if re.search(p, filename)]
        if len(hits) >= rule.get("min_hits", 1):
            scores[name] = hits
    if len(scores) == 1:
        name = next(iter(scores))
        return {"template": name, "hits": scores}
    return {"template": None, "hits": scores}


def render_png(src: str | Path | bytes, scale: float = 2.6, rotate: int = 0) -> bytes:
    doc = pymupdf.open(stream=src, filetype="pdf") if isinstance(src, bytes) else pymupdf.open(src)
    pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale).prerotate(rotate))
    return pix.tobytes("png")


def fit_png(png: bytes, max_px: int = 1600) -> bytes:
    im = Image.open(io.BytesIO(png))
    if max(im.size) > max_px:
        k = max_px / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def tiles(png: bytes, rows: int = 2, cols: int = 2, overlap: float = 0.10,
          max_px: int = 1600) -> list[bytes]:
    """Overlapping tiles (prep_scan.py logic) so small callout text stays readable."""
    im = Image.open(io.BytesIO(png))
    W, H = im.size
    tw, th = W / cols, H / rows
    ox, oy = tw * overlap, th * overlap
    out = []
    for r in range(rows):
        for c in range(cols):
            box = (max(0, int(c * tw - ox)), max(0, int(r * th - oy)),
                   min(W, int((c + 1) * tw + ox)), min(H, int((r + 1) * th + oy)))
            buf = io.BytesIO()
            im.crop(box).save(buf, "PNG")
            out.append(fit_png(buf.getvalue(), max_px))
    return out


def ingest(path: str | Path) -> dict:
    info = classify(path)
    info["template_guess"] = detect_template(info["text"], Path(path).name)
    return info
