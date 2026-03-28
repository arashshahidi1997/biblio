# Set Up a User Profile

A user profile writes sensible defaults to `~/.config/biblio/config.yml` so
you do not have to repeat common settings (pool paths, GROBID URL) in every
project.

## List available profiles

```bash
biblio profile list
```

Bundled profiles ship with the package. Output example:

```
  sirota               Sirota Lab
                       Default profile for Sirota Lab members (UCSF HPC)
```

## Apply a profile

```bash
biblio profile use sirota
```

`biblio` detects your personal storage path automatically and asks for
confirmation. To skip the prompt:

```bash
biblio profile use sirota --yes
```

To specify the storage path explicitly (e.g. if auto-detection finds the wrong
volume):

```bash
biblio profile use sirota --storage /storage3/arash
```

## Inspect the current user config

```bash
biblio profile show
```

Prints `~/.config/biblio/config.yml` with its path as a header comment.

## Edit user config manually

`~/.config/biblio/config.yml` is plain YAML. You can edit it directly. Any key
accepted by a project `bib/config/biblio.yml` is valid here.

Example — set a default GROBID URL lab-wide:

```yaml
grobid:
  url: http://grobid-node:8070
```

## Override the user config path

Set `BIBLIO_USER_CONFIG` to point to a different file:

```bash
export BIBLIO_USER_CONFIG=/storage2/arash/biblio-user.yml
```

This is useful on systems where `~` is quota-limited or when sharing a config
across multiple home directories.

## Config precedence

Settings are resolved in this order (later wins):

1. Package defaults (hardcoded)
2. User config (`~/.config/biblio/config.yml`)
3. Project config (`bib/config/biblio.yml`)

Nested sections are merged: a project config that sets `grobid.url` does not
erase `pool.path` from the user config.
