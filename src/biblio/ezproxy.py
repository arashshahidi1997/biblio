"""EZProxy URL rewriting, download helpers, and Shibboleth SAML login."""
from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path
from typing import Any
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
    cookie: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> bool:
    """Attempt to download a URL through the EZProxy.

    Returns True on success, False on failure.

    Args:
        url: Original publisher URL (will be rewritten through proxy).
        proxy_base: Institutional proxy base URL.
        dest: Local destination path for the PDF.
        mode: URL rewriting mode — "prefix" (most common) or "suffix".
        cookie: EZProxy session cookie string (e.g. "ezproxy=abc123").
            Obtain by logging in via browser and copying the cookie.
            Store in ``~/.config/biblio/config.yml`` under
            ``pdf_fetch.ezproxy_cookie``.
        timeout: HTTP request timeout in seconds.
    """
    proxied = rewrite_url(url, proxy_base, mode=mode)
    headers = {"User-Agent": _USER_AGENT}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(proxied, headers=headers)
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


class ShibbolethLoginError(Exception):
    """Raised when Shibboleth SAML login fails."""


def shibboleth_login(
    proxy_base: str,
    username: str,
    password: str,
    *,
    test_url: str = "https://doi.org/10.1038/nrn3687",
) -> str:
    """Perform Shibboleth SAML login to EZProxy and return session cookies.

    Follows the full SAML2 POST flow:
    1. GET proxy login URL → collects initial cookies + SAML request
    2. POST SAML request to IdP
    3. IdP presents login form → POST credentials
    4. IdP returns SAML response → POST back to EZProxy
    5. Extract authenticated session cookies

    Args:
        proxy_base: EZProxy base URL (e.g. "https://emedien.ub.uni-muenchen.de").
        username: Institutional username (e.g. LMU Kennung).
        password: Institutional password.
        test_url: A DOI URL to use as the initial proxy request target.

    Returns:
        Cookie string in ``name1=value1; name2=value2`` format.

    Raises:
        ShibbolethLoginError: If any step of the SAML flow fails.
        ImportError: If ``requests`` or ``beautifulsoup4`` are not installed.
    """
    try:
        import requests as _requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ImportError(
            f"Shibboleth login requires 'requests' and 'beautifulsoup4'. "
            f"Install with: pip install requests beautifulsoup4\n"
            f"Missing: {exc.name}"
        ) from exc

    session = _requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})

    # Step 1: Hit the EZProxy login URL to start the SAML flow
    proxy_base = proxy_base.rstrip("/")
    login_url = f"{proxy_base}/login?url={quote(test_url, safe='')}"

    try:
        resp = session.get(login_url, allow_redirects=True, timeout=30)
    except Exception as exc:
        raise ShibbolethLoginError(f"Failed to reach EZProxy: {exc}") from exc

    # Step 2: We should be at the IdP or an intermediate page.
    # Look for the SAML form that auto-submits to the IdP.
    soup = BeautifulSoup(resp.text, "html.parser")

    # Follow any auto-submit SAML forms until we hit a login form
    from urllib.parse import urljoin

    for _ in range(5):  # max redirects
        form = soup.find("form")
        if form is None:
            break

        # Check if this is a login form (has password field)
        if form.find("input", {"type": "password"}):
            break

        # It's an auto-submit SAML relay form — submit it
        action = form.get("action", "")
        if not action:
            break
        if not action.startswith("http"):
            action = urljoin(resp.url, action)

        fields: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                fields[name] = inp.get("value", "")

        try:
            resp = session.post(action, data=fields, allow_redirects=True, timeout=30)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            raise ShibbolethLoginError(f"SAML relay failed: {exc}") from exc

    # Step 3: We should now be at the IdP login form
    login_form = soup.find("form")
    if login_form is None:
        raise ShibbolethLoginError(
            "Could not find login form. The EZProxy/IdP flow may have changed."
        )

    password_field = login_form.find("input", {"type": "password"})
    if password_field is None:
        raise ShibbolethLoginError(
            "No password field found in form. May already be authenticated or flow changed."
        )

    # Find the username and password field names
    username_field_name = "j_username"  # Shibboleth default
    password_field_name = password_field.get("name", "j_password")

    # Check for actual username field
    for inp in login_form.find_all("input"):
        inp_type = (inp.get("type") or "").lower()
        inp_name = inp.get("name", "")
        if inp_type == "text" and inp_name:
            username_field_name = inp_name
            break

    login_action = login_form.get("action", "")
    if not login_action.startswith("http"):
        login_action = urljoin(resp.url, login_action)

    # Collect all form fields (inputs + buttons)
    form_data: dict[str, str] = {}
    for el in login_form.find_all(["input", "button"]):
        name = el.get("name")
        if name:
            form_data[name] = el.get("value", "")

    form_data[username_field_name] = username
    form_data[password_field_name] = password

    # Step 4: POST credentials to IdP
    try:
        resp = session.post(login_action, data=form_data, allow_redirects=True, timeout=30)
    except Exception as exc:
        raise ShibbolethLoginError(f"Login POST failed: {exc}") from exc

    # Step 5: Follow any SAML response / consent forms back to EZProxy
    soup = BeautifulSoup(resp.text, "html.parser")
    for relay_i in range(10):  # allow more hops for consent pages
        form = soup.find("form")
        if form is None:
            break

        # If we see a password field again, login failed
        if form.find("input", {"type": "password"}):
            raise ShibbolethLoginError(
                "Login failed — credentials rejected. Check username and password."
            )

        action = form.get("action", "")
        if not action:
            break
        if not action.startswith("http"):
            action = urljoin(resp.url, action)

        # Collect form fields. For submit buttons, only include the
        # "proceed"/"accept" one — skip reject/deny/cancel buttons.
        fields = {}
        for el in form.find_all(["input", "button"]):
            name = el.get("name")
            if not name:
                continue
            el_type = (el.get("type") or "").lower()
            if el_type == "submit":
                # Only include the affirmative submit action
                val = (el.get("value") or "").lower()
                if "reject" in name.lower() or "cancel" in name.lower() or "deny" in val:
                    continue
            fields[name] = el.get("value", "")
        # For consent pages: prefer "remember consent" option
        if "_shib_idp_consentOptions" in fields:
            fields["_shib_idp_consentOptions"] = "_shib_idp_rememberConsent"

        try:
            resp = session.post(action, data=fields, allow_redirects=True, timeout=30)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:
            raise ShibbolethLoginError(f"SAML response relay failed: {exc}") from exc

    # Extract EZProxy cookies from the session
    proxy_host = urlparse(proxy_base).hostname or ""
    ezproxy_cookies = {
        c.name: c.value
        for c in session.cookies
        if proxy_host in (c.domain or "")
        and c.name.startswith("ezproxy")
        and c.value  # skip empty values
    }

    # Also check for cookies on subdomains (e.g. .emedien.ub.uni-muenchen.de)
    if not ezproxy_cookies:
        ezproxy_cookies = {
            c.name: c.value
            for c in session.cookies
            if c.name.startswith("ezproxy") and c.value
        }

    if not ezproxy_cookies:
        # Build debug info
        all_cookies = [
            f"{c.domain}: {c.name}={c.value[:20]}..."
            for c in session.cookies
        ]
        debug = f"Final URL: {resp.url}\nAll cookies ({len(all_cookies)}): " + "; ".join(all_cookies[:10])
        raise ShibbolethLoginError(
            f"No EZProxy cookies received after login.\n{debug}"
        )

    cookie_str = "; ".join(f"{k}={v}" for k, v in sorted(ezproxy_cookies.items()))
    return cookie_str
