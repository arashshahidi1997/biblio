"""Native-resolution figure extraction (backlog D10)."""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
import yaml

from biblio.figures import (
    EmbeddedImage,
    bbox_top_left,
    match_embedded,
    parse_pdfimages_list,
    pdftoppm_args,
)

LISTING = """page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio
--------------------------------------------------------------------------------------------
   1     0 image     672   500  rgb     3   8  image  no         7  0   407   407 31.0K 3.1%
   1     1 smask     672   500  gray    1   8  image  no         7  0   407   407  348B 0.1%
   7     4 image    1446  2033  rgb     3   8  jpeg   no       127  0   300   300  297K 3.4%
"""


def test_parse_listing_skips_masks():
    images = parse_pdfimages_list(LISTING)
    assert [(i.page, i.num, i.enc) for i in images] == [(1, 0, "image"), (7, 4, "jpeg")]
    w, h = images[1].displayed_pt
    assert round(w) == 347 and round(h) == 488


def test_bbox_conversion_and_match():
    bbox = bbox_top_left({"l": 100, "r": 445, "t": 700, "b": 210, "coord_origin": "BOTTOMLEFT"}, 842.0)
    assert bbox == {"x": 100.0, "y": 142.0, "w": 345.0, "h": 490.0}
    img = EmbeddedImage(page=7, num=4, width=1446, height=2033, enc="jpeg", x_ppi=300, y_ppi=300)
    assert match_embedded(bbox, [img]) is img
    assert match_embedded({"x": 0, "y": 0, "w": 200, "h": 50}, [img]) is None


def test_pdftoppm_crop_in_pixels():
    args = pdftoppm_args(Path("p.pdf"), 3, {"x": 72, "y": 144, "w": 36, "h": 72}, 300, Path("out"))
    assert args[args.index("-x") + 1:args.index("-x") + 2] == ["300"]
    assert args[args.index("-y") + 1] == "600" and args[args.index("-W") + 1] == "150"
    assert args[args.index("-H") + 1] == "300" and "-singlefile" in args


def _pdf_with_jpeg(jpeg: bytes, px: tuple[int, int], overlay: bytes = b"") -> bytes:
    """One 200x200 pt page with the JPEG drawn at x=50, y=100 (bottom-left), 100x50 pt; ``overlay``
    is extra content drawn on top (e.g. a filled rectangle standing in for outlined labels)."""
    content = b"q 100 0 0 50 50 100 cm /Im0 Do Q " + overlay
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (px[0], px[1], len(jpeg)) + jpeg + b"\nendstream",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]
    out = io.BytesIO(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref))
    return out.getvalue()


@pytest.mark.skipif(not (shutil.which("pdfimages") and shutil.which("pdftoppm")), reason="poppler not installed")
def test_extract_embedded_and_rendered(tmp_path, monkeypatch):
    Image = pytest.importorskip("PIL.Image")
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})
    from biblio.config import load_biblio_config
    from biblio.figures import extract_figures

    buf = io.BytesIO()
    Image.new("RGB", (400, 200), (200, 30, 30)).save(buf, format="JPEG")
    key = "test_2026_Figures"
    pdf_dir = tmp_path / "bib" / "articles" / key
    pdf_dir.mkdir(parents=True)
    (pdf_dir / f"{key}.pdf").write_bytes(_pdf_with_jpeg(buf.getvalue(), (400, 200)))
    doc_dir = tmp_path / "bib" / "derivatives" / "docling" / key
    doc_dir.mkdir(parents=True)
    (doc_dir / f"{key}.md").write_text("# Test\n")
    caption = {"self_ref": "#/texts/0", "text": "Figure 1. A red block."}
    (doc_dir / f"{key}.json").write_text(json.dumps({
        "texts": [caption],
        "pages": {"1": {"size": {"width": 200.0, "height": 200.0}}},
        "pictures": [
            {"prov": [{"page_no": 1, "bbox": {"l": 50, "r": 150, "t": 150, "b": 100, "coord_origin": "BOTTOMLEFT"}}],
             "captions": [{"$ref": "#/texts/0"}]},
            {"prov": [{"page_no": 1, "bbox": {"l": 10, "r": 190, "t": 60, "b": 10, "coord_origin": "BOTTOMLEFT"}}],
             "captions": []},
            {"prov": [{"page_no": 1, "bbox": {"l": 0, "r": 10, "t": 10, "b": 0, "coord_origin": "BOTTOMLEFT"}}],
             "captions": []},
        ],
    }))
    cfg_file = tmp_path / ".projio" / "biblio" / "biblio.yml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text("pdf_root: bib/articles\nout_root: bib/derivatives/docling\n")
    cfg = load_biblio_config(cfg_file, root=tmp_path)

    (tmp_path / "bib" / "main.bib").write_text(
        f"@article{{{key},\n  author = {{Doe, Jane and Roe, Rick}},\n  title = {{Red blocks}},\n"
        "  journal = {Test Journal},\n  year = {2026},\n  doi = {10.1/red}\n}\n")
    result = extract_figures(cfg, key, dpi=144, pdf_version="publisher", licence="CC BY 4.0")
    assert result["figures"] == 2 and result["embedded"] == 1 and result["skipped_small"] == 1
    manifest = yaml.safe_load(result["manifest"].read_text())
    assert manifest["version"] == 2
    paper = manifest["paper"]
    assert paper["pdf"] == f"bib/articles/{key}/{key}.pdf" and len(paper["pdf_sha256"]) == 64
    assert paper["credit"] == "Doe et al. 2026, Test Journal, doi:10.1/red"
    assert (paper["pdf_version"], paper["licence"], paper["doi"]) == ("publisher", "CC BY 4.0", "10.1/red")
    fig1, pic = manifest["figures"]
    assert fig1["file"] == "fig-1.jpg" and fig1["source"] == "embedded" and fig1["number"] == "1"
    assert fig1["ref"] == f"{key}:fig-1" and fig1["kind"] == "figure" and fig1["caption"] == "Figure 1. A red block."
    assert (fig1["width_px"], fig1["height_px"]) == (400, 200)
    if shutil.which("pdftohtml"):
        assert fig1["art"] == "raster"                       # the image alone is the figure
        assert pic["art"] == "vector"
        if shutil.which("pdftocairo"):
            assert pic["pdf_file"] == f"{pic['file'][:-4]}.pdf"
            assert set(pic["sha256"]) == {pic["file"], pic["pdf_file"]}
    assert pic["source"] == "rendered" and pic["file"].startswith("pic-p1-") and pic["kind"] == "picture"
    assert (pic["width_px"], pic["height_px"]) == (360, 100)               # 180x50 pt at 144 dpi
    assert extract_figures(cfg, key)["status"] == "exists"


# --- D11 (journal-club R04 round 2) ---------------------------------------------------

@pytest.mark.parametrize("caption,expected", [
    ("Figure 3. Ripples", ("fig-3", "3", "figure")),
    ("Fig. S2 Supplement", ("fig-S2", "S2", "supplementary")),
    ("Supplementary Figure 2. Extra", ("fig-S2", "S2", "supplementary")),
    ("Extended Data Fig. 4 | Maps", ("ed-4", "ED4", "extended-data")),
])
def test_figure_names(caption, expected):
    from biblio.figures import CAPTION_RE, figure_name
    assert figure_name(CAPTION_RE.match(caption)) == expected


def test_art_classification():
    from biblio.figures import classify_art
    fig = {"x": 0, "y": 0, "w": 100, "h": 100}
    assert classify_art(fig, [{"x": 0, "y": 0, "w": 100, "h": 95}])[0] == "raster"
    assert classify_art(fig, [])[0] == "vector"
    assert classify_art(fig, [{"x": 0, "y": 0, "w": 50, "h": 50}])[0] == "mixed"
    assert classify_art(fig, [{"x": -500, "y": -500, "w": 1000, "h": 1000}])[0] == "mixed"   # page-size image
    labels = [{"x": 10 * i, "y": 90, "w": 8, "h": 6} for i in range(4)]                   # axis labels on top
    assert classify_art(fig, [{"x": 0, "y": 0, "w": 100, "h": 95}], labels)[0] == "mixed"


@pytest.mark.skipif(not (shutil.which("pdfimages") and shutil.which("pdftoppm")), reason="poppler not installed")
def test_wrong_caption_link_logos_and_panels(tmp_path, monkeypatch):
    """Maingret 2016: docling linked 'Figure 1' to a margin icon; logos must go; split panels merge."""
    Image = pytest.importorskip("PIL.Image")
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})
    from biblio.config import load_biblio_config
    from biblio.figures import extract_figures

    buf = io.BytesIO()
    Image.new("RGB", (400, 200), (30, 30, 200)).save(buf, format="JPEG")
    key = "test_2016_Panels"
    (tmp_path / "bib" / "articles" / key).mkdir(parents=True)
    (tmp_path / "bib" / "articles" / key / f"{key}.pdf").write_bytes(_pdf_with_jpeg(buf.getvalue(), (400, 200)))
    doc_dir = tmp_path / "bib" / "derivatives" / "docling" / key
    doc_dir.mkdir(parents=True)
    (doc_dir / f"{key}.md").write_text("# T\n")
    bl = lambda l, b, r, t: {"l": l, "b": b, "r": r, "t": t, "coord_origin": "BOTTOMLEFT"}  # noqa: E731
    (doc_dir / f"{key}.json").write_text(json.dumps({
        "texts": [{"self_ref": "#/texts/0", "text": "Figure 1. Panels A and B.",
                   "prov": [{"page_no": 1, "bbox": bl(50, 80, 150, 95)}]}],
        "pages": {"1": {"size": {"width": 200.0, "height": 200.0}}},
        "pictures": [
            {"prov": [{"page_no": 1, "bbox": bl(185, 185, 199, 199)}], "captions": [{"$ref": "#/texts/0"}]},  # icon
            {"prov": [{"page_no": 1, "bbox": bl(50, 125, 150, 150)}], "captions": []},   # panel A (top half)
            {"prov": [{"page_no": 1, "bbox": bl(50, 100, 150, 124)}], "captions": []},   # panel B, touching
            {"prov": [{"page_no": 1, "bbox": bl(2, 2, 22, 22)}], "captions": []},        # 1% logo, uncaptioned
        ],
    }))
    cfg = load_biblio_config(tmp_path / ".projio" / "biblio" / "biblio.yml", root=tmp_path)
    result = extract_figures(cfg, key, dpi=72)
    manifest = yaml.safe_load(result["manifest"].read_text())
    figs = manifest["figures"]
    assert [f["ref"].split(":")[1] for f in figs] == ["fig-1"]            # icon and logo skipped
    fig = figs[0]
    assert fig["caption"] == "Figure 1. Panels A and B." and fig["pieces"] == 2
    assert fig["bbox_pt"] == {"x": 50.0, "y": 50.0, "w": 100.0, "h": 50.0}   # A and B merged
    assert result["skipped_small"] == 2


@pytest.mark.skipif(not (shutil.which("pdfimages") and shutil.which("pdftohtml")), reason="poppler not installed")
def test_image_with_vector_overlay_is_rendered_whole(tmp_path, monkeypatch):
    """Sebastian 2023 Extended Data: labels drawn as outlines over an image; the image alone loses them."""
    Image = pytest.importorskip("PIL.Image")
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})
    from biblio.config import load_biblio_config
    from biblio.figures import extract_figures

    buf = io.BytesIO()
    Image.new("RGB", (400, 200), (255, 255, 255)).save(buf, format="JPEG")
    key = "test_2023_Overlay"
    (tmp_path / "bib" / "articles" / key).mkdir(parents=True)
    (tmp_path / "bib" / "articles" / key / f"{key}.pdf").write_bytes(
        _pdf_with_jpeg(buf.getvalue(), (400, 200), overlay=b"0 g 60 105 40 40 re f"))
    doc_dir = tmp_path / "bib" / "derivatives" / "docling" / key
    doc_dir.mkdir(parents=True)
    (doc_dir / f"{key}.md").write_text("# T\n")
    (doc_dir / f"{key}.json").write_text(json.dumps({
        "texts": [{"self_ref": "#/texts/0", "text": "Figure 1. Labelled."}],
        "pages": {"1": {"size": {"width": 200.0, "height": 200.0}}},
        "pictures": [{"prov": [{"page_no": 1, "bbox": {"l": 50, "r": 150, "t": 150, "b": 100,
                                                        "coord_origin": "BOTTOMLEFT"}}],
                      "captions": [{"$ref": "#/texts/0"}]}],
    }))
    cfg = load_biblio_config(tmp_path / ".projio" / "biblio" / "biblio.yml", root=tmp_path)
    fig = yaml.safe_load(extract_figures(cfg, key, dpi=72)["manifest"].read_text())["figures"][0]
    assert fig["art"] == "mixed" and fig["source"] == "rendered" and fig["file"] == "fig-1.png"
    if shutil.which("pdftocairo"):
        assert fig["pdf_file"] == "fig-1.pdf"
