import re
from pathlib import Path

def get_citekeys(md_path: str | Path):
    """
    Extract all @citekeys from a markdown file.
    Returns a sorted list of unique keys (without the @).
    """
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8")
    keys = set(re.findall(r'@([\w:-]+)', text))
    return sorted(keys)

