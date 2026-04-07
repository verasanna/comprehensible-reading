"""
language.py — language detection for extracted book text.

Detects: Spanish, English, Portuguese, French, German.
Returns a LanguageResult with the detected language, confidence, and
whether the text is in a supported language with accurate readability formulas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────

@dataclass
class LanguageResult:
    lang: str = "unknown"           # ISO 639-1 code
    lang_name: str = "Unknown"
    is_supported: bool = False      # True if we have good formulas for it
    confidence: str = "low"        # "high" | "medium" | "low"
    warning: bool = True


# ─────────────────────────────────────────────────────────────
# Marker word sets
# ─────────────────────────────────────────────────────────────

_ES_MARKERS = {
    "que", "de", "el", "la", "en", "los", "las", "un", "una", "con",
    "por", "para", "se", "como", "más", "pero", "al", "del", "este",
    "esta", "también", "ya", "cuando", "muy", "todo", "sobre", "le",
    "su", "sus", "son", "hay", "lo", "me", "te", "nos", "yo", "si",
    "fue", "ser", "así", "sin", "entre", "hasta", "porque", "bien",
    "donde", "tanto", "durante", "dos", "tres",
}
_EN_MARKERS = {
    "the", "and", "that", "with", "for", "this", "from", "have", "not",
    "are", "was", "but", "they", "his", "her", "had", "she", "been",
    "when", "him", "all", "would", "there", "their", "what", "out",
    "about", "who", "which", "were", "into", "more", "time", "has",
    "said", "its", "will", "could", "then", "some", "than", "just",
    "like", "other", "only", "also", "over", "after", "back", "very",
}
_PT_MARKERS = {
    "que", "de", "o", "a", "os", "as", "em", "um", "uma", "com",
    "por", "para", "se", "como", "mais", "mas", "ao", "do", "da",
    "este", "esta", "também", "já", "quando", "muito", "todo",
    "sobre", "lhe", "seu", "seus", "são", "há", "me", "te", "nos",
    "eu", "foi", "ser", "assim", "sem", "entre", "até", "porque",
    "bem", "onde", "tanto", "durante",
}
_FR_MARKERS = {
    "que", "de", "le", "la", "les", "en", "un", "une", "avec", "par",
    "pour", "se", "comme", "plus", "mais", "au", "du", "cette", "ce",
    "aussi", "déjà", "quand", "très", "tout", "sur", "lui", "son",
    "ses", "sont", "il", "me", "te", "nous", "je", "été", "être",
    "ainsi", "sans", "entre", "parce", "bien", "où", "tant",
}
_DE_MARKERS = {
    "der", "die", "das", "und", "in", "den", "dem", "zu", "von",
    "mit", "ist", "auf", "für", "nicht", "sich", "des", "ein",
    "eine", "einer", "als", "auch", "an", "es", "im", "so", "war",
    "werden", "durch", "nach", "bei", "noch", "aus",
}

_ES_CHARS = re.compile(r"[áéíóúüñ¡¿]", re.IGNORECASE)
_ES_PATTERN = re.compile(
    r"\b(que|de|los|las|para|pero|con|por|como|más|también|cuando|todo"
    r"|sobre|sin|entre|hasta|porque|bien|donde)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"\b[a-záéíóúüñàâçèêëîïôùûüÿœæäöüßa-z]{3,}\b", re.IGNORECASE)

# Supported languages (have dedicated readability formulas)
_SUPPORTED = {"es", "en"}
_LANG_NAMES = {
    "es": "Spanish",
    "en": "English",
    "pt": "Portuguese",
    "fr": "French",
    "de": "German",
}


# ─────────────────────────────────────────────────────────────
# Detection
# ─────────────────────────────────────────────────────────────

def _score_markers(words: list[str], markers: set[str]) -> float:
    word_set = {w.lower() for w in words}
    return len(markers & word_set) / len(markers)


def detect(text: str) -> LanguageResult:
    """Detect the language of a text sample."""
    sample = text[:8000]
    words = _WORD_RE.findall(sample)

    if len(words) < 30:
        return LanguageResult(
            lang="unknown", lang_name="Unknown",
            is_supported=False, confidence="low", warning=True
        )

    has_es_chars = bool(_ES_CHARS.search(sample))
    es_score = _score_markers(words, _ES_MARKERS) + (0.15 if has_es_chars else 0)
    es_pattern_boost = min(0.1, len(_ES_PATTERN.findall(sample)) / max(1, len(words)))
    final_es = es_score + es_pattern_boost

    scores = {
        "es": final_es,
        "en": _score_markers(words, _EN_MARKERS),
        "pt": _score_markers(words, _PT_MARKERS),
        "fr": _score_markers(words, _FR_MARKERS),
        "de": _score_markers(words, _DE_MARKERS),
    }
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_lang, top_score = ranked[0]
    _, second_score = ranked[1]

    margin = top_score - second_score
    confidence = "high" if margin > 0.08 else "medium" if margin > 0.03 else "low"
    is_supported = top_lang in _SUPPORTED

    return LanguageResult(
        lang=top_lang,
        lang_name=_LANG_NAMES.get(top_lang, top_lang),
        is_supported=is_supported,
        confidence=confidence,
        warning=not is_supported or confidence == "low",
    )
