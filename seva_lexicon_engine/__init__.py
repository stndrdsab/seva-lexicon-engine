# Copyright 2026 STNDRDS AB
# Licensed under the Apache License, Version 2.0
"""Public API for the seva-lexicon-engine package."""
from .engine import (
    LexiconEngine,
    LexiconHit,
    LexiconTerm,
    get_lexicon_engine,
    match_lexicon,
    match_lexicon_grouped,
)

__version__ = "0.1.0"

__all__ = [
    "LexiconEngine",
    "LexiconHit",
    "LexiconTerm",
    "get_lexicon_engine",
    "match_lexicon",
    "match_lexicon_grouped",
]
