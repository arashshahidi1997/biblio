"""EZProxy URL rewriting and download helpers for institutional access."""
from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

_USER_AGENT = "biblio-tools (https://github.com/arashshahidi1997/biblio)"
_CHUNK = 1024 * 256
_DEFAULT_TIMEOUT = 30


def rewrite_url(url: str, proxy_base: str, *, mode: str = "prefix") -> str:
    """Rewrite a URL through an EZProxy.

    Modes:
      - "prefix": ``{proxy_base}/login?url={url}``  (most common, e.g. LMU Munich)
      - "suffix": replaces the host with ``{host}.{proxy_suffix}``
    """
    proxy_base = proxy_base.rstrip("/")
    if mode == "suffix":
        parsed = urlparse(url)
        proxy_host = urlparse(proxy_base).hostname or proxy_base
        new_host = f"{parsed.hostname}.{proxy_host}"
        return parsed._replace(netloc=new_host).geturl()
    # Default: prefix mode
    return f"{proxy_base}/login?url={quote(url, safe='')}"


def download_via_proxy(
    url: str,
    proxy_base: str,
    dest: Path,
    *,
    mode: str = "prefix",
    timeout: int = _DEFAULT_TIMEOUT,
) -> bool:
    """Attempt to download a URL through the EZProxy.

    Returns True on success, False on failure.
    This requires the user to be on VPN or have an active institutional session.
    """
    proxied = rewrite_url(url, proxy_base, mode=mode)
    req = urllib.request.Request(proxied, headers={"User-Agent": _USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # If the proxy redirects to a login page (HTML), treat as failure
            if "text/html" in content_type:
                Path(tmp_path).unlink(missing_ok=True)
                return False
            with open(tmp_fd, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
        # Verify we got a real PDF (check magic bytes)
        with open(tmp_path, "rb") as f:
            header = f.read(5)
        if header != b"%PDF-":
            Path(tmp_path).unlink(missing_ok=True)
            return False
        Path(tmp_path).replace(dest)
        return True
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        return False
