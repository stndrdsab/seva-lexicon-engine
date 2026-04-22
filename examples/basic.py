# Copyright 2026 STNDRDS AB
# Licensed under the Apache License, Version 2.0
"""Basic usage example for seva-lexicon-engine.

Run with:
    python examples/basic.py
"""
from seva_lexicon_engine import LexiconEngine


def main() -> None:
    # The engine auto-loads the YAML lexicons that ship with the package.
    engine = LexiconEngine()
    print(f"Loaded {engine.term_count} terms across categories: {engine.categories}")
    print()

    # ── Example 1: fraud scenario ────────────────────────────────────
    # A realistic support-line transcript fragment. Demonstrates how the
    # engine pulls multiple category hits from a single message and how
    # the context boosters raise the confidence of ambiguous terms.
    fraud_text = (
        "Case note: suspect demanded a wire transfer for an advance fee; "
        "linked to identity theft."
    )
    print(f"Fraud example:\n  {fraud_text!r}")
    for h in engine.match(fraud_text, lang="en"):
        print(
            f"  [{h.category}] {h.term!r:<20} "
            f"conf={h.confidence:.2f} "
            f"(base={h.base_confidence:.2f})  "
            f"boosters={sorted(h.boosters_found)}"
        )
    print()

    # ── Example 2: drug-slang scenario ───────────────────────────────
    # Illustrates the dampener/booster mechanism on deliberately
    # ambiguous terms ("gas" and "pack" are common English words; they
    # only signal drug context when co-occurring with other slang).
    drug_text = "pulled up with some zaza, pack of gas, you trynna link?"
    print(f"Drug-slang example:\n  {drug_text!r}")
    for h in engine.match(drug_text, lang="en"):
        print(
            f"  [{h.category}] {h.term!r:<20} "
            f"conf={h.confidence:.2f} "
            f"(base={h.base_confidence:.2f})  "
            f"boosters={sorted(h.boosters_found)}"
        )
    print()

    # ── Example 3: coercive-control demo lexicon ─────────────────────
    # Shows that the same engine handles the schema extension to a
    # coercive-control use case. Keep in mind the bundled
    # coercive_control_demo lexicon carries only 2 markers per category
    # — it is a sketch, not an operational detector.
    cc_text = (
        "You're imagining things again. I've never felt this way "
        "about you before — you are my everything."
    )
    print(f"Coercive-control demo:\n  {cc_text!r}")
    for h in engine.match(cc_text, lang="en"):
        if h.category != "coercive_control":
            continue
        print(
            f"  [{h.category}] {h.term!r:<30} "
            f"conf={h.confidence:.2f} "
            f"(base={h.base_confidence:.2f})  "
            f"boosters={sorted(h.boosters_found)}"
        )
    print()

    # ── Example 4: grouped output ────────────────────────────────────
    # ``match_grouped`` returns only hits at or above the given
    # confidence floor and buckets them by category — useful as the
    # input to a triage UI or a downstream aggregator.
    grouped = engine.match_grouped(fraud_text, lang="en", min_confidence=0.70)
    print(f"Grouped output (min_confidence=0.70):")
    for category, hits in grouped.items():
        print(f"  {category}: {len(hits)} hit(s)")
        for h in hits:
            print(f"    - {h.term!r} (conf={h.confidence:.2f})")


if __name__ == "__main__":
    main()
