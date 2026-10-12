"""Corpus access for the knowledge-graph experiments.

Reads citekey sets from ``corpus/corpus.yml`` and resolves each paper's
derivatives under ``$KG_CORPUS_ROOT/bib/derivatives/``. Paper content is read
in place and never copied into the experiment folder.

Only local derivatives are resolved; the shared biblio pool is not consulted.

Usage::

    python common/corpus.py --set core
    python common/corpus.py --set extended --root /path/to/project
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

EXP_ROOT = Path(__file__).resolve().parents[1]
CORPUS_FILE = EXP_ROOT / "corpus" / "corpus.yml"


def corpus_root(root: str | os.PathLike | None = None) -> Path:
    value = root or os.environ.get("KG_CORPUS_ROOT")
    if not value:
        raise SystemExit("Set KG_CORPUS_ROOT (or pass --root) to a projio project with bib/derivatives/")
    path = Path(value).expanduser().resolve()
    if not (path / "bib" / "derivatives").is_dir():
        raise SystemExit(f"No bib/derivatives/ under {path}")
    return path


def load_set(name: str) -> list[str]:
    data = yaml.safe_load(CORPUS_FILE.read_text())
    if name in data.get("sets", {}):
        return list(data["sets"][name])
    if name in data:
        return list(data[name])
    raise KeyError(f"Unknown corpus set {name!r}")


@dataclass(frozen=True)
class Paper:
    citekey: str
    root: Path

    @property
    def derivatives(self) -> Path:
        return self.root / "bib" / "derivatives"

    @property
    def docling_md(self) -> Path:
        return self.derivatives / "docling" / self.citekey / f"{self.citekey}.md"

    @property
    def tei(self) -> Path:
        return self.derivatives / "grobid" / self.citekey / f"{self.citekey}.tei.xml"

    @property
    def grobid_references(self) -> Path:
        return self.derivatives / "grobid" / self.citekey / "references.json"

    def text(self) -> str:
        return self.docling_md.read_text(encoding="utf-8")

    def openalex(self) -> dict | None:
        return _resolved(self.root).get(self.citekey)

    def availability(self) -> dict[str, bool]:
        return {
            "docling": self.docling_md.is_file(),
            "grobid": self.tei.is_file(),
            "openalex": self.openalex() is not None,
        }


@lru_cache(maxsize=None)
def _resolved(root: Path) -> dict[str, dict]:
    path = root / "bib" / "derivatives" / "openalex" / "resolved.jsonl"
    records: dict[str, dict] = {}
    if not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("citekey") and rec.get("openalex_id"):
            records[rec["citekey"]] = rec
    return records


def papers(set_name: str, root: str | os.PathLike | None = None) -> list[Paper]:
    base = corpus_root(root)
    return [Paper(ck, base) for ck in load_set(set_name)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", default="core")
    ap.add_argument("--root", default=None)
    args = ap.parse_args(argv)

    rows = papers(args.set, args.root)
    width = max(len(p.citekey) for p in rows)
    counts = {"docling": 0, "grobid": 0, "openalex": 0}
    print(f"{'citekey':<{width}}  docling grobid openalex")
    for p in rows:
        avail = p.availability()
        for key, ok in avail.items():
            counts[key] += ok
        marks = "  ".join("  x   " if avail[k] else "  -   " for k in counts)
        print(f"{p.citekey:<{width}}  {marks}")
    total = len(rows)
    print(f"\n{total} papers: " + ", ".join(f"{k} {v}/{total}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
