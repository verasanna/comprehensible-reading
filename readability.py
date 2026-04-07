"""
readability.py — readability analysis pipeline.

Orchestrates: extraction → language detection → stats → scores.

Supports two formula sets:
  - Spanish: Flesch (adapted), Szigriszt–Pazos, Crawford
  - English: Flesch Reading Ease, Flesch–Kincaid Grade, Gunning Fog

All syllable counting is language-aware.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from pathlib import Path

import extraction
import language as lang_module


# ─────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────

@dataclass
class TextStats:
    total_words: int = 0
    total_sentences: int = 0
    total_syllables: int = 0
    total_chars: int = 0
    avg_sent_len: float = 0.0
    avg_syllables_per_word: float = 0.0
    avg_chars_per_word: float = 0.0
    polysyllabic_count: int = 0
    polysyllabic_pct: float = 0.0


@dataclass
class ReadabilityScores:
    # Spanish formulas (None if not applicable)
    flesch_es: float | None = None
    szigriszt: float | None = None
    crawford: float | None = None
    # English formulas (None if not applicable)
    flesch_en: float | None = None
    flesch_kincaid_grade: float | None = None
    gunning_fog: float | None = None


@dataclass
class AnalysisResult:
    title: str = ""
    author: str = ""
    stats: TextStats = field(default_factory=TextStats)
    scores: ReadabilityScores = field(default_factory=ReadabilityScores)
    language: lang_module.LanguageResult = field(default_factory=lang_module.LanguageResult)


# ─────────────────────────────────────────────────────────────
# Spanish syllable counting
# ─────────────────────────────────────────────────────────────

_ES_VOWELS = re.compile(r"[aeiouáéíóúü]", re.IGNORECASE)
_ES_DIPHTHONG = re.compile(
    r"[aeoáéó][iuíú]|[iuíú][aeoáéó]|[iuíú][iuíú]", re.IGNORECASE
)
_WORD_CLEAN_ES = re.compile(r"[^a-záéíóúüñ]", re.IGNORECASE)


def _syllables_es(word: str) -> int:
    word = _WORD_CLEAN_ES.sub("", word.lower())
    if not word:
        return 0
    count = len(_ES_VOWELS.findall(word))
    count -= len(_ES_DIPHTHONG.findall(word))
    return max(1, count)


# ─────────────────────────────────────────────────────────────
# English syllable counting
# ─────────────────────────────────────────────────────────────

_EN_VOWELS = re.compile(r"[aeiouy]+", re.IGNORECASE)
_WORD_CLEAN_EN = re.compile(r"[^a-z]", re.IGNORECASE)

_EN_SILENT_E = re.compile(r"[^aeiou]e$", re.IGNORECASE)
_EN_VOWEL_PAIR = re.compile(r"[aeiouy]{2}", re.IGNORECASE)

# Suffixes that add a syllable (e.g. "-ion", "-ious")
_EN_ADD_SYLLABLE = re.compile(
    r"(ia|io|ii|[^aeiou]ed$|[^aeiou]es$)", re.IGNORECASE
)


def _syllables_en(word: str) -> int:
    """Approximate English syllable count."""
    word = _WORD_CLEAN_EN.sub("", word.lower())
    if not word:
        return 0
    if len(word) <= 3:
        return 1

    # Count vowel groups
    count = len(_EN_VOWELS.findall(word))

    # Silent trailing 'e'
    if word.endswith("e") and len(word) > 2 and word[-2] not in "aeiou":
        count -= 1

    # Special patterns
    count += len(_EN_ADD_SYLLABLE.findall(word))

    return max(1, count)


# ─────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{2,}\b")
_SENTENCE_SPLIT = re.compile(r"[.!?]+")


def compute_stats(text: str, lang: str) -> TextStats:
    syllable_fn = _syllables_es if lang == "es" else _syllables_en

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text)]
    sentences = [s for s in sentences if len(s.split()) >= 2]
    tokens = _TOKEN_RE.findall(text)

    n_words = len(tokens)
    n_sentences = max(1, len(sentences))
    n_syllables = sum(syllable_fn(w) for w in tokens)
    n_chars = sum(len(w) for w in tokens)
    n_poly = sum(1 for w in tokens if syllable_fn(w) >= 3)

    return TextStats(
        total_words=n_words,
        total_sentences=n_sentences,
        total_syllables=n_syllables,
        total_chars=n_chars,
        avg_sent_len=n_words / n_sentences,
        avg_syllables_per_word=n_syllables / max(1, n_words),
        avg_chars_per_word=n_chars / max(1, n_words),
        polysyllabic_count=n_poly,
        polysyllabic_pct=(n_poly / max(1, n_words)) * 100,
    )


# ─────────────────────────────────────────────────────────────
# Scores
# ─────────────────────────────────────────────────────────────

def compute_scores(stats: TextStats, lang: str) -> ReadabilityScores:
    s = stats
    scores = ReadabilityScores()

    if lang == "es":
        # Flesch adapted for Spanish
        scores.flesch_es = 206.835 - 1.02 * s.avg_sent_len - 60.0 * s.avg_syllables_per_word
        # Szigriszt–Pazos (Perspicuidad) — gold standard for Spanish
        scores.szigriszt = 206.835 - 62.3 * s.avg_syllables_per_word - s.avg_sent_len
        # Crawford — predicts school grade level in Spanish
        scores.crawford = (-0.205 * s.avg_sent_len) + (4.41 * s.avg_syllables_per_word) - 3.40

    elif lang == "en":
        # Flesch Reading Ease (original English formula)
        scores.flesch_en = 206.835 - 1.015 * s.avg_sent_len - 84.6 * s.avg_syllables_per_word
        # Flesch–Kincaid Grade Level
        scores.flesch_kincaid_grade = 0.39 * s.avg_sent_len + 11.8 * s.avg_syllables_per_word - 15.59
        # Gunning Fog Index
        scores.gunning_fog = 0.4 * (s.avg_sent_len + s.polysyllabic_pct)

    return scores


# ─────────────────────────────────────────────────────────────
# Full pipeline
# ─────────────────────────────────────────────────────────────

def analyse(path: Path) -> AnalysisResult:
    """Extract text, detect language, compute stats and readability scores."""
    text, title, author = extraction.extract_text(path)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 300:
        raise ValueError(
            "Not enough text could be extracted. "
            "The file may be scanned, encrypted, or image-based."
        )

    detected = lang_module.detect(text)
    lang = detected.lang if detected.lang in ("es", "en") else "es"

    stats = compute_stats(text, lang)
    scores = compute_scores(stats, lang)

    return AnalysisResult(title=title, author=author, stats=stats, scores=scores, language=detected)
