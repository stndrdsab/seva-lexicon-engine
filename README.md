# seva-lexicon-engine

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-beta-orange.svg)](#stability)
[![Tests](https://img.shields.io/badge/tests-15%20passing-brightgreen.svg)](tests/)

A context-aware lexicon matcher for forensic text analysis. YAML-driven
term lists, per-term confidence, context-window boosters and dampeners.
No ML, no LLM — a single Python module you can read end-to-end.

This is a lightweight **reference implementation** of the
pattern-plus-context approach to forensic text analysis — a
YAML-driven matcher that readers and researchers can inspect, tune,
and build on. The full operational coercive-control lexicons and
the context-gate integration live in the commercial S-EVA product
and are not part of this release.

---

## What's in the box

- **`LexiconEngine`** — ~500 lines, Python stdlib only (plus PyYAML).
  Loads YAML lexicons at startup, compiles one mega-regex per category
  and language, scores each hit against its context window.
- **Six demonstration lexicons**, all deliberately small subsets that
  illustrate the YAML schema rather than operate as production detectors:
  `drugs_en_demo`, `drugs_sv_demo`, `fraud_en_demo`, `fraud_sv_demo`,
  `emoji_universal_demo`, and `coercive_control_demo`. Each file's
  header is explicit that it is a schema sketch. Terms with available
  institutional sourcing carry an inline `source:` citation to a public
  reference (DEA Intelligence Reports, UNODC, Polisen.se, FTC, Europol,
  Stark 2007, Duluth Model, Hamberger et al. 2017); terms without
  verifiable institutional attribution have the field omitted rather
  than backfilled with unverifiable references — a deliberate
  source-verification policy, not an oversight. The full operational
  lexicons used in the deployed S-EVA pipeline are not part of this
  release.
- **15 smoke tests**, a runnable example, and `pyproject.toml` for
  editable installs.

## What it is not

- **It is not a coercive-control detection module.** A five-category
  pattern library (gaslighting, isolation, love-bombing,
  blame-shifting, economic control) and the accompanying context-gate
  logic remain part of the commercial stack.
- **It is not a message classifier.** It surfaces term hits with
  context-adjusted confidence. Aggregation, thresholding, and trajectory
  logic are left to the caller.
- **It is not a turnkey forensic tool.** Investigator-ready pipelines
  need ingestion, chain of custody, reporting, and review workflows on
  top of this.

---

## Architecture coverage

The accompanying article describes a four-layer detection architecture.
This reference release implements:

- **Layer 1** — pattern lexicon with per-term confidence and per-term
  context-window boosters/dampeners. **Included** as six demonstration
  subsets.
- **Layer 2** — relational-stance gate (pronoun and stance-indicator
  co-occurrence check at the message level). *Not included.*
- **Layer 3** — embedding-similarity rescue against per-category
  exemplars. *Not included.*
- **Layer 4** — trajectory aggregation across the conversation
  timeline. *Not included.*

The per-term context-window mechanism in the lexicon schema (see
[How context adjustment works](#how-context-adjustment-works) below) is
internal to Layer 1 and is distinct from the Layer 2 relational-stance
gate that sits above it in the deployed pipeline. The release goal is
to make Layer 1 lexicon curation and pattern matching peer-reviewable,
not to ship a turnkey detector.

---

## Install

The package is not yet published to PyPI. Install from source:

```bash
git clone https://github.com/stndrdsab/seva-lexicon-engine.git
cd seva-lexicon-engine
pip install -e .
```

Requires Python 3.10 or newer and `PyYAML>=6.0`.

## Quickstart

```python
from seva_lexicon_engine import LexiconEngine

engine = LexiconEngine()  # auto-loads the bundled demo lexicons

text = (
    "Case note: suspect demanded a wire transfer for an advance fee; "
    "linked to identity theft."
)

for h in engine.match(text, lang="en"):
    print(
        f"{h.category:10}  {h.term:20}  "
        f"conf={h.confidence:.2f}  "
        f"boosters={sorted(h.boosters_found)}"
    )
```

Output:

```
fraud       advance fee           conf=0.98  boosters=['transfer', 'wire']
fraud       identity theft        conf=0.75  boosters=[]
fraud       wire transfer         conf=0.30  boosters=[]
```

Three observations from this one example:

1. **`advance fee`** rises from its base `0.70` to `0.98` because two of
   its boosters (`wire`, `transfer`) appear nearby.
2. **`wire transfer`** stays at base `0.30` — its own boosters
   (`urgent`, `vendor`, `invoice`, `change`) didn't fire in this text.
   Each hit is scored independently against its own context window.
3. **`identity theft`** has no boosters configured; its confidence is
   just the declared base.

See [`examples/basic.py`](examples/basic.py) for a longer walk-through
that also covers the `match_grouped` API and Swedish-language matching.

### A note on the bundled lexicons

All six bundled lexicons are deliberately small demonstration subsets,
not production detectors. Each file is named with a `_demo` suffix and
opens with a header making this explicit. The goal is to illustrate
the schema concretely — term / canonical / confidence / boosters /
dampeners / source — without shipping operationally tuned lists. In
particular, the `coercive_control_demo` lexicon carries only two
English markers per category (gaslighting, isolation, love-bombing,
blame-shifting, economic control) and omits the separate *context-gate*
layer that sits above the per-term booster mechanism. A pipeline built
from any of these demo subsets alone will not perform at production
quality and should not drive investigative decisions.

---

## Lexicon format

Lexicons are YAML files loaded at engine startup. Minimal schema:

```yaml
category: drugs
language: en
version: "2026-04"

terms:
  - term: "zaza"
    canonical: "cannabis (premium)"
    confidence: 0.75

  - term: "exotic"
    canonical: "cannabis (premium strain)"
    confidence: 0.35
    context_boosters: ["smoke", "pack", "strain"]
    context_dampeners: ["animal", "travel"]
    source: "DEA Intelligence Report (public)"
```

| Field | Required | Notes |
|---|---|---|
| `term` | ✔ | The string to match. Single words use word-boundary regex; multi-word phrases allow flexible whitespace. |
| `canonical` | ✔ | Human-readable normalised form. |
| `confidence` | ✔ | Base confidence in `[0.05, 0.98]`. |
| `context_boosters` | | Terms that, when found in the hit's context window, raise confidence (`+0.15` each, capped at `+0.45` total — i.e. the first three boosters count). |
| `context_dampeners` | | Terms that lower confidence (`-0.25` each; no lower cap beyond the absolute floor of `0.05`). |
| `source` | | Free-text provenance (e.g. `"DEA Intelligence Report (public)"`). |
| `type` | | `word` (default), `emoji`, or `phrase`. |

Supported language tags: `sv`, `en`, `ar`, `de`, `no`, `da`, `fi`, `pl`,
`ru`, `tr`, `es`, `ku`, `so`, `ti`, `fa`, `fr`, `nl`, `it`, `pt`, `bg`,
`ro`, plus `all` for language-agnostic lexicons (emoji, code numbers).

## How context adjustment works

For each term hit at position `p`, the engine looks at the character
range `[p − window, p + len(term) + window]` (default window: 50 chars).

- Each booster present adds `+0.15`, capped at `+0.45` — so at most
  three boosters count toward raising a hit.
- Each dampener present subtracts `0.25`. There is no per-term lower
  cap beyond the absolute floor of `0.05`.
- The final score is clamped to `[0.05, 0.98]`.

The arithmetic is deliberately simple. It's meant to be read, inspected,
and tuned — not treated as a black box.

## Adding your own lexicons

Either drop a new `.yaml` file into `seva_lexicon_engine/lexicons/` so it
ships with the package, or point the engine at a separate directory:

```python
from pathlib import Path
from seva_lexicon_engine import LexiconEngine

engine = LexiconEngine(lexicon_dir=Path("/path/to/my/lexicons"))
```

Schema is validated at load time. Missing required fields,
out-of-range confidence values, and duplicate terms across files are
exposed via `engine.validation_warnings` (a list of human-readable
strings).

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Stability

`v0.1.0`. The public API (`LexiconEngine`, `LexiconHit`, `LexiconTerm`,
`match_lexicon`, `match_lexicon_grouped`) is stable within the `0.x`
series. Breaking changes will bump the minor version and be flagged in
[`CHANGELOG.md`](CHANGELOG.md).

## Publisher

[STNDRDS AB](https://stndrds.se) — compliance and forensics software.
For the operational coercive-control module, cross-case intelligence,
narrative generation, and full forensic pipeline, see the main S-EVA
product. This release exists to make the *approach* peer-reviewable
and reproducible, not to ship the product.

## Citing this work

If you reference this repository, please cite the accompanying
article:

> Antonsen, A. (2026). *Detecting coercive control patterns in
> forensic chat analysis: a pattern-plus-context approach.*
> eForensics Magazine, forthcoming.

A BibTeX entry will be added once the article is published.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
