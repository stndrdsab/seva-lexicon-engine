# Copyright 2026 STNDRDS AB
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
"""Context-aware lexicon matcher — data-driven terminology detection.

Loads YAML lexicon files and matches terms against text using a sliding
context window. Each term carries a base confidence score that is boosted
or dampened depending on which other words appear nearby.

Architecture:
    lexicons/*.yaml  ->  LexiconEngine.load()  ->  compiled term index
    text + window    ->  LexiconEngine.match()  ->  List[LexiconHit]

Design decisions:
    - YAML (not Python) so analysts can update term lists without code changes
    - Context window (+/- 50 chars default) to resolve ambiguity
    - Boosters/dampeners adjust confidence from base, never above 0.98
    - Minimum 2 distinct hits required before a caller treats it as a finding
    - Thread-safe: compiled once, read-only after init

A small reference implementation of a pattern-plus-context matcher
for forensic text analysis. The full operational lexicons and the
context-gate integration used in the deployed pipeline are not part
of this open release.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

log = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

_LEXICON_DIR = Path(__file__).parent / "lexicons"

# ── Data classes ──────────────────────────────────────────────────────────

# Valid language codes (ISO 639-1 + "all" for universal lexicons)
_VALID_LANGUAGES = {
    "all", "sv", "en", "ar", "de", "no", "da", "fi", "pl", "ru",
    "tr", "es", "ku", "so", "ti", "fa", "fr", "nl", "it", "pt",
    "bg", "ro",
}


@dataclass(frozen=True)
class LexiconTerm:
    """A single term with context modifiers."""
    term: str
    canonical: str
    base_confidence: float
    boosters: FrozenSet[str] = frozenset()
    dampeners: FrozenSet[str] = frozenset()
    term_type: str = "word"  # word, emoji, phrase
    source: str = ""  # provenance: "Polisen.se 2024", "BRÅ 2023:3"
    pattern: re.Pattern = field(default=None, compare=False, hash=False)  # type: ignore


@dataclass
class LexiconHit:
    """A matched term with context-adjusted confidence."""
    term: str
    canonical: str
    category: str
    language: str
    confidence: float
    base_confidence: float
    position: int  # char offset in text
    source: str = ""
    boosters_found: List[str] = field(default_factory=list)
    dampeners_found: List[str] = field(default_factory=list)


# ── Engine ────────────────────────────────────────────────────────────────

class LexiconEngine:
    """Context-aware lexicon matcher.

    Usage::

        engine = LexiconEngine()          # auto-loads all YAML files
        hits = engine.match(text)         # returns List[LexiconHit]
        grouped = engine.match_grouped(text)  # {category: [hits]}
    """

    def __init__(self, lexicon_dir: Optional[Path] = None, window: int = 50):
        self._dir = lexicon_dir or _LEXICON_DIR
        self._window = window
        # category → language → [LexiconTerm]
        self._terms: Dict[str, Dict[str, List[LexiconTerm]]] = {}
        # category → language → compiled mega-regex (all terms OR'd)
        self._patterns: Dict[str, Dict[str, re.Pattern]] = {}
        # term string → LexiconTerm (for fast lookup after regex hit)
        self._lookup: Dict[str, List[LexiconTerm]] = {}
        # Validation: (term_lower, category) → source filename
        self._global_seen: Dict[Tuple[str, str], str] = {}
        self._validation_warnings: List[str] = []
        self._loaded = False
        self._load()

    # ── Loading ───────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load all YAML lexicon files from the lexicons directory."""
        if yaml is None:
            log.warning("lexicon_engine: PyYAML not installed, lexicons disabled")
            return
        if not self._dir.exists():
            log.warning("lexicon_engine: %s not found", self._dir)
            return

        total_terms = 0
        file_count = 0
        for path in sorted(self._dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if not data or not isinstance(data, dict):
                    self._validation_warnings.append(
                        f"{path.name}: empty or non-dict YAML")
                    continue
                # Validate required top-level fields
                warnings = self._validate_file(data, path.name)
                self._validation_warnings.extend(warnings)
                count = self._load_file(data, path.name)
                total_terms += count
                file_count += 1
            except Exception as e:
                log.warning("lexicon_engine: failed to load %s: %s", path.name, e)

        self._compile_patterns()
        self._loaded = True
        log.info("lexicon_engine: loaded %d terms from %d files",
                 total_terms, file_count)
        if self._validation_warnings:
            log.warning("lexicon_engine: %d validation warnings",
                        len(self._validation_warnings))
            for w in self._validation_warnings[:20]:
                log.warning("  %s", w)

    def _validate_file(self, data: dict, filename: str) -> List[str]:
        """Validate a lexicon YAML file structure. Returns list of warnings."""
        warnings: List[str] = []

        # Required top-level fields
        if "category" not in data:
            warnings.append(f"{filename}: missing required field 'category'")
        if "language" not in data:
            warnings.append(f"{filename}: missing required field 'language'")
        if "version" not in data:
            warnings.append(f"{filename}: missing recommended field 'version'")

        lang = data.get("language", "unknown")
        if lang not in _VALID_LANGUAGES:
            warnings.append(
                f"{filename}: unknown language '{lang}' "
                f"(valid: {', '.join(sorted(_VALID_LANGUAGES))})")

        terms = data.get("terms", [])
        if not isinstance(terms, list):
            warnings.append(f"{filename}: 'terms' must be a list")
            return warnings
        if not terms:
            warnings.append(f"{filename}: empty terms list")

        category = data.get("category", "unknown")
        for i, entry in enumerate(terms):
            if not isinstance(entry, dict):
                warnings.append(f"{filename}[{i}]: term entry must be a dict")
                continue
            # Required term fields
            if "term" not in entry:
                warnings.append(f"{filename}[{i}]: missing 'term'")
                continue
            if "canonical" not in entry:
                warnings.append(
                    f"{filename}[{i}]: '{entry.get('term', '?')}' missing 'canonical'")
            if "confidence" not in entry:
                warnings.append(
                    f"{filename}[{i}]: '{entry.get('term', '?')}' missing 'confidence'")

            # Confidence bounds
            conf = entry.get("confidence", 0.5)
            try:
                conf_f = float(conf)
                if conf_f < 0.05 or conf_f > 0.98:
                    warnings.append(
                        f"{filename}: '{entry['term']}' confidence {conf_f} "
                        f"outside [0.05, 0.98]")
            except (TypeError, ValueError):
                conf_f = 0.5  # default so subsequent checks don't NameError
                warnings.append(
                    f"{filename}: '{entry.get('term', '?')}' confidence "
                    f"'{conf}' is not a number")

            # Low confidence without context modifiers
            if conf_f < 0.40:
                has_boosters = bool(entry.get("context_boosters"))
                has_dampeners = bool(entry.get("context_dampeners"))
                if not has_boosters and not has_dampeners:
                    warnings.append(
                        f"{filename}: '{entry['term']}' has low confidence "
                        f"({conf_f}) but no boosters/dampeners — high FP risk")

            # Cross-file duplicate check
            term_key = entry.get("term", "").strip().lower()
            global_key = (term_key, category)
            if global_key in self._global_seen:
                prev_file = self._global_seen[global_key]
                if prev_file != filename:
                    warnings.append(
                        f"{filename}: '{entry['term']}' in category '{category}' "
                        f"already defined in {prev_file}")
            else:
                self._global_seen[global_key] = filename

        return warnings

    def _load_file(self, data: dict, filename: str) -> int:
        """Parse a single lexicon YAML file into LexiconTerm objects."""
        category = data.get("category", "unknown")
        language = data.get("language", "unknown")
        terms_list = data.get("terms", [])

        if category not in self._terms:
            self._terms[category] = {}
        if language not in self._terms[category]:
            self._terms[category][language] = []

        count = 0
        seen: Set[str] = set()  # deduplicate within file

        for entry in terms_list:
            if not isinstance(entry, dict):
                continue
            term_str = entry.get("term", "").strip()
            if not term_str or len(term_str) < 2:
                continue
            # Deduplicate
            term_key = term_str.lower()
            if term_key in seen:
                continue
            seen.add(term_key)

            boosters = frozenset(
                b.lower() for b in entry.get("context_boosters", []) if isinstance(b, str)
            )
            dampeners = frozenset(
                d.lower() for d in entry.get("context_dampeners", []) if isinstance(d, str)
            )

            # Determine type
            term_type = entry.get("type", "word")
            if any(ord(c) > 0x2600 for c in term_str):
                term_type = "emoji"

            # Build regex pattern for this term
            if term_type == "emoji":
                pat = re.compile(re.escape(term_str))
            elif " " in term_str:
                # Multi-word phrase: match with flexible whitespace
                parts = term_str.split()
                pat_str = r"\s+".join(re.escape(p) for p in parts)
                pat = re.compile(pat_str, re.IGNORECASE)
            else:
                # Single word: word boundary
                pat = re.compile(r"\b" + re.escape(term_str) + r"\b", re.IGNORECASE)

            lt = LexiconTerm(
                term=term_str,
                canonical=entry.get("canonical", term_str),
                base_confidence=min(0.98, max(0.05, float(entry.get("confidence", 0.5)))),
                boosters=boosters,
                dampeners=dampeners,
                term_type=term_type,
                source=entry.get("source", ""),
                pattern=pat,
            )
            self._terms[category][language].append(lt)

            # Lookup index
            if term_key not in self._lookup:
                self._lookup[term_key] = []
            self._lookup[term_key].append(lt)
            count += 1

        return count

    def _compile_patterns(self) -> None:
        """Compile mega-regex per (category, language) for fast scanning."""
        for category, langs in self._terms.items():
            self._patterns[category] = {}
            for lang, terms in langs.items():
                # Sort by length descending (greedy match)
                sorted_terms = sorted(terms, key=lambda t: len(t.term), reverse=True)
                parts = []
                for t in sorted_terms:
                    if t.term_type == "emoji":
                        parts.append(re.escape(t.term))
                    elif " " in t.term:
                        word_parts = t.term.split()
                        parts.append(r"\s+".join(re.escape(p) for p in word_parts))
                    else:
                        parts.append(r"\b" + re.escape(t.term) + r"\b")
                if parts:
                    try:
                        self._patterns[category][lang] = re.compile(
                            "|".join(parts), re.IGNORECASE
                        )
                    except re.error as e:
                        log.warning("lexicon_engine: regex compile failed for %s/%s: %s",
                                    category, lang, e)

    # ── Matching ──────────────────────────────────────────────────────

    def match(self, text: str, lang: Optional[str] = None,
              window: Optional[int] = None) -> List[LexiconHit]:
        """Match text against all loaded lexicons.

        Parameters
        ----------
        text : str
            Text to scan.
        lang : str, optional
            Filter to only this language's terms.  If None, scan all languages.
        window : int, optional
            Context window size in characters (default: self._window = 50).

        Returns
        -------
        List[LexiconHit]
            Matched terms with context-adjusted confidence scores.
        """
        if not self._loaded or not text or len(text) < 2:
            return []

        win = window if window is not None else self._window
        text_lower = text.lower()
        hits: List[LexiconHit] = []
        seen_positions: Set[Tuple[str, int]] = set()  # (term, position) dedup

        for category, langs in self._terms.items():
            for term_lang, terms in langs.items():
                # "all" language matches regardless of filter
                if lang and term_lang != lang and term_lang != "all":
                    continue

                # Use mega-regex for fast scan
                mega = self._patterns.get(category, {}).get(term_lang)
                if mega is None:
                    continue

                for m in mega.finditer(text):
                    matched_text = m.group(0).lower()
                    pos = m.start()

                    # Dedup
                    if (matched_text, pos) in seen_positions:
                        continue
                    seen_positions.add((matched_text, pos))

                    # Find the LexiconTerm
                    candidates = self._lookup.get(matched_text, [])
                    if not candidates:
                        # Try original case
                        candidates = self._lookup.get(m.group(0), [])
                    if not candidates:
                        continue

                    # Pick best candidate for this category
                    term_def = None
                    for c in candidates:
                        if c.term.lower() == matched_text:
                            term_def = c
                            break
                    if term_def is None:
                        term_def = candidates[0]

                    # Extract context window
                    ctx_start = max(0, pos - win)
                    ctx_end = min(len(text), pos + len(m.group(0)) + win)
                    context = text_lower[ctx_start:ctx_end]

                    # Adjust confidence based on context
                    confidence = term_def.base_confidence
                    boosters_found = []
                    dampeners_found = []

                    for b in term_def.boosters:
                        if b in context:
                            boosters_found.append(b)

                    for d in term_def.dampeners:
                        if d in context:
                            dampeners_found.append(d)

                    # Boost: +0.15 per booster (max +0.45)
                    boost = min(0.45, len(boosters_found) * 0.15)
                    # Dampen: -0.25 per dampener (no floor, but min 0.05)
                    dampen = len(dampeners_found) * 0.25

                    confidence = min(0.98, max(0.05, confidence + boost - dampen))

                    hits.append(LexiconHit(
                        term=m.group(0),
                        canonical=term_def.canonical,
                        category=category,
                        language=term_lang,
                        confidence=confidence,
                        base_confidence=term_def.base_confidence,
                        position=pos,
                        source=term_def.source,
                        boosters_found=boosters_found,
                        dampeners_found=dampeners_found,
                    ))

        # Sort by confidence descending
        hits.sort(key=lambda h: h.confidence, reverse=True)
        return hits

    def match_grouped(self, text: str, lang: Optional[str] = None,
                      min_confidence: float = 0.30) -> Dict[str, List[LexiconHit]]:
        """Match and group by category, filtering by minimum confidence.

        Parameters
        ----------
        text : str
            Text to scan.
        lang : str, optional
            Filter to only this language's terms.
        min_confidence : float
            Minimum confidence threshold (default: 0.30).

        Returns
        -------
        Dict[str, List[LexiconHit]]
            Category → list of hits above threshold.
        """
        hits = self.match(text, lang=lang)
        grouped: Dict[str, List[LexiconHit]] = {}
        for hit in hits:
            if hit.confidence >= min_confidence:
                grouped.setdefault(hit.category, []).append(hit)
        return grouped

    @property
    def categories(self) -> List[str]:
        """Return list of loaded categories."""
        return list(self._terms.keys())

    @property
    def term_count(self) -> int:
        """Total number of loaded terms."""
        return sum(
            len(terms)
            for langs in self._terms.values()
            for terms in langs.values()
        )

    def get_terms(self, category: str, lang: Optional[str] = None) -> List[LexiconTerm]:
        """Return terms for a category (optionally filtered by language)."""
        langs = self._terms.get(category, {})
        if lang:
            return langs.get(lang, [])
        return [t for terms in langs.values() for t in terms]

    @property
    def validation_warnings(self) -> List[str]:
        """Return list of validation warnings from loading."""
        return list(self._validation_warnings)


# ── Module-level singleton ────────────────────────────────────────────────

_engine: Optional[LexiconEngine] = None


def get_lexicon_engine() -> LexiconEngine:
    """Return the global LexiconEngine singleton (lazy init)."""
    global _engine
    if _engine is None:
        _engine = LexiconEngine()
    return _engine


def match_lexicon(text: str, lang: Optional[str] = None) -> List[LexiconHit]:
    """Convenience function: match text against all lexicons."""
    return get_lexicon_engine().match(text, lang=lang)


def match_lexicon_grouped(text: str, lang: Optional[str] = None,
                          min_confidence: float = 0.30) -> Dict[str, List[LexiconHit]]:
    """Convenience function: match and group by category."""
    return get_lexicon_engine().match_grouped(text, lang=lang, min_confidence=min_confidence)
