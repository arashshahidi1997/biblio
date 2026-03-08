from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .openalex.openalex_cache import OpenAlexCache
from .openalex.openalex_client import OpenAlexClient, OpenAlexClientConfig


@dataclass(frozen=True)
class GraphExpandResult:
    total_inputs: int
    seeds_with_openalex: int
    candidates: int
    output_path: Path


def load_openalex_seed_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return records
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _normalize_openalex_id(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("http"):
        raw = raw.rstrip("/").split("/")[-1]
    return raw or None


def _load_or_fetch_work(
    *,
    client: OpenAlexClient,
    cache: OpenAlexCache,
    openalex_id: str,
    force: bool,
) -> dict[str, Any]:
    cache_path = cache.path_for_work_id(openalex_id)
    cached = None if force else cache.load_json(cache_path)
    if cached is not None:
        return cached
    payload = client.get_work(openalex_id)
    cache.save_json(cache_path, payload)
    return payload


def expand_openalex_reference_graph(
    *,
    cfg: OpenAlexClientConfig,
    cache: OpenAlexCache,
    records: list[dict[str, Any]],
    out_path: str | Path,
    force: bool = False,
) -> GraphExpandResult:
    client = OpenAlexClient(cfg)
    output_path = Path(out_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seed_ids = {
        seed_id
        for record in records
        for seed_id in [_normalize_openalex_id(record.get("openalex_id"))]
        if seed_id is not None
    }
    candidates_seen: set[str] = set()
    discovered: list[dict[str, Any]] = []

    try:
        for record in records:
            seed_id = _normalize_openalex_id(record.get("openalex_id"))
            if seed_id is None:
                continue

            work = _load_or_fetch_work(client=client, cache=cache, openalex_id=seed_id, force=force)
            refs = work.get("referenced_works")
            if not isinstance(refs, list):
                continue

            for raw_ref in refs:
                if not isinstance(raw_ref, str):
                    continue
                ref_id = _normalize_openalex_id(raw_ref)
                if ref_id is None or ref_id in seed_ids or ref_id in candidates_seen:
                    continue
                candidates_seen.add(ref_id)
                discovered.append(
                    {
                        "source": "openalex_reference_expansion",
                        "seed_openalex_id": seed_id,
                        "openalex_id": ref_id,
                        "openalex_url": f"https://openalex.org/{ref_id}",
                    }
                )
    finally:
        client.close()

    discovered.sort(key=lambda item: (str(item["seed_openalex_id"]), str(item["openalex_id"])))
    output_path.write_text(json.dumps(discovered, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return GraphExpandResult(
        total_inputs=len(records),
        seeds_with_openalex=len(seed_ids),
        candidates=len(discovered),
        output_path=output_path,
    )
