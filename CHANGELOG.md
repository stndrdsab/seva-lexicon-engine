# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-22

Initial public release. See [README.md](README.md) for the full
description of what this release contains and what is deliberately
held back.

### Added

- `LexiconEngine` — YAML-driven term matcher with context-window
  confidence adjustment.
- `LexiconHit`, `LexiconTerm` — public dataclasses for match results
  and loaded terms.
- Module-level convenience functions `match_lexicon` and
  `match_lexicon_grouped`.
- Six demonstration lexicons bundled with the package, all explicitly
  scoped as schema samples rather than production detectors:
  `drugs_en_demo`, `drugs_sv_demo`, `fraud_en_demo`, `fraud_sv_demo`,
  `emoji_universal_demo`, and `coercive_control_demo`. Each file is
  named with a `_demo` suffix and opens with a header explaining what
  is intentionally missing compared to the full operational lexicons
  used in the deployed S-EVA pipeline.
- Schema validation at load time: missing required fields, out-of-range
  confidence values, and duplicate terms across files produce warnings
  accessible via `engine.validation_warnings`.
- Example (`examples/basic.py`) and smoke test suite (15 tests in
  `tests/`).

### Not included (intentionally)

- Coercive-control five-category lexicon and context-gate logic —
  these remain part of the commercial S-EVA deployment.
- Production-tuned thresholds, ML components, narrative generation,
  and cross-case intelligence modules.
