````markdown
# CLI and Task Graph

The CLI maps directly to pipeline stages and is guided by the manifest.

## Core commands (illustrative)
- `bib ingest`
- `bib extract`
- `bib align`
- `bib link`
- `bib index`
- `bib report`
- `bib validate`

---

## Partial rebuilds and invalidation

The CLI must support invalidating downstream stages without rerunning upstream work.

### Example
If an override is added or modified:
```bash
bib align --force-from alignment
````

Behavior:

* Raw extraction outputs are preserved.
* Silver and Gold artifacts are invalidated.
* Manifest marks downstream stages as `pending`.

This enables fast iteration without recomputation of expensive steps.

---

## Validation gates

Each phase ends with a validation step.

### `bib validate`

Checks:

* unresolved citation rate
* alignment confidence distribution
* linking coverage
* schema compliance

### Gating policy

If validation thresholds are exceeded:

* pipeline halts before Gold indexing
* manifest records validation failure
* user intervention (logic change or override) is required

Validation thresholds are configurable per project.

````
