"""Build, check and upload biblio-tools to PyPI (or TestPyPI with --test).

Run through pixi: `pixi run -e dev publish` or `pixi run -e dev publish-test`.

The token comes from TWINE_PASSWORD (with TWINE_USERNAME, default __token__),
else from ~/.config/tokens/pypi.token (testpypi.token with --test), else from
the file named by --token-file. The token is passed to twine through the
environment and never printed.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS_DIR = Path.home() / ".config" / "tokens"
URLS = {"pypi": "https://upload.pypi.org/legacy/", "testpypi": "https://test.pypi.org/legacy/"}


def _version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from biblio import __version__

    return __version__


def _token(repo: str, token_file: Path | None) -> str:
    if os.environ.get("TWINE_PASSWORD"):
        return os.environ["TWINE_PASSWORD"]
    path = token_file or TOKENS_DIR / f"{repo}.token"
    if not path.is_file():
        raise SystemExit(f"[ERROR] no token: set TWINE_PASSWORD or create {path}")
    token = path.read_text(encoding="utf-8").strip()
    if not token.startswith("pypi-"):
        raise SystemExit(f"[ERROR] {path} does not hold an API token (expected 'pypi-...')")
    return token


def _run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--test", action="store_true", help="Upload to TestPyPI instead of PyPI.")
    ap.add_argument("--token-file", type=Path, help="Token file (default ~/.config/tokens/<pypi|testpypi>.token).")
    ap.add_argument("--skip-build", action="store_true", help="Upload what is in dist/ as it is.")
    args = ap.parse_args(argv)

    repo = "testpypi" if args.test else "pypi"
    token = _token(repo, args.token_file)
    version = _version()
    dist = ROOT / "dist"
    if not args.skip_build:
        shutil.rmtree(dist, ignore_errors=True)
        _run([sys.executable, "-m", "build"])
    files = sorted(str(p.relative_to(ROOT)) for p in dist.glob(f"biblio_tools-{version}*"))
    if not files:
        raise SystemExit(f"[ERROR] no dist/biblio_tools-{version}* files; build first")
    _run([sys.executable, "-m", "twine", "check", *files])
    env = {**os.environ, "TWINE_USERNAME": os.environ.get("TWINE_USERNAME", "__token__"), "TWINE_PASSWORD": token}
    _run([sys.executable, "-m", "twine", "upload", "--repository-url", URLS[repo], *files], env=env)
    print(f"[OK] biblio-tools {version} uploaded to {repo}")


if __name__ == "__main__":
    main()
