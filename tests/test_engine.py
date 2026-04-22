# Copyright 2026 STNDRDS AB
# Licensed under the Apache License, Version 2.0
"""Smoke tests for the bundled lexicon engine + demonstration lexicons."""
from __future__ import annotations

import pytest

from seva_lexicon_engine import (
    LexiconEngine,
    LexiconHit,
    match_lexicon,
    match_lexicon_grouped,
)


@pytest.fixture(scope="module")
def engine() -> LexiconEngine:
    """Shared engine instance loaded from the bundled demo lexicons."""
    return LexiconEngine()


# ── Loading ──────────────────────────────────────────────────────────────

def test_engine_loads_demo_lexicons(engine: LexiconEngine) -> None:
    # The bundled lexicons cover at least drugs, fraud, and
    # coercive-control demo categories.
    cats = set(engine.categories)
    assert "drugs" in cats
    assert "fraud" in cats
    assert "coercive_control" in cats
    assert engine.term_count > 0


def test_coercive_control_demo_fires_on_known_markers(engine: LexiconEngine) -> None:
    # The bundled coercive_control_demo lexicon should match at least
    # one canonical gaslighting marker.
    text = "You're imagining things again. You always say that."
    hits = engine.match(text, lang="en")
    cc_terms = {h.term.lower() for h in hits if h.category == "coercive_control"}
    assert "you're imagining things" in cc_terms, (
        f"expected gaslighting marker; got categories "
        f"{[(h.term, h.category) for h in hits]}"
    )


def test_validation_warnings_are_exposed(engine: LexiconEngine) -> None:
    # The warnings list may be empty, but the property must exist and be a list.
    assert isinstance(engine.validation_warnings, list)


# ── Matching ─────────────────────────────────────────────────────────────

def test_match_finds_swedish_drug_term(engine: LexiconEngine) -> None:
    text = "har rullar och gräs kvar om du vill"
    hits = engine.match(text, lang="sv")
    assert any(h.category == "drugs" for h in hits), (
        f"expected a drugs hit in {text!r}; got {[(h.term, h.category) for h in hits]}"
    )


def test_match_respects_language_filter(engine: LexiconEngine) -> None:
    text = "pulled up with some zaza tonight"
    # Should find the English drug term.
    hits_en = engine.match(text, lang="en")
    assert any(h.category == "drugs" and h.term.lower() == "zaza" for h in hits_en)
    # Should not leak into a Swedish-filtered match (zaza is in drugs_en).
    hits_sv = engine.match(text, lang="sv")
    assert not any(h.term.lower() == "zaza" for h in hits_sv)


def test_context_booster_raises_confidence(engine: LexiconEngine) -> None:
    # "exotic" has base_confidence 0.35 with boosters like "smoke"/"pack"/"gas".
    plain = engine.match("that plant is exotic", lang="en")
    boosted = engine.match("got some exotic, pack of gas, come smoke", lang="en")

    plain_exotic = [h for h in plain if h.term.lower() == "exotic"]
    boosted_exotic = [h for h in boosted if h.term.lower() == "exotic"]

    assert plain_exotic, "expected an 'exotic' hit in the plain text"
    assert boosted_exotic, "expected an 'exotic' hit in the boosted text"
    assert boosted_exotic[0].confidence > plain_exotic[0].confidence, (
        f"boosters should raise confidence: "
        f"plain={plain_exotic[0].confidence}, boosted={boosted_exotic[0].confidence}"
    )


def test_match_grouped_applies_min_confidence(engine: LexiconEngine) -> None:
    text = "ikväll fixar jag rullar och gräs till dig, ok?"
    low = engine.match_grouped(text, lang="sv", min_confidence=0.10)
    high = engine.match_grouped(text, lang="sv", min_confidence=0.95)
    low_count = sum(len(v) for v in low.values())
    high_count = sum(len(v) for v in high.values())
    assert low_count >= high_count


def test_hit_is_a_dataclass_instance(engine: LexiconEngine) -> None:
    hits = engine.match("har rullar och gräs kvar", lang="sv")
    if not hits:
        pytest.skip("no hits produced; skipping shape check")
    h = hits[0]
    assert isinstance(h, LexiconHit)
    assert isinstance(h.term, str)
    assert 0.05 <= h.confidence <= 0.98
    assert h.position >= 0


# ── Convenience functions ────────────────────────────────────────────────

def test_module_level_match_convenience() -> None:
    hits = match_lexicon("pulled up with zaza", lang="en")
    assert any(h.category == "drugs" for h in hits)


def test_module_level_grouped_convenience() -> None:
    grouped = match_lexicon_grouped("pulled up with zaza", lang="en", min_confidence=0.1)
    assert "drugs" in grouped


# ── Graceful handling of edge cases ──────────────────────────────────────

@pytest.mark.parametrize("text", ["", " ", "a", "\n\n"])
def test_empty_or_tiny_input_returns_no_hits(engine: LexiconEngine, text: str) -> None:
    assert engine.match(text) == []


def test_match_is_deterministic(engine: LexiconEngine) -> None:
    text = "got some zaza, pack of gas"
    a = engine.match(text, lang="en")
    b = engine.match(text, lang="en")
    assert [(h.term, h.confidence, h.position) for h in a] == \
           [(h.term, h.confidence, h.position) for h in b]
