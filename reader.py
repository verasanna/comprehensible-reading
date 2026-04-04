"""
reader.py — text extraction and Spanish readability analysis.

Supports .epub (via ebooklib) and .pdf (via PyMuPDF / fitz).
All readability formulas are calibrated for Spanish.
"""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from pathlib import Path


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
    flesch: float = 0.0
    szigriszt: float = 0.0
    crawford: float = 0.0


@dataclass
class LanguageResult:
    lang: str = "unknown"
    lang_name: str = "Unknown"
    is_spanish: bool = False
    confidence: str = "low"   # "high" | "medium" | "low"
    warning: bool = True


@dataclass
class AnalysisResult:
    title: str = ""
    stats: TextStats = field(default_factory=TextStats)
    scores: ReadabilityScores = field(default_factory=ReadabilityScores)
    language: LanguageResult = field(default_factory=LanguageResult)


# ─────────────────────────────────────────────────────────────
# Text extraction
# ─────────────────────────────────────────────────────────────

def extract_epub(path: Path) -> tuple[str, str]:
    """Return (text, title) from an EPUB file."""
    import ebooklib
    from ebooklib import epub
    from html.parser import HTMLParser

    class _StripHTML(HTMLParser):
        def __init__(self):
            super().__init__()
            self.chunks: list[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "nav"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style", "nav"):
                self._skip = False

        def handle_data(self, data):
            if not self._skip:
                self.chunks.append(data)

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    title = book.title or path.stem

    chunks: list[str] = []
    total = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        parser = _StripHTML()
        parser.feed(item.get_content().decode("utf-8", errors="replace"))
        chunk = " ".join(parser.chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > 600_000:
            break

    return " ".join(chunks), title


def extract_pdf(path: Path) -> tuple[str, str]:
    """Return (text, title) from a PDF file using PyMuPDF."""
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    title = doc.metadata.get("title", "").strip() or path.stem

    chunks: list[str] = []
    total = 0
    max_pages = min(doc.page_count, 120)
    for i in range(max_pages):
        page_text = doc[i].get_text()
        chunks.append(page_text)
        total += len(page_text)
        if total > 600_000:
            break

    return " ".join(chunks), title


def extract_text(path: Path) -> tuple[str, str]:
    """Dispatch to the correct extractor based on file extension."""
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return extract_epub(path)
    elif suffix == ".pdf":
        return extract_pdf(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


# ─────────────────────────────────────────────────────────────
# Language detection
# ─────────────────────────────────────────────────────────────

_ES_MARKERS = {
    "que", "de", "el", "la", "en", "los", "las", "un", "una", "con",
    "por", "para", "se", "como", "más", "pero", "al", "del", "este",
    "esta", "también", "ya", "cuando", "muy", "todo", "sobre", "le",
    "su", "sus", "son", "hay", "lo", "me", "te", "nos", "yo", "si",
    "fue", "ser", "así", "sin", "entre", "hasta", "porque", "bien",
    "donde", "tanto", "durante", "dos", "tres",
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
_WORD_RE = re.compile(r"\b[a-záéíóúüñàâçèêëîïôùûüÿœæäöüß]{3,}\b", re.IGNORECASE)


def _score_markers(words: list[str], markers: set[str]) -> float:
    word_set = {w.lower() for w in words}
    return len(markers & word_set) / len(markers)


def detect_language(text: str) -> LanguageResult:
    sample = text[:8000]
    words = _WORD_RE.findall(sample)
    if len(words) < 30:
        return LanguageResult(lang="unknown", lang_name="Unknown",
                              is_spanish=False, confidence="low", warning=True)

    has_es_chars = bool(_ES_CHARS.search(sample))
    es_score = _score_markers(words, _ES_MARKERS) + (0.15 if has_es_chars else 0)
    es_pattern_boost = min(0.1, len(_ES_PATTERN.findall(sample)) / len(words))
    final_es = es_score + es_pattern_boost

    scores = {
        "es": final_es,
        "pt": _score_markers(words, _PT_MARKERS),
        "fr": _score_markers(words, _FR_MARKERS),
        "de": _score_markers(words, _DE_MARKERS),
    }
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_lang, top_score = ranked[0]
    _, second_score = ranked[1]

    margin = top_score - second_score
    confidence = "high" if margin > 0.08 else "medium" if margin > 0.03 else "low"
    is_spanish = top_lang == "es"

    lang_names = {"es": "Spanish", "pt": "Portuguese", "fr": "French", "de": "German"}
    return LanguageResult(
        lang=top_lang,
        lang_name=lang_names.get(top_lang, top_lang),
        is_spanish=is_spanish,
        confidence=confidence,
        warning=not is_spanish or confidence == "low",
    )


# ─────────────────────────────────────────────────────────────
# Spanish syllable counting
# ─────────────────────────────────────────────────────────────

_VOWELS = re.compile(r"[aeiouáéíóúü]", re.IGNORECASE)
_DIPHTHONG = re.compile(
    r"[aeoáéó][iuíú]|[iuíú][aeoáéó]|[iuíú][iuíú]", re.IGNORECASE
)
_WORD_CLEAN = re.compile(r"[^a-záéíóúüñ]", re.IGNORECASE)


def _syllables(word: str) -> int:
    word = _WORD_CLEAN.sub("", word.lower())
    if not word:
        return 0
    count = len(_VOWELS.findall(word))
    count -= len(_DIPHTHONG.findall(word))
    return max(1, count)


# ─────────────────────────────────────────────────────────────
# Stats and readability
# ─────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{2,}\b")
_SENTENCE_SPLIT = re.compile(r"[.!?]+")


def compute_stats(text: str) -> TextStats:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text)]
    sentences = [s for s in sentences if len(s.split()) >= 2]
    tokens = _TOKEN_RE.findall(text)

    n_words = len(tokens)
    n_sentences = max(1, len(sentences))
    n_syllables = sum(_syllables(w) for w in tokens)
    n_chars = sum(len(w) for w in tokens)
    n_poly = sum(1 for w in tokens if _syllables(w) >= 3)

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


def compute_scores(stats: TextStats) -> ReadabilityScores:
    s = stats
    return ReadabilityScores(
        # Flesch adapted for Spanish
        flesch=206.835 - 1.02 * s.avg_sent_len - 60.0 * s.avg_syllables_per_word,
        # Szigriszt–Pazos (Perspicuidad) — primary Spanish formula
        szigriszt=206.835 - 62.3 * s.avg_syllables_per_word - s.avg_sent_len,
        # Crawford — predicts school grade level in Spanish
        crawford=(-0.205 * s.avg_sent_len) + (4.41 * s.avg_syllables_per_word) - 3.40,
    )


# ─────────────────────────────────────────────────────────────
# Full analysis pipeline
# ─────────────────────────────────────────────────────────────

def analyse(path: Path) -> AnalysisResult:
    """Extract text, detect language, compute stats and scores."""
    text, title = extract_text(path)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 300:
        raise ValueError(
            "Not enough text could be extracted. "
            "The file may be scanned, encrypted, or image-based."
        )

    stats = compute_stats(text)
    scores = compute_scores(stats)
    language = detect_language(text)

    return AnalysisResult(title=title, stats=stats, scores=scores, language=language)
