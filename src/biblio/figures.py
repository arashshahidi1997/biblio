"""Figures at native resolution.

docling's picture crops are page renders at 144 dpi. For each picture docling
found (page and bounding box in its JSON), this takes the image embedded in
the PDF when one matches the picture's place on the page (lossless, often
300 ppi), and otherwise re-renders the bounding box at a chosen resolution.

Needs poppler's ``pdfimages`` and ``pdftoppm`` (e.g. ``pixi global install poppler``).
Output: ``bib/derivatives/figures/<citekey>/`` with ``manifest.yml``.
"""
from __future__ import annotations

import json
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


def _captions(doc: dict[str, Any], picture: dict[str, Any]) -> str:
    texts = {t.get("self_ref"): t for t in doc.get("texts", [])}
    return " ".join(texts.get(c.get("$ref"), {}).get("text", "") for c in picture.get("captions") or []).strip()


def _pool_pdf(cfg: BiblioConfig, citekey: str) -> Path | None:
    for pool_root in cfg.pool_search:
        candidate = pool_root / citekey / f"{citekey}.pdf"
        if candidate.exists():
            return candidate
    return None


def figures_dir(cfg: BiblioConfig, citekey: str) -> Path:
    return cfg.repo_root / "bib" / "derivatives" / "figures" / citekey


def extract_figures(
    cfg: BiblioConfig,
    citekey: str,
    *,
    dpi: int = 300,
    min_pt: float = 36.0,
    tolerance: float = 0.1,
    force: bool = False,
) -> dict[str, Any]:
    """Write native-resolution figures and a manifest for one paper."""
    from .docling import pdf_path_for_key, resolve_docling_outputs

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

    pdf = pdf_path_for_key(cfg, key)
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

    if outdir.exists() and force:
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    entries: list[FigureEntry] = []
    skipped = 0
    used: set[int] = set()
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        extracted = False
        for index, picture in enumerate(doc.get("pictures", [])):
            prov = (picture.get("prov") or [None])[0]
            if not prov:
                continue
            page = int(prov["page_no"])
            page_size = (doc.get("pages", {}).get(str(page)) or {}).get("size") or {}
            bbox = bbox_top_left(prov["bbox"], float(page_size.get("height", 0.0)))
            if bbox["w"] < min_pt and bbox["h"] < min_pt:
                skipped += 1
                continue
            caption = _captions(doc, picture)
            m = FIGURE_RE.match(caption)
            number = int(m.group(1)) if m else None
            stem = f"fig-{number}" if number is not None else f"pic-{index:02d}"
            if (outdir / f"{stem}.png").exists() or any(outdir.glob(f"{stem}.*")):
                stem = f"{stem}-{index:02d}"

            match = match_embedded(bbox, [i for i in by_page.get(page, []) if i.num not in used], tolerance)
            if match is not None:
                if not extracted:
                    subprocess.run(["pdfimages", "-all", str(pdf), str(tmpdir / "img")], check=True,
                                   capture_output=True)
                    extracted = True
                found = sorted(tmpdir.glob(f"img-{match.num:03d}.*"))
                if found:
                    target = outdir / f"{stem}{found[0].suffix}"
                    shutil.copyfile(found[0], target)
                    used.add(match.num)
                    entries.append(FigureEntry(index, number, "figure" if number else "picture", caption, page,
                                               {k: round(v, 2) for k, v in bbox.items()}, "embedded",
                                               target.name, match.width, match.height,
                                               round(min(match.x_ppi, match.y_ppi), 1)))
                    continue
            prefix = outdir / stem
            subprocess.run(pdftoppm_args(pdf, page, bbox, dpi, prefix), check=True, capture_output=True)
            target = prefix.with_suffix(".png")
            w, h = _png_size(target)
            entries.append(FigureEntry(index, number, "figure" if number else "picture", caption, page,
                                       {k: round(v, 2) for k, v in bbox.items()}, "rendered", target.name,
                                       w, h, float(dpi)))

    manifest = {
        "citekey": key,
        "pdf": str(pdf),
        "docling_json": str(outputs.json_path),
        "dpi_rendered": dpi,
        "figures": [asdict(e) for e in entries],
        "skipped_small": skipped,
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {"citekey": key, "status": "written", "manifest": manifest_path, "figures": len(entries),
            "embedded": sum(e.source == "embedded" for e in entries), "skipped_small": skipped}
