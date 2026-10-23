"""Figures at native resolution.

docling's picture crops are page renders at 144 dpi. For each picture docling
found (page and bounding box in its JSON), this takes the image embedded in
the PDF when one matches the picture's place on the page (lossless, often
300 ppi), and otherwise re-renders the bounding box at a chosen resolution.

Figures are named from their captions (``fig-3``, ``fig-S2``, ``ed-4`` for
Extended Data, ``ga`` for a graphical abstract); when docling links a caption
to the wrong picture, the nearest unused "Figure N" text on the page is used.
Logos and cover marks (small, uncaptioned pictures) are skipped, and panels
docling split apart are merged back. Vector and mixed figures also get a
one-page PDF cropped to the figure, so the original vector art is kept.

Needs poppler (``pdfimages``, ``pdftoppm``, ``pdftohtml``, ``pdftocairo``,
``pdfinfo``; e.g. ``pixi global install poppler``).
Output: ``bib/derivatives/figures/<citekey>/`` with ``manifest.yml``
(paper provenance: project-relative PDF, sha256, version, credit, licence;
per figure: ``ref``, kind, art, files with sha256).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import BiblioConfig

FIGURE_RE = re.compile(r"^\s*(?:Figure|Fig\.?)\s*(\d+)", re.IGNORECASE)
# "Figure 3", "Fig. S2", "Supplementary Figure 2", "Extended Data Fig. 4"
CAPTION_RE = re.compile(r"^\s*(?:(Extended\s+Data|Supplementary)\s+)?Fig(?:ure)?\.?\s*(S?\d+)", re.IGNORECASE)
MANIFEST_VERSION = 2


@dataclass
class EmbeddedImage:
    page: int
    num: int
    width: int
    height: int
    enc: str
    x_ppi: float
    y_ppi: float

    @property
    def displayed_pt(self) -> tuple[float, float]:
        return (self.width / self.x_ppi * 72.0, self.height / self.y_ppi * 72.0)


@dataclass
class FigureEntry:
    index: int
    number: int | None
    kind: str                 # "figure" (captioned "Figure N") | "picture"
    caption: str
    page: int
    bbox_pt: dict[str, float]   # top-left origin: x, y, w, h in PDF points
    source: str               # "embedded" | "rendered"
    file: str
    width_px: int
    height_px: int
    ppi: float


def require_poppler() -> None:
    missing = [tool for tool in ("pdfimages", "pdftoppm") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(f"{', '.join(missing)} not found; install poppler (e.g. `pixi global install poppler`)")


def parse_pdfimages_list(text: str) -> list[EmbeddedImage]:
    """Rows of ``pdfimages -list`` that are images (alpha masks and stencils skipped)."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 14 or not parts[0].isdigit():
            continue
        if parts[2] != "image":
            continue
        try:
            out.append(EmbeddedImage(page=int(parts[0]), num=int(parts[1]), width=int(parts[3]),
                                     height=int(parts[4]), enc=parts[8],
                                     x_ppi=float(parts[12]), y_ppi=float(parts[13])))
        except ValueError:
            continue
    return out


def bbox_top_left(prov_bbox: dict[str, Any], page_height: float) -> dict[str, float]:
    """docling bbox (BOTTOMLEFT or TOPLEFT origin) -> top-left x, y, w, h in points."""
    l, r = float(prov_bbox["l"]), float(prov_bbox["r"])
    t, b = float(prov_bbox["t"]), float(prov_bbox["b"])
    if str(prov_bbox.get("coord_origin", "BOTTOMLEFT")).upper() == "BOTTOMLEFT":
        y_top = page_height - t
        h = t - b
    else:
        y_top = t
        h = b - t
    return {"x": l, "y": y_top, "w": r - l, "h": h}


def match_embedded(bbox: dict[str, float], candidates: list[EmbeddedImage], tolerance: float = 0.1) -> EmbeddedImage | None:
    """The embedded image whose displayed size matches the bbox within ``tolerance`` (relative)."""
    best, best_err = None, None
    for img in candidates:
        w, h = img.displayed_pt
        if bbox["w"] <= 0 or bbox["h"] <= 0:
            continue
        err_w = abs(w - bbox["w"]) / bbox["w"]
        err_h = abs(h - bbox["h"]) / bbox["h"]
        if err_w <= tolerance and err_h <= tolerance and (best_err is None or err_w + err_h < best_err):
            best, best_err = img, err_w + err_h
    return best


def pdftoppm_args(pdf: Path, page: int, bbox: dict[str, float], dpi: int, out_prefix: Path) -> list[str]:
    scale = dpi / 72.0
    return [
        "pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi),
        "-x", str(int(round(bbox["x"] * scale))), "-y", str(int(round(bbox["y"] * scale))),
        "-W", str(int(round(bbox["w"] * scale))), "-H", str(int(round(bbox["h"] * scale))),
        "-png", "-singlefile", str(pdf), str(out_prefix),
    ]


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        head = fh.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    return (0, 0)


_LABEL_ONLY = re.compile(r"^\s*(?:(?:Extended\s+Data|Supplementary)\s+)?Fig(?:ure)?\.?\s*S?\d+\s*[.:|]?\s*$", re.I)


def _text_with_body(texts: list[dict[str, Any]], idx: int) -> str:
    """A caption text; when docling split off the label ("Figure 1."), the next text item is its body."""
    text = (texts[idx].get("text") or "").strip()
    if _LABEL_ONLY.match(text) and idx + 1 < len(texts):
        return f"{text} {(texts[idx + 1].get('text') or '').strip()}".strip()
    return text


def _captions(doc: dict[str, Any], picture: dict[str, Any]) -> str:
    texts = doc.get("texts", [])
    index = {t.get("self_ref"): i for i, t in enumerate(texts)}
    parts = [_text_with_body(texts, index[c.get("$ref")]) for c in picture.get("captions") or []
             if c.get("$ref") in index]
    return " ".join(p for p in parts if p).strip()


def _pool_pdf(cfg: BiblioConfig, citekey: str) -> Path | None:
    for pool_root in cfg.pool_search:
        candidate = pool_root / citekey / f"{citekey}.pdf"
        if candidate.exists():
            return candidate
    return None


def figures_dir(cfg: BiblioConfig, citekey: str) -> Path:
    return cfg.repo_root / "bib" / "derivatives" / "figures" / citekey


def figure_name(m: re.Match) -> tuple[str, str, str]:
    """(file stem, number, kind) from a caption match: fig-3, fig-S2, ed-4."""
    prefix, num = (m.group(1) or "").lower(), m.group(2).upper()
    if prefix.startswith("extended"):
        return f"ed-{num}", f"ED{num}", "extended-data"
    if prefix.startswith("supplementary") or num.startswith("S"):
        num = num if num.startswith("S") else f"S{num}"
        return f"fig-{num}", num, "supplementary"
    return f"fig-{num}", num, "figure"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _area(b: dict[str, float]) -> float:
    return max(0.0, b["w"]) * max(0.0, b["h"])


def _overlap(a: dict[str, float], b: dict[str, float]) -> float:
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return max(0.0, w) * max(0.0, h)


def _union(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
    x1, y1 = max(a["x"] + a["w"], b["x"] + b["w"]), max(a["y"] + a["h"], b["y"] + b["h"])
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _gap(a: dict[str, float], b: dict[str, float]) -> float:
    """Distance between two boxes (0 when they touch or overlap)."""
    dx = max(0.0, max(a["x"], b["x"]) - min(a["x"] + a["w"], b["x"] + b["w"]))
    dy = max(0.0, max(a["y"], b["y"]) - min(a["y"] + a["h"], b["y"] + b["h"]))
    return max(dx, dy)


def page_layout(pdf: Path, tmpdir: Path) -> dict[int, dict[str, list[dict[str, float]]]]:
    """Where images and text are drawn on each page (top-left boxes in points), from ``pdftohtml -xml``.

    Returns ``{page: {"images": [...], "texts": [...]}}``; empty without pdftohtml.
    """
    if shutil.which("pdftohtml") is None:
        return {}
    out = tmpdir / "layout"
    subprocess.run(["pdftohtml", "-xml", "-q", "-zoom", "1", "-nodrm", str(pdf), str(out)],
                   capture_output=True, check=False)
    xml = out.with_suffix(".xml")
    if not xml.is_file():
        return {}
    layout: dict[int, dict[str, list[dict[str, float]]]] = {}
    page = 0
    for m in re.finditer(r'<page number="(\d+)"|<(image|text) top="([\d.-]+)" left="([\d.-]+)" width="([\d.]+)" '
                         r'height="([\d.]+)"', xml.read_text(encoding="utf-8", errors="replace")):
        if m.group(1):
            page = int(m.group(1))
            continue
        box = {"x": float(m.group(4)), "y": float(m.group(3)), "w": float(m.group(5)), "h": float(m.group(6))}
        layout.setdefault(page, {"images": [], "texts": []})["images" if m.group(2) == "image" else "texts"].append(box)
    return layout


def classify_art(bbox: dict[str, float], images: list[dict[str, float]],
                 texts: list[dict[str, float]] | None = None) -> tuple[str, dict[str, float] | None]:
    """'raster' (one image covers the figure, nothing drawn on top), 'vector' (no image) or 'mixed';
    plus the covering image. Labels drawn as text over an image (axes, panel letters) make it mixed:
    the embedded image alone would lose them."""
    area = _area(bbox) or 1.0
    best, best_cov, total = None, 0.0, 0.0
    for img in images:
        cov = _overlap(img, bbox) / area
        total += cov
        if cov > best_cov:
            best, best_cov = img, cov
    if best is not None and best_cov >= 0.8 and _area(best) <= 1.5 * area:
        on_top = sum(1 for t in texts or [] if _overlap(t, bbox) >= 0.5 * (_area(t) or 1.0))
        return ("mixed", None) if on_top >= 3 else ("raster", best)
    return ("vector" if total < 0.1 else "mixed"), None


def overlay_check(pdf: Path, page: int, cover: dict[str, float], image_file: Path, tmpdir: Path) -> bool | None:
    """Whether something is drawn over an embedded image (labels as vector outlines, arrows): the
    rendered page region differs from the image alone. None when Pillow is not installed."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return None
    prefix = tmpdir / f"check-{page}"
    subprocess.run(pdftoppm_args(pdf, page, cover, 36, prefix), capture_output=True, check=False)
    rendered_path = prefix.with_suffix(".png")
    if not rendered_path.is_file():
        return None
    try:
        rendered = Image.open(rendered_path).convert("L")
        image = Image.open(image_file).convert("L").resize(rendered.size)
    except Exception:  # noqa: BLE001  unreadable image formats (JBIG2, CCITT)
        return None
    # resampling a clean image changes many pixels a little; overlays change some pixels a lot
    # (measured: clean raster 0.1% of pixels differ by >128, a figure with outlined labels 5.7%)
    w, h = rendered.size
    if w > 8 and h > 8:      # the crop's last row and column round differently: compare the inside
        rendered, image = rendered.crop((2, 2, w - 2, h - 2)), image.crop((2, 2, w - 2, h - 2))
    diff = ImageChops.difference(rendered, image).point(lambda v: 255 if v > 128 else 0)
    changed = diff.histogram()[255] / max(1, rendered.size[0] * rendered.size[1])
    return changed > 0.01


def pdftocairo_crop_args(pdf: Path, page: int, bbox: dict[str, float], out: Path) -> list[str]:
    """A one-page PDF of the figure box; vector art and embedded images are kept as they are."""
    x, y = int(round(bbox["x"])), int(round(bbox["y"]))
    w, h = max(1, int(round(bbox["w"]))), max(1, int(round(bbox["h"])))
    return ["pdftocairo", "-q", "-pdf", "-f", str(page), "-l", str(page), "-x", str(x), "-y", str(y),
            "-W", str(w), "-H", str(h), "-paperw", str(w), "-paperh", str(h), "-nocenter", "-noshrink",
            str(pdf), str(out)]


def _caption_texts(doc: dict[str, Any], page_heights: dict[int, float]) -> dict[int, list[tuple[float, str]]]:
    """Every "Figure N" text per page with its vertical centre (top-left), linked to a picture or not."""
    out: dict[int, list[tuple[float, str]]] = {}
    texts = doc.get("texts", [])
    for i, t in enumerate(texts):
        prov = (t.get("prov") or [None])[0]
        if prov and CAPTION_RE.match(t.get("text", "")):     # caption items and "Figure N." headings alike
            page = int(prov["page_no"])
            b = bbox_top_left(prov["bbox"], page_heights.get(page, 0.0))
            out.setdefault(page, []).append((b["y"] + b["h"] / 2, _text_with_body(texts, i)))
    return out


def _graphical_abstract_pages(doc: dict[str, Any]) -> set[int]:
    pages = set()
    for t in doc.get("texts", []):
        prov = (t.get("prov") or [None])[0]
        if prov and "graphical abstract" in t.get("text", "").lower():
            pages.add(int(prov["page_no"]))
    return pages


def _bib_entry(cfg: BiblioConfig, key: str) -> dict[str, str]:
    """Author, year, title, journal and DOI of a paper from the project's or the pools' bibliographies."""
    from ._pybtex_utils import parse_bibtex_file
    from .pool import _find_pool_bib
    from .refs import _project_bibs
    bibs = list(_project_bibs(cfg)) + [b for b in (_find_pool_bib(r) for r in cfg.pool_search) if b]
    for bib in bibs:
        try:
            db = parse_bibtex_file(bib)
        except Exception:  # noqa: BLE001
            continue
        entry = next((e for k, e in db.entries.items() if k.lower() == key.lower()), None)
        if entry is None:
            continue
        persons = entry.persons.get("author") or []
        first = " ".join(persons[0].last_names) if persons else ""
        f = entry.fields
        clean = lambda v: re.sub(r"[{}]", "", " ".join(str(v or "").split()))  # noqa: E731
        return {"first": clean(first), "n_authors": str(len(persons)), "year": clean(f.get("year")),
                "title": clean(f.get("title")), "journal": clean(f.get("journal") or f.get("journaltitle")),
                "doi": clean(f.get("doi"))}
    return {}


def credit_line(key: str, bib: dict[str, str]) -> str:
    first = bib.get("first") or key.split("_")[0].capitalize()
    etal = " et al." if bib.get("n_authors", "2") != "1" else ""
    year = bib.get("year") or (key.split("_")[1] if "_" in key else "")
    parts = [f"{first}{etal} {year}".strip(), bib.get("journal", ""), f"doi:{bib['doi']}" if bib.get("doi") else ""]
    return ", ".join(p for p in parts if p)


def _rel(path: Path, root: Path) -> str:
    """Project-relative path without resolving symlinks (an annexed PDF keeps its working-tree name)."""
    try:
        return os.path.relpath(path, root) if Path(path).is_absolute() and str(path).startswith(str(root)) else str(path)
    except ValueError:
        return str(path)


def extract_figures(
    cfg: BiblioConfig,
    citekey: str,
    *,
    dpi: int = 300,
    min_pt: float = 36.0,
    tolerance: float = 0.1,
    force: bool = False,
    min_frac: float = 0.05,
    pdf_version: str = "unknown",
    licence: str = "unknown",
) -> dict[str, Any]:
    """Write native-resolution figures, cropped vector PDFs and a manifest for one paper.

    ``min_frac``: uncaptioned pictures smaller than this share of the page are skipped (logos,
    cover marks); captioned ones are kept down to 1%.
    """
    from .docling import resolve_docling_outputs
    from .wiki.embeds import clean_caption

    require_poppler()
    key = citekey.lstrip("@")
    outdir = figures_dir(cfg, key)
    manifest_path = outdir / "manifest.yml"
    if manifest_path.exists() and not force:
        return {"citekey": key, "status": "exists", "manifest": manifest_path}

    outputs, source = resolve_docling_outputs(cfg, key)
    if source == "missing" or not outputs.json_path.exists():
        raise FileNotFoundError(f"no docling JSON for {key}; run `biblio docling run --key {key}` first")
    doc = json.loads(outputs.json_path.read_text(encoding="utf-8"))

    pdf = cfg.pdf_root / cfg.pdf_pattern.format(citekey=key)          # unresolved: keep the working-tree path
    if not pdf.exists():
        pdf = _pool_pdf(cfg, key) or pdf
    if not pdf.exists():
        hint = " (annexed file without content: run `datalad get`)" if pdf.is_symlink() else ""
        raise FileNotFoundError(f"PDF not found for {key}: {pdf}{hint}")

    listing = subprocess.run(["pdfimages", "-list", str(pdf)], capture_output=True, text=True, check=True).stdout
    embedded = parse_pdfimages_list(listing)
    by_page: dict[int, list[EmbeddedImage]] = {}
    for img in embedded:
        by_page.setdefault(img.page, []).append(img)
    heights = {int(k): float((v.get("size") or {}).get("height", 0.0)) for k, v in (doc.get("pages") or {}).items()}
    widths = {int(k): float((v.get("size") or {}).get("width", 0.0)) for k, v in (doc.get("pages") or {}).items()}
    captions_by_page = _caption_texts(doc, heights)
    pdf_pages = None
    if shutil.which("pdfinfo"):
        info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
        mp = re.search(r"^Pages:\s+(\d+)", info, re.M)
        pdf_pages = int(mp.group(1)) if mp else None
    outside = [int((p.get("prov") or [{}])[0].get("page_no", 0)) for p in doc.get("pictures", [])
               if pdf_pages and int((p.get("prov") or [{}])[0].get("page_no", 0)) > pdf_pages]
    doc_pages = len(doc.get("pages") or {})
    if pdf_pages and doc_pages and doc_pages != pdf_pages:
        raise RuntimeError(f"docling read a {doc_pages}-page PDF but {pdf} has {pdf_pages} pages: the full text "
                           f"comes from another version of the paper, so figures would get wrong pages and "
                           f"captions. Re-run docling on this PDF (`biblio docling run --key {key} --force`).")
    ga_pages = _graphical_abstract_pages(doc)

    # pass 1: name each picture; skip margin marks, logos and cover sheets
    cands, used_caps, skipped = [], set(), 0
    for index, picture in enumerate(doc.get("pictures", [])):
        prov = (picture.get("prov") or [None])[0]
        if not prov:
            continue
        page = int(prov["page_no"])
        if pdf_pages and page > pdf_pages:
            skipped += 1        # docling saw a page this PDF does not have (counted in the warning below)
            continue
        bbox = bbox_top_left(prov["bbox"], heights.get(page, 0.0))
        frac = _area(bbox) / ((heights.get(page) or 1.0) * (widths.get(page) or 1.0))
        if (bbox["w"] < min_pt and bbox["h"] < min_pt) or frac < 0.01:
            skipped += 1
            continue
        caption = _captions(doc, picture)
        m = CAPTION_RE.match(caption)
        if not m:   # docling linked no caption, or the wrong text: nearest unused figure caption on the page
            centre = bbox["y"] + bbox["h"] / 2
            free = [(y, t) for y, t in captions_by_page.get(page, []) if t not in used_caps]
            if free:
                caption = min(free, key=lambda yt: abs(yt[0] - centre))[1]
                m = CAPTION_RE.match(caption)
            elif frac >= min_frac:   # some layouts set the caption on the facing page: next, then previous
                for other in (page + 1, page - 1):
                    near = [t for _, t in captions_by_page.get(other, []) if t not in used_caps]
                    if near:
                        caption, m = near[0], CAPTION_RE.match(near[0])
                        break
        if m:
            stem, number, kind = figure_name(m)
            used_caps.add(caption)
        elif frac < min_frac:
            skipped += 1
            continue
        elif page in ga_pages:
            stem, number, kind, caption = "ga", "GA", "graphical-abstract", ""
        else:
            stem, number, kind, caption = None, None, "picture", ""
        cands.append({"index": index, "stem": stem, "number": number, "kind": kind, "caption": caption,
                      "page": page, "bbox": bbox, "pieces": 1})

    # pass 2: docling splits some figures into panels; on a page with one captioned figure, merge the
    # uncaptioned pictures that touch it (within 8% of the page height) into it. Extended Data and
    # supplementary pages hold one figure each, so every uncaptioned piece there belongs to it.
    merged = []
    for page in sorted({c["page"] for c in cands}):
        on_page = [c for c in cands if c["page"] == page]
        named = {c["stem"] for c in on_page if c["kind"] not in ("picture", "graphical-abstract")}
        if len(named) == 1:
            (stem,) = named
            base = next(c for c in on_page if c["stem"] == stem)
            rest = [c for c in on_page if c is not base and (c["stem"] in (stem, None))]
            others = [c for c in on_page if c is not base and c not in rest]
            one_per_page = base["kind"] in ("extended-data", "supplementary")
            tol = float("inf") if one_per_page else 0.08 * (heights.get(page) or 1.0)
            grew = True
            while grew:
                grew = False
                for c in list(rest):
                    if _gap(base["bbox"], c["bbox"]) <= tol:
                        base = {**base, "bbox": _union(base["bbox"], c["bbox"]), "pieces": base["pieces"] + 1}
                        rest.remove(c)
                        grew = True
            merged += [base] + rest + others
        else:
            merged += on_page
    seen: set[str] = set()
    for i, c in enumerate(merged):
        if c["stem"] is None:
            c["stem"] = f"pic-p{c['page']}-{i + 1:02d}"
        elif c["stem"] in seen:
            c["stem"] = f"{c['stem']}-p{c['page']}"
        seen.add(c["stem"])

    final_dir = outdir
    outdir = final_dir.parent / f".{key}.staging"     # built here, swapped in only when complete
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    try:
        return _extract_into(cfg, key, pdf, doc, outputs, merged, by_page, outdir, final_dir, dpi, tolerance,
                             skipped, pdf_pages, outside, pdf_version, licence)
    except BaseException:
        shutil.rmtree(outdir, ignore_errors=True)
        raise


def _extract_into(cfg, key, pdf, doc, outputs, merged, by_page, outdir, final_dir, dpi, tolerance, skipped,
                  pdf_pages, outside, pdf_version, licence) -> dict[str, Any]:
    from .wiki.embeds import clean_caption

    # pass 3: extract
    figures: list[dict[str, Any]] = []
    used: set[int] = set()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        layout = page_layout(pdf, tmpdir)
        extracted = False
        for c in merged:
            page, bbox, stem = c["page"], c["bbox"], c["stem"]
            on_page = layout.get(page, {"images": [], "texts": []})
            art, cover = classify_art(bbox, on_page["images"], on_page["texts"]) if layout else ("unknown", None)
            target = None
            match = None
            art_note = ""
            if art in ("raster", "unknown"):
                size = cover or bbox
                match = match_embedded(size, [i for i in by_page.get(page, []) if i.num not in used], tolerance)
            if match is not None:
                if not extracted:
                    subprocess.run(["pdfimages", "-all", str(pdf), str(tmpdir / "img")], check=True,
                                   capture_output=True)
                    extracted = True
                found = sorted(tmpdir.glob(f"img-{match.num:03d}.*"))
                overlays = overlay_check(pdf, page, cover or bbox, found[0], tmpdir) if found else None
                if found and overlays:
                    art = "mixed"           # labels drawn over the image: the image alone would lose them
                elif found:
                    target = outdir / f"{stem}{found[0].suffix}"
                    shutil.copyfile(found[0], target)
                    used.add(match.num)
                    src, w, h, ppi = "embedded", match.width, match.height, round(min(match.x_ppi, match.y_ppi), 1)
                    if overlays is None:
                        art_note = "overlay check skipped (install pillow); the PDF crop shows the figure as printed"
            if target is None:
                prefix = outdir / stem
                subprocess.run(pdftoppm_args(pdf, page, bbox, dpi, prefix), check=True, capture_output=True)
                target = prefix.with_suffix(".png")
                (w, h), src, ppi = _png_size(target), "rendered", float(dpi)
            files = {"file": target.name}
            sums = {target.name: _sha256(target)}
            if shutil.which("pdftocairo"):     # every figure: the box as printed, vector art and overlays kept
                crop = outdir / f"{stem}.pdf"
                subprocess.run(pdftocairo_crop_args(pdf, page, bbox, crop), capture_output=True, check=False)
                if crop.is_file():
                    files["pdf_file"] = crop.name
                    sums[crop.name] = _sha256(crop)
            caption, warnings = clean_caption(c["caption"])
            entry = {
                "ref": f"{key}:{stem}", "index": c["index"], "number": c["number"], "kind": c["kind"],
                "caption": caption, "page": page, "bbox_pt": {k: round(v, 2) for k, v in bbox.items()},
                "art": art, "source": src, **files, "width_px": w, "height_px": h, "ppi": ppi,
                "pieces": c["pieces"], "sha256": sums,
            }
            if warnings:
                entry["caption_warnings"] = warnings
            if art_note:
                entry["art_note"] = art_note
            figures.append(entry)

    bib = _bib_entry(cfg, key)
    pages = pdf_pages
    manifest = {
        "version": MANIFEST_VERSION,
        "citekey": key,
        "paper": {
            "citekey": key, "doi": bib.get("doi", ""), "title": bib.get("title", ""),
            "pdf": _rel(pdf, cfg.repo_root), "pdf_version": pdf_version, "pdf_sha256": _sha256(pdf),
            "pdf_pages": pages, "docling_json": _rel(outputs.json_path, cfg.repo_root),
            "credit": credit_line(key, bib), "licence": licence,
        },
        "dpi_rendered": dpi,
        "notes": "Pages are PDF pages (1-based); bbox_pt is in PDF points with a top-left origin. "
                 "Built by `biblio figures run`.",
        "figures": figures,
        "skipped_small": skipped,
    }
    if outside:
        manifest["warnings"] = [f"{len(outside)} docling pictures are on pages beyond the PDF's {pdf_pages} "
                                "(docling may have read another version of the paper); skipped"]
    (outdir / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
                                         encoding="utf-8")
    changes = _swap_in(outdir, final_dir)
    return {"citekey": key, "status": "written", "manifest": final_dir / "manifest.yml", "figures": len(figures),
            "embedded": sum(f["source"] == "embedded" for f in figures), "skipped_small": skipped,
            "vector_pdfs": sum("pdf_file" in f for f in figures), "changes": changes,
            "warnings": manifest.get("warnings", [])}


def _swap_in(staging: Path, final_dir: Path) -> dict[str, list[str]]:
    """Replace the figure folder with the staged one; report files added, removed and changed.

    In a DataLad dataset the old files may be annex symlinks: the new files are regular files
    until `datalad save`, which annexes them again.
    """
    def digest(path: Path) -> str | None:
        try:
            return _sha256(path)
        except OSError:          # an annexed file without content
            return None
    old = {p.name: p for p in final_dir.iterdir() if p.is_file() or p.is_symlink()} if final_dir.is_dir() else {}
    new = {p.name: p for p in staging.iterdir() if p.is_file()}
    changes = {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
               "changed": sorted(n for n in set(new) & set(old) if n != "manifest.yml"
                                 and digest(new[n]) != digest(old[n]))}
    if final_dir.exists() or final_dir.is_symlink():
        shutil.rmtree(final_dir)
    staging.rename(final_dir)
    return changes
