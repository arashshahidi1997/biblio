# Edit The Wiki In Obsidian Or VS Code

A biblio wiki is plain markdown under `docs/wiki/`, so any editor works. These
settings keep what the editor writes in line with what `biblio wiki lint`
checks. They were tested on 2026-10-22 with Obsidian 1.14 on Ubuntu
(details in [the laptop test](../log/task/task-arash-20261022-laptop-zotero-obsidian.md)).

## Link style

biblio wikis use **relative markdown links**: `[Sharp-wave ripple](../concepts/sharp-wave-ripple.md)`.
`biblio wiki hubs` writes them, and they work unchanged in Obsidian, VS Code,
MkDocs and GitHub. Lint still accepts `[[wikilinks]]`, and a wiki can opt back
in with `link_style: wikilink` in `docs/wiki/wiki.yml`, but on a rename
Obsidian turns wikilinks into path wikilinks (`[[../concepts/x|...]]`), which
work nowhere else.

Use the page title as link text, not the file name: when Obsidian renames a
page it also rewrites link text that equals the old file name.

## Obsidian

1. **Open the project root as the vault**, not `docs/wiki/`, so links to paper
   full text under `bib/derivatives/docling/<key>/<key>.md` resolve.
2. Settings, Files and links:
   - **Use [[Wikilinks]]**: off
   - **New link format**: Relative path to file
   - **Automatically update internal links**: on
   - **Excluded files**: `bib/` (and project folders that hold generated
     markdown, such as `derivatives/`). Full texts then stay out of search,
     the graph and the quick switcher, and links into `bib/` still open.
3. Keep Obsidian's per-machine state out of git. Add to `.gitignore`:

   ```text
   .obsidian/workspace*.json
   ```

   or all of `.obsidian/` if the vault settings are not meant to be shared.

Dot folders (`.git`, `.datalad`, `.projio`, `.pixi`) are never indexed.

**Frontmatter.** Obsidian's Properties view shows the page fields as text,
dates and lists. The first edit through it rewrites flow lists as block lists
(`tags: [event/ripple]` becomes `tags:` plus `- event/ripple`). Lint accepts
both; expect a whole-frontmatter diff the first time.

**Renames.** With automatic link updates on, Obsidian rewrites every markdown
link to a renamed page. Hub listings are generated: run `biblio wiki hubs`
afterwards (lint reports `HUB001` until you do).

## Figures and other annexed files

In a DataLad dataset, PDFs and images are annexed: the working tree holds a
symlink into `.git/annex`. **Obsidian ignores file symlinks**, so an annexed
figure is missing from the vault and its embed shows "could not be found".
Markdown full text is in git (with `text2git`) and works.

To embed a paper's figure, extract the paper's figures once and print a
snippet (image, caption and citation, with the right relative path):

```bash
biblio figures run --key <citekey>
biblio wiki figure <citekey> 3 --page docs/wiki/sources/<page>.md
```

Then unlock what the wiki embeds, so the files become regular files:

```bash
biblio wiki embeds --unlock     # add --get to fetch content that is not here yet
```

`biblio wiki embeds` alone lists every embedded file with its state (`file`,
`locked`, `absent`, `missing`); lint reports the same as `IMG001`/`IMG002`,
and `IMG003` when a paper's figure is embedded without citing the paper.
`datalad save` keeps unlocked files annexed and unlocked. For a whole
checkout, `git annex adjust --unlock` unlocks everything.

## VS Code

Not tested yet. VS Code follows symlinks, so annexed figures should display
without unlocking, and relative markdown links work in its preview. Write
settings for the project between the managed markers projio uses in
`.vscode/settings.json`.

## Check

After editing in either editor:

```bash
biblio wiki hubs
biblio wiki lint
```
