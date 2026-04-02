# Institutional PDF access via EZProxy

This guide walks through setting up biblio to download paywalled PDFs through
your university's EZProxy. The example uses LMU Munich, but the same steps
apply to any EZProxy-based institution.

## Quick setup (LMU Munich)

```bash
# 1. Apply the LMU profile (sets ezproxy_base, mode, sources)
biblio profile use lmu-munich

# 2. Authenticate (opens browser, prompts for cookie)
biblio auth ezproxy

# 3. Fetch PDFs
biblio bibtex fetch-pdfs-oa
```

That's it. The rest of this page explains each step in detail.

## Step 1: Apply your institution's profile

Profiles pre-configure EZProxy settings so you don't have to edit YAML by hand.

```bash
# List available profiles
biblio profile list

# Apply one
biblio profile use lmu-munich
```

This writes `~/.config/biblio/config.yml` with:

```yaml
pdf_fetch:
  ezproxy_base: "https://emedien.ub.uni-muenchen.de"
  ezproxy_mode: "prefix"
  sources: ["pool", "openalex", "unpaywall", "ezproxy"]
  delay: 1.0
```

If your institution doesn't have a profile yet, create the config manually:

```yaml
# ~/.config/biblio/config.yml
pdf_fetch:
  ezproxy_base: "https://your-library-proxy.edu"
  ezproxy_mode: "prefix"    # or "suffix" for some institutions
  unpaywall_email: "you@university.edu"
```

## Step 2: Authenticate with EZProxy

EZProxy uses browser-based Shibboleth/SAML login. Biblio needs the session
cookie from an authenticated browser session.

```bash
biblio auth ezproxy
```

This will:

1. Open your EZProxy login page in the default browser
2. Wait for you to log in with your institutional credentials
3. Prompt you to paste the session cookies from your browser

### How to copy cookies from your browser

After logging in:

1. Open **DevTools** (F12 or right-click > Inspect)
2. Go to **Application** tab > **Cookies** > your proxy domain
3. Find the session cookies (typically named `ezproxy`, `ezproxyl`, `ezproxyn`)
4. For each cookie, note the **Name** and **Value** columns
5. Combine them in the format: `name1=value1; name2=value2; name3=value3`

Example:

```
ezproxy=YeyEabc123; ezproxyl=YeyEdef456; ezproxyn=YeyEghi789
```

Paste this when prompted. The command writes the cookie to
`~/.config/biblio/config.yml` and sets file permissions to `600` (owner-only).

### Cookie expiration

Session cookies expire after your institution's timeout (typically a few hours).
When fetches start failing with `"ezproxy"` status returning 0 results, re-run:

```bash
biblio auth ezproxy
```

## Step 3: Fetch PDFs

```bash
# Fetch all papers via open-access cascade
biblio bibtex fetch-pdfs-oa

# Fetch specific papers
biblio bibtex fetch-pdfs-oa --citekeys zipf1949 shannon1948

# Force re-download even if PDF exists
biblio bibtex fetch-pdfs-oa --force
```

Or via MCP tools:

```
biblio_pdf_fetch_oa()                          # all papers
biblio_pdf_fetch_oa(citekeys=["zipf1949"])     # specific papers
```

The cascade tries sources in order: **pool** > **OpenAlex** > **Unpaywall** >
**EZProxy**. Most open-access papers are found before EZProxy is needed. The
session cookie is only used for the EZProxy fallback step.

## How it works

For each paper with a DOI, the EZProxy step:

1. Constructs: `https://emedien.ub.uni-muenchen.de/login?url=https://doi.org/10.xxxx/paper`
2. Sends HTTP GET with your session cookie
3. The proxy authenticates the request and redirects to the publisher
4. Publisher serves the PDF (thinking you're on campus)
5. Biblio validates the response is a real PDF (checks `%PDF-` magic bytes)
6. Saves to `bib/articles/<citekey>/<citekey>.pdf`

If the cookie is expired, the proxy returns an HTML login page instead of a PDF.
Biblio detects this and reports the paper as needing manual fetch.

## Manual config (without profile or auth command)

If you prefer to edit the config directly:

```yaml
# ~/.config/biblio/config.yml
pdf_fetch:
  ezproxy_base: "https://emedien.ub.uni-muenchen.de"
  ezproxy_mode: "prefix"
  ezproxy_cookie: "ezproxy=YeyEabc123; ezproxyl=YeyEdef456; ezproxyn=YeyEghi789"
  unpaywall_email: "your.name@uni-muenchen.de"
  sources: ["pool", "openalex", "unpaywall", "ezproxy"]
  delay: 1.0
```

Then set permissions:

```bash
chmod 600 ~/.config/biblio/config.yml
```

## Adding a profile for your institution

Create a YAML file in `packages/biblio/src/biblio/profiles/`:

```yaml
# your-university.yml
name: Your University
description: EZProxy access for Your University Library

pdf_fetch:
  ezproxy_base: "https://proxy.library.your-university.edu"
  ezproxy_mode: "prefix"  # or "suffix"
  sources: ["pool", "openalex", "unpaywall", "ezproxy"]
  delay: 1.0
```

Then users can run `biblio profile use your-university`.

## Troubleshooting

**"0 ezproxy results" after successful login**
: Cookie has expired. Re-run `biblio auth ezproxy`.

**"No ezproxy_base configured"**
: Run `biblio profile use lmu-munich` first, or set `ezproxy_base` in your config.

**Downloads return HTML instead of PDF**
: The proxy is redirecting to a login page. Your cookie is either expired,
  incomplete (you may need all three cookies), or your institution uses a
  different auth mechanism.

**EZProxy works in browser but not in biblio**
: Some institutions require additional cookies beyond `ezproxy`. Check DevTools
  for all cookies set by the proxy domain and include all of them.
