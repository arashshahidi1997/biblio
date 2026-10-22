"""Status report: pages by type and status, the review queue, open flags."""
from __future__ import annotations

import json
from collections import Counter

from .pages import load_pages
from .schema import STATUSES, WikiConfig


def status(cfg: WikiConfig) -> dict:
    pages = load_pages(cfg.wiki_root)
    by_type: dict[str, Counter] = {}
    for page in pages:
        by_type.setdefault(page.type or "?", Counter())[page.status or "?"] += 1
    queue = [p.rel for p in pages
             if p.status == "draft" and str(p.frontmatter.get("author", "")) in ("llm", "mixed")]
    flagged = {p.rel: p.list_field("review_flags") for p in pages if p.list_field("review_flags")}
    return {
        "pages": len(pages),
        "by_type": {t: dict(c) for t, c in sorted(by_type.items())},
        "review_queue": sorted(queue),
        "flagged": flagged,
        "stubs": sorted(p.rel for p in pages if p.status == "stub"),
    }


def format_status(report: dict, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(report, indent=1)
    cols = [s for s in STATUSES if any(s in c for c in report["by_type"].values())]
    lines = [f"{report['pages']} pages", ""]
    if report["by_type"]:
        lines.append(f"{'type':<10}" + "".join(f"{s:>10}" for s in cols))
        for ptype, counts in report["by_type"].items():
            lines.append(f"{ptype:<10}" + "".join(f"{counts.get(s, 0):>10}" for s in cols))
    lines += ["", f"Review queue (draft, written by llm or mixed): {len(report['review_queue'])}"]
    lines += [f"  {rel}" for rel in report["review_queue"]]
    lines += ["", f"Open review flags: {len(report['flagged'])} pages"]
    for rel, flags in report["flagged"].items():
        lines += [f"  {rel}"] + [f"    - {flag}" for flag in flags]
    lines += ["", f"Stubs: {len(report['stubs'])}"]
    return "\n".join(lines)
