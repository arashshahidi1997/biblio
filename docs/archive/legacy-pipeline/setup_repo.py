"""Setup script to scaffold the medallion data lake layout."""

from __future__ import annotations

from pathlib import Path


DATA_SUBDIRS = [
    Path("data/01_bronze"),
    Path("data/02_raw"),
    Path("data/03_silver"),
    Path("data/04_gold"),
]

CONFIG_FILES = [
    Path(".config/docling.yaml"),
    Path(".config/grobid.yaml"),
]

OVERRIDE_FILES = {
    Path("overrides/alignment.yaml"): "# alignment patches: work_id -> list of patches\n# - type: force_link|ignore|reanchor\n#   citation_marker: \"[12]\"\n#   target_text_snippet: \"target sentence fragment\"\n#   reason: \"why this override exists\"\n",
    Path("overrides/identities.yaml"): "# metadata patches: work_id -> fields to override\n# - doi: \"10.1234/example\"\n#   openalex_id: \"W1234567890\"\n",
}


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    keep = path / ".keep"
    if not keep.exists():
        keep.touch()


def ensure_file(path: Path, contents: str = "") -> None:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(contents, encoding="utf-8")


def main() -> None:
    for subdir in DATA_SUBDIRS:
        ensure_directory(subdir)

    ensure_directory(Path(".config"))
    for cfg in CONFIG_FILES:
        ensure_file(cfg, "# tool configuration\n")

    ensure_directory(Path("overrides"))
    for override_path, body in OVERRIDE_FILES.items():
        ensure_file(override_path, body)

    manifest = Path("manifest.jsonl")
    ensure_file(manifest, '{"note": "manifest initialized; add per-work records as the pipeline runs"}\n')


if __name__ == "__main__":
    main()
