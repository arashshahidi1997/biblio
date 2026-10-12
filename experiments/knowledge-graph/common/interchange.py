"""Validate a run folder in the interchange format and print graph stats.

Checks ``nodes.jsonl`` / ``edges.jsonl`` against ``schema/reference-schema.yml``
and verifies that each ``quote`` occurs in the paper's docling markdown
(see ``schema/interchange.md``).

Usage::

    python common/interchange.py runs/a01-llm-schema/20261012-1430-haiku/
    python common/interchange.py <run-dir> --no-quotes     # skip quote checks
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict, deque
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus import EXP_ROOT, Paper, corpus_root  # noqa: E402

SCHEMA_FILE = EXP_ROOT / "schema" / "reference-schema.yml"
SHINGLE = 3          # words per shingle for fuzzy quote matching
FUZZY_MIN = 0.8      # share of quote shingles that must occur in the text


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"-\s*\n\s*", "", text)            # hyphenated line breaks
    text = re.sub(r"[^\w\s]|_", " ", text)            # punctuation and markdown markup
    return re.sub(r"\s+", " ", text).strip().lower()


def shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + SHINGLE]) for i in range(max(1, len(words) - SHINGLE + 1))}


class QuoteChecker:
    def __init__(self, root: Path):
        self.root = root
        self._texts: dict[str, tuple[str, set] | None] = {}

    def _text(self, citekey: str):
        if citekey not in self._texts:
            paper = Paper(citekey, self.root)
            if paper.docling_md.is_file():
                norm = normalize(paper.text())
                self._texts[citekey] = (norm, shingles(norm.split()))
            else:
                self._texts[citekey] = None
        return self._texts[citekey]

    def check(self, citekey: str, quote: str) -> str:
        """Return 'exact', 'fuzzy', 'missing' (quote not found) or 'no-text'."""
        entry = self._text(citekey)
        if entry is None:
            return "no-text"
        text, text_shingles = entry
        q = normalize(quote)
        if q in text:
            return "exact"
        q_shingles = shingles(q.split())
        hit = len(q_shingles & text_shingles) / len(q_shingles)
        return "fuzzy" if hit >= FUZZY_MIN else "missing"


def sources_of(item: dict) -> list[dict]:
    if "sources" in item:
        return item["sources"] or []
    return [item["source"]] if item.get("source") else []


def level_connectivity(nodes: dict[str, dict], edges: list[dict]) -> tuple[int, int]:
    """Count Claims with an (undirected) path to a Theory and to an Experiment/Parameter."""
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        adj[e["src"]].add(e["dst"])
        adj[e["dst"]].add(e["src"])

    def reaches(start: str, targets: set[str], max_hops: int = 4) -> bool:
        seen, queue = {start}, deque([(start, 0)])
        while queue:
            node, hops = queue.popleft()
            if hops and nodes.get(node, {}).get("type") in targets:
                return True
            if hops < max_hops:
                for nxt in adj[node] - seen:
                    seen.add(nxt)
                    queue.append((nxt, hops + 1))
        return False

    claims = [nid for nid, n in nodes.items() if n.get("type") == "Claim"]
    connected = sum(
        reaches(c, {"Theory"}) and reaches(c, {"Experiment", "Parameter"}) for c in claims
    )
    return connected, len(claims)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--root", default=None, help="corpus root (default: $KG_CORPUS_ROOT)")
    ap.add_argument("--no-quotes", action="store_true")
    args = ap.parse_args(argv)

    schema = yaml.safe_load(SCHEMA_FILE.read_text())
    node_types = set(schema["node_types"])
    edge_types = set(schema["edge_types"])

    run = args.run_dir
    node_list = load_jsonl(run / "nodes.jsonl")
    edges = load_jsonl(run / "edges.jsonl")
    if not node_list:
        print(f"No nodes in {run / 'nodes.jsonl'}")
        return 1
    if not (run / "run.yml").is_file():
        print("warning: run.yml missing")

    errors: list[str] = []
    nodes: dict[str, dict] = {}
    for n in node_list:
        nid = n.get("id")
        if not nid:
            errors.append(f"node without id: {str(n)[:80]}")
            continue
        if nid in nodes:
            errors.append(f"duplicate node id: {nid}")
        nodes[nid] = n
        if n.get("type") not in node_types:
            errors.append(f"{nid}: unknown node type {n.get('type')!r}")
    for e in edges:
        if e.get("type") not in edge_types:
            errors.append(f"edge {e.get('src')}->{e.get('dst')}: unknown edge type {e.get('type')!r}")
        for end in ("src", "dst"):
            ref = e.get(end)
            if ref not in nodes and not str(ref).startswith(("paper:", "person:", "inst:")):
                errors.append(f"edge {end} {ref!r} not in nodes")

    quote_stats: Counter = Counter()
    if not args.no_quotes:
        checker = QuoteChecker(corpus_root(args.root))
        for n in node_list:
            for src in sources_of(n):
                if not src.get("quote"):
                    quote_stats["null"] += 1
                elif not src.get("citekey"):
                    quote_stats["no-citekey"] += 1
                else:
                    quote_stats[checker.check(src["citekey"], src["quote"])] += 1

    type_counts = Counter(n.get("type") for n in node_list)
    edge_counts = Counter(e.get("type") for e in edges)
    merged = sum(1 for n in node_list if len({s.get("citekey") for s in sources_of(n)}) >= 2)
    connected, n_claims = level_connectivity(nodes, edges)

    print(f"run: {run}")
    print(f"nodes: {len(node_list)}  edges: {len(edges)}  errors: {len(errors)}")
    print("node types:  " + ", ".join(f"{t} {c}" for t, c in type_counts.most_common()))
    print("edge types:  " + ", ".join(f"{t} {c}" for t, c in edge_counts.most_common()))
    print(f"type coverage: nodes {len(node_types & set(type_counts))}/{len(node_types)}, "
          f"edges {len(edge_types & set(edge_counts))}/{len(edge_types)}")
    if quote_stats:
        total = sum(quote_stats.values())
        valid = quote_stats["exact"] + quote_stats["fuzzy"]
        print(f"quotes: {valid}/{total} valid  ({dict(quote_stats)})")
    print(f"cross-paper nodes: {merged}")
    if n_claims:
        print(f"level connectivity: {connected}/{n_claims} claims reach a Theory and an Experiment/Parameter")
    for err in errors[:30]:
        print(f"  error: {err}")
    if len(errors) > 30:
        print(f"  ... {len(errors) - 30} more")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
