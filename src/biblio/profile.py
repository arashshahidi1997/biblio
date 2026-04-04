"""User profile management for biblio: apply lab-wide presets to user config."""
from __future__ import annotations

import getpass
import glob
import os
from pathlib import Path
from typing import Any

import yaml

PROFILES_DIR = Path(__file__).parent / "profiles"
USER_CONFIG_ENV = "BIBLIO_USER_CONFIG"


def user_config_path() -> Path:
    override = os.environ.get(USER_CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".config" / "biblio" / "config.yml"


def load_user_config() -> dict[str, Any]:
    path = user_config_path()
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {}


def list_profiles() -> list[dict[str, str]]:
    """Return [{slug, name, description}] for all bundled profiles."""
    results = []
    for p in sorted(PROFILES_DIR.glob("*.yml")):
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        results.append({
            "slug": p.stem,
            "name": str(raw.get("name") or p.stem),
            "description": str(raw.get("description") or ""),
        })
    return results


def _find_storage_candidates(storage_glob: str, username: str) -> list[Path]:
    return sorted(
        Path(base) / username
        for base in glob.glob(storage_glob)
        if (Path(base) / username).is_dir()
    )


def apply_profile(
    slug: str,
    *,
    personal_storage: Path | None = None,
    yes: bool = False,
) -> Path:
    """Apply a named profile, writing ~/.config/biblio/config.yml.

    Detects the user's personal storage path automatically when possible,
    prompts interactively otherwise (suppressed with yes=True + explicit
    personal_storage).

    Returns the path of the written user config file.
    """
    profile_path = PROFILES_DIR / f"{slug}.yml"
    if not profile_path.exists():
        available = ", ".join(p["slug"] for p in list_profiles()) or "(none)"
        raise FileNotFoundError(
            f"Profile '{slug}' not found. Available: {available}"
        )

    raw: dict[str, Any] = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    username = getpass.getuser()
    storage_glob = str(raw.get("storage_glob") or "")

    # --- resolve personal storage root (only if profile uses pool/storage) ---
    needs_storage = bool(storage_glob or raw.get("pool"))
    if needs_storage:
        if personal_storage is None and storage_glob:
            candidates = _find_storage_candidates(storage_glob, username)
            if len(candidates) == 1:
                if yes:
                    personal_storage = candidates[0]
                else:
                    resp = input(
                        f"Personal storage detected: {candidates[0]}\nUse this? [Y/n] "
                    ).strip().lower()
                    personal_storage = candidates[0] if resp in ("", "y", "yes") else None
            elif len(candidates) > 1:
                print("Multiple storage volumes found:")
                for i, c in enumerate(candidates, 1):
                    print(f"  [{i}] {c}")
                choice = input("Choose [1]: ").strip() or "1"
                personal_storage = candidates[int(choice) - 1]

        if personal_storage is None:
            if yes:
                raise ValueError(
                    "Could not detect personal storage automatically. "
                    "Pass --storage <path> to specify it."
                )
            path_input = input(
                f"Enter your personal storage path (e.g. /storage2/{username}): "
            ).strip()
            personal_storage = Path(path_input).expanduser().resolve()

    config: dict[str, Any] = {}
    if needs_storage and personal_storage is not None:
        personal_storage = personal_storage.expanduser().resolve()
        personal_pool = personal_storage / "bib"

        raw_pool = raw.get("pool") or {}
        lab_root = raw_pool.get("lab_root")

        pool_section: dict[str, Any] = {"path": str(personal_pool)}
        if lab_root:
            pool_section["search"] = [str(lab_root), str(personal_pool)]
        config["pool"] = pool_section

    for key, value in raw.items():
        if key not in ("name", "description", "pool", "storage_glob"):
            config[key] = value

    dest = user_config_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return dest
